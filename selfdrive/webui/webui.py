#!/usr/bin/env python3
import json
import logging
import math
import mimetypes
import os
import subprocess
import threading
import time
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
from urllib.parse import unquote, urlsplit

import numpy as np
from cereal import car, log, messaging
from cereal.visionipc import VisionIpcClient, VisionStreamType
from openpilot.common.params import Params
from openpilot.system.hardware import HARDWARE
from PIL import Image


LOG = logging.getLogger("webui")
HOST = os.getenv("LEGACYPILOT_WEBUI_HOST", "0.0.0.0")
PORT = int(os.getenv("LEGACYPILOT_WEBUI_PORT", "8082"))
STATIC_ROOT = Path(__file__).resolve().parent / "static"
REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_REQUEST_BODY = 4096
PITCH_LIMITS = (-0.09074112085129739, 0.14907572052989657)
YAW_LIMITS = (-0.06912048084718224, 0.06912048084718235)
ROAD_STREAM_SIZE = (640, 480)
ROAD_STREAM_FPS = 5.0
ROAD_STREAM_QUALITY = 55
MJPEG_BOUNDARY = "legacypilotframe"
ROAD_STREAM_RESAMPLE = getattr(Image, "Resampling", Image).BILINEAR


class RoadCameraStream:
  """On-demand, low-rate MJPEG preview of camerad's RGB road stream."""
  def frames(self) -> Iterator[bytes]:
    try:
      yield from self._frames()
    except Exception:
      LOG.exception("road camera stream failed")

  def _frames(self) -> Iterator[bytes]:
    client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_RGB_ROAD, True)
    connect_deadline = time.monotonic() + 10.0
    while not client.connect(False):
      if time.monotonic() >= connect_deadline:
        return
      time.sleep(0.1)

    frame_interval = 1.0 / ROAD_STREAM_FPS
    last_frame_time = 0.0
    missed_frames = 0
    while True:
      buf = client.recv(1000)
      if buf is None:
        missed_frames += 1
        if missed_frames >= 5:
          return
        continue
      missed_frames = 0

      now = time.monotonic()
      if now - last_frame_time < frame_interval:
        continue
      last_frame_time = now
      yield self.encode(buf)

  @staticmethod
  def encode(buf) -> bytes:
    # RGB VisionIPC buffers on these devices are stored as interleaved BGR.
    # Convert through numpy like camerad/snapshot.py does. Older device Pillow
    # builds do not reliably accept VisionBuf's writable numpy view in
    # Image.frombuffer().
    rows = np.asarray(buf.data)[:buf.stride * buf.height].reshape(
      buf.height, buf.stride
    )
    bgr = rows[:, :buf.width * 3].reshape(buf.height, buf.width, 3)
    image = Image.fromarray(bgr[:, :, ::-1])
    # EON images can carry an older Pillow without the Image.Resampling enum.
    image.thumbnail(ROAD_STREAM_SIZE, ROAD_STREAM_RESAMPLE)
    output = BytesIO()
    image.save(output, "JPEG", quality=ROAD_STREAM_QUALITY)
    return output.getvalue()


