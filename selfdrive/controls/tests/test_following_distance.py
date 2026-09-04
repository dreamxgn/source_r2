#!/usr/bin/env python3
import unittest
from types import SimpleNamespace

from openpilot.common.params import Params
from cereal import log

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  LongitudinalMpc, STOP_DISTANCE, desired_follow_distance, get_dynamic_follow,
  get_T_FOLLOW,
)
from openpilot.selfdrive.test.longitudinal_maneuvers.maneuver import Maneuver


def run_following_distance_simulation(v_lead, t_end=100.0, e2e=False):
  man = Maneuver(
    '',
    duration=t_end,
    initial_speed=float(v_lead),
    lead_relevancy=True,
    initial_distance_lead=100,
    speed_lead_values=[v_lead],
    breakpoints=[0.],
    e2e=e2e,
  )
  valid, output = man.evaluate()
  assert valid
  return output[-1,2] - output[-1,1]


class TestFollowingDistance(unittest.TestCase):
  def test_guarded_coast_does_not_extrapolate_vision_deceleration(self):
    lead = SimpleNamespace(status=True, radar=False, dRel=65.0, vLead=8.0,
                           aLeadK=-2.0, aLeadTau=0.3)
    mpc = LongitudinalMpc()
    mpc.set_cur_state(13.0, 0.0)
    normal_lead = mpc.process_lead(lead)
    coast_lead = mpc.process_lead(lead, coast_active=True)
    self.assertGreater(coast_lead[-1, 0], normal_lead[-1, 0])
    self.assertGreater(coast_lead[-1, 1], normal_lead[-1, 1])

  def test_guarded_coast_preserves_radar_deceleration(self):
    lead = SimpleNamespace(status=True, radar=True, dRel=65.0, vLead=8.0,
                           aLeadK=-2.0, aLeadTau=0.3)
    mpc = LongitudinalMpc()
    mpc.set_cur_state(13.0, 0.0)
    normal_lead = mpc.process_lead(lead)
    coast_lead = mpc.process_lead(lead, coast_active=True)
    self.assertTrue((coast_lead == normal_lead).all())

  def test_dynamic_follow_tuning(self):
    personalities = [log.LongitudinalPersonality.relaxed,
                     log.LongitudinalPersonality.standard,
                     log.LongitudinalPersonality.aggressive]
    self.assertEqual([get_dynamic_follow(0.0, personality) for personality in personalities], [1.9, 1.6, 1.4])

    for speed in [0.0, 5.0, 15.0, 30.0]:
      time_gaps = [get_dynamic_follow(speed, personality) for personality in personalities]
      self.assertGreater(time_gaps[0], time_gaps[1])
      self.assertGreater(time_gaps[1], time_gaps[2])

    for personality in personalities:
      self.assertGreaterEqual(get_dynamic_follow(30.0, personality), get_T_FOLLOW(personality))

  def test_lead_pullaway_response(self):
    params = Params()
    params.put("LongitudinalPersonality", str(log.LongitudinalPersonality.standard))
    params.put("dp_long_accel_profile", "0")
    params.put_bool("dp_long_use_df_tune", False)
    params.put_bool("dp_long_use_krkeegen_tune", False)
    man = Maneuver(
      'lead pullaway',
      duration=6.0,
      initial_speed=0.0,
      lead_relevancy=True,
      initial_distance_lead=STOP_DISTANCE,
      speed_lead_values=[0.0, 0.0, 5.0, 5.0],
      breakpoints=[0.0, 1.0, 4.0, 6.0],
      cruise_values=[15.0] * 4,
    )
    valid, output = man.evaluate()
    speed_at_four_seconds = output[abs(output[:, 0] - 4.0).argmin(), 3]
    self.assertTrue(valid)
    self.assertGreater(speed_at_four_seconds, 1.9)

  def test_following_distance(self):
    params = Params()
    personalities = [log.LongitudinalPersonality.relaxed,
                     log.LongitudinalPersonality.standard,
                     log.LongitudinalPersonality.aggressive]
    for personality in personalities:
      params.put("LongitudinalPersonality", str(personality))
      for e2e in [False, True]:
        for speed in [0,10,35]:
          print(f'Testing {speed} m/s')
          v_lead = float(speed)
          simulation_steady_state = run_following_distance_simulation(v_lead, e2e=e2e)
          correct_steady_state = desired_follow_distance(v_lead, v_lead, get_T_FOLLOW(personality))
          err_ratio = 0.2 if e2e else 0.1
          self.assertAlmostEqual(simulation_steady_state, correct_steady_state, delta=(err_ratio * correct_steady_state + .5))


if __name__ == "__main__":
  unittest.main()
