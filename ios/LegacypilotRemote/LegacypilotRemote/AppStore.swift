import Foundation

@MainActor
final class AppStore: ObservableObject {
  @Published var status = DeviceStatus.offline
  @Published var parameters: [String: String] = [:]
  @Published var parameterStates: [String: ParameterState] = [:]
  @Published var isLoading = false
  @Published var errorMessage: String?
  @Published var demoMode: Bool {
    didSet { defaults.set(demoMode, forKey: Keys.demoMode) }
  }
  @Published var deviceAddress: String {
    didSet { defaults.set(deviceAddress, forKey: Keys.deviceAddress) }
  }

  private let defaults: UserDefaults
  private var pollingTask: Task<Void, Never>?

  private enum Keys {
    static let deviceAddress = "deviceAddress"
    static let demoMode = "demoMode"
  }

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    deviceAddress = defaults.string(forKey: Keys.deviceAddress) ?? "http://172.20.10.2:8082"
    demoMode = defaults.object(forKey: Keys.demoMode) as? Bool ?? true
    if demoMode {
      status = .demo
      parameters = Self.demoParameters
      parameterStates = Self.demoParameterStates(values: parameters)
    }
  }

  deinit { pollingTask?.cancel() }

  func startPolling() {
    pollingTask?.cancel()
    pollingTask = Task { [weak self] in
      while !Task.isCancelled {
        await self?.refreshStatus(showSpinner: false)
        try? await Task.sleep(nanoseconds: 2_000_000_000)
      }
    }
  }

  func stopPolling() {
    pollingTask?.cancel()
    pollingTask = nil
  }

  func connect() async {
    isLoading = true
    errorMessage = nil
    defer { isLoading = false }
    if demoMode {
      status = .demo
      parameters = Self.demoParameters
      parameterStates = Self.demoParameterStates(values: parameters)
      return
    }
    do {
      let client = try APIClient(address: deviceAddress)
      async let newStatus = client.fetchStatus()
      async let newParameters = client.fetchParameters()
      status = try await newStatus
      let response = try await newParameters
      parameters = response.values
      parameterStates = response.states ?? [:]
    } catch {
      status = .offline
      errorMessage = error.localizedDescription
    }
  }

  func refreshStatus(showSpinner: Bool = true) async {
    if demoMode {
      status.updatedAt = Date()
      return
    }
    if showSpinner { isLoading = true }
    defer { if showSpinner { isLoading = false } }
    do {
      status = try await APIClient(address: deviceAddress).fetchStatus()
      errorMessage = nil
    } catch {
      status.online = false
      if showSpinner {
        errorMessage = error.localizedDescription
      }
    }
  }

  func refreshParameters() async {
    if demoMode { return }
    do {
      let response = try await APIClient(address: deviceAddress).fetchParameters()
      parameters = response.values
      parameterStates = response.states ?? [:]
      errorMessage = nil
    } catch {
      errorMessage = error.localizedDescription
    }
  }

  func setParameter(_ key: String, value: String) async {
    let oldValue = parameters[key]
    parameters[key] = value
    if demoMode {
      parameterStates = Self.demoParameterStates(values: parameters)
      return
    }
    do {
      let client = try APIClient(address: deviceAddress)
      try await client.updateParameter(key: key, value: value)
      let response = try await client.fetchParameters()
      parameters = response.values
      parameterStates = response.states ?? [:]
      errorMessage = nil
    } catch {
      parameters[key] = oldValue
      errorMessage = error.localizedDescription
    }
  }

  private static let demoParameters = Dictionary(
    uniqueKeysWithValues: ParameterCatalog.definitions.map { definition in
      let value: String
      switch definition.kind {
      case .toggle: value = "0"
      case .choice: value = "0"
      case .stringChoice(let choices): value = choices.first?.value ?? ""
      case .number(let range, _, _): value = String(range.lowerBound)
      case .text: value = ""
      }
      return (definition.key, value)
    }
  )

  private static func demoParameterStates(values: [String: String]) -> [String: ParameterState] {
    Dictionary(uniqueKeysWithValues: ParameterCatalog.definitions.map { definition in
      var visible = true
      if values["dp_0813"] == "1" && ["ExperimentalMode", "ExperimentalLongitudinalEnabled"].contains(definition.key) {
        visible = false
      } else if definition.key == "ExperimentalLongitudinalEnabled" {
        visible = false
      } else if definition.key == "dp_device_auto_shutdown_in" {
        visible = values["dp_device_auto_shutdown"] == "1"
      } else if definition.key == "dp_lat_lane_priority_mode_speed_based" {
        visible = values["dp_lat_lane_priority_mode"] == "1"
      }
      return (definition.key, ParameterState(visible: visible, enabled: true))
    })
  }
}
