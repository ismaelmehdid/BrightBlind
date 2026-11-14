# Mastra developer digest (VexoHacks, 2026-11-14)

Sponsor tier: silver ("Build with agents"). Prize details (Mastra credits / "Mastra Studio") come from the event brief;
the public hackathon page (vexoai.com/hackathon) only lists Mastra as a sponsor and gives no prize breakdown. **Unverified.**

Source of everything below: official docs at https://mastra.ai/docs (read 2026-11-14) unless marked otherwise.
Mastra's docs say they are the canonical reference and to trust them over model training data: APIs changed a lot
from v0 to v1 (e.g. `execute({ context })` became `execute(inputData, context)`, Mastra Cloud became "Mastra platform").

---

## 1. What it is

- Open-source **TypeScript framework for AI agents and apps** (`@mastra/core`). It runs on Node and ships as a Hono server.
- Building blocks: **Agents** (LLM + tools + memory, loops until a final answer), **Tools** (`createTool`, zod schemas),
  **Workflows** (typed steps, `.then/.parallel/.branch`, suspend/resume, streaming), **Memory** (history, working memory,
  semantic recall, observational memory), **Voice** (TTS / STT / realtime speech-to-speech), **MCP** client and server,
  plus Harness (durable agents, schedules), Sandboxes/Workspaces, Evals, Tracing, Channels (Slack, Discord, Telegram...).
- **Model router**: models are plain strings `provider/model` (e.g. `anthropic/claude-sonnet-4-6`). No provider SDK import.
  The API key comes from env vars: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, ...
- **Studio**: local UI at `http://localhost:4111` (chat with agents, run workflows, run tools on their own, traces, MCP servers).
- **Mastra platform** (formerly *Mastra Cloud*): hosted Observability, Studio and Server, deployed with `mastra deploy`.

## 2. Fit for this hackathon (Vexo band: motion + taps + mic audio; tracks: Voice / Vision / Ambient)

| Band signal / need | Mastra piece |
|---|---|
| Mic audio clip -> text | `agent.voice.listen(stream)` (OpenAI, Deepgram, ElevenLabs, Google... STT) |
| Spoken reply | `agent.voice.speak(text)` -> audio stream (TTS) |
| Full-duplex voice | `OpenAIRealtimeVoice` + `voice.connect()/send()/on('speaker')` |
| Tap / gesture -> fixed pipeline | Workflow (`createWorkflow`) started from a custom HTTP route |
| Motion stream -> context | Tool that reads latest IMU state from your Python bridge |
| Remember user across sessions | `Memory` + `LibSQLStore` (`resource` = user, `thread` = session) |
| Camera frame (e.g. Marv Labs headset) -> vision | `agent.generate([{ role:'user', content:[{type:'image', image, mimeType}, {type:'text', text}] }])` |
| Let Claude Code drive your agents | Built-in MCP endpoint `http://localhost:4111/api/mcp` |
| Browser dashboard | `@mastra/client-js` (`MastraClient`, uses fetch, built for browsers) |

Suggested architecture (keeps the Python band code you already have):

```
Vexo band --(BLE)--> Python 3.12 bridge --(HTTP POST JSON / WAV)--> Mastra server :4111
                                                                     |- custom route /band/event -> workflow
                                                                     |- agent (tools, memory, voice)
browser dashboard <-- @mastra/client-js / REST -----------------------/
```

## 3. Quickstart (Windows 11, Node 24, PowerShell)

Requirements: **Node.js >= 22.13.0** (Mastra v1 requirement; Node 24 is fine). An LLM API key.

```powershell
# Scaffold. The default starter = agent harness (workspace, shell tools, memory, tasks, web access, schedules)
npx create-mastra@latest band-agent --llm anthropic      # or openai | google | xai | mastra (Gateway)
#   --empty          provider-free minimal project (no agents/examples)
#   --template <slug|github-url>  e.g. --template agent-harness
#   --no-skills --no-git --no-install --timeout 60000
cd band-agent
npm run dev                                               # = mastra dev
# Studio:   http://localhost:4111
# REST:     http://localhost:4111/api      Swagger: http://localhost:4111/swagger-ui
```

