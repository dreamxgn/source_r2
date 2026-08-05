import SwiftUI

struct OverviewView: View {
  @EnvironmentObject private var store: AppStore
  @State private var confirmingCalibrationReset = false

  var body: some View {
    ScrollView {
      VStack(spacing: 16) {
        connectionCard
        if let alert = store.status.alert, !alert.isEmpty {
          Label(alert, systemImage: "exclamationmark.triangle.fill")
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding().background(.orange.opacity(0.16), in: RoundedRectangle(cornerRadius: 16))
        }
        ForEach(store.status.messages ?? []) { message in
          Label(message.text, systemImage: message.severity > 0 ? "exclamationmark.triangle.fill" : "info.circle.fill")
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background((message.severity > 0 ? Color.red : Color.blue).opacity(0.14), in: RoundedRectangle(cornerRadius: 16))
        }
        speedCard
        metricsGrid
        drivingControlsCard
        temperatureCard
        calibrationCard
        informationCard
      }
      .padding()
    }
    .navigationTitle("Legacypilot")
    .refreshable { await store.connect() }
    .confirmationDialog("确定重置设备校准吗？", isPresented: $confirmingCalibrationReset, titleVisibility: .visible) {
      Button("重置校准", role: .destructive) { Task { await store.resetCalibration() } }
      Button("取消", role: .cancel) {}
    } message: {
      Text("设备需要重新行驶一段距离完成校准。")
    }
  }

  private var connectionCard: some View {
    HStack(spacing: 14) {
      Image(systemName: store.status.online ? "checkmark.circle.fill" : "wifi.slash")
        .font(.system(size: 34)).foregroundStyle(store.status.online ? .green : .secondary)
      VStack(alignment: .leading, spacing: 4) {
        Text(store.status.deviceName).font(.headline)
        Text(store.status.online ? drivingState : "未连接")
          .font(.subheadline).foregroundStyle(.secondary)
      }
      Spacer()
      if store.demoMode { Text("演示").font(.caption).padding(6).background(.blue.opacity(0.14), in: Capsule()) }
    }
    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
  }

  private var drivingState: String {
    if store.status.engaged { return "已启用 · 行驶中" }
    if store.status.onroad { return "上路 · 未启用" }
    return "停车状态"
  }

  private var metricsGrid: some View {
    LazyVGrid(columns: [.init(.flexible()), .init(.flexible())], spacing: 12) {
      MetricCard(title: "CPU 温度", value: formatted(store.status.cpuTempC, suffix: "°C"), icon: "thermometer.medium")
      MetricCard(title: "内存", value: formatted(store.status.memoryPercent, suffix: "%"), icon: "memorychip")
      MetricCard(title: "存储", value: formatted(store.status.storagePercent, suffix: "%"), icon: "internaldrive")
      MetricCard(title: "热状态", value: store.status.thermalStatus, icon: "flame")
    }
  }

  private var speedCard: some View {
    VStack(alignment: .leading, spacing: 14) {
      Label("行驶速度", systemImage: "speedometer").font(.headline)
      HStack(alignment: .firstTextBaseline) {
        VStack(alignment: .leading, spacing: 2) {
          Text("当前车速").font(.caption).foregroundStyle(.secondary)
          Text(speedText(store.status.speedKph)).font(.system(size: 38, weight: .bold, design: .rounded))
        }
        Spacer()
        VStack(alignment: .trailing, spacing: 2) {
          Text("OP 限定车速").font(.caption).foregroundStyle(.secondary)
          Text(speedText(store.status.setSpeedKph)).font(.title2.bold())
        }
      }
    }
    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
  }

  private func speedText(_ speed: Double?) -> String {
    speed.map { String(format: "%.0f km/h", $0) } ?? "— km/h"
  }

  private var informationCard: some View {
    VStack(spacing: 12) {
      InfoRow(label: "车辆", value: store.status.vehicle ?? "—")
      Divider()
      InfoRow(label: "版本", value: store.status.version ?? "—")
      Divider()
      InfoRow(label: "分支", value: store.status.branch ?? "—")
      Divider()
      InfoRow(label: "IP 地址", value: store.status.ipAddress ?? "—")
    }
    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
  }

