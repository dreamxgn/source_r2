import SwiftUI

struct RootView: View {
  @EnvironmentObject private var store: AppStore
  @Environment(\.scenePhase) private var scenePhase

  var body: some View {
    TabView {
      NavigationStack { OverviewView() }
        .tabItem { Label("概览", systemImage: "gauge.with.dots.needle.67percent") }
      NavigationStack { ParametersView() }
        .tabItem { Label("配置", systemImage: "slider.horizontal.3") }
      NavigationStack { DeviceView() }
        .tabItem { Label("设备", systemImage: "iphone.and.arrow.forward") }
    }
    .safeAreaInset(edge: .top, spacing: 0) {
      BackendConnectionBar(
        isConnected: store.status.online,
        isDemoMode: store.demoMode
      )
    }
    .task { store.startPolling() }
    .onChange(of: scenePhase) { _, phase in
      if phase == .active { store.startPolling() } else { store.stopPolling() }
    }
    .alert("连接问题", isPresented: Binding(
      get: { store.errorMessage != nil },
      set: { if !$0 { store.errorMessage = nil } }
    )) {
      Button("好", role: .cancel) { store.errorMessage = nil }
    } message: {
      Text(store.errorMessage ?? "未知错误")
    }
  }
}

private struct BackendConnectionBar: View {
  let isConnected: Bool
  let isDemoMode: Bool

  private var color: Color {
    if isDemoMode { return .blue }
    return isConnected ? Color(red: 0.12, green: 0.68, blue: 0.32) : .orange
  }

  private var title: String {
    if isDemoMode { return "演示模式" }
    return isConnected ? "后端已连接" : "后端离线"
  }

  private var systemImage: String {
    if isDemoMode { return "play.circle.fill" }
    return isConnected ? "checkmark.circle.fill" : "exclamationmark.circle.fill"
  }

  var body: some View {
    HStack(spacing: 5) {
      Image(systemName: systemImage)
      Text(title)
    }
    .font(.caption2.weight(.semibold))
    .foregroundStyle(.white)
    .frame(maxWidth: .infinity)
    .padding(.vertical, 3)
    .background(color)
    .animation(.easeInOut(duration: 0.2), value: color)
    .accessibilityElement(children: .combine)
    .accessibilityLabel(title)
  }
}
