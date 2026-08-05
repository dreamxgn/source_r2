import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Set
from urllib.parse import unquote, urlsplit

MAX_REQUEST_BODY = 4096
LOG = logging.getLogger("mobile_api")

# Keep this list in sync with common/params.cc. Unknown keys are deliberately
# rejected so a typo in a client cannot create an unused parameter file.
SUPPORTED_PARAMS: Set[str] = {
  "DisengageOnAccelerator", "ExperimentalLongitudinalEnabled",
  "ExperimentalMode", "GsmApn", "GsmMetered", "GsmRoaming",
  "IsLdwEnabled", "IsMetric", "IsRhdDetected", "LanguageSetting",
  "LongitudinalPersonality", "OpenpilotEnabledToggle", "RecordFront",
  "dp_0813", "dp_alka", "dp_car_assigned", "dp_car_dashcam_mode_removal",
  "dp_device_audible_alert_mode", "dp_device_auto_shutdown",
  "dp_device_auto_shutdown_in", "dp_device_disable_temp_check",
  "dp_device_display_off_mode", "dp_device_enable_comma_registration",
  "dp_device_no_ir_ctrl", "dp_hkg_min_steer_speed_bypass",
  "dp_lat_controller", "dp_lat_lane_change_assist_speed",
  "dp_lat_lane_priority_mode", "dp_lat_lane_priority_mode_speed_based",
  "dp_logging", "dp_long_accel_btn", "dp_long_accel_profile",
  "dp_long_de2e", "dp_long_personality_btn", "dp_long_use_df_tune",
  "dp_long_use_krkeegen_tune", "dp_mapd", "dp_mapd_vision_turn_control",
  "dp_no_fan_ctrl", "dp_no_gps_ctrl", "dp_toyota_auto_lock",
  "dp_toyota_auto_unlock", "dp_toyota_enhanced_bsm", "dp_toyota_sng",
  "dp_toyota_zss", "dp_vag_timebomb_bypass",
}


def decode_param(params: Any, key: str) -> Optional[str]:
  value = params.get(key)
  return value.decode("utf-8", errors="replace") if value is not None else None


class MobileAPI:
  def __init__(self, params: Any, status_provider: Any):
    self.params = params
    self.status_provider = status_provider

  def get_status(self) -> Dict[str, Any]:
    return self.status_provider.status()

  def get_params(self) -> Dict[str, Any]:
    values = {}
    for key in sorted(SUPPORTED_PARAMS):
      value = decode_param(self.params, key)
      if value is not None:
        values[key] = value
    context = self.status_provider.parameter_context() if hasattr(self.status_provider, "parameter_context") else {}
    states = {key: self._parameter_state(key, values, context) for key in SUPPORTED_PARAMS}
    return {"values": values, "states": states}

  def _parameter_state(self, key: str, values: Dict[str, str],
                       context: Dict[str, Any]) -> Dict[str, bool]:
    visible = True
    enabled = not self._get_bool(key + "Lock")
    old_model = values.get("dp_0813") == "1"

    if key in ("ExperimentalMode", "ExperimentalLongitudinalEnabled") and old_model:
      visible = False
    elif key == "ExperimentalLongitudinalEnabled" and context.get("hasCarParams"):
      visible = bool(context.get("experimentalLongitudinalAvailable")) and not bool(context.get("isReleaseBranch"))
    elif key == "ExperimentalLongitudinalEnabled":
      visible = False

    if key in ("ExperimentalMode", "LongitudinalPersonality") and context.get("hasCarParams") and not old_model:
      enabled = enabled and bool(context.get("hasLongitudinalControl"))

    if key == "dp_device_auto_shutdown_in":
      visible = values.get("dp_device_auto_shutdown") == "1"
    elif key == "dp_lat_lane_priority_mode_speed_based":
      visible = values.get("dp_lat_lane_priority_mode") == "1"

    return {"visible": visible, "enabled": enabled}

  def _get_bool(self, key: str) -> bool:
    try:
      return decode_param(self.params, key) == "1"
    except Exception:
      return False

  def put_param(self, key: str, value: Any) -> Dict[str, str]:
    if key not in SUPPORTED_PARAMS:
      raise KeyError(key)
    if not isinstance(value, str) or len(value) > 128:
      raise ValueError("value must be a string of at most 128 characters")
    self.params.put(key, value)
    if key == "dp_0813" and value == "1":
      for incompatible_key in ("ExperimentalMode", "ExperimentalLongitudinalEnabled"):
        try:
          self.params.remove(incompatible_key)
        except (AttributeError, KeyError):
          pass
    return {"value": value}

  def reset_calibration(self) -> Dict[str, bool]:
    for key in ("CalibrationParams", "LiveTorqueParameters"):
      try:
        self.params.remove(key)
      except (AttributeError, KeyError):
        pass
    self.params.put("ResetCalibration", "1")
    return {"ok": True}


def make_handler(api: MobileAPI):
  class MobileAPIHandler(BaseHTTPRequestHandler):
    server_version = "LegacypilotMobileAPI/1"

    def do_GET(self) -> None:
      path = urlsplit(self.path).path.rstrip("/")
      if path == "/api/v1/status":
        self._send_json(200, api.get_status())
      elif path == "/api/v1/params":
        self._send_json(200, api.get_params())
      elif path == "/api/v1/health":
        self._send_json(200, {"ok": True})
      else:
        self._send_error(404, "not_found", "Endpoint not found")

    def do_PUT(self) -> None:
      prefix = "/api/v1/params/"
      path = urlsplit(self.path).path
      if not path.startswith(prefix):
        self._send_error(404, "not_found", "Endpoint not found")
        return

      key = unquote(path[len(prefix):])
      try:
        body = self._read_json()
        result = api.put_param(key, body.get("value") if isinstance(body, dict) else None)
      except KeyError:
        self._send_error(404, "unknown_param", "Unknown or unsupported parameter")
      except (ValueError, json.JSONDecodeError) as exc:
        self._send_error(400, "invalid_request", str(exc))
      else:
        self._send_json(200, result)

    def do_POST(self) -> None:
      path = urlsplit(self.path).path.rstrip("/")
      if path == "/api/v1/actions/reset-calibration":
        self._send_json(200, api.reset_calibration())
      else:
        self._send_error(404, "not_found", "Endpoint not found")

    def _read_json(self) -> Any:
      try:
        length = int(self.headers.get("Content-Length", "0"))
      except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
      if length <= 0 or length > MAX_REQUEST_BODY:
        raise ValueError("request body must be between 1 and 4096 bytes")
      return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, status: int, payload: Any) -> None:
      body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
      self.send_response(status)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      self.wfile.write(body)

    def _send_error(self, status: int, code: str, message: str) -> None:
      self._send_json(status, {"error": code, "message": message})

    def log_message(self, fmt: str, *args: Any) -> None:
      LOG.debug(fmt, *args)

  return MobileAPIHandler


def create_server(host: str, port: int, api: MobileAPI) -> HTTPServer:
  return HTTPServer((host, port), make_handler(api))
