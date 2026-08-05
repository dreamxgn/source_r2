#pragma once

#include <tuple>

#include <QMap>
#include <QSoundEffect>
#include <QString>

#include "system/hardware/hw.h"
#include "selfdrive/ui/ui.h"

const std::tuple<AudibleAlert, QString, int> sound_list[] = {
  // AudibleAlert, file name, loop count
  {AudibleAlert::ENGAGE, "engage.wav", 0},
  {AudibleAlert::DISENGAGE, "disengage.wav", 0},
  {AudibleAlert::REFUSE, "refuse.wav", 0},

  {AudibleAlert::PROMPT, "prompt.wav", 0},
  {AudibleAlert::PROMPT_REPEAT, "prompt.wav", QSoundEffect::Infinite},
  {AudibleAlert::PROMPT_DISTRACTED, "prompt_distracted.wav", QSoundEffect::Infinite},

  {AudibleAlert::WARNING_SOFT, "warning_soft.wav", QSoundEffect::Infinite},
  {AudibleAlert::WARNING_IMMEDIATE, "warning_immediate.wav", QSoundEffect::Infinite},
};

class Sound : public QObject {
public:
  explicit Sound(QObject *parent = 0);

protected:
  void update();
  void setAlert(const Alert &alert);
  bool shouldPlaySound(const Alert &alert);

  SubMaster sm;
  Alert current_alert = {};
  QMap<AudibleAlert, QPair<QSoundEffect *, int>> sounds;
  QSoundEffect *mounting_offset_voice;
  QSoundEffect *calibration_success_voice;
  QSoundEffect *calibration_failure_voice;
  QSoundEffect *calibration_check_passed_voice;
  QSoundEffect *calibration_recalibrating_voice;
  QSoundEffect *calibration_initial_voice;
  QSoundEffect *temperature_warning_sound;
  QMap<QString, QSoundEffect *> calibration_adjustment_voices;
  QString calibration_adjustment_direction;
  uint64_t last_calibration_adjustment_time = 0;
  bool mounting_offset_detected = false;
  int temperature_warning_level = 0;
  uint64_t last_temperature_warning_time = 0;
  int current_volume = -1;
  int dp_device_audible_alert_mode = 0;
};
