# Google DeepMind / Gemini API (Gemini 4) - developer digest

Track: **"Best use of Gemini 4"**. Researched 2026-11-14 from ai.google.dev / aistudio.google.com docs (the
ai.google.dev pages now redirect to aistudio.google.com/docs/...) and the official GitHub orgs.
Items marked **[unverified]** were not confirmed on an official page.

---

## 1. TL;DR for the hackathon

- **Default model: `gemini-4-hydrogen`.** It is fast, has a **free tier**, takes text/image/audio/video/PDF in, and has a 1M unified context.
  Carbon and Argon are **paid tier only**.
- **Real-time voice from the wristband mic: Live API with `gemini-3.8-live`** (the Live model is a 3.8 model, not a
  Gemini 4 model). It uses WebSockets, takes 16 kHz 16-bit PCM in, and sends 24 kHz PCM out. It has a free tier.
- **For a "Best use of Gemini 4" pitch:** use `gemini-4-hydrogen` (or Carbon/Argon) as the reasoning brain, for example
  to classify motion and tap events, summarize audio, or call tools. Add `gemini-3.8-live` only for the spoken loop.
- **New API surface:** the **Interactions API** (`client.interactions.create(...)`) is the recommended interface as of
  June 2026. `generateContent` (`client.models.generate_content`) is now "legacy" but still fully supported.
- SDKs: `pip install google-genai` (Python, `from google import genai`) and `npm install @google/genai` (JS).
  The old `google-generativeai` / `@google/generative-ai` packages are **deprecated**. Do not use them.
- Auth: an API key from **https://aistudio.google.com/apikey**, set as env var `GEMINI_API_KEY`. If both are set,
  `GOOGLE_API_KEY` wins.

## 2. Models (as of 2026-11-14)

| Model ID | Role | Price per 1M tokens (in / out, paid tier) | Free tier | Thinking levels |
|---|---|---|---|---|
| `gemini-4-hydrogen` | Default general-purpose, fast | $1.50 / $7.50 | **Yes** | `low`, `medium`, `high` (default), `xhigh` |
| `gemini-4-argon` | Efficient frontier reasoning | $2 / $10 intro through Nov 30 2026, then $4 / $20 | No | `low`, `medium` (default), `high` |
| `gemini-4-carbon` | Strongest reasoning (spends more thinking tokens) | $2 / $10 intro through Nov 30 2026, then $4 / $20 | No | `low`, `medium` (default), `high` |
| `gemini-3.5-flash-lite` | Cheapest/fastest, routing/classification | $0.30 / $2.50 | Yes | `minimal` (default), `low`, `medium`, `high` |
| `gemini-3.8-live` | Live API: real-time voice | text in $0.75, audio in $3.00 (or $0.005/min); text out $4.50, audio out $12.00 (or $0.018/min) | Yes | interleaved thinking |
| `gemini-3.8-live-extended-thinking` | Live with configurable thinking | see pricing page [unverified] | [unverified] | `thinking_level` in Live config |
| `gemini-3.8-flash-tts` | Text-to-speech | text in $0.50, audio out $9.00 (through Dec 31 2026) | Yes | - |
| `gemini-3.5-transcribe` | Speech-to-text | audio in $2.00 (or $0.003/min) | Yes | - |
| `gemini-embedding-2` | Multimodal embeddings | text $0.20, audio $6.50 | Yes | - |

Specs shared by all three Gemini 4 models:
- **Inputs:** text, image, video, audio, PDF. **Output:** text.
- **Context:** 1,048,576 tokens, *unified*: input, thinking and output share one window.
- **Output limit:** 65,536 tokens per synchronous request. "Long decode" up to 1M tokens is available with `background=True`.
- **Built-in tools:** all support Google Search grounding, code execution, function calling, computer use and structured outputs.
- **Caching:** only implicit caching (prompts of 4,096 tokens or more, 95% discount on hits). Explicit `caches.create` / `cached_content` is **not supported**.

Other specialized IDs mentioned on the latest-models page: `gemini-nano-banana-2.1` (images), `gemini-omni-1.2-flash` (video
generation), `lyria-3.5` (music), `gemini-decision-1` (Decisions API: yes/no, choice and score decisions),
`antigravity-preview-09-2026` and `deep-research-preview-04-2026` (Managed Agents).

## 3. Setup (Windows 11, Python 3.12)

```powershell
pip install -U google-genai pydantic
# For this shell only:
$env:GEMINI_API_KEY = "AIza..."        # from https://aistudio.google.com/apikey
# Persist it (open a new terminal afterwards):
setx GEMINI_API_KEY "AIza..."
```

