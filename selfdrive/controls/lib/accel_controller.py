from openpilot.common.numpy_fast import interp

DP_ACCEL_STOCK = 0
DP_ACCEL_ECO = 1
DP_ACCEL_NORMAL = 2
DP_ACCEL_SPORT = 3

COAST_MIN_EGO_SPEED = 2.0
COAST_MIN_CLOSING_SPEED = 0.3
COAST_MIN_TTC = 5.0
COAST_MIN_EXTRA_DISTANCE = 5.0
COAST_MAX_REQUIRED_DECEL = -0.8
COAST_COMFORT_BRAKE = 2.5
COAST_STOP_DISTANCE = 6.0
LEAD_PULLAWAY_MIN_SPEED_DELTA = 0.5
LEAD_PULLAWAY_MIN_DISTANCE_MARGIN = 0.5


def should_coast_for_lead(v_ego, lead, t_follow):
  if lead is None or not lead.status or v_ego < COAST_MIN_EGO_SPEED:
    return False

  v_lead = max(float(lead.vLead), 0.0)
  closing_speed = max(float(v_ego) - v_lead, -float(lead.vRel), 0.0)
  if closing_speed < COAST_MIN_CLOSING_SPEED:
    return False

  desired_distance = ((v_ego ** 2 - v_lead ** 2) / (2.0 * COAST_COMFORT_BRAKE) +
                      t_follow * v_ego + COAST_STOP_DISTANCE)
  extra_distance = float(lead.dRel) - desired_distance
  if extra_distance < max(COAST_MIN_EXTRA_DISTANCE, 0.3 * v_ego):
    return False

  ttc = float(lead.dRel) / closing_speed
  required_decel = (v_lead ** 2 - v_ego ** 2) / (2.0 * extra_distance)
  return ttc > COAST_MIN_TTC and required_decel >= COAST_MAX_REQUIRED_DECEL


def should_relax_accel_change_for_lead(v_ego, lead, t_follow):
  """Allow a prompt acceleration recovery once a safely-spaced lead pulls away."""
  minimum_distance = t_follow * max(float(v_ego), 0.0) + COAST_STOP_DISTANCE + LEAD_PULLAWAY_MIN_DISTANCE_MARGIN
  return (lead is not None and lead.status and
          float(lead.vLead) - float(v_ego) >= LEAD_PULLAWAY_MIN_SPEED_DELTA and
          float(lead.dRel) >= minimum_distance)

# accel profile by @arne182 modified by cgw
_DP_CRUISE_MIN_V =       [-0.765, -0.765,  -0.80, -0.80, -0.75, -0.70]
_DP_CRUISE_MIN_V_ECO =   [-0.760, -0.760,  -0.76, -0.76, -0.70, -0.65]
_DP_CRUISE_MIN_V_SPORT = [-0.770, -0.770,  -0.90, -1.00, -0.90, -0.80]
_DP_CRUISE_MIN_BP =      [0.,     15.66,  17.88, 20.,   30.,   55.]
#DP_CRUISE_MIN_BP in mph=[0.,     18,     35,    40,    45,    67,    123]

_DP_CRUISE_MAX_V =       [3.4, 2.8, 1.8, 1.4, 1.06, .88, .68,  .46, .35, .13]
_DP_CRUISE_MAX_V_ECO =   [3.2, 2.6, 1.6, 1.2, .76,  .62, .48,  .36, .28, .09]
_DP_CRUISE_MAX_V_SPORT = [3.5, 3.0, 2.4, 2.9, 2.1,  1.7,  1.3, .9,  .7,  .5]
_DP_CRUISE_MAX_BP =      [0.,  3,   6.,  8.,  11.,  15.,  20., 25., 30., 55.]
#DP_CRUISE_MAX_BP in mph=[0.,  6.7, 13,  18,  25,   33,   45,  56,  67,  123]


class AccelController:

  def __init__(self):
    # self._params = Params()
    self._profile = DP_ACCEL_STOCK

  def set_profile(self, profile):
    try:
      self._profile = int(profile) if int(profile) in [DP_ACCEL_STOCK, DP_ACCEL_ECO, DP_ACCEL_NORMAL, DP_ACCEL_SPORT] else DP_ACCEL_STOCK
    except:
      self._profile = DP_ACCEL_STOCK

  def _dp_calc_cruise_accel_limits(self, v_ego):
    if self._profile == DP_ACCEL_ECO:
      min_v = _DP_CRUISE_MIN_V_ECO
      max_v = _DP_CRUISE_MAX_V_ECO
    elif self._profile == DP_ACCEL_SPORT:
      min_v = _DP_CRUISE_MIN_V_SPORT
      max_v = _DP_CRUISE_MAX_V_SPORT
    else:
      min_v = _DP_CRUISE_MIN_V
      max_v = _DP_CRUISE_MAX_V

    a_cruise_min = interp(v_ego, _DP_CRUISE_MIN_BP, min_v)
    a_cruise_max = interp(v_ego, _DP_CRUISE_MAX_BP, max_v)
    return a_cruise_min, a_cruise_max

  def get_accel_limits(self, v_ego, accel_limits):
    return accel_limits if self._profile == DP_ACCEL_STOCK else self._dp_calc_cruise_accel_limits(v_ego)

  def is_enabled(self):
    return self._profile != DP_ACCEL_STOCK
