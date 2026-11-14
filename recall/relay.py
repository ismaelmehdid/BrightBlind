"""Band -> team backend relay (WebSocket contract v0 in README.md), running inside Recall.

The band takes one program at a time, so Recall itself forwards what the backend needs:
  hello     {client: "band", caps}
  audio     {seq, opus_b64}        one 20 ms Opus packet, as the band sends it (or pcm_b64 with pcm=True)
  event     {kind}                 tap, double-tap, free-fall, tilt
  activity  {state, steps, cadence} about once a second
and runs what comes back:
  led       {color}                only while the microphone is off: the band refuses LED commands otherwise

It reconnects by itself, drops audio while the backend is away (old sound is useless to a live loop),
and never stops Recall: the memory keeps working when the backend is down.
"""
import asyncio
import base64
import json
import time

import aiohttp

CAPS = ["audio", "events", "activity", "led"]
RETRY_SECONDS = 2
FORWARD_EVENTS = {"tap", "double-tap", "free-fall", "tilt"}


def _ms():
    return int(time.time() * 1000)


class BackendRelay:
    def __init__(self, url, band_ref, pcm=False, on_status=None):
        """band_ref: a callable that returns the connected Band, or None. on_status: async fn(bool)."""
        self.url = url
        self.band_ref = band_ref
        self.pcm = pcm
        self.on_status = on_status
        self.connected = False
        self.sent = {"audio": 0, "event": 0, "activity": 0}
        self._ws = None
        self._last_report = time.time()

    async def run(self):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self.url, heartbeat=20) as ws:
                        self._ws = ws
                        await self._send({"type": "hello", "client": "band", "caps": CAPS})
                        await self._set_status(True)
                        print("Backend relay: connected to", self.url)
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._command(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if self.connected:
                    print("Backend relay: lost the backend:", type(e).__name__)
            self._ws = None
            await self._set_status(False)
            await asyncio.sleep(RETRY_SECONDS)

    async def _set_status(self, up):
        if up != self.connected:
            self.connected = up
            if self.on_status:
                await self.on_status(up)

    async def _send(self, obj):
        if not self._ws or self._ws.closed:
            return False
        obj.setdefault("ts", _ms())
        try:
            await self._ws.send_str(json.dumps(obj))
            return True
        except Exception:
            return False

    def _report(self):
        if time.time() - self._last_report >= 10:
            self._last_report = time.time()
            print(f"Backend relay: sent {self.sent['audio']} audio, {self.sent['event']} events, "
                  f"{self.sent['activity']} activity so far")

    # --- band -> backend -----------------------------------------------------------------

    async def audio(self, a, pcm=None):
        if not self.connected:
            return
        msg = {"type": "audio", "seq": getattr(a, "seq", None)}
        if self.pcm and pcm is not None:
            msg["pcm_b64"] = base64.b64encode(pcm).decode()
        else:
            msg["opus_b64"] = base64.b64encode(bytes(a.opus)).decode()
        if await self._send(msg):
            self.sent["audio"] += 1
            self._report()

    async def event(self, kind):
        if kind in FORWARD_EVENTS and await self._send({"type": "event", "kind": kind}):
            self.sent["event"] += 1
            print("Backend relay: sent event", kind)

    async def activity(self, e):
        if await self._send({"type": "activity", "state": e.state, "steps": e.steps, "cadence": e.cadence}):
            self.sent["activity"] += 1

    # --- backend -> band -----------------------------------------------------------------

    async def _command(self, raw):
        try:
            cmd = json.loads(raw)
        except ValueError:
            return
        if cmd.get("type") != "led":
            return
        band = self.band_ref()
        color = str(cmd.get("color", ""))
        if not band or not color.startswith("#"):
            return
        try:
            await band.set_led(color)
            print("Backend relay: LED", color)
        except Exception as e:  # "denied" while the mic is on (kit rule 4)
            print("Backend relay: LED", color, "refused:", getattr(e, "code", type(e).__name__))