# This is the web equivalent of settings.cc/settings_dp.cc. Values remain
# strings because that is the on-disk Params representation used by Qt.
CONTROL_GROUPS = [
  {"id": "toggles", "label": "Toggles", "controls": [
    {"key": "OpenpilotEnabledToggle", "title": "Enable openpilot", "type": "toggle", "description": "Use the openpilot system for adaptive cruise control and lane keep driver assistance. Your attention is required at all times to use this feature. Changing this setting takes effect when the car is powered off."},
    {"key": "dp_0813", "title": "Use 0.8.13.1 Driving Model", "type": "toggle", "description": "When enabled, openpilot will use the good old driving model from 0.8.13.1. For safety reason, vision only openpilot longitudinal will be disabled. Reboot required."},
    {"key": "dp_logging", "title": "Enable Logging", "type": "toggle", "description": "When enabled, openpilot will log your car stats as well as all the camera footages. Reboot required."},
    {"key": "ExperimentalLongitudinalEnabled", "title": "openpilot Longitudinal Control (Alpha)", "type": "toggle", "description": "WARNING: openpilot longitudinal control is in alpha for this car and will disable Automatic Emergency Braking (AEB)."},
    {"key": "ExperimentalMode", "title": "Experimental Mode", "type": "toggle", "description": "Enables alpha-level end-to-end longitudinal control and the new driving visualization."},
    {"key": "DisengageOnAccelerator", "title": "Disengage on Accelerator Pedal", "type": "toggle", "description": "When enabled, pressing the accelerator pedal will disengage openpilot."},
    {"key": "LongitudinalPersonality", "title": "Driving Personality", "type": "choice", "choices": ["Aggressive", "Standard", "Relaxed"], "description": "Standard is recommended. Aggressive follows closer; relaxed stays further away."},
    {"key": "IsLdwEnabled", "title": "Enable Lane Departure Warnings", "type": "toggle", "description": "Receive alerts when the vehicle drifts over a detected lane line without a turn signal."},
    {"key": "IsRhdDetected", "title": "Enable Right-Hand Drive", "type": "toggle", "description": "Use left-hand traffic conventions and monitor the right driver seat."},
    {"key": "RecordFront", "title": "Record and Upload Driver Camera", "type": "toggle", "description": "Upload driver-facing camera data to help improve driver monitoring."},
    {"key": "IsMetric", "title": "Use Metric System", "type": "toggle", "description": "Display speed in km/h instead of mph."},
  ]},
  {"id": "dragonpilot", "label": "dragonpilot", "controls": [
    {"section": "🐉 Ctrl - Overall 🐉"},
    {"key": "dp_car_dashcam_mode_removal", "title": "Dashcam Mode Removal", "type": "toggle", "description": "Force-enable openpilot control when the vehicle is not fully supported. USE AT YOUR OWN RISK. Reboot required."},
    {"section": "🐉 Ctrl - Lateral 🐉"},
    {"key": "dp_alka", "title": "Enable ALKA", "type": "toggle", "description": "Keep lateral control on whenever ACC MAIN is on. Reboot required."},
    {"key": "dp_lat_controller", "title": "Lateral Controller", "type": "choice", "choices": ["DEFAULT", "INDI", "LQR"], "description": "Change the lateral controller. USE AT YOUR OWN RISK. Reboot required."},
    {"key": "dp_lat_lane_priority_mode", "title": "Enable Lane Priority Mode", "type": "toggle", "description": "Use lane lines when reliable and fall back to laneless mode automatically."},
    {"key": "dp_lat_lane_priority_mode_speed_based", "title": "Only When Drive Above", "type": "number", "min": 0, "max": 120, "step": 1, "suffix": " kph", "zeroText": "All Speed", "visibleWhen": ["dp_lat_lane_priority_mode", "1"], "description": "Use lane lines only above this speed; zero means all speeds."},
    {"key": "dp_lat_lane_change_assist_speed", "title": "Lane Change Assist Activate Speed", "type": "number", "min": 0, "max": 80, "step": 1, "suffix": " mph", "zeroText": "Off", "description": "Adjust lane change assistance activation speed."},
    {"section": "🐉 Ctrl - Longitudinal 🐉"},
    {"key": "dp_long_use_df_tune", "title": "Enable Dynamic Following", "type": "toggle", "description": "Dynamically adjust following distance using Driving Personality."},
    {"key": "dp_long_use_krkeegen_tune", "title": "Enable krkeegan Tune (SNG Boost)", "type": "toggle", "description": "Apply an offset to request acceleration earlier from a stop."},
    {"key": "dp_long_de2e", "title": "Enable Dynamic End-to-End Longitudinal Control", "type": "toggle", "description": "Dynamically switch between End-to-End and ACC modes."},
    {"key": "dp_mapd_vision_turn_control", "title": "Enable Turn Speed Control - Vision", "type": "toggle", "description": "Estimate an appropriate turn speed from camera path predictions."},
    {"key": "dp_long_accel_profile", "title": "Acceleration Profile", "type": "choice", "choices": ["OP", "ECO", "NOR", "SPT"], "description": "Select stock, eco, normal, or sport acceleration."},
    {"key": "dp_mapd", "title": "Enable MapD", "type": "toggle", "description": "Display road name and speed limit. Reboot required."},
    {"key": "dp_long_personality_btn", "title": "On-Screen Personality Button", "type": "toggle", "description": "Display an on-road personality button."},
    {"key": "dp_long_accel_btn", "title": "On-Screen Accel Button", "type": "toggle", "description": "Display an on-road acceleration profile button."},
    {"section": "🐉 Toyota / Lexus 🐉"},
    {"key": "dp_toyota_sng", "title": "Enable Stop and Go (SnG) Hack", "type": "toggle", "description": "Stop sending standstill when fully stopped. Only works on some vehicles. Reboot required."},
    {"key": "dp_toyota_enhanced_bsm", "title": "Enable Enhanced BSM", "type": "toggle", "description": "Use debugging CAN messages for unfiltered blind-spot signals. Reboot required."},
    {"key": "dp_toyota_auto_lock", "title": "Enable Door Auto Locking", "type": "toggle", "description": "Attempt to lock doors above 10 km/h. Reboot required."},
    {"key": "dp_toyota_auto_unlock", "title": "Enable Door Auto Unlocking", "type": "toggle", "description": "Attempt to unlock doors when shifting to P. Reboot required."},
    {"key": "dp_toyota_zss", "title": "Enable Zorro-Steering-Sensor (ZSS) Support", "type": "toggle", "description": "Use ZSS output. Do not enable unless ZSS is installed. Reboot required."},
    {"section": "🐉 Hyundai / Kia / Genesis 🐉"},
    {"key": "dp_hkg_min_steer_speed_bypass", "title": "Enable Minimum Steer Speed Bypass", "type": "toggle", "description": "Allow steering control down to zero speed. An MDPS harness may be required."},
    {"section": "🐉 VW / Skoda / Audi 🐉"},
    {"key": "dp_vag_timebomb_bypass", "title": "Enable Lateral Control Timebomb Bypass", "type": "toggle", "description": "Temporarily disable and resume lateral control around the stock time limit."},
    {"section": "🐉 Device 🐉"},
    {"key": "dp_device_disable_temp_check", "title": "Disable Temp Check", "type": "toggle", "description": "Disable device temperature checks. An overheated device may shut down or lag. Reboot required."},
    {"key": "dp_device_no_ir_ctrl", "title": "Disable IR", "type": "toggle", "description": "Disable infrared illumination. Reboot required."},
    {"key": "dp_device_auto_shutdown", "title": "Enable Auto Shutdown", "type": "toggle", "description": "Automatically shut down the device. Reboot required."},
    {"key": "dp_device_auto_shutdown_in", "title": "Auto Shutdown In", "type": "number", "min": 0, "max": 600, "step": 1, "suffix": " mins", "zeroText": "Immediately", "visibleWhen": ["dp_device_auto_shutdown", "1"], "description": "Adjust the shutdown waiting period."},
    {"key": "dp_device_display_off_mode", "title": "Display Mode", "type": "choice", "choices": ["Standard", "On-Road", "MAIN", "OP"], "description": "Choose when the device display turns off. Reboot required."},
    {"key": "dp_device_audible_alert_mode", "title": "Audible Alert Mode", "type": "choice", "choices": ["Standard", "Warning", "Off"], "description": "Choose standard sounds, warnings only, or no sound."},
    {"action": "reset-configuration", "title": "Reset Configuration", "button": "RESET"},
  ]},
]

