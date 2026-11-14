# OpenAI: developer digest for VexoHacks (2026-11-14)

Perk: **$50 OpenAI API credits per participant**; overall prizes are paid in OpenAI credits.
Our stack: Windows 11, Python 3.12, browser JS, Vexo band (motion, taps, mic audio as 16 kHz mono 16-bit PCM after `vexo_open.audio.decode_packets`).

All facts below come from developers.openai.com, openai.com and openai.github.io (Agents SDK), read on 2026-11-14.
Items marked **[UNVERIFIED]** are my inference and were not confirmed on a doc page.

---

## 0. TL;DR for the team

- **MCP:** OpenAI hosts a public, documentation-only Docs MCP at `https://developers.openai.com/mcp` (streamable HTTP, no auth).
  `claude mcp add --transport http openaiDeveloperDocs https://developers.openai.com/mcp`
  It searches and reads OpenAI docs; it does **not** call the API for you. There is no official MCP that runs OpenAI API calls from Claude Code.
- **Model IDs changed a lot this year.** Current flagships: `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-luna`.
  `gpt-4o`, `gpt-4.1`, `o3`, `gpt-5`, `gpt-5-mini`, `whisper-1`, `tts-1` and `gpt-4o-mini-tts` are all marked **Deprecated**.
- **Cheapest useful brain for a wearable:** `gpt-6-luna` ($0.10 in / $0.50 out per 1M tokens, supports `effort: none`). $50 goes very far.
- **Voice agent (speech to speech):** Realtime API with `gpt-realtime-2.1` (or `gpt-realtime-2.1-mini` to save credits).
  Browser: WebRTC with an ephemeral key. Python on the laptop: WebSocket with the normal API key.
- **Speech to text from the band:** `gpt-transcribe` for files ($0.0045/min), `gpt-live-transcribe` for live streams ($0.017/min).
- **Text to speech:** `/v1/audio/speech` models are all deprecated (shutdown **2027-01-06**) but still work today.
  OpenAI's migration target is `gpt-realtime-2.1-mini` through the Realtime API. For the ElevenLabs track, use ElevenLabs TTS instead.
- **Fastest demo:** band tap -> record 5 s -> `gpt-transcribe` -> `gpt-6-luna` with function calling -> speak the answer.

---

## 1. MCP servers

| Item | Value |
|---|---|
| Official server | OpenAI Docs MCP, `https://developers.openai.com/mcp` |
| Covers | Docs on developers.openai.com, platform.openai.com and learn.chatgpt.com (search + read pages) |
| Transport | Streamable HTTP (`--transport http`) |
| Auth | None. OpenAI's Agents API guide says the docs MCP "allows anonymous access". |
| Claude Code (project scope) | `claude mcp add --transport http openaiDeveloperDocs https://developers.openai.com/mcp` |
| Claude Code (all projects) | `claude mcp add --transport http --scope user openaiDeveloperDocs https://developers.openai.com/mcp` |
| Verify | `claude mcp list`, then `/mcp` inside a session |
| Limitation | Documentation only: "It does not call the OpenAI API on your behalf." |

Other official option: the **OpenAI Developers plugin** for Claude Code. It bundles the same Docs MCP plus portable skills
(API key setup, Agents SDK, troubleshooting). Inside Claude Code:

```text
/plugin marketplace add openai/openai-developers-for-claude
/plugin install openai-developers@openai-developers
```

Then start a new session. The Codex-only "OpenAI API Platform" connector is **not** included in the Claude Code version.
I found no other official OpenAI MCP server for Claude Code.

---

## 2. Models (from the Models and All models pages)

### Text / reasoning (Responses API)

