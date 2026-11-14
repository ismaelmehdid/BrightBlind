# Pipecat developer digest (VexoHacks, 2026-11-14)

Why it matters: the Deepgram gold prize is **"Best Voice Use Case on Pipecat"** (event brief, **unverified** beyond
it), so the project must run on Pipecat, ideally with Deepgram STT/TTS. Deepgram-side details: `deepgram.md`.

Sources: docs.pipecat.ai, github.com/pipecat-ai (pipecat, pipecat-examples, pipecat-mcp-server), pypi.org,
daily.co/pricing/pipecat-cloud (all read 2026-11-14). Code not copied from those pages is marked **(unverified)**:
nothing here was run on a band.

**Versions**: `pipecat-ai` **1.16.0** (2026-11-12), Python **>= 3.11** (3.11-3.14; the team's 3.12 is fine).
**API rename in 1.3.0**: `PipelineTask` -> `PipelineWorker` (`pipecat.pipeline.worker`), `PipelineRunner` ->
`WorkerRunner` (`pipecat.workers.runner`), `runner.run(task)` -> `await runner.add_workers(worker)` then
`await runner.run()`, `task.queue_frames` -> `worker.queue_frames`. The old names still import with a
`DeprecationWarning` and go away in 2.0.0. Many tutorials, **including Deepgram's own Pipecat guide**, use the old names.

---

## 1. What it is

- Open-source (BSD-2) **Python framework for real-time voice and multimodal agents**, by Daily.
- A bot is a **Pipeline** of **FrameProcessors**; data moves as **Frames** (audio, text, control).
  Typical: `transport.input() -> stt -> user_aggregator -> llm -> tts -> transport.output() -> assistant_aggregator`.
- Frame classes: `SystemFrame` (high priority, never dropped by interruptions: `InputAudioRawFrame`, `StartFrame`,
  `InterruptionFrame`, `UserStartedSpeakingFrame`), `DataFrame` (dropped on interruption: `TextFrame`,
  `TranscriptionFrame`, `LLMTextFrame`, `OutputAudioRawFrame`, `TTSSpeakFrame`), `ControlFrame` (`EndFrame`, ...).
- **Transports** connect users: SmallWebRTC (P2P, no account), Daily, LiveKit, FastAPI WebSocket (telephony),
  plain WebSocket server/client, local audio (PyAudio), WhatsApp, MoQ, avatar transports (HeyGen, Tavus, ...).
- ~All STT/LLM/TTS vendors as services; swap by changing one line. Voice activity: Silero VAD. Turn-taking:
  "user turn strategies" (Deepgram Flux brings its own).
- **Pipecat CLI** (`pipecat init`, `pipecat cloud ...`, `pipecat context-hub ...`) and **Pipecat Cloud** (hosting).
- Client SDKs (JS/React, iOS, Android) speak the **RTVI** protocol to the bot.

## 2. Fit for the band

    band mic --BLE--> laptop (vexo_open async Band) --Opus--> PcmDecoder --PCM 16 kHz--> Pipecat pipeline
         Deepgram STT (Nova-3 or Flux) -> LLM (OpenAI key from the organisers) -> Deepgram TTS -> laptop speaker
                                                       |
                                 LLM tools / your code: band LED (after the mic is off), screen, motion state

- Pipecat transports expect **PCM**, not Opus: decode every band packet with the kit's `vexo_open.audio.PcmDecoder`
  (`python -m pip install av`), 640 bytes = 20 ms at 16 kHz mono 16-bit. Pipecat's default input rate is 16000, the
  same as the band, so no resampling.
- Two ways in: (A) **custom input transport** fed by the band (section 6, recommended: real wearable demo);
  (B) the built-in **SmallWebRTC browser client** with the laptop mic (section 5) to build and demo the agent first.
- Kit rules still apply: one band number in one place, tell people the mic is on, `mip_opt_out`, keys only in env/.env,
  **no LED commands while the mic is on** (kit rule 4).

## 3. MCP servers (for your coding agent) and MCP in bots. Nothing installed.

| Name | URL / package | Transport | Auth | Claude Code command |
|---|---|---|---|---|
| **Pipecat docs MCP** (hosted by docs.pipecat.ai, Mintlify) | `https://docs.pipecat.ai/mcp` | HTTP | none (read-only; tools `search_pipecat`, `query_docs_filesystem`, `submit_feedback`) | `claude mcp add --transport http pipecat-docs https://docs.pipecat.ai/mcp` |
| **Pipecat Context Hub** (official, documented) | PyPI `pipecat-ai-context-hub` (also ships in `pipecat-ai[cli]`) | stdio, local index | none (builds a local index: ~3+ min, ~900 MB) | `claude mcp add pipecat-context-hub -- uvx pipecat-ai-context-hub serve` (or `pipecat context-hub install`, which registers it and builds the index) |
| Pipecat MCP Server (gives *Claude* a voice; not docs) | PyPI `pipecat-ai-mcp-server`, runs at `http://localhost:9090/mcp` | HTTP (local) | none by default (local Whisper + Kokoro) | `claude mcp add pipecat --transport http http://localhost:9090/mcp --scope user` |
| `pipecat-mcp-transport` (serve **your bot** as an MCP server) | `McpBotServer(bot).run()`, default `http://127.0.0.1:7870/mcp` | Streamable HTTP | none, binds localhost | `claude mcp add --transport http pipecat http://127.0.0.1:7870/mcp` |

- The hosted docs MCP was confirmed by fetching `https://docs.pipecat.ai/mcp` (server card JSON); no docs page was
  found that documents it, so treat its permanence as **unverified**. The Context Hub is the documented route:
  Tools `search_docs`, `search_examples`, `search_api`, `get_doc`, `get_example`, `get_code_snippet`,
  `check_deprecation` (useful because of the 1.3.0 renames), `get_hub_status`. MCP servers load at session start.
- Bot side: `MCPClient` (`uv add "pipecat-ai[mcp]"`, MCP SDK 2.1.1+) lets the bot's LLM call MCP tools:
  `context = LLMContext(tools=await MCPClient(server_params=...).tools())` (stdio, SSE or Streamable HTTP params).

## 4. Install (Windows 11, Python 3.12)

```powershell
python -m pip install uv                  # or the official uv installer
uv tool install "pipecat-ai[cli]"         # CLI; add --with pipecatcloud for `pipecat cloud ...`
mkdir my-project; cd my-project            # the kit goes inside it (kit layout rules)
uv init --python 3.12
uv add "pipecat-ai[deepgram,openai,silero,webrtc,runner,local]" python-dotenv av bleak
```
- Extras: `deepgram`, `openai`, `silero` (VAD), `webrtc` (SmallWebRTC via aiortc), `runner` (dev runner + browser
  client), `local` (PyAudio; Windows wheels include PortAudio, no extra install), `websocket`, `daily`, `mcp`.
  `av` and `bleak` are for the kit (decoder, Bluetooth). Plain pip works too:
  `python -m pip install "pipecat-ai[deepgram,openai,silero,webrtc,runner,local]"`.
- Scaffold instead: `pipecat init quickstart` (writes `bot.py`, `.env.example`, `AGENTS.md`, `CLAUDE.md`,
  `pcc-deploy.toml`, Dockerfile). Quickstart default services: Deepgram STT, OpenAI, **Cartesia** TTS (a third key):
  switch TTS to Deepgram as below.
- Windows: a 2026-05 issue (pipecat 1.2.1) shows `pipecat init` crashing with `'charmap' codec can't encode
  character`; if you see it, run `$env:PYTHONUTF8 = "1"` first **(workaround unverified)**.

## 5. Minimal bot: Deepgram STT + OpenAI + Deepgram TTS, browser mic (current API)

Adapted from Deepgram's Pipecat guide and Pipecat's `examples/voice/voice-deepgram-flux.py`, with the 1.3.0 names.
`.env`: `DEEPGRAM_API_KEY=...`, `OPENAI_API_KEY=...` (the team creates it; never commit it).

```python
# bot.py  --  uv run bot.py -t webrtc   then open http://localhost:7860/client
import os
from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair, LLMUserAggregatorParams)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.responses.llm import OpenAIResponsesLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

def services():
    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"], mip_opt_out=True,
        settings=DeepgramSTTService.Settings(model="nova-3-general", language="en", smart_format=True))
    llm = OpenAIResponsesLLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAIResponsesLLMService.Settings(
            model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),   # same default as the kit's ai.MODEL
            system_instruction="You are a voice assistant on a wristband. Answer in one or two short "
                               "spoken sentences, no lists, no emojis."))
    tts = DeepgramTTSService(api_key=os.environ["DEEPGRAM_API_KEY"],
                             settings=DeepgramTTSService.Settings(voice="aura-2-thalia-en"))
    return stt, llm, tts

async def run_bot(transport, handle_sigint=True, network=True):
    stt, llm, tts = services()
    context = LLMContext()
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()))
    pipeline = Pipeline([transport.input(), stt, user_agg, llm, tts, transport.output(), assistant_agg])
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))
    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)

    if network:                                       # these events exist on network transports only
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            context.add_message({"role": "developer", "content": "Greet the user in one sentence."})
            await worker.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            await runner.cancel()

    await runner.run()

async def bot(runner_args: RunnerArguments):          # entry point the dev runner / Pipecat Cloud call
    transport = await create_transport(runner_args, {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True)})
    await run_bot(transport, runner_args.handle_sigint)

if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
```
- First run downloads the Silero model (~20 s). Runner flags: `-t webrtc|daily|...`, `--host`, `--port` (default
  7860), `-v`. With no `-t` the runner serves all transports at once and the client picks one.
- `OpenAILLMService` (`pipecat.services.openai.llm`, Chat Completions) also exists; the quickstart uses the Responses
  service. Whether the organisers' key/model works with both: **unverified**; the kit itself uses the Responses API.

## 6. Feeding the band into Pipecat (custom input transport)

Pattern taken from Pipecat's own `LocalAudioTransport` source (subclass `BaseInputTransport`, call
`set_transport_ready()` in `start()`, push `InputAudioRawFrame`s with `push_audio_frame()`). The kit's **async**
`Band` (`from vexo_open import Band`) runs its handlers on the same asyncio loop as Pipecat. Output goes to the
laptop speaker through Pipecat's `LocalAudioOutputTransport`. **(unverified: written from the sources, not run.)**

