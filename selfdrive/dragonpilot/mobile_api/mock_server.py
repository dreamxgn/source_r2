#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
from typing import Any, Dict

from openpilot.selfdrive.dragonpilot.mobile_api.server import MobileAPI, SUPPORTED_PARAMS, create_server


class MemoryParams:
  def __init__(self):
    self.values = {key: b"0" for key in SUPPORTED_PARAMS}
    self.values.update({
      "dp_0813": b"1",
      "dp_device_auto_shutdown_in": b"30",
      "dp_lat_lane_change_assist_speed": b"20",
      "dp_logging": b"1",
    })

  def get(self, key: str):
    return self.values.get(key)

  def put(self, key: str, value: str) -> None:
    self.values[key] = value.encode("utf-8")

  def remove(self, key: str) -> None:
    self.values.pop(key, None)


class MockStatusProvider:
  def status(self) -> Dict[str, Any]:
    return {
      "deviceName": "Desktop OP simulator",
      "online": True,
      "onroad": False,
      "engaged": False,
      "vehicle": "TOYOTA RAV4 2019",
      "version": "0.8.16-r2-mock",
      "branch": "main",
      "ipAddress": None,
      "thermalStatus": "green",
      "cpuTempC": 54.0,
      "gpuTempC": 51.5,
      "memoryTempC": 48.2,
      "ambientTempC": 35.6,
      "memoryPercent": 42.0,
      "storagePercent": 36.0,
      "speedKph": 0.0,
      "setSpeedKph": 0.0,
      "alert": None,
      "messages": [{
        "id": "Offroad_Recalibration",
        "text": "检测到设备安装位置变化，请确认设备和支架固定牢固。",
        "severity": 0,
      }],
      "calibrationStatus": "calibrated",
      "calibrationProgress": 100,
      "calibrationPitchDeg": 1.24,
      "calibrationYawDeg": -0.38,
      "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main() -> None:
  parser = argparse.ArgumentParser(description="Desktop mock for the Legacypilot mobile API")
  parser.add_argument("--host", default="0.0.0.0")
  parser.add_argument("--port", type=int, default=8082)
  args = parser.parse_args()

  api = MobileAPI(MemoryParams(), MockStatusProvider())
  server = create_server(args.host, args.port, api)
  print("Mock mobile API listening on http://%s:%d" % (args.host, args.port), flush=True)
  try:
    server.serve_forever(poll_interval=0.5)
  except KeyboardInterrupt:
    pass
  finally:
    server.server_close()


if __name__ == "__main__":
  main()
