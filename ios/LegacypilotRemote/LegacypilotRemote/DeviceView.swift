import SwiftUI

struct DeviceView: View {
  @EnvironmentObject private var store: AppStore

  var body: some View {
    Form {
      Section("连接") {
        TextField("http://172.20.10.2:8082", text: $store.deviceAddress)
          .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
        Toggle("演示模式", isOn: $store.demoMode)
        Button {
          Task { await store.connect() }
        } label: {
          HStack {
            Text("连接")
            Spacer()
            if store.isLoading { ProgressView() }
          }
        }
        .disabled(store.isLoading)
      }
      Section("状态") {
        LabeledContent("连接", value: store.status.online ? "在线" : "离线")
        LabeledContent("设备", value: store.status.deviceName)
        LabeledContent("地址", value: store.deviceAddress)
      }
      Section {
        Text("设备地址会保存在本机。第一版使用两秒轮询，设备端 API 完成后即可连接真实设备。")
          .font(.footnote).foregroundStyle(.secondary)
      }
    }
    .navigationTitle("设备")
  }
}