```python
# band_bot.py  --  python band_bot.py <band number>     (reuses services() from bot.py above)
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "vexo-open-kit" / "python"))
import pyaudio
from vexo_open import Band                                  # async API, same loop as Pipecat
from vexo_open.audio import PcmDecoder
from pipecat.frames.frames import InputAudioRawFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.local.audio import LocalAudioOutputTransport, LocalAudioTransportParams
from bot import run_bot

BAND = int(sys.argv[1])                                     # the team's number: one place, never guessed

class BandInput(BaseInputTransport):
    def __init__(self, params):
        super().__init__(params)
        self.ready = asyncio.Event()
    async def start(self, frame):
        await super().start(frame)
        await self.set_transport_ready(frame)
        self.ready.set()
    async def push_pcm(self, pcm: bytes):
        await self.push_audio_frame(InputAudioRawFrame(audio=pcm, sample_rate=16000, num_channels=1))

class BandTransport(BaseTransport):
    def __init__(self, params):
        super().__init__()
        self._in = BandInput(params)
        self._out = LocalAudioOutputTransport(pyaudio.PyAudio(), params)   # laptop speaker
    def input(self): return self._in
    def output(self): return self._out

async def main():
    transport = BandTransport(LocalAudioTransportParams(audio_in_enabled=True, audio_out_enabled=True))
    print("Loading the sound decoder...")
    decoder = await asyncio.to_thread(PcmDecoder)           # first one takes seconds

    async def start_band():
        await transport.input().ready.wait()                # pipeline is up
        band = await Band.connect(BAND)
        async def on_audio(a):
            await transport.input().push_pcm(decoder.feed(a))   # 20 ms of PCM per band packet
        band.on("audio", on_audio)
        print("Note: the band's microphone is sent to Deepgram while this runs. Tell the people near you.")
        await band.configure(audio=True)                    # solid blue light: mic on, LED locked

    band_task = asyncio.create_task(start_band())          # keep a reference to the task
    await run_bot(transport, network=False)

asyncio.run(main())
```
- `on_client_connected` / `on_client_disconnected` belong to network transports, hence `network=False`. To greet
  the wearer, have `run_bot` return or expose the worker and queue `LLMRunFrame()` once the band is on.