  private var drivingControlsCard: some View {
    VStack(alignment: .leading, spacing: 12) {
      Label("驾驶快捷调节", systemImage: "slider.horizontal.3").font(.headline)
      HStack(spacing: 12) {
        QuickControlButton(
          title: "加速模式", value: accelerationProfile,
          systemImage: "bolt.fill", enabled: canChange("dp_long_accel_profile")
        ) { cycleParameter("dp_long_accel_profile", count: 4) }
        QuickControlButton(
          title: "驾驶个性", value: drivingPersonality,
          systemImage: "car.fill", enabled: canChange("LongitudinalPersonality")
        ) { cycleParameter("LongitudinalPersonality", count: 3) }
      }
    }
    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
  }

  private var temperatureCard: some View {
    VStack(alignment: .leading, spacing: 12) {
      Label("实际温度", systemImage: "thermometer.medium").font(.headline)
      InfoRow(label: "CPU", value: temperature(store.status.cpuTempC))
      Divider()
      InfoRow(label: "GPU", value: temperature(store.status.gpuTempC))
      Divider()
      InfoRow(label: "内存", value: temperature(store.status.memoryTempC))
      Divider()
      InfoRow(label: "环境", value: temperature(store.status.ambientTempC))
    }
    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
  }

  private var calibrationCard: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        Label("设备校准", systemImage: "scope").font(.headline)
        Spacer()
        Text(calibrationStatus).foregroundStyle(.secondary)
      }
      ProgressView(value: Double(store.status.calibrationProgress ?? 0), total: 100)
      InfoRow(label: "进度", value: store.status.calibrationProgress.map { "\($0)%" } ?? "—")
      Divider()
      InfoRow(label: "俯仰角", value: angle(store.status.calibrationPitchDeg, positive: "向下", negative: "向上"))
      Divider()
      InfoRow(label: "偏航角", value: angle(store.status.calibrationYawDeg, positive: "向左", negative: "向右"))
      Button(role: .destructive) { confirmingCalibrationReset = true } label: {
        Label("重置校准", systemImage: "arrow.counterclockwise")
          .frame(maxWidth: .infinity)
      }
      .disabled(!store.status.online)
    }
    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
  }

  private var calibrationStatus: String {
    switch store.status.calibrationStatus {
    case "uncalibrated": return "校准中"
    case "calibrated": return "已校准"
    case "invalid": return "校准无效"
    case "recalibrating": return "重新校准中"
    default: return "等待数据"
    }
  }

  private func temperature(_ value: Double?) -> String {
    value.map { String(format: "%.1f °C", $0) } ?? "—"
  }

  private func angle(_ value: Double?, positive: String, negative: String) -> String {
    guard let value else { return "—" }
    return String(format: "%.2f° %@", abs(value), value >= 0 ? positive : negative)
  }

  private var accelerationProfile: String {
    let labels = ["OP", "节能", "标准", "运动"]
    return labels[safe: Int(store.parameters["dp_long_accel_profile"] ?? "0") ?? 0] ?? "OP"
  }

  private var drivingPersonality: String {
    let labels = ["激进", "标准", "舒适"]
    return labels[safe: Int(store.parameters["LongitudinalPersonality"] ?? "1") ?? 1] ?? "标准"
  }

  private func canChange(_ key: String) -> Bool {
    store.status.online && (store.parameterStates[key]?.enabled ?? true)
  }

  private func cycleParameter(_ key: String, count: Int) {
    let current = Int(store.parameters[key] ?? "0") ?? 0
    Task { await store.setParameter(key, value: String((current + 1) % count)) }
  }

  private func formatted(_ value: Double?, suffix: String) -> String {
    value.map { String(format: "%.0f%@", $0, suffix) } ?? "—"
  }
}

private struct QuickControlButton: View {
  let title: String
  let value: String
  let systemImage: String
  let enabled: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      VStack(spacing: 8) {
        Image(systemName: systemImage).font(.title2)
        Text(title).font(.caption).foregroundStyle(.secondary)
        Text(value).font(.headline)
      }
      .frame(maxWidth: .infinity).padding(.vertical, 12)
      .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
    }
    .buttonStyle(.plain).disabled(!enabled).opacity(enabled ? 1 : 0.5)
  }
}

private extension Array {
  subscript(safe index: Int) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}

private struct MetricCard: View {
  let title: String
  let value: String
  let icon: String
  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Label(title, systemImage: icon).font(.caption).foregroundStyle(.secondary)
      Text(value).font(.title2.bold())
    }
    .frame(maxWidth: .infinity, alignment: .leading).padding()
    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
  }
}

private struct InfoRow: View {
  let label: String
  let value: String
  var body: some View {
    HStack { Text(label).foregroundStyle(.secondary); Spacer(); Text(value).multilineTextAlignment(.trailing) }
  }
}
