import AVFoundation
import AudioToolbox

/// Plays into whatever audio output is current. With the glasses paired as the Bluetooth
/// headset that is the glasses' speakers. Two sources: backend-supplied audio (mp3/wav
/// bytes, e.g. ElevenLabs) and on-device TTS as the fallback.
final class Speaker: NSObject, AVAudioPlayerDelegate {
    private var synthesizer = AVSpeechSynthesizer()
    private var player: AVAudioPlayer?
    var log: ((String) -> Void)?
    var rate: Float = 0.47

    private func activate() {
        let session = AVAudioSession.sharedInstance()
        // .playback ignores the silent switch; allowBluetoothA2DP keeps the glasses as output.
        try? session.setCategory(.playback, mode: .spokenAudio, options: [.allowBluetoothA2DP])
        try? session.setActive(true)
    }

    var route: String {
        AVAudioSession.sharedInstance().currentRoute.outputs
            .map { "\($0.portType.rawValue) \($0.portName)" }
            .joined(separator: ", ")
    }

    func beep() {
        activate()
        AudioServicesPlaySystemSound(1057)
    }

    func stop() {
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        player?.stop()
        player = nil
    }

    /// Backend audio bytes (mp3, wav, m4a). Interrupts whatever is playing when asked.
    func play(_ data: Data, interrupt: Bool) {
        activate()
        if interrupt { stop() } else if synthesizer.isSpeaking || (player?.isPlaying ?? false) { stop() }
        do {
            let p = try AVAudioPlayer(data: data)
            p.delegate = self
            player = p
            p.play()
            log?("play \(data.count / 1024) KB via \(route)")
        } catch {
            log?("play failed: \(error.localizedDescription)")
        }
    }

    /// On-device voice, used when the backend sends text only.
    func say(_ text: String, language: String = "en-US", interrupt: Bool) {
        activate()
        if interrupt || synthesizer.isSpeaking || synthesizer.isPaused {
            synthesizer.stopSpeaking(at: .immediate)
            synthesizer = AVSpeechSynthesizer()
        }
        player?.stop()
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: language)
        utterance.rate = rate
        log?("say \"\(text.prefix(60))\" via \(route)")
        synthesizer.speak(utterance)
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        log?("audio finished")
    }
}
