#include "selfdrive/ui/qt/home.h"

#include <cmath>

#include <QHBoxLayout>
#include <QMouseEvent>
#include <QStackedWidget>
#include <QVBoxLayout>

#include "selfdrive/ui/qt/offroad/experimental_mode.h"
#include "selfdrive/ui/qt/util.h"
#include "selfdrive/ui/qt/widgets/prime.h"

#ifdef ENABLE_MAPS
#include "selfdrive/ui/qt/maps/map_settings.h"
#else
#include "selfdrive/ui/qt/widgets/drive_stats.h"
#endif

// HomeWindow: the container for the offroad and onroad UIs

HomeWindow::HomeWindow(QWidget* parent) : QWidget(parent) {
  QHBoxLayout *main_layout = new QHBoxLayout(this);
  main_layout->setMargin(0);
  main_layout->setSpacing(0);

  sidebar = new Sidebar(this);
  main_layout->addWidget(sidebar);
  QObject::connect(sidebar, &Sidebar::openSettings, this, &HomeWindow::openSettings);

  slayout = new QStackedLayout();
  main_layout->addLayout(slayout);

  home = new OffroadHome(this);
  QObject::connect(home, &OffroadHome::openSettings, this, &HomeWindow::openSettings);
  slayout->addWidget(home);

  onroad = new OnroadWindow(this);
  QObject::connect(onroad, &OnroadWindow::mapPanelRequested, this, [=] { sidebar->hide(); });
  slayout->addWidget(onroad);

  body = new BodyWindow(this);
  slayout->addWidget(body);

  driver_view = new DriverViewWindow(this);
  connect(driver_view, &DriverViewWindow::done, [=] {
    showDriverView(false);
  });
  slayout->addWidget(driver_view);
  setAttribute(Qt::WA_NoSystemBackground);
  QObject::connect(uiState(), &UIState::uiUpdate, this, &HomeWindow::updateState);
  QObject::connect(uiState(), &UIState::offroadTransition, this, &HomeWindow::offroadTransition);
  QObject::connect(uiState(), &UIState::offroadTransition, sidebar, &Sidebar::offroadTransition);
}

void HomeWindow::showSidebar(bool show) {
  sidebar->setVisible(show);
}

void HomeWindow::showMapPanel(bool show) {
  onroad->showMapPanel(show);
}

void HomeWindow::updateState(const UIState &s) {
  const SubMaster &sm = *(s.sm);

  // switch to the generic robot UI
  if (onroad->isVisible() && !body->isEnabled() && sm["carParams"].getCarParams().getNotCar()) {
    body->setEnabled(true);
    slayout->setCurrentWidget(body);
  }
}

void HomeWindow::offroadTransition(bool /*offroad*/) {
  body->setEnabled(false);
  // Keep the configuration UI visible while driving.  In particular, never
  // show OnroadWindow: its camera widget starts a VisionIPC thread and renders
  // every road-camera frame, which makes remote control over scrcpy sluggish.
  // The driving processes are unaffected; this only disables the UI preview.
  sidebar->show();
  slayout->setCurrentWidget(home);
}

void HomeWindow::showDriverView(bool show) {
  if (show) {
    emit closeSettings();
    slayout->setCurrentWidget(driver_view);
  } else {
    slayout->setCurrentWidget(home);
  }
  sidebar->setVisible(show == false);
}

void HomeWindow::mousePressEvent(QMouseEvent* e) {
  // Handle sidebar collapsing
  if ((onroad->isVisible() || body->isVisible()) && (!sidebar->isVisible() || e->x() > sidebar->width())) {
    sidebar->setVisible(!sidebar->isVisible() && !onroad->isMapVisible());
  }
}

void HomeWindow::mouseDoubleClickEvent(QMouseEvent* e) {
  HomeWindow::mousePressEvent(e);
  const SubMaster &sm = *(uiState()->sm);
  if (sm["carParams"].getCarParams().getNotCar()) {
    if (onroad->isVisible()) {
      slayout->setCurrentWidget(body);
    } else if (body->isVisible()) {
      slayout->setCurrentWidget(onroad);
    }
    showSidebar(false);
  }
}

// OffroadHome: the offroad home page

