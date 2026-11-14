import SwiftUI

struct ContentView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        Inner(glasses: model.glasses, relay: model.relay, model: model)
    }

    private struct Inner: View {
        @ObservedObject var glasses: GlassesController
        @ObservedObject var relay: Relay
        @ObservedObject var model: AppModel

        var body: some View {
            NavigationStack {
                List {
                    Section("Backend") {
                        TextField("ws://host:port/ws", text: $relay.url)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                        HStack {
                            Text("link").foregroundStyle(.secondary)
                            Spacer()
                            Text(relay.state)
                            Text("↑\(relay.sent) ↓\(relay.received)").foregroundStyle(.secondary)
                        }
                        HStack {
                            Button("Reconnect") { relay.disconnect(); relay.connect() }
                            Spacer()
                            Button("Test voice") { model.speaker.say("Second Vision is listening.", interrupt: true) }
                        }
                    }
                    Section("Glasses") {
                        row("registration", glasses.registration)
                        row("device", glasses.deviceInfo)
                        row("session", glasses.sessionState)
                        row("mode", glasses.mode.rawValue)
                        row("stream", "\(glasses.streamState)  frames seen \(glasses.framesSeen), sent \(glasses.framesSent)")
                        row("shutter", glasses.photoState)
                        row("button", glasses.buttonReady ? "listening" : "not attached")
                        HStack {
                            Button("1. Register") { Task { await glasses.register() } }
                            Spacer()
                            Button("2. Camera permission") { Task { await glasses.requestCameraPermission() } }
                        }
                        HStack {
                            Button("Reconnect session") { glasses.reconnect() }
                            Spacer()
                            Button("Capture") { glasses.capture(reqId: "ui", quality: "medium") }
                        }
                        HStack {
                            Button("Stream on") { glasses.setStreaming(true, fps: 1) }
                            Spacer()
                            Button("Stream off") { glasses.setStreaming(false, fps: nil) }
                        }
                    }
                    Section("Heading") {
                        HeadingRow(heading: model.heading)
                    }
                    if glasses.streamState == "streaming", let frame = glasses.preview {
                        Section("Live stream  \(Int(frame.size.width))x\(Int(frame.size.height))  frames \(glasses.framesSeen)") {
                            Image(uiImage: frame).resizable().scaledToFit().frame(maxHeight: 420)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    if let photo = model.lastPhoto {
                        Section("Last photo \(model.lastPhotoInfo)") {
                            Image(uiImage: photo).resizable().scaledToFit().frame(maxHeight: 220)
                        }
                    }
                    Section("Log") {
                        ForEach(Array(glasses.lines.suffix(80).reversed().enumerated()), id: \.offset) { _, line in
                            Text(line).font(.system(size: 11, design: .monospaced))
                        }
                    }
                }
                .navigationTitle("SecondVision relay")
            }
        }

        private func row(_ k: String, _ v: String) -> some View {
            HStack(alignment: .top) {
                Text(k).foregroundStyle(.secondary)
                Spacer()
                Text(v).multilineTextAlignment(.trailing).font(.footnote)
            }
        }
    }
}


private struct HeadingRow: View {
    @ObservedObject var heading: Heading
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(String(format: "yaw %.0f°   %@", heading.yaw,
                        heading.guiding ? String(format: "target %.0f°  offset %.0f°  %@", heading.targetYaw, heading.offset, heading.lastCue) : "not guiding"))
                .font(.footnote)
            HStack {
                Button("Guide to here") { heading.guide(to: heading.yaw) }
                Spacer()
                Button("Stop guide") { heading.stopGuiding() }
            }
        }
    }
}