- Stop: Ctrl+C (`WorkerRunner` has a Windows fallback for SIGINT). Turn the mic off with
  `await band.configure(audio=False)` and `await band.disconnect()` before exit if you can.
- **Self-hearing**: the band mic hears the laptop speaker, Silero/Deepgram see speech, and the bot interrupts
  itself. Use headphones for the demo, or drop band frames while the bot speaks (watch `BotStartedSpeakingFrame` /
  `BotStoppedSpeakingFrame` in a small `FrameProcessor` and gate `push_pcm`) **(approach unverified)**.
- Tap-to-talk: Flux's `ForceEndTurn` or Nova's `Finalize` can end a turn on a `tap` event (deepgram.md).
- Browser alternative (no Python BLE): the kit's `BandAudio` decodes band packets in Chrome; turning those samples
  into a MediaStreamTrack for the Pipecat JS client is possible in principle **(unverified, more work)**.

## 7. Swap in Deepgram Flux (turn detection by the model)

```python
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.flux.tts import DeepgramFluxTTSService

stt = DeepgramFluxSTTService(api_key=os.environ["DEEPGRAM_API_KEY"], mip_opt_out=True,
        enable_eager_end_of_turn=True,       # start the LLM on EagerEndOfTurn, keep it if the turn confirms
        settings=DeepgramFluxSTTService.Settings(eot_threshold=0.8, keyterm=["Vexo", "Pipecat"]))
tts = DeepgramFluxTTSService(api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramFluxTTSService.Settings(voice="flux-cole-en"))
```
- Flux STT requests its own `ExternalUserTurnStrategies`; a VAD is then optional (keep Silero for STT metrics).
  Encoding must be `linear16` (Pipecat sends PCM anyway). `model="flux-general-multi"` +
  `language_hints=[Language.EN, Language.ES]` for multilingual.
