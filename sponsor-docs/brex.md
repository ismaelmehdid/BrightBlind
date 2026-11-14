# Brex: developer digest for VexoHacks (2026-11-14)

Brex is a **gold sponsor**. Brex is a corporate card, spend management and business banking platform. Its developer platform
(https://developer.brex.com) has REST APIs for team and cards, expenses, budgets and spend limits, payments (ACH, wire, check),
transactions and accounts, accounting, fields, travel and webhooks. It also has an **official hosted MCP server (beta)**.

All facts below come from developer.brex.com and brex.com, read on 2026-11-14. Items marked **[UNVERIFIED]** are my inference.

---

## 0. TL;DR for the team

- **MCP exists and is official:** `https://api.brex.com/mcp` (HTTP transport, **beta**).
  Claude Code: `claude mcp add --transport http brex https://api.brex.com/mcp`, then run `/mcp` to sign in with OAuth.
- **Biggest constraint: there is no public sandbox.** Every API reference lists a Staging server with the note
  *"This is not a sandbox. It will not work with customer tokens."* Real calls need a **real Brex account**; card creation and
  transfers move or commit real money.
- To build with it today you need: (1) access to a Brex account (a sponsor or team account) where an **account admin or card admin**
  accepted the Developer API agreement, and (2) either a **user token** (`bxt_...`) or OAuth via MCP. **Ask the Brex booth for a
  demo or test account.** That is the realistic route **[UNVERIFIED: whether Brex offers hackathon demo accounts]**.
- **MCP scope:** mostly read access (expenses, cards metadata, limits, bank transactions, bills, travel) plus a few writes
  (expense memos, receipts, attendees, assigning expenses to limits). Approvals and card management are **not** available via MCP,
  and it never returns raw card numbers.
- **REST API scope** is broader: create and lock virtual cards with spend controls, create transfers, manage budgets and spend
  limits, and use webhooks.

---

## 1. MCP server

| Item | Value |
|---|---|
| Official server | `https://api.brex.com/mcp` (hosted by Brex, **Beta**; tools may change) |
| Transport | HTTP (Streamable HTTP; `--transport http` / `"type": "http"`) |
| Auth option 1 (recommended) | **OAuth** with Dynamic Client Registration (RFC 7591). Authorization server `https://accounts-api.brex.com/oauth2/default`; discovery `https://api.brex.com/.well-known/oauth-protected-resource/mcp`. Any employee can connect, and tools follow their Brex permissions |
| Auth option 2 | **API token** (account or card admin only) sent as `Authorization: Bearer <token>`; generate it at Settings > Developer |
| Prerequisites | (1) An account or card admin accepts the Developer API agreement in **Settings > Developer**. (2) Enable the beta at **Settings > Beta features > "Brex in AI assistants"** |
| Revoke | Settings > Personal settings > Connected integrations |
| Other clients | Claude Desktop connector (claude.com/connectors/brex), ChatGPT app, Cursor (http URL), Codex (`codex mcp add brex --url https://api.brex.com/mcp`) |

### Claude Code install (official commands from developer.brex.com/docs/mcp)

```bash
# OAuth (recommended)
claude mcp add --transport http brex https://api.brex.com/mcp
# then verify / log in:
/mcp

# API-token variant (admins only); keep the token in an env var, never in git
claude mcp add --transport http brex https://api.brex.com/mcp --header "Authorization: Bearer YOUR_BREX_ACCESS_TOKEN"
```

`.mcp.json` variant. The env-var expansion `${BREX_TOKEN}` is a Claude Code feature; Brex's own example hardcodes a placeholder.

```json
{
  "mcpServers": {
    "brex": {
      "type": "http",
      "url": "https://api.brex.com/mcp",
      "headers": { "Authorization": "Bearer ${BREX_TOKEN}" }
    }
  }
}
```

### MCP tools (from the Brex MCP page)

| Area | Tools | Access |
|---|---|---|
| Users and org | `get_user_myself`, `get_user_by_id`, `list_users`, `list_users_by_name_or_email`, `list_departments`, `list_locations`, `list_cost_centers`, `list_legal_entities`, `list_titles`, `list_roles` | all users |
| Expenses (read) | `list_expenses`, `get_expense_by_id`, `start_expense_download`, `get_expense_download_result`, `list_expense_categories`, `list_merchants`, `list_merchant_categories` | view-expenses capability (some all users) |
| Expenses (write) | `update_expense_memo` (bulk), `upload_card_expense_receipt_from_urls`, `replace_attendees_for_card_expense`, `assign_limit_for_card_expenses`, `get_reimbursement_payout_date` | all users (own expenses) |
| Analytics | `brex-analytics` (natural-language questions about spend, banking, accounting); `query_expense_analytics` is deprecated | account or card admin |
| Cards and limits | `list_cards`, `get_card_by_id`, `list_my_limits`, `get_expense_policy` | metadata only; **no PAN, CVV or expiry** |
| Banking | `list_business_accounts`, `get_business_account`, `list_banking_transactions`, `get_banking_transaction` | view accounts and balances |
| Bills and vendors | `list_bills`, `get_bill_by_id`, `list_vendors`, `get_vendor_by_id` | view bills and vendors |
| Accounting | `get_active_integration`, `list_accounting_records`, `list_gl_accounts` | respective capabilities |
| Travel | `list_trips`, `list_bookings`, `list_group_events` | view travel |
| Misc | `get_reward_points`, `submit_feedback` | |

**Not available via MCP:** approvals and card management (create, lock, limits). Use the REST API for those.

---

## 2. Fit for this hackathon

Brex suits **agents that manage or audit company spend**. Brex itself publicly describes building an "audit agent" and an expense
agent. Ideas for the Vexo wristband:

- **Voice expense memos:** after a card swipe (picked up through the `expensePaymentUpdated` webhook or by polling
  `GET /v1/expenses`), the band buzzes, the user speaks a memo into the mic, an LLM cleans it up, and the agent calls
  `PUT /v1/expenses/card/{id}` with `memo` (or MCP `update_expense_memo`).
- **Tap-to-lock card:** a triple tap locks the agent's or the user's virtual card (`POST /v2/cards/{id}/lock`); a later gesture
  unlocks it.
- **Just-in-time vendor card for an agent:** the agent creates a **VIRTUAL vendor card** (`limit_type: CARD`) with a `ONE_TIME`
  spend limit equal to the purchase, uses it, then terminates it. This is a "safe economic agent" story that pairs well with Stripe.
  It needs a real Brex account and the `cards` scope.
- **Budget awareness:** before any agent purchase, check `GET /v2/spend_limits` / `list_my_limits` and refuse when over budget.
  The band vibrates to warn.
- **Spend Q&A by voice:** "How much did we spend on software this month?" goes to MCP `brex-analytics`.

---

## 3. Auth (REST API)

### 3.1 User token (your own Brex account): use this at a hackathon

1. An **account admin or card admin** signs in at dashboard.brex.com and opens **Settings > Developer**
   (https://dashboard.brex.com/settings/developer). Accept the Developer API agreement if prompted.
2. **Create Token**, name it, choose **scopes** (least privilege, for example `cards.readonly`), then **Allow Access**.
3. Copy the token (format `bxt_...`). It is shown **once**.
4. Send it as a header on every request: `Authorization: Bearer bxt_...`
- Tokens **expire after 90 days without use**, stop working when the user becomes inactive, and can be revoked in the dashboard.
  All admins get an email whenever a token is created or revoked.

### 3.2 OAuth (partner apps acting on other Brex customers)

- Authorization Code grant (PKCE supported). Authorize at
  `https://accounts-api.brex.com/oauth2/default/v1/authorize?client_id=...&response_type=code&redirect_uri=...&scope=...&state=...`
  (`state` must be longer than 8 characters). Exchange the code at `/v1/token`. Access tokens last **1 hour**; refresh with
  `offline_access`.
- Client credentials are only for the onboarding API. Partner client IDs and secrets come from Brex developer support.
  This is too slow to obtain on hack day.

### 3.3 Scopes (subset)

| API | Scopes |
|---|---|
| Team / users | `users.readonly`, `users` |
| Cards | `cards.readonly`, `cards` |
| Expenses | `expenses.card.readonly`, `expenses.card` |
| Payments | `transfers.readonly`, `transfers`, `vendors.readonly`, `vendors`, `linked_accounts.readonly`, `incoming_transfers` |
| Transactions | `transactions.card.readonly`, `transactions.cash.readonly`, `accounts.card.readonly`, `accounts.cash.readonly`, `statements.*.readonly` |
| Always included | `openid`, `offline_access` |

Budgets, webhooks and accounting scopes are listed on the roles and permissions page. I have not copied their exact names here.

---

## 4. Key endpoints (base URL `https://api.brex.com`)

| Area | Method and path | Notes |
|---|---|---|
| Me | `GET /v2/users/me` | quickstart call |
| Users | `GET /v2/users`, `POST /v2/users` (invite), `POST /v2/users/create` (no invite), `PUT /v2/users/{id}` | |
| Company | `GET /v2/company` | |
| Cards | `GET /v2/cards?user_id=...`, `POST /v2/cards`, `GET/PUT /v2/cards/{id}` | `POST` **requires** an `Idempotency-Key` |
| Card state | `POST /v2/cards/{id}/lock`, `/unlock`, `/terminate` | the owner gets a notification |
| Card PAN | `GET /v2/cards/{id}/pan` | number, CVV, expiry. Highly sensitive; keep it out of LLM context |
| Expenses | `GET /v1/expenses` (filters `user_id[]`, `budget_id[]`, `status[]`, `expense_type[]`, `expand[]=merchant`...), `GET /v1/expenses/{id}` | `limit` is at most 100 for this endpoint |
| Expense update | `PUT /v1/expenses/card/{expense_id}` with body `{"memo": "..."}` | regular users can update only their own |
| Receipts | `POST /v1/expenses/card/{expense_id}/receipt_upload`, `POST /v1/expenses/card/receipt_match` with body `{"receipt_name": "x.jpg"}` | returns a pre-signed S3 `uri`; `PUT` the file within 30 min; max 50 MB |
| Budgets (v2) | `GET/POST /v2/budgets`, `GET/PUT /v2/budgets/{id}`, `POST /v2/budgets/{id}/archive` | v1 `/v1/budgets` = legacy spend limits, deprecated |
| Spend limits (v2) | `GET/POST /v2/spend_limits`, `GET/PUT /v2/spend_limits/{id}`, `POST .../archive` | |
| Transfers | `POST /v1/transfers` (ACH, DOMESTIC_WIRE, CHEQUE, INTERNATIONAL_WIRES), list and get | requires `Idempotency-Key`; `approval_type: "MANUAL"` makes a cash admin approve it |
| Vendors | `POST /v1/vendors`, list and get | `Idempotency-Key` required on create |
| Card transactions | `GET /v2/transactions/card/primary` | settled only; use at least a 1-day lookback when syncing |
| Cash | `GET /v2/accounts/cash`, `GET /v2/accounts/cash/primary`, `GET /v2/transactions/cash/{id}` | |
| Webhooks | `GET/POST /v1/webhooks`, `GET /v1/webhooks/secrets`, `PUT/DELETE /v1/webhooks/{id}` | events: `EXPENSE_PAYMENT_UPDATED`, `TRANSFER_PROCESSED`, `TRANSFER_FAILED`, `USER_UPDATED`, `ACCOUNTING_RECORD_READY_FOR_EXPORT`, referral events. The exact enum casing is **[UNVERIFIED]**; the docs list them as `expensePaymentUpdated` and so on |

**Money format:** `{"amount": 700, "currency": "USD"}` means USD 7.00, in the smallest unit.
**Pagination:** `limit` (default 100, max 1000 on most list endpoints) plus `cursor`. Responses return `items` and `next_cursor`,
which is null at the end.

---

## 5. Python code samples (Python 3.12, `pip install requests`)

```python
# brex_client.py
import os, uuid, requests

BASE = "https://api.brex.com"
TOKEN = os.environ["BREX_TOKEN"]          # bxt_... placeholder; never commit
S = requests.Session()
S.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})

def get(path, **params):
    r = S.get(BASE + path, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def post(path, body=None, idempotent=False):
    headers = {"Idempotency-Key": str(uuid.uuid4())} if idempotent else {}
    r = S.post(BASE + path, json=body or {}, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else None

def paginate(path, **params):
    cursor = None
    while True:
        page = get(path, **({**params, "cursor": cursor} if cursor else params))
        yield from page.get("items", [])
        cursor = page.get("next_cursor")
        if not cursor:
            break
```

### 5.1 Who am I, plus my cards

```python
from brex_client import get, paginate

me = get("/v2/users/me")
print(me["id"], me.get("email"))
for card in paginate("/v2/cards", user_id=me["id"]):
    print(card["id"], card["card_name"], card["status"], card.get("last_four"))
```

### 5.2 Create a one-time virtual vendor card for an agent (scope `cards`; this creates a REAL card)

```python
from brex_client import post

card = post("/v2/cards", {
    "owner": {"type": "USER", "user_id": "cuuser_..."},        # placeholder
    "card_name": "Vexo agent - strap purchase",
    "card_type": "VIRTUAL",
    "limit_type": "CARD",                                       # vendor card; spend_controls required
    "spend_controls": {
        "spend_limit": {"amount": 2500, "currency": "USD"},     # $25.00
        "spend_duration": "ONE_TIME",
        "lock_after_date": "2026-11-15",
    },
}, idempotent=True)
print(card["id"], card["status"])
```

The request body follows the official Team API example. Store the idempotency key for a semantic purchase and reuse it on retry;
the helper above generates a fresh key on every call for brevity.

### 5.3 Lock and terminate after use

```python
post(f"/v2/cards/{card['id']}/lock")          # reversible: /unlock
# post(f"/v2/cards/{card['id']}/terminate")   # permanent. Lock and terminate may need a body; [UNVERIFIED], check the reference
```

### 5.4 Recent expenses and setting a memo (for example from a voice note)

```python
from brex_client import S, BASE, paginate

for e in paginate("/v1/expenses", **{"expand[]": "merchant", "limit": 50}):
    print(e["id"], e.get("status"), e.get("memo"))
    break

expense_id = "expense_..."                                   # placeholder
r = S.put(f"{BASE}/v1/expenses/card/{expense_id}", json={"memo": "Team lunch with Vexo demo judges"})
r.raise_for_status()
```

### 5.5 Upload a receipt and let Brex match it

```python
from brex_client import post
import requests

up = post("/v1/expenses/card/receipt_match", {"receipt_name": "lunch.jpg"})
with open("lunch.jpg", "rb") as f:
    requests.put(up["uri"], data=f, timeout=60).raise_for_status()   # pre-signed S3 URL, valid 30 min
```

### 5.6 Check spend limits before an agent spends

```python
from brex_client import paginate
for sl in paginate("/v2/spend_limits"):
    print(sl.get("id"), sl.get("name"), sl.get("status"))   # field names [UNVERIFIED]: check the SpendLimit schema
```

### 5.7 Register a webhook for card spend events

```python
from brex_client import post, get
hook = post("/v1/webhooks", {"url": "https://YOUR-TUNNEL.example/brex", "event_types": ["EXPENSE_PAYMENT_UPDATED"]})
secrets = get("/v1/webhooks/secrets")   # verify the 'Webhook-Signature' header against ALL returned keys (rotation)
```

The body field names (`url`, `event_types`) and the enum value are **[UNVERIFIED]**; see the Register Webhook reference. Your
endpoint must be publicly reachable over HTTPS, for example through a tunnel.

---

## 6. Limits and gotchas

1. **No sandbox.** Staging (`api-staging.brex.com`) rejects customer tokens. Every write in production is real: real cards,
   real ACH or wires. For demos, prefer read-only scopes and Brex MCP. If you create cards, use `ONE_TIME` limits with small amounts
   and terminate them afterwards.
2. **Admin-only tokens.** Only account or card admins can create API tokens. Most APIs need admin-granted access; bookkeepers can
   use the accounting API.
3. **Rate limits** (per client ID and Brex account): **1,000 requests per 60 s**; **1,000 transfers per 24 h**; **100 international
   wires per 24 h**; **5,000 cards created per 24 h**. Exceeding them returns HTTP 429; back off and retry.
4. **Idempotency-Key is required** on Create card, Create transfer and Create vendor. Use UUIDv4 and reuse the same key on retries.
5. **Physical cards** need a `mailing_address` and are capped at 10 active per user. Use VIRTUAL cards.
6. **Empower accounts:** creating cards requires budget management, otherwise you get a 403.
7. **MCP is beta** and must be enabled under Settings > Beta features. It is mostly read access, and card management and approvals
   are excluded. A 401 usually means an expired OAuth session or a missing `Bearer ` prefix. If the OAuth popup fails, allow popups
   from `accounts-api.brex.com`.
8. **PAN endpoint** (`/v2/cards/{id}/pan`) returns full card data. Never send it to an LLM, a log or a frontend.
9. **Compliance:** the Payments API may not be used for activity that requires a money-transmission license without Brex's review.
10. **Transactions lag:** use a lookback of 1 day or more when syncing with cursors.
11. **Deprecated:** `/v1/budgets` (legacy spend limits; use `/v2/spend_limits` and `/v2/budgets`) and `/v1/expenses/card` list/get
    (use `/v1/expenses`).
12. **Postman:** the official Brex developer workspace has collections for all APIs: https://www.postman.com/brex-api/workspace/brex-developer

---

## 7. Suggested hack-day plan with Brex

1. At the booth, ask for a **demo Brex account or a token with read scopes**. Have them enable "Brex in AI assistants".
2. `claude mcp add --transport http brex https://api.brex.com/mcp`, then `/mcp` (OAuth). Try "Show my expenses missing receipts".
3. Python loop: poll `GET /v1/expenses` (or use a webhook through a tunnel). On a new expense, buzz the band, record a voice memo,
   transcribe it and send `PUT /v1/expenses/card/{id}` with the memo.
4. Optional "safe agent" feature: create a `ONE_TIME` virtual vendor card for an approved purchase, lock it with a gesture and
   terminate it afterwards.
5. Combine with Stripe: Stripe handles the agent's earning and paying side; Brex handles company spend control and expense hygiene.

---

## 8. Sources (official)

- Brex MCP: https://developer.brex.com/docs/mcp
- Authentication (user tokens): https://developer.brex.com/guides/authentication
- Partner OAuth: https://developer.brex.com/guides/partner_authentication
- Quickstart: https://developer.brex.com/guides/quickstart
- Roles, permissions, scopes: https://developer.brex.com/guides/roles_permissions_scopes
- Rate limits: https://developer.brex.com/guides/rate_limits
- Idempotency: https://developer.brex.com/guides/idempotency
- Pagination: https://developer.brex.com/guides/pagination
- FAQ: https://developer.brex.com/docs/faq
- Team API (users, cards): https://developer.brex.com/openapi/team_api ; create card: https://developer.brex.com/openapi/team_api/cards/createcard.md ; examples: https://developer.brex.com/examples/team_examples
- Expenses API: https://developer.brex.com/openapi/expenses_api ; list expenses: https://developer.brex.com/openapi/expenses_api/expenses/listexpenses.md
- Budgets API: https://developer.brex.com/openapi/budgets_api
- Payments API, create transfer: https://developer.brex.com/openapi/payments_api/transfers/createtransfer.md
- Transactions API: https://developer.brex.com/openapi/transactions_api
- Webhooks API: https://developer.brex.com/openapi/webhooks_api
- Changelog: https://developer.brex.com/changelog
- Postman: https://developer.brex.com/docs/postman
- Brex API overview (support): https://brex.com/support/brex-api
- Brex in Claude announcement: https://brex.com/journal/brex-connector-for-claude