| Model ID | Role | Input / Output per 1M tokens | Context | Reasoning efforts |
|---|---|---|---|---|
| `gpt-6-astra` | Most capable, "if you're not sure where to start" | $10 / $50 (cached input $1) | 1.05M, 128K max output | low ... max |
| `gpt-6.1-sol` | Near-Astra quality, cheaper | $2 / $10 (cached $0.10) | 1.05M, 128K out | low ... max |
| `gpt-6.1-terra` | Fast: visual reasoning, computer use, writing | $1 / $5 (cached $0.05) | 1.05M, 128K out | none ... max |
| `gpt-6-luna` | Most efficient, high-volume | $0.10 / $0.50 (cached $0.01) | 1.05M, 128K out | none ... max |

All four support functions, web search, file search and computer use, plus text and image input.
Long-context requests cost more (for example Luna $0.20 / $0.75). The exact threshold where "long context" starts was not on the page I read. **[UNVERIFIED threshold]**
Older but still listed (not deprecated): `gpt-6-sol`, `gpt-5.6-sol/terra/luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.2`.
Open-weight: `gpt-oss-120b`, `gpt-oss-20b`. Embeddings: `text-embedding-3-small`, `text-embedding-3-large`.

Budget sanity check: $50 on `gpt-6-luna` is about 100M input tokens or 100M output tokens. With `gpt-6-astra` it is 5M input tokens. Use Luna or Terra for the live loop.

### Realtime and audio

| Model ID | What it does | Price |
|---|---|---|
| `gpt-realtime-2.1` | Speech-to-speech voice agent with reasoning and tools (recommended Realtime model) | audio $32 in / $64 out per 1M; text $4 / $24 |
| `gpt-realtime-2.1-mini` | Cheaper Realtime model, also OpenAI's TTS migration target | audio $10 / $20 per 1M; text $0.60 / $2.40 |
| `gpt-live-1` | GPT-Live: full-duplex voice front end that delegates work to a backend model | $0.05/min, billed per second, plus backend tokens |
| `gpt-transcribe` | File transcription (and Realtime input transcription) | $0.0045/min |
| `gpt-live-transcribe` | Low-latency streaming speech-to-text | $0.017/min |
| `gpt-realtime-whisper` | Streaming speech-to-text | $0.017/min |
| `gpt-realtime-translate` | Streaming speech-to-speech translation | not read |
| `gpt-audio-1.5` | Audio in/out through Chat Completions | not read |

Deprecated (avoid for new code): `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe-diarize`
(shutdown 2027-02-26); `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts` (shutdown 2027-01-06); `gpt-realtime`, `gpt-realtime-mini`.
Image models: the All models page lists `GPT-Image-2.6 Sunburst/Flare` and `2.5 Sunburst/Flare`; I did not read their API IDs. **[UNVERIFIED IDs]**

---

## 3. Setup and auth

```powershell
pip install openai openai-agents websockets numpy
setx OPENAI_API_KEY "sk-...your key..."   # then open a NEW terminal; never commit the key
```

- The SDK reads `OPENAI_API_KEY` automatically: `OpenAI()` needs no arguments.
- Browsers must never see the real key. For browser voice, mint an **ephemeral client secret** on a Python server (section 6.2).
- Optional: send a hashed user ID as `safety_identifier` (Responses) or the `OpenAI-Safety-Identifier` header (Realtime).

---

## 4. Responses API (text, images, tools)

### 4.1 Hello world

```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="gpt-6-luna",
    input="In one sentence: what could a wristband with a mic and motion sensor help with?",
)
print(response.output_text)
```

Reasoning effort is set with `reasoning={"effort": "none"}` (Luna and Terra accept `none`; Astra and Sol start at `low`).
The effort values come from the Models page; the `reasoning={"effort": ...}` parameter shape is the long-standing Responses API form. **[parameter shape not re-read today]**

### 4.2 Streaming

```python
stream = client.responses.create(model="gpt-6-luna", input="Count to five.", stream=True)
for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
```

### 4.3 Image input (for example a webcam frame)

