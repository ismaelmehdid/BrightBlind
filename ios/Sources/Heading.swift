import CoreMotion
import Foundation

/// Body heading from the phone's gyro, and real-time turn guidance spoken on the phone.
///
/// Why: a vision model answers in 2–3 s, too slow to steer a person who is turning. So the model
/// only has to find the target once ("the door was in the frame taken at yaw 140°, 10° to the right");
/// from then on the phone compares the live yaw with that bearing 10 times a second and talks with
/// no network round trip. The phone must stay fixed on the body (pocket), any orientation.
///
/// yaw: degrees, relative to where the app started, positive = turning LEFT (counter-clockwise from above).
@MainActor
final class Heading: ObservableObject {
    @Published private(set) var yaw: Double = 0
    @Published private(set) var guiding = false
    @Published private(set) var targetYaw: Double = 0
    @Published private(set) var lastCue = ""

    var speak: ((String) -> Void)?
    var log: ((String) -> Void)?
    /// Reports zone changes to the backend: "left", "right", "ahead".
    var onZone: ((String, Double) -> Void)?

    private let motion = CMMotionManager()
    private var lastStamp: TimeInterval?
    private var zone = ""
    private var lastSpoken = Date.distantPast
    private let aheadWindow = 12.0      // degrees either side that count as "facing it"

    func start() {
        guard motion.isDeviceMotionAvailable, !motion.isDeviceMotionActive else { return }
        motion.deviceMotionUpdateInterval = 1.0 / 30.0
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
            guard let data else { return }
            Task { @MainActor in self?.integrate(data) }
        }
    }

    private func integrate(_ d: CMDeviceMotion) {
        defer { lastStamp = d.timestamp }
        guard let last = lastStamp else { return }
        let dt = d.timestamp - last
        guard dt > 0, dt < 0.5 else { return }
        // Rotation rate about the "up" axis = rate · (−gravity). Works however the phone sits in the pocket.
        let g = d.gravity, r = d.rotationRate
        let rateUp = -(r.x * g.x + r.y * g.y + r.z * g.z)
        yaw += rateUp * dt * 180 / .pi
        if guiding { tick() }
    }

    /// Signed angle from where the wearer faces to the target: positive = target is to the LEFT.
    var offset: Double {
        var d = (targetYaw - yaw).truncatingRemainder(dividingBy: 360)
        if d > 180 { d -= 360 }
        if d <= -180 { d += 360 }
        return d
    }

    func guide(to target: Double) {
        targetYaw = target
        guiding = true
        zone = ""
        lastSpoken = .distantPast
        log?(String(format: "guide on: target yaw %.0f°, now %.0f°, offset %.0f°", target, yaw, offset))
        tick()
    }

    func stopGuiding() {
        guard guiding else { return }
        guiding = false
        zone = ""
        log?("guide off")
    }

    private func tick() {
        let off = offset
        let now: String = abs(off) <= aheadWindow ? "ahead" : (off > 0 ? "left" : "right")
        let since = Date().timeIntervalSince(lastSpoken)
        if now != zone {
            zone = now
            say(now, off)
            onZone?(now, off)
        } else if now != "ahead", since > 2.2 {
            say(now, off)                       // still turning: keep the wearer oriented
        } else if now == "ahead", since > 4 {
            say(now, off)
        }
    }

    private func say(_ zone: String, _ off: Double) {
        lastSpoken = Date()
        let cue: String
        switch zone {
        case "ahead": cue = "Stop. Straight ahead."
        case "left": cue = abs(off) > 100 ? "Turn around, to your left." : (abs(off) > 35 ? "Turn left." : "A little left.")
        default: cue = abs(off) > 100 ? "Turn around, to your right." : (abs(off) > 35 ? "Turn right." : "A little right.")
        }
        lastCue = cue
        speak?(cue)
    }
}
