#include "selfdrive/ui/soundd/sound.h"

#include <cmath>

#include <QAudio>
#include <QAudioDeviceInfo>
#include <QDebug>

#include "cereal/messaging/messaging.h"
#include "common/util.h"
#include "common/params.h"

// TODO: detect when we can't play sounds
// TODO: detect when we can't display the UI

Sound::Sound(QObject *parent) : sm({"controlsState", "microphone", "carState", "deviceState"}) {
  qInfo() << "default audio device: " << QAudioDeviceInfo::defaultOutputDevice().deviceName();

  dp_device_audible_alert_mode = std::atoi(Params().get("dp_device_audible_alert_mode").c_str());
  for (auto &[alert, fn, loops] : sound_list) {
    QSoundEffect *s = new QSoundEffect(this);
    QObject::connect(s, &QSoundEffect::statusChanged, [=]() {
      assert(s->status() != QSoundEffect::Error);
    });
    s->setSource(QUrl::fromLocalFile("../../assets/sounds/" + fn));
    sounds[alert] = {s, loops};
  }
  mounting_offset_voice = new QSoundEffect(this);
  mounting_offset_voice->setSource(QUrl::fromLocalFile("../../assets/sounds/mounting_offset_zh.wav"));
  calibration_success_voice = new QSoundEffect(this);
  calibration_success_voice->setSource(QUrl::fromLocalFile("../../assets/sounds/calibration_success_zh.wav"));
  calibration_failure_voice = new QSoundEffect(this);
  calibration_failure_voice->setSource(QUrl::fromLocalFile("../../assets/sounds/calibration_failure_zh.wav"));
  calibration_check_passed_voice = new QSoundEffect(this);
  calibration_check_passed_voice->setSource(QUrl::fromLocalFile("../../assets/sounds/calibration_check_passed_zh.wav"));
  calibration_recalibrating_voice = new QSoundEffect(this);
  calibration_recalibrating_voice->setSource(QUrl::fromLocalFile("../../assets/sounds/calibration_recalibrating_zh.wav"));
  calibration_initial_voice = new QSoundEffect(this);
  calibration_initial_voice->setSource(QUrl::fromLocalFile("../../assets/sounds/calibration_initial_zh.wav"));
  temperature_warning_sound = new QSoundEffect(this);

  QTimer *timer = new QTimer(this);
  QObject::connect(timer, &QTimer::timeout, this, &Sound::update);
  timer->start(1000 / UI_FREQ);
}

