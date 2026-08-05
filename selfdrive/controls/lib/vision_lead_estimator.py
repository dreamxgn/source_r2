from openpilot.common.numpy_fast import clip


VISION_ACCEL_MIN = -3.5
VISION_ACCEL_MAX = 2.0
VISION_ACCEL_TAU = 0.3
VISION_ACCEL_ATTACK = 0.35
VISION_ACCEL_RELEASE = 0.08
VISION_LEAD_DIST_JUMP_MIN = 3.0
VISION_LEAD_VEL_JUMP = 7.0
VISION_STOPPED_SPEED = 0.5
VISION_STOPPED_DISTANCE_COMPENSATION = 1.3
VISION_STOPPED_DISTANCE_COMPENSATION_MAX_EGO_SPEED = 3.0

STOPPED_LEAD_EGO_SPEED = 0.5
STOPPED_LEAD_RESET_EGO_SPEED = 1.0
STOPPED_LEAD_MAX_DISTANCE = 25.0
STOPPED_LEAD_MATCH_DISTANCE = 3.0
STOPPED_LEAD_MATCH_LATERAL = 1.5
STOPPED_LEAD_MOVING_SPEED = 0.5
STOPPED_LEAD_RELEASE_FRAMES = 5


def compensate_stopped_lead_distance(v_ego: float, lead, enabled: bool):
  if (not enabled or not lead.get('status', False) or
      abs(lead['vLead']) >= VISION_STOPPED_SPEED or
      not 0.0 < lead['dRel'] < STOPPED_LEAD_MAX_DISTANCE or
      v_ego >= VISION_STOPPED_DISTANCE_COMPENSATION_MAX_EGO_SPEED):
    return lead

  compensated_lead = dict(lead)
  speed_factor = 1.0 - max(v_ego, 0.0) / VISION_STOPPED_DISTANCE_COMPENSATION_MAX_EGO_SPEED
  compensated_lead['dRel'] += VISION_STOPPED_DISTANCE_COMPENSATION * speed_factor
  return compensated_lead


class VisionLeadEstimator:
  """Estimate lead acceleration across consecutive vision-only observations."""
  def __init__(self, dt: float):
    self.dt = dt
    self.reset()

  def reset(self):
    self.initialized = False
    self.d_rel = 0.0
    self.v_rel = 0.0
    self.v_lead = 0.0
    self.a_lead = 0.0

  def update(self, d_rel: float, v_rel: float, v_lead: float) -> float:
    if not self.initialized:
      self.initialized = True
      self.d_rel = d_rel
      self.v_rel = v_rel
      self.v_lead = v_lead
      return self.a_lead

    expected_d_rel = self.d_rel + self.v_rel * self.dt
    dist_jump = max(VISION_LEAD_DIST_JUMP_MIN, self.d_rel * 0.15)
    if abs(d_rel - expected_d_rel) > dist_jump or abs(v_lead - self.v_lead) > VISION_LEAD_VEL_JUMP:
      self.reset()
      return self.update(d_rel, v_rel, v_lead)

    raw_accel = clip((v_lead - self.v_lead) / self.dt, VISION_ACCEL_MIN, VISION_ACCEL_MAX)
    alpha = VISION_ACCEL_ATTACK if raw_accel < self.a_lead else VISION_ACCEL_RELEASE
    self.a_lead = clip((1.0 - alpha) * self.a_lead + alpha * raw_accel, VISION_ACCEL_MIN, VISION_ACCEL_MAX)
    self.d_rel = d_rel
    self.v_rel = v_rel
    self.v_lead = v_lead
    return self.a_lead


class VisionStoppedLeadHold:
  """Keep the stopped in-path lead authoritative through short vision target changes."""
  def __init__(self, dt: float):
    self.dt = dt
    self.reset()

  def reset(self):
    self.lead = None
    self.moving_frames = 0

  @staticmethod
  def _valid(lead):
    return lead.get('status', False)

  def _same_lead(self, lead):
    return (self._valid(lead) and
            abs(lead['dRel'] - self.lead['dRel']) < STOPPED_LEAD_MATCH_DISTANCE and
            abs(lead['yRel'] - self.lead['yRel']) < STOPPED_LEAD_MATCH_LATERAL)

  def update(self, v_ego: float, lead_one, lead_two):
    if v_ego > STOPPED_LEAD_RESET_EGO_SPEED:
      self.reset()
      return lead_one, lead_two

    if self.lead is None:
      if (v_ego < STOPPED_LEAD_EGO_SPEED and self._valid(lead_one) and
          0.0 < lead_one['dRel'] < STOPPED_LEAD_MAX_DISTANCE and
          abs(lead_one['vLead']) < VISION_STOPPED_SPEED):
        self.lead = dict(lead_one)
      return lead_one, lead_two

    candidates = [lead for lead in (lead_one, lead_two) if self._same_lead(lead)]
    matched_lead = min(candidates, key=lambda lead: abs(lead['dRel'] - self.lead['dRel'])) if candidates else None

    if matched_lead is not None and matched_lead['vLead'] > STOPPED_LEAD_MOVING_SPEED:
      self.moving_frames += 1
      if self.moving_frames >= STOPPED_LEAD_RELEASE_FRAMES:
        self.reset()
        return lead_one, lead_two
    else:
      self.moving_frames = 0
      if matched_lead is not None and abs(matched_lead['vLead']) < VISION_STOPPED_SPEED:
        self.lead = dict(matched_lead)

    # Keep the obstacle fixed in the world while ego creeps toward it.
    self.lead['dRel'] = max(0.1, self.lead['dRel'] - v_ego * self.dt)
    self.lead['vRel'] = -v_ego
    self.lead['vLead'] = 0.0
    self.lead['vLeadK'] = 0.0
    self.lead['aLeadK'] = 0.0
    self.lead['status'] = True
    return dict(self.lead), lead_two