```python
response = client.responses.create(
    model="gpt-6.1-terra",
    input=[{"role": "user", "content": [
        {"type": "input_text", "text": "What is the user holding?"},
        {"type": "input_image", "image_url": "https://example.com/frame.jpg"},  # or a data: URL
    ]}],
)
print(response.output_text)
```

### 4.4 Function calling (band events -> actions)

Pattern from the official guide: define tools, run the call, append `function_call_output` items with the same `call_id`, call again.

```python
import json
from openai import OpenAI

client = OpenAI()
tools = [{
    "type": "function",
    "name": "set_band_light",
    "description": "Change the wristband LED colour to signal the user.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {"color": {"type": "string", "enum": ["red", "green", "blue", "off"]}},
        "required": ["color"],
        "additionalProperties": False,
    },
}]

def set_band_light(color):
    print("LED ->", color)          # call the Vexo kit here
    return "ok"

items = [{"role": "user", "content": "I just finished my workout, celebrate!"}]
response = client.responses.create(model="gpt-6-luna", tools=tools, input=items)
items += response.output
for item in response.output:
    if item.type == "function_call" and item.name == "set_band_light":
        args = json.loads(item.arguments)
        items.append({"type": "function_call_output", "call_id": item.call_id,
                      "output": set_band_light(**args)})

response = client.responses.create(model="gpt-6-luna", tools=tools, input=items)
print(response.output_text)
```

Hosted tools are added the same way, for example `tools=[{"type": "web_search"}]` ($10 per 1k calls plus content tokens).

### 4.5 Structured outputs (classify a gesture or a spoken command)

```python
from pydantic import BaseModel
from openai import OpenAI

class Intent(BaseModel):
    action: str          # e.g. "start_timer"
    minutes: int | None
    confidence: float

client = OpenAI()
response = client.responses.parse(
    model="gpt-6-luna",
    input=[{"role": "system", "content": "Turn the user's words into an intent."},
           {"role": "user", "content": "set a timer for ten minutes"}],
    text_format=Intent,
)
print(response.output_parsed)
```

Rules for strict JSON schemas: every object needs `additionalProperties: false`, and every field must be listed in `required`.
Make a field optional with a union that includes `null` (Pydantic `int | None` does this).
Raw form: `text={"format": {"type": "json_schema", "name": "...", "schema": {...}, "strict": True}}`.

---

## 5. Speech to text from the band

### 5.1 File transcription (after `record_band.py` writes `recording.wav`)

```python
from openai import OpenAI

client = OpenAI()
with open("recording.wav", "rb") as f:
    t = client.audio.transcriptions.create(model="gpt-transcribe", file=f)
print(t.text)
```

- Max **25 MB** per file. Formats: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm.
- `gpt-transcribe` returns `text` plus detected `languages`. Add `stream=True` to get `transcript.text.delta` / `transcript.text.done` events while it works.
- Speaker labels: only the deprecated `gpt-4o-transcribe-diarize` model (`response_format="diarized_json"`).

### 5.2 Live transcription over WebSocket

Connect to `wss://api.openai.com/v1/realtime?intent=transcription` (no `model` in the URL), then send:

```json
{"type": "session.update",
 "session": {"type": "transcription",
   "audio": {"input": {
     "format": {"type": "audio/pcm", "rate": 24000},
     "transcription": {"model": "gpt-live-transcribe"},
     "turn_detection": null}}}}
```

Results arrive as `conversation.item.input_audio_transcription.delta` and `...completed`.
`audio.input.transcription.delay` takes `minimal | low | medium | high | xhigh` (lower = earlier partials, higher = better accuracy).
With `turn_detection: null` you must send `input_audio_buffer.commit` yourself. **[UNVERIFIED: inferred from the Realtime event model]**

---

## 6. Realtime API (speech to speech voice agent)

Key facts:
- Model: `gpt-realtime-2.1`. GA interface: do **not** send the old `OpenAI-Beta: realtime=v1` header.
- Transports: **WebRTC** in the browser (`POST https://api.openai.com/v1/realtime/calls` with SDP), **WebSocket** from a trusted server
  (`wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1`), plus SIP for phone calls.