```bash
npm install @google/genai          # JS / browser bundle
```

- The SDK reads `GEMINI_API_KEY` or `GOOGLE_API_KEY` from the environment. You can also pass it explicitly with
  `genai.Client(api_key=...)` or `new GoogleGenAI({ apiKey })`.
- **Never ship the key to the browser.** Use a backend proxy (for example your Python server). For browser Live API sessions,
  use **ephemeral tokens** (section 9).
- Rate limits apply **per project, not per API key**. Your actual RPM/TPM/RPD numbers are shown at
  https://aistudio.google.com/rate-limit. RPD resets at midnight Pacific time.
- Minimum `google-genai` version: [unverified]. The Interactions API needs a recent 2.x release, so run `pip install -U`.

## 4. First call (Interactions API)

```python
from google import genai

client = genai.Client()  # reads GEMINI_API_KEY

interaction = client.interactions.create(
    model="gemini-4-hydrogen",
    system_instruction="You are a concise wearable assistant.",
    input="Explain gravity to a skeptical cat in three short sentences.",
    generation_config={"thinking_level": "medium"},   # lower latency than the default "high"
)
print(interaction.output_text)
print(interaction.usage)
```

```javascript
import { GoogleGenAI } from "@google/genai";
const client = new GoogleGenAI({});   // reads GEMINI_API_KEY in Node

const interaction = await client.interactions.create({
  model: "gemini-4-hydrogen",
  system_instruction: "You are a concise wearable assistant.",
  input: "Explain gravity to a skeptical cat in three short sentences.",
});
console.log(interaction.output_text);
```

REST: `POST https://generativelanguage.googleapis.com/v1beta/interactions` with header `x-goog-api-key: $GEMINI_API_KEY`
and body `{"model": "...", "input": "..."}`.

Key request fields: `model` (or `agent`), `input` (a string or a list of typed parts), `system_instruction`, `tools`,
`generation_config` (`thinking_level`, `max_output_tokens`, `tool_choice`), `response_format`, `previous_interaction_id`,
`stream`, `store` (default true), `background`.

Response: `output_text`, `steps` (model_output, function_call, thoughts, ...), `usage`, `id`, `status`.

### Streaming

```python
for chunk in client.interactions.create(model="gemini-4-hydrogen",
                                        input="Tell me a short story.", stream=True):
    print(chunk.text, end="")
```

```javascript
const stream = await client.interactions.create({ model: "gemini-4-hydrogen", input: "Tell me a short story.", stream: true });
for await (const chunk of stream) process.stdout.write(chunk.text);
```

### Multi-turn (server-side state)

```python
i1 = client.interactions.create(model="gemini-4-hydrogen", input="I have 2 dogs in my house.")
i2 = client.interactions.create(model="gemini-4-hydrogen",
                                input="How many paws are in my house?",
                                previous_interaction_id=i1.id)
print(i2.output_text)
```

`tools`, `system_instruction` and `generation_config` are scoped to one interaction. Pass them again on every turn.
`store=False` makes the call stateless, and you then cannot use `previous_interaction_id` or `background`.

## 5. Audio input (wristband mic recordings)

Supported MIME types: `audio/wav`, `audio/mp3`, `audio/aiff`, `audio/aac`, `audio/ogg`, `audio/flac`, `audio/mpeg`,
`audio/m4a`, `audio/l16`, `audio/opus`, `audio/alaw`, `audio/mulaw`, `audio/webm`.
Audio costs **32 tokens per second** (1 minute = 1,920 tokens). The maximum is 9.5 hours per prompt. Inline requests can be
at most **20 MB** in total. Use the Files API for anything larger.

```python
import base64
from google import genai

client = genai.Client()
with open("recording.wav", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode("utf-8")

interaction = client.interactions.create(
    model="gemini-4-hydrogen",
    input=[
        {"type": "text", "text": "Transcribe this, then say what the speaker wants in one line."},
        {"type": "audio", "data": audio_b64, "mime_type": "audio/wav"},
    ],
)
print(interaction.output_text)

# Larger files: upload first
up = client.files.upload(file="long_recording.mp3")
interaction = client.interactions.create(
    model="gemini-4-hydrogen",
    input=[{"type": "text", "text": "Summarize"},
           {"type": "audio", "uri": up.uri, "mime_type": up.mime_type}],
)
```

The official audio page examples use `gemini-3.8-flash`. Using `gemini-4-hydrogen` instead works because Gemini 4 models
accept audio input according to their model pages. Images work the same way with `{"type": "image", "uri"|"data": ..., "mime_type": "image/jpeg"}`.

