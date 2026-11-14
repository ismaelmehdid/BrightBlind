import Foundation
import UIKit

/// Wires glasses ↔ backend ↔ speakers. No product logic lives here on purpose:
/// the backend decides, the phone executes.
@MainActor
final class AppModel: ObservableObject {
    let glasses = GlassesController()
    let relay = Relay()
    let speaker = Speaker()
    @Published var lastPhoto: UIImage?
    @Published var lastPhotoInfo = ""

    init() {
        speaker.log = { [weak self] s in Task { @MainActor in self?.glasses.log(s) } }
        relay.log = { [weak self] s in Task { @MainActor in self?.glasses.log(s) } }

        glasses.onPhoto = { [weak self] jpeg, source, reqId in
            guard let self else { return }
            let image = UIImage(data: jpeg)
            self.lastPhoto = image
            self.lastPhotoInfo = "\(source) \(jpeg.count / 1024) KB \(image.map { "\(Int($0.size.width))x\(Int($0.size.height))" } ?? "")"
            var m: [String: Any] = [
                "type": "photo",
                "jpeg_b64": jpeg.base64EncodedString(),
                "w": Int(image?.size.width ?? 0),
                "h": Int(image?.size.height ?? 0),
                "source": source,
            ]
            if let reqId { m["req_id"] = reqId }
            self.relay.send(m)
        }
        glasses.onFrame = { [weak self] jpeg, w, h, seq in
            self?.relay.send(["type": "frame", "jpeg_b64": jpeg.base64EncodedString(), "w": w, "h": h, "seq": seq])
        }
        glasses.onButton = { [weak self] press in
            self?.relay.send(["type": "button", "press": press])
        }
        glasses.onState = { [weak self] in
            guard let self else { return }
            let g: String = {
                if self.glasses.streamState == "streaming" { return "streaming" }
                if self.glasses.sessionState == "started" { return "connected" }
                return "disconnected"
            }()
            var m: [String: Any] = ["type": "state", "glasses": g, "mode": self.glasses.mode.rawValue]
            if let b = self.glasses.battery { m["battery"] = b }
            self.relay.send(m)
        }
        relay.onCommand = { [weak self] cmd in self?.handle(cmd) }
    }

    func start() {
        glasses.observeRegistration()
        relay.connect()
    }

    private func handle(_ cmd: [String: Any]) {
        guard let type = cmd["type"] as? String else { return }
        switch type {
        case "capture":
            glasses.capture(reqId: cmd["req_id"] as? String, quality: cmd["quality"] as? String ?? "medium")
        case "stream":
            let on = (cmd["on"] as? Bool) ?? ((cmd["on"] as? Int).map { $0 != 0 } ?? false)
            glasses.setStreaming(on, fps: cmd["fps"] as? Double)
        case "say":
            let interrupt = (cmd["interrupt"] as? Bool) ?? true
            if let b64 = cmd["audio_b64"] as? String, let data = Data(base64Encoded: b64) {
                speaker.play(data, interrupt: interrupt)
            } else if let text = cmd["text"] as? String, !text.isEmpty {
                speaker.say(text, language: cmd["language"] as? String ?? "en-US", interrupt: interrupt)
            }
        case "stop_speaking":
            speaker.stop()
        case "beep":
            speaker.beep()
        case "hello", "ack", "pong":
            break
        default:
            glasses.log("unknown command: \(type)")
        }
    }
}
