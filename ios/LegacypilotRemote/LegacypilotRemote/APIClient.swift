import Foundation

enum APIError: LocalizedError {
  case invalidAddress
  case invalidResponse
  case server(Int)

  var errorDescription: String? {
    switch self {
    case .invalidAddress: return "设备地址无效"
    case .invalidResponse: return "设备返回了无法识别的数据"
    case .server(let code): return "设备请求失败（HTTP \(code)）"
    }
  }
}

struct APIClient {
  let baseURL: URL
  var session: URLSession = .shared

  init(address: String, session: URLSession = .shared) throws {
    var normalized = address.trimmingCharacters(in: .whitespacesAndNewlines)
    if !normalized.contains("://") { normalized = "http://" + normalized }
    guard let url = URL(string: normalized), url.host != nil else {
      throw APIError.invalidAddress
    }
    self.baseURL = url
    self.session = session
  }

  func fetchStatus() async throws -> DeviceStatus {
    try await request(path: "api/v1/status")
  }

  func fetchParameters() async throws -> ParameterValuesResponse {
    try await request(path: "api/v1/params")
  }

  func updateParameter(key: String, value: String) async throws {
    let encodedKey = key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? key
    let _: ParameterValue = try await request(
      path: "api/v1/params/\(encodedKey)", method: "PUT", body: ParameterValue(value: value)
    )
  }

  func resetCalibration() async throws {
    let _: ActionResponse = try await request(
      path: "api/v1/actions/reset-calibration", method: "POST", body: Optional<String>.none
    )
  }

  private func request<Response: Decodable, Body: Encodable>(
    path: String, method: String = "GET", body: Body?
  ) async throws -> Response {
    let url = baseURL.appendingPathComponent(path)
    var request = URLRequest(url: url, timeoutInterval: 5)
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    if let body {
      request.httpBody = try JSONEncoder().encode(body)
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
    guard (200..<300).contains(http.statusCode) else { throw APIError.server(http.statusCode) }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(Response.self, from: data)
  }

  private func request<Response: Decodable>(path: String) async throws -> Response {
    try await request(path: path, body: Optional<String>.none)
  }
}