- Audio over WebSocket: base64 **PCM16, 24 kHz, mono**. The band gives 16 kHz, so resample (code below).
- Session shape: `session.type = "realtime"`, audio settings under `session.audio.input` / `session.audio.output`, voice such as `marin` or `cedar`, `turn_detection: {"type": "semantic_vad"}`.
- Useful events: `session.created`, `input_audio_buffer.speech_started/stopped`, `response.output_audio.delta`,
  `response.output_audio_transcript.delta`, `response.function_call_arguments.delta`, `response.done`, `error`.

### 6.1 Python WebSocket client fed by the band (sketch)

```python
# pip install websockets numpy
import asyncio, base64, json, os
import numpy as np
import websockets

URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1"
HEADERS = {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}

def pcm16k_to_24k(pcm: bytes) -> bytes:
    """Linear resample 16 kHz s16 mono -> 24 kHz (good enough for speech)."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n_out = int(len(x) * 24000 / 16000)
    y = np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x)
    return y.astype(np.int16).tobytes()

async def main(pcm_16k: bytes):
    async with websockets.connect(URL, additional_headers=HEADERS) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": "You are a wristband coach. Answer in one short sentence.",
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": 24000},
                          "turn_detection": {"type": "semantic_vad"}},
                "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": "marin"},
            },
        }}))
        pcm = pcm16k_to_24k(pcm_16k)
        for i in range(0, len(pcm), 4800):              # 100 ms chunks
            await ws.send(json.dumps({"type": "input_audio_buffer.append",
                                      "audio": base64.b64encode(pcm[i:i + 4800]).decode()}))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await ws.send(json.dumps({"type": "response.create"}))
        out = bytearray()
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "response.output_audio.delta":
                out += base64.b64decode(ev["delta"])
            elif ev["type"] == "response.output_audio_transcript.delta":
                print(ev["delta"], end="", flush=True)
            elif ev["type"] in ("response.done", "error"):
                print("\n", ev["type"]); break
        return bytes(out)   # 24 kHz PCM16; wrap in a WAV header to play it
```

The event names and payloads come from the Realtime conversations guide. The server events reference confirms that
`response.output_audio.delta` and `response.output_audio_transcript.delta` carry a `delta` field (plus `item_id`, `response_id`).
Sending a manual `commit` while `semantic_vad` is on may be redundant. **[UNVERIFIED]** For push-to-talk on a band tap, set
`turn_detection: null` and commit on release.

### 6.2 Browser WebRTC (dashboard.html) with an ephemeral key

Server side (Python), endpoint `POST /v1/realtime/client_secrets`. The key is in the response field `value`:

```python
import os, requests

def mint_realtime_key() -> str:
    r = requests.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
        json={"session": {"type": "realtime", "model": "gpt-realtime-2.1",
                          "audio": {"output": {"voice": "marin"}}}},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["value"]       # serve this from GET /token
```

Browser side (from the official WebRTC guide, trimmed):

```js
const { value: EPHEMERAL_KEY } = await (await fetch("/token")).json();
const pc = new RTCPeerConnection();
const audio = document.createElement("audio"); audio.autoplay = true;
pc.ontrack = (e) => (audio.srcObject = e.streams[0]);
const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
pc.addTrack(mic.getTracks()[0]);
const dc = pc.createDataChannel("oai-events");          // JSON events travel here
dc.onmessage = (e) => console.log(JSON.parse(e.data).type);
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
const sdp = await fetch("https://api.openai.com/v1/realtime/calls", {
  method: "POST", body: offer.sdp,
  headers: { Authorization: `Bearer ${EPHEMERAL_KEY}`, "Content-Type": "application/sdp" },
});
await pc.setRemoteDescription({ type: "answer", sdp: await sdp.text() });
```