## 6. Function calling (tools) - for example "the band tapped twice, so call `toggle_lights`"

```python
import json
from google import genai

client = genai.Client()

set_light = {
    "type": "function",
    "name": "set_light_values",
    "description": "Set the brightness and color temperature of a room light.",
    "parameters": {
        "type": "object",
        "properties": {
            "brightness": {"type": "number", "description": "Light level from 0 to 100."},
            "color_temp": {"type": "string", "description": "daylight, cool_white or warm_white"},
        },
        "required": ["brightness", "color_temp"],
    },
}

interaction = client.interactions.create(
    model="gemini-4-hydrogen",
    input="User double-tapped the band and said 'make it cozy'.",
    tools=[set_light],
)

for step in interaction.steps:
    if step.type == "function_call":
        result = {"ok": True, **step.arguments}          # run your real function here
        final = client.interactions.create(
            model="gemini-4-hydrogen",
            input=[{
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": json.dumps(result)}],
            }],
            tools=[set_light],                            # re-declare tools on each turn
            previous_interaction_id=interaction.id,
        )
        print(final.output_text)
```

- Force tool use with `generation_config={"tool_choice": "any"}`. Restrict it with
  `{"tool_choice": {"allowed_tools": {"mode": "any", "tools": ["get_current_temperature"]}}}`.
- The model can return several `function_call` steps in parallel.
- **Gotcha:** declare tools natively. If you ask for raw JSON "tool calls" in the system prompt without declaring tools,
  you can get a `MALFORMED_FUNCTION_CALL` error.
- Built-in tools such as `{"type": "google_search"}`, `{"type": "code_execution"}` and `url_context` exist. Managed Agents also accept
  `{"type": "mcp_server", "name": ..., "url": ...}`. Whether plain model calls accept `mcp_server` is [unverified].

JS: same shape (`tools: [{ type: "function", name, description, parameters }]`, loop over `interaction.steps`,
send back `{ type: "function_result", name, call_id, result: [{ type: "text", text }] }` with `previous_interaction_id`).

## 7. Structured output (JSON schema)

```python
from pydantic import BaseModel, Field
from typing import Literal
from google import genai

class Gesture(BaseModel):
    label: Literal["wave", "double_tap", "shake", "idle"]
    confidence: float = Field(description="0..1")
    reason: str

client = genai.Client()
interaction = client.interactions.create(
    model="gemini-4-hydrogen",
    input="Accel window (g): ax=[...], ay=[...], az=[...]. Taps: 2 within 300ms. Classify.",
    response_format={
        "type": "text",
        "mime_type": "application/json",
        "schema": Gesture.model_json_schema(),
    },
)
g = Gesture.model_validate_json(interaction.output_text)
print(g.label, g.confidence)
```

```javascript
const interaction = await client.interactions.create({
  model: "gemini-4-hydrogen",
  input: prompt,
  response_format: { type: "text", mime_type: "application/json", schema: jsonSchema },
});
const obj = JSON.parse(interaction.output_text);
```

The Live API (`gemini-3.8-live`) does **not** support structured outputs.

## 8. Live API (real-time voice and audio streaming)

- **Model:** `gemini-3.8-live`, or `gemini-3.8-live-extended-thinking` if you need configurable thinking. Input limit 131,072 tokens,
  output limit 65,536.
- **Protocol:** a stateful WebSocket (WSS). The SDK wraps it as `client.aio.live.connect(...)` in Python and `ai.live.connect(...)` in JS.
- **Audio in:** raw 16-bit PCM, **16 kHz**, little-endian, with MIME type `audio/pcm;rate=16000`. **Audio out:** raw 16-bit PCM, **24 kHz**, little-endian.
  Images: JPEG at 1 fps or less. Text is also accepted.
- **Response modality:** `["AUDIO"]` only. Turn on transcriptions to get text as well.
- **Session limits:** audio-only sessions last 15 min, audio+video sessions 2 min, and a connection lives for about 10 min. Use
  `context_window_compression` (sliding window) and session resumption (handles stay valid for 2 h) to go longer. Watch for
  `response.go_away`.
- **Features:** barge-in (`server_content.interrupted`), automatic VAD (configurable or disabled), input and output
  transcription (with `custom_vocabulary`), function calling, Google Search, prebuilt voices (for example `"Kore"`), affective dialog,
  proactive audio. Language support is given as 70 on the overview page and 99 on the capabilities page.

### Python: stream a WAV/PCM source and save the spoken reply

