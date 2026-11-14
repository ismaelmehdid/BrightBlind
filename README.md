# SecondVision

Eyes for people who cannot see, built from two wearables that each do half the job.

VexoHacks, Y Combinator SF, November 14, 2026. Team: Andrii (Meta glasses + iPhone), Ismaël (Vexo band + laptop), Tarang (backend + agents).

## What it is

A blind user wears a Vexo band on the wrist and Ray-Ban Meta glasses on the face.

- The **band** is the ears and the button. It listens all the time, so the user just talks: "what am I missing in the fridge", "find the dark chocolate", "is this my bus". A double tap on the band means "look now". The band also knows when the user is walking, standing still, or has fallen.
- The **glasses** are the eyes and the voice. They have a camera and speakers but no always-on microphone the user can rely on. When the agent needs to see, it tells the glasses to take a photo or to stream video. The answer is spoken into the glasses' speakers.
- The **agent** in the middle decides when to look, what to look for, and what to say. It is not a chat window. The user never touches a phone.

Neither device works alone: the band cannot see and has no speaker, the glasses cannot listen all day and have no gesture input the user can find by touch. Together they make a person who cannot see able to ask the world a question and get a spoken answer.

## Demo scenes (what the judges will see)

1. **Fridge.** User opens the fridge, says "what am I missing". Agent takes a photo through the glasses, lists what is there, compares with the user's usual stock, says what is missing.
2. **Bus stop.** User says "I am going to the store". Agent gets the route and the bus arrival time from Google Maps. One minute before arrival it starts streaming from the glasses, reads bus numbers as they pull in, and says "this is the 38, yours, get on" or "not yours, wait".
3. **Shelf.** In the store the user says "find the dark chocolate". Agent streams, finds it on the shelf, and guides the hand: "higher", "a bit left", "that one".

Every scene has the same shape: the band hears, the agent decides to look, the glasses see, the glasses speak.

## Architecture

```
Vexo band ──BLE──> laptop (Python, vexo-open-kit) ──> Opus audio, taps, motion ──┐
                                                                                 ├──WebSocket──> backend
Ray-Ban Meta ──BLE/Wi-Fi──> iPhone relay app (Swift, Meta DAT SDK) ──> photos, frames ─┘        │
                              ▲                                                                   │
                              └──── capture / stream on|off / say (text or audio) ────────────────┘

backend: Pipecat voice loop (Deepgram STT ─ LLM ─ ElevenLabs TTS) + agents (planner, vision on Gemini,
         transit on Google Maps, researcher) + dashboard for judges
```

**Memory layer (Recall, Ismaël).** Next to the live loop, the band's day is kept as memory:

```
band mic ──> laptop: Pipecat (Deepgram Flux STT) ──> SQLite: every sentence + what the body was doing
                                                       (still / walk / run, steps, taps)
                                                         │
                         Gemini 4 (gemini-4-hydrogen) ───┴──> memories (task, plan, person, fact, ...)
                                                               and answers ("what did Sam want from me?")
```

One tap on the band keeps the last 30 seconds; a double-tap followed by a spoken question gets a spoken answer
(Deepgram TTS on the laptop). A local page (`http://localhost:8100`) shows what was heard, the memories, and the
band timeline. The same server runs on Railway (`recall/cloud.py`) for the phone. The backend's planner can use it
as the user's long-term memory (for example the "usual stock" in the fridge scene) by sending
`{"cmd": "ask", "text": "..."}` on Recall's own `/ws` (a separate server and protocol from the backend's `/ws`
below).

Two hubs, one backend. The band talks only to the laptop. The glasses talk only to the iPhone. The backend talks to both over one WebSocket server and is the only place with logic.

## Who does what

### Ismaël: band → laptop → backend (`band/`)

- Connect the Vexo Open band to the laptop with the kit (`vexo-open-kit`, Python, `bleak`). Band number is on the bag. Double tap before every connect, one program at a time, close the dashboard tab first.
- Turn on `audio`, `events`, `activity`. Forward to the backend over WebSocket:
  - audio: Opus packets as they come (50/s, 16 kHz mono, 20 ms each), or PCM decoded with the kit's `PcmDecoder` if the backend wants PCM. Agree with Tarang on which.
  - `tap`, `double-tap`, `free-fall` events.
  - `activity` state (`still`, `walk`, `run`) once a second.
- Accept `led` commands from the backend (colour feedback is useless for the user but great for the demo: blue = listening, green = looking, red = fall).
- Auto-reconnect when the link drops (the kit has it). Must survive the band going out of range for ten seconds.
- Deliverable by 14:00: `python3 band/relay.py <band number>` streams audio and events to the backend and prints what it sends.
- **Recall, the memory layer** (`app.py`, `recall/`): see "Memory layer" under Architecture. Run it with
  `.venv\Scripts\python.exe app.py --usb --port COM5` (or `--sim` with no band), then open
  `http://localhost:8100`. Keys go in `.env` (copy `.env.example`): `DEEPGRAM_API_KEY`, `GEMINI_API_KEY`.
  The band takes one program at a time, so `app.py` and `band/relay.py` cannot both hold it: until Recall
  forwards to the backend itself, run one or the other.

