import json
import threading
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from cereal import car
from PIL import Image

from openpilot.selfdrive.webui.webui import (REPO_ROOT, RoadCameraStream, WebUI,
                                             create_server)


class FakeParams:
  def __init__(self):
    self.values = {"dp_alka": b"0", "dp_0813": b"1", "dp_car_list": b'{"cars":["TEST CAR"]}'}
  def get(self, key): return self.values.get(key)
  def get_bool(self, key):
    if key.endswith("Lock") and key not in ("RecordFrontLock",):
      raise KeyError(key)
    return self.values.get(key) == b"1"
  def put(self, key, value): self.values[key] = value.encode("utf-8")
  def put_bool(self, key, value): self.values[key] = b"1" if value else b"0"
  def remove(self, key): self.values.pop(key, None)


class FakeSM:
  def __init__(self):
    status = type("Status", (), {"raw": 2})()
    calibration = type("Calibration", (), {"calStatus": status, "calPerc": 100, "rpyCalib": [0.0, 0.16, -0.08]})()
    controls = type("C", (), {"enabled": True, "active": True, "vCruise": 100.0, "vCruiseCluster": 0.0, "alertText1": "Keep hands on wheel", "alertText2": "Driver attention required"})()
    car_state = type("CarState", (), {"vEgo": 20.0, "vEgoCluster": 0.0})()
    event_name = type("EventName", (), {"__str__": lambda self: "steerTempUnavailable"})()
    event = type("Event", (), {"name": event_name})()
    self.data = {"deviceState": type("D", (), {"started": True})(), "controlsState": controls, "liveCalibration": calibration, "carState": car_state, "carEvents": [event]}
    self.rcv_frame = {"deviceState": 1, "controlsState": 1, "liveCalibration": 1, "carState": 1, "carEvents": 1}
  def update(self, _): pass
  def __getitem__(self, key): return self.data[key]


