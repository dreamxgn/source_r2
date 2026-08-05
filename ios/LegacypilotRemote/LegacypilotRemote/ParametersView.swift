import SwiftUI

struct ParametersView: View {
  @EnvironmentObject private var store: AppStore
  @State private var searchText = ""

  private var categories: [String] {
    Array(Set(filtered.map(\.category))).sorted()
  }

  private var filtered: [ParameterDefinition] {
    guard !searchText.isEmpty else { return ParameterCatalog.definitions }
    return ParameterCatalog.definitions.filter {
      $0.title.localizedCaseInsensitiveContains(searchText) || $0.key.localizedCaseInsensitiveContains(searchText)
    }
  }

  var body: some View {
    List {
      if !store.status.online {
        Label("连接设备后才能同步配置", systemImage: "wifi.slash").foregroundStyle(.secondary)
      }
      ForEach(categories, id: \.self) { category in
        Section(category) {
          ForEach(filtered.filter { $0.category == category }) { definition in
            ParameterRow(definition: definition)
          }
        }
      }
    }
    .navigationTitle("配置")
    .searchable(text: $searchText, prompt: "名称或参数键")
    .refreshable { await store.refreshParameters() }
  }
}

private struct ParameterRow: View {
  @EnvironmentObject private var store: AppStore
  let definition: ParameterDefinition

  private var value: String { store.parameters[definition.key] ?? "0" }

  var body: some View {
    switch definition.kind {
    case .toggle:
      Toggle(isOn: Binding(
        get: { value == "1" },
        set: { newValue in Task { await store.setParameter(definition.key, value: newValue ? "1" : "0") } }
      )) { title }
    case .choice(let choices):
      Picker(selection: Binding(
        get: { Int(value) ?? 0 },
        set: { newValue in Task { await store.setParameter(definition.key, value: String(newValue)) } }
      )) {
        ForEach(choices.indices, id: \.self) { Text(choices[$0]).tag($0) }
      } label: { title }
    case .stringChoice(let choices):
      Picker(selection: Binding(
        get: { value },
        set: { newValue in Task { await store.setParameter(definition.key, value: newValue) } }
      )) {
        ForEach(choices, id: \.value) { Text($0.label).tag($0.value) }
      } label: { title }
    case .number(let range, let suffix, let zeroLabel):
      NavigationLink {
        NumberParameterView(definition: definition, range: range, suffix: suffix, zeroLabel: zeroLabel)
      } label: {
        HStack { title; Spacer(); Text(numberLabel(Int(value) ?? range.lowerBound, suffix: suffix, zeroLabel: zeroLabel)).foregroundStyle(.secondary) }
      }
    case .text(let placeholder):
      NavigationLink {
        TextParameterView(definition: definition, placeholder: placeholder)
      } label: {
        HStack { title; Spacer(); Text(value.isEmpty ? placeholder : value).lineLimit(1).foregroundStyle(.secondary) }
      }
    }
  }

  private var title: some View {
    VStack(alignment: .leading, spacing: 3) {
      HStack { Text(definition.title); if definition.requiresReboot { Image(systemName: "arrow.clockwise").font(.caption).foregroundStyle(.orange) } }
      Text(definition.key).font(.caption2.monospaced()).foregroundStyle(.secondary)
    }
  }

  private func numberLabel(_ value: Int, suffix: String, zeroLabel: String?) -> String {
    value == 0 ? (zeroLabel ?? "0\(suffix)") : "\(value)\(suffix)"
  }
}

private struct TextParameterView: View {
  @EnvironmentObject private var store: AppStore
  @Environment(\.dismiss) private var dismiss
  let definition: ParameterDefinition
  let placeholder: String
  @State private var value = ""

  var body: some View {
    Form {
      Section {
        TextField(placeholder, text: $value)
          .textInputAutocapitalization(.never)
          .autocorrectionDisabled()
      } footer: { Text(definition.detail) }
      Button("保存") {
        Task {
          await store.setParameter(definition.key, value: value.trimmingCharacters(in: .whitespacesAndNewlines))
          dismiss()
        }
      }
    }
    .navigationTitle(definition.title)
    .onAppear { value = store.parameters[definition.key] ?? "" }
  }
}

private struct NumberParameterView: View {
  @EnvironmentObject private var store: AppStore
  let definition: ParameterDefinition
  let range: ClosedRange<Int>
  let suffix: String
  let zeroLabel: String?
  @State private var value: Int = 0

  var body: some View {
    Form {
      Section {
        Stepper(value: $value, in: range) {
          Text(value == 0 ? (zeroLabel ?? "0\(suffix)") : "\(value)\(suffix)").font(.title2.monospacedDigit())
        }
      } footer: { Text(definition.detail) }
      Button("保存") { Task { await store.setParameter(definition.key, value: String(value)) } }
    }
    .navigationTitle(definition.title)
    .onAppear { value = Int(store.parameters[definition.key] ?? "") ?? range.lowerBound }
  }
}
