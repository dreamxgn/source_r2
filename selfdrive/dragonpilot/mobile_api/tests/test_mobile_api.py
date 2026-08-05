import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openpilot.selfdrive.dragonpilot.mobile_api.server import MobileAPI, create_server


class FakeParams:
  def __init__(self):
    self.values = {"dp_alka": b"0", "dp_lat_controller": b"2"}

  def get(self, key):
    return self.values.get(key)

  def put(self, key, value):
    self.values[key] = value.encode("utf-8")

  def remove(self, key):
    self.values.pop(key, None)


class FakeStatusProvider:
  def status(self):
    return {"deviceName": "test device", "online": True}

  def parameter_context(self):
    return {
      "hasCarParams": True,
      "experimentalLongitudinalAvailable": True,
      "hasLongitudinalControl": True,
      "isReleaseBranch": False,
    }


class TestMobileAPI(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.params = FakeParams()
    api = MobileAPI(params=cls.params, status_provider=FakeStatusProvider())
    cls.server = create_server("127.0.0.1", 0, api)
    cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
    cls.thread.start()
    cls.base_url = "http://127.0.0.1:%d" % cls.server.server_port

  @classmethod
  def tearDownClass(cls):
    cls.server.shutdown()
    cls.server.server_close()
    cls.thread.join(timeout=2)

  def request(self, path, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(self.base_url + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=2) as response:
      return response.status, json.loads(response.read())

  def test_health(self):
    status, body = self.request("/api/v1/health")
    self.assertEqual(status, 200)
    self.assertEqual(body, {"ok": True})

  def test_status(self):
    status, body = self.request("/api/v1/status")
    self.assertEqual(status, 200)
    self.assertEqual(body["deviceName"], "test device")
    self.assertTrue(body["online"])

  def test_get_params(self):
    status, body = self.request("/api/v1/params")
    self.assertEqual(status, 200)
    self.assertEqual(body["values"]["dp_alka"], "0")
    self.assertEqual(body["values"]["dp_lat_controller"], "2")
    self.assertIn("states", body)

  def test_dependent_setting_visibility(self):
    self.request("/api/v1/params/dp_device_auto_shutdown", "PUT", {"value": "0"})
    _, body = self.request("/api/v1/params")
    self.assertFalse(body["states"]["dp_device_auto_shutdown_in"]["visible"])

    self.request("/api/v1/params/dp_device_auto_shutdown", "PUT", {"value": "1"})
    _, body = self.request("/api/v1/params")
    self.assertTrue(body["states"]["dp_device_auto_shutdown_in"]["visible"])

  def test_old_model_rejected_while_openpilot_longitudinal_enabled(self):
    self.request("/api/v1/params/ExperimentalMode", "PUT", {"value": "1"})
    self.request("/api/v1/params/ExperimentalLongitudinalEnabled", "PUT", {"value": "1"})
    with self.assertRaises(HTTPError) as context:
      self.request("/api/v1/params/dp_0813", "PUT", {"value": "1"})
    self.assertEqual(context.exception.code, 400)
    context.exception.close()
    _, body = self.request("/api/v1/params")
    self.assertEqual(body["values"]["ExperimentalLongitudinalEnabled"], "1")
    self.assertFalse(body["states"]["dp_0813"]["enabled"])

    self.request("/api/v1/params/ExperimentalLongitudinalEnabled", "PUT", {"value": "0"})
    self.request("/api/v1/params/dp_0813", "PUT", {"value": "1"})
    _, body = self.request("/api/v1/params")
    self.assertNotIn("ExperimentalMode", body["values"])
    self.assertEqual(body["values"]["ExperimentalLongitudinalEnabled"], "0")
    self.assertFalse(body["states"]["ExperimentalMode"]["visible"])

    # A device left in the inconsistent state by an older version must still
    # allow the legacy model to be turned off.
    self.params.put("ExperimentalLongitudinalEnabled", "1")
    _, body = self.request("/api/v1/params")
    self.assertTrue(body["states"]["dp_0813"]["enabled"])
    self.request("/api/v1/params/dp_0813", "PUT", {"value": "0"})
    _, body = self.request("/api/v1/params")
    self.assertTrue(body["states"]["ExperimentalLongitudinalEnabled"]["visible"])

  def test_put_param(self):
    status, body = self.request("/api/v1/params/dp_alka", "PUT", {"value": "1"})
    self.assertEqual(status, 200)
    self.assertEqual(body, {"value": "1"})
    self.assertEqual(self.params.values["dp_alka"], b"1")

  def test_unknown_param_is_rejected(self):
    with self.assertRaises(HTTPError) as context:
      self.request("/api/v1/params/not_a_param", "PUT", {"value": "1"})
    self.assertEqual(context.exception.code, 404)
    context.exception.close()

  def test_non_string_value_is_rejected(self):
    with self.assertRaises(HTTPError) as context:
      self.request("/api/v1/params/dp_alka", "PUT", {"value": True})
    self.assertEqual(context.exception.code, 400)
    context.exception.close()

  def test_reset_calibration(self):
    self.params.values["CalibrationParams"] = b"calibration"
    self.params.values["LiveTorqueParameters"] = b"torque"
    status, body = self.request("/api/v1/actions/reset-calibration", "POST")
    self.assertEqual(status, 200)
    self.assertEqual(body, {"ok": True})
    self.assertNotIn("CalibrationParams", self.params.values)
    self.assertNotIn("LiveTorqueParameters", self.params.values)
    self.assertEqual(self.params.values["ResetCalibration"], b"1")


if __name__ == "__main__":
  unittest.main()