OffroadHome::OffroadHome(QWidget* parent) : QFrame(parent) {
  QVBoxLayout* main_layout = new QVBoxLayout(this);
  main_layout->setContentsMargins(40, 40, 40, 40);

  // top header
  QHBoxLayout* header_layout = new QHBoxLayout();
  header_layout->setContentsMargins(0, 0, 0, 0);
  header_layout->setSpacing(16);

  update_notif = new QPushButton(tr("UPDATE"));
  update_notif->setVisible(false);
  update_notif->setStyleSheet("background-color: #364DEF;");
  QObject::connect(update_notif, &QPushButton::clicked, [=]() { center_layout->setCurrentIndex(1); });
  header_layout->addWidget(update_notif, 0, Qt::AlignHCenter | Qt::AlignLeft);

  alert_notif = new QPushButton();
  alert_notif->setVisible(false);
  alert_notif->setStyleSheet("background-color: #E22C2C;");
  QObject::connect(alert_notif, &QPushButton::clicked, [=] { center_layout->setCurrentIndex(2); });
  header_layout->addWidget(alert_notif, 0, Qt::AlignHCenter | Qt::AlignLeft);

  version = new ElidedLabel();
  header_layout->addWidget(version, 0, Qt::AlignHCenter | Qt::AlignRight);

  main_layout->addLayout(header_layout);

  // main content
  main_layout->addSpacing(25);
  center_layout = new QStackedLayout();

  QWidget *home_widget = new QWidget(this);
  {
    QHBoxLayout *home_layout = new QHBoxLayout(home_widget);
    home_layout->setContentsMargins(0, 0, 0, 0);
    home_layout->setSpacing(30);

    // left: MapSettings/PrimeAdWidget
    QStackedWidget *left_widget = new QStackedWidget(this);
#ifdef ENABLE_MAPS
    left_widget->addWidget(new MapSettings);
#else
    left_widget->addWidget(new DriveStats);
#endif
    left_widget->addWidget(new PrimeAdWidget);
    left_widget->setStyleSheet("border-radius: 0px;");

    left_widget->setCurrentIndex(uiState()->primeType() ? 0 : 1);
    connect(uiState(), &UIState::primeTypeChanged, [=](int prime_type) {
      left_widget->setCurrentIndex(prime_type ? 0 : 1);
    });

    home_layout->addWidget(left_widget, 1);

    // right: ExperimentalModeButton, SetupWidget
    QWidget* right_widget = new QWidget(this);
    QVBoxLayout* right_column = new QVBoxLayout(right_widget);
    right_column->setContentsMargins(0, 0, 0, 0);
    right_widget->setFixedWidth(750);
    right_column->setSpacing(30);

    QFrame *calibration_widget = new QFrame(this);
    calibration_widget->setObjectName("calibration_widget");
    QVBoxLayout *calibration_layout = new QVBoxLayout(calibration_widget);
    calibration_layout->setContentsMargins(32, 22, 32, 22);
    calibration_layout->setSpacing(10);

    QLabel *calibration_title = new QLabel(tr("Live Calibration"));
    calibration_title->setObjectName("calibration_title");
    calibration_status = new QLabel(tr("Waiting for data"));
    calibration_status->setObjectName("calibration_status");
    calibration_progress = new QProgressBar;
    calibration_progress->setRange(0, 100);
    calibration_progress->setValue(0);
    calibration_progress->setTextVisible(true);

    QHBoxLayout *angles_layout = new QHBoxLayout;
    calibration_pitch = new QLabel(tr("Pitch: N/A"));
    calibration_yaw = new QLabel(tr("Yaw: N/A"));
    calibration_yaw->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    angles_layout->addWidget(calibration_pitch);
    angles_layout->addWidget(calibration_yaw);

    calibration_layout->addWidget(calibration_title);
    calibration_layout->addWidget(calibration_status);
    calibration_layout->addWidget(calibration_progress);
    calibration_layout->addLayout(angles_layout);
    right_column->addWidget(calibration_widget, 1);

    ExperimentalModeButton *experimental_mode = new ExperimentalModeButton(this);
    QObject::connect(experimental_mode, &ExperimentalModeButton::openSettings, this, &OffroadHome::openSettings);
    right_column->addWidget(experimental_mode, 1);

    SetupWidget *setup_widget = new SetupWidget;
    QObject::connect(setup_widget, &SetupWidget::openSettings, this, &OffroadHome::openSettings);
    right_column->addWidget(setup_widget, 1);

    home_layout->addWidget(right_widget, 1);
  }
  center_layout->addWidget(home_widget);

  // add update & alerts widgets
  update_widget = new UpdateAlert();
  QObject::connect(update_widget, &UpdateAlert::dismiss, [=]() { center_layout->setCurrentIndex(0); });
  center_layout->addWidget(update_widget);
  alerts_widget = new OffroadAlert();
  QObject::connect(alerts_widget, &OffroadAlert::dismiss, [=]() { center_layout->setCurrentIndex(0); });
  center_layout->addWidget(alerts_widget);

  main_layout->addLayout(center_layout, 1);

  // set up refresh timer
  timer = new QTimer(this);
  timer->callOnTimeout(this, &OffroadHome::refresh);
  connect(uiState(), &UIState::uiUpdate, this, [=](const UIState &) {
    updateCalibrationDisplay();
  });

  setStyleSheet(R"(
    * {
      color: white;
    }
    OffroadHome {
      background-color: black;
    }
    OffroadHome > QPushButton {
      padding: 15px 30px;
      border-radius: 0px;
      font-size: 40px;
      font-weight: 500;
    }
    OffroadHome > QLabel {
      font-size: 55px;
    }
    #calibration_widget {
      background-color: #292929;
      border-radius: 12px;
    }
    #calibration_status, #calibration_widget QLabel {
      font-size: 28px;
    }
    #calibration_title {
      font-size: 38px;
      font-weight: 600;
    }
    QProgressBar {
      height: 34px;
      border: 2px solid #555555;
      border-radius: 8px;
      background-color: #111111;
      text-align: center;
      font-size: 22px;
    }
    QProgressBar::chunk {
      border-radius: 6px;
      background-color: #00C853;
    }
  )");
}

