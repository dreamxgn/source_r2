#!/usr/bin/env python3
'''
This process finds calibration values. More info on what these calibration values
are can be found here https://github.com/commaai/openpilot/tree/master/common/transformations
While the roll calibration is a real value that can be estimated, here we assume it's zero,
and the image input into the neural network is not corrected for roll.
'''

import gc
import os
import capnp
import numpy as np
from typing import List, NoReturn, Optional

from cereal import log
import cereal.messaging as messaging
from openpilot.common.conversions import Conversions as CV
from openpilot.common.params import Params, put_nonblocking
from openpilot.common.realtime import set_realtime_priority
from openpilot.common.transformations.orientation import rot_from_euler, euler_from_rot
from openpilot.system.swaglog import cloudlog

MIN_SPEED_FILTER = 15 * CV.MPH_TO_MS
MAX_VEL_ANGLE_STD = np.radians(0.25)
MAX_YAW_RATE_FILTER = np.radians(2)  # per second

MAX_HEIGHT_STD = np.exp(-3.5)

# This is at model frequency, blocks needed for efficiency
SMOOTH_CYCLES = 10
BLOCK_SIZE = 100
INPUTS_NEEDED = 5   # Minimum blocks needed for valid calibration
INPUTS_WANTED = 50   # We want a little bit more than we need for stability
MAX_ALLOWED_SPREAD = np.radians(2)
MOUNTING_OFFSET_THRESHOLD = MAX_ALLOWED_SPREAD
MOUNTING_OFFSET_CLEAR = np.radians(1.5)
MOUNTING_OFFSET_MIN_SAMPLES = BLOCK_SIZE
RPY_INIT = np.array([0.0,0.0,0.0])
WIDE_FROM_DEVICE_EULER_INIT = np.array([0.0, 0.0, 0.0])
HEIGHT_INIT = np.array([1.22])

# C2 mounting limits: about 5 degrees up, 8 degrees down, and 4 degrees left/right.
PITCH_LIMITS = np.array([-0.09074112085129739, 0.14907572052989657])
YAW_LIMITS = np.array([-0.06912048084718224, 0.06912048084718235])
DEBUG = os.getenv("DEBUG") is not None


def is_calibration_valid(rpy: np.ndarray) -> bool:
  return (PITCH_LIMITS[0] < rpy[1] < PITCH_LIMITS[1]) and (YAW_LIMITS[0] < rpy[2] < YAW_LIMITS[1])  # type: ignore


def get_calibration_adjustment(rpy: np.ndarray) -> str:
  horizontal = ""
  vertical = ""
  if rpy[2] <= YAW_LIMITS[0]:
    horizontal = "left"
  elif rpy[2] >= YAW_LIMITS[1]:
    horizontal = "right"

  if rpy[1] <= PITCH_LIMITS[0]:
    vertical = "down"
  elif rpy[1] >= PITCH_LIMITS[1]:
    vertical = "up"

  return "_".join(direction for direction in (horizontal, vertical) if direction)


def sanity_clip(rpy: np.ndarray) -> np.ndarray:
  if np.isnan(rpy).any():
    rpy = RPY_INIT
  return np.array([rpy[0],
                   np.clip(rpy[1], PITCH_LIMITS[0] - .005, PITCH_LIMITS[1] + .005),
                   np.clip(rpy[2], YAW_LIMITS[0] - .005, YAW_LIMITS[1] + .005)])

def moving_avg_with_linear_decay(prev_mean: np.ndarray, new_val: np.ndarray, idx: int, block_size: float) -> np.ndarray:
  return (idx*prev_mean + (block_size - idx) * new_val) / block_size

