# VexoHacks sponsor docs (2026-11-14)

Digests of each sponsor's developer docs, written from official sources on hack day. MiniMax left out on purpose.
Each file marks anything not confirmed on an official page as **[UNVERIFIED]**.

| Sponsor | Tier / track | File | MCP in `.mcp.json` | Auth |
|---|---|---|---|---|
| Google DeepMind (Gemini 4) | Platinum, "Best use of Gemini 4" | [gemini.md](gemini.md) | `gemini-docs` (docs only) | none |
| Stripe | Platinum, "Best Economic Agent" | [stripe.md](stripe.md) | `stripe` (real API, pick a sandbox) | OAuth via `/mcp` |
| Brex | Gold | [brex.md](brex.md) | `brex` (mostly read; no sandbox, real money) | OAuth via `/mcp` |
| Deepgram | Gold, "Best Voice Use Case on Pipecat" | [deepgram.md](deepgram.md) | `deepgram-docs` (docs only) | none |
| Pipecat (voice track framework) | used by the Deepgram track | [pipecat.md](pipecat.md) | `pipecat-docs` (docs only) | none |
| Marv Labs | Gold, cameras at the event | [marvlabs.md](marvlabs.md) | none exists | - |
| Mastra | Silver | [mastra.md](mastra.md) | `mastra-docs` (docs only, stdio via npx) | none |
| Superserve | Silver, $100 credits code `VEXOHACKS` | [superserve.md](superserve.md) | `superserve-docs` (docs only) | none |
| OpenAI | Credits, overall prizes | [openai.md](openai.md) | `openai-docs` (docs only) | none |
| ElevenLabs | Credits, "Best ElevenLabs Project" | [elevenlabs.md](elevenlabs.md) | `elevenlabs` (full hosted server; uses workspace credits) | OAuth via `/mcp` |

Not installed (need a key or heavy setup): Superserve sandbox MCP (`SUPERSERVE_API_KEY`), Deepgram `dg mcp`
(`DEEPGRAM_API_KEY`, billed), Pipecat Context Hub (~900 MB local index), Mastra app MCP (`http://localhost:4111/api/mcp`, once a Mastra app runs).

Key facts that bite:
- Model IDs moved this year: Gemini `gemini-4-hydrogen` (free tier), OpenAI `gpt-6-luna` (cheap) / `gpt-realtime-2.1`,
  ElevenLabs `eleven_flash_v2_5` / `eleven_v4`, Deepgram `nova-3` / `flux-general-en`.
- Band audio is 16 kHz mono PCM after decoding: matches Gemini Live input, ElevenLabs Agents and Pipecat; OpenAI Realtime wants 24 kHz.
- Pipecat 1.16 needs Python 3.11+ and renamed `PipelineTask/PipelineRunner` to `PipelineWorker/WorkerRunner`.
- Stripe MCP stops accepting plain secret keys in December 2026: use OAuth or an agent-tagged key.
- Submissions close 6 PM Pacific: public GitHub repo + README, video demo, Devpost.
