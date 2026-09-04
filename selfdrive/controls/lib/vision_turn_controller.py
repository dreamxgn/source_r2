import numpy as np
import math
from cereal import custom
from openpilot.common.numpy_fast import interp
from openpilot.common.conversions import Conversions as CV
from openpilot.selfdrive.controls.lib.drive_helpers import V_CRUISE_MAX

TRAJECTORY_SIZE = 33
_MIN_V = 5.6  # Do not operate under 20km/h

_ENTERING_PRED_LAT_ACC_TH = 1.3  # Predicted Lat Acc threshold to trigger entering turn state.
_ABORT_ENTERING_PRED_LAT_ACC_TH = 1.1  # Predicted Lat Acc threshold to abort entering state if speed drops.

_TURNING_LAT_ACC_TH = 1.6  # Lat Acc threshold to trigger turning turn state.

_LEAVING_LAT_ACC_TH = 1.3  # Lat Acc threshold to trigger leaving turn state.
_FINISH_LAT_ACC_TH = 1.1  # Lat Acc threshold to trigger end of turn cycle.

_EVAL_STEP = 2.5  # mts. Resolution of the curvature evaluation.
_EVAL_START = 5.  # mts. Distance ahead where to start evaluating vision curvature.
_EVAL_LENGHT = 150.  # mts. Distance ahead where to stop evaluating vision curvature.
_EVAL_HORIZON_TIME = 6.  # s. Speed-dependent vision horizon.
_EVAL_MIN_LENGHT = 60.  # mts. Minimum vision horizon when enough path is available.
_MIN_PATH_POINTS = 6

_A_LAT_REG_MAX = 2.  # Maximum lateral acceleration

_NO_OVERSHOOT_TIME_HORIZON = 4.  # s. Time to use for velocity desired based on a_target when not overshooting.

# Lookup table for the minimum smooth deceleration during the ENTERING state
# depending on the actual maximum absolute lateral acceleration predicted on the turn ahead.
_ENTERING_SMOOTH_DECEL_V = [-0.2, -1.]  # min decel value allowed on ENTERING state
_ENTERING_SMOOTH_DECEL_BP = [1.3, 3.]  # absolute value of lat acc ahead

# Lookup table for the acceleration for the TURNING state
# depending on the current lateral acceleration of the vehicle.
_TURNING_ACC_V = [0.5, 0., -0.4]  # acc value
_TURNING_ACC_BP = [1.5, 2.3, 3.]  # absolute value of current lat acc

_LEAVING_ACC = 0.5  # Confortble acceleration to regain speed while leaving a turn.

_MIN_LANE_PROB = 0.6  # Minimum lanes probability to allow curvature prediction based on lanes.

_DEBUG = False


def _debug(msg):
  if not _DEBUG:
    return
  print(msg)


VisionTurnControllerState = custom.LongitudinalPlanExt.VisionTurnControllerState


def eval_curvature(path_x, path_y, x_vals):
  """
  Return absolute curvature for a discrete path evaluated at `x_vals`.

  Resampling before taking derivatives avoids extrapolating a global polynomial
  beyond the model's valid spatial horizon and handles S-curves more naturally.
  """
  path_x = np.asarray(path_x, dtype=float)
  path_y = np.asarray(path_y, dtype=float)
  x_vals = np.asarray(x_vals, dtype=float)
  y_vals = np.interp(x_vals, path_x, path_y)
  dy = np.gradient(y_vals, x_vals)
  ddy = np.gradient(dy, x_vals)
  return np.abs(ddy) / np.power(1. + np.square(dy), 1.5)


def eval_lat_acc(v_ego, x_curv):
  """
  This function returns a vector with the lateral acceleration based
  for the provided speed `v_ego` evaluated over curvature vector `x_curv`
  """

  def lat_acc(curv):
    a = v_ego**2 * curv
    return a

  return np.vectorize(lat_acc)(x_curv)


def _description_for_state(turn_controller_state):
  if turn_controller_state == VisionTurnControllerState.disabled:
    return 'DISABLED'
  if turn_controller_state == VisionTurnControllerState.entering:
    return 'ENTERING'
  if turn_controller_state == VisionTurnControllerState.turning:
    return 'TURNING'
  if turn_controller_state == VisionTurnControllerState.leaving:
    return 'LEAVING'


