# ElevenLabs: developer digest for VexoHacks (2026-11-14)

Track: **"Best Project Built with ElevenLabs"**. Prize: **3 months of the Scale plan per team member**
(Scale is $299/mo, 1.8M credits/month, 3 seats). Sponsor credits are provided for building.
Our stack: Windows 11, Python 3.12, browser JS, Vexo band (mic decoded by `vexo_open.audio` to **16 kHz mono 16-bit PCM**).
That is exactly the format ElevenLabs STT and the Agents Python SDK expect, so no resampling is needed.

All facts below come from elevenlabs.io (docs, pricing, MCP page, changelog), help.elevenlabs.io and github.com/elevenlabs, read on 2026-11-14.
Items marked **[UNVERIFIED]** are my inference and were not confirmed on a doc page.

---

## 0. TL;DR for the team

- **MCP (recommended):** hosted server `https://api.elevenlabs.io/v1/mcp`, HTTP transport, **OAuth** (no API key in the client).
  `claude mcp add --transport http elevenlabs https://api.elevenlabs.io/v1/mcp`, then run `/mcp` in a session to sign in.
  It can generate speech, sound, music, images and video, design voices, and create and manage Agents. Generations use your workspace credits.
- **MCP (local, legacy, API key):** PyPI package `elevenlabs-mcp`, run with `uvx elevenlabs-mcp`, env var `ELEVENLABS_API_KEY`.
- **Python SDK:** `pip install elevenlabs` (add `elevenlabs[pyaudio]` for mic/speaker in Agents). Env var: `ELEVENLABS_API_KEY`. Auth header: `xi-api-key`.
- **Models to use today:**
  - TTS, low latency: `eleven_flash_v2_5` (~100 ms, 32 languages, works on the TTS WebSocket).
  - TTS, best quality: `eleven_v4` (90+ languages; used in the official quickstart with `text_to_speech.convert`).
  - TTS, expressive and realtime: `eleven_v4_turbo` (~100 ms), streamed over the **Text to Dialogue** WebSocket.
  - STT: `scribe_v3` (files) and `scribe_v3_live` (realtime, turn prediction, diarization).
  - Sound effects: `eleven_text_to_sound_v3`. Music: `music_v2_5`. Voice design: `eleven_ttv_v3` or `eleven_multilingual_ttv_v2`.
  - Voice agents: ElevenAgents with `eleven_realtime_v1_mini` (default) or `eleven_realtime_v1_max`.
- **Best fit for the track:** an **ElevenAgents voice agent** that hears the band mic (custom `AudioInterface` at 16 kHz),
  with **client tools** that read band motion and taps and act on the band (LED, vibration). Add **sound effects** on gestures.
- **Free tier:** 10k credits/month, no commercial licence, 4 concurrent requests. Burn it carefully; sponsor credits should cover the rest.

---

## 1. MCP servers

### 1.1 Hosted ElevenLabs MCP (official, recommended)

| Item | Value |
|---|---|
| URL | `https://api.elevenlabs.io/v1/mcp` (global). US residency: `https://api.us.elevenlabs.io/v1/mcp`. EU, India and Singapore residency URLs exist too. |
| Transport | Remote HTTP (streamable HTTP) |
| Auth | **OAuth**, one time per client. You sign in, choose a workspace, approve scopes. Access is revocable. No client registration needed for clients with CIMD support. |
| Claude Code install | `claude mcp add --transport http elevenlabs https://api.elevenlabs.io/v1/mcp` then `/mcp` inside a session to complete OAuth |
| Scope (add for all projects) | `claude mcp add --transport http --scope user elevenlabs https://api.elevenlabs.io/v1/mcp` **[UNVERIFIED: standard Claude Code flag, not shown on the ElevenLabs page]** |
| Capabilities | Agents: create, update prompts/voices/tools, list, read transcripts and metrics, tests, branches, knowledge base. Creative: speech, music, images, video, sound effects, voice design, Flows. |
| Billing | Generations use the credits of the workspace you sign in to |

Notes:
- The ElevenLabs connector in the **Claude connector directory** is a **restricted** version (speech, voices, transcription, agents; no images, video or music).
  The custom URL above gives every tool. This Claude Code session already has an ElevenLabs connector attached that looks like the restricted one.
- Companion CLI and skills (optional): `npm i -g @elevenlabs/cli`, `elevenlabs auth login`, `npx skills add elevenlabs/skills`.
- The hosted server also returns TTS as a short-lived download link. Useful for generating demo assets from Claude Code.