The page must run on `https://` or `localhost` for microphone access. The browser mic here is the laptop mic, not the band.
To use the band mic in the browser, send its PCM over the data channel or use the WebSocket path instead.

### 6.3 Tools inside a Realtime session

Add `"tools": [{"type": "function", "name": ..., "description": ..., "parameters": {...}}]` and `"tool_choice": "auto"` to
`session.update`. When the model calls a tool, reply with:

```json
{"type": "conversation.item.create",
 "item": {"type": "function_call_output", "call_id": "call_...", "output": "{\"ok\": true}"}}
```

then send `{"type": "response.create"}` so the model speaks the result.

### 6.4 GPT-Live (alternative)

`gpt-live-1` listens while it speaks (full duplex) and hands real work to a backend Responses model (delegation), for example
`gpt-5.6-terra` with `web_search`. Sessions start with `POST /v1/live/sessions` (Python SDK: `client.live.create(session=..., transport={"type": "webrtc", "sdp": ...})`).
WebRTC session creation bills 15 s up front, credited against the running session. Good for a polished demo. It is newer and has
fewer examples, so the Realtime API is the safer choice for a one-day build.

---

## 7. Text to speech (legacy, still working)

```python
from openai import OpenAI

client = OpenAI()
with client.audio.speech.with_streaming_response.create(
    model="gpt-4o-mini-tts",            # deprecated, shuts down 2027-01-06
    voice="marin",                       # marin / cedar recommended
    input="Nice pace! Two more minutes.",
    instructions="Upbeat coach, short and clear.",
    response_format="wav",               # mp3, opus, aac, flac, wav, pcm
) as resp:
    resp.stream_to_file("coach.wav")
```

Input max is 4096 characters; `speed` ranges from 0.25 to 4.0. OpenAI's usage policy requires telling users that the voice is AI-generated.
Custom voices: `POST /v1/audio/voices` (from a consent recording plus a sample, or from a text prompt). Prompt voices work only in GPT-Live.

---

## 8. Agents SDK (Python)

```powershell
pip install openai-agents      # Python 3.10+
```

```python
from agents import Agent, Runner, function_tool

@function_tool
def band_battery() -> str:
    """Return the wristband battery level."""
    return "82%"

agent = Agent(
    name="Band assistant",
    instructions="Help the wearer. Use tools for band state. Be brief.",
    model="gpt-6-luna",
    tools=[band_battery],
)
result = Runner.run_sync(agent, "How much battery is left?")
print(result.final_output)
```

- Hosted tools: `WebSearchTool`, `FileSearchTool`, `CodeInterpreterTool`, `HostedMCPTool`, `ImageGenerationTool`, `ToolSearchTool`.
- Also: handoffs and agents as tools, guardrails, sessions, built-in tracing (visible in the OpenAI dashboard).
- The tools page also shows a newer `from agents.decorators import tool` decorator. `@function_tool` is still referenced there. **[pick one; both appear in docs]**
- Async: `result = await Runner.run(agent, "...")`.

### 8.1 Realtime agents in Python

```python
import asyncio
from agents.realtime import RealtimeAgent, RealtimeRunner

agent = RealtimeAgent(name="Coach", instructions="Short, encouraging answers.")
runner = RealtimeRunner(starting_agent=agent, config={"model_settings": {
    "model_name": "gpt-realtime-2.1",
    "audio": {
        "input": {"format": "pcm16",
                  "transcription": {"model": "gpt-4o-mini-transcribe"},
                  "turn_detection": {"type": "semantic_vad", "interrupt_response": True}},
        "output": {"format": "pcm16", "voice": "ash"},
    },
}})

async def main():
    session = await runner.run()
    async with session:
        await session.send_message("Say hello in one short sentence.")
        # for band audio: await session.send_audio(pcm24k_bytes)
        async for event in session:
            if event.type == "audio":
                pass                      # event.audio.data -> speaker
            elif event.type == "agent_end":
                break
            elif event.type == "error":
                print(event.error)

asyncio.run(main())
```