### Tarang: backend + agents (`backend/`)

- One WebSocket server with two kinds of clients, `band` and `glasses`. Message contract is below. This is the one file everyone depends on, so write it first and keep it stable.
- Voice loop on **Pipecat**: band audio in → Deepgram streaming STT → LLM → ElevenLabs TTS → audio out to the glasses client. Pipecat is a sponsor track, so the voice path must really run through it.
- Agents (Pipecat pipeline or Mastra, your call):
  - **Planner**: reads the transcript, decides whether the request needs eyes, which scene it is, and whether to capture one photo or start a stream.
  - **Vision**: Gemini on the photo or on sampled frames. Returns structured facts (items in fridge, bus numbers in frame, position of the target on the shelf relative to the hand).
  - **Transit**: Google Maps Directions / Transit for the bus scene, arrival time, line number.
  - **Researcher**: web lookup when the answer needs facts not in the frame (what is usually in a fridge for this user, product names).
- Scene logic: fridge (one photo), bus (stream from T-60 s, stop after boarding), shelf (stream, compare target position to hand position, speak a direction every ~2 s, stop on "got it").
- Dashboard for judges: a web page that shows the live transcript, the frames the agent chose to look at, and what each agent decided. This is how we prove "meaningful use of AI agents" in three minutes.
- Deliverable by 14:00: server accepts both clients, echoes a spoken answer to a typed question. By 16:00: all three scenes.

### Andrii: glasses → iPhone → backend (`ios/`)

- Swift app on iPhone using the Meta Wearables Device Access Toolkit (`meta-wearables-dat-ios` 1.0.1). Built in GitHub Actions on `macos-26`, signed and installed from Linux with Impactor/plumesign (no Mac in the team). Scaffold (XcodeGen `project.yml`, `build.yml`, DAT session boilerplate) is copied from Andrii's own public repo `andriidrok1/glasses-tutor`; all product code is written today.
- The app is a dumb relay, no logic:
  - Session with `SpecificDeviceSelector`, camera attached, Inputs attached (capture button on the glasses as a backup trigger).
  - On `capture`: `stream.capturePhoto(.jpeg)` if streaming, else standalone `Photo` capture; send the JPEG to the backend.
  - On `stream on`: HEVC stream (`hvc1`, 504x896, 7 fps), sample 1–2 frames per second, send as JPEG. On `stream off`: stop.
  - On `say`: play the audio (or text via `AVSpeechSynthesizer` as fallback) through the Bluetooth route, which is the glasses' speakers.
  - Keep the screen awake, run under Guided Access, phone stays in the pocket.
- Wi-Fi: DAT streams over a Wi-Fi network hosted by the glasses. Needs `NSLocalNetworkUsageDescription`, `NSBonjourServices` and the Hotspot Configuration entitlement. iOS keeps internet on cellular while joined to that Wi-Fi, so the phone needs mobile data. If the entitlement is not available on the signing account, fall back to photos over Bluetooth (2–5 s per photo at medium quality, proven).
- Deliverable by 13:00: app connects to backend, `capture` returns a photo, `say` is heard in the glasses. By 15:00: streaming.

## WebSocket contract (v0, Tarang owns it)

One server, path `/ws`. Every message is a JSON text frame: `{"type": "...", "ts": <ms since epoch>, ...}`. Binary payloads are base64 inside JSON for now (simple beats fast today). First message from any client is `hello`.

Client → backend:

| type | from | fields |
|---|---|---|
| `hello` | both | `client: "band" \| "glasses"`, `caps: [...]` |
| `audio` | band | `seq`, `opus_b64` (one 20 ms packet) or `pcm_b64` (16 kHz s16le) |
| `event` | band | `kind: "tap" \| "double-tap" \| "free-fall" \| "tilt"` |
| `activity` | band | `state: "still" \| "walk" \| "run"`, `steps`, `cadence` |
| `photo` | glasses | `jpeg_b64`, `w`, `h`, `source: "capture" \| "stream"`, `req_id` |
| `frame` | glasses | `jpeg_b64`, `w`, `h`, `seq` (sampled stream frame) |
| `state` | glasses | `glasses: "disconnected" \| "connected" \| "streaming"`, `battery` |
| `button` | glasses | `press: "short" \| "double" \| "hold"` |

Backend → client:

| type | to | fields |
|---|---|---|
| `capture` | glasses | `req_id`, `quality: "medium" \| "full"` |
| `stream` | glasses | `on: true \| false`, `fps` (sampled frames per second to send, 1–2) |
| `say` | glasses | `text` and/or `audio_b64` (mp3), `interrupt: true \| false` |
| `stop_speaking` | glasses | |
| `led` | band | `color: "#rrggbb"` |