class VisionTurnController():
  def __init__(self, CP):
    # self._params = Params()
    self._CP = CP
    self._op_enabled = False
    self._gas_pressed = False
    self._is_enabled = False
    self._v_cruise_setpoint = 0.
    self._v_ego = 0.
    self._a_ego = 0.
    self._a_target = 0.
    self._v_overshoot = 0.
    self._state = VisionTurnControllerState.disabled
    self._reset()

  @property
  def state(self):
    return self._state

  @state.setter
  def state(self, value):
    if value != self._state:
      _debug(f'TVC: TurnVisionController state: {_description_for_state(value)}')
      if value == VisionTurnControllerState.disabled:
        self._reset()
    self._state = value

  @property
  def a_target(self):
    return self._a_target if self.is_active else self._a_ego

  @property
  def v_turn(self):
    if not self.is_active:
      return self._v_cruise_setpoint
    v_turn = self._v_overshoot if self._lat_acc_overshoot_ahead \
      else self._v_ego + self._a_target * _NO_OVERSHOOT_TIME_HORIZON
    return min(max(v_turn, 0.), self._v_cruise_setpoint)

  @property
  def is_active(self):
    return self._state != VisionTurnControllerState.disabled

  @property
  def is_enabled(self):
    return self._is_enabled

  def _reset(self):
    self._current_lat_acc = 0.
    self._max_v_for_current_curvature = 0.
    self._max_pred_lat_acc = 0.
    self._v_overshoot_distance = 200.
    self._lat_acc_overshoot_ahead = False
    self._path_source = 'invalid'

  @property
  def path_source(self):
    return self._path_source

  @staticmethod
  def _valid_path(path_x, path_y):
    path_x = np.asarray(path_x, dtype=float)
    path_y = np.asarray(path_y, dtype=float)
    return len(path_x) == len(path_y) and len(path_x) >= _MIN_PATH_POINTS and \
      np.isfinite(path_x).all() and np.isfinite(path_y).all() and \
      np.all(np.diff(path_x) > 0.) and path_x[-1] >= _EVAL_START + (2. * _EVAL_STEP)

  def _update_calculations(self, sm, fallback_path=None):
    path_x = None
    path_y = None
    model_data = sm['modelV2']

    # 1. When the probability of lanes is good enough, compute polynomial from lanes as they are way more stable
    # on current mode than drving path.
    if model_data is not None and len(model_data.laneLines) == 4 and len(model_data.laneLines[0].t) == TRAJECTORY_SIZE:
      ll_x = model_data.laneLines[1].x  # left and right ll x is the same
      lll_y = np.array(model_data.laneLines[1].y)
      rll_y = np.array(model_data.laneLines[2].y)
      l_prob = model_data.laneLineProbs[1]
      r_prob = model_data.laneLineProbs[2]
      lll_std = model_data.laneLineStds[1]
      rll_std = model_data.laneLineStds[2]

      # Reduce reliance on lanelines that are too far apart or will be in a few seconds
      width_pts = rll_y - lll_y
      prob_mods = []
      for t_check in [0.0, 1.5, 3.0]:
        width_at_t = interp(t_check * (self._v_ego + 7), ll_x, width_pts)
        prob_mods.append(interp(width_at_t, [4.0, 5.0], [1.0, 0.0]))
      mod = min(prob_mods)
      l_prob *= mod
      r_prob *= mod

      # Reduce reliance on uncertain lanelines
      l_std_mod = interp(lll_std, [.15, .3], [1.0, 0.0])
      r_std_mod = interp(rll_std, [.15, .3], [1.0, 0.0])
      l_prob *= l_std_mod
      r_prob *= r_std_mod

      # Find path from lanes as the average center lane only if min probability on both lanes is above threshold.
      if l_prob > _MIN_LANE_PROB and r_prob > _MIN_LANE_PROB and self._valid_path(ll_x, lll_y) and self._valid_path(ll_x, rll_y):
        c_y = width_pts / 2 + lll_y
        path_x = np.asarray(ll_x, dtype=float)
        path_y = c_y
        self._path_source = 'laneLines'

    # 2. Fall back to the current compensated driving path from lateralPlanner.
    if path_x is None and fallback_path is not None:
      fallback_path = np.asarray(fallback_path, dtype=float)
      if fallback_path.ndim == 2 and fallback_path.shape[1] >= 2 and \
          self._valid_path(fallback_path[:, 0], fallback_path[:, 1]):
        path_x = fallback_path[:, 0]
        path_y = fallback_path[:, 1]
        self._path_source = 'modelPath'

    controls_curvature = sm['controlsState'].curvature
    if math.isfinite(controls_curvature):
      current_curvature = abs(controls_curvature)
    else:
      current_curvature = abs(
        sm['carState'].steeringAngleDeg * CV.DEG_TO_RAD / (self._CP.steerRatio * self._CP.wheelbase))
    self._current_lat_acc = current_curvature * self._v_ego**2
    self._max_v_for_current_curvature = math.sqrt(_A_LAT_REG_MAX / current_curvature) if current_curvature > 0 \
      else V_CRUISE_MAX * CV.KPH_TO_MS

    if path_x is None:
      self._path_source = 'invalid'
      self._max_pred_lat_acc = 0.
      self._lat_acc_overshoot_ahead = False
      return

    eval_end = min(path_x[-1], _EVAL_LENGHT, max(_EVAL_MIN_LENGHT, self._v_ego * _EVAL_HORIZON_TIME))
    eval_range = np.arange(_EVAL_START, eval_end + 0.5 * _EVAL_STEP, _EVAL_STEP)
    if len(eval_range) < 3:
      self._max_pred_lat_acc = 0.
      self._lat_acc_overshoot_ahead = False
      return

    pred_curvatures = eval_curvature(path_x, path_y, eval_range)
    max_pred_curvature = np.amax(pred_curvatures)
    self._max_pred_lat_acc = self._v_ego**2 * max_pred_curvature

    max_curvature_for_vego = _A_LAT_REG_MAX / max(self._v_ego, 0.1)**2
    lat_acc_overshoot_idxs = np.nonzero(pred_curvatures >= max_curvature_for_vego)[0]
    self._lat_acc_overshoot_ahead = len(lat_acc_overshoot_idxs) > 0

    if self._lat_acc_overshoot_ahead:
      max_curvature_idx = int(np.argmax(pred_curvatures))
      self._v_overshoot = min(math.sqrt(_A_LAT_REG_MAX / max_pred_curvature), self._v_cruise_setpoint)
      self._v_overshoot_distance = max(eval_range[max_curvature_idx], _EVAL_STEP)
      _debug(f'TVC: High LatAcc. Dist: {self._v_overshoot_distance:.2f}, v: {self._v_overshoot * CV.MS_TO_KPH:.2f}')

  def _state_transition(self):
    # In any case, if system is disabled or the feature is disabeld or gas is pressed, disable.
    if not self._op_enabled or not self._is_enabled or self._gas_pressed:
      self.state = VisionTurnControllerState.disabled
      return

    # DISABLED
    if self.state == VisionTurnControllerState.disabled:
      # Do not enter a turn control cycle if speed is low.
      if self._v_ego <= _MIN_V:
        pass
      # If substantial lateral acceleration is predicted ahead, then move to Entering turn state.
      elif self._max_pred_lat_acc >= _ENTERING_PRED_LAT_ACC_TH:
        self.state = VisionTurnControllerState.entering
    # ENTERING
    elif self.state == VisionTurnControllerState.entering:
      # Transition to Turning if current lateral acceleration is over the threshold.
      if self._current_lat_acc >= _TURNING_LAT_ACC_TH:
        self.state = VisionTurnControllerState.turning
      # Abort if the predicted lateral acceleration drops
      elif self._max_pred_lat_acc < _ABORT_ENTERING_PRED_LAT_ACC_TH:
        self.state = VisionTurnControllerState.disabled
    # TURNING
    elif self.state == VisionTurnControllerState.turning:
      # Transition to Leaving if current lateral acceleration drops drops below threshold.
      if self._current_lat_acc <= _LEAVING_LAT_ACC_TH:
        self.state = VisionTurnControllerState.leaving
    # LEAVING
    elif self.state == VisionTurnControllerState.leaving:
      # Transition back to Turning if current lateral acceleration goes back over the threshold.
      if self._current_lat_acc >= _TURNING_LAT_ACC_TH:
        self.state = VisionTurnControllerState.turning
      # Finish if current lateral acceleration goes below threshold.
      elif self._current_lat_acc < _FINISH_LAT_ACC_TH:
        self.state = VisionTurnControllerState.disabled

  def _update_solution(self):
    # DISABLED
    if self.state == VisionTurnControllerState.disabled:
      # when not overshooting, calculate v_turn as the speed at the prediction horizon when following
      # the smooth deceleration.
      a_target = self._a_ego
    # ENTERING
    elif self.state == VisionTurnControllerState.entering:
      # when not overshooting, target a smooth deceleration in preparation for a sharp turn to come.
      a_target = interp(self._max_pred_lat_acc, _ENTERING_SMOOTH_DECEL_BP, _ENTERING_SMOOTH_DECEL_V)
      if self._lat_acc_overshoot_ahead:
        # when overshooting, target the acceleration needed to achieve the overshoot speed at
        # the required distance
        a_target = min((self._v_overshoot**2 - self._v_ego**2) / (2 * self._v_overshoot_distance), a_target)
      _debug(f'TVC Entering: Overshooting: {self._lat_acc_overshoot_ahead}')
      _debug(f'    Decel: {a_target:.2f}, target v: {self.v_turn * CV.MS_TO_KPH}')
    # TURNING
    elif self.state == VisionTurnControllerState.turning:
      # When turning we provide a target acceleration that is confortable for the lateral accelearation felt.
      a_target = interp(self._current_lat_acc, _TURNING_ACC_BP, _TURNING_ACC_V)
    # LEAVING
    elif self.state == VisionTurnControllerState.leaving:
      # When leaving we provide a confortable acceleration to regain speed.
      a_target = _LEAVING_ACC

    # update solution values.
    self._a_target = a_target

  def update(self, enabled, v_ego, a_ego, v_cruise_setpoint, sm, fallback_path=None):
    self._op_enabled = enabled
    self._gas_pressed = sm['carState'].gasPressed
    self._v_ego = v_ego
    self._a_ego = a_ego
    self._v_cruise_setpoint = v_cruise_setpoint

    self._update_calculations(sm, fallback_path)
    self._state_transition()
    self._update_solution()

  def set_enabled(self, enabled):
    self._is_enabled = enabled
