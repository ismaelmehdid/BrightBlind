# SecondVision backend

Andrii owns the glasses relay. Ismaël owns the band and Recall. Tarang owns this folder.

This backend follows the root README's v0 contract: one JSON WebSocket endpoint, **/ws**, with a band client and a glasses client. No new device message types or fields are required. The existing iOS Relay.swift can connect by changing its URL. The code outside backend/ is unchanged.

## Run locally

Requires Python 3.12 and ffmpeg.

~~~sh
cd backend
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env
# Set provider keys in .env, then:
.venv/bin/python server.py
~~~

Dashboard: http://127.0.0.1:8765. Relay: ws://127.0.0.1:8765/ws.

The local default is loopback-only. Phones and other laptops cannot reach that address directly. Use the HTTPS deployment below, or an authenticated private-network setup. Non-loopback binding refuses to start unless relay and dashboard tokens are configured.

## What actually runs

~~~text
Vexo relay: PCM or Opus, events, activity
  → /ws → decode/rechunk to 80 ms PCM
  → Pipecat → Deepgram Flux
  → final transcript → planner
       ├─ Gemini: interpret a request / analyze a selected image
       ├─ Google Maps: bus line, departure stop and departure estimate
       └─ Recall: query personal memory over its separate /ws
  → Pipecat → Deepgram Flux TTS → MP3
  → /ws say → iPhone → glasses audio route
~~~

Explicit label-reading and fully specified route commands skip the planner model round trip. Other phrasing uses Gemini. The dashboard distinguishes local routing from model decisions.

The planner, visual task, transit task and Recall query are separate asynchronous operations. Camera/Maps work does not block incoming audio. A new visual task invalidates older visual results. Stop cancels scheduled camera actions; unrelated conversation does not cancel a scheduled bus watch.

## Device contract

First message:

~~~json
{"type":"hello","ts":1794690000000,"client":"band","caps":["audio","events","activity"]}
~~~

Use the actual current timestamp, in milliseconds. Glasses use client=glasses and their existing capabilities.

Band audio accepts either:

- pcm_b64: signed little-endian PCM, 16 kHz mono. **Preferred:** decode with the kit's PcmDecoder on the relay.
- opus_b64: a raw Opus packet. The backend decodes it with PyAV.

The relay supplies an increasing seq. Duplicate/out-of-order audio packets are ignored; the counter resets on reconnect. Four 20 ms PCM packets become one 80 ms Flux chunk. The microphone is muted with silence while generated speech is expected to play, to limit feedback. Double-tap still interrupts. This is an echo guard, not validated acoustic echo cancellation or proven full-duplex speech.

Photos must echo capture.req_id. Unsolicited or stale photos are discarded. Streaming frames need fresh ts values; the backend requests 1 fps, analyzes no more than one frame every two seconds, and never runs two vision calls simultaneously. Ordinary camera sessions end after 30 seconds; bus-watch sessions after 90 seconds. A backlog is dropped rather than described as current.

The backend emits only capture, stream, say, stop_speaking and led, with ts. Say audio is MP3 as required by the contract. The typed-question endpoint is HTTP, not an undocumented device message.

## Scenes and limits

- **Fridge:** capture one image and report visible items. It does not conclude that something is absent from the whole fridge based on one view. Query Recall for known stock; automatic stock comparison is not implemented yet.
- **Bus:** Google Maps supplies the route, departure stop, line and departure timestamp. The backend schedules a camera session at that estimate minus 60 seconds. That is a departure estimate, not a verified live bus-arrival feed. Visible bus-number matches are reported; they do not authorize boarding or crossing.
- **Shelf:** stream sampled frames to identify product labels and image-relative location. The backend does not give hand-positioning commands.
- **Surroundings:** identify visible stairs/curbs/obstructions and announce uncertainty. It never instructs a blind user to take a step down from a monocular image.
- **Memory/research:** query Ismaël's Recall server with cmd=ask. No personal stock, preferences or facts are invented when Recall is unavailable. An open-web research agent is not implemented.

Final band speech is considered a request while the session is active. Set REQUIRE_WAKE_WORD=1 to require “Second Vision” or the 20-second window after a double tap.

