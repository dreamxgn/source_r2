#!/usr/bin/env python3
import unittest

from openpilot.selfdrive.controls.lib.vision_lead_estimator import STOPPED_LEAD_RELEASE_FRAMES, VisionLeadEstimator, VisionStoppedLeadHold, compensate_stopped_lead_distance


class TestVisionLeadEstimator(unittest.TestCase):
  def setUp(self):
    self.dt = 0.05
    self.estimator = VisionLeadEstimator(self.dt)

  def test_constant_speed(self):
    for i in range(20):
      accel = self.estimator.update(30.0 + i * self.dt * -2.0, -2.0, 18.0)
    self.assertAlmostEqual(accel, 0.0)

  def test_sustained_deceleration(self):
    v_lead = 20.0
    d_rel = 40.0
    accel = 0.0
    for _ in range(10):
      v_rel = v_lead - 22.0
      d_rel += v_rel * self.dt
      v_lead -= 2.0 * self.dt
      accel = self.estimator.update(d_rel, v_rel, v_lead)
    self.assertLess(accel, -1.5)
    self.assertGreaterEqual(accel, -3.5)

  def test_accel_recovers_slowly(self):
    self.estimator.update(30.0, -2.0, 18.0)
    braking_accel = self.estimator.update(29.9, -2.1, 17.9)
    recovered_accel = self.estimator.update(29.8, -2.1, 17.9)
    self.assertLess(braking_accel, 0.0)
    self.assertLess(recovered_accel, 0.0)
    self.assertGreater(recovered_accel, braking_accel)

  def test_target_change_resets_acceleration(self):
    self.estimator.update(30.0, -2.0, 18.0)
    self.assertLess(self.estimator.update(29.9, -4.0, 16.0), 0.0)
    self.assertEqual(self.estimator.update(12.0, -1.0, 19.0), 0.0)

  def test_reset(self):
    self.estimator.update(30.0, -2.0, 18.0)
    self.estimator.update(29.9, -4.0, 16.0)
    self.estimator.reset()
    self.assertEqual(self.estimator.update(29.8, -2.0, 18.0), 0.0)


class TestVisionStoppedLeadHold(unittest.TestCase):
  def setUp(self):
    self.hold = VisionStoppedLeadHold(0.05)
    self.stopped_lead = {'status': True, 'dRel': 7.0, 'yRel': 0.0, 'vRel': 0.0,
                         'vLead': 0.0, 'vLeadK': 0.0, 'aLeadK': 0.0}
    self.no_lead = {'status': False}

  def test_holds_stopped_lead_when_vision_drops(self):
    self.hold.update(0.0, self.stopped_lead, self.no_lead)
    lead_one, _ = self.hold.update(0.0, self.no_lead, self.no_lead)
    self.assertTrue(lead_one['status'])
    self.assertEqual(lead_one['vLead'], 0.0)

  def test_adjacent_moving_lead_does_not_release(self):
    adjacent_lead = dict(self.stopped_lead, yRel=3.2, vLead=4.0, vLeadK=4.0)
    self.hold.update(0.0, self.stopped_lead, self.no_lead)
    for _ in range(STOPPED_LEAD_RELEASE_FRAMES + 1):
      lead_one, _ = self.hold.update(0.0, self.no_lead, adjacent_lead)
    self.assertTrue(lead_one['status'])
    self.assertEqual(lead_one['vLead'], 0.0)

  def test_same_lead_must_move_consistently_to_release(self):
    moving_lead = dict(self.stopped_lead, dRel=7.2, vLead=1.0, vLeadK=1.0)
    self.hold.update(0.0, self.stopped_lead, self.no_lead)
    for _ in range(STOPPED_LEAD_RELEASE_FRAMES - 1):
      lead_one, _ = self.hold.update(0.0, moving_lead, self.no_lead)
      self.assertEqual(lead_one['vLead'], 0.0)
    lead_one, _ = self.hold.update(0.0, moving_lead, self.no_lead)
    self.assertEqual(lead_one['vLead'], 1.0)

  def test_driver_movement_resets_hold(self):
    self.hold.update(0.0, self.stopped_lead, self.no_lead)
    lead_one, _ = self.hold.update(1.1, self.no_lead, self.no_lead)
    self.assertFalse(lead_one['status'])

  def test_stopped_lead_distance_compensation(self):
    compensated = compensate_stopped_lead_distance(0.0, self.stopped_lead, enabled=True)
    self.assertEqual(compensated['dRel'], self.stopped_lead['dRel'] + 1.0)
    self.assertEqual(self.stopped_lead['dRel'], 7.0)

    compensated = compensate_stopped_lead_distance(1.5, self.stopped_lead, enabled=True)
    self.assertEqual(compensated['dRel'], self.stopped_lead['dRel'] + 0.5)

  def test_distance_compensation_scope(self):
    moving_lead = dict(self.stopped_lead, vLead=1.0)
    self.assertIs(compensate_stopped_lead_distance(0.0, moving_lead, enabled=True), moving_lead)
    self.assertIs(compensate_stopped_lead_distance(3.0, self.stopped_lead, enabled=True), self.stopped_lead)
    self.assertIs(compensate_stopped_lead_distance(0.0, self.stopped_lead, enabled=False), self.stopped_lead)


if __name__ == "__main__":
  unittest.main()