class Calibrator:
  def __init__(self, param_put: bool = False):
    self.param_put = param_put

    self.not_car = False

    # Read saved calibration
    params = Params()
    calibration_params = params.get("CalibrationParams")
    rpy_init = RPY_INIT
    wide_from_device_euler = WIDE_FROM_DEVICE_EULER_INIT
    height = HEIGHT_INIT
    valid_blocks = 0
    self.cal_status = log.LiveCalibrationData.Status.uncalibrated

    if param_put and calibration_params:
      try:
        msg = log.Event.from_bytes(calibration_params)
        # with log.Event.from_bytes(calibration_params) as msg:
        rpy_init = np.array(msg.liveCalibration.rpyCalib)
        valid_blocks = msg.liveCalibration.validBlocks
        wide_from_device_euler = np.array(msg.liveCalibration.wideFromDeviceEuler)
        height = np.array(msg.liveCalibration.height)
      except Exception:
        cloudlog.exception("Error reading cached CalibrationParams")

    self.reset(rpy_init, valid_blocks, wide_from_device_euler, height)
    self.update_status()
    self.startup_mount_check_active = bool(param_put and calibration_params and
                                           valid_blocks >= INPUTS_NEEDED and is_calibration_valid(rpy_init))
    self.startup_voice_event = "initial_calibrating" if param_put and valid_blocks < INPUTS_NEEDED else None

  def reset_calibration(self) -> None:
    self.startup_mount_check_active = False
    self.cal_status = log.LiveCalibrationData.Status.uncalibrated
    self.reset()
    self.update_status()

  def reset(self, rpy_init: np.ndarray = RPY_INIT,
                  valid_blocks: int = 0,
                  wide_from_device_euler_init: np.ndarray = WIDE_FROM_DEVICE_EULER_INIT,
                  height_init: np.ndarray = HEIGHT_INIT,
                  smooth_from: Optional[np.ndarray] = None) -> None:
    if not np.isfinite(rpy_init).all():
      self.rpy = RPY_INIT.copy()
    else:
      self.rpy = rpy_init.copy()

    if not np.isfinite(height_init).all() or len(height_init) != 1:
      self.height = HEIGHT_INIT.copy()
    else:
      self.height = height_init.copy()

    if not np.isfinite(wide_from_device_euler_init).all() or len(wide_from_device_euler_init) != 3:
      self.wide_from_device_euler = WIDE_FROM_DEVICE_EULER_INIT.copy()
    else:
      self.wide_from_device_euler = wide_from_device_euler_init.copy()

    if not np.isfinite(valid_blocks) or valid_blocks < 0:
      self.valid_blocks = 0
    else:
      self.valid_blocks = valid_blocks

    self.rpys = np.tile(self.rpy, (INPUTS_WANTED, 1))
    self.wide_from_device_eulers = np.tile(self.wide_from_device_euler, (INPUTS_WANTED, 1))
    self.heights = np.tile(self.height, (INPUTS_WANTED, 1))

    self.idx = 0
    self.block_idx = 0
    self.v_ego = 0.0
    self.mounting_offset_detected = False

    if smooth_from is None:
      self.old_rpy = RPY_INIT
      self.old_rpy_weight = 0.0
    else:
      self.old_rpy = smooth_from
      self.old_rpy_weight = 1.0

  def get_valid_idxs(self) -> List[int]:
    # exclude current block_idx from validity window
    before_current = list(range(self.block_idx))
    after_current = list(range(min(self.valid_blocks, self.block_idx + 1), self.valid_blocks))
    return before_current + after_current

  def update_status(self) -> None:
    valid_idxs = self.get_valid_idxs()
    if valid_idxs:
      self.wide_from_device_euler = np.mean(self.wide_from_device_eulers[valid_idxs], axis=0)
      self.height = np.mean(self.heights[valid_idxs], axis=0)
      rpys = self.rpys[valid_idxs]
      self.rpy = np.mean(rpys, axis=0)
      max_rpy_calib = np.array(np.max(rpys, axis=0))
      min_rpy_calib = np.array(np.min(rpys, axis=0))
      self.calib_spread = np.abs(max_rpy_calib - min_rpy_calib)
    else:
      self.calib_spread = np.zeros(3)

    if self.valid_blocks < INPUTS_NEEDED:
      if self.cal_status == log.LiveCalibrationData.Status.recalibrating:
        self.cal_status = log.LiveCalibrationData.Status.recalibrating
      else:
        self.cal_status = log.LiveCalibrationData.Status.uncalibrated
    elif is_calibration_valid(self.rpy):
      self.cal_status = log.LiveCalibrationData.Status.calibrated
    else:
      self.cal_status = log.LiveCalibrationData.Status.invalid

    # If spread is too high, assume mounting was changed and reset to last block.
    # Make the transition smooth. Abrupt transitions are not good for feedback loop through supercombo model.
    # TODO: add height spread check with smooth transition too
    if max(self.calib_spread) > MAX_ALLOWED_SPREAD and self.cal_status == log.LiveCalibrationData.Status.calibrated:
      self.reset(self.rpys[self.block_idx - 1], valid_blocks=INPUTS_NEEDED, smooth_from=self.rpy)
      self.update_status()
      self.mounting_offset_detected = True

    write_this_cycle = (self.idx == 0) and (self.block_idx % (INPUTS_WANTED//5) == 5)
    if self.param_put and write_this_cycle:
      put_nonblocking("CalibrationParams", self.get_msg().to_bytes())

  def handle_v_ego(self, v_ego: float) -> None:
    self.v_ego = v_ego

  def get_smooth_rpy(self) -> np.ndarray:
    if self.old_rpy_weight > 0:
      return self.old_rpy_weight * self.old_rpy + (1.0 - self.old_rpy_weight) * self.rpy
    else:
      return self.rpy

  def handle_cam_odom(self, trans: List[float],
                            rot: List[float],
                            wide_from_device_euler: List[float],
                            trans_std: List[float],
                            road_transform_trans: List[float],
                            road_transform_trans_std: List[float]) -> Optional[np.ndarray]:
    self.old_rpy_weight = max(0.0, self.old_rpy_weight - 1/SMOOTH_CYCLES)

    straight_and_fast = ((self.v_ego > MIN_SPEED_FILTER) and (trans[0] > MIN_SPEED_FILTER) and (abs(rot[2]) < MAX_YAW_RATE_FILTER))
    angle_std_threshold = MAX_VEL_ANGLE_STD
    height_std_threshold = MAX_HEIGHT_STD
    rpy_certain = np.arctan2(trans_std[1], trans[0]) < angle_std_threshold
    if len(road_transform_trans_std) == 3:
      height_certain = road_transform_trans_std[2] < height_std_threshold
    else:
      height_certain = True

    certain_if_calib = (rpy_certain and height_certain) or (self.valid_blocks < INPUTS_NEEDED)
    if not (straight_and_fast and certain_if_calib):
      return None

    observed_rpy = np.array([0,
                             -np.arctan2(trans[2], trans[0]),
                             np.arctan2(trans[1], trans[0])])
    new_rpy = euler_from_rot(rot_from_euler(self.get_smooth_rpy()).dot(rot_from_euler(observed_rpy)))
    new_rpy = sanity_clip(new_rpy)

    if len(wide_from_device_euler) == 3:
      new_wide_from_device_euler = np.array(wide_from_device_euler)
    else:
      new_wide_from_device_euler = WIDE_FROM_DEVICE_EULER_INIT

    if (len(road_transform_trans) == 3):
      new_height = np.array([road_transform_trans[2]])
    else:
      new_height = HEIGHT_INIT

    self.rpys[self.block_idx] = moving_avg_with_linear_decay(self.rpys[self.block_idx], new_rpy, self.idx, float(BLOCK_SIZE))
    self.wide_from_device_eulers[self.block_idx] = moving_avg_with_linear_decay(self.wide_from_device_eulers[self.block_idx],
                                                                                new_wide_from_device_euler, self.idx, float(BLOCK_SIZE))
    self.heights[self.block_idx] = moving_avg_with_linear_decay(self.heights[self.block_idx], new_height, self.idx, float(BLOCK_SIZE))

    # Compare a complete block against the accepted calibration. Match the
    # upstream C2 calibration spread threshold and do not gate engagement for
    # an in-range mounting change; calibration continuously follows the mount.
    samples_in_block = self.idx + 1
    if self.cal_status == log.LiveCalibrationData.Status.calibrated and samples_in_block >= MOUNTING_OFFSET_MIN_SAMPLES:
      delta = np.abs(self.rpys[self.block_idx] - self.rpy)
      if not self.mounting_offset_detected:
        self.mounting_offset_detected = (delta[1] > MOUNTING_OFFSET_THRESHOLD or
                                         delta[2] > MOUNTING_OFFSET_THRESHOLD)
      elif delta[1] < MOUNTING_OFFSET_CLEAR and delta[2] < MOUNTING_OFFSET_CLEAR:
        self.mounting_offset_detected = False

      if self.startup_mount_check_active and self.mounting_offset_detected:
        # Seed continuous calibration from the complete recent block. Preserve
        # the minimum valid block count so an in-range change does not disable
        # controls; only an absolute out-of-range angle becomes invalid.
        old_rpy = self.rpy.copy()
        new_mount_rpy = self.rpys[self.block_idx].copy()
        new_mount_wide = self.wide_from_device_eulers[self.block_idx].copy()
        new_mount_height = self.heights[self.block_idx].copy()
        self.reset(new_mount_rpy, valid_blocks=INPUTS_NEEDED,
                   wide_from_device_euler_init=new_mount_wide,
                   height_init=new_mount_height, smooth_from=old_rpy)
        self.update_status()
        self.startup_mount_check_active = False
        self.startup_voice_event = "recalibrating" if self.cal_status == log.LiveCalibrationData.Status.calibrated else "failure"
        return new_rpy
      elif self.startup_mount_check_active:
        # The startup mounting check passed. The cached calibration can now be
        # exposed as calibrated and controls may be engaged.
        self.startup_mount_check_active = False
        self.startup_voice_event = "check_passed"

    self.idx = (self.idx + 1) % BLOCK_SIZE
    if self.idx == 0:
      self.block_idx += 1
      self.valid_blocks = max(self.block_idx, self.valid_blocks)
      self.block_idx = self.block_idx % INPUTS_WANTED

    self.update_status()

    return new_rpy

  def get_msg(self) -> capnp.lib.capnp._DynamicStructBuilder:
    smooth_rpy = self.get_smooth_rpy()

    msg = messaging.new_message('liveCalibration')
    liveCalibration = msg.liveCalibration

    liveCalibration.validBlocks = self.valid_blocks
    liveCalibration.calStatus = self.cal_status
    liveCalibration.calPerc = min(100 * (self.valid_blocks * BLOCK_SIZE + self.idx) // (INPUTS_NEEDED * BLOCK_SIZE), 100)
    liveCalibration.rpyCalib = smooth_rpy.tolist()
    liveCalibration.rpyCalibSpread = self.calib_spread.tolist()
    liveCalibration.wideFromDeviceEuler = self.wide_from_device_euler.tolist()
    liveCalibration.height = self.height.tolist()

    if self.not_car:
      liveCalibration.validBlocks = INPUTS_NEEDED
      liveCalibration.calStatus = log.LiveCalibrationData.Status.calibrated
      liveCalibration.calPerc = 100.
      liveCalibration.rpyCalib = [0, 0, 0]
      liveCalibration.rpyCalibSpread = self.calib_spread.tolist()

    return msg

  def send_data(self, pm: messaging.PubMaster) -> None:
    pm.send('liveCalibration', self.get_msg())


def calibrationd_thread(sm: Optional[messaging.SubMaster] = None, pm: Optional[messaging.PubMaster] = None) -> NoReturn:
  gc.disable()
  set_realtime_priority(1)

  if sm is None:
    sm = messaging.SubMaster(['cameraOdometry', 'carState', 'carParams'], poll=['cameraOdometry'])

  if pm is None:
    pm = messaging.PubMaster(['liveCalibration'])

  calibrator = Calibrator(param_put=True)
  params = Params()
  mounting_offset_prev = calibrator.mounting_offset_detected
  startup_mount_check_prev = calibrator.startup_mount_check_active
  params.put_bool("MountingOffsetDetected", mounting_offset_prev)
  params.put_bool("StartupMountingCheckActive", startup_mount_check_prev)
  adjustment_direction_prev = get_calibration_adjustment(calibrator.rpy) if calibrator.cal_status == log.LiveCalibrationData.Status.invalid else ""
  if adjustment_direction_prev:
    params.put("CalibrationAdjustmentDirection", adjustment_direction_prev)
  else:
    params.remove("CalibrationAdjustmentDirection")
  params.remove("StartupCalibrationResult")
  if calibrator.startup_voice_event is not None:
    params.put("StartupCalibrationResult", calibrator.startup_voice_event)
    calibrator.startup_voice_event = None

  while 1:
    timeout = 0 if sm.frame == -1 else 100
    sm.update(timeout)

    if params.get_bool("ResetCalibration"):
      # Clear both the in-memory state and any cached state that may have been
      # queued for writing immediately before the reset request.
      calibrator.reset_calibration()
      params.remove("CalibrationParams")
      params.remove("ResetCalibration")
      calibrator.send_data(pm)

    calibrator.not_car = sm['carParams'].notCar

    if sm.updated['cameraOdometry']:
      calibrator.handle_v_ego(sm['carState'].vEgo)
      new_rpy = calibrator.handle_cam_odom(sm['cameraOdometry'].trans,
                                           sm['cameraOdometry'].rot,
                                           sm['cameraOdometry'].wideFromDeviceEuler,
                                           sm['cameraOdometry'].transStd,
                                           sm['cameraOdometry'].roadTransformTrans,
                                           sm['cameraOdometry'].roadTransformTransStd)

      if calibrator.mounting_offset_detected != mounting_offset_prev:
        mounting_offset_prev = calibrator.mounting_offset_detected
        params.put_bool("MountingOffsetDetected", mounting_offset_prev)

      if calibrator.startup_voice_event is not None:
        params.put("StartupCalibrationResult", calibrator.startup_voice_event)
        calibrator.startup_voice_event = None

      adjustment_direction = get_calibration_adjustment(calibrator.rpy) if calibrator.cal_status == log.LiveCalibrationData.Status.invalid else ""
      if adjustment_direction != adjustment_direction_prev:
        if adjustment_direction:
          params.put("CalibrationAdjustmentDirection", adjustment_direction)
        elif adjustment_direction_prev and calibrator.cal_status == log.LiveCalibrationData.Status.calibrated:
          params.put("CalibrationAdjustmentDirection", "recovered")
        else:
          params.remove("CalibrationAdjustmentDirection")
        adjustment_direction_prev = adjustment_direction

      if DEBUG and new_rpy is not None:
        print('got new rpy', new_rpy)

    if calibrator.startup_mount_check_active != startup_mount_check_prev:
      startup_mount_check_prev = calibrator.startup_mount_check_active
      params.put_bool("StartupMountingCheckActive", startup_mount_check_prev)

    # 4Hz driven by cameraOdometry
    if sm.frame % 5 == 0:
      calibrator.send_data(pm)


def main(sm: Optional[messaging.SubMaster] = None, pm: Optional[messaging.PubMaster] = None) -> NoReturn:
  calibrationd_thread(sm, pm)


if __name__ == "__main__":
  main()
