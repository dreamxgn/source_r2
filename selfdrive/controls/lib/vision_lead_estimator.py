from openpilot.common.numpy_fast import clip


VISION_ACCEL_MIN = -3.5
VISION_ACCEL_MAX = 2.0
VISION_ACCEL_TAU = 0.3
VISION_ACCEL_ATTACK = 0.35
VISION_ACCEL_RELEASE = 0.08
VISION_LEAD_DIST_JUMP_MIN = 3.0
VISION_LEAD_VEL_JUMP = 7.0


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
