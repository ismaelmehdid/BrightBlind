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
as the user's long-term memory (for example the "usual stock" in the fridge scene) over plain HTTP on the same
server (Railway: add `?token=` or `Authorization: Bearer`):

| Call | Body | Returns |
|---|---|---|
| `POST /api/ask` | `{"question": "what is usually in my fridge?"}` | `{"question", "answer", "ts", ...}` (Gemini, from all memories) |
| `POST /api/note` | `{"text": "..."}` | `{"ok": true}`: stores a line as if the band heard it |
| `GET /api/memories?limit=200` | | memories, newest first: `kind`, `text`, `people`, `importance`, `context`, `ts` |
| `GET /api/heard?limit=100` | | the transcript with band context (`activity`, `steps`, `bookmarked`) |
| `GET /api/context` | | the band right now: `activity`, `steps`, `battery`, `connected`, `mic`, `backend` |

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
- **The band relay is built into Recall** (`recall/relay.py`), so one program holds the band and does both jobs.
  Add `--backend "wss://<backend host>/ws?token=<band relay token>"` (or set `BACKEND_WS_URL` in `.env`): it sends
  `hello`, `audio` (`pcm_b64`, 16 kHz s16le as `backend/` prefers, with its own increasing `seq`; `--backend-opus`
  for raw Opus), `event` (`tap`, `double-tap`, `free-fall`, `tilt`) and `activity` exactly as in the contract
  below, reconnects by itself, and runs `led` commands. The band refuses `led` while its microphone is on
  (kit rule 4), and the microphone is on whenever audio is forwarded.
  With a backend connected, Recall stays silent and leaves double-tap to the backend (one voice, in the glasses);
  it keeps transcribing, storing and bookmarking (tap). `--sim --backend ...` tests it with no band.
- **The backend asks the Recall on Railway** when its planner picks `memory`. Only the laptop hears the band, so
  the laptop copies its memory there as it goes (`recall/mirror.py`): every stored line with what the body was
  doing, and every tap. Set `RECALL_CLOUD_URL=https://<service>.up.railway.app` and `RECALL_CLOUD_TOKEN=<the
  Railway service's RECALL_TOKEN>` in the laptop's `.env` (add `--mirror-backfill` once to send what is already
  there). Lines wait while Railway is unreachable. In the backend's `.env`:
  `RECALL_WS_URL=wss://<service>.up.railway.app/ws` and `RECALL_TOKEN=<the same Railway token>`. The Railway
  Recall needs its own `GEMINI_API_KEY` to distill and answer (`DEPLOY.md`). An answer that takes more than 20 s
  (a rate-limited Gemini) comes back as "my memory is busy", inside the backend's 25 s limit.
- Fallback without Railway: `--tunnel` gives the laptop's Recall a public `https://….trycloudflare.com` address
  (needs `cloudflared`), guarded by `RECALL_TOKEN`; the address changes on every start.
- **Without the backend, Recall can drive the glasses itself** (`recall/glasses.py`): Andrii's app connects to
  `wss://…/glasses?token=…` (printed with `--tunnel`). Answers then play in the glasses, and a tap also takes a
  photo that Gemini describes into a memory.

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
mobile/      Ismaël   Expo control app (Expo Go): band + glasses status, burst control, live agent steps and photos
                      from Recall's /ws, plus the team backend's /api/state when given its URL and dashboard token.
                      Run: cd mobile; npx expo start --tunnel ngrok, scan the QR code with Expo Go
docs/        all      contract.md (this table, kept in sync), demo script, judging notes
```

Stay in your folder. The only shared file is the contract table above (mirrored in `docs/contract.md`). If you change it, say so in the team chat.

## How we work today (the pipeline)

Six stages, adapted from Andrii's hackathon pipeline (Notion: "Universal pipeline for hackathon"). Stages 1–3 are done and live in this file; 4–6 are what the rest of the day looks like.

1. **Idea.** Done: SecondVision, three demo scenes above. Everything is built backwards from the 2-minute demo. If a feature is not in a scene, it does not get built.
2. **Explain it to the agent.** Done: this README is the explanation. Every new agent session starts by reading it; if the agent's summary of the project does not match yours, fix the README, not the agent.
3. **Architecture.** Done: two hubs, one backend, one WebSocket contract. `README.md` plays the role of `PLAN.md`. A feature that needs a new message type goes through the contract table and the board first.
4. **Ready-made components.** Nobody styles buttons today. The judges' dashboard (`backend/`) is shadcn/ui for the base, Magic UI or Aceternity for the first screen. Band code comes from `vexo-open-kit` examples. The glasses session is copied from Andrii's public scaffold.
   Prompt: `Build the UI with shadcn/ui. For the first screen use Magic UI / Aceternity components. Don't write styles from scratch if an existing component already does the job.`
5. **Building.** Three agents in parallel, one per folder, because the slices do not share files (`band/`, `backend/`, `ios/`). The one shared thing is the contract table; changes to it go on the board. After every step the human opens the result and checks it, no "done" on trust. Before a merge into `main`, run a reviewer agent that did not write the code:
   `You didn't write this code. Go through <folder/feature> and find bugs, broken flows and anything that will break during the demo. Don't fix anything, give me a list with file and line.`
6. **Presentation.** Feature freeze at 17:00. After that only: bugs visible in the demo flow, the backup video, the pitch (problem, solution, live demo, what's next), two full dry runs out loud.
   Prompt at 17:00: `Submission is in one hour. We're not adding features. Help me with: 1) bugs visible in the demo flow, by priority; 2) a structure for a 3-minute pitch; 3) a step-by-step script for recording the demo video.`

Two habits from the pipeline that pay off most here: walk up to the judges and sponsors and ask what they want to see (Vexo, Mastra and Pipecat people are in the room), and decide the demo before building anything.

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
| 16:00 | Bus and shelf scenes. |
| 17:00 | Feature freeze (stage 6). Only demo-flow bugs, video, pitch, dry runs. |
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
