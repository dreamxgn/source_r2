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
