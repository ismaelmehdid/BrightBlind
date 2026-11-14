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

    func connect() {
        wanted = true
        open()
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
        guard let u = URL(string: url.trimmingCharacters(in: .whitespaces)) else {
            state = "bad url"
            return
        }
        state = "connecting"
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
