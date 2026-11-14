# Stripe: developer digest for VexoHacks (2026-11-14)

Track: **"Build an agent that can safely participate in the economy" (Best Economic Agent)**.
Perk: **$500 in Stripe credits** (offsets Payments/Connect/Billing fees) plus free Atlas incorporation; **new Stripe users only**.
Benefits page: https://stripe.com/startup-benefits/vexohacks. Stripe's hackathon cheat sheet: https://shipbysundown.dev/

All facts below come from docs.stripe.com, docs.link.com, mpp.dev, github.com/stripe/* and stripe.com, read on 2026-11-14.
Items marked **[UNVERIFIED]** are my inference and have not been checked against a doc page.

---

## 0. TL;DR for the team

- **MCP:** use the hosted server `https://mcp.stripe.com` (Streamable HTTP). In Claude Code:
  `claude mcp add --transport http stripe https://mcp.stripe.com/`, then run `/mcp` inside Claude Code to sign in with OAuth.
  You pick a **sandbox** in the OAuth consent screen.
- **Do not use `@stripe/mcp` or `stripe-agent-toolkit` for new work.** The stripe/ai README now marks both as deprecated,
  with no further updates or security fixes. It points people to the hosted MCP instead.
- **Deadline:** from **December 2026**, Stripe MCP stops accepting full-access secret keys (`sk_...`) and restricted keys
  that lack the **Agent** tag. Use OAuth or an **agent API key** (a restricted key created with the intended use
  "Authorizing agent access to your account").
- **Fastest money demo:** a Payment Link or a Checkout Session in test mode, paid with test card `4242 4242 4242 4242`.
- **Best fits for the "safe economic agent" track:**
  1. **Stripe Issuing for agents**: give the agent its own virtual card with spend limits, allowed merchant categories and a
     real-time authorization webhook that can approve or decline each charge. A wristband tap can act as the human approval.
  2. **Link Agent Wallet**: the agent creates a *spend request*, the human approves it, and the agent gets a one-time card
     or a Shared Payment Token (SPT). US and Canada customers only.
  3. **Machine Payments (MPP / x402)**: the agent pays per API call through HTTP 402 challenges, or you sell your own API to agents.
- **Fastest keys:** `stripe sandbox create` provisions a sandbox with test keys without an account. The sandbox expires after
  7 days unless you claim it.

---

## 1. MCP servers

| Item | Value |
|---|---|
| Official server | `https://mcp.stripe.com` (hosted by Stripe; "Public preview") |
| Transport | HTTP (Streamable HTTP), shown as `--transport http` / `"type": "http"` in Stripe's configs |
| Auth option 1 (recommended) | **OAuth.** The client opens Stripe's consent page, where you choose live accounts and/or sandboxes and set permissions for each environment |
| Auth option 2 | **Agent API key** as `Authorization: Bearer <key>`. Create it as a restricted key and choose "Authorizing agent access to your account". It shows an **Agent** badge in the Dashboard |
| Connected accounts | Use an agent API key plus the `Stripe-Account: acct_...` header (OAuth is not supported for this case) |
| Admin control | Dashboard > Settings > MCP and CLI access (https://dashboard.stripe.com/settings/mcp-and-cli-access); set live and sandbox separately |
| Revoke sessions | Dashboard > user settings > **OAuth sessions** > Revoke access |

### Claude Code install (official command from docs.stripe.com/mcp)

```bash
claude mcp add --transport http stripe https://mcp.stripe.com/
# then inside Claude Code:
/mcp        # complete the OAuth login; choose a sandbox
```

To use an agent API key instead of OAuth (for headless runs), put this in the project's `.mcp.json` and keep the key in an env var.
Never write the key into the file.

```json
{
  "mcpServers": {
    "stripe": {
      "type": "http",
      "url": "https://mcp.stripe.com",
      "headers": { "Authorization": "Bearer ${STRIPE_AGENT_API_KEY}" }
    }
  }
}
```

The Windows/PowerShell env var for that file: `$env:STRIPE_AGENT_API_KEY = "rk_test_..."`. The `rk_test_` prefix for agent keys
is **[UNVERIFIED]**: agent keys are a kind of restricted key, and restricted sandbox keys start with `rk_test_`.

### Recommended alternative: the agent plugin (installs MCP plus Stripe "skills")

```powershell
irm https://cli.stripe.com/install.ps1 | iex     # Windows installer for the Stripe CLI (from docs)
# open a NEW terminal, then:
stripe agent setup                               # detects your agents (Claude Code, Cursor, Codex...) and configures them
```

### Tools exposed by mcp.stripe.com

| Group | Tool | Notes |
|---|---|---|
| API | `stripe_api_search` | find API methods by keyword |
| API | `stripe_api_details` | parameter details for a method |
| API | `stripe_api_read` | any `GET` |
| API | `stripe_api_write` | any `POST/PATCH/PUT/DELETE`. Some actions (for example refunds) can require **human confirmation** in the Dashboard; the approval expires after 24 h |
| Account | `get_stripe_account_info` | |
| Atlas | `atlas_company_formation` | prepares a Delaware C corp or LLC application |
| Analytics (preview) | `stripe_analytics` | metrics and natural-language-to-SQL |
| Treasury (preview) | `get_balance_summary`, `convert_currency`*, `send_money`*, `setup_recipient`, `transfer_money`* | *requires human confirmation |
| Other | `search_stripe_documentation`, `stripe_implementation_planner`, `send_stripe_feedback` | |

Issuing cardholders and cards can also be created through MCP (`stripe_api_search`, then `stripe_api_write`) if your account
has Issuing. See https://docs.stripe.com/issuing/agents/mcp

### Deprecated local package (avoid)

- `npx -y @stripe/mcp --api-key=...` is now a thin stdio-to-HTTP proxy to mcp.stripe.com. The old `--tools=all` flag is gone;
  the key's permissions decide which tools you get. The stripe/ai README marks `@stripe/mcp` as **deprecated**.
- Security guidance from the docs: turn on your MCP client's tool-approval setting, and be careful about prompt injection when
  you run Stripe MCP next to other MCP servers.

---

## 2. Why Stripe fits this hackathon

"Safely participate in the economy" maps directly onto Stripe primitives that have **built-in guardrails**:

| Guardrail you want to demo | Stripe primitive |
|---|---|
| Agent has a budget it cannot exceed | Issuing card `spending_controls.spending_limits` (per authorization, daily, monthly...) |
| Agent can only buy from certain kinds of merchants | Issuing `spending_controls.allowed_categories` (MCC categories) |
| A human approves each purchase in real time | Issuing `issuing_authorization.request` webhook (approve or decline within about **2 s** by default), or a Link Agent Wallet spend request with an approval URL |
| Credential is single-use and seller-scoped | Shared Payment Token (SPT): seller-scoped, amount-limited, time-limited |
| Agent sells its own services | Payment Links, Checkout, usage billing (meters), MPP 402 paywall |
| Sensitive admin actions need sign-off | MCP human-confirmation flow; approval rules on agent-tagged keys |

**Wearable angle (Vexo band) ideas:**
- *Tap-to-approve agent spending*: an agent proposes a purchase, the band vibrates, a double tap approves and a long hold
  declines. Your `issuing_authorization.request` handler waits for the tap. Keep it under the ~2 s timeout, or pre-approve with
  a tap before the agent checks out.
- *Voice-ordered errands*: mic audio goes to an LLM, which creates a Link spend request; the human approves on the phone; the
  agent pays with the single-use card or SPT.
- *Pay-per-use sensor API*: expose band-derived insights (for example motion classification) behind an MPP 402 paywall so other
  agents pay per call.
- *Usage-metered coaching*: meter "coaching minutes" or "inference tokens" with Billing meters and show the invoice.

---

## 3. Test mode, sandboxes and keys

- **Sandbox keys:** `pk_test_...` (publishable), `sk_test_...` (secret), `rk_test_...` (restricted). Live keys use `_live_`.
- Use a **restricted key** (or an **agent-tagged** restricted key) for anything an LLM touches.
  Agent-tagged keys are automatically subject to **approval rules**: a designated reviewer must approve sensitive actions such as
  payouts, refunds and account configuration changes.
- **Instant sandbox without an account:**

  ```bash
  stripe sandbox create --email you@example.com --non-interactive
  # prints JSON with secret_key (shown in docs as rkcs_test_...), publishable_key, claim_url, account_id, expires_at
  stripe sandbox claim     # convert to a real account within 7 days (needed to claim the $500 new-user credits) [UNVERIFIED that credits need a claimed account]
  ```
- **Test cards (Checkout quickstart):** `4242 4242 4242 4242` succeeds; `4000 0025 0000 3155` requires 3DS; `4000 0000 0000 9995`
  is declined. Use any future expiry date and any CVC.
- **Rate limits:** sandbox **25 req/s** global; live 100 req/s; most endpoints 25 req/s each; Meter Events have a separate live limit
  of 1000/s (one concurrent call per customer per meter).
- **Local webhooks:** `stripe listen --forward-to localhost:4242/webhook` prints a `whsec_...` signing secret for local testing.

---

## 4. Quickstart (Python 3.12, Windows)

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install stripe flask
$env:STRIPE_SECRET_KEY = "sk_test_..."     # placeholder: use your sandbox key, never commit it
```

The current stripe-python style (as in the Checkout quickstart) uses `StripeClient` with `client.v1.<resource>.create(params={...})`.

### 4.1 Payment Link (fastest "get paid" demo)

```python
import os, stripe

client = stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"])

product = client.v1.products.create(params={
    "name": "Vexo Focus Session",
    "default_price_data": {"currency": "usd", "unit_amount": 500},  # $5.00, in cents
})
link = client.v1.payment_links.create(params={
    "line_items": [{"price": product.default_price, "quantity": 1}],
})
print(link.url)   # open it and pay with 4242 4242 4242 4242
```

The CLI equivalent from the cheat sheet is `stripe payment_links create --line-items price=price_123`.
I have not run the Python snippet; the parameter names match the API reference (`default_price_data`, `line_items`).

### 4.2 Checkout Session (Flask, adapted from docs.stripe.com/checkout/quickstart?lang=python)

```python
import os, stripe
from flask import Flask, redirect

client = stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"])
app = Flask(__name__)
DOMAIN = "http://localhost:4242"

@app.post("/create-checkout-session")
def create_checkout_session():
    session = client.v1.checkout.sessions.create(params={
        "line_items": [{"price": "price_...", "quantity": 1}],   # placeholder Price ID
        "mode": "payment",                                        # or "subscription"
        "success_url": DOMAIN + "/success.html",
        "cancel_url": DOMAIN + "/cancel.html",
    })
    return redirect(session.url, code=303)

if __name__ == "__main__":
    app.run(port=4242)
```

### 4.3 Webhook handler (verify signatures)

```python
import os, stripe
from flask import Flask, request

app = Flask(__name__)
WHSEC = os.environ["STRIPE_WEBHOOK_SECRET"]   # whsec_... from `stripe listen`

@app.post("/webhook")
def webhook():
    try:
        event = stripe.Webhook.construct_event(
            request.data, request.headers.get("Stripe-Signature"), WHSEC)
    except (ValueError, stripe.SignatureVerificationError):
        return "bad signature", 400
    if event["type"] == "checkout.session.completed":
        print("paid:", event["data"]["object"]["id"])
    return "", 200
```

---

## 5. Agentic commerce: what exists in Nov 2026

Docs hub: https://docs.stripe.com/agentic-commerce and https://docs.stripe.com/agents

### 5.1 Issuing for agents (virtual cards for your agent): best match for "safe economic agent"

- What it is: you issue **virtual cards** to agents and control them with spend limits, MCC allow-lists, single-use lifecycle
  controls, real-time authorization webhooks and Radar risk scores.
- Access: Issuing must be activated (Dashboard > Issuing). You can activate it in a **sandbox** and simulate purchases with test
  helpers. Live access requires an application.
- Two ways for agents to pay with it:
  - **Browser checkout**: retrieve the virtual card details and type them into a card form. Prefer single-use cards.
  - **Programmatic checkout** (MPP or UCP sellers): turn the Issuing card into an **SPT**, so the agent never sees the card number.

```python
import os, stripe
client = stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"])

# 1) In a sandbox: activate Issuing and fund the test Issuing balance first (see issuing/testing)
holder = client.v1.issuing.cardholders.create(params={
    "name": "Vexo Agent", "type": "company", "status": "active",
    "email": "agent@example.com", "phone_number": "+18008675309",
    "billing": {"address": {"line1": "123 Main Street", "city": "San Francisco",
                            "state": "CA", "postal_code": "94111", "country": "US"}},
})

# 2) Virtual card with guardrails: $20 max per authorization, $100/month, only two allowed MCC categories
card = client.v1.issuing.cards.create(params={
    "cardholder": holder.id, "currency": "usd", "type": "virtual", "status": "active",
    "metadata": {"agent_id": "vexo_agent_01"},
    "spending_controls": {
        "allowed_categories": ["eating_places_restaurants", "fast_food_restaurants"],
        "spending_limits": [
            {"amount": 2000,  "interval": "per_authorization"},
            {"amount": 10000, "interval": "monthly"},
        ],
    },
})

# 3) Simulate a purchase (sandbox only): fires issuing_authorization.request and issuing_authorization.created
auth = client.v1.test_helpers.issuing.authorizations.create(params={
    "card": card.id, "amount": 1500,
    "merchant_data": {"category": "fast_food_restaurants", "name": "Taco Stand"},
})
print(auth.id, auth.approved, auth.status)

# 4) Freeze the card if the agent misbehaves
client.v1.issuing.cards.update(card.id, params={"status": "inactive"})
```

The MCC category strings `eating_places_restaurants` and `fast_food_restaurants` are **[UNVERIFIED]**; check the
"spending controls" category list. `airlines_air_carriers` and `hotels_motels_and_resorts` appear in the docs.

**Real-time approval (human-in-the-loop via wristband):** subscribe to `issuing_authorization.request`. You have about a **2 s
default timeout** before Stripe falls back to the card's default rules. Approve or decline either in the webhook response or via
`POST /v1/issuing/authorizations/{id}/approve|decline`. Which mechanism to use is **[UNVERIFIED]**; read
https://docs.stripe.com/issuing/controls/real-time-authorizations before you build it. Because of the short timeout, use the tap
to **arm** a pending approval before the agent checks out, rather than waiting for the tap inside the webhook.

### 5.2 Link Agent Wallet (pay on a user's behalf with approval)

- The agent creates a **spend request** (amount, merchant, a `context` of at least 100 characters). The customer approves it on
  Link web or app. The agent then gets one of:
  - a **one-time virtual card** (for plain card forms; recurring cards are also supported),
  - a **Shared Payment Token** (for MPP or SPT APIs), or
  - a **Link Pay Token** (for Stripe checkouts with Link).
- Separate API: `api.link.com`, OAuth through `login.link.com`. It uses an OAuth access token per customer (`LINK_ACCESS_TOKEN`),
  **not** Stripe API keys.
- Availability: **agent payments for US and Canadian customers only**; financial insights for US only.
- Tooling: `npm i -g @stripe/link-cli` (handles auth, polling and an `--test` flag) or SDKs. Python: `pip install stripe-link-sdk`
  (import name `link`, Python 3.11+).

```python
import os, uuid
from link import Client   # pip install stripe-link-sdk

with Client(access_token=os.environ["LINK_ACCESS_TOKEN"]) as client:
    methods = client.payment_methods.list()
    method = next((m for m in methods if m.is_default), methods[0])
    req = client.spend_requests.create(
        idempotency_key=str(uuid.uuid4()),
        payment_details=method.id,
        credential_type="card",
        amount=1299, currency="usd",
        merchant_name="Acme", merchant_url="https://acme.example",
        context=("The user double-tapped their Vexo band to approve buying one replacement strap "
                 "from Acme for $12.99 including shipping, at their spoken request."),
    )
    approval = client.spend_requests.request_approval(req.id)
    print("Approve:", approval.approval_url)
    # Poll client.spend_requests.retrieve(req.id) until status == "approved",
    # then retrieve(req.id, include=["card"]). Keep card data OUT of LLM context and logs.
```

The Python SDK docs warn that this example creates **live** requests and that you should use test mode while developing.
How to switch the SDK to test mode is **[UNVERIFIED]**; see docs.link.com "spend requests > test mode". The CLI uses `--test`.

### 5.3 Shared Payment Tokens (SPT) and the Agentic Commerce Protocol (ACP)

- **SPT** = a scoped grant of a customer's payment method to one seller (Stripe profile), with `usage_limits`
  (currency, max_amount, expires_at). ID format `spt_...`. Available in the US, Canada and some European countries.
- These are **preview** APIs: send the header `Stripe-Version: 2026-09-30.preview`. Whether stripe-python exposes typed methods
  for them is **[UNVERIFIED]**, so the example below uses raw HTTP.
- **Seller side in a sandbox**: simulate receiving an SPT, then charge it.

```python
import os, requests
SK = os.environ["STRIPE_SECRET_KEY"]   # sk_test_...
H = {"Stripe-Version": "2026-09-30.preview"}

spt = requests.post("https://api.stripe.com/v1/test_helpers/shared_payment/granted_tokens",
    auth=(SK, ""), headers=H, data={
        "payment_method": "pm_card_visa",
        "usage_limits[currency]": "usd",
        "usage_limits[max_amount]": 1000,
        "usage_limits[expires_at]": 1798761600,
    }).json()

pi = requests.post("https://api.stripe.com/v1/payment_intents", auth=(SK, ""), headers=H, data={
    "amount": 1000, "currency": "usd",
    "payment_method_data[shared_payment_granted_token]": spt["id"],
    "confirm": "true",
}).json()
print(pi["status"])
```

- **Agent side**: `POST /v1/shared_payment/issued_tokens` with `payment_method`, `seller_details[network_business_profile]`
  and `usage_limits[...]`. Sandbox test seller profile: `profile_test_61TU90nIeGjU7NNVXA6TU90m7ISQWsBxpcx9lASWWXTk`.
- **ACP** (https://agenticcommerce.dev, Apache-2.0, maintained by OpenAI and Stripe, currently beta; latest spec folder
  `2026-04-17`) covers checkout sessions, cart and feed, delegated payment, delegated auth, and orders/webhooks. It powers ChatGPT
  Instant Checkout. Full seller onboarding (Agentic Commerce Suite) is a **waitlist** and too heavy for a one-day hack; just cite
  it in the pitch.
- **UCP** (Universal Commerce Protocol) is also supported through the `com.stripe.payments` handler. It has live-mode-only examples.

### 5.4 Machine Payments Protocol (MPP) and x402: pay per call

- Flow: client requests a resource, server returns **HTTP 402** with a challenge, the agent pays (SPT card or stablecoin), retries,
  and gets the resource plus a receipt.
- Minimums: SPT card payments **$0.50**; stablecoin **0.01 USDC**. Stablecoins: MPP on Tempo (USDC.e) and Solana (USDC);
  x402 on Base (USDC). Stablecoins are unavailable to NY businesses and need Dashboard enablement and review, so they are
  unlikely to be ready on hack day.
- Stripe's guide is Node (`npm install mppx stripe`). A Python SDK exists: `pip install pympp`
  (https://mpp.dev/sdk/python, github.com/tempoxyz/pympp). A Stripe sample in Python is at
  `github.com/stripe-samples/machine-payments/mpp/server/python` (Tempo method).
- Validate an endpoint: `npx mppx@latest validate http://localhost:4242`. In a sandbox it completes round-trip test transactions.
- Pay an MPP endpoint as an agent: `link-cli mpp pay <url> --context "<100+ chars>" --test`.

Python server sketch (from mpp.dev; this is the Tempo stablecoin method, **not** the Stripe SPT method):

```python
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mpp import Challenge
from mpp.server import Mpp
from mpp.methods.tempo import tempo, ChargeIntent

app = FastAPI()
mpp = Mpp.create(
    method=tempo(currency="0x20c0000000000000000000000000000000000000",  # from docs
                 intents={"charge": ChargeIntent()},
                 recipient="0xYOUR_DEPOSIT_ADDRESS"),
    secret_key=os.environ["MPP_SECRET_KEY"],
)

@app.get("/insight")
async def insight(request: Request):
    result = await mpp.charge(authorization=request.headers.get("Authorization"), amount="0.01")
    if isinstance(result, Challenge):
        return JSONResponse(status_code=402, content={"error": "Payment required"},
                            headers={"WWW-Authenticate": result.to_www_authenticate(mpp.realm)})
    credential, receipt = result
    return {"data": "your motion insight", "payer": credential.source}
```

### 5.5 Usage-based billing for AI

- **Billing Meters** (classic Stripe Billing): create a meter in the Dashboard (event name, aggregation sum/count/last), attach a
  metered price, then send meter events:

```python
client.v1.billing.meter_events.create(params={
    "event_name": "vexo_coaching_tokens",
    "payload": {"stripe_customer_id": "cus_...", "value": "25"},
    "identifier": "evt-uuid-123",  # idempotency; unique for at least 24 h
})
```

  Timestamps must be within the past 35 days and no more than 5 minutes in the future.
- **LLM token billing** has moved to **Metronome** (Stripe-owned; public preview; needs a Metronome account), with automatic
  model price sync for OpenAI, Anthropic and Google. `@stripe/token-meter` and `@stripe/ai-sdk` are **deprecated**. For a
  hackathon, plain Billing Meters are simpler.

### 5.6 Other items on Stripe's hackathon cheat sheet

- **Stripe Projects**: `stripe projects init` and `stripe projects add supabase|vercel|resend|openrouter` provision third-party
  services billed through Stripe.
- **Stripe Directory**: `stripe directory search "email sending api"` gives agents a way to discover paid services.
- **WebMCP**: the cheat sheet says Checkout has native WebMCP support, so agents can drive Checkout in a browser.
- "Order Intents": I found **no current Stripe doc** under that name. The agent-facing purchase primitives in 2026 are spend
  requests (Link), SPTs, ACP/UCP checkout sessions and MPP.

---

## 6. Stripe Agent Toolkit (Python and TypeScript): status

- Packages: `stripe-agent-toolkit` (PyPI, Python 3.11+) and `@stripe/agent-toolkit` (npm). They provide function-calling tools for
  the OpenAI Agents SDK, LangChain, CrewAI, Strands and the Vercel AI SDK.
- **Deprecated**: the github.com/stripe/ai README says these packages "will receive no further updates, including security fixes";
  use native MCP support with Stripe MCP instead.
- If a framework has no MCP client, you can still use it. The v0.7+ API is async:

```python
import asyncio, os
from agents import Agent, Runner                       # openai-agents
from stripe_agent_toolkit.openai.toolkit import create_stripe_agent_toolkit

async def main():
    toolkit = await create_stripe_agent_toolkit(secret_key=os.environ["STRIPE_RESTRICTED_KEY"])  # rk_test_...
    try:
        agent = Agent(name="Stripe Agent", tools=toolkit.get_tools())
        r = await Runner.run(agent, "Create a payment link for a product 'Test' at $10")
        print(r.final_output)
    finally:
        await toolkit.close()

asyncio.run(main())
```

  Tool names are snake_case (`create_payment_link`, `create_customer`...). The restricted key's permissions decide which tools
  are available. Because v0.7 appears to go through the hosted MCP, an agent-tagged key will likely be needed after December 2026
  **[UNVERIFIED]**.
- **Preferred approach for Python agents:** an MCP client (Claude Agent SDK, OpenAI Agents SDK MCP support, and so on) pointed at
  `https://mcp.stripe.com` with an agent API key.

---

## 7. Gotchas

1. **The MCP key deadline is Nov 30, 2026.** Plain `sk_test_` keys may work today but will stop in December. Start with OAuth or
   agent keys so your demo keeps working.
2. **Two docs contradict each other** about whether `npx @stripe/mcp` still runs. Do not rely on it; use the hosted server.
3. **Amounts are integer minor units** (cents). `unit_amount: 500` means $5.00.
4. **Issuing in a sandbox** requires activating Issuing and **funding the test Issuing balance** before authorizations succeed.
5. **The Issuing real-time auth timeout is about 2 s.** Do not block waiting for a human tap inside the webhook.
6. **Link Agent Wallet is a separate API** (`api.link.com`), uses OAuth tokens instead of Stripe keys, and serves **US/CA
   customers only**.
7. **SPT, MPP and Crypto APIs are preview** and need a `Stripe-Version: 2026-xx-xx.preview` header. stripe-python may not have
   typed helpers, so use `requests`.
8. **Never put card data in LLM context or logs** (Link SDK docs: `model_dump()` includes credentials).
9. **Prompt injection:** treat seller 402 challenge text and MCP tool outputs as data. Turn on tool-approval in Claude Code.
10. **Sandbox from `stripe sandbox create` expires in 7 days.** `sandbox create` needs an email (or `--from-git`); do not put
    personal data into demo payloads.
11. **The $500 credits are for new Stripe users only.** Register (or claim the sandbox) with the account you will redeem on.
12. **Windows:** install the CLI with `irm https://cli.stripe.com/install.ps1 | iex` and open a new terminal afterwards.
    Set env vars with `$env:NAME = "..."`.

---

## 8. Suggested 1-day build plan (Best Economic Agent)

1. `stripe sandbox create` (or log in), then `claude mcp add --transport http stripe https://mcp.stripe.com/` and `/mcp`.
2. Activate Issuing in the sandbox, fund the test balance, create an "agent" cardholder and a virtual card with limits and MCC rules.
3. Python service: band event (double tap) arms an approval window, the agent proposes a purchase, a test-helper authorization
   runs, and the webhook shows approved or declined on screen.
4. Revenue side: a Payment Link or Billing meter for the agent's own service (for example metered "coach minutes").
5. Pitch: limits, MCC allow-list, human tap approval, single-use credentials (SPT or Link), audit trail in the Dashboard.

---

## 9. Sources (official)

- Hackathon cheat sheet: https://shipbysundown.dev/
- VexoHacks benefits: https://stripe.com/startup-benefits/vexohacks and FAQ https://support.stripe.com/questions/stripe-startups-program-faqs
- MCP: https://docs.stripe.com/mcp (Markdown version: https://docs.stripe.com/mcp.md)
- Agents hub: https://docs.stripe.com/agents ; plugin: https://docs.stripe.com/agents/plugin ; skills: https://docs.stripe.com/skills
- API keys and agent keys: https://docs.stripe.com/keys#agent-keys
- Sandboxes and CLI: https://docs.stripe.com/sandboxes , https://docs.stripe.com/cli/sandbox
- Rate limits: https://docs.stripe.com/rate-limits
- Checkout quickstart (Python): https://docs.stripe.com/checkout/quickstart?lang=python
- Payment Links: https://docs.stripe.com/payment-links
- Agentic commerce: https://docs.stripe.com/agentic-commerce
- Issuing for agents: https://docs.stripe.com/issuing/agents ; programmatic checkout: https://docs.stripe.com/issuing/agents/programmatic-checkout ; MCP: https://docs.stripe.com/issuing/agents/mcp ; testing: https://docs.stripe.com/issuing/testing
- Link Agent Wallet: https://docs.stripe.com/agentic-commerce/agents/link-agent-wallet ; spend: https://docs.stripe.com/agentic-commerce/agents/link-agent-wallet/use-link-wallet-pay-online ; Python SDK: https://docs.link.com/sdks/python
- Shared payment tokens: https://docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens
- ACP: https://docs.stripe.com/agentic-commerce/protocols/acp , https://agenticcommerce.dev , https://github.com/agentic-commerce-protocol/agentic-commerce-protocol , https://stripe.com/blog/developing-an-open-standard-for-agentic-commerce
- Machine payments: https://docs.stripe.com/payments/machine , MPP: https://docs.stripe.com/payments/machine/mpp , https://mpp.dev/sdk/python
- Usage billing: https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage-api , token billing: https://docs.stripe.com/billing/token-billing
- Agent toolkit and deprecation notice: https://github.com/stripe/ai
