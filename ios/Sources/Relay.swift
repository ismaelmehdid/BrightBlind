import Foundation

/// WebSocket client for the backend. JSON text frames, see the contract in the repo README.
/// Reconnects by itself; the app never has to think about the link.
@MainActor
final class Relay: ObservableObject {
    @Published var state = "disconnected"
    @Published var url: String {
        didSet { UserDefaults.standard.set(url, forKey: "relayURL") }
    }
    @Published var sent = 0
    @Published var received = 0

    /// Commands from the backend, decoded JSON objects.
    var onCommand: (@MainActor ([String: Any]) -> Void)?
    var log: ((String) -> Void)?

    private var task: URLSessionWebSocketTask?
    private var wanted = false
    private var backoff: TimeInterval = 1
    private var pingTimer: Timer?
    private let session = URLSession(configuration: .default)

    init() {
        url = UserDefaults.standard.string(forKey: "relayURL") ?? "ws://192.168.0.10:8765/ws"
    }

    /// The backend address also lives in the repo (a public gist, see ios/README.md), so it can be changed
    /// with a push instead of typing on the phone. A non-empty file wins over the text field.
    private static let remoteConfig = "https://gist.githubusercontent.com/andriidrok1/132465d630f612f6917d308f773119e5/raw/backend-url.txt"

    func connect() {
        wanted = true
        Task { @MainActor in
            if let remote = await Self.fetchRemoteURL(), remote != self.url {
                self.log?("backend url from repo: \(remote)")
                self.url = remote
            }
            self.open()
        }
    }

    private static func fetchRemoteURL() async -> String? {
        guard let u = URL(string: remoteConfig + "?t=\(Int(Date().timeIntervalSince1970))") else { return nil }
        var req = URLRequest(url: u, cachePolicy: .reloadIgnoringLocalAndRemoteCacheData, timeoutInterval: 5)
        req.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let text = String(data: data, encoding: .utf8) else { return nil }
        let line = text.split(whereSeparator: \.isNewline).first.map(String.init)?.trimmingCharacters(in: .whitespaces) ?? ""
        return line.hasPrefix("ws") ? line : nil
    }

    func disconnect() {
        wanted = false
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        pingTimer?.invalidate()
        state = "disconnected"
    }

    private func open() {
        guard wanted, task == nil else { return }
        guard let u = URL(string: url.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            state = "bad url"
            log?("ws: bad url '\(url)'")
            return
        }
        state = "connecting"
        log?("ws connecting to \(u.absoluteString)")
        let t = session.webSocketTask(with: u)
        task = t
        t.resume()
        receiveLoop(t)
        send(["type": "hello", "client": "glasses", "caps": ["capture", "stream", "say", "button"]])
        pingTimer?.invalidate()
        pingTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.ping() }
        }
    }

    private func ping() {
        task?.sendPing { [weak self] error in
            Task { @MainActor in
                if let error { self?.dropped("ping: \(error.localizedDescription)") }
            }
        }
    }

    private func receiveLoop(_ t: URLSessionWebSocketTask) {
        t.receive { [weak self] result in
            Task { @MainActor in
                guard let self, self.task === t else { return }
                switch result {
                case .failure(let error):
                    self.dropped(error.localizedDescription)
                case .success(let message):
                    self.state = "connected"
                    self.backoff = 1
                    self.received += 1
                    switch message {
                    case .string(let text): self.handle(text)
                    case .data(let data): if let text = String(data: data, encoding: .utf8) { self.handle(text) }
                    @unknown default: break
                    }
                    self.receiveLoop(t)
                }
            }
        }
    }

    private func handle(_ text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            log?("ws: not a JSON object: \(text.prefix(80))")
            return
        }
        onCommand?(obj)
    }

    private func dropped(_ why: String) {
        log?("ws dropped: \(why)")
        task?.cancel()
        task = nil
        state = "reconnecting"
        guard wanted else { return }
        let delay = backoff
        backoff = min(backoff * 2, 10)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            Task { @MainActor in self?.open() }
        }
    }

    /// Adds `ts` and sends. Silently drops when not connected (the backend re-asks).
    func send(_ message: [String: Any]) {
        guard let task else { return }
        var m = message
        m["ts"] = Int(Date().timeIntervalSince1970 * 1000)
        guard let data = try? JSONSerialization.data(withJSONObject: m),
              let text = String(data: data, encoding: .utf8) else { return }
        task.send(.string(text)) { [weak self] error in
            Task { @MainActor in
                if let error { self?.dropped("send: \(error.localizedDescription)") } else { self?.sent += 1 }
            }
        }
    }
}
