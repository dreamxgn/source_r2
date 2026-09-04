#!/usr/bin/env python3
import unittest
from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.accel_controller import should_coast_for_lead, should_relax_accel_change_for_lead


def lead(d_rel, v_lead, v_rel=None, a_lead=0.0, status=True):
  return SimpleNamespace(status=status, dRel=d_rel, vLead=v_lead,
                         vRel=(v_lead - 20.0) if v_rel is None else v_rel,
                         aLeadK=a_lead)


class TestLeadCoasting(unittest.TestCase):
  def test_does_not_coast_for_very_distant_slower_lead(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(105.0, 18.0), 1.45))

  def test_coasts_before_gradually_matching_a_slower_lead(self):
    self.assertTrue(should_coast_for_lead(20.0, lead(70.0, 18.0), 1.45))

  def test_does_not_coast_when_relative_braking_is_needed(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(50.0, 12.0), 1.45))

  def test_coasts_for_recorded_tiguan_approach(self):
    self.assertTrue(should_coast_for_lead(12.94, lead(65.3, 7.7, v_rel=-5.24), 1.25))

  def test_does_not_coast_at_short_ttc(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(45.0, 12.0), 1.45))

  def test_does_not_coast_for_non_closing_lead(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(60.0, 21.0), 1.45))

  def test_does_not_coast_without_valid_lead(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(100.0, 18.0, status=False), 1.45))

  def test_coasts_toward_distant_stopped_lead(self):
    self.assertTrue(should_coast_for_lead(5.0, lead(40.0, 0.0, v_rel=-5.0), 1.45))

  def test_does_not_coast_toward_near_stopped_lead(self):
    self.assertFalse(should_coast_for_lead(5.0, lead(25.0, 0.0, v_rel=-5.0), 1.45))

  def test_does_not_coast_below_control_speed(self):
    self.assertFalse(should_coast_for_lead(1.5, lead(20.0, 0.0, v_rel=-1.5), 1.45))


class TestLeadPullaway(unittest.TestCase):
  def test_relaxes_accel_change_for_pulling_away_lead(self):
    self.assertTrue(should_relax_accel_change_for_lead(20.0, lead(40.0, 21.0), 1.45))

  def test_relaxes_earlier_for_accelerating_lead(self):
    self.assertTrue(should_relax_accel_change_for_lead(20.0, lead(40.0, 20.15, a_lead=0.5), 1.45))

  def test_keeps_smoothing_for_small_speed_delta(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(36.9, 20.2), 1.45))

  def test_keeps_smoothing_for_unconfirmed_lead_acceleration(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(36.9, 20.15, a_lead=0.2), 1.45))

  def test_keeps_smoothing_at_short_distance(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(34.9, 21.0), 1.45))

  def test_relaxes_for_excessive_gap_to_same_speed_lead(self):
    self.assertTrue(should_relax_accel_change_for_lead(20.0, lead(37.0, 20.0), 1.45))

  def test_keeps_smoothing_for_excessive_gap_to_slower_lead(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(37.0, 19.4), 1.45))

  def test_keeps_smoothing_for_slightly_slower_cut_in(self):
    self.assertFalse(should_relax_accel_change_for_lead(
      20.0, lead(37.0, 19.9), 1.45))

  def test_keeps_smoothing_without_valid_lead(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(40.0, 21.0, status=False), 1.45))


if __name__ == "__main__":
  unittest.main()
