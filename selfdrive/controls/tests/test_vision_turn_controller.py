#!/usr/bin/env python3
import math
import unittest
from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.controls.lib.vision_turn_controller import VisionTurnController, \
  VisionTurnControllerState, eval_curvature


def make_sm(curvature=0., gas_pressed=False):
  return {
    'modelV2': SimpleNamespace(laneLines=[]),
    'carState': SimpleNamespace(steeringAngleDeg=0., gasPressed=gas_pressed),
    'controlsState': SimpleNamespace(curvature=curvature),
  }


def circular_path(radius=100., length=80., points=33):
  path_x = np.linspace(0., length, points)
  path_y = radius - np.sqrt(radius ** 2 - path_x ** 2)
  return np.column_stack((path_x, path_y, np.zeros(points)))


class TestVisionTurnController(unittest.TestCase):
  def setUp(self):
    CP = SimpleNamespace(steerRatio=15.6, wheelbase=2.74)
    self.controller = VisionTurnController(CP)
    self.controller.set_enabled(True)

  def test_discrete_circle_curvature(self):
    path = circular_path()
    x_vals = np.arange(5., 80., 5.)
    curvatures = eval_curvature(path[:, 0], path[:, 1], x_vals)
    self.assertAlmostEqual(float(np.median(curvatures[2:-2])), 0.01, delta=0.002)

  def test_fallback_path_can_start_at_zero(self):
    self.controller.update(True, 20., 0., 30., make_sm(), circular_path())
    self.assertEqual(self.controller.path_source, 'modelPath')
    self.assertEqual(self.controller.state, VisionTurnControllerState.entering)
    self.assertLess(self.controller.v_turn, 20.)

  def test_invalid_path_does_not_activate(self):
    invalid_path = np.array([[0., 0., 0.], [10., math.nan, 0.]])
    self.controller.update(True, 20., 0., 30., make_sm(), invalid_path)
    self.assertEqual(self.controller.path_source, 'invalid')
    self.assertEqual(self.controller.state, VisionTurnControllerState.disabled)

  def test_current_controls_curvature_drives_turn_state(self):
    path = circular_path()
    self.controller.update(True, 20., 0., 30., make_sm(), path)
    self.controller.update(True, 20., 0., 30., make_sm(curvature=0.005), path)
    self.assertEqual(self.controller.state, VisionTurnControllerState.turning)

  def test_gas_disables_controller(self):
    path = circular_path()
    self.controller.update(True, 20., 0., 30., make_sm(), path)
    self.controller.update(True, 20., 0., 30., make_sm(gas_pressed=True), path)
    self.assertEqual(self.controller.state, VisionTurnControllerState.disabled)


if __name__ == '__main__':
  unittest.main()