```python
import asyncio, wave
from google import genai
from google.genai import types

client = genai.Client(http_options={"api_version": "v1beta"})
MODEL = "gemini-3.8-live"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a wrist assistant. Answer in one short sentence.",
    "input_audio_transcription": {},
    "output_audio_transcription": {},
    "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Kore"}}},
}

async def main():
    async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
        # Assumes 16 kHz / 16-bit / mono WAV. Resample first if your band mic differs.
        with wave.open("recording.wav", "rb") as w:
            while chunk := w.readframes(1600):            # 100 ms chunks
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
        await session.send_realtime_input(audio_stream_end=True)

        out = wave.open("reply.wav", "wb"); out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000)
        async for resp in session.receive():
            sc = resp.server_content
            if resp.tool_call:
                await session.send_tool_response(function_responses=[
                    types.FunctionResponse(name=fc.name, id=fc.id, response={"result": "ok"})
                    for fc in resp.tool_call.function_calls])
            if not sc:
                continue
            if sc.input_transcription:  print("User:", sc.input_transcription.text)
            if sc.output_transcription: print("Gemini:", sc.output_transcription.text)
            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.inline_data:
                        out.writeframes(part.inline_data.data)
            if sc.turn_complete:          # field name from the SDK types [unverified on docs page]
                break
        out.close()

asyncio.run(main())
```

This example is put together from the official snippets for connect, `send_realtime_input`, receive, transcription,
tool calls and `audio_stream_end`. For a live microphone, feed 16 kHz PCM chunks from your band stream into the same `send_realtime_input` call.
Official end-to-end sample (Python backend plus browser media handler):
https://github.com/google-gemini/gemini-live-api-examples/tree/main/gemini-live-genai-python-sdk

VAD tuning (Python):
```python
config = {"response_modalities": ["AUDIO"],
          "realtime_input_config": {"automatic_activity_detection": {
              "disabled": False,
              "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_LOW,
              "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_LOW,
              "prefix_padding_ms": 20, "silence_duration_ms": 100}}}
```

## 9. Live API from the browser (ephemeral tokens)

The server (Python) mints a single-use token and never sends the real key to the browser:
```python
import datetime
from google import genai
client = genai.Client()
now = datetime.datetime.now(tz=datetime.timezone.utc)
token = client.auth_tokens.create(config={
    "uses": 1,
    "expire_time": now + datetime.timedelta(minutes=30),           # default 30 min
    "new_session_expire_time": now + datetime.timedelta(minutes=1), # default 1 min
})
# return token.name to the browser
```

Browser JS:
```javascript
import { GoogleGenAI, Modality } from "@google/genai";
const ai = new GoogleGenAI({ apiKey: tokenName });   // the ephemeral token, not the API key
const session = await ai.live.connect({
  model: "gemini-3.8-live",
  config: { responseModalities: [Modality.AUDIO], inputAudioTranscription: {}, outputAudioTranscription: {} },
  callbacks: {
    onopen: () => console.log("open"),
    onmessage: (msg) => { /* msg.serverContent?.modelTurn?.parts[].inlineData.data = base64 PCM 24k */ },
    onerror: (e) => console.error(e),
    onclose: (e) => console.log("closed", e.reason),
  },
});
// Send 16 kHz PCM16 (base64) chunks. Shape follows SDK conventions [unverified on docs page]:
session.sendRealtimeInput({ audio: { data: pcmBase64, mimeType: "audio/pcm;rate=16000" } });
session.sendRealtimeInput({ audioStreamEnd: true });
```
Ephemeral tokens only work for the Live API, and only on `v1beta`. Browser microphones usually capture at 48 kHz, so
downsample to 16 kHz Int16 in an AudioWorklet before sending.

## 10. Long outputs and background jobs

```python
import time
i = client.interactions.create(model="gemini-4-hydrogen", input="...", background=True,
                               generation_config={"max_output_tokens": 262144})
while i.status in ("in_progress", "queued"):
    time.sleep(5); i = client.interactions.get(id=i.id)
```
If you set `background=True` without `max_output_tokens`, generation stops at 65,536 tokens.

## 11. Pricing, free tier and limits

- **Free tier:** `gemini-4-hydrogen`, `gemini-3.5-flash-lite`, `gemini-3.8-live`, TTS, transcribe and embeddings are free of charge,
  with lower rate limits. **Free-tier data is used to improve Google products.** Carbon and Argon need billing (Tier 1 or higher).
- **Billing tiers:** Free (an active project); Tier 1 (a linked billing account, $250 cap); Tier 2 ($100 paid + 3 days, $2,000 cap);
  Tier 3 ($1,000 paid + 30 days).
- **Rate limits:** RPM, TPM (input) and RPD, applied per project. The docs page does not list exact per-model free-tier numbers; check
  https://aistudio.google.com/rate-limit [unverified numbers].