- `create-mastra` also installs **Mastra skills** for detected coding agents (Claude Code etc.) and makes an initial git commit.
- Opting into the Mastra platform during the interactive setup writes `MASTRA_PLATFORM_ACCESS_TOKEN` and `MASTRA_PROJECT_ID` to `.env`.
- Mastra Gateway option: one key for all models (`MASTRA_GATEWAY_API_KEY`), models prefixed `mastra/` (e.g. `mastra/openai/...`),
  paid per token from Gateway credits. This is likely where hackathon "Mastra credits" would land (**unverified**).
- Changes in `src/mastra/` hot-restart the dev server.
- Skills for Claude Code by hand: `npx skills add mastra-ai/skills` (update: `npx skills update mastra`).

Adding Mastra to an existing folder by hand (from the Agents doc):

```powershell
npm init -y   # then set "type": "module" in package.json
npm install @mastra/core@latest zod@latest typescript@latest @types/node@latest mastra@latest
```

Project layout convention: `src/mastra/{agents,tools,workflows,scorers}/` plus `src/mastra/index.ts` (the `Mastra` instance).

## 4. Key APIs (TypeScript)

Model IDs below: the docs list `anthropic/claude-sonnet-4-6`, `anthropic/claude-haiku-4-5`, `openai/gpt-5-mini`,
`google/gemini-2.5-flash` as known IDs. Check https://mastra.ai/models before demo day if a call 404s.

### 4.1 Tool (`createTool`)

Plain object tools **silently fail**. Always use `createTool` with `id`, `description`, `inputSchema`, `execute`.
The signature is `execute(inputData, context)`. `context` holds `requestContext`, `abortSignal`, `tracingContext` and so on.

```ts
// src/mastra/tools/band-state.ts
import { createTool } from '@mastra/core/tools'
import { z } from 'zod'

// Latest band state, updated by the /band/event route (in-memory, fine for a demo)
export const bandState = { lastGesture: 'none', accelMag: 0, taps: 0, updatedAt: 0 }

export const bandStateTool = createTool({
  id: 'get-band-state',
  description: 'Latest wristband motion/tap state: last gesture, acceleration magnitude, tap count',
  inputSchema: z.object({}),
  outputSchema: z.object({
    lastGesture: z.string(), accelMag: z.number(), taps: z.number(), updatedAt: z.number(),
  }),
  execute: async () => ({ ...bandState }),
})
```

### 4.2 Agent

```ts
// src/mastra/agents/band-agent.ts
import { Agent } from '@mastra/core/agent'
import { Memory } from '@mastra/memory'
import { bandStateTool } from '../tools/band-state'

export const bandAgent = new Agent({
  id: 'band-agent',
  name: 'Band Agent',
  instructions: `You are an ambient assistant on a wristband. Answer in one or two spoken sentences.
Call get-band-state when the user refers to what they are doing physically.`,
  model: 'anthropic/claude-sonnet-4-6',     // string 'provider/model'; NOT 'provider:model', no provider object
  tools: { bandStateTool },
  memory: new Memory({ options: { lastMessages: 20 } }),
})
```

Calling it:

```ts
const agent = mastra.getAgentById('band-agent')        // use the Mastra instance, so storage/logging are wired in
const res = await agent.generate('What am I doing right now?', {
  memory: { resource: 'user-1', thread: 'session-1' }, // resource = user, thread = conversation
})
console.log(res.text, res.toolCalls, res.usage)

const stream = await agent.stream('Summarise my last hour')
for await (const chunk of stream.textStream) process.stdout.write(chunk)
```

Structured output:

```ts
const r = await agent.generate('Classify this gesture log: ...', {
  structuredOutput: { schema: z.object({ intent: z.enum(['call', 'note', 'ignore']), confidence: z.number() }) },
})
console.log(r.object)
```

Image input (vision, e.g. a camera frame as URL or data):

```ts
const r = await agent.generate([{
  role: 'user',
  content: [
    { type: 'image', image: 'https://example.com/frame.jpg', mimeType: 'image/jpeg' },
    { type: 'text', text: 'What part is the technician looking at?' },
  ],
}])
```

### 4.3 Mastra instance + storage + custom route for band events