- Change settings live: `await worker.queue_frame(STTUpdateSettingsFrame(delta=DeepgramFluxSTTService.Settings(
  eot_threshold=0.9)))` sends Flux a `Configure` without reconnecting (keyterm, thresholds, language_hints).
- `DeepgramSTTService` (Nova): settings `model`, `language`, `diarize` (pushes one frame per speaker run;
  `speaker_format="{speaker}: {text}"`), `endpointing`, `interim_results` (default True), `keyterm`, `numerals`,
  `smart_format`, `utterance_end_ms`, `redact`. It sends Deepgram `Finalize` when the VAD hears the user stop.
  Changing a setting reconnects after the current user turn. After 3 failed reconnects it gives up.
- Aura `DeepgramTTSService` (WebSocket), `DeepgramHttpTTSService` (REST), `DeepgramFluxTTSService` (`/v2/speak`,
  token streaming, `speed` 0.5-1.5, `expressivity` -2..2, sample rates 8000-48000).

## 8. Key APIs, briefly

| Need | API |
|---|---|
| Speak without the LLM | `await worker.queue_frames([TTSSpeakFrame("Band connected.")])` |
| Kick the LLM | `context.add_message({...}); await worker.queue_frames([LLMRunFrame()])` |
| Add context and answer | `LLMMessagesAppendFrame([msg], run_llm=True)` pushed from a processor |
| End cleanly | `await worker.queue_frames([TTSSpeakFrame("Bye"), EndFrame()])` (processed in order) |
| Your own logic | subclass `FrameProcessor`; call `super().__init__()`, `await super().process_frame(frame, direction)`, and **always** `await self.push_frame(frame, direction)` |
| Read transcripts | a processor after `stt` checking `isinstance(frame, TranscriptionFrame)` -> `frame.text` |
| Play a sound | push `OutputAudioRawFrame(wav_bytes, rate, channels)` |
| Change STT/TTS settings live | `STTUpdateSettingsFrame(delta=...)`, `TTSUpdateSettingsFrame(delta=...)` |
| Tools from MCP servers | `LLMContext(tools=await MCPClient(server_params=...).tools())` |
| Frames to a band action | e.g. on `TranscriptionFrame` set a flag; act on the band (LED) only after `configure(audio=False)` |

## 9. Transports at a glance

| Transport | Install extra | When |
|---|---|---|
| SmallWebRTC (`SmallWebRTCTransport`) | `webrtc` (+`runner` for the built-in client) | Local dev and demo in a browser, no account, P2P (UDP; VPN/firewall can block it) |
| Daily (`DailyTransport`) | `daily` | Production WebRTC rooms; `DAILY_API_KEY`; default for Pipecat Cloud |
| Local audio (`LocalAudioTransport`) | `local` | Laptop mic/speaker; its output half is reused in section 6 |
| WebSocket server (`SingleClientWebsocketServerTransport`, default `localhost:8765`) | `websocket` | Your own client; **needs a `FrameSerializer`** (none = messages ignored); prototyping only |
| WebSocket client (`WebsocketClientTransport`) | `websocket` | Bot dials out to a WS server (Protobuf serializer by default) |
| FastAPI WebSocket | `websocket`/`runner` | Telephony (Twilio, Telnyx, Plivo, Exotel serializers) |

## 10. Pipecat Cloud