### 1.2 Local open-source server `elevenlabs-mcp` (official repo, older)

| Item | Value |
|---|---|
| Package | PyPI `elevenlabs-mcp` (GitHub `elevenlabs/elevenlabs-mcp`) |
| Transport | stdio (local process) |
| Auth | API key in env var `ELEVENLABS_API_KEY` |
| Run | `uvx elevenlabs-mcp` (needs `uv`), or `pip install elevenlabs-mcp` then `python -m elevenlabs_mcp --api-key=... --print` to print a client config |
| Options | `ELEVENLABS_MCP_BASE_PATH` (default `~/Desktop`, also the allowed folder for input files), `ELEVENLABS_MCP_OUTPUT_MODE` = `files` / `resources` / `both` |
| Claude Code install | `claude mcp add elevenlabs-local -e ELEVENLABS_API_KEY=YOUR_KEY -- uvx elevenlabs-mcp` **[UNVERIFIED: built from the README's Claude Desktop config; the README shows no `claude mcp add` line]** |

ElevenLabs says the local server "runs locally and requires an API key, built for developers", while the hosted one needs nothing installed.
Prefer the hosted one. Windows tip from the README: if you get `spawn uvx ENOENT`, use the full path to `uvx.exe`.

---

## 2. Models (from the Models page)

| Model ID | Use | Latency | Languages | Max chars / request |
|---|---|---|---|---|
| `eleven_v4` | Highest quality, most expressive TTS; voice cloning | n/a | 90+ | 10,000 |
| `eleven_v4_turbo` | Expressive realtime TTS (agents, assistants, characters) | ~100 ms | 90+ | not stated |
| `eleven_v3` | Previous expressive model | n/a | 70+ | 5,000 |
| `eleven_v3_conversational` | Expressive realtime | ~165 ms | 70+ | not stated |
| `eleven_multilingual_v2` | Stable, lifelike; API default `model_id` for TTS | higher than Flash | 29 | 10,000 |
| `eleven_flash_v2_5` | Ultra-fast realtime TTS | ~100 ms | 32 | 40,000 |
| `eleven_flash_v2` | Ultra-fast, English only | ~135 ms | en | 30,000 |
| `scribe_v3` | Batch speech-to-text | n/a | 90+ | n/a |
| `scribe_v3_live` | Realtime STT with turn prediction and diarization | n/a | 90+ | n/a |
| `scribe_v2_realtime` | Older realtime STT (~150 ms to committed text) | ~150 ms | 90+ | n/a |
| `eleven_text_to_sound_v3` | Sound effects | n/a | n/a | n/a |
| `music_v2_5` | Music generation | n/a | en, es, de, ja, ... | n/a |
| `eleven_ttv_v3`, `eleven_multilingual_ttv_v2` | Voice design (text to voice) | n/a | 70+ / 29 | n/a |
| `eleven_multilingual_sts_v2` | Voice changer (speech to speech) | n/a | 29 | n/a |
| `eleven_realtime_v1_mini` / `_max` | Complete voice agent models (STT + turn taking + LLM + TTS) | n/a | 90+ | n/a |

Latency figures are medians that exclude app and network time.
Deprecated: `eleven_turbo_v2_5` and `eleven_turbo_v2` (use Flash), `scribe_v1`, `music_v1` (removed 2027-01-31),
`eleven_text_to_sound_v2` (removed 2027-03-01).

Which endpoint takes which model:
- `POST /v1/text-to-speech/{voice_id}` (convert / stream): all TTS models. The quickstart uses `eleven_v4` here.
- TTS WebSocket `/v1/text-to-speech/{voice_id}/stream-input`: **not** `eleven_v3` or `eleven_v4`. Use Flash or Multilingual v2.
- Text to Dialogue WebSocket `/v1/text-to-dialogue/stream-input`: only models starting with `eleven_v3` or `eleven_v4` (for example `eleven_v4_turbo`).

---

## 3. Setup and auth

```powershell
pip install elevenlabs python-dotenv websockets
pip install "elevenlabs[pyaudio]"     # only for DefaultAudioInterface (laptop mic and speaker)
setx ELEVENLABS_API_KEY "...your key..."   # new terminals only; never commit the key
```

- Create keys at https://elevenlabs.io/app/settings/api-keys. Keys can be scoped (for example a key with only Text to Speech permission).
- REST and WebSocket auth header: `xi-api-key: <key>`. Some WebSockets also accept `xi_api_key` in the first JSON message.
- Browsers: never ship the key. Use a **signed URL** (Agents) or a **single-use token** (realtime STT) minted by your Python server.
- `play()` from `elevenlabs.play` needs **mpv** and/or **ffmpeg** installed (on Windows, put them on PATH). Saving to a file avoids this.

---

## 4. Text to speech

### 4.1 Convert (one request, full audio)

```python
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()
elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

audio = elevenlabs.text_to_speech.convert(
    text="Nice pace! Two more minutes.",
    voice_id="JBFqnCBsd6RMkjVDRZzb",      # "George", used in the official quickstart
    model_id="eleven_flash_v2_5",          # or "eleven_v4" for best quality
    output_format="mp3_44100_128",
)
with open("coach.mp3", "wb") as f:
    for chunk in audio:                    # the SDK returns an iterator of bytes
        f.write(chunk)
```

- Other voice IDs seen in official examples: `pNInz6obpgDQGcFmaJgB` (Adam), `21m00Tcm4TlvDq8ikWAM`, `Xb7hH8MSUJpSbSDYk0k2`. Browse more in the Voice Library.
- `voice_settings=VoiceSettings(stability=..., similarity_boost=..., style=..., use_speaker_boost=True, speed=1.0)` (import from `elevenlabs`).
- Other body params: `language_code`, `seed`, `previous_text` / `next_text` (smoother joins across chunks).
- Output formats look like `codec_samplerate_bitrate`: `mp3_22050_32`, `mp3_44100_128`, `pcm_16000`, `pcm_24000`, `ulaw_8000`, and so on.
  `mp3_44100_192` needs Creator or above. PCM/WAV at 44.1 kHz needs Pro or above.
- `optimize_streaming_latency` is deprecated. Pick a Flash model instead.

### 4.2 HTTP streaming (start playing before generation ends)

```python
stream = elevenlabs.text_to_speech.stream(
    text="Heads up, your heart rate is climbing.",
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    model_id="eleven_flash_v2_5",
    output_format="pcm_16000",             # raw PCM is easy to play with sounddevice / pyaudio
)
for chunk in stream:
    if chunk:
        pass                               # write to the audio device as chunks arrive
```

### 4.3 WebSocket input streaming (LLM tokens in, audio out)

Endpoint: `wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id=eleven_flash_v2_5`

```python
import asyncio, base64, json, os, websockets

VOICE = "JBFqnCBsd6RMkjVDRZzb"
URI = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE}/stream-input?model_id=eleven_flash_v2_5"

async def speak(text_parts):
    async with websockets.connect(URI) as ws:
        await ws.send(json.dumps({                     # first message: settings and key
            "text": " ",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            "generation_config": {"chunk_length_schedule": [50, 120, 160, 290]},
            "xi_api_key": os.environ["ELEVENLABS_API_KEY"],
        }))
        for part in text_parts:                        # e.g. deltas from an LLM stream
            await ws.send(json.dumps({"text": part}))
        await ws.send(json.dumps({"text": ""}))        # empty text = end of input
        audio = bytearray()
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("audio"):
                audio += base64.b64decode(msg["audio"])
            if msg.get("isFinal"):
                break
        return bytes(audio)                            # MP3 by default

asyncio.run(speak(["Great job. ", "Take a sip of water ", "before the next set."]))
```

`chunk_length_schedule` sets how many characters are buffered before each audio chunk. Smaller first values give faster first audio and slightly lower quality.

### 4.4 Eleven v4 Turbo over the Text to Dialogue WebSocket

`wss://api.elevenlabs.io/v1/text-to-dialogue/stream-input?model_id=eleven_v4_turbo&output_format=mp3_44100_128`.
First message: `{"voices": [VOICE_ID], "xi_api_key": KEY}` (v4 Turbo allows exactly one voice; `eleven_v4` up to 10).
Then send `{"inputs": [{"text": "...", "voice_id": VOICE_ID, "new_turn": false}]}` frames. Finish with `{"close_socket": true}`.
Responses use snake_case (`audio`, `is_final`). The server waits for about 40 characters and 8 words before the first audio; send `{"flush": true}` to force it.
The socket closes after 20 s with no client message; send `{"keep_alive": true}` to keep it open.

---

## 5. Speech to text (Scribe)

### 5.1 Batch: the band recording

```python
from elevenlabs.client import ElevenLabs

elevenlabs = ElevenLabs()                     # reads ELEVENLABS_API_KEY
with open("recording.wav", "rb") as f:
    result = elevenlabs.speech_to_text.convert(
        file=f,
        model_id="scribe_v3",
        tag_audio_events=True,                # (laughter), (applause), ...
        language_code=None,                   # None = auto-detect; e.g. "eng"
        diarize=True,                         # who is speaking
    )
print(result.text)
```

Limits: up to 5 GB and 15 hours per file. Formats include wav, mp3, ogg, opus, flac, m4a, webm and common video containers.
Billing counts silence. Keyterm prompting (up to 1,000 terms in batch) costs extra.

### 5.2 Realtime: stream the band mic

Endpoint: `wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v3_live&audio_format=pcm_16000`
(add `&diarize=true`, `&commit_strategy=vad` or `turn_prediction`, `&language_code=...`, `&keyterms=...` as needed).

```python
import asyncio, base64, json, os
from websockets.asyncio.client import connect

URL = ("wss://api.elevenlabs.io/v1/speech-to-text/realtime"
       "?model_id=scribe_v3_live&audio_format=pcm_16000&commit_strategy=vad")

async def transcribe(pcm_chunks):             # iterable of 16 kHz s16 mono bytes from the band
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    async with connect(URL, additional_headers=headers) as ws:
        async def sender():
            for chunk in pcm_chunks:
                await ws.send(json.dumps({
                    "message_type": "input_audio_chunk",
                    "audio_base_64": base64.b64encode(chunk).decode(),
                    "commit": False,
                    "sample_rate": 16000,
                }))
                await asyncio.sleep(0.02)     # pace roughly like live audio
        async def receiver():
            async for raw in ws:
                ev = json.loads(raw)
                if ev.get("message_type") == "partial_transcript":
                    print("...", ev.get("text"))
                elif ev.get("message_type") == "committed_transcript":
                    print("FINAL:", ev.get("text"))
        await asyncio.gather(sender(), receiver())
```

- Commit strategies: `manual` (send `"commit": true` yourself, for example on a band tap release), `vad`, `turn_prediction`.
- Server messages: `session_started`, `partial_transcript`, `committed_transcript`, plus diarization and many `scribe*Error` types (quota, throttled, chunk too large, ...).
- The Python SDK has a wrapper: `await elevenlabs.speech_to_text.realtime.connect(RealtimeAudioOptions(model_id=..., audio_format=AudioFormat.PCM_16000, sample_rate=16000, commit_strategy=CommitStrategy.MANUAL))`
  with handlers on `RealtimeEvents.PARTIAL_TRANSCRIPT` / `COMMITTED_TRANSCRIPT`. The official examples still use `scribe_v2_realtime`.
- Browser clients use a single-use `token` query parameter instead of the API key.
- The `receiver` loop above never ends on its own; cancel it when the sender finishes. **[sketch, not run]**

---

## 6. ElevenAgents (conversational voice agents)

What it is: a hosted voice agent (STT + turn taking + LLM + TTS + tools + knowledge base). You configure it in the dashboard
(https://elevenlabs.io/app/agents) or with the API, then talk to it from Python, JS, a widget, a phone number or a raw WebSocket.

### 6.1 Talk to an agent from Python with the band as the microphone

`AudioInterface` contract (from the SDK source): input is **16-bit PCM mono at 16 kHz**, recommended chunk 4000 samples (250 ms);
`output(audio)` gets 16 kHz PCM too and must not block; `interrupt()` must drop buffered output.

```python
import os, signal, queue, threading
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, AudioInterface, ClientTools

class BandAudio(AudioInterface):
    """Feed band mic PCM to the agent; play replies on the laptop."""
    def __init__(self, band_pcm_source, speaker):
        self.source, self.speaker, self.q = band_pcm_source, speaker, queue.Queue()
    def start(self, input_callback):
        def pump():
            for chunk in self.source():            # yields 16 kHz s16 mono bytes (8000 bytes = 250 ms)
                input_callback(chunk)
        threading.Thread(target=pump, daemon=True).start()
    def output(self, audio: bytes):
        self.speaker.write(audio)                  # must return quickly (buffer in your player)
    def interrupt(self):
        self.speaker.clear()
    def stop(self):
        pass

tools = ClientTools()
tools.register("setBandLight", lambda params: f"light set to {params.get('color')}")
tools.register("getActivity", lambda params: {"steps": 4200, "state": "walking"})

elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
conversation = Conversation(
    elevenlabs,
    os.environ["AGENT_ID"],
    requires_auth=True,                            # False for a public agent
    audio_interface=BandAudio(band_pcm_source=..., speaker=...),
    client_tools=tools,
    callback_agent_response=lambda r: print("Agent:", r),
    callback_user_transcript=lambda t: print("User:", t),
)
conversation.start_session()
signal.signal(signal.SIGINT, lambda *_: conversation.end_session())
print("Conversation ID:", conversation.wait_for_session_end())
```

- Quick test without the band: `from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface` (needs `elevenlabs[pyaudio]`).
- Client tools must also be defined on the agent (dashboard Tools tab, type **Client**, same case-sensitive name and parameters).
  Tick **Wait for response** if the agent should use the returned value.
- Other `Conversation` methods: `send_user_message`, `send_contextual_update` (push band events such as "user just double-tapped"
  without interrupting), `register_user_activity`, `send_multimodal_message`. An `AsyncConversation` class also exists.
- `ConversationInitiationData(dynamic_variables={...})` passes per-session variables (for example the wearer's name).
- The `speaker` object above is a placeholder. Use `sounddevice` or `pyaudio` at 16 kHz. **[sketch, not run]**

### 6.2 Create or update an agent from code

```python
from elevenlabs import ElevenLabs

elevenlabs = ElevenLabs()
agent = elevenlabs.conversational_ai.agents.create(
    name="Band coach",
    conversation_config={
        "agent": {
            "first_message": "Hey! Tap twice when you want me.",
            "prompt": {"prompt": "You are a fitness coach living in a wristband. Keep answers to one sentence."},
        },
        "tts": {"voice_id": "JBFqnCBsd6RMkjVDRZzb"},
    },
)
print(agent.agent_id)

# switch to the new all-in-one realtime model (documented example)
elevenlabs.conversational_ai.agents.update(
    agent_id=agent.agent_id,
    conversation_config={"realtime_model": "eleven_realtime_v1_mini"},
)
```

The `conversation_config` keys for `first_message`, `prompt` and `tts.voice_id` follow the SDK's `ConversationalConfig` / `AgentConfig`
types, but I did not read a page showing this exact dict. **[UNVERIFIED shape; dashboard setup is the safe path]**
The `realtime_model` update and `tool_ids` / `mcp_server_ids` under `agent.prompt` are from official examples.
Eleven Realtime models are "rolling out gradually across workspaces" (changelog, 2026-10-19). Mini is not available under Zero Retention Mode or HIPAA.

### 6.3 Tools for agents

- **Client tools**: run in your Python or JS client (section 6.1). Best for band actions.
- **Server (webhook) tools**: the agent calls your HTTPS endpoint. Needs a public URL (for example a tunnel).
- **MCP servers**: attach SSE or streamable-HTTP MCP servers to an agent. MCP is off by default per workspace; enable it once with
  `elevenlabs.conversational_ai.settings.update(can_use_mcp_servers=True)` or by accepting the MCP terms in the dashboard.
- **System tools**: end call, language detection, transfer to agent or number, skip turn, voicemail detection.

### 6.4 Browser: raw WebSocket or the JS SDK

- Public agent: `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=<AGENT_ID>`.
- Private agent: your server calls `elevenlabs.conversational_ai.conversations.get_signed_url(agent_id=...)` and hands `signed_url` to the browser.
- Client to server events: `user_audio_chunk`, `pong`, `conversation_initiation_client_data`, `contextual_update`, `user_message`, `client_tool_result`.
  Server to client events: `audio`, `agent_response`, `user_transcript`, `interruption`, `ping`, `client_tool_call`, `agent_response_correction`.
  Answer every `ping` with a `pong` or the server drops you. **[UNVERIFIED: standard behaviour, not re-read today]**
- JS packages: `@elevenlabs/client` (browser Conversation API with `clientTools`) and `@elevenlabs/elevenlabs-js` (Node/server SDK).

### 6.5 OpenAI-compatible Realtime API (new)

ElevenLabs Realtime speaks the OpenAI Realtime wire protocol over **WebSocket only** (no WebRTC yet):
`wss://api.elevenlabs.io/v1/convai/realtime`, models `eleven_realtime_v1_mini` / `eleven_realtime_v1_max`.
Mint a short-lived secret with `POST /v1/convai/realtime/client_secrets` (returns `value`, `expires_at`; session `max_duration_seconds` 60 to 7,200, default 600).
Audio is PCM16 at 24 kHz. Existing OpenAI Realtime code can switch by changing the URL and model. It runs separately from ElevenAgents
(no knowledge base or channels).

---

## 7. Sound effects, voice design, music

### 7.1 Sound effects (gesture -> sound)

```python
audio = elevenlabs.text_to_sound_effects.convert(
    text="Short bright success chime",
    model_id="eleven_text_to_sound_v3",   # set it: the API default is still the deprecated v2
    duration_seconds=1.5,                  # 0.5 to 30; omit to let the model choose
    prompt_influence=0.5,                  # 0 to 1, default 0.3
    loop=False,
    output_format="mp3_44100_128",
)
with open("chime.mp3", "wb") as f:
    for chunk in audio:
        f.write(chunk)
```

Generate the gesture sounds once before the demo and cache the files. About 200 credits per generation.

### 7.2 Voice design (a custom voice for the band persona)

```python
import base64
previews = elevenlabs.text_to_voice.design(
    model_id="eleven_multilingual_ttv_v2",           # or "eleven_ttv_v3"
    voice_description="A calm, warm coach with a slight smile in the voice.",
    text="Nice work. Breathe in, and let's go again when you're ready.",
)
for p in previews.previews:
    open(f"{p.generated_voice_id}.mp3", "wb").write(base64.b64decode(p.audio_base_64))

voice = elevenlabs.text_to_voice.create(
    voice_name="Band coach",
    voice_description="A calm, warm coach with a slight smile in the voice.",
    generated_voice_id=previews.previews[0].generated_voice_id,
)
print(voice.voice_id)                                # use it in TTS and in your agent
```

The preview audio format (MP3 or other) was not stated on the page. **[UNVERIFIED file extension]**

### 7.3 Music

`music_v2_5` generates tracks from text prompts or composition plans (about 900 credits per minute). It is useful for a demo soundtrack,
less so for the wearable loop.

---

## 8. Pricing, credits and limits

| Plan | Price | Credits / month | Notes |
|---|---|---|---|
| Free | $0 | 10k | No commercial licence; 128 kbps 44.1 kHz; 4 concurrent requests |
| Starter | $6 (first month $1) | 30k | Commercial licence, instant voice cloning; 6 concurrent |
| Creator | $22 (first month $11) | 121k | Professional voice cloning, 192 kbps; 10 concurrent |
| Pro | $99 | 600k | 44.1 kHz PCM over the API; 20 concurrent |
| Scale | $299 | 1.8M | 3 seats, 3 professional clones; 30 concurrent |
| Business | $990 | 6M | 10 seats; 40 concurrent |

Credit costs (pricing page FAQ): TTS about 1 credit per character (Flash and Turbo 0.5 credits on self-serve plans),
STT about 330 credits/minute, sound effects about 200 credits per generation, music about 900 credits/minute,
voice changer and isolator about 1,000 credits/minute.

Pay-as-you-go API prices: TTS $0.04 per 1K characters (Flash, v4 Turbo, v3 Conversational) or $0.08 (v4, v3, Multilingual v2);
STT $0.20/hour (Scribe v3) or $0.22/hour (Scribe v3 Live); agents about $0.08/minute plus LLM tokens; sound effects $0.12/minute; music $0.15/minute.

Rough budget on the free tier: 10k credits is about 20k characters of Flash TTS, or about 30 minutes of STT, or about 50 sound effects.

---

## 9. Fit for this hackathon

- **Hero demo (track winner material):** "talk to your wristband". Double tap starts an ElevenAgents session, band mic streams in at 16 kHz,
  the agent answers in a designed voice, and client tools read motion state and control the band LED or vibration.
- **Coach mode:** motion events become `send_contextual_update("user started running, 160 spm")`. The agent comments without being asked.
- **Sound UI:** each gesture plays a pre-generated `eleven_text_to_sound_v3` sound. Cheap and very visible in a demo.
- **Hybrid with OpenAI:** OpenAI model does the reasoning (or plug it into ElevenAgents as a custom LLM), ElevenLabs does voice and STT.
  The ElevenLabs Speech Engine SDK also accepts streamed OpenAI Responses output directly (`session.send_response(stream)`).
- **Live captions:** `scribe_v3_live` with `diarize=true` to caption conversations around the wearer.

---

## 10. Gotchas

- **Model and endpoint mismatch:** the TTS WebSocket rejects `eleven_v3` and `eleven_v4`. Use Flash there, or the Text to Dialogue WebSocket for v3/v4.
- **Defaults are stale:** TTS defaults to `eleven_multilingual_v2` and sound effects to the deprecated `eleven_text_to_sound_v2`. Always pass `model_id`.
- **Sample rates:** Agents SDK audio and `pcm_16000` STT match the band (16 kHz). The ElevenLabs Realtime API (OpenAI compatible) wants 24 kHz.
- **`play()` on Windows** needs mpv or ffmpeg on PATH. Write to a file or use `sounddevice` instead.
- **Concurrency:** the free tier allows 4 concurrent requests. An open agent conversation plus parallel TTS and STT can hit it.
- **Agents client tools** are case-sensitive and must exist in the agent config as well as in code.
- **MCP for agents** is disabled per workspace until someone accepts the MCP terms.
- **Silence is billed** in STT. Stop streaming when the band mic is idle.
- **Free tier** has no commercial licence (pricing page). Fine for a hackathon demo; check terms before shipping anything.
- **Keys:** never put `ELEVENLABS_API_KEY` in `dashboard.html`. Use signed URLs or single-use tokens.

---

## 11. Sources (read 2026-11-14)

- Hosted MCP landing page: https://elevenlabs.io/mcp
- MCP server docs: https://elevenlabs.io/docs/eleven-api/resources/mcp-server
- Hosted MCP for agents: https://elevenlabs.io/docs/eleven-agents/operate/hosted-mcp
- MCP in external assistants: https://elevenlabs.io/docs/eleven-agents/operate/architect/external-assistants
- llms.txt (MCP endpoints summary): https://elevenlabs.io/llms.txt
- Local MCP repo: https://github.com/elevenlabs/elevenlabs-mcp (PyPI: https://pypi.org/project/elevenlabs-mcp)
- Models: https://elevenlabs.io/docs/overview/models
- API quickstart: https://elevenlabs.io/docs/eleven-api/quickstart
- TTS convert reference: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- Streaming TTS: https://elevenlabs.io/docs/eleven-api/guides/how-to/text-to-speech/streaming
- TTS WebSocket: https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/realtime-tts
- Text to Dialogue WebSocket: https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/realtime-tdd
- STT quickstart: https://elevenlabs.io/docs/eleven-api/guides/cookbooks/speech-to-text
- STT capability and limits: https://elevenlabs.io/docs/overview/capabilities/speech-to-text
- Realtime STT (server side): https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/server-side-streaming
- Realtime STT diarization: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/diarization
- Realtime STT reference: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
- Agents Python SDK: https://elevenlabs.io/docs/eleven-agents/libraries/python
- SDK source (AudioInterface, Conversation): https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/conversational_ai/conversation.py
- Client tools: https://elevenlabs.io/docs/eleven-agents/customization/tools/client-tools
- Agent MCP tools: https://elevenlabs.io/docs/eleven-agents/customization/tools/mcp
- Agent authentication (signed URLs): https://elevenlabs.io/docs/eleven-agents/customization/authentication
- Agents WebSocket: https://elevenlabs.io/docs/eleven-agents/libraries/web-sockets
- Realtime models: https://elevenlabs.io/docs/eleven-agents/customization/realtime-models
- OpenAI Realtime compatibility: https://elevenlabs.io/docs/eleven-agents/guides/openai-realtime-compatibility
- Changelog 2026-10-19: https://elevenlabs.io/docs/changelog/2026/10/19
- Speech Engine Python SDK: https://elevenlabs.io/docs/eleven-api/resources/libraries/speech-engine/python-sdk-reference
- Sound effects quickstart: https://elevenlabs.io/docs/eleven-api/guides/cookbooks/sound-effects
- Sound effects reference: https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert
- Voice design quickstart: https://elevenlabs.io/docs/eleven-api/guides/cookbooks/voices/voice-design
- Pricing: https://elevenlabs.io/pricing and https://elevenlabs.io/pricing/api
- Credits explainer: https://help.elevenlabs.io/hc/en-us/articles/27562020846481-What-are-credits
