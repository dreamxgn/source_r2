import SwiftUI

struct OverviewView: View {
  @EnvironmentObject private var store: AppStore

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
        metricsGrid
        temperatureCard
        calibrationCard
        informationCard
      }
      .padding()
    }
    .navigationTitle("Legacypilot")
    .refreshable { await store.connect() }
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

  private func formatted(_ value: Double?, suffix: String) -> String {
    value.map { String(format: "%.0f%@", $0, suffix) } ?? "—"
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
