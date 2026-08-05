import Foundation

struct DeviceMessage: Codable, Identifiable, Equatable {
  let id: String
  let text: String
  let severity: Int
}

struct DeviceStatus: Codable, Equatable {
  var deviceName: String
  var online: Bool
  var onroad: Bool
  var engaged: Bool
  var vehicle: String?
  var version: String?
  var branch: String?
  var ipAddress: String?
  var thermalStatus: String
  var cpuTempC: Double?
  var gpuTempC: Double?
  var memoryTempC: Double?
  var ambientTempC: Double?
  var memoryPercent: Double?
  var storagePercent: Double?
  var speedKph: Double?
  var setSpeedKph: Double?
  var alert: String?
  var messages: [DeviceMessage]?
  var calibrationStatus: String?
  var calibrationProgress: Int?
  var calibrationPitchDeg: Double?
  var calibrationYawDeg: Double?
  var updatedAt: Date?

  static let offline = DeviceStatus(
    deviceName: "OP device", online: false, onroad: false, engaged: false,
    thermalStatus: "unknown"
  )

  static let demo = DeviceStatus(
    deviceName: "comma two", online: true, onroad: false, engaged: false,
    vehicle: "TOYOTA RAV4 2019", version: "0.8.16-r2", branch: "main",
    ipAddress: "172.20.10.2", thermalStatus: "green", cpuTempC: 58.5,
    gpuTempC: 55.2, memoryTempC: 51.8, ambientTempC: 37.4,
    memoryPercent: 46, storagePercent: 63, speedKph: 0, setSpeedKph: 0,
    messages: [.init(id: "Offroad_Recalibration", text: "检测到设备安装位置变化，请确认设备和支架固定牢固。", severity: 0)],
    calibrationStatus: "calibrated", calibrationProgress: 100,
    calibrationPitchDeg: 1.24, calibrationYawDeg: -0.38,
    updatedAt: Date()
  )
}

struct ParameterValuesResponse: Codable {
  let values: [String: String]
}

struct ParameterValue: Codable {
  let value: String
}

enum ParameterKind {
  case toggle
  case choice([String])
  case stringChoice([(label: String, value: String)])
  case number(range: ClosedRange<Int>, suffix: String, zeroLabel: String?)
  case text(placeholder: String)
}

struct ParameterDefinition: Identifiable {
  let key: String
  let title: String
  let detail: String
  let category: String
  let kind: ParameterKind
  let requiresReboot: Bool

  var id: String { key }
}

