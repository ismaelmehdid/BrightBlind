# Deepgram developer digest (VexoHacks, 2026-11-14)

Sponsor tier: gold. Prize (from the event brief, not checked on a public page): **"Best Voice Use Case on Pipecat"**,
up to $100,000 in Deepgram model credits + Nintendo Switches. The track requires building on **Pipecat**: see
`pipecat.md` next to this file. **Unverified** beyond the brief.

Sources: developers.deepgram.com, deepgram.com/pricing, github.com/deepgram/deepgram-python-sdk, pypi.org (all read
2026-11-14). Anything not taken from those pages is marked **(unverified)**.

**What the kit already covers (not repeated here)**: `vexo-open-kit/docs/deepgram.md` and `docs/speech.md`. Nova-3 on
`wss://api.deepgram.com/v1/listen` with the band's raw Opus packets (`encoding=opus&sample_rate=16000&channels=1`, one
packet per binary message), `interim_results`, `smart_format`, `endpointing=100` (measured best on the band),
`mip_opt_out=true` (required by the kit's rules), `KeepAlive` / `CloseStream`, the status-code table (401/402/403/429),
key handling rules, and `examples/python/speech.py` (`speech.create()/feed()/stop()`). This file adds: Flux, TTS, the
Voice Agent API, the current Python SDK, extra STT features, MCP/agent tooling, pricing, gotchas.

---

## 1. What it is (product map, Nov 2026)

| Product | Endpoint | Model strings | Use it for |
|---|---|---|---|
| STT, Nova-3 (streaming) | `wss://api.deepgram.com/v1/listen` | `nova-3` (Pipecat default `nova-3-general`), `language=multi` for multilingual | General live transcription, diarization, keyterms (what the kit uses) |
| STT, **Flux** (conversational) | `wss://api.deepgram.com/v2/listen` | `flux-general-en`, `flux-general-multi` (10 languages, `language_hint`) | Voice agents: model-integrated end-of-turn (~260 ms), `EagerEndOfTurn`, barge-in |
| STT, pre-recorded | `POST https://api.deepgram.com/v1/listen` | `nova-3`, ... | Transcribing a saved `recording.ogg` |
| TTS, Aura-2 | `POST /v1/speak` and `wss://api.deepgram.com/v1/speak` | `aura-2-thalia-en`, `aura-2-apollo-en`, ... (7 languages) | Previous-generation TTS, simple REST |
| TTS, **Flux TTS** | `wss://api.deepgram.com/v2/speak` (streaming) and `POST /v2/speak` (batch) | `flux-{voice}-{lang}`, e.g. `flux-haley-en`, `flux-cole-en`, `flux-heather-en` | Deepgram's recommended TTS now: turn-based, interruptible, cross-turn prosody |
| **Voice Agent API** | `wss://agent.deepgram.com/v1/agent/converse` (regional: `wss://api.eu.deepgram.com/v1/agent/converse`, `.au.`, `.in.`) | listen + think (LLM) + speak in one socket | A full agent without your own orchestration (but the track wants Pipecat) |
| Temporary tokens | `POST https://api.deepgram.com/v1/auth/grant` | JWT, 30 s default TTL | Letting a browser connect without holding the team key |

Flux STT needs `/v2/listen`; `/v1/listen` does not serve it, and `model=flux` is wrong (use the full model name).
Flux TTS needs `/v2/speak`; Aura voices are rejected there, and Flux voices are not served on `/v1/speak`.

## 2. Fit for the track

- The track is "Best Voice Use Case **on Pipecat**", so Deepgram is used **through Pipecat services**:
  `DeepgramSTTService` (Nova-3), `DeepgramFluxSTTService` (Flux), `DeepgramTTSService` (Aura-2),
  `DeepgramFluxTTSService` (Flux TTS). Code for those is in `pipecat.md`.
- Direct Deepgram code (this file) is still useful for: side channels next to the Pipecat bot (e.g. meeting notes with
  diarization from the band), quick tests of a setting before you put it into Pipecat, and TTS of fixed prompts.
- Band specifics: 16 kHz mono Opus, 20 ms per packet. Nova-3 takes the packets as they are (kit). Pipecat and Flux in
  Pipecat take **PCM (linear16)**, so decode with the kit's `vexo_open.audio.PcmDecoder` (needs `pip install av`).
- The band has no speaker: TTS audio plays on the laptop (or the browser). The band's microphone will hear the laptop
  speaker, so the agent can hear itself (see Gotchas).

## 3. MCP servers and agent tooling (do not install anything during the event without the team's OK)

| Name | URL / package | Transport | Auth | Claude Code command |
|---|---|---|---|---|
| **Deepgram docs MCP** (official, documented) | `https://api.dx.deepgram.com/kapa/mcp` (alt: `https://deepgram.mcp.kapa.ai`) | HTTP | none documented | `claude mcp add deepgram-docs --scope project --transport http https://api.dx.deepgram.com/kapa/mcp` |
| **`dg` CLI as MCP** (official) | package `deepctl` (command `dg`) | stdio (default); `dg mcp --transport sse --port 8000` | `dg login` stored credentials, or `DEEPGRAM_API_KEY` in the environment | `claude mcp add deepgram --scope user -- dg mcp` (see note) |
| Deepgram skills plugin (not MCP) | GitHub `deepgram/skills` | Claude Code plugin | none | in Claude Code: `/plugin marketplace add deepgram/skills` then `/plugin install deepgram@deepgram-agent-skills` |

Notes:
- The docs MCP only answers questions from Deepgram's documentation: safe, no key, no billing. Recommended.
- The `dg mcp` server proxies the **real Deepgram API** with your key, so its calls are billed to the team key, and audio
  you hand it leaves the laptop. Deepgram's page prints `claude mcp add deepgram --scope user --command dg --args mcp`;
  Claude Code's `mcp add` has no `--command/--args` flags, the standard form is `claude mcp add <name> -- <cmd> <args>`
  as in the table **(the official page's syntax looks wrong; unverified which one your Claude Code accepts)**.
- Install `dg` with `pip install deepctl` or `uv tool install deepctl` (documented). Deepgram also documents
  `iwr https://deepgram.com/install.ps1 -useb | iex` for PowerShell; that runs a remote script, prefer pip/uv.
- An older Fern-generated docs MCP at `https://developers.deepgram.com/_mcp/server` appeared in search results but
  returned 404 on 2026-11-14. Do not use it.
- Never put the key into `.mcp.json` or a `claude mcp add -e ...` line that ends up in a committed file.

## 4. Keys and auth

- Each team gets a key from the organisers (kit rules). Otherwise: console.deepgram.com sign-up gives **$200 free
  credit, no credit card, no expiry** (pricing page).
- REST and WebSocket header: `Authorization: Token <API key>`; temporary tokens use `Authorization: Bearer <jwt>`.
- Python SDK reads `DEEPGRAM_API_KEY` (or `DEEPGRAM_TOKEN`, which takes precedence) from the environment:
  `DeepgramClient()` with no arguments. Explicit `api_key=` / `access_token=` beat the environment.
- Temporary tokens for a browser page: your Python backend calls `POST /v1/auth/grant` with the key; the token lives
  30 s by default (`{"ttl_seconds": N}` up to 3600; the field is `ttl_seconds`, an unknown field is silently ignored).
  It only has to be valid at the WebSocket handshake. **Minting needs a key with Member permission or higher**; an event
  key may not have that (unverified). SDK: `DeepgramClient().auth.v1.tokens.grant().access_token`.
  In a browser: `new WebSocket(url, ['bearer', jwt])` **(unverified; the kit's documented form is `['token', key]`)**.

## 5. Python SDK (current)

- Package `deepgram-sdk` **7.19.0** (2026-11-13), Python >= 3.10. Install: `python -m pip install deepgram-sdk`.
- v7 kept the v6 client API. Old tutorials (v3/v4: `LiveOptions`, `deepgram.listen.websocket.v("1")`) and v5
  (`ListenV1MediaMessage`, `send_control(...)`, `deepgram.extensions...`) **no longer work**. v6+ uses
  `send_media(bytes)`, `send_keep_alive()`, `send_finalize()`, `send_close_stream()`, `send_configure(...)`.
- WebSocket query parameters are passed as keyword arguments and are typed as **strings** in `listen.v1.connect`
  (`interim_results="true"`, `sample_rate="16000"`); `listen.v2.connect` takes `sample_rate` as an int.
- `connection.start_listening()` blocks: run it on a thread (sync client) or `await` it in a task (async client).

### 5a. Nova-3 from the band through the SDK, with diarization and UtteranceEnd

Complements the kit's raw-WebSocket `forward.py`. Not run here **(unverified end to end)**; the API calls are from the
SDK reference. Save in `my-project/`, run `python dg_notes.py <band number>`.

```python
import sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "vexo-open-kit" / "python"))
from vexo_open.sync import Band
from deepgram import DeepgramClient
from deepgram.core.events import EventType

BAND = int(sys.argv[1])                       # the team's band number: one place, never guessed
client = DeepgramClient()                     # key from DEEPGRAM_API_KEY (env or set in the terminal)

def on_message(m):
    kind = getattr(m, "type", "")
    if kind == "Results" and m.is_final:
        words = m.channel.alternatives[0].words or []
        if words:                              # diarize: each word carries a speaker number
            print(f"[speaker {words[0].speaker}] {m.channel.alternatives[0].transcript}")
    elif kind == "UtteranceEnd":
        print("--- utterance end ---")

print("Note: the band's microphone is sent to Deepgram while this runs.")
with client.listen.v1.connect(
    model="nova-3", language="en", encoding="opus", sample_rate="16000", channels="1",
    interim_results="true", smart_format="true", endpointing="100",
    utterance_end_ms="1000", vad_events="true", diarize="true",
    keyterm="Vexo", mip_opt_out="true",
) as dg:
    dg.on(EventType.MESSAGE, on_message)
    dg.on(EventType.ERROR, lambda e: print("Deepgram error:", type(e).__name__))   # never print the key
    threading.Thread(target=dg.start_listening, daemon=True).start()
    band = Band.connect(BAND)
    band.on("audio", lambda a: dg.send_media(a.opus))   # one Opus packet = one message
    band.configure(audio=True)                           # light goes solid blue
    band.wait(30)
    band.configure(audio=False)
    band.disconnect()
    dg.send_close_stream()                               # last results, then Deepgram closes
```

Extra Nova-3 streaming features (all from the `/v1/listen` streaming reference):
- `diarize_model=latest|v1` is the new way to ask for diarization (`diarize=true` is deprecated but still routes to
  the v1 diarizer; `v2` is batch-only and fails on streaming). The SDK's `connect()` does not list `diarize_model`;
  pass it via `request_options={"additional_query_parameters": {"diarize_model": "latest"}}` **(unverified)**.
- `utterance_end_ms` (needs `interim_results=true`) sends an `UtteranceEnd` message after a gap in words: more robust
  than `speech_final` in noise. `vad_events=true` sends `SpeechStarted` (Beta).
- `keyterm` (Nova-3 only, plain terms, no `:weight`; a weight is silently treated as part of the term). Mid-stream:
  `dg.send_configure(ListenV1Configure(keyterms=[...], features={"numerals": True}))` from `deepgram.listen.v1.types`,
  answered by `ConfigureSuccess` / `ConfigureFailure`.
- `numerals`, `redact`, `profanity_filter`, `language=multi` (+ `language_hint`, SDK >= 7.15), `tag`, `extra`.
- `Finalize` (`dg.send_finalize()`): flush the current result now, e.g. when the wearer taps the band to "send".

## 6. Flux STT (`/v2/listen`) for turn-taking

- Models `flux-general-en`, `flux-general-multi`. Raw encodings: `linear16, linear32, mulaw, alaw, opus, ogg-opus`
  (`encoding` and `sample_rate` required; 16000 recommended). Containerized: WAV, Ogg-Opus, WebM-Opus (omit both).
- **Send ~80 ms chunks** (strongly recommended): at 16 kHz linear16 that is 2560 bytes = 4 band packets decoded.
  Raw `opus` is listed as supported, but packet-per-message at 20 ms is below the recommendation; decode to PCM.
- Parameters: `eot_threshold` 0.5-1.0 (default 0.7), `eager_eot_threshold` 0.3-0.9 (default none; required to get
  `EagerEndOfTurn`), `eot_timeout_ms` 500-60000 (default 5000), `keyterm`, `language_hint` (multi only), `numerals`,
  `profanity_filter`, `redact`, `mip_opt_out`, `tag`. Do not send `language=`.
- Messages: `Connected`, `TurnInfo` with `event` = `StartOfTurn` / `Update` / `EagerEndOfTurn` / `TurnResumed` /
  `EndOfTurn` (only `Update`, `StartOfTurn`, `EndOfTurn` by default), plus `transcript`, `words`, `turn_index`,
  `end_of_turn_confidence`. Control: `CloseStream`, `Configure` (change thresholds/keyterms/numerals mid-stream,
  answered by `ConfigureSuccess`), `ForceEndTurn` (end the turn now: perfect for "tap the band to finish").
- Recommended agent logic: `StartOfTurn` = stop the bot talking; `EndOfTurn` = send transcript to the LLM.

```python
import sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "vexo-open-kit" / "python"))
from vexo_open.sync import Band
from vexo_open.audio import PcmDecoder
from deepgram import DeepgramClient
from deepgram.core.events import EventType

BAND = int(sys.argv[1])
print("Loading the sound decoder...")
decoder = PcmDecoder()                                    # a few seconds the first time (needs `av`)
buf = bytearray()

def on_message(m):
    if getattr(m, "type", "") == "TurnInfo" and m.event == "EndOfTurn":
        print("turn:", m.transcript)

print("Note: the band's microphone is sent to Deepgram while this runs.")
with DeepgramClient().listen.v2.connect(model="flux-general-en", encoding="linear16",
                                        sample_rate=16000, mip_opt_out="true") as dg:
    dg.on(EventType.MESSAGE, on_message)
    threading.Thread(target=dg.start_listening, daemon=True).start()
    band = Band.connect(BAND)
    def on_audio(a):
        buf.extend(decoder.feed(a))                       # 640 bytes per 20 ms packet
        if len(buf) >= 2560:                              # 80 ms
            dg.send_media(bytes(buf)); buf.clear()
    band.on("audio", on_audio)
    band.configure(audio=True)
    band.wait(30)
    band.configure(audio=False); band.disconnect()
    dg.send_close_stream()
```
**(unverified end to end; structure from Deepgram's Flux quickstart and SDK reference.)** A GitHub issue (Jan 2026,
SDK 5.3.1) reports Flux sockets dropping after ~20-30 s of silence and JSON `KeepAlive` not helping on `/v2/listen`;
while the band's microphone is on it streams continuously, so keep sending audio rather than pausing.

## 7. Text to speech

Aura-2 over REST, played with Windows' built-in `winsound` (no install). Ask for WAV so `winsound` can play it:

```python
import json, os, urllib.request, winsound

def say(text, voice="aura-2-thalia-en"):
    url = (f"https://api.deepgram.com/v1/speak?model={voice}"
           "&encoding=linear16&container=wav&sample_rate=24000")
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
        headers={"Authorization": "Token " + os.environ["DEEPGRAM_API_KEY"], "Content-Type": "application/json"})
    winsound.PlaySound(urllib.request.urlopen(req).read(), winsound.SND_MEMORY)

say("Your band is connected.")
```
**(container=wav with linear16 is the documented pattern for a playable file; not run here.)** SDK alternative:
`DeepgramClient().speak.v1.audio.generate(text=...)` yields MP3 chunks by default.

- Streaming Aura: `client.speak.v1.connect(model=..., encoding="linear16", sample_rate=24000)`, then
  `send_text(SpeakV1Text(text=...))`, `send_flush()` (get audio now), `send_clear()` (barge-in), `send_close()`.
  The stream is raw PCM with no header.
- **Flux TTS** (`/v2/speak`, model required, e.g. `flux-haley-en`): stream LLM tokens with `Speak` messages, end a turn
  with `Flush`; the server places flushes itself. `Interrupt` reports `text_spoken` / `text_remaining` so the LLM
  context matches what was heard. Streaming output: raw `linear16` (default), `mulaw`, `alaw`; sample rates
  8000-48000; `speed` 0.5-1.5; `expressivity` -2..2 (Beta); `mip_opt_out`. MP3/Opus/FLAC/AAC only on batch REST.
  SDK: `client.speak.v2.connect(model="flux-haley-en")`, `send_speak(SpeakV2Speak(text=token))`, `send_flush()`.
- Aura-2 voices: `aura-2-{voice}-{en|es|de|fr|nl|it|ja}`; featured English: thalia, andromeda, helena, apollo, arcas,
  aries. Full list: developers.deepgram.com/docs/tts-models.

## 8. Voice Agent API (one socket: listen + think + speak)

Flow: connect, wait for `Welcome`, send `Settings`, wait for `SettingsApplied`, then stream binary audio; you get
`ConversationText`, `UserStartedSpeaking` (stop playback = barge-in), binary TTS audio, function-call messages.
Inject text with `{"type": "InjectUserMessage", "content": "Hello"}`. Minimal `Settings` (from Deepgram's docs):

```json
{"type": "Settings",
 "audio": {"input": {"encoding": "linear16", "sample_rate": 16000},
           "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"}},
 "agent": {"listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
           "think": {"provider": {"type": "open_ai", "model": "gpt-4o-mini"}, "prompt": "You are..."},
           "speak": {"provider": {"type": "deepgram", "version": "v2", "model": "flux-kit-en"}},
           "greeting": "Hi!"}}
```
- Listen can be Flux (`flux-general-en`, provider `version: "v2"`). Think providers include `open_ai`, `google`,
  `groq`, `aws_bedrock`; speak providers include `deepgram`, `eleven_labs`, `cartesia`, `open_ai`, `aws_polly`.
- Python SDK: `with client.agent.v1.connect() as agent: agent.send_settings(AgentV1Settings(...))`,
  `agent.send_media(pcm)`, `agent.send_keep_alive()` (types under `deepgram.agent.v1.types` and `deepgram.types`; v7
  renamed many: copy from the SDK README, not old blogs). Whether `audio.input.encoding` accepts `opus` is not stated
  in what was read: feed decoded linear16 **(unverified)**.
- For this prize, prefer Pipecat (which orchestrates STT, LLM, TTS itself); the Voice Agent API is the fallback if
  Pipecat will not run on a laptop.

## 9. Pricing and limits (deepgram.com/pricing, 2026-11-14, Pay as you go)

| Item | Price |
|---|---|
| Free credit | $200, no card, no expiry ("roughly 43,000 minutes" of Nova-3) |
| Streaming STT, monolingual (Nova-3 or Flux) | $0.46 / hour (Growth $0.39) |
| Streaming STT, multilingual | Nova-3 $0.55 / hour, Flux $0.47 / hour |
| Pre-recorded STT | Nova-3 $0.0048 / min; Flux EN $0.0065 / min |
| Add-ons | diarization $0.0020 / min, keyterm $0.0013 / min, redaction $0.0020 / min, entity detection $0.0017 / min, smart format included |
| TTS (Flux TTS, Aura-2, Aura-1) | per 1,000 characters; Aura-2 $0.030 / 1k chars per a Deepgram blog **(check the pricing table)** |
| Voice Agent API | per minute of connection, one rate for STT + managed LLM + TTS **(rate not extracted; check the page)** |
| Concurrency, PAYG | pricing page: 150 streaming STT connections; an older Deepgram landing page says 50 WSS STT, 15 TTS, 15 Voice Agent **(conflicting)** |

Every open socket is billed for the audio sent, so close it (`CloseStream`) when the microphone goes off.

## 10. Gotchas

- **Windows key setup**: PowerShell `$env:DEEPGRAM_API_KEY = "..."` (quotes), cmd `set DEEPGRAM_API_KEY=...` (no
  quotes). A new terminal forgets it. Or the `.env` file (kit rules: never commit it).
- **Old snippets everywhere.** SDK v3/v4/v5 code (`LiveOptions`, `ListenV1MediaMessage`, `send_control`) fails on v7.
  Deepgram's own "Pipecat + Deepgram" guide still uses Pipecat's old `PipelineTask/PipelineRunner` (see pipecat.md).
- **Flux vs Nova endpoints**: Flux only on `/v2/listen`, chunk ~80 ms, `language=` not allowed; Pipecat's
  `DeepgramFluxSTTService` accepts only `linear16`.
- **Silence timeout**: Deepgram closes a `/v1/listen` socket that gets no audio/text for ~10 s (error `NET-0001`,
  close 1011). Send `KeepAlive` during pauses (kit covers it).
- **Self-hearing**: the band's mic picks up the laptop speaker playing TTS; with Flux/VAD barge-in the agent
  interrupts itself. Use headphones, or ignore band audio while the bot speaks.
- **`mip_opt_out=true`**: required by the kit's rules on every connection; Pipecat's docs say to check the Model
  Improvement Program page for pricing impact before setting it **(impact not checked)**.
- **TTS output has no header** on WebSockets: wrap PCM in a WAV header yourself (Python `wave` module) to play/save.
- **Model name typos**: `flux` (wrong) vs `flux-general-en`; `aura-2-thalia-en` on `/v1/speak` only.
- **Do not log the key**: catch `ApiError` and print `e.status_code` only (the kit's rule), never `e.headers`/request.
- **Network**: event Wi-Fi may block WebSockets; the kit's table says try a phone hotspot.

## 11. Links

- Docs home / LLM index: https://developers.deepgram.com , https://developers.deepgram.com/llms.txt (append `.md` to
  any docs page for clean Markdown)
- Streaming STT reference: https://developers.deepgram.com/reference/speech-to-text/listen-streaming
- Encoding list: https://developers.deepgram.com/docs/encoding
- Diarization: https://developers.deepgram.com/docs/diarization
- Flux STT quickstart: https://developers.deepgram.com/docs/flux/quickstart ; Configure:
  https://developers.deepgram.com/docs/flux/configure ; ForceEndTurn: https://developers.deepgram.com/docs/flux/force-end-turn
- Nova-3 to Flux migration: https://developers.deepgram.com/docs/flux/nova-3-migration
- Flux voice agent guide: https://developers.deepgram.com/docs/flux/agent
- Flux TTS: https://developers.deepgram.com/docs/flux-tts/quickstart ; TTS models:
  https://developers.deepgram.com/docs/tts-models-languages-overview , https://developers.deepgram.com/docs/tts-models
- Voice Agent: https://developers.deepgram.com/docs/build-a-voice-agent ,
  https://developers.deepgram.com/docs/voice-agent-message-flow , https://developers.deepgram.com/docs/configure-voice-agent
- Token auth: https://developers.deepgram.com/guides/fundamentals/token-based-authentication
- Pipecat + Deepgram guide (old Pipecat API names): https://developers.deepgram.com/docs/build-voice-agent-with-pipecat-and-deepgram
- Agentic tools (MCP, CLI, skills): https://developers.deepgram.com/developer-tools/agentic-tools ; CLI MCP:
  https://developers.deepgram.com/developer-tools/cli/mcp-server ; https://cli.deepgram.com
- Python SDK: https://github.com/deepgram/deepgram-python-sdk (README, `reference.md`, `docs/Migrating-v6-to-v7.md`),
  https://pypi.org/project/deepgram-sdk/
- Pricing: https://deepgram.com/pricing ; Console / keys: https://console.deepgram.com
- Playground: https://playground.deepgram.com/?endpoint=agent
