import Foundation
import UIKit
import MWDATCore
import MWDATCamera
import MWDATInputs

/// Owns the glasses session: camera (stream + standalone photo) and the capture button.
///
/// Two camera modes, because stream and standalone photo cannot share the sensor:
///   .photo   standalone shutter armed, stream stopped. Default. `capture` → Photo.capturePhoto.
///   .stream  video frames flowing (sampled and forwarded), standalone shutter stopped.
///            `capture` → Stream.capturePhoto (still taken from the live stream, no mode switch).
///
/// Start-up sequence (proven on Ray-Ban Meta gen 1, SDK 1.0.1):
///   session.start → .started → addCamera → stream.start (wakes the sensor)
///   → stream .streaming → photo.start + addInputs
///   → photo .started → stream.stop  (unless the backend already asked for streaming)
@MainActor
final class GlassesController: ObservableObject {
    enum CameraMode: String { case photo, stream }

    @Published var registration = "unknown"
    @Published var sessionState = "idle"
    @Published var streamState = "stopped"
    @Published var photoState = "stopped"
    @Published var mode: CameraMode = .photo
    @Published var buttonReady = false
    @Published var framesSeen = 0
    @Published var framesSent = 0
    @Published var lines: [String] = []
    @Published var deviceInfo = "no glasses seen yet"
    @Published var battery: Int?

    /// Sampled stream frames per second forwarded to the backend (backend can change it).
    var sendFps: Double = 1.0

    /// Callbacks into the app (all on the main actor).
    var onPhoto: (@MainActor (_ jpeg: Data, _ source: String, _ reqId: String?) -> Void)?
    var onFrame: (@MainActor (_ jpeg: Data, _ w: Int, _ h: Int, _ seq: Int) -> Void)?
    var onButton: (@MainActor (_ press: String) -> Void)?
    var onState: (@MainActor () -> Void)?

    private var session: DeviceSession?
    private var camera: Camera?
    private var inputs: Inputs?
    private let tokens = ListenerTokenBag()
    private var tasks: [Task<Void, Never>] = []
    private var sessionTokens = ListenerTokenBag()
    private var sessionTasks: [Task<Void, Never>] = []
    private var watchedDevices: Set<UUID> = []
    private var readyDevice: DeviceIdentifier?

    /// What the backend wants right now; the state handlers steer the hardware towards it.
    private var desiredMode: CameraMode = .photo
    private var photoStartRequested = false
    private var wakeStreamReleased = false
    private var pendingReqId: String?
    private var captureStarted: Date?
    private var photoInFlight = false
    private var lastDoublePress: Date?
    private var pendingShort: Task<Void, Never>?

    // Frame sampling runs off the main actor (see handleFrame).
    private let frameQueue = DispatchQueue(label: "secondvision.frames")

    func log(_ s: String) {
        let stamp = Self.clock.string(from: Date())
        lines.append("\(stamp) \(s)")
        if lines.count > 300 { lines.removeFirst(lines.count - 300) }
        print("[SecondVision] \(s)")
    }

    private static let clock: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    // MARK: - Registration, devices, permissions

    private var isForeground: Bool { UIApplication.shared.applicationState != .background }

