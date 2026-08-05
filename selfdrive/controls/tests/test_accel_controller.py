#!/usr/bin/env python3
import unittest
from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.accel_controller import should_coast_for_lead, should_relax_accel_change_for_lead


def lead(d_rel, v_lead, v_rel=None, status=True):
  return SimpleNamespace(status=status, dRel=d_rel, vLead=v_lead,
                         vRel=(v_lead - 20.0) if v_rel is None else v_rel)


class TestLeadCoasting(unittest.TestCase):
  def test_coasts_for_distant_slower_lead(self):
    self.assertTrue(should_coast_for_lead(20.0, lead(105.0, 18.0), 1.45))

  def test_does_not_coast_when_braking_is_needed(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(70.0, 18.0), 1.45))

  def test_does_not_coast_at_short_ttc(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(45.0, 12.0), 1.45))

  def test_does_not_coast_for_non_closing_lead(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(60.0, 21.0), 1.45))

  def test_does_not_coast_without_valid_lead(self):
    self.assertFalse(should_coast_for_lead(20.0, lead(100.0, 18.0, status=False), 1.45))


class TestLeadPullaway(unittest.TestCase):
  def test_relaxes_accel_change_for_pulling_away_lead(self):
    self.assertTrue(should_relax_accel_change_for_lead(20.0, lead(40.0, 21.0), 1.45))

  def test_keeps_smoothing_for_small_speed_delta(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(40.0, 20.4), 1.45))

  def test_keeps_smoothing_at_short_distance(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(35.0, 21.0), 1.45))

  def test_keeps_smoothing_without_valid_lead(self):
    self.assertFalse(should_relax_accel_change_for_lead(20.0, lead(40.0, 21.0, status=False), 1.45))


if __name__ == "__main__":
  unittest.main()