- Hosted runtime for Pipecat bots (Daily-hosted regions: US, Europe, India); bring a container image; transports
  Daily WebRTC, WebSocket, telephony. Sign up: https://pipecat.daily.co .
- Deploy: `uv tool install "pipecat-ai[cli]" --with pipecatcloud`, `pipecat cloud auth login`,
  `pipecat cloud secrets set <secret-set> --file .env`, `pipecat cloud deploy` (reads `pcc-deploy.toml` +
  Dockerfile; builds without your own registry). Test in the dashboard's **Sandbox**.
- Price: agent-1x (0.5 vCPU, 1 GB) $0.01/min active, $0.0005/min reserved; 2x $0.02; 3x $0.03. Daily WebRTC 1:1
  voice listed as free on Pipecat Cloud. No hackathon free tier found **(check with organisers)**.
- Not needed for the demo: the band's BLE link only works on the laptop, so a band bot runs locally. Cloud is for a
  phone/browser companion.

## 11. Gotchas

- **Old API names**: `PipelineTask`, `PipelineRunner`, `pipecat.pipeline.task`, `runner.run(task)`,
  `transport.input()` VAD params, `live_options=` / `params=` on Deepgram services (deprecated since 0.0.105, removed
  in 2.0.0). Use `PipelineWorker`, `WorkerRunner`, `settings=Service.Settings(...)`, VAD in
  `LLMUserAggregatorParams(vad_analyzer=...)`. Check with the Context Hub's `check_deprecation`.
- **Python 3.11+ only**; the kit itself works on 3.9+, but Pipecat does not.
- **Always push frames** in custom processors, or the pipeline silently stalls.
- **Opus is not PCM**: never put band packets into `InputAudioRawFrame` without decoding.
- **Echo/self-interruption** with the band mic and laptop speakers (section 6).
- **Mic on = LED locked** (kit rule 4): a tool that sets the LED while the band streams audio fails with `denied`.
- **Windows**: PowerShell env vars need quotes (`$env:DEEPGRAM_API_KEY = "..."`); `pipecat init` charmap error ->
  `PYTHONUTF8=1`; WebRTC needs UDP (event Wi-Fi may block: try a hotspot); first Silero load ~20 s.
- **One BLE connection**: close the kit dashboard before running the band bot (kit rule 7).
- **Keys**: `.env` in `.gitignore` before creating it; `pipecat cloud secrets set --file .env` uploads every line of it.

## 12. Links

- Docs: https://docs.pipecat.ai (index: https://docs.pipecat.ai/llms.txt ; append `.md` to a page for Markdown)
- Quickstart: https://docs.pipecat.ai/pipecat/get-started/quickstart ; install:
  https://docs.pipecat.ai/pipecat/get-started/introduction
- Pipeline & frames: https://docs.pipecat.ai/pipecat/learn/pipeline , https://docs.pipecat.ai/api-reference/server/frames/overview
- Custom processor: https://docs.pipecat.ai/pipecat/fundamentals/custom-frame-processor
- Transports: https://docs.pipecat.ai/pipecat/learn/transports ; SmallWebRTC:
  https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc ; WebSocket:
  https://docs.pipecat.ai/api-reference/server/services/transport/websocket-server
- Local audio source: https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/transports/local/audio.py
- Deepgram STT/TTS services: https://docs.pipecat.ai/api-reference/server/services/stt/deepgram ,
  https://docs.pipecat.ai/api-reference/server/services/tts/deepgram
- Examples: https://github.com/pipecat-ai/pipecat/tree/main/examples/voice (`voice-deepgram.py`,
  `voice-deepgram-flux.py`), https://github.com/pipecat-ai/pipecat-examples
- Dev runner: https://docs.pipecat.ai/api-reference/server/utilities/runner/guide
- Context Hub: https://docs.pipecat.ai/api-reference/context-hub ; CLI: https://docs.pipecat.ai/api-reference/cli/context-hub
- MCP client / transport: https://docs.pipecat.ai/api-reference/server/utilities/mcp/mcp ,
  https://docs.pipecat.ai/api-reference/server/services/transport/mcp ; https://github.com/pipecat-ai/pipecat-mcp-server
- Pipecat Cloud: https://docs.pipecat.ai/pipecat-cloud/introduction , https://www.daily.co/pricing/pipecat-cloud/
- Repo guide for agents (API concepts, 1.3.0 renames): https://github.com/pipecat-ai/pipecat/blob/main/AGENTS.md
- PyPI: https://pypi.org/project/pipecat-ai/
