#!/usr/bin/env python3
import random
import unittest

import numpy as np

import cereal.messaging as messaging
from cereal import log
from openpilot.common.params import Params
from openpilot.selfdrive.locationd.calibrationd import Calibrator, INPUTS_NEEDED, INPUTS_WANTED, BLOCK_SIZE, MIN_SPEED_FILTER, \
                                                         MAX_YAW_RATE_FILTER, SMOOTH_CYCLES, HEIGHT_INIT, MOUNTING_OFFSET_MIN_SAMPLES, \
                                                         PITCH_LIMITS, YAW_LIMITS, get_calibration_adjustment


class TestCalibrationd(unittest.TestCase):

  def test_calibration_adjustment_direction(self):
    self.assertEqual(get_calibration_adjustment(np.array([0., 0., YAW_LIMITS[0] - 0.01])), "left")
    self.assertEqual(get_calibration_adjustment(np.array([0., 0., YAW_LIMITS[1] + 0.01])), "right")
    self.assertEqual(get_calibration_adjustment(np.array([0., PITCH_LIMITS[0] - 0.01, 0.])), "down")
    self.assertEqual(get_calibration_adjustment(np.array([0., PITCH_LIMITS[1] + 0.01, 0.])), "up")
    self.assertEqual(get_calibration_adjustment(np.array([0., PITCH_LIMITS[1] + 0.01, YAW_LIMITS[0] - 0.01])), "left_up")
    self.assertEqual(get_calibration_adjustment(np.zeros(3)), "")

  def test_read_saved_params(self):
    msg = messaging.new_message('liveCalibration')
    msg.liveCalibration.validBlocks = random.randint(1, 10)
    msg.liveCalibration.rpyCalib = [random.random() for _ in range(3)]
    msg.liveCalibration.height = [random.random() for _ in range(1)]
    Params().put("CalibrationParams", msg.to_bytes())
    c = Calibrator(param_put=True)

    np.testing.assert_allclose(msg.liveCalibration.rpyCalib, c.rpy)
    np.testing.assert_allclose(msg.liveCalibration.height, c.height)
    self.assertEqual(msg.liveCalibration.validBlocks, c.valid_blocks)


  def test_calibration_basics(self):
    c = Calibrator(param_put=False)
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    self.assertEqual(c.valid_blocks, INPUTS_WANTED)
    np.testing.assert_allclose(c.rpy, np.zeros(3))
    np.testing.assert_allclose(c.height, HEIGHT_INIT)
    c.reset()

  def test_reset_calibration(self):
    c = Calibrator(param_put=False)
    c.valid_blocks = INPUTS_NEEDED
    c.rpy = np.array([0.01, 0.02, 0.03])
    c.update_status()
    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.calibrated)

    c.reset_calibration()

    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.uncalibrated)
    self.assertEqual(c.valid_blocks, 0)
    self.assertEqual(c.idx, 0)
    np.testing.assert_allclose(c.rpy, np.zeros(3))

  def test_mounting_offset_detection_does_not_change_calibration(self):
    c = Calibrator(param_put=False)
    c.valid_blocks = INPUTS_WANTED
    c.update_status()
    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.calibrated)

    for _ in range(MOUNTING_OFFSET_MIN_SAMPLES):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, np.tan(np.radians(2.5)) * (MIN_SPEED_FILTER + 1), 0.0],
                        [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1e-3, 1e-3, 1e-3],
                        [0.0, 0.0, HEIGHT_INIT.item()], [1e-3, 1e-3, 1e-3])

    self.assertTrue(c.mounting_offset_detected)
    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.calibrated)

  def test_startup_mounting_offset_preserves_valid_calibration(self):
    c = Calibrator(param_put=False)
    c.valid_blocks = INPUTS_WANTED
    c.update_status()
    c.startup_mount_check_active = True

    for _ in range(MOUNTING_OFFSET_MIN_SAMPLES):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, np.tan(np.radians(2.5)) * (MIN_SPEED_FILTER + 1), 0.0],
                        [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1e-3, 1e-3, 1e-3],
                        [0.0, 0.0, HEIGHT_INIT.item()], [1e-3, 1e-3, 1e-3])

    self.assertFalse(c.startup_mount_check_active)
    self.assertEqual(c.startup_voice_event, "recalibrating")
    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.calibrated)
    self.assertEqual(c.valid_blocks, INPUTS_NEEDED)
    self.assertEqual(c.get_msg().liveCalibration.calStatus, log.LiveCalibrationData.Status.calibrated)

  def test_startup_mounting_check_does_not_gate_engagement(self):
    c = Calibrator(param_put=False)
    c.valid_blocks = INPUTS_WANTED
    c.update_status()
    c.startup_mount_check_active = True

    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.calibrated)
    self.assertEqual(c.get_msg().liveCalibration.calStatus, log.LiveCalibrationData.Status.calibrated)

    for _ in range(MOUNTING_OFFSET_MIN_SAMPLES):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                        [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1e-3, 1e-3, 1e-3],
                        [0.0, 0.0, HEIGHT_INIT.item()], [1e-3, 1e-3, 1e-3])

    self.assertFalse(c.startup_mount_check_active)
    self.assertEqual(c.startup_voice_event, "check_passed")
    self.assertEqual(c.get_msg().liveCalibration.calStatus, log.LiveCalibrationData.Status.calibrated)

  def test_startup_mounting_offset_outside_absolute_limit_is_invalid(self):
    c = Calibrator(param_put=False)
    c.valid_blocks = INPUTS_WANTED
    c.update_status()
    c.startup_mount_check_active = True

    yaw = YAW_LIMITS[1] + np.radians(0.2)
    for _ in range(MOUNTING_OFFSET_MIN_SAMPLES):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, np.tan(yaw) * (MIN_SPEED_FILTER + 1), 0.0],
                        [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1e-3, 1e-3, 1e-3],
                        [0.0, 0.0, HEIGHT_INIT.item()], [1e-3, 1e-3, 1e-3])

    self.assertFalse(c.startup_mount_check_active)
    self.assertEqual(c.startup_voice_event, "failure")
    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.invalid)


  def test_calibration_low_speed_reject(self):
    c = Calibrator(param_put=False)
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER - 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER - 1, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    self.assertEqual(c.valid_blocks, 0)
    np.testing.assert_allclose(c.rpy, np.zeros(3))
    np.testing.assert_allclose(c.height, HEIGHT_INIT)


  def test_calibration_yaw_rate_reject(self):
    c = Calibrator(param_put=False)
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                         [0.0, 0.0, MAX_YAW_RATE_FILTER ],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    self.assertEqual(c.valid_blocks, 0)
    np.testing.assert_allclose(c.rpy, np.zeros(3))
    np.testing.assert_allclose(c.height, HEIGHT_INIT)


  def test_calibration_speed_std_reject(self):
    c = Calibrator(param_put=False)
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e3, 1e3, 1e3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    self.assertEqual(c.valid_blocks, INPUTS_NEEDED)
    np.testing.assert_allclose(c.rpy, np.zeros(3))


  def test_calibration_speed_std_height_reject(self):
    c = Calibrator(param_put=False)
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e3, 1e3, 1e3])
    self.assertEqual(c.valid_blocks, INPUTS_NEEDED)
    np.testing.assert_allclose(c.rpy, np.zeros(3))


  def test_calibration_auto_reset(self):
    c = Calibrator(param_put=False)
    for _ in range(BLOCK_SIZE * INPUTS_WANTED):
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    self.assertEqual(c.valid_blocks, INPUTS_WANTED)
    np.testing.assert_allclose(c.rpy, [0.0, 0.0, 0.0])
    old_rpy_weight_prev = 0.0
    for _ in range(BLOCK_SIZE + 10):
      self.assertLess(old_rpy_weight_prev - c.old_rpy_weight, 1/SMOOTH_CYCLES + 1e-3)
      old_rpy_weight_prev = c.old_rpy_weight
      c.handle_v_ego(MIN_SPEED_FILTER + 1)
      c.handle_cam_odom([MIN_SPEED_FILTER + 1, -0.05 * MIN_SPEED_FILTER, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [1e-3, 1e-3, 1e-3],
                         [0.0, 0.0, HEIGHT_INIT.item()],
                         [1e-3, 1e-3, 1e-3])
    self.assertEqual(c.valid_blocks, INPUTS_NEEDED)
    self.assertEqual(c.cal_status, log.LiveCalibrationData.Status.calibrated)
    np.testing.assert_allclose(c.rpy, [0.0, 0.0, -0.05], atol=1e-2)

if __name__ == "__main__":
  unittest.main()
