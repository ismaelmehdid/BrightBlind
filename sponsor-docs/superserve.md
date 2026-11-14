# Superserve - developer digest

Sponsor offer: **$100 credits with code `VEXOHACKS`** at https://console.superserve.ai.
Researched 2026-11-14 from superserve.ai, docs.superserve.ai and github.com/superserve-ai.
Items marked **[unverified]** were not confirmed on an official page.

---

## 1. What it is

Superserve is **cloud sandbox infrastructure for AI agents**: isolated **Firecracker microVMs** that start in
seconds (the marketing site says milliseconds). It provides:

- **Commands:** run shell commands and stream their output, plus interactive processes with stdin.
- **Files:** read and write files, upload and download directories.
- **Pause and resume:** memory, disk and running processes are kept intact. Compute billing stops while a sandbox is paused.
- **Snapshots and forks:** save a sandbox's state, then start new sandboxes from it.
- **Templates:** custom base images with preinstalled dependencies and a chosen vCPU/memory/disk shape.
- **Preview URLs:** publish a sandbox port as a public or private HTTPS URL.
- **Secrets:** a sandbox gets a stand-in token, and the platform swaps in the real API key on outbound requests to allowed hosts.
- **Network rules:** per-sandbox egress allow/deny lists, plus a network log.
- **Desktop / computer use:** GUI sandboxes (template `superserve/desktop`).

The SDKs are open source (Apache-2.0): https://github.com/superserve-ai/superserve
(`packages/python-sdk` = PyPI `superserve`, `packages/sdk` = npm `@superserve/sdk`, `packages/cli` = `@superserve/cli`).

> Note: older Superserve docs (around March 2026) described an *agent deployment* product
> (`superserve deploy agent.py`, `superserve sessions ...`). That surface is **not** in the current docs index
> (docs.superserve.ai/llms.txt). The product today is sandboxes. Do not build on `superserve deploy`.

## 2. What it is good for at VexoHacks

- **Run model-generated code safely.** Let Gemini write Python (for example a gesture classifier or a plot of accelerometer data) and execute it
  in a sandbox instead of on the laptop ("code interpreter" guide).
- **Host the demo backend.** Run a FastAPI/WebSocket server or a static dashboard in a sandbox and share it via a preview URL,
  so judges can open it from their phones.
- **Persistent agent workspace.** Pause the sandbox between demo runs and resume it with state intact.
- **Parallel evals.** Run one sandbox per trial when testing prompts or gesture models.
- **Give Claude Code / your agent a sandbox** through the Superserve MCP server (section 8).

## 3. Account, credits and API key

1. Sign up at https://console.superserve.ai (free, no card required). A new account gets a limited free trial for its first sandbox.
2. **Redeem `VEXOHACKS`.** The docs do not describe where to enter promo codes. Look in the console's billing/credits
   section [unverified]. A billing summary API with `credits_applied_usd` and `credits_remaining_usd` exists, so credits
   show up there.
3. **API Keys** page, then **Create Key**. The key is shown once. It looks like `ss_live_<region>_<random>` and is scoped to one team.
4. Set the env var:
   ```powershell
   $env:SUPERSERVE_API_KEY = "ss_live_..."     # this shell
   setx SUPERSERVE_API_KEY "ss_live_..."        # persist (open a new terminal)
   ```

- The SDKs read `SUPERSERVE_API_KEY`, or the `api_key` / `apiKey` option.
- `superserve login` (CLI) saves its *own* key to `~/.superserve/credentials.json`. **The SDKs do not read that file.**
- Regions: keys starting `ss_live_use_` use `https://api.superserve.ai`, and `ss_live_usw_` keys use `https://api-usw.superserve.ai`.
  The SDK infers the region from the key. A key used against the wrong region returns `401 wrong_region`.