void Sound::update() {
  sm.update(0);

  // Remind immediately on entering a warning band, then periodically while it
  // remains hot. Red and danger share the more urgent five-minute cadence.
  if (sm.updated("deviceState")) {
    const auto thermal_status = sm["deviceState"].getDeviceState().getThermalStatus();
    const int warning_level = thermal_status >= cereal::DeviceState::ThermalStatus::RED ? 2 :
                              thermal_status >= cereal::DeviceState::ThermalStatus::YELLOW ? 1 : 0;
    const uint64_t now = nanos_since_boot();
    const uint64_t reminder_interval = warning_level == 2 ? 5ULL * 60 * 1000000000 : 10ULL * 60 * 1000000000;
    const bool entered_warning_level = warning_level > temperature_warning_level;
    const bool reminder_due = warning_level > 0 &&
                              now - last_temperature_warning_time >= reminder_interval;

    if ((entered_warning_level || reminder_due) && dp_device_audible_alert_mode != 2) {
      const int temperature = qBound(60, static_cast<int>(std::round(
        sm["deviceState"].getDeviceState().getMaxTempC())), 130);
      const QString filename = QString("../../assets/sounds/temperature_zh_%1.wav")
                                 .arg(temperature, 3, 10, QLatin1Char('0'));
      temperature_warning_sound->setSource(QUrl::fromLocalFile(filename));
      temperature_warning_sound->play();
      last_temperature_warning_time = now;
    }
    if (warning_level == 0) {
      last_temperature_warning_time = 0;
    }
    temperature_warning_level = warning_level;
  }

  const bool offset_detected = Params().getBool("MountingOffsetDetected");
  if (offset_detected && !mounting_offset_detected && dp_device_audible_alert_mode != 2) {
    mounting_offset_voice->play();
  }
  mounting_offset_detected = offset_detected;

  const std::string calibration_result = Params().get("StartupCalibrationResult");
  if (!calibration_result.empty()) {
    if (dp_device_audible_alert_mode != 2) {
      if (calibration_result == "success") {
        calibration_success_voice->play();
      } else if (calibration_result == "failure") {
        calibration_failure_voice->play();
      } else if (calibration_result == "check_passed") {
        calibration_check_passed_voice->play();
      } else if (calibration_result == "recalibrating") {
        calibration_recalibrating_voice->play();
      } else if (calibration_result == "initial_calibrating") {
        calibration_initial_voice->play();
      }
    }
    Params().remove("StartupCalibrationResult");
  }

  #ifdef QCOM2
  // scale volume using ambient noise level
  if (sm.updated("microphone")) {
    float volume = util::map_val(sm["microphone"].getMicrophone().getFilteredSoundPressureWeightedDb(), 30.f, 60.f, 0.f, 1.f);
    volume = QAudio::convertVolume(volume, QAudio::LogarithmicVolumeScale, QAudio::LinearVolumeScale);
    // set volume on changes
    if (std::exchange(current_volume, std::nearbyint(volume * 10)) != current_volume) {
      Hardware::set_volume(volume);
    }
  }
  #else
  if (sm.updated("carState")) {
    float volume = util::map_val(sm["carState"].getCarState().getVEgo(), 11.f, 20.f, 0.f, 1.0f);
    volume = QAudio::convertVolume(volume, QAudio::LogarithmicVolumeScale, QAudio::LinearVolumeScale);
    volume = util::map_val(volume, 0.f, 1.f, Hardware::MIN_VOLUME, Hardware::MAX_VOLUME);
    for (auto &[s, loops] : sounds) {
      s->setVolume(std::round(100 * volume) / 100);
    }
    mounting_offset_voice->setVolume(std::round(100 * volume) / 100);
    calibration_success_voice->setVolume(std::round(100 * volume) / 100);
    calibration_failure_voice->setVolume(std::round(100 * volume) / 100);
    calibration_check_passed_voice->setVolume(std::round(100 * volume) / 100);
    calibration_recalibrating_voice->setVolume(std::round(100 * volume) / 100);
    calibration_initial_voice->setVolume(std::round(100 * volume) / 100);
    temperature_warning_sound->setVolume(std::round(100 * volume) / 100);
  }
  #endif
  setAlert(Alert::get(sm, 0));
}

void Sound::setAlert(const Alert &alert) {
  if (!current_alert.equal(alert)) {
    current_alert = alert;
    // stop sounds
    for (auto &[s, loops] : sounds) {
      // Only stop repeating sounds
      if (s->loopsRemaining() > 1 || s->loopsRemaining() == QSoundEffect::Infinite) {
        s->stop();
      }
    }

    // play sound
    if (shouldPlaySound(alert)) {
      auto &[s, loops] = sounds[alert.sound];
      s->setLoopCount(loops);
      s->play();
    }
  }
}

bool Sound::shouldPlaySound(const Alert &alert) {
//    tr("Standard"), tr("Warning/Alert"), tr("Off")
  if (dp_device_audible_alert_mode > 0) {
    // off - Does not emit any sound at all.
    if (dp_device_audible_alert_mode == 2) {
      return false;
    // Warning - Only emits sound when there is a warning.
    } else if (dp_device_audible_alert_mode == 1) {
      return (alert.sound == AudibleAlert::WARNING_IMMEDIATE || alert.sound == AudibleAlert::PROMPT_REPEAT || alert.sound == AudibleAlert::PROMPT_DISTRACTED);
    } else {
      return alert.sound != AudibleAlert::NONE;
    }
  } else {
    return alert.sound != AudibleAlert::NONE;
  }
}
