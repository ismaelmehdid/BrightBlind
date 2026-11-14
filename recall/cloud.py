"""Cloud entrypoint for Railway: the memory server without the USB band or the laptop mic.

On Railway the server is on the public internet, so unlike `web.start` (127.0.0.1 only) it
binds 0.0.0.0:$PORT and refuses every request without RECALL_TOKEN. The band reaches it
through the phone (Expo app) over the same /ws protocol the local page uses.

    python -m recall.cloud

Env:
  PORT            set by Railway
  RECALL_TOKEN    required; clients send it as ?token=... or "Authorization: Bearer ..."
  RECALL_DB       SQLite path; put it on a Railway volume (default /data/recall.db)
  GEMINI_API_KEY  optional; without it memories are stored but not distilled
"""
import asyncio
import hmac
import os
from pathlib import Path

from aiohttp import web

from .brain import make_brain
from .core import Recall
from .store import Store
from .web import make_app

OPEN_PATHS = {"/healthz"}


def _token_middleware(token):
    @web.middleware
    async def check(req, handler):
        if req.path in OPEN_PATHS:
            return await handler(req)
        given = req.query.get("token", "")
        auth = req.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            given = auth[7:]
        if not hmac.compare_digest(given.encode(), token.encode()):
            raise web.HTTPUnauthorized(text="missing or wrong token")
        return await handler(req)

    return check


async def main():
    token = os.getenv("RECALL_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("RECALL_TOKEN must be set (16+ chars): this server is public")
    port = int(os.getenv("PORT", "8080"))
    db = Path(os.getenv("RECALL_DB", "/data/recall.db"))
    db.parent.mkdir(parents=True, exist_ok=True)

    brain, problem = make_brain()
    if problem:
        print("Brain:", problem)
    recall = Recall(Store(str(db)), brain, problem)

    # The phone relays band taps as {"cmd": "tap"} / {"cmd": "double-tap"} over /ws.
    app = make_app(recall, band_actions={"tap": recall.on_tap, "double-tap": recall.on_double_tap})
    app.middlewares.append(_token_middleware(token))

    async def healthz(_req):
        return web.json_response({"ok": True, "brain": brain is not None})

    app.router.add_get("/healthz", healthz)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"Recall cloud server on :{port} (db {db})")
    await recall.distill_loop()


if __name__ == "__main__":
    asyncio.run(main())
