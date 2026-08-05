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


class FakeStatusProvider:
  def status(self):
    return {"deviceName": "test device", "online": True}


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


if __name__ == "__main__":
  unittest.main()