class TestWebUI(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.params = FakeParams(); api = WebUI(cls.params); api.sm = FakeSM()
    cls.server = create_server("127.0.0.1", 0, api)
    cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
    cls.url = "http://127.0.0.1:%d" % cls.server.server_port
  @classmethod
  def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.thread.join(2)
  def request(self, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(self.url + path, data=data, method=method, headers={"Content-Type":"application/json"}), timeout=2) as r:
      return r.status, json.loads(r.read()) if path.startswith("/api/") else r.read()
  def test_index_and_config(self):
    self.assertEqual(self.request("/")[0], 200)
    status, data = self.request("/api/v1/config"); self.assertEqual(status, 200); self.assertTrue(data["groups"])
    self.assertTrue(data["states"]["OpenpilotEnabledToggle"]["enabled"])
    self.assertFalse(data["homeModeControlsVisible"])

  def test_home_modes_require_new_model_and_openpilot_longitudinal(self):
    saved = dict(self.params.values)
    try:
      cp = car.CarParams.new_message()
      cp.experimentalLongitudinalAvailable = True
      self.params.values["CarParamsPersistent"] = cp.to_bytes()
      self.params.values["dp_0813"] = b"0"
      self.params.values["ExperimentalLongitudinalEnabled"] = b"1"
      _, data = self.request("/api/v1/config")
      self.assertTrue(data["homeModeControlsVisible"])
      self.params.values["ExperimentalLongitudinalEnabled"] = b"0"
      _, data = self.request("/api/v1/config")
      self.assertFalse(data["homeModeControlsVisible"])
      self.params.values["dp_0813"] = b"1"
      self.params.values["ExperimentalLongitudinalEnabled"] = b"1"
      _, data = self.request("/api/v1/config")
      self.assertFalse(data["homeModeControlsVisible"])
    finally:
      self.params.values = saved
  def test_write_validation(self):
    self.request("/api/v1/params/dp_alka", "PUT", {"value":"1"}); self.assertEqual(self.params.values["dp_alka"], b"1")
    self.request("/api/v1/params/LongitudinalPersonality", "PUT", {"value":"2"}); self.assertEqual(self.params.values["LongitudinalPersonality"], b"2")
    self.request("/api/v1/params/dp_long_accel_profile", "PUT", {"value":"3"}); self.assertEqual(self.params.values["dp_long_accel_profile"], b"3")
    with self.assertRaises(HTTPError): self.request("/api/v1/params/dp_alka", "PUT", {"value":"bad"})
  def test_car_selection(self):
    self.request("/api/v1/actions/select-car", "POST", {"value":"TEST CAR"}); self.assertEqual(self.params.values["dp_car_assigned"], b"TEST CAR")

  def test_calibration_angles_and_adjustment(self):
    _, data = self.request("/api/v1/config")
    self.assertAlmostEqual(data["calibration"]["pitchDeg"], 9.1673, places=3)
    self.assertAlmostEqual(data["calibration"]["yawDeg"], -4.5836, places=3)
    self.assertEqual(data["calibration"]["adjustment"], ["left", "up"])

  def test_driving_overview(self):
    _, data = self.request("/api/v1/config")
    self.assertEqual(data["driving"]["status"], "ACTIVE")
    self.assertAlmostEqual(data["driving"]["speedKph"], 72.0)
    self.assertEqual(data["driving"]["setSpeedKph"], 100.0)
    self.assertEqual(data["driving"]["alertText1"], "Keep hands on wheel")
    self.assertEqual(data["driving"]["events"], ["steerTempUnavailable"])

  def test_road_camera_jpeg_encoding(self):
    # Two BGR rows with padding exercise the VisionIPC stride handling.
    buf = type("Buffer", (), {"width": 2, "height": 2, "stride": 8,
                               "data": np.array([0, 0, 255, 0, 255, 0, 0, 0,
                                                 255, 0, 0, 255, 255, 255, 0, 0],
                                                dtype=np.uint8)})()
    encoded = RoadCameraStream.encode(buf)
    image = Image.open(BytesIO(encoded))
    self.assertEqual(image.size, (2, 2))
    self.assertEqual(image.format, "JPEG")

  def test_road_camera_mjpeg_endpoint(self):
    class FakeRoadStream(RoadCameraStream):
      @staticmethod
      def frames():
        yield b"jpeg-frame"

    server = create_server("127.0.0.1", 0, WebUI(self.params), FakeRoadStream())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
      url = "http://127.0.0.1:%d/api/v1/road-camera.mjpeg" % (
        server.server_port,
      )
      with urlopen(url, timeout=2) as response:
        body = response.read()
        self.assertIn(
          "multipart/x-mixed-replace", response.headers["Content-Type"]
        )
        self.assertIn(b"Content-Type: image/jpeg", body)
        self.assertIn(b"jpeg-frame", body)
    finally:
      server.shutdown()
      server.server_close()
      thread.join(2)

  def test_pull_update_uses_repository_root_without_lfs(self):
    def fake_run(command, **kwargs):
      self.assertEqual(command[:3], ["git", "-C", str(REPO_ROOT)])
      self.assertEqual(kwargs["cwd"], str(REPO_ROOT))
      self.assertEqual(kwargs["env"]["GIT_LFS_SKIP_SMUDGE"], "1")
      return type("Result", (), {"stdout": "abc123\n", "stderr": ""})()
    with patch("openpilot.selfdrive.webui.webui.subprocess.run", side_effect=fake_run) as run:
      self.assertEqual(WebUI._git("rev-parse", "--short", "HEAD"), "abc123")
      with self.assertRaises(HTTPError):
        self.request("/api/v1/actions/pull-update", "POST", {})
      self.assertEqual(run.call_count, 1)

  def test_car_list_falls_back_when_manager_has_not_started(self):
    saved = self.params.values.pop("dp_car_list")
    try:
      _, data = self.request("/api/v1/config")
      self.assertGreater(len(data["device"]["cars"]), 0)
    finally:
      self.params.values["dp_car_list"] = saved


if __name__ == "__main__": unittest.main()