CONTROL_BY_KEY = {c["key"]: c for group in CONTROL_GROUPS for c in group["controls"] if "key" in c}


class WebUI:
  def __init__(self, params: Any):
    self.params = params
    self.sm = messaging.SubMaster(["deviceState", "controlsState", "liveCalibration", "carState", "carEvents"])
    self.update_lock = threading.Lock()

  def document(self) -> Dict[str, Any]:
    self.sm.update(0)
    values = {}
    states = {}
    for key in CONTROL_BY_KEY:
      raw = self.params.get(key)
      if raw is not None:
        values[key] = raw.decode("utf-8", errors="replace")
      states[key] = {"enabled": not self._get_bool(key + "Lock"), "visible": True}

    old_model = values.get("dp_0813") == "1"
    has_long = False
    states["ExperimentalMode"]["visible"] = not old_model
    states["ExperimentalLongitudinalEnabled"]["visible"] = False
    cp_raw = self.params.get("CarParamsPersistent")
    if not old_model and cp_raw:
      try:
        cp = car.CarParams.from_bytes(cp_raw)
        states["ExperimentalLongitudinalEnabled"]["visible"] = bool(cp.experimentalLongitudinalAvailable) and not self.params.get_bool("IsReleaseBranch")
        has_long = self.params.get_bool("ExperimentalLongitudinalEnabled") if cp.experimentalLongitudinalAvailable else bool(cp.openpilotLongitudinalControl)
        states["ExperimentalMode"]["enabled"] = states["ExperimentalMode"]["enabled"] and has_long
        states["LongitudinalPersonality"]["enabled"] = states["LongitudinalPersonality"]["enabled"] and has_long
      except Exception:
        pass
    states["dp_0813"]["enabled"] = states["dp_0813"]["enabled"] and (old_model or values.get("ExperimentalLongitudinalEnabled") != "1")

    device_state = self.sm["deviceState"]
    controls_state = self.sm["controlsState"]
    has_device_state = getattr(self.sm, "rcv_frame", {}).get("deviceState", 0) > 0
    cpu_temps = list(getattr(device_state, "cpuTempC", [])) if has_device_state else []
    gpu_temps = list(getattr(device_state, "gpuTempC", [])) if has_device_state else []
    network_type = getattr(getattr(device_state, "networkType", None), "raw", 0)
    network_names = ("--", "Wi-Fi", "ETH", "2G", "3G", "LTE", "5G")
    network_strength = int(getattr(getattr(device_state, "networkStrength", None), "raw", 0))
    calibration = self._calibration()
    driving = self._driving(device_state, controls_state)
    return {
      "groups": CONTROL_GROUPS,
      "values": values,
      "states": states,
      "device": {
        "name": HARDWARE.get_device_type() or "openpilot",
        "dongleId": self._decode("DongleId") or "N/A",
        "serial": self._decode("HardwareSerial") or "N/A",
        "version": self._decode("Version") or "N/A",
        "branch": self._decode("GitBranch") or "N/A",
        "onroad": bool(device_state.started),
        "engaged": bool(controls_state.enabled),
        "car": self._decode("dp_car_assigned") or "[AUTO SELECT]",
        "cars": self._car_list(),
        "cpuTempC": max(cpu_temps) if cpu_temps else None,
        "gpuTempC": max(gpu_temps) if gpu_temps else None,
        "memoryPercent": float(getattr(device_state, "memoryUsagePercent", 0.0)) if has_device_state else None,
        "storagePercent": 100.0 - float(getattr(device_state, "freeSpacePercent", 100.0)) if has_device_state else None,
        "networkType": network_names[network_type] if 0 <= network_type < len(network_names) else "--",
        "networkStrength": network_strength,
      },
      "calibration": calibration,
      "driving": driving,
      "homeModeControlsVisible": (not old_model) and has_long,
    }

  def _driving(self, device_state, controls_state):
    frames = getattr(self.sm, "rcv_frame", {})
    has_controls = frames.get("controlsState", 0) > 0
    has_car_state = frames.get("carState", 0) > 0
    car_state = self.sm["carState"]
    v_ego_cluster = float(getattr(car_state, "vEgoCluster", 0.0)) if has_car_state else 0.0
    v_ego = v_ego_cluster if v_ego_cluster != 0.0 else float(getattr(car_state, "vEgo", 0.0))
    v_cruise_cluster = float(getattr(controls_state, "vCruiseCluster", 0.0)) if has_controls else 0.0
    v_cruise = v_cruise_cluster if v_cruise_cluster != 0.0 else float(getattr(controls_state, "vCruise", 0.0))
    set_speed = v_cruise if has_controls and 0.0 < v_cruise < 255.0 else None
    alert_text_1 = str(getattr(controls_state, "alertText1", "")) if has_controls else ""
    alert_text_2 = str(getattr(controls_state, "alertText2", "")) if has_controls else ""
    events = []
    if frames.get("carEvents", 0) > 0:
      events = [str(getattr(event, "name", "")) for event in self.sm["carEvents"] if getattr(event, "name", None) is not None]
    onroad = bool(device_state.started)
    active = bool(getattr(controls_state, "active", False)) if has_controls else False
    enabled = bool(getattr(controls_state, "enabled", False)) if has_controls else False
    status = "OFFROAD"
    if onroad:
      status = "ACTIVE" if active else "OVERRIDE" if enabled else "STANDBY"
    return {
      "available": has_controls and has_car_state,
      "speedKph": max(0.0, v_ego * 3.6) if has_car_state else None,
      "setSpeedKph": set_speed,
      "status": status,
      "alertText1": alert_text_1,
      "alertText2": alert_text_2,
      "events": events[:6],
    }

  def _calibration(self):
    calibration = None
    if getattr(self.sm, "rcv_frame", {}).get("liveCalibration", 0) > 0:
      calibration = self.sm["liveCalibration"]
    else:
      cached = self.params.get("CalibrationParams")
      if cached:
        try:
          calibration = log.Event.from_bytes(cached).liveCalibration
        except Exception:
          pass
    if calibration is None:
      return {"available": False, "status": "Waiting for data", "progress": 0,
              "pitchDeg": None, "yawDeg": None, "adjustment": []}

    rpy = list(getattr(calibration, "rpyCalib", []))
    pitch = float(rpy[1]) if len(rpy) == 3 else None
    yaw = float(rpy[2]) if len(rpy) == 3 else None
    status_raw = int(getattr(getattr(calibration, "calStatus", None), "raw", 0))
    status_names = ("Calibrating", "Calibrated", "Invalid calibration", "Recalibrating")
    adjustment = []
    if yaw is not None:
      if yaw <= YAW_LIMITS[0]:
        adjustment.append("left")
      elif yaw >= YAW_LIMITS[1]:
        adjustment.append("right")
    if pitch is not None:
      if pitch <= PITCH_LIMITS[0]:
        adjustment.append("down")
      elif pitch >= PITCH_LIMITS[1]:
        adjustment.append("up")
    return {
      "available": pitch is not None and yaw is not None,
      "status": status_names[status_raw] if 0 <= status_raw < len(status_names) else "Unknown",
      "progress": max(0, min(100, int(getattr(calibration, "calPerc", 0)))),
      "pitchDeg": math.degrees(pitch) if pitch is not None else None,
      "yawDeg": math.degrees(yaw) if yaw is not None else None,
      "adjustment": adjustment,
    }

  def _decode(self, key: str) -> Optional[str]:
    raw = self.params.get(key)
    return raw.decode("utf-8", errors="replace") if raw is not None else None

  def _get_bool(self, key: str) -> bool:
    # Qt probes <Param>Lock even when a lock key is not registered. The C++
    # Params API returns false in that case, while Python raises UnknownKeyName.
    try:
      return self.params.get_bool(key)
    except Exception:
      return False

  def _car_list(self):
    try:
      cars = json.loads(self._decode("dp_car_list") or "{}").get("cars", [])
      if cars:
        return cars
    except (TypeError, ValueError):
      pass

    # manager normally populates dp_car_list during boot. Standalone WebUI
    # previews do not run manager_init, so build the identical list on demand.
    from openpilot.selfdrive.car.fingerprints import all_known_cars, all_legacy_fingerprint_cars
    return sorted(set(str(candidate) for candidate in list(all_known_cars()) + list(all_legacy_fingerprint_cars())))

  def put(self, key: str, value: Any):
    control = CONTROL_BY_KEY.get(key)
    if control is None or not isinstance(value, str) or len(value) > 128:
      raise ValueError("unsupported parameter or value")
    if self._get_bool(key + "Lock"):
      raise ValueError("parameter is locked")
    if control["type"] == "toggle" and value not in ("0", "1"):
      raise ValueError("toggle value must be 0 or 1")
    if control["type"] == "choice" and (not value.isdigit() or int(value) >= len(control["choices"])):
      raise ValueError("choice is out of range")
    if control["type"] == "number":
      try:
        number = int(value)
      except ValueError as exc:
        raise ValueError("value must be an integer") from exc
      if number < control["min"] or number > control["max"] or (number - control["min"]) % control["step"]:
        raise ValueError("number is out of range")
    if key == "dp_0813" and value == "1" and self.params.get_bool("ExperimentalLongitudinalEnabled"):
      raise ValueError("disable openpilot longitudinal control first")
    self.params.put(key, value)
    if key == "dp_0813" and value == "1":
      self.params.remove("ExperimentalMode")

  def action(self, name: str, payload: Dict[str, Any]):
    if name == "reset-calibration":
      self.params.remove("CalibrationParams")
      self.params.remove("LiveTorqueParameters")
      self.params.put_bool("ResetCalibration", True)
    elif name == "reset-configuration":
      self.params.put_bool("dp_reset_conf", True)
    elif name == "select-car":
      value = payload.get("value")
      if not isinstance(value, str) or (value and value not in self._car_list()):
        raise ValueError("unsupported car")
      self.params.put("dp_car_assigned", value)
    elif name in ("reboot", "poweroff"):
      self.sm.update(0)
      if bool(self.sm["controlsState"].enabled):
        raise ValueError("disengage openpilot first")
      self.params.put_bool("DoReboot" if name == "reboot" else "DoShutdown", True)
    elif name == "pull-update":
      return self._pull_update()
    else:
      raise ValueError("unsupported action")

  def _pull_update(self):
    self.sm.update(0)
    if bool(self.sm["deviceState"].started) or bool(self.sm["controlsState"].enabled):
      raise ValueError("updates are only allowed while offroad and disengaged")
    if not self.update_lock.acquire(blocking=False):
      raise ValueError("an update is already in progress")
    try:
      branch = self._git("symbolic-ref", "--quiet", "--short", "HEAD")
      remote = self._git("config", "--get", "branch.%s.remote" % branch)
      merge_ref = self._git("config", "--get", "branch.%s.merge" % branch)
      if not merge_ref.startswith("refs/heads/") or remote not in self._git("remote").splitlines():
        raise ValueError("the current branch has no valid remote upstream")
      self._git("fetch", "--no-tags", remote, merge_ref, timeout=300)
      self._git("reset", "--hard", "FETCH_HEAD", timeout=120)
      return {"revision": self._git("rev-parse", "--short", "HEAD")}
    finally:
      self.update_lock.release()

  @staticmethod
  def _git(*args, timeout=30):
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    try:
      result = subprocess.run(["git", "-C", str(REPO_ROOT)] + list(args), cwd=str(REPO_ROOT), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout, check=True)
      return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
      stderr = getattr(exc, "stderr", "") or "git command failed"
      raise ValueError(stderr.strip()[-500:]) from exc


