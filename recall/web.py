"""Local web page for the memory: live transcript, memories, band context, ask box.

Binds to 127.0.0.1 only: the transcript of the wearer's day must not be readable by the whole event Wi-Fi.
When a tunnel makes it public (for the glasses' phone), a token guards every path.
"""
import asyncio
import hmac
import json
from pathlib import Path

from aiohttp import WSMsgType, web

STATIC = Path(__file__).resolve().parent / "static"
PHOTOS = Path(__file__).resolve().parent.parent / "photos"


def token_middleware(token, open_paths=()):
    """Refuse every request without the token (?token=... or Authorization: Bearer ...)."""

    @web.middleware
    async def check(req, handler):
        if req.path in open_paths:
            return await handler(req)
        given = req.query.get("token", "")
        auth = req.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            given = auth[7:]
        if not hmac.compare_digest(given.encode(), token.encode()):
            raise web.HTTPUnauthorized(text="missing or wrong token")
        return await handler(req)

    return check


def make_app(recall, band_actions, glasses=None, token=None, phoneband=None):
    """band_actions: dict of async callables the page may trigger (tap, double-tap).
    glasses: a recall.glasses.Glasses, served at /glasses for Andrii's phone app. token: guard every path.
    phoneband: a recall.phoneband.PhoneBand, served at /band for the Expo app relaying the band."""
    app = web.Application(middlewares=[token_middleware(token)] if token else [])

    async def index(_req):
        return web.FileResponse(STATIC / "index.html")

    async def ws_handler(req):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        pending = set()                      # commands running in the background, kept so they are not collected
        recall.clients.add(ws)
        await ws.send_str(json.dumps({"type": "snapshot", "data": recall.snapshot()}))
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    cmd = json.loads(msg.data)
                except ValueError:
                    continue
                if cmd.get("cmd") == "refresh":
                    await ws.send_str(json.dumps({"type": "snapshot", "data": recall.snapshot()}))
                else:
                    # In the background: a Gemini answer can take seconds, and while this loop waits it
                    # does not answer the client's keep-alive pings (the backend's socket then drops).
                    task = asyncio.create_task(handle(cmd))
                    pending.add(task)
                    task.add_done_callback(pending.discard)
        finally:
            recall.clients.discard(ws)
        return ws

    async def handle(cmd):
        kind = cmd.get("cmd")
        text = str(cmd.get("text", ""))[:2000]
        if kind == "ask" and text.strip():
            await recall.ask(text.strip(), source="typed")
        elif kind == "note" and text.strip():
            await recall.on_transcript(text, source="typed")
        elif kind == "distill":
            await recall.distill_now()
        elif kind == "forget":
            recall.store.forget_memory(int(cmd.get("id", 0)))
            await recall.broadcast("forgot", {"id": int(cmd.get("id", 0))})
        elif kind == "burst" and recall.eyes is not None:          # the phone app's manual burst control
            if cmd.get("on") and text.strip():
                await recall.eyes.start(text.strip(), say="Looking now.")
            elif not cmd.get("on"):
                await recall.eyes.stop("stopped in the app", say="Okay.")
        elif kind == "capture" and glasses is not None:
            await glasses.capture("tap")                             # a "tap-" photo: described into memory
        elif kind == "say" and text.strip():
            await recall._say(text.strip())
        elif kind in band_actions:
            await band_actions[kind]()

    # --- plain HTTP for the team backend (its planner asks the memory without speaking our /ws) ---

    async def body(req):
        try:
            data = await req.json()
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def limit(req, default):
        try:
            return max(1, min(1000, int(req.query.get("limit", default))))
        except ValueError:
            return default

    async def api_context(_req):
        return web.json_response(recall.ctx)

    async def api_memories(req):
        return web.json_response(recall.store.memories(limit=limit(req, 200)))

    async def api_heard(req):
        return web.json_response(recall.store.utterances(limit=limit(req, 100)))

    async def api_ask(req):
        q = str((await body(req)).get("question", "")).strip()[:2000]
        if not q:
            return web.json_response({"error": "question is empty"}, status=400)
        return web.json_response(await recall.ask(q, source="backend"))

    async def api_note(req):
        text = str((await body(req)).get("text", "")).strip()[:2000]
        if not text:
            return web.json_response({"error": "text is empty"}, status=400)
        await recall.on_transcript(text, source="backend")
        return web.json_response({"ok": True})

    async def api_mirror(req):
        """Lines and taps copied from the laptop's Recall (recall/mirror.py) into this one (Railway)."""
        if await recall.from_mirror(await body(req)):
            return web.json_response({"ok": True})
        return web.json_response({"error": "not a line or a tap"}, status=400)

    app.router.add_post("/api/mirror", api_mirror)
    app.router.add_get("/api/context", api_context)
    app.router.add_get("/api/memories", api_memories)
    app.router.add_get("/api/heard", api_heard)
    app.router.add_post("/api/ask", api_ask)
    app.router.add_post("/api/note", api_note)

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", STATIC)
    PHOTOS.mkdir(exist_ok=True)
    app.router.add_static("/photos/", PHOTOS)
    if glasses is not None:
        app.router.add_get("/glasses", glasses.handler)
    if phoneband is not None:
        app.router.add_get("/band", phoneband.handler)
    return app


async def start(recall, band_actions, port, glasses=None, token=None, phoneband=None):
    runner = web.AppRunner(make_app(recall, band_actions, glasses=glasses, token=token, phoneband=phoneband))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    return runner