```ts
// src/mastra/index.ts
import { Mastra } from '@mastra/core'
import { registerApiRoute } from '@mastra/core/server'
import { LibSQLStore } from '@mastra/libsql'
import { bandAgent } from './agents/band-agent'
import { tapWorkflow } from './workflows/tap-workflow'
import { bandState } from './tools/band-state'

export const mastra = new Mastra({
  agents: { bandAgent },
  workflows: { tapWorkflow },
  storage: new LibSQLStore({
    id: 'mastra-storage',                                    // id is required
    url: process.env.TURSO_DATABASE_URL ?? 'file:./mastra.db', // env-guarded so `mastra deploy` preflight passes
    authToken: process.env.TURSO_AUTH_TOKEN,
  }),
  server: {
    apiRoutes: [
      registerApiRoute('/band/event', {
        method: 'POST',
        handler: async c => {
          const mastra = c.get('mastra')
          const ev = await c.req.json()          // { type: 'tap'|'motion', ... } from the Python bridge
          Object.assign(bandState, ev.state ?? {}, { updatedAt: Date.now() })
          if (ev.type === 'tap') {
            const run = await mastra.getWorkflow('tapWorkflow').createRun()
            const result = await run.start({ inputData: { taps: ev.taps ?? 1 } })
            return c.json(result)
          }
          return c.json({ ok: true })
        },
      }),
    ],
  },
})
```

Install for the above: `npm install @mastra/memory@latest @mastra/libsql@latest`.
`url: ':memory:'` also works for throwaway runs. Memory **requires** a storage provider.

Python side (stdlib only, untested sketch):

```python
import json, urllib.request
def post_event(ev: dict):
    req = urllib.request.Request("http://localhost:4111/band/event", data=json.dumps(ev).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=30))
post_event({"type": "tap", "taps": 2})
```

### 4.4 Workflow

```ts
// src/mastra/workflows/tap-workflow.ts
import { createWorkflow, createStep } from '@mastra/core/workflows'
import { z } from 'zod'

const decide = createStep({
  id: 'decide',
  inputSchema: z.object({ taps: z.number() }),
  outputSchema: z.object({ action: z.string() }),
  execute: async ({ inputData }) => ({ action: inputData.taps >= 2 ? 'summarise' : 'note' }),
})

const act = createStep({
  id: 'act',
  inputSchema: z.object({ action: z.string() }),
  outputSchema: z.object({ reply: z.string() }),
  execute: async ({ inputData, mastra }) => {
    const agent = mastra.getAgentById('band-agent')
    const r = await agent.generate(`Do this for the user: ${inputData.action}`)
    return { reply: r.text }
  },
})

export const tapWorkflow = createWorkflow({
  id: 'tap-workflow',
  inputSchema: z.object({ taps: z.number() }),
  outputSchema: z.object({ reply: z.string() }),
})
  .then(decide)
  .then(act)
  .commit()
```

Step `execute` receives (per the Step reference): `inputData`, `mastra`, `state`, `setState`, `getStepResult`, `getStepResultAsync`,
`getInitData`, `suspend`, `resumeData`, `suspendData`, `runId`, `requestContext`, `retryCount`.

Run: `const run = await wf.createRun(); const res = await run.start({ inputData })`, then check `res.status === 'success'` and read `res.result`.
Stream: `const s = run.stream({ inputData }); for await (const c of s.fullStream) {...}; await s.result`.
CLI (needs `mastra dev` running): `npx mastra api workflow run start tap-workflow '{"inputData":{"taps":2}}'`.
Registration key vs id: `mastra.getWorkflow('tapWorkflow')` (key, full type inference) vs `getWorkflowById('tap-workflow')`.
Other control flow: `.parallel()`, `.branch()`, loops, `stateSchema` + `setState`, suspend/resume, `cloneWorkflow`.

### 4.5 Memory

- Message history is on by default once `memory` + storage exist. Pass `memory: { resource, thread }` per call.
- **Working memory** (structured user facts), **semantic recall** (needs vector store + embedder),
  **Observational Memory** (recommended for long sessions: `new Memory({ options: { observationalMemory: true } })`).
- Gotcha: a thread's owner `resourceId` can't change. Don't reuse a thread id across users.
- Gotcha: Observational Memory needs a storage adapter that supports it. With any other adapter it **turns off without a warning**.

### 4.6 Voice

Packages: `@mastra/voice-openai`, `@mastra/voice-openai-realtime`, `@mastra/voice-elevenlabs`, `@mastra/voice-deepgram`,
`@mastra/voice-google`, `@mastra/voice-azure`, plus others (Cloudflare, Gladia, Inworld, LiveKit, Murf, Sarvam, Speechify, xAI, AWS Nova Sonic, Mistral).
ElevenLabs and Deepgram are also event sponsors.