## Keys

Required for the full loop:

| Variable | Actual use |
|---|---|
| DEEPGRAM_API_KEY | Flux STT and Flux TTS inside Pipecat, mip_opt_out enabled |
| ELEVENLABS_API_KEY | Optional alternative: set VOICE_TTS_PROVIDER=elevenlabs for its sponsor track |
| GEMINI_API_KEY | Gemini planner and visual observations |
| GOOGLE_MAPS_API_KEY | Routes API transit planning |
| RECALL_WS_URL / RECALL_TOKEN | Optional connection to the separate Recall service |

The Google Maps project must have Routes API enabled and a billing/credit arrangement that permits it. A Gemini key alone does not prove Maps access.

LIVE_ONLY=1 is the default. Requests are blocked when the band relay, glasses relay, Meta camera connection or essential provider keys are missing. Server speech does not silently fall back to system voice. Isolated engineering tests set LIVE_ONLY=0; they do not constitute a hardware demo. Relay state is not hardware attestation: the actual devices still need an observed end-to-end check.

## Deploy as a team server

Use a Linux host with Docker Compose, a DNS hostname pointed at it, and inbound TCP ports 80 and 443. From backend/:

~~~sh
python3 configure.py --domain secondvision.your-domain.com --email your-email@example.com
docker compose config --quiet
docker compose up --build -d
docker compose logs --tail=40 backend
~~~

The setup script prompts privately for the Deepgram, Gemini and Maps keys and generates independent relay tokens plus dashboard tokens for Andrii, Ismaël and Tarang. It writes .env and access.txt with owner-only permissions. It refuses to overwrite existing configuration. If a local development .env already exists, preserve it under a private name before running setup.

Caddy terminates HTTPS and proxies WebSockets. Only ports 80/443 are published; the backend port remains inside Docker. The data volume retains the last 300 backend events. Raw audio is not stored; the most recent selected frame is held in memory. Recall owns long-term memory.

Each teammate gets their own dashboard token. The relays use their role-specific wss://.../ws?token=... URL (supported by the existing iOS URL field), or a Bearer header if the relay supports it. Access logs are disabled so these URLs are not routinely logged. Keep these links private.

This is one shared wearer session, not a multi-tenant product. A second connection with the same role replaces the first. Dashboard tokens share the same workspace and permissions; there is no account management or role-specific authorization UI.

## Verification

~~~sh
.venv/bin/python -m unittest test_contract -v
~~~

The tests run the real Pipecat pipeline with clearly labeled provider fixtures and simulated relays. They cover typed question → say, req_id correlation, stale/unmatched photo rejection, camera stop, band gestures, reconnect, role-token isolation, and foreign browser origins.

Verified on November 14:

- Six contract integration tests pass, including PCM-to-MP3 output through Pipecat.
- Docker image builds and boots with a read-only filesystem and a non-root app user.
- Container health, dashboard token protection, both relay handshakes and double-tap capture pass.
- A real Pipecat + Gemini planner/vision request read a synthetic chocolate label correctly through a simulated glasses client. The first complete test took 19.5 seconds. After adding explicit-command routing, the same request triggered capture in 34 ms and returned the correct price in 3.1 seconds. Both used text say fallback; see verification.json. These small tests do not measure real wearable/audio latency.
- The issued Deepgram key was tested with synthetic speech streamed through a simulated band in 20 ms PCM packets. Real Deepgram Flux inside Pipecat transcribed the phrase exactly, triggered capture, and real Gemini returned the correct product price. Speech end to capture request was about 2.0 seconds in this single test. Output used text say fallback.

Real Deepgram Flux TTS has also passed a speech-in/speech-out test through Pipecat. The resulting MP3 was transcribed back and contained the correct product name and price. ElevenLabs is optional and has not been tested. Google Maps calls, the actual band, and physical glasses capture/playback remain unverified. No public deployment has been performed. Provider usage events are recorded, but credit-balance deductions have not been verified in either provider console.

Tarang chose Deepgram speech output to avoid requiring a fourth provider key. This overrides the earlier root README voice-stack choice without changing any relay message.