    func observeRegistration() {
        tasks.append(Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: UIApplication.didBecomeActiveNotification) {
                await MainActor.run {
                    guard let self, self.session == nil, self.readyDevice != nil else { return }
                    self.log("app opened, glasses are here, starting session")
                    self.connect()
                }
            }
        })
        tasks.append(Task { [weak self] in
            for await state in Wearables.shared.registrationStateStream() {
                await MainActor.run { self?.registration = String(describing: state) }
            }
        })
        tasks.append(Task { [weak self] in
            for await ids in Wearables.shared.devicesStream() {
                await MainActor.run {
                    guard let self else { return }
                    self.log("devices: \(ids.count)")
                    for id in ids { self.watch(id) }
                }
            }
        })
    }

    private func describe(_ d: Device, _ state: DeviceState) -> String {
        "\(d.nameOrId()) \(d.deviceType()) link=\(state.linkState) compat=\(state.compatibility) "
            + "worn=\(state.donState) battery=\(state.batteryLevel.map(String.init) ?? "?")"
    }

    private func watch(_ id: DeviceIdentifier) {
        guard let device = Wearables.shared.deviceForIdentifier(id) else {
            log("device \(id): no Device object")
            return
        }
        guard !watchedDevices.contains(device.deviceUUID) else { return }
        watchedDevices.insert(device.deviceUUID)
        device.addDeviceStateListener { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                self.deviceInfo = self.describe(device, state)
                self.battery = state.batteryLevel
                self.log("device: \(self.deviceInfo)")
                self.onState?()
                if state.linkState == .connected, state.compatibility == .compatible {
                    self.readyDevice = device.identifier
                    if self.session == nil {
                        if self.isForeground {
                            self.log("glasses connected and compatible, starting session")
                            self.connect()
                        } else {
                            self.log("glasses connected while in background, waiting for the app to open")
                        }
                    }
                } else if state.linkState == .disconnected {
                    self.readyDevice = nil
                }
            }
        }.store(in: tokens)
    }

    func register() async {
        do {
            try await Wearables.shared.startRegistration()
            log("registration started (Meta AI opens)")
        } catch {
            log("registration: \(error)")
        }
    }

    func requestCameraPermission() async {
        do {
            let status = try await Wearables.shared.requestPermission(.camera)
            log("camera permission: \(String(describing: status))")
        } catch {
            log("camera permission: \(error)")
        }
    }

    // MARK: - Session

    func connect() {
        guard session == nil else { return }
        guard isForeground else {
            log("app in background, session starts when it is opened")
            return
        }
        let wearables = Wearables.shared
        // AutoDeviceSelector used right after creation has nothing selected (noEligibleDevice).
        guard let id = readyDevice ?? wearables.devices.first else {
            log("no glasses in the device list yet, will start when they appear")
            return
        }
        do {
            let s = try wearables.createSession(deviceSelector: SpecificDeviceSelector(device: id))
            session = s
            sessionTasks.append(Task { [weak self] in
                for await state in s.stateStream() {
                    await MainActor.run {
                        guard let self else { return }
                        self.sessionState = String(describing: state)
                        self.log("session: \(state)")
                        self.onState?()
                        switch state {
                        case .started: self.attachCamera(s)
                        case .stopped: self.teardown()
                        default: break
                        }
                    }
                }
            })
            sessionTasks.append(Task { [weak self] in
                for await error in s.errorStream() {
                    await MainActor.run { self?.log("session error: \(error.description)") }
                }
            })
            try s.start()
            log("session start requested")
        } catch {
            log("session: \(error)")
            session = nil
        }
    }

    func reconnect() {
        teardown()
        connect()
    }

    private func teardown() {
        camera?.stop()
        session?.stop()
        sessionTokens.clear()
        sessionTokens = ListenerTokenBag()
        for task in sessionTasks { task.cancel() }
        sessionTasks.removeAll()
        camera = nil
        inputs = nil
        session = nil
        buttonReady = false
        photoStartRequested = false
        wakeStreamReleased = false
        mode = .photo
        streamState = "stopped"
        photoState = "stopped"
        onState?()
    }

    // MARK: - Camera

    private func attachCamera(_ s: DeviceSession) {
        guard camera == nil else { return }
        Task { [weak self] in
            let status = try? await Wearables.shared.checkPermissionStatus(.camera)
            await MainActor.run { self?.log("camera permission status: \(status.map { String(describing: $0) } ?? "unreadable")") }
        }
        // raw = decoded pixel buffers (app stays in the foreground anyway); medium = 504x896.
        let config = StreamConfiguration(videoCodec: .raw, resolution: .medium, frameRate: 7)
        guard let cam = try? s.addCamera(config: config) else {
            log("camera would not attach (camera permission granted in Meta AI?)")
            return
        }
        camera = cam

        // Standalone photo (Bluetooth path, works without Wi-Fi).
        let photo = cam.photo
        photo.statePublisher.listen { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                self.photoState = String(describing: state)
                self.log("photo: \(state)")
                self.onState?()
                switch state {
                case .started:
                    // Shutter owns the sensor now: put the wake-up stream down, unless streaming was asked for.
                    if self.desiredMode == .photo { self.releaseWakeStream() }
                case .stopped:
                    self.photoStartRequested = false
                    if self.desiredMode == .stream, let camera = self.camera, camera.stream.state == .stopped {
                        self.log("shutter down, starting stream")
                        camera.stream.start()
                    }
                default: break
                }
            }
        }.store(in: sessionTokens)

        photo.photoDataPublisher.listen { [weak self] data in
            Task { @MainActor in
                guard let self else { return }
                self.photoInFlight = false
                let took = self.captureStarted.map { String(format: " in %.1f s", Date().timeIntervalSince($0)) } ?? ""
                self.log("photo arrived: \(data.imageData.count / 1024) KB\(took)")
                let req = self.pendingReqId
                self.pendingReqId = nil
                self.onPhoto?(data.imageData, "capture", req)
            }
        }.store(in: sessionTokens)

        photo.transferProgressPublisher.listen { [weak self] progress in
            Task { @MainActor in
                guard let self else { return }
                let pct = Int(progress.fraction * 100)
                if pct == 0 || pct == 50 { self.log("photo transfer: \(progress.bytesReceived / 1024)/\(progress.totalBytes / 1024) KB") }
            }
        }.store(in: sessionTokens)

        photo.errorPublisher.listen { [weak self] error in
            Task { @MainActor in
                self?.photoInFlight = false
                self?.pendingReqId = nil
                self?.log("photo error: \(error)")
            }
        }.store(in: sessionTokens)

        cam.statePublisher.listen { [weak self] state in
            Task { @MainActor in self?.log("camera: \(state)") }
        }.store(in: sessionTokens)

        // Stream (Wi-Fi path; also used once at start to wake the sensor).
        let stream = cam.stream
        stream.statePublisher.listen { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                self.streamState = String(describing: state)
                self.log("stream: \(state)")
                self.onState?()
                switch state {
                case .streaming:
                    self.attachInputs(s)
                    if self.desiredMode == .photo {
                        self.mode = .photo
                        self.startPhotoIfNeeded()      // then photo .started → releaseWakeStream
                    } else {
                        self.mode = .stream
                    }
                case .stopped:
                    if self.desiredMode == .photo, self.wakeStreamReleased {
                        self.mode = .photo
                        self.startPhotoIfNeeded()      // coming back from stream mode
                    }
                default: break
                }
            }
        }.store(in: sessionTokens)

        stream.errorPublisher.listen { [weak self] error in
            Task { @MainActor in self?.log("stream error: \(error)") }
        }.store(in: sessionTokens)

        stream.photoDataPublisher.listen { [weak self] photo in
            Task { @MainActor in
                guard let self else { return }
                self.photoInFlight = false
                let took = self.captureStarted.map { String(format: " in %.1f s", Date().timeIntervalSince($0)) } ?? ""
                self.log("stream still arrived: \(photo.data.count / 1024) KB\(took)")
                let req = self.pendingReqId
                self.pendingReqId = nil
                self.onPhoto?(photo.data, "stream", req)
            }
        }.store(in: sessionTokens)

        stream.videoFramePublisher.listen { [weak self] frame in
            self?.handleFrame(frame)
        }.store(in: sessionTokens)

        stream.start()
    }

    /// Called on the SDK's thread for every frame; sample, encode, hand the JPEG to the main actor.
    nonisolated private func handleFrame(_ frame: VideoFrame) {
        frameQueue.async { [weak self] in
            guard let self else { return }
            Task { @MainActor in self.framesSeen += 1 }
            let now = Date()
            let interval = 1.0 / max(0.2, self.sendFpsSnapshot())
            guard now.timeIntervalSince(self.lastFrameSentUnsafe) >= interval else { return }
            self.lastFrameSentUnsafe = now
            guard let image = frame.makeUIImage(), let jpeg = image.jpegData(compressionQuality: 0.6) else { return }
            let w = Int(image.size.width * image.scale), h = Int(image.size.height * image.scale)
            self.frameSeqUnsafe += 1
            let seq = self.frameSeqUnsafe
            Task { @MainActor in
                self.framesSent += 1
                self.onFrame?(jpeg, w, h, seq)
            }
        }
    }

    // Accessed only on frameQueue.
    nonisolated(unsafe) private var lastFrameSentUnsafe = Date.distantPast
    nonisolated(unsafe) private var frameSeqUnsafe = 0
    nonisolated(unsafe) private var sendFpsUnsafe: Double = 1.0
    nonisolated private func sendFpsSnapshot() -> Double { sendFpsUnsafe }

    private func startPhotoIfNeeded() {
        guard !photoStartRequested, let camera else { return }
        photoStartRequested = true
        camera.photo.start()
    }

    /// Frames and stills compete for the sensor; the wake-up stream must go before stills work.
    private func releaseWakeStream() {
        guard !wakeStreamReleased, let camera else { return }
        wakeStreamReleased = true
        camera.stream.stop()
        log("wake-up stream put down, shutter owns the sensor")
    }

    // MARK: - Commands from the backend

    /// `stream on/off`. Switching modes takes one to three seconds on the glasses.
    func setStreaming(_ on: Bool, fps: Double?) {
        if let fps { sendFps = fps; frameQueue.async { self.sendFpsUnsafe = fps } }
        guard let camera else {
            log("stream \(on ? "on" : "off") asked, but no camera yet")
            desiredMode = on ? .stream : .photo
            return
        }
        if on {
            desiredMode = .stream
            wakeStreamReleased = true          // whatever happens next, the stream is wanted for real
            if camera.stream.state == .streaming { mode = .stream; return }
            if camera.photo.state == .started || camera.photo.state == .starting {
                log("stream on: stopping the standalone shutter first")
                camera.photo.stop()            // photo .stopped → stream.start()
            } else if camera.stream.state == .stopped {
                camera.stream.start()
            }
        } else {
            desiredMode = .photo
            if camera.stream.state == .streaming || camera.stream.state == .starting {
                log("stream off: stopping stream, re-arming the shutter")
                camera.stream.stop()           // stream .stopped → photo.start()
            } else {
                startPhotoIfNeeded()
            }
        }
    }

    /// `capture`. In stream mode the still comes from the live stream, otherwise from the standalone shutter.
    func capture(reqId: String?, quality: String) {
        guard let camera else {
            log("capture asked, but no camera")
            return
        }
        if photoInFlight, let started = captureStarted, Date().timeIntervalSince(started) < 30 {
            log("capture asked while the previous photo is still on its way, ignored")
            return
        }
        pendingReqId = reqId
        captureStarted = Date()
        photoInFlight = true
        if camera.stream.state == .streaming {
            let ok = camera.stream.capturePhoto(format: .jpeg)
            log("capture from stream (\(quality)): \(ok ? "requested" : "refused")")
            if !ok { photoInFlight = false; pendingReqId = nil }
            return
        }
        guard camera.photo.state == .started else {
            log("capture asked, but the shutter is not ready (photo=\(photoState), stream=\(streamState))")
            photoInFlight = false
            pendingReqId = nil
            return
        }
        let (res, q): (PhotoResolution, PhotoQuality) = {
            switch quality {
            case "full": return (.full, .high)
            case "large": return (.large, .medium)
            case "small": return (.small, .medium)
            default: return (.medium, .medium)
            }
        }()
        log("capture standalone \(res.rawValue)/\(q.rawValue)")
        camera.photo.capturePhoto(resolution: res, quality: q)
    }

    // MARK: - Capture button on the glasses

    private func attachInputs(_ s: DeviceSession) {
        guard inputs == nil else { return }
        let configuration = InputsConfiguration(sources: [.captureButton])
        do {
            guard let attached = try s.addInputs(configuration: configuration) else {
                log("this pair reports no inputs")
                return
            }
            inputs = attached
            buttonReady = true
            sessionTasks.append(Task { [weak self] in
                for await event in attached.events {
                    await MainActor.run { self?.handle(event) }
                }
                await MainActor.run {
                    self?.buttonReady = false
                    self?.log("inputs stream ended")
                }
            })
            log("capture button attached")
        } catch {
            log("inputs: \(error)")
        }
    }

    private func handle(_ event: InputEvent) {
        switch event {
        case let .capture(pressType, source, _):
            guard source == .captureButton else { return }
            switch pressType {
            case .shortPress:
                // The glasses report a double press as short, short, double: debounce the short.
                if let last = lastDoublePress, Date().timeIntervalSince(last) < 0.7 { return }
                pendingShort?.cancel()
                pendingShort = Task { @MainActor [weak self] in
                    try? await Task.sleep(nanoseconds: 600_000_000)
                    guard !Task.isCancelled, let self else { return }
                    self.pendingShort = nil
                    self.log("button: short")
                    self.onButton?("short")
                }
            case .doublePress:
                lastDoublePress = Date()
                pendingShort?.cancel()
                pendingShort = nil
                log("button: double")
                onButton?("double")
            default:
                log("button: \(pressType)")
                onButton?("hold")
            }
        default:
            break
        }
    }
}