The official quickstart still uses the deprecated `gpt-4o-mini-transcribe` for input transcripts. Swapping it for `gpt-transcribe`
should work. **[UNVERIFIED]**

---

## 9. Ideas that fit the wearable theme

- **Tap-to-ask:** double tap starts recording, release sends audio to `gpt-transcribe` (or Realtime), answer is spoken back. Cheap with Luna.
- **Motion coach:** send windows of accelerometer summaries (not raw streams) as text/JSON to `gpt-6-luna` with Structured Outputs
  to label activity or count reps. Keep raw signal processing local in Python.
- **Agent with band tools:** expose `set_band_light`, `vibrate`, `start_recording` as function tools so the model can act on the band.
- **Combine sponsors:** OpenAI for reasoning and STT, ElevenLabs for the voice (needed for the ElevenLabs track).

---

## 10. Limits and gotchas

- **Deprecated defaults in old tutorials:** `gpt-4o`, `whisper-1`, `tts-1`, `gpt-4o-mini-tts`, `gpt-realtime` all appear in older blog posts. Use the IDs in section 2.
- **Realtime cost:** audio tokens on `gpt-realtime-2.1` cost $32/$64 per 1M. Leaving a session open with VAD on keeps billing input audio. Close sessions and prefer `-mini` while developing.
- **Sample rate:** Realtime WebSocket examples use 24 kHz PCM16. The band is 16 kHz, so resample (section 6.1).
- **Browser mic** needs HTTPS or localhost. Never ship `OPENAI_API_KEY` to the browser; use `/v1/realtime/client_secrets`.
- **Rate limits** depend on the account's usage tier. New accounts with only promo credits may hit low limits. I did not read the tier table today. **[UNVERIFIED specifics]**
- **Structured Outputs** need `additionalProperties: false` and every field in `required`.
- **Windows:** `setx` only affects new terminals. In PowerShell, use `$env:OPENAI_API_KEY="..."` for the current window.
- **TTS disclosure:** tell users the voice is AI-generated (OpenAI usage policy).

---

## 11. Sources (read 2026-11-14)

- Docs MCP: https://developers.openai.com/learn/docs-mcp
- OpenAI Developers plugin: https://developers.openai.com/learn/developers-codex-plugin
- Agents API MCP tool (anonymous docs MCP): https://developers.openai.com/api/docs/guides/agents-api/tools/mcp
- Models: https://developers.openai.com/api/docs/models
- All models (incl. deprecated): https://developers.openai.com/api/docs/models/all
- Pricing: https://developers.openai.com/api/docs/pricing
- Quickstart: https://developers.openai.com/api/docs/quickstart
- Function calling: https://developers.openai.com/api/docs/guides/function-calling
- Structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- File transcription: https://developers.openai.com/api/docs/guides/speech-to-text
- Realtime transcription: https://developers.openai.com/api/docs/guides/realtime-transcription
- Realtime getting started: https://developers.openai.com/api/docs/guides/realtime
- Realtime conversations (session/events): https://developers.openai.com/api/docs/guides/realtime-conversations
- Realtime WebRTC: https://developers.openai.com/api/docs/guides/voice-webrtc?api=realtime
- Realtime WebSocket: https://developers.openai.com/api/docs/guides/voice-websockets?api=realtime
- GPT-Live: https://developers.openai.com/api/docs/guides/live
- Text to speech: https://developers.openai.com/api/docs/guides/text-to-speech
- Speech API reference: https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create.md
- Custom voices: https://developers.openai.com/api/docs/guides/custom-voices
- Agents SDK: https://openai.github.io/openai-agents-python/
- Agents SDK tools: https://openai.github.io/openai-agents-python/tools/
- Agents SDK realtime quickstart: https://openai.github.io/openai-agents-python/realtime/quickstart/
- GPT-6 Sol/Luna announcement: https://openai.com/blog/introducing-gpt-6-sol-and-luna