- REST: send the header `X-API-Key: $SUPERSERVE_API_KEY` to the API URL. Exec and file endpoints instead go to `https://sandbox.superserve.ai`
  (or `usw-sandbox...`) with `X-Superserve-Sandbox-Id` and `X-Access-Token` (the sandbox's `access_token`).

## 4. Install

```powershell
pip install superserve            # Python SDK (Python 3.12 OK; integrations require 3.11+)
npm install @superserve/sdk       # TypeScript/JS SDK (Node 18+ per older SDK page [unverified for current])
npm install -g @superserve/cli    # CLI via npm, needs Node.js >= 22.4
```

**Windows note:** the `curl -fsSL https://superserve.ai/install | sh` script downloads a **macOS or Linux** binary, and
Homebrew is macOS/Linux only. On Windows 11, use the **npm CLI** (`@superserve/cli`) or run the script inside WSL.
Native Windows support for the npm CLI is not stated in the docs [unverified]. The Python SDK is pure HTTP and should
work on Windows [unverified, but nothing indicates otherwise].

## 5. Quickstart (Python)

```python
from superserve import Sandbox

sandbox = Sandbox.create(name="quickstart")          # default template: superserve/base

result = sandbox.commands.run("echo 'Hello from Superserve!'")
print(result.stdout)

sandbox.files.write("/tmp/hello.txt", "Hello, world!")
print(sandbox.files.read_text("/tmp/hello.txt"))

sandbox.kill()                                        # permanent delete
```

TypeScript:
```typescript
import { Sandbox } from "@superserve/sdk"

const sandbox = await Sandbox.create({ name: "quickstart" })
const result = await sandbox.commands.run("echo 'Hello from Superserve!'")
console.log(result.stdout)
await sandbox.files.write("/tmp/hello.txt", "Hello, world!")
console.log(await sandbox.files.readText("/tmp/hello.txt"))
await sandbox.kill()
```
Save the TypeScript as `index.mts` (top-level await) and run it with `npx tsx index.mts`.

## 6. Key Python APIs

### Sandbox.create

```python
Sandbox.create(
    name: str,
    from_template: str | Template | None = None,   # e.g. "superserve/python-3.11", "superserve/desktop"
    from_snapshot: str | Snapshot | None = None,
    timeout_seconds: int | None = None,             # cap on ACTIVE time, then auto-pause (unset = never)
    idle_timeout_seconds: int | None = None,        # auto-pause after N s idle (60..604800)
    auto_delete_seconds: int | None = None,         # delete after N s continuously paused (max 30 days)
    metadata: dict[str, str] | None = None,
    env_vars: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,          # {ENV_VAR_NAME: secret_name}
    network: NetworkConfig | None = None,
    preview_access: Literal["public", "private"] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
)
```

Other entry points: `Sandbox.connect(id)`, `Sandbox.list(metadata=..., status="active", limit=, offset=)`,
`sandbox.pause(wait=False)`, `sandbox.resume()`, `sandbox.kill()`, `sandbox.snapshot(name="before-demo")`.
For async code use `from superserve import AsyncSandbox, AsyncSnapshot, async_connection_pool`.

### Commands

```python
import sys

r = sandbox.commands.run("python script.py", cwd="/app",
                         env={"PORT": "3000"}, timeout_seconds=60)
if r.exit_code != 0:                     # a non-zero exit is NOT an exception; check exit_code
    print("failed:", r.stderr)

# streaming
r = sandbox.commands.run("pip install numpy",
                         on_stdout=lambda d: sys.stdout.write(d),
                         on_stderr=lambda d: sys.stderr.write(d),
                         timeout_seconds=300)
```

Long-running or interactive processes use `commands.spawn`, which is **async-only in Python** (it needs `AsyncSandbox`):
```python
import asyncio
from superserve import AsyncSandbox

async def main():
    sb = await AsyncSandbox.create(name="repl")
    async with await sb.commands.spawn("python3 -i", on_stdout=lambda d: print(d, end="")) as s:
        await s.stdin.write("print(2 + 2)\n")
        await s.stdin.close()
        print("exited", (await s.wait()).exit_code)
    await sb.kill()

asyncio.run(main())
```
With the sync SDK, a simple workaround for background servers is `nohup ... &` inside `commands.run`. The official CLI
example does the same.

### Preview URLs (share a demo server)

```python
import asyncio
from superserve import AsyncSandbox

async def main():
    sb = await AsyncSandbox.create(name="vexo-dash", from_template="superserve/python-3.11",
                                   preview_access="public")
    await sb.files.write("/home/user/app/index.html", "<h1>Vexo live</h1>")
    await sb.commands.spawn("cd /home/user/app && python3 -m http.server 3000")
    await sb.publish_preview_port(3000, access="public")
    print(sb.get_preview_url(3000))        # not awaited
asyncio.run(main())
```
- URL format: `https://{port}-{sandbox_id}.<sandbox-domain>`. Only published ports are reachable. Other ports return 404.
- `access="private"` requires a minted token header, or a signed URL via MCP (default 1 h, up to 7 days).
- Sync versions: `sandbox.publish_preview_port(port, access=...)`, `get_preview_url`, `list_preview_ports`, `unpublish_preview_port`.
- WebSocket support over preview URLs is not explicitly documented [unverified]. The older docs mentioned WebSockets for HTTP-server mode.

### Secrets (for example a Gemini key that never enters the sandbox)

```python
import os
from superserve import Secret, Sandbox

Secret.create(                                   # custom header scheme for Gemini (no provider shortcut verified)
    name="gemini-key",
    value=os.environ["GEMINI_API_KEY"],
    hosts=["generativelanguage.googleapis.com"],
    auth={"type": "api-key", "header": "x-goog-api-key", "prefix": ""},   # prefix "" [unverified]
)
sb = Sandbox.create(name="agent", secrets={"GEMINI_API_KEY": "gemini-key"})
```
Inside the sandbox, `GEMINI_API_KEY` holds a **stand-in token**. The platform replaces it with the real value only on requests
to the secret's `hosts`. Provider shortcuts exist (`provider="openai"` sets the hosts to `api.openai.com`). A Google/Gemini shortcut is
[unverified]. Simpler but less safe: `env_vars={"GEMINI_API_KEY": ...}` puts the real key inside the VM.

### Network rules

```python
from superserve import Sandbox, NetworkConfig
sb = Sandbox.create(name="locked", network=NetworkConfig(
    allow_out=["generativelanguage.googleapis.com", "1.1.1.1/32", "8.8.8.8/32"],
    deny_out=["0.0.0.0/0"]))
```
For a strict allowlist, always pair `allow_out` with `deny_out: ["0.0.0.0/0"]`, and allow the DNS resolvers
(`1.1.1.1/32` and `8.8.8.8/32`) whenever you use domain rules.

## 7. CLI cheatsheet

```bash
superserve login                 # browser approval; --no-browser / --no-wait for headless
superserve whoami
superserve sandbox create --name demo --template superserve/python-3.11
superserve exec demo -- python3 -c "print('hello')"
superserve cp ./app demo:/home/user/app
superserve exec demo "cd /home/user/app && nohup python3 -m http.server 3000 >/dev/null 2>&1 &"
superserve preview publish demo 3000 --open
superserve shell demo
superserve sandbox list --status active --json
superserve sandbox pause demo
superserve sandbox delete demo
echo "$SUPERSERVE_API_KEY" | superserve login --with-key
```
Add `--json` to any data command for machine-readable output. If `SUPERSERVE_API_KEY` is set, the CLI uses it instead of its saved key.

## 8. MCP servers (official)

### A. Superserve sandbox MCP (does real work: creates and drives sandboxes)

| | Local | Hosted |
|---|---|---|
| Package / URL | npm `@superserve/mcp` (bin `superserve-mcp`) | `https://mcp.superserve.ai` |
| Transport | stdio | Streamable HTTP |
| Auth | env `SUPERSERVE_API_KEY` | `Authorization: Bearer <SUPERSERVE_API_KEY>` (no OAuth yet) |

Claude Code (verbatim from docs, with a placeholder key):
```bash
# local (stdio)
claude mcp add superserve \
  --env SUPERSERVE_API_KEY=ss_live_xxxxxxxxxxxxxxxx \
  -- npx -y -p @superserve/mcp superserve-mcp

# hosted (http)
claude mcp add --transport http superserve https://mcp.superserve.ai \
  --header "Authorization: Bearer ss_live_xxxxxxxxxxxxxxxx"
```
MCP clients do **not** inherit the key from your shell, so pass it explicitly. On Windows, the stdio `npx` launch may need a
`cmd /c` wrapper in some clients [unverified for Claude Code].

Tools: `sandbox_create`, `sandbox_update`, `sandbox_list`, `sandbox_info`, `sandbox_exec`, `sandbox_files_read`,
`sandbox_files_write`, `sandbox_files_list`, `sandbox_files_download_dir`, `sandbox_pause`, `sandbox_resume`,
`sandbox_kill`, `sandbox_preview_url`, `sandbox_network_log`, `sandbox_computer`, `sandbox_template_list`,
`sandbox_template_create`, `secret_list`, `sandbox_attach_secret`, `sandbox_detach_secret`.

Limits:
- `sandbox_exec` stdout and stderr are each capped at about 32 KiB (the middle is truncated). The default timeout is 60 s and the maximum is 10 min (`timeout_ms`).
- `sandbox_files_read` rejects files over 1 MiB. Inline writes are limited to 8 MiB locally and about 4 MB on the hosted server.
- Directory download is capped at 10 MiB.
- Not available over MCP: secret creation, streaming or interactive commands (`spawn`), and billing.

### B. Superserve docs MCP (documentation search only)

- URL: `https://docs.superserve.ai/mcp`. Transport: **http**. Auth: **none** (public, read-only). It is a Mintlify-hosted
  server with the tools `search_superserve`, `query_docs_filesystem` and `submit_feedback`. Confirmed by fetching the endpoint.
- The docs say to add it from the "menu at the top right of any page". The exact command below is the standard form and was
  **not printed verbatim** in the docs:
  ```bash
  claude mcp add --transport http superserve-docs https://docs.superserve.ai/mcp
  ```

## 9. Pricing and limits

| Plan | Price | Included usage | Concurrency | Max per sandbox |
|---|---|---|---|---|
| Free trial | $0, no card | limited trial for the first sandbox | - | - |
| Developer | $20/mo | $20 | 100 sandboxes | 4 vCPU / 16 GiB |
| Pro | $250/mo | $250 | 2,000 | 16 vCPU / 64 GiB |
| Enterprise | custom | - | custom | custom, BYOC |

Usage rates (the same on every plan, billed per second):
- **vCPU:** $0.0504 per hour.
- **Memory:** $0.0162 per GiB-hour.
- **Storage:** $0.000108 per GiB-hour. Copy-on-write: you pay for the template once plus each sandbox's diffs, and storage is billed while paused.

Rough estimate: a 1 vCPU / 1 GiB sandbox costs about $0.067/h, so $100 of credits covers about 1,500 sandbox-hours.

Template build defaults: 1 vCPU, 1024 MiB memory, 4096 MiB disk.

## 10. Gotchas

1. The CLI's `superserve login` key **is not used by the SDKs**. Set `SUPERSERVE_API_KEY` yourself.
2. **Pausing preserves state and storage is still billed.** `kill()` deletes permanently, and `auto_delete_seconds` can clean up for you.
3. Set `idle_timeout_seconds` (for example 600) during the hackathon so forgotten sandboxes stop burning credits.
4. A non-zero exit code is returned in the result (`exit_code`), not raised as an exception.
5. Python `commands.spawn` is **async-only** (`AsyncSandbox`).
6. vCPU and memory come from the **template**. You cannot override them in `Sandbox.create`, so build a template for a bigger shape.
7. A deny-all egress rule also blocks DNS. Allow `1.1.1.1/32` and `8.8.8.8/32` when you use domain rules.
8. Windows: there is no native install-script binary. Use the npm CLI or WSL.
9. Region-bound keys: `usw` keys fail against the default API URL. Let the SDK infer the URL instead of hardcoding it.

## 11. Example: Gemini writes code, Superserve runs it

```python
from google import genai
from superserve import Sandbox

gem = genai.Client()
code = gem.interactions.create(
    model="gemini-4-hydrogen",
    input="Write a Python script (stdlib only) that prints the mean and max of [0.1, 0.9, 2.3, 0.4]. Output only code.",
    generation_config={"thinking_level": "low"},
).output_text.strip().removeprefix("```python").removesuffix("```")

sb = Sandbox.create(name="gemini-exec", from_template="superserve/python-3.11", idle_timeout_seconds=600)
try:
    sb.files.write("/home/user/job.py", code)
    r = sb.commands.run("python3 /home/user/job.py", timeout_seconds=60)
    print(r.exit_code, r.stdout, r.stderr)
finally:
    sb.kill()
```

## 12. Sources

- https://superserve.ai (agent-facing summary: CLI, SDK, REST and MCP endpoints)
- https://superserve.ai/agent-hosting
- https://www.superserve.ai/pricing/
- https://docs.superserve.ai (introduction)
- https://docs.superserve.ai/llms.txt
- https://docs.superserve.ai/quickstart.md
- https://docs.superserve.ai/api-key.md
- https://docs.superserve.ai/cli.md
- https://docs.superserve.ai/integrations/mcp.md
- https://docs.superserve.ai/mcp (docs MCP endpoint)
- https://docs.superserve.ai/sdk-reference/sandbox.md
- https://docs.superserve.ai/commands/overview.md
- https://docs.superserve.ai/commands/streaming.md
- https://docs.superserve.ai/commands/sessions.md
- https://docs.superserve.ai/sandbox/lifecycle.md
- https://docs.superserve.ai/sandbox/preview-urls.md
- https://docs.superserve.ai/secrets/binding.md
- https://docs.superserve.ai/secrets/create.md
- https://docs.superserve.ai/integrations/agent-harnesses/google-adk.md
- https://docs.superserve.ai/integrations/agent-harnesses/langchain
- https://github.com/superserve-ai/superserve
