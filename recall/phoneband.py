"""The band through the phone: the Expo app (mobile/src/bandRelay.ts) connects the band over
Bluetooth and relays it here, path /band. Recall then works as with a local band.

  phone -> Recall   hello {client: "band"}, audio {seq, opus_b64} (raw 20 ms Opus packets),
                    event {kind: tap | double-tap | free-fall | tilt}, activity {state, steps, cadence},
                    battery {percent}

The Opus packets are decoded to 16 kHz PCM with the kit's PcmDecoder and fed to the voice
pipeline exactly as app.py does for a local band.
"""
import asyncio
import base64
import json
from types import SimpleNamespace

from aiohttp import WSMsgType, web

BAND_NAME = "Vexo-HACK-63 (phone)"


class PhoneBand:
    def __init__(self, recall, voice=None):
        self.recall = recall
        self.voice = voice          # set by app.py once the voice pipeline exists (may stay None)
        self.ws = None
        self._decoder = None
        self._decoder_lock = asyncio.Lock()
        self._voice_ready = False
        self.packets = 0
        self._pending = set()      # tap / double-tap work runs beside the audio, kept so it is not collected

    @property
    def connected(self):
        return self.ws is not None and not self.ws.closed

    async def _get_decoder(self):
        if self._decoder is None:
            async with self._decoder_lock:
                if self._decoder is None:
                    from vexo_open.audio import PcmDecoder

                    print("Phone band: loading the sound decoder...")
                    self._decoder = await asyncio.to_thread(PcmDecoder)
        return self._decoder

    async def _audio(self, msg):
        if self.voice is None:
            return
        try:
            opus = base64.b64decode(msg.get("opus_b64") or "")
        except Exception:
            return
        if not opus:
            return
        decoder = await self._get_decoder()
        if not self._voice_ready:
            await self.voice.transport.input().ready.wait()
            self._voice_ready = True
        pcm = decoder.feed(opus)            # no seq: our seq restarts per phone connection, and gaps are dropped audio
        if pcm:
            await self.voice.feed(pcm)
        self.packets += 1

    async def _event(self, kind):
        r = self.recall
        if kind == "tap":
            await r.on_tap()
        elif kind == "double-tap":
            await r.on_double_tap()
        elif kind == "free-fall":
            await r.broadcast("event", r.store.add_event("free-fall", "the band fell or the wearer did"))

    async def _handle(self, msg):
        t = msg.get("type")
        if t == "audio":
            await self._audio(msg)
        elif t == "event":
            task = asyncio.create_task(self._event(msg.get("kind")))   # never hold up the audio behind a tap
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
        elif t == "activity":
            await self.recall.on_activity(SimpleNamespace(
                state=msg.get("state"), steps=msg.get("steps") or 0, cadence=msg.get("cadence")))
        elif t == "battery":
            await self.recall.on_battery(SimpleNamespace(percent=msg.get("percent")))
        elif t == "hello":
            print("Phone band connected:", msg.get("client"))
            self.recall.ctx.update(connected=True, band=BAND_NAME, mic=True)
            try:
                self.recall.store.add_event("connect", BAND_NAME)
            except Exception:
                pass
            await self.recall.push_ctx()
            if self.voice is not None:
                asyncio.create_task(self._get_decoder())   # warm it up before the first packet

    async def handler(self, req):
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1 << 20)
        await ws.prepare(req)
        old, self.ws = self.ws, ws
        if old is not None and not old.closed:
            await old.close()                # one phone at a time: the newest wins
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(m.data)
                except ValueError:
                    continue
                try:
                    await self._handle(msg)
                except Exception as e:     # one bad message must not drop the band
                    print("Phone band: message failed:", type(e).__name__, e)
        finally:
            if self.ws is ws:
                self.ws = None
                print("Phone band disconnected")
                self.recall.ctx.update(connected=False, mic=False)
                await self.recall.push_ctx()
        return ws


class PhoneBandOnly(Exception):
    """app.py --phone-band: the laptop does not look for the band; the phone relays it."""
