#!/usr/bin/env python3
import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cereal import car, messaging
from openpilot.common.conversions import Conversions as CV
from openpilot.common.params import Params
from openpilot.selfdrive.dragonpilot.mobile_api.server import MobileAPI, create_server, decode_param
from openpilot.system.hardware import HARDWARE
from openpilot.system.swaglog import cloudlog


DEFAULT_HOST = os.getenv("LEGACYPILOT_API_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("LEGACYPILOT_API_PORT", "8082"))
OFFROAD_ALERT_KEYS = (
  "Offroad_TemperatureTooHigh", "Offroad_ConnectivityNeededPrompt",
  "Offroad_ConnectivityNeeded", "Offroad_UpdateFailed", "Offroad_InvalidTime",
  "Offroad_IsTakingSnapshot", "Offroad_NeosUpdate", "Offroad_UnofficialHardware",
  "Offroad_StorageMissing", "Offroad_BadNvme", "Offroad_CarUnrecognized",
  "Offroad_NoFirmware", "Offroad_Recalibration",
)


class StatusProvider:
  def __init__(self, params: Params):
    self.params = params
    self.sm = messaging.SubMaster(["deviceState", "controlsState", "carState", "liveCalibration"])

  def _vehicle_name(self) -> Optional[str]:
    raw = self.params.get("CarParamsPersistent")
    if raw is None:
      return None
    try:
      return str(car.CarParams.from_bytes(raw).carFingerprint)
    except Exception:
      return None

  def status(self) -> Dict[str, Any]:
    # Drain pending messages without blocking the HTTP request.
    self.sm.update(0)
    device_state = self.sm["deviceState"]
    controls_state = self.sm["controlsState"]
    car_state = self.sm["carState"]
    calibration = self.sm["liveCalibration"]

    cpu_temps = list(device_state.cpuTempC)
    alert_parts = [controls_state.alertText1, controls_state.alertText2]
    alert = " — ".join(part for part in alert_parts if part) or None

    thermal_names = ("green", "yellow", "red", "danger")
    thermal_index = int(device_state.thermalStatus.raw)
    thermal_status = thermal_names[thermal_index] if 0 <= thermal_index < len(thermal_names) else "unknown"

    calibration_status = None
    calibration_progress = None
    calibration_pitch = None
    calibration_yaw = None
    if self.sm.rcv_frame["liveCalibration"] > 0:
      calibration_names = ("uncalibrated", "calibrated", "invalid", "recalibrating")
      calibration_index = int(calibration.calStatus.raw)
      calibration_status = calibration_names[calibration_index] if 0 <= calibration_index < len(calibration_names) else "unknown"
      calibration_progress = int(calibration.calPerc)
      rpy = list(calibration.rpyCalib)
      if len(rpy) == 3:
        calibration_pitch = math.degrees(float(rpy[1]))
        calibration_yaw = math.degrees(float(rpy[2]))

    gpu_temps = list(device_state.gpuTempC)
    messages = []
    for key in OFFROAD_ALERT_KEYS:
      raw = self.params.get(key)
      if raw is None:
        continue
      try:
        payload = json.loads(raw.decode("utf-8"))
        text = str(payload.get("text", ""))
        extra = str(payload.get("extra", ""))
        if extra:
          text = text.replace("%1", extra)
        if text:
          messages.append({"id": key, "text": text, "severity": int(payload.get("severity", 0))})
      except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        continue

    return {
      "deviceName": HARDWARE.get_device_type() or "OP device",
      "online": True,
      "onroad": bool(device_state.started),
      "engaged": bool(controls_state.enabled),
      "vehicle": self._vehicle_name(),
      "version": decode_param(self.params, "Version"),
      "branch": decode_param(self.params, "GitBranch"),
      "ipAddress": None,
      "thermalStatus": thermal_status,
      "cpuTempC": max(cpu_temps) if cpu_temps else None,
      "gpuTempC": max(gpu_temps) if gpu_temps else None,
      "memoryTempC": float(device_state.memoryTempC),
      "ambientTempC": float(device_state.ambientTempC),
      "memoryPercent": float(device_state.memoryUsagePercent),
      "storagePercent": 100.0 - float(device_state.freeSpacePercent),
      "speedKph": float(car_state.vEgo) * CV.MS_TO_KPH,
      "setSpeedKph": float(controls_state.vCruise),
      "alert": alert,
      "messages": messages,
      "calibrationStatus": calibration_status,
      "calibrationProgress": calibration_progress,
      "calibrationPitchDeg": calibration_pitch,
      "calibrationYawDeg": calibration_yaw,
      "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main() -> None:
  params = Params()
  api = MobileAPI(params, StatusProvider(params))
  server = create_server(DEFAULT_HOST, DEFAULT_PORT, api)
  cloudlog.info("mobile_api listening on %s:%d", DEFAULT_HOST, DEFAULT_PORT)
  try:
    server.serve_forever(poll_interval=0.5)
  finally:
    server.server_close()


if __name__ == "__main__":
  main()
