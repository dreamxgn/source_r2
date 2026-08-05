import SwiftUI

@main
struct LegacypilotRemoteApp: App {
  @StateObject private var store = AppStore()

  var body: some Scene {
    WindowGroup {
      RootView()
        .environmentObject(store)
    }
  }
}
