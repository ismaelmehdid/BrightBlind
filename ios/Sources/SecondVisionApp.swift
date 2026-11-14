import SwiftUI
import UIKit
import MWDATCore

@main
struct SecondVisionApp: App {
    @StateObject private var model = AppModel()

    init() {
        do {
            try Wearables.configure()
        } catch {
            assertionFailure("Wearables.configure failed: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .onOpenURL { url in
                    // Meta AI calls back with ?metaWearablesAction=... after registration and permissions.
                    guard
                        let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
                        components.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true
                    else { return }
                    Task { @MainActor in
                        do {
                            _ = try await Wearables.shared.handleUrl(url)
                            model.glasses.log("Meta AI callback handled")
                        } catch {
                            model.glasses.log("handleUrl: \(error)")
                        }
                    }
                }
                .onAppear {
                    // The glasses session lives only while the app is on screen: never let the phone lock.
                    UIApplication.shared.isIdleTimerDisabled = true
                    model.start()
                }
        }
    }
}