```ts
import { Agent } from '@mastra/core/agent'
import { OpenAIVoice } from '@mastra/voice-openai'
import { createReadStream } from 'node:fs'

const voiceAgent = new Agent({
  id: 'voice-agent', name: 'Voice Agent',
  instructions: 'Short spoken answers.',
  model: 'openai/gpt-5-mini',
  voice: new OpenAIVoice(),                // needs OPENAI_API_KEY
})

// STT: a WAV recorded by the band (e.g. recording.wav from record_band.py)
const transcript = await voiceAgent.voice.listen(createReadStream('./recording.wav'))
const { text } = await voiceAgent.generate(transcript)
// TTS: returns an audio stream; pipe to a file or HTTP response
const audio = await voiceAgent.voice.speak(text, { speaker: 'default', responseFormat: 'wav' })
```

Realtime speech-to-speech:

```ts
import { OpenAIRealtimeVoice } from '@mastra/voice-openai-realtime'
import { playAudio, getMicrophoneStream } from '@mastra/node-audio'
// agent with voice: new OpenAIRealtimeVoice()
voiceAgent.voice.on('speaker', ({ audio }) => playAudio(audio))
voiceAgent.voice.on('writing', ({ text, role }) => console.log(`${role}: ${text}`))
await voiceAgent.voice.connect()
await voiceAgent.voice.speak('How can I help?')
await voiceAgent.voice.send(getMicrophoneStream())   // or a stream fed from the band's mic audio
```

`CompositeVoice` mixes providers (e.g. Deepgram STT + ElevenLabs TTS). See `reference/voice/composite-voice`.

### 4.7 MCP (client and server, `@mastra/mcp`)

Both speak MCP revision `2026-07-28` over **stdio** and **Streamable HTTP**.

Client: use other MCP servers' tools in an agent.

```ts
import { MCPClient } from '@mastra/mcp'
export const mcp = new MCPClient({
  id: 'band-mcp-client',
  servers: {
    wikipedia: { command: 'npx', args: ['-y', 'wikipedia-mcp'] },              // stdio
    remote: { url: new URL('https://example.com/mcp'),                          // HTTP
              requestInit: { headers: { Authorization: `Bearer ${process.env.X_KEY}` } } },
  },
})
// static:  tools: await mcp.listTools()           (names prefixed: remote_get_weather)
// runtime: agent.generate(p, { toolsets: await mcp.listToolsets() })   then mcp.disconnect()
// approval: servers.x.requireToolApproval = true | ({ toolName }) => toolName.startsWith('delete_')
```

Server: expose your agents, tools and workflows to other MCP clients.

```ts
import { MCPServer } from '@mastra/mcp'
export const mcpServer = new MCPServer({
  id: 'band-mcp', name: 'Band MCP', version: '1.0.0',
  agents: { bandAgent },          // becomes tool ask_bandAgent
  tools: { bandStateTool },
  workflows: { tapWorkflow },     // becomes tool run_tapWorkflow
})
// new Mastra({ mcpServers: { mcpServer } })  -> served at /api/mcp/mcpServer/mcp (Streamable HTTP)
```

**Built-in MCP server** (no code): with `@mastra/mcp` installed, `mastra dev` serves every registered agent, workflow and tool at
`/api/mcp`, with no auth in dev. Tools: `list_agents`, `get_agent`, `call_agent`, `list_workflows`, `start_workflow`, `get_workflow_run`, ...,
`tool_<id>`. A production build needs `server.auth` (bearer token). Without it the endpoint returns 404 unless `server.mcp.enabled: true`.

```powershell
claude mcp add --transport http mastra http://localhost:4111/api/mcp
```

### 4.8 Browser client (`@mastra/client-js`)

```ts
import { MastraClient } from '@mastra/client-js'
const client = new MastraClient({ baseUrl: 'http://localhost:4111' })
const r = await client.getAgent('bandAgent').generate('Hello')     // registration key
console.log(r.text)
```

## 5. Deploy (Mastra platform, formerly Mastra Cloud)

