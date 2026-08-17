import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openpilot.selfdrive.webui.webui import WebUI, create_server


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
    self.data = {"deviceState": type("D", (), {"started": False})(), "controlsState": type("C", (), {"enabled": False})()}
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
  def test_write_validation(self):
    self.request("/api/v1/params/dp_alka", "PUT", {"value":"1"}); self.assertEqual(self.params.values["dp_alka"], b"1")
    with self.assertRaises(HTTPError): self.request("/api/v1/params/dp_alka", "PUT", {"value":"bad"})
  def test_car_selection(self):
    self.request("/api/v1/actions/select-car", "POST", {"value":"TEST CAR"}); self.assertEqual(self.params.values["dp_car_assigned"], b"TEST CAR")

  def test_car_list_falls_back_when_manager_has_not_started(self):
    saved = self.params.values.pop("dp_car_list")
    try:
      _, data = self.request("/api/v1/config")
      self.assertGreater(len(data["device"]["cars"]), 0)
    finally:
      self.params.values["dp_car_list"] = saved


if __name__ == "__main__": unittest.main()