void OffroadHome::updateCalibrationDisplay() {
  const SubMaster &sm = *(uiState()->sm);
  if (sm.rcv_frame("liveCalibration") == 0) {
    return;
  }

  const auto calib = sm["liveCalibration"].getLiveCalibration();
  const auto rpy = calib.getRpyCalib();
  QString status;
  switch (calib.getCalStatus()) {
    case cereal::LiveCalibrationData::Status::UNCALIBRATED:
      status = tr("Calibrating");
      break;
    case cereal::LiveCalibrationData::Status::RECALIBRATING:
      status = tr("Recalibrating");
      break;
    case cereal::LiveCalibrationData::Status::CALIBRATED:
      status = tr("Calibrated");
      break;
    case cereal::LiveCalibrationData::Status::INVALID:
      status = tr("Invalid calibration");
      break;
  }
  if (params.getBool("StartupMountingCheckActive")) {
    status = tr("Checking device position");
  }
  calibration_status->setText(status);
  calibration_progress->setValue(static_cast<int>(std::round(calib.getCalPerc())));

  if (rpy.size() == 3) {
    const double pitch = rpy[1] * (180.0 / M_PI);
    const double yaw = rpy[2] * (180.0 / M_PI);
    calibration_pitch->setText(tr("Pitch: %1° %2")
                                 .arg(std::abs(pitch), 0, 'f', 2)
                                 .arg(pitch > 0 ? tr("down") : tr("up")));
    calibration_yaw->setText(tr("Yaw: %1° %2")
                               .arg(std::abs(yaw), 0, 'f', 2)
                               .arg(yaw > 0 ? tr("left") : tr("right")));
  }
}

void OffroadHome::showEvent(QShowEvent *event) {
  refresh();
  timer->start(10 * 1000);
}

void OffroadHome::hideEvent(QHideEvent *event) {
  timer->stop();
}

void OffroadHome::refresh() {
  version->setText(getBrand() + " " +  QString::fromStdString(params.get("UpdaterCurrentDescription")));

  bool updateAvailable = update_widget->refresh();
  int alerts = alerts_widget->refresh();

  // pop-up new notification
  int idx = center_layout->currentIndex();
  if (!updateAvailable && !alerts) {
    idx = 0;
  } else if (updateAvailable && (!update_notif->isVisible() || (!alerts && idx == 2))) {
    idx = 1;
  } else if (alerts && (!alert_notif->isVisible() || (!updateAvailable && idx == 1))) {
    idx = 2;
  }
  center_layout->setCurrentIndex(idx);

  update_notif->setVisible(updateAvailable);
  alert_notif->setVisible(alerts);
  if (alerts) {
    alert_notif->setText(QString::number(alerts) + (alerts > 1 ? tr(" ALERTS") : tr(" ALERT")));
  }
}
