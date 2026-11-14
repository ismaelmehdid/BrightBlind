# Team handoff — November 14

Andrii / Ismaël / Tarang

Local branch: codex/secondvision-backend. All changes are in backend/. The device JSON contract is unchanged. Nothing has been posted to the team board or pushed.

**Andrii:** your existing Relay and AppModel command handling match this server. Set the backend URL to the deployed glasses URL in access.txt. Capture replies must preserve req_id; frames need current ts. The backend sends full MP3 files in say.audio_b64. Deepgram Flux TTS is now the default, using the same key as STT. ElevenLabs remains optional. In LIVE_ONLY mode, missing server TTS blocks output instead of silently sending system-voice fallback.

**Ismaël:** connect the band relay to the band URL. PCM 16 kHz mono s16le is preferred; raw Opus is accepted and decoded server-side. Keep seq increasing per connection. Audio packets remain JSON/base64. Double-tap produces capture and opens the optional wake-word window. Only one program should own the band. Recall is queried separately via its configured WebSocket address; the backend does not modify Recall.

**Tarang:** run configure.py on the deployment host with the sponsor keys, then docker compose up --build -d. The typed endpoint is POST /api/question with {"text":"..."}. Dashboard and HTTP API use a dashboard bearer token. Review provider readiness on the dashboard before rehearsing.

The first demo gate is a typed request through Pipecat that produces speech in the actual glasses. The second is live Vexo audio through Deepgram. Only then test vision and Maps outdoors. A number match is not a boarding instruction; scene descriptions are not safe step-by-step navigation.

Deepgram is now configured privately on Tarang's local backend and verified with synthetic audio through the real Pipecat pipeline. The transcript triggered capture and Gemini label reading successfully. The handoff archive deliberately contains no keys; the deployment host needs its own private configuration.

Live-only mode is now the default. The voice provider starts when a relay/request needs it, so an idle server does not open provider sessions before use. Google usage metadata and Pipecat speech usage are logged as evidence of real API work; console credit deductions remain unverified.

For real glasses testing, typed dashboard requests no longer require a connected band. LIVE_ONLY=1 still requires the actual camera connection and provider keys, and disables silent system-voice fallback. Complete hands-free operation still needs the band. Gemini thinking is LOW; the backend refreshes Google Maps when asked about the next bus.
