"""The glasses as Recall's eyes and voice: Andrii's iPhone relay app (ios/) connects here.

Speaks the same messages as the team contract (README, "WebSocket contract"), with Recall in the
backend's seat, so the app needs no change: give it this server's address, path /glasses.

  glasses -> Recall   hello, photo {jpeg_b64, req_id}, button {press}, state {glasses}
  Recall -> glasses   say {text, audio_b64 (mp3, Deepgram voice), interrupt}, capture {req_id, quality}

What it does:
- Recall's spoken replies ("Saved.", answers) play in the glasses instead of the laptop speaker.
- A tap on the band (or a short press on the glasses' button) also takes a photo; Gemini describes
  it and the description is kept as a bookmarked memory ("what was in my fridge?").
- A double press on the glasses' button is the same as a double-tap on the band: ask a question.
"""
import asyncio
import base64
import json
import os
import time
from pathlib import Path

import aiohttp
from aiohttp import WSMsgType, web

PHOTOS = Path(__file__).resolve().parent.parent / "photos"
VOICE = os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en")


def _ms():
    return int(time.time() * 1000)


class Glasses:
    def __init__(self, recall):
        self.recall = recall
        self.ws = None
        self.state = None
        PHOTOS.mkdir(exist_ok=True)

    @property
    def connected(self):
        return self.ws is not None and not self.ws.closed

    # --- Recall -> glasses -------------------------------------------------------------

    async def _send(self, **msg):
        if not self.connected:
            return False
        msg["ts"] = _ms()
        try:
            await self.ws.send_str(json.dumps(msg))
            return True
        except Exception:
            return False

    async def say(self, text):
        """Speak in the glasses: Deepgram's voice as mp3 when the key works, the phone's own voice otherwise."""
        msg = {"type": "say", "text": text, "interrupt": True}
        mp3 = await _deepgram_mp3(text)
        if mp3:
            msg["audio_b64"] = base64.b64encode(mp3).decode()
        return await self._send(**msg)

    async def capture(self, why="tap"):
        return await self._send(type="capture", req_id=f"{why}-{_ms()}", quality="medium")

    # --- glasses -> Recall -------------------------------------------------------------

    async def handler(self, req):
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=32 * 1024 * 1024)
        await ws.prepare(req)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    m = json.loads(msg.data)
                except ValueError:
                    continue
                await self._on_message(ws, m)
        finally:
            if self.ws is ws:
                self.ws = None
                self.state = None
                await self._push_ctx()
                print("Glasses: disconnected")
        return ws

    async def _on_message(self, ws, m):
        kind = m.get("type")
        if kind == "hello" and m.get("client") == "glasses":
            self.ws = ws                       # the newest phone wins
            print("Glasses: connected, caps", m.get("caps"))
            await self._push_ctx()
            await self.say("Recall is connected.")
        elif kind == "photo" and m.get("jpeg_b64"):
            jpeg = base64.b64decode(m["jpeg_b64"])
            name = f"{time.strftime('%Y%m%d-%H%M%S')}-{m.get('req_id') or 'photo'}.jpg"
            (PHOTOS / name).write_bytes(jpeg)
            print(f"Glasses: photo {len(jpeg) // 1024} KB -> photos/{name}")
            asyncio.create_task(self.recall.on_photo(jpeg, name))
        elif kind == "button":
            press = m.get("press")
            if press == "short":
                await self.recall.on_tap()
            elif press == "double":
                await self.recall.on_double_tap()
        elif kind == "state":
            self.state = m.get("glasses")
            await self._push_ctx()

    async def _push_ctx(self):
        self.recall.ctx["glasses"] = self.state or ("connected" if self.connected else None)
        await self.recall.push_ctx()


async def _deepgram_mp3(text):
    key = os.getenv("DEEPGRAM_API_KEY")
    if not key:
        return None
    url = f"https://api.deepgram.com/v1/speak?model={VOICE}&encoding=mp3&mip_opt_out=true"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"text": text}, timeout=aiohttp.ClientTimeout(total=10),
                              headers={"Authorization": "Token " + key}) as r:
                if r.status == 200:
                    return await r.read()
                print("Glasses: Deepgram voice failed, status", r.status, "(the phone's own voice is used)")
    except Exception as e:
        print("Glasses: Deepgram voice failed:", type(e).__name__)
    return None
