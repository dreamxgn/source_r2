#!/usr/bin/env python3
import unittest

from openpilot.selfdrive.controls.lib.vision_lead_estimator import VisionLeadEstimator


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


if __name__ == "__main__":
  unittest.main()
