import ExpoModulesCore
import Foundation
import UIKit
import MWDATCore

/// JS face of the glasses: the same wiring as ios/Sources/AppModel.swift + SecondVisionApp.swift,
/// but commands come from JS and everything goes back up as events. No product logic here.
public class MetaGlassesModule: Module {
  // Touched only on the main actor (every use is inside a @MainActor function or Task).
  private var controllerStorage: GlassesController?
  private static var configured = false
  private lazy var speaker = Speaker()

  public func definition() -> ModuleDefinition {
    Name("MetaGlasses")

    Events("onState", "onPhoto", "onFrame", "onButton", "onLog")

    /// Wearables.configure() once, then start watching registration and devices.
    AsyncFunction("configure") { (promise: Promise) in
      Task { @MainActor in
        if !MetaGlassesModule.configured {
          do {
            try Wearables.configure()
            MetaGlassesModule.configured = true
          } catch {
            self.emitLog("Wearables.configure failed: \(error)")
            promise.resolve(false)
            return
          }
        }
        // The glasses session lives only while the app is on screen: never let the phone lock.
        UIApplication.shared.isIdleTimerDisabled = true
        _ = self.controller()
        promise.resolve(true)
      }
    }

    AsyncFunction("register") { (promise: Promise) in
      Task { @MainActor in
        await self.controller().register()
        promise.resolve(nil)
      }
    }

    AsyncFunction("requestCameraPermission") { (promise: Promise) in
      Task { @MainActor in
        await self.controller().requestCameraPermission()
        promise.resolve(nil)
      }
    }

    /// Meta AI calls the app back with ?metaWearablesAction=... after registration / permission.
    AsyncFunction("handleUrl") { (urlString: String, promise: Promise) in
      Task { @MainActor in
        guard let url = URL(string: urlString),
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              components.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true else {
          promise.resolve(false)
          return
        }
        do {
          _ = try await Wearables.shared.handleUrl(url)
          self.controller().log("Meta AI callback handled")
          promise.resolve(true)
        } catch {
          self.controller().log("handleUrl: \(error)")
          promise.resolve(false)
        }
      }
    }

    AsyncFunction("connect") { (promise: Promise) in
      Task { @MainActor in
        self.controller().connect()
        promise.resolve(nil)
      }
    }

    AsyncFunction("reconnect") { (promise: Promise) in
      Task { @MainActor in
        self.controller().reconnect()
        promise.resolve(nil)
      }
    }

    AsyncFunction("capture") { (reqId: String?, quality: String, promise: Promise) in
      Task { @MainActor in
        self.controller().capture(reqId: reqId, quality: quality)
        promise.resolve(nil)
      }
    }

    AsyncFunction("setStreaming") { (on: Bool, fps: Double?, promise: Promise) in
      Task { @MainActor in
        self.controller().setStreaming(on, fps: fps)
        promise.resolve(nil)
      }
    }

    AsyncFunction("say") { (text: String, promise: Promise) in
      Task { @MainActor in
        if !text.isEmpty { self.speaker.say(text, interrupt: true) }
        promise.resolve(nil)
      }
    }

    AsyncFunction("playMp3") { (base64: String, promise: Promise) in
      Task { @MainActor in
        if let data = Data(base64Encoded: base64, options: .ignoreUnknownCharacters) {
          self.speaker.play(data, interrupt: true)
        } else {
          self.emitLog("playMp3: bad base64")
        }
        promise.resolve(nil)
      }
    }

    AsyncFunction("stopSpeaking") { (promise: Promise) in
      Task { @MainActor in
        self.speaker.stop()
        promise.resolve(nil)
      }
    }

    AsyncFunction("beep") { (promise: Promise) in
      Task { @MainActor in
        self.speaker.beep()
        promise.resolve(nil)
      }
    }

    /// Current state, same shape as onState.
    AsyncFunction("getState") { (promise: Promise) in
      Task { @MainActor in
        promise.resolve(self.statePayload(self.controller()).compactMapValues { $0 })
      }
    }
  }

  // MARK: - Wiring (AppModel.swift)

  @MainActor
  private func controller() -> GlassesController {
    if let c = controllerStorage { return c }
    let c = GlassesController()
    controllerStorage = c
    speaker.log = { [weak c] s in Task { @MainActor in c?.log(s) } }
    c.onLog = { [weak self] line in
      self?.sendEvent("onLog", ["line": line])
    }
    c.onPhoto = { [weak self, weak c] jpeg, source, reqId in
      guard let self else { return }
      // The standalone shutter returns HEIC; the contract (and the backend) want JPEG.
      var jpeg = jpeg
      if !(jpeg.count > 2 && jpeg[jpeg.startIndex] == 0xFF && jpeg[jpeg.startIndex + 1] == 0xD8),
         let converted = UIImage(data: jpeg)?.jpegData(compressionQuality: 0.85) {
        c?.log("photo converted HEIC → JPEG, \(converted.count / 1024) KB")
        jpeg = converted
      }
      let image = UIImage(data: jpeg)
      let w = Int((image?.size.width ?? 0) * (image?.scale ?? 1))
      let h = Int((image?.size.height ?? 0) * (image?.scale ?? 1))
      self.sendEvent("onPhoto", [
        "jpeg_b64": jpeg.base64EncodedString(),
        "w": w,
        "h": h,
        "source": source,
        "req_id": reqId,
      ])
    }
    c.onFrame = { [weak self] jpeg, w, h, seq in
      self?.sendEvent("onFrame", ["jpeg_b64": jpeg.base64EncodedString(), "w": w, "h": h, "seq": seq])
    }
    c.onButton = { [weak self] press in
      self?.sendEvent("onButton", ["press": press])
    }
    c.onState = { [weak self, weak c] in
      guard let self, let c else { return }
      self.sendEvent("onState", self.statePayload(c))
    }
    c.observeRegistration()
    return c
  }

  @MainActor
  private func statePayload(_ c: GlassesController) -> [String: Any?] {
    let glasses: String = {
      if c.streamState == "streaming" { return "streaming" }
      if c.sessionState == "started" { return "connected" }
      return "disconnected"
    }()
    return [
      "glasses": glasses,
      "session": c.sessionState,
      "stream": c.streamState,
      "photo": c.photoState,
      "mode": c.mode.rawValue,
      "registration": c.registration,
      "device": c.deviceInfo,
      "buttonReady": c.buttonReady,
      "battery": c.battery,
    ]
  }

  private func emitLog(_ line: String) {
    sendEvent("onLog", ["line": line])
  }
}