```powershell
npm install -g mastra@latest
mastra auth login
mastra build                 # bundles a Hono server to .mastra/output (mastra start serves it)
mastra deploy                # creates project + 'production' env on first run, streams logs, prints URL
mastra deploy --env staging --region eu    # region us|eu, fixed at env creation
```

- Dashboard: https://projects.mastra.ai. First deploy writes `.mastra-project.json`. Commit it.
- The platform **does not host a DB by default**. Preflight blocks `file:./mastra.db` and offers
  `mastra env db create production --kind turso` (managed Turso). Guard local paths with env vars (see 4.3).
- Older split commands `mastra server deploy` / `mastra studio deploy` still work. `mastra deploy` is recommended.
- Verify with `<url>/api/agents`. **Set up auth before exposing endpoints** (docs warning).
- Alternatives: any Node host (`mastra build` + `mastra start`), framework integration (Next.js, Vite, Express, Hono...).

## 6. Studio (local dev playground)

- `mastra dev` -> http://localhost:4111. Agents tab: chat, switch models, temperature, tool call traces, memory sidebar.
  Workflows tab: graph view, auto-generated input form from `inputSchema`, live step status, time travel.
  Tools tab: run tools on their own. MCP Servers page: shows "Mastra (built-in)" with copy-paste Claude Code setup.
- `mastra dev --request-context-presets ./presets.json` adds a dropdown of request-context presets.
- Hosted Studio: `mastra deploy`, or `mastra studio deploy`. Browser-only agent creation: https://agent-builder.mastra.ai.

## 7. Official docs MCP server (`@mastra/mcp-docs-server`)

- Package: `@mastra/mcp-docs-server` (npm). Transport: **stdio**, run through `npx`. Auth: **none**.
- Claude Code install, as printed in the docs (project scope, writes `.mcp.json`):

```bash
claude mcp add --scope project mastra -- npx -y @mastra/mcp-docs-server@latest
```

- **Windows note (Claude Code docs, not Mastra):** on native Windows, `npx`-based stdio servers usually need a `cmd /c` wrapper:
  `claude mcp add --scope project mastra -- cmd /c npx -y @mastra/mcp-docs-server@latest`
- Generic JSON: `{"mcpServers":{"mastra":{"type":"stdio","command":"npx","args":["-y","@mastra/mcp-docs-server@latest"]}}}`
- Remote alternative: `https://mastra.mcp.kapa.ai` (Kapa-hosted). It needs **Google account sign-in** for rate limiting (only an anonymous ID is sent).
  Mastra recommends the local server instead. My construction, not in the docs:
  `claude mcp add --transport http mastra-docs-remote https://mastra.mcp.kapa.ai` (**unverified**).
- Docs warning: the MCP docs server "isn't recommended for everyday development". Use the **Mastra skill**
  (`npx skills add mastra-ai/skills`) instead. Keep the MCP server for MCP-only tools such as the migration tool.
- Env vars: `DEBUG=1` (verbose stderr), `REBUILD_DOCS_ON_START=true`. These come from an older reference page. **May be stale.**
- Docs are also bundled in every installed package at `node_modules/@mastra/*/dist/docs` (SKILL.md + references),
  and any page is available as Markdown by appending `.md` (e.g. `https://mastra.ai/docs/agents/overview.md`). Index: https://mastra.ai/llms.txt.

## 8. Limits and gotchas

General:
- Tools must be `createTool(...)`. Plain objects silently don't execute. `execute(inputData, context)` is the only signature.
- Model strings are `provider/model`. `openai:gpt-x` or passing provider objects is outdated guidance (still works via AI SDK, but the docs steer away from it).
- `mastra.getAgentById('id')` vs `mastra.getAgent('registrationKey')`. Client-js `getAgent` uses the registration key.
  A directly imported agent works but misses instance storage and logging.
- File-based agents (`src/mastra/agents/<name>/config.ts` + `instructions.md`) are only discovered by `mastra dev` / `mastra build`,
  not when you import `mastra` from your own script.
- Built-in `/api/mcp` in dev **rejects a foreign Origin/Host** (DNS-rebinding guard). Tunnels (ngrok) and LAN IPs are blocked unless
  you set `server.host` to the hostname clients use. Binding `0.0.0.0` alone doesn't help.