If you need a field that is not here, add it to this table in the same commit as the code.

## Repo layout

```
band/        Ismaël   Python relay for the Vexo Open band (kit is a git submodule or a copy, see band/README.md)
app.py       Ismaël   Recall: runs the memory layer on the laptop with the band
recall/      Ismaël   Recall: memory store, Gemini brain, Pipecat voice, local page; cloud.py + Dockerfile,
                      railway.json, .github/workflows/backend.yml deploy it to Railway
backend/     Tarang   WebSocket server, Pipecat pipeline, agents, dashboard
ios/         Andrii   Swift relay app, XcodeGen project, GitHub Actions build
docs/        all      contract.md (this table, kept in sync), demo script, judging notes
```

Stay in your folder. The only shared file is the contract table above (mirrored in `docs/contract.md`). If you change it, say so in the team chat.

## Team board

One pinned issue is the board: https://github.com/ismaelmehdid/SecondVision/issues/2. Post before you touch another folder or the contract table; address with `@ios`, `@backend`, `@band`.

    tools/board post "@backend contract: photo now carries req_id"
    tools/board unread        # new posts since you last read
    tools/board wait          # keep in a terminal, prints new posts every 30 s

Needs `gh auth login` and collaborator access to the repo. The script is 40 lines of bash over `gh`, written today.

## Rules we must not break

- All code written after 9:00 AM today. Scaffolding copied from a public repo must be named in the README (done above for `ios/`).
- Public repo. No API keys in commits: keys live in `.env` files that are in `.gitignore`. Team keys (Deepgram, OpenAI, Gemini, ElevenLabs) come from the sponsor channels on Discord.
- Submission before 6:00 PM Pacific: this repo, a video demo, a Devpost entry. Final commits before 6:00 PM. Judges want a live in-person demo.
- Tracks we enter: Best Overall, Best Voice Use Case on Pipecat, Best Use of Gemini 4, Best ElevenLabs Project. Each needs the sponsor's tool to be genuinely on the path, not decorative.

## Timeline

| Time | Milestone |
|---|---|
| 12:00 | Contract agreed. Each folder has a README with how to run. |
| 13:00 | Glasses relay: `capture` and `say` work end to end. Band relay: audio and taps reach the backend. |
| 14:00 | Backend: typed question → spoken answer in the glasses. First full loop: say "what is in front of me", hear the answer. |
| 15:00 | Fridge scene works. Streaming from the glasses works (or BLE photo fallback decided). |
| 16:00 | Bus and shelf scenes. Feature freeze. |
| 16:00–17:00 | Record the video. Write Devpost. |
| 17:30 | Final push. Rehearse the 3-minute demo twice. |

## For AI coding agents

If a teammate pointed you at this file, you are working on one of the three parts. Before you write code:

0. Run `tools/board unread` and read what the other two posted. Before you change the WebSocket contract or anything outside your folder, post on the board (`tools/board post "@who ..."`) and wait for the human to say go.

1. Ask which role you are helping: `band/` (Ismaël), `backend/` (Tarang) or `ios/` (Andrii). Work only inside that folder.
2. Read the WebSocket contract above. Your code must send and accept exactly those message types. Do not invent new ones silently; if one is missing, add it to the table in `docs/contract.md` and tell the human.
3. Keep the live loop's logic in `backend/`. The exception is Recall (`app.py`, `recall/`, Ismaël's): the memory
   layer has its own Pipecat pipeline and Gemini calls. The band relay and the glasses relay are dumb pipes: they forward data up and execute commands down. Do not put scene logic, prompts or model calls in `band/` or `ios/`.
4. Never write an API key into a file that is tracked by git. Read keys from environment variables or `.env`.
5. For `band/`: the kit is the source of truth, `vexo-open-kit/AGENTS.md` and `vexo-open-kit/docs/api.md`. Ask for the band number, never guess it. One program on the band at a time.
6. For `ios/`: the SDK is `meta-wearables-dat-ios` 1.0.1. Check signatures against the `.swiftinterface` files in the xcframework, not from memory. Session only via `SpecificDeviceSelector`. Order: `addCamera` → `stream.start` → on `.streaming` attach photo and inputs. Builds run in GitHub Actions; there is no Mac, so every build costs 15–20 minutes: batch changes.
7. For `backend/`: the voice path must run through Pipecat with Deepgram STT and ElevenLabs TTS. Vision calls go to Gemini. Expose what every agent decided on the dashboard; judges score "meaningful use of AI agents".
8. Prefer the smallest thing that demos. A scene that works at 504x896 with a 3-second delay beats a scene that would be perfect at 1080p and is not finished by 16:00.