def make_handler(api: WebUI, road_stream: RoadCameraStream):
  class Handler(BaseHTTPRequestHandler):
    server_version = "LegacypilotWebUI/1"

    def do_GET(self):
      path = urlsplit(self.path).path
      if path == "/api/v1/config":
        return self._json(200, api.document())
      if path == "/api/v1/health":
        return self._json(200, {"ok": True})
      if path == "/api/v1/road-camera.mjpeg":
        return self._road_camera()
      self._static(path)

    def do_PUT(self):
      prefix = "/api/v1/params/"
      path = urlsplit(self.path).path
      if not path.startswith(prefix):
        return self._error(404, "not found")
      try:
        body = self._body()
        api.put(unquote(path[len(prefix):]), body.get("value"))
        self._json(200, {"ok": True})
      except (ValueError, json.JSONDecodeError) as exc:
        self._error(400, str(exc))

    def do_POST(self):
      prefix = "/api/v1/actions/"
      path = urlsplit(self.path).path
      if not path.startswith(prefix):
        return self._error(404, "not found")
      try:
        result = api.action(unquote(path[len(prefix):]), self._body()) or {}
        self._json(200, dict({"ok": True}, **result))
      except (ValueError, json.JSONDecodeError) as exc:
        self._error(400, str(exc))

    def _body(self):
      length = int(self.headers.get("Content-Length", "0"))
      if length < 0 or length > MAX_REQUEST_BODY:
        raise ValueError("invalid request size")
      if length == 0:
        return {}
      body = json.loads(self.rfile.read(length).decode("utf-8"))
      if not isinstance(body, dict):
        raise ValueError("JSON object required")
      return body

    def _static(self, request_path):
      relative = "index.html" if request_path in ("", "/") else unquote(request_path).lstrip("/")
      target = (STATIC_ROOT / relative).resolve()
      if STATIC_ROOT not in target.parents or not target.is_file():
        return self._error(404, "not found")
      data = target.read_bytes()
      self.send_response(200)
      self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
      self.send_header("Content-Length", str(len(data)))
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      self.wfile.write(data)

    def _road_camera(self):
      self.send_response(200)
      self.send_header(
        "Content-Type", "multipart/x-mixed-replace; boundary=%s" % MJPEG_BOUNDARY
      )
      self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
      self.send_header("Pragma", "no-cache")
      self.end_headers()
      try:
        for frame in road_stream.frames():
          self.wfile.write(("--%s\r\n" % MJPEG_BOUNDARY).encode("ascii"))
          self.wfile.write(b"Content-Type: image/jpeg\r\n")
          content_length = "Content-Length: %d\r\n\r\n" % len(frame)
          self.wfile.write(content_length.encode("ascii"))
          self.wfile.write(frame)
          self.wfile.write(b"\r\n")
          self.wfile.flush()
      except (BrokenPipeError, ConnectionResetError):
        pass

    def _json(self, status, payload):
      data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
      self.send_response(status)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(data)))
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      self.wfile.write(data)

    def _error(self, status, message):
      self._json(status, {"error": message})

    def log_message(self, fmt, *args):
      LOG.debug(fmt, *args)

  return Handler


class WebUIHTTPServer(ThreadingHTTPServer):
  daemon_threads = True


def create_server(host: str, port: int, api: WebUI,
                  road_stream: Optional[RoadCameraStream] = None):
  handler = make_handler(api, road_stream or RoadCameraStream())
  return WebUIHTTPServer((host, port), handler)


def main():
  server = create_server(HOST, PORT, WebUI(Params()))
  LOG.info("webui listening on %s:%d", HOST, PORT)
  try:
    server.serve_forever(poll_interval=0.5)
  finally:
    server.server_close()


if __name__ == "__main__":
  main()