- MCP tool results are untrusted input. Use `requireToolApproval` and processors for risky tools.
- Deploys replace the server process and can cut streaming turns. Use durable agents if that matters (it probably doesn't for a 1-day demo).
- Telemetry: the CLI sends anonymous usage data. Opt out with `MASTRA_TELEMETRY_DISABLED=1`.

Windows-specific:
- **Env var prefix syntax in the docs is bash.** In PowerShell use `$env:MASTRA_TELEMETRY_DISABLED='1'; npx create-mastra@latest ...`.
- `ERR_UNSUPPORTED_ESM_URL_SCHEME ... Received protocol 'c:'` when `mastra dev` starts: this was a Windows path bug fixed in Jan 2026
  (mastra PR #11340). Fix: update `mastra` and `@mastra/*` to latest.
- `[GatewayRegistry] Failed to write to global cache` (EPERM/EBUSY from Defender or the indexer on `~/.cache/mastra/provider-registry.json`):
  this is harmless (Studio uses stale cache), and Aug 2026 `@mastra/core` builds retry the write (PR #21425). Update core.
- Starter workspace path: on Windows, `mastra dev` resolved a relative `workspace` to `src/mastra/public/workspace` (issue #22740,
  CLI 1.27.2). Use absolute paths for workspace and data files.
- `@mastra/node-audio` (`playAudio`, `getMicrophoneStream`) wraps native speaker and mic libs and needs **ffmpeg on PATH**
  (`choco install ffmpeg` / `winget install ffmpeg`). Native builds can fail on Windows. For the band, prefer sending the
  band's WAV/PCM to `voice.listen()` and returning TTS audio to the browser over relying on node-audio.
- Claude Code + `npx` stdio MCP servers on native Windows: use `cmd /c npx ...` (see section 7).
- Building the Mastra monorepo from source on Windows had path-separator bugs. Use the published npm packages, not a source build.

## 9. Link list

- Docs home / quickstart: https://mastra.ai/docs
- Docs index for agents: https://mastra.ai/llms.txt (full: https://mastra.ai/llms-full.txt)
- Develop (mastra dev, skills, CLI): https://mastra.ai/docs/develop
- create-mastra reference: https://mastra.ai/reference/cli/create-mastra
- CLI reference: https://mastra.ai/reference/cli/mastra
- Agents: https://mastra.ai/docs/agents/overview | Tools: https://mastra.ai/docs/agents/tools | Structured output: https://mastra.ai/docs/agents/structured-output
- Agent class: https://mastra.ai/reference/agents/agent | generate(): https://mastra.ai/reference/agents/generate | createTool: https://mastra.ai/reference/tools/create-tool
- Workflows: https://mastra.ai/docs/workflows/overview | Control flow: https://mastra.ai/docs/workflows/control-flow | Step: https://mastra.ai/reference/workflows/step
- Memory: https://mastra.ai/docs/memory/overview | Storage: https://mastra.ai/docs/storage | libSQL: https://mastra.ai/integrations/databases/libsql
- Voice overview: https://mastra.ai/reference/voice/overview | OpenAI: https://mastra.ai/integrations/voice/openai | ElevenLabs: https://mastra.ai/integrations/voice/elevenlabs | Deepgram: https://mastra.ai/integrations/voice/deepgram
- MCP: https://mastra.ai/docs/connections/mcp | MCPClient: https://mastra.ai/reference/tools/mcp-client | MCPServer: https://mastra.ai/reference/tools/mcp-server
- Built-in MCP server: https://mastra.ai/docs/server/mcp
- Custom API routes: https://mastra.ai/docs/server/custom-api-routes | Mastra client: https://mastra.ai/docs/server/mastra-client
- Studio: https://mastra.ai/docs/studio/overview
- Mastra platform: https://mastra.ai/docs/mastra-platform/overview | Deploy: https://mastra.ai/docs/mastra-platform/deploy | Dashboard: https://projects.mastra.ai
- Mastra Cloud -> platform migration: https://mastra.ai/reference/migrations/mastra-cloud
- Docs MCP server / Build with AI: https://mastra.ai/docs/build-with-ai/mcp-docs-server (redirects to https://mastra.ai/reference/build-with-ai)
- Models directory: https://mastra.ai/models | Env var names: https://mastra.ai/models/environment-variables
- Templates: https://mastra.ai/templates | Skills repo: https://github.com/mastra-ai/skills
- node-audio: https://github.com/mastra-ai/node-audio
- Hackathon page: https://vexoai.com/hackathon
