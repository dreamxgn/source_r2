import Foundation

@MainActor
final class AppStore: ObservableObject {
  @Published var status = DeviceStatus.offline
  @Published var parameters: [String: String] = [:]
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
      return
    }
    do {
      let client = try APIClient(address: deviceAddress)
      async let newStatus = client.fetchStatus()
      async let newParameters = client.fetchParameters()
      status = try await newStatus
      parameters = try await newParameters
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
      parameters = try await APIClient(address: deviceAddress).fetchParameters()
      errorMessage = nil
    } catch {
      errorMessage = error.localizedDescription
    }
  }

  func setParameter(_ key: String, value: String) async {
    let oldValue = parameters[key]
    parameters[key] = value
    guard !demoMode else { return }
    do {
      try await APIClient(address: deviceAddress).updateParameter(key: key, value: value)
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
}