enum ParameterCatalog {
  static let definitions: [ParameterDefinition] = [
    .init(key: "OpenpilotEnabledToggle", title: "启用 openpilot", detail: "使用 openpilot 自适应巡航和车道保持功能。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "dp_0813", title: "使用 0.8.13.1 驾驶模型", detail: "切换到旧版驾驶模型。", category: "openpilot", kind: .toggle, requiresReboot: true),
    .init(key: "dp_logging", title: "启用行车记录", detail: "记录车辆状态和摄像头数据。", category: "openpilot", kind: .toggle, requiresReboot: true),
    .init(key: "ExperimentalLongitudinalEnabled", title: "openpilot 纵向控制", detail: "使用实验性 openpilot 纵向控制。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "ExperimentalMode", title: "实验模式", detail: "启用实验性驾驶功能。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "DisengageOnAccelerator", title: "踩加速踏板时退出", detail: "踩下加速踏板时退出 openpilot。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "LongitudinalPersonality", title: "驾驶个性", detail: "选择纵向跟车风格。", category: "openpilot", kind: .choice(["激进", "标准", "舒适"]), requiresReboot: false),
    .init(key: "IsLdwEnabled", title: "车道偏离警告", detail: "车辆无转向灯偏离车道时发出提醒。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "IsRhdDetected", title: "右舵驾驶", detail: "使用右舵驾驶员监控和交通习惯。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "RecordFront", title: "记录驾驶员摄像头", detail: "记录驾驶员摄像头数据。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "IsMetric", title: "使用公制单位", detail: "使用 km/h 显示速度。", category: "openpilot", kind: .toggle, requiresReboot: false),
    .init(key: "LanguageSetting", title: "设备界面语言", detail: "修改后设备 UI 需要重新启动。", category: "设备设置", kind: .stringChoice([
      ("English", "main_en"), ("Deutsch", "main_de"), ("Français", "main_fr"),
      ("Português", "main_pt-BR"), ("Türkçe", "main_tr"), ("ไทย", "main_th"),
      ("中文（繁體）", "main_zh-CHT"), ("中文（简体）", "main_zh-CHS"),
      ("한국어", "main_ko"), ("日本語", "main_ja")
    ]), requiresReboot: true),
    .init(key: "GsmRoaming", title: "允许蜂窝网络漫游", detail: "允许设备调制解调器使用漫游网络。", category: "网络", kind: .toggle, requiresReboot: false),
    .init(key: "GsmMetered", title: "蜂窝网络按流量计费", detail: "避免通过蜂窝网络上传大型文件。", category: "网络", kind: .toggle, requiresReboot: false),
    .init(key: "GsmApn", title: "蜂窝网络 APN", detail: "留空时由设备自动配置。", category: "网络", kind: .text(placeholder: "自动"), requiresReboot: false),
    .init(key: "dp_car_assigned", title: "指定车型", detail: "留空表示自动识别；必须使用 OP 支持列表中的完整车型名称。", category: "车型", kind: .text(placeholder: "自动识别"), requiresReboot: true),
    .init(key: "dp_car_dashcam_mode_removal", title: "移除行车记录仪模式", detail: "强制启用 openpilot 控制。", category: "总体", kind: .toggle, requiresReboot: true),
    .init(key: "dp_alka", title: "启用 ALKA", detail: "ACC MAIN 开启时始终启用横向控制。", category: "横向控制", kind: .toggle, requiresReboot: true),
    .init(key: "dp_lat_controller", title: "横向控制器", detail: "选择横向控制算法。", category: "横向控制", kind: .choice(["默认", "INDI", "LQR"]), requiresReboot: true),
    .init(key: "dp_lat_lane_priority_mode", title: "车道线优先模式", detail: "优先使用车道线，置信度低时自动回退。", category: "横向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_lat_lane_priority_mode_speed_based", title: "车道线模式最低速度", detail: "0 表示所有速度。", category: "横向控制", kind: .number(range: 0...120, suffix: " km/h", zeroLabel: "所有速度"), requiresReboot: false),
    .init(key: "dp_lat_lane_change_assist_speed", title: "变道辅助启用速度", detail: "0 表示关闭变道辅助。", category: "横向控制", kind: .number(range: 0...80, suffix: " mph", zeroLabel: "关闭"), requiresReboot: false),
    .init(key: "dp_long_use_df_tune", title: "动态跟车", detail: "根据驾驶个性动态调整跟车距离。", category: "纵向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_long_use_krkeegen_tune", title: "SnG Boost", detail: "使用 krkeegan 起步调校。", category: "纵向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_long_de2e", title: "动态端到端纵向控制", detail: "在端到端和 ACC 模式间动态切换。", category: "纵向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_mapd_vision_turn_control", title: "视觉弯道速度控制", detail: "根据视觉路径预测调整弯道速度。", category: "纵向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_long_accel_profile", title: "加速模式", detail: "选择纵向加速调校。", category: "纵向控制", kind: .choice(["OP", "节能", "标准", "运动"]), requiresReboot: false),
    .init(key: "dp_mapd", title: "启用 MapD", detail: "显示道路名称和限速。", category: "纵向控制", kind: .toggle, requiresReboot: true),
    .init(key: "dp_long_personality_btn", title: "屏幕驾驶个性按钮", detail: "在 OP 屏幕上显示驾驶个性按钮。", category: "纵向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_long_accel_btn", title: "屏幕加速模式按钮", detail: "在 OP 屏幕上显示加速模式按钮。", category: "纵向控制", kind: .toggle, requiresReboot: false),
    .init(key: "dp_device_no_ir_ctrl", title: "关闭红外灯", detail: "完全禁用设备红外灯。", category: "设备", kind: .toggle, requiresReboot: true),
    .init(key: "dp_device_disable_temp_check", title: "关闭温度检查", detail: "关闭设备过热状态检查。", category: "设备", kind: .toggle, requiresReboot: true),
    .init(key: "dp_no_fan_ctrl", title: "关闭风扇控制", detail: "禁用 openpilot 风扇控制。", category: "设备", kind: .toggle, requiresReboot: true),
    .init(key: "dp_no_gps_ctrl", title: "关闭 GPS 控制", detail: "禁用 openpilot GPS 控制。", category: "设备", kind: .toggle, requiresReboot: true),
    .init(key: "dp_device_enable_comma_registration", title: "启用 comma 注册", detail: "允许设备使用 comma 注册服务。", category: "设备", kind: .toggle, requiresReboot: true),
    .init(key: "dp_device_auto_shutdown", title: "自动关机", detail: "停车后自动关闭设备。", category: "设备", kind: .toggle, requiresReboot: true),
    .init(key: "dp_device_auto_shutdown_in", title: "自动关机等待时间", detail: "0 表示立即关机。", category: "设备", kind: .number(range: 0...600, suffix: " 分钟", zeroLabel: "立即"), requiresReboot: false),
    .init(key: "dp_device_display_off_mode", title: "屏幕关闭模式", detail: "选择设备屏幕自动关闭条件。", category: "设备", kind: .choice(["标准", "上路", "MAIN", "OP 启用"]), requiresReboot: true),
    .init(key: "dp_device_audible_alert_mode", title: "声音提醒模式", detail: "选择设备发出声音的条件。", category: "设备", kind: .choice(["标准", "仅警告", "关闭"]), requiresReboot: false),
    .init(key: "dp_toyota_sng", title: "丰田 SnG", detail: "适用于部分 Toyota/Lexus 车型。", category: "车型", kind: .toggle, requiresReboot: true),
    .init(key: "dp_toyota_enhanced_bsm", title: "丰田增强 BSM", detail: "通过调试 CAN 消息获取未过滤盲区信号。", category: "车型", kind: .toggle, requiresReboot: true),
    .init(key: "dp_toyota_auto_lock", title: "丰田自动落锁", detail: "车速超过 10 km/h 后尝试锁门。", category: "车型", kind: .toggle, requiresReboot: true),
    .init(key: "dp_toyota_auto_unlock", title: "丰田自动解锁", detail: "挂入 P 挡时尝试解锁。", category: "车型", kind: .toggle, requiresReboot: true),
    .init(key: "dp_toyota_zss", title: "丰田 ZSS 支持", detail: "仅在安装 Zorro Steering Sensor 后启用。", category: "车型", kind: .toggle, requiresReboot: true),
    .init(key: "dp_hkg_min_steer_speed_bypass", title: "现代/起亚最低转向速度绕过", detail: "允许低速转向控制。", category: "车型", kind: .toggle, requiresReboot: true),
    .init(key: "dp_vag_timebomb_bypass", title: "VAG 横向控制计时绕过", detail: "临时停用并恢复横向控制。", category: "车型", kind: .toggle, requiresReboot: true)
  ]
}
