import Foundation
import UIKit

/// Wires glasses ↔ backend ↔ speakers. No product logic lives here on purpose:
/// the backend decides, the phone executes.
@MainActor
final class AppModel: ObservableObject {
    let glasses = GlassesController()
    let relay = Relay()
    let speaker = Speaker()
    let heading = Heading()
    @Published var lastPhoto: UIImage?
    @Published var lastPhotoInfo = ""

    init() {
        speaker.log = { [weak self] s in Task { @MainActor in self?.glasses.log(s) } }
        relay.log = { [weak self] s in Task { @MainActor in self?.glasses.log(s) } }

        glasses.onPhoto = { [weak self] jpeg, source, reqId in
            guard let self else { return }
            // The standalone shutter returns HEIC; the contract (and the backend) want JPEG.
            var jpeg = jpeg
            if !(jpeg.count > 2 && jpeg[jpeg.startIndex] == 0xFF && jpeg[jpeg.startIndex + 1] == 0xD8),
               let converted = UIImage(data: jpeg)?.jpegData(compressionQuality: 0.85) {
                self.glasses.log("photo converted HEIC → JPEG, \(converted.count / 1024) KB")
                jpeg = converted
            }
            let image = UIImage(data: jpeg)
            self.lastPhoto = image
            self.lastPhotoInfo = "\(source) \(jpeg.count / 1024) KB \(image.map { "\(Int($0.size.width))x\(Int($0.size.height))" } ?? "")"
            var m: [String: Any] = [
                "type": "photo",
                "jpeg_b64": jpeg.base64EncodedString(),
                "w": Int(image?.size.width ?? 0),
                "h": Int(image?.size.height ?? 0),
                "source": source,
                "yaw": (self.heading.yaw * 10).rounded() / 10,
            ]
            if let reqId { m["req_id"] = reqId }
            self.relay.send(m)
        }
        glasses.onFrame = { [weak self] jpeg, w, h, seq in
            guard let self else { return }
            self.relay.send(["type": "frame", "jpeg_b64": jpeg.base64EncodedString(), "w": w, "h": h, "seq": seq,
                             "yaw": (self.heading.yaw * 10).rounded() / 10])
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
        heading.log = { [weak self] s in self?.glasses.log(s) }
        heading.speak = { [weak self] cue in self?.speaker.say(cue, interrupt: true) }
        heading.onZone = { [weak self] zone, off in
            guard let self else { return }
            self.relay.send(["type": "guide_state", "zone": zone, "offset": off.rounded(), "yaw": self.heading.yaw.rounded()])
        }
        relay.onCommand = { [weak self] cmd in self?.handle(cmd) }
        relay.onOpen = { [weak self] in self?.glasses.onState?() }
    }

    func start() {
        heading.start()
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
        case "guide":
            // {on, target_yaw} absolute, or {on, frame_yaw, offset_deg}: the yaw of the frame the target was
            // seen in plus its angle from the frame centre (positive = left of centre).
            let on = (cmd["on"] as? Bool) ?? true
            let num: (String) -> Double? = { k in (cmd[k] as? Double) ?? (cmd[k] as? Int).map(Double.init) }
            if !on { heading.stopGuiding() }
            else if let t = num("target_yaw") { heading.guide(to: t) }
            else if let f = num("frame_yaw") { heading.guide(to: f + (num("offset_deg") ?? 0)) }
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