- **Google Search grounding:** 5,000 free requests per month (shared across Gemini 3+), then $14 per 1,000, with a cap of 1,500 per day per project.
- **Batch API:** 50% cheaper for asynchronous bulk jobs.
- Every token is billed, **including thinking tokens**. Use a lower `thinking_level` to save money and latency.

## 12. Gotchas (Gemini 4 specific)

1. **Remove `temperature`, `top_p` and `top_k`.** The server ignores in-range values and returns 400 for out-of-range ones on Gemini 4.
2. **`thinking_level: "minimal"` is rejected** by Hydrogen (it is valid only on Flash-Lite). Hydrogen defaults to `high`, so use `low` or `medium` for
   snappy wearable UX.
3. **Do not hardcode a low `max_output_tokens`** (such as 8192). The cap covers thinking plus output, so answers can get cut off.
4. **No explicit context caching** on Gemini 4. Only implicit caching is available.
5. **Thought signatures:** with legacy `generateContent` multi-turn, return the prior model turns unchanged. With the Interactions API,
   use `previous_interaction_id` instead.
6. Live API **audio format must match exactly**: 16 kHz PCM16 LE in, 24 kHz PCM16 LE out.
7. The Live API caps audio+video sessions at **2 minutes**. Use audio-only (15 min) unless you need the camera.
8. The free tier is rate-limited per *project*, so a team sharing one project shares the quota.
9. **Never put the API key in browser JS.** Use a Python proxy or ephemeral tokens.

## 13. MCP and coding-agent tooling (official)

**Gemini Docs MCP server** (official, documentation search only. It does not call the API for you):
- URL: `https://gemini-api-docs-mcp.dev`
- Transport: **http** (streamable HTTP)
- Auth: **none** (the official install configs send empty headers)
- Tools: `gemini_search_docs` (live search) and `gemini_get_doc` (full page read)
- Claude Code install (verbatim from https://ai.google.dev/gemini-api/docs/coding-agents):
  ```bash
  claude mcp add --transport http geminiDocs https://gemini-api-docs-mcp.dev
  ```
- Generic alternative: `npx add-mcp "https://gemini-api-docs-mcp.dev"`. Stdio bridge: `npx mcp-remote@0.1.25 https://gemini-api-docs-mcp.dev`.

**No official "Gemini API" MCP server** (one that would run generation as MCP tools) was found. The "Gemini API Plugin"
bundle (skills, the Docs MCP and API key tools) is for Antigravity only.

**Agent skills** (official repo `google-gemini/gemini-skills`):
```bash
npx skills add google-gemini/gemini-skills --skill gemini-api-dev --global
npx skills add google-gemini/gemini-skills --skill gemini-live-api-dev --global
```
You can also append `.md` to any docs URL, or feed https://aistudio.google.com/llms.txt (or `llms-full.txt`) to your agent.

## 14. Hackathon ideas mapped to the APIs

- **Gesture + voice copilot:** band taps and motion go to `gemini-4-hydrogen` with structured output (a gesture label), and the label triggers
  function calls such as smart-home control or notes.
- **Ambient memory:** mic clips go to `gemini-4-hydrogen` audio understanding (transcript, intent, summary), then into `gemini-embedding-2` for search.
- **Talk-to-your-wrist:** `gemini-3.8-live` with function calling, where the tools read the latest motion stats from your Python server.
- **Deep analysis:** send a long sensor log (CSV in a 1M-token context) to `gemini-4-carbon` (paid) for anomaly reports.

## 15. Sources

- https://ai.google.dev/gemini-api/docs/latest-model
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/models/gemini-4-argon
- https://ai.google.dev/gemini-api/docs/models/gemini-4-hydrogen
- https://ai.google.dev/gemini-api/docs/whats-new-gemini-4-hydrogen
- https://ai.google.dev/gemini-api/docs/whats-new-gemini-4-carbon.md
- https://ai.google.dev/gemini-api/docs/interactions-overview
- https://ai.google.dev/gemini-api/docs/text-generation
- https://ai.google.dev/gemini-api/docs/audio
- https://ai.google.dev/gemini-api/docs/function-calling
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/live-api
- https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk
- https://ai.google.dev/gemini-api/docs/live-api/capabilities
- https://ai.google.dev/gemini-api/docs/live-api/session-management
- https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live
- https://ai.google.dev/gemini-api/docs/api-key
- https://ai.google.dev/gemini-api/docs/libraries
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/coding-agents
- https://gemini-api-docs-mcp.dev
- https://github.com/googleapis/python-genai
- https://github.com/google-gemini/gemini-live-api-examples
