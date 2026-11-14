"""Recall: a memory layer for the Vexo band.

The band hears your day; Pipecat + Deepgram Flux turn it into text; every line is stored with what
your body was doing (still, walking, running, steps); Gemini 4 distills it into memories and answers
questions about them. Tap the band once to keep the last 30 seconds; double-tap and ask out loud.

    python app.py --usb --port COM5     our band on the USB cable (Windows needs the port)
    python app.py                       our band over Bluetooth (double-tap it first)
    python app.py --sim                 a pretend band (add --sim-voice to play the kit's sample speech)

Then open http://localhost:8100 . Keys come from .env (DEEPGRAM_API_KEY, GEMINI_API_KEY), never from code.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vexo-open-kit" / "python"))

from dotenv import load_dotenv  # noqa: E402
from vexo_open import Band, audio  # noqa: E402

from recall import web  # noqa: E402
from recall.brain import MODEL, make_brain  # noqa: E402
from recall.core import Recall  # noqa: E402
from recall.store import Store  # noqa: E402

BAND = 63  # our team's band number: Vexo-HACK-63. Change it only here.


def parse_args():
    p = argparse.ArgumentParser(description="Recall: memory layer for the Vexo band")
    p.add_argument("--usb", action="store_true", help="use the USB cable")
    p.add_argument("--port", help="serial port of the band, e.g. COM5")
    p.add_argument("--sim", action="store_true", help="pretend band, no hardware")
    p.add_argument("--sim-voice", action="store_true", help="pretend band plays the kit's sample speech")
    p.add_argument("--web-port", type=int, default=8100)
    p.add_argument("--db", default=str(ROOT / "recall.db"))
    p.add_argument("--backend", default=os.getenv("BACKEND_WS_URL"),
                   help="team backend WebSocket, e.g. ws://host:port/ws: also forward band data there (contract v0)")
    p.add_argument("--backend-pcm", action="store_true", help="send decoded PCM to the backend instead of Opus")
    return p.parse_args()


async def connect_band(args):
    if args.sim:
        from vexo_open.transports.sim import SimTransport

        packets = None
        if args.sim_voice:
            packets = audio.ogg_packets(ROOT / "vexo-open-kit" / "dashboard" / "speech" / "sample-speech.opus")
        return await Band.connect(BAND, transport=SimTransport(BAND, auto_tap=False, audio_packets=packets))
    if args.usb:
        options = {"port": args.port} if args.port else {}
        return await Band.connect(BAND, transport="serial", **options)
    return await Band.connect(BAND, auto_reconnect=True)  # fails with "wrong-band" if another band answers


async def main():
    args = parse_args()
    load_dotenv(ROOT / ".env")

    store = Store(args.db)
    brain, problem = make_brain()
    recall = Recall(store, brain, problem)
    print(f"Brain: Gemini {MODEL}" if brain else f"Brain off: {problem}")

    band = None

    # Page buttons. With the pretend band they tap the band itself, so the whole path runs
    # (band event -> memory -> backend relay); otherwise they act on the memory directly.
    async def tap():
        if args.sim and band:
            band.transport.tap("tap")
        else:
            await recall.on_tap()

    async def double_tap():
        if args.sim and band:
            band.transport.tap("double-tap")
        else:
            await recall.on_double_tap()

    runner = await web.start(recall, {"tap": tap, "double-tap": double_tap}, args.web_port)
    print(f"Open http://localhost:{args.web_port}")

    voice = None
    if os.getenv("DEEPGRAM_API_KEY"):
        from recall.voice import Voice

        voice = Voice(recall)
        recall.ctx["voice"] = True
    else:
        print("Voice off: no DEEPGRAM_API_KEY in .env. Typed notes and questions still work.")

    tasks = [asyncio.create_task(recall.distill_loop())]
    if voice:
        tasks.append(asyncio.create_task(voice.run()))

    relay = None
    if args.backend:
        from recall.relay import BackendRelay

        async def backend_status(up):
            recall.ctx["backend"] = up
            await recall.push_ctx()

        relay = BackendRelay(args.backend, lambda: band, pcm=args.backend_pcm, on_status=backend_status)
        recall.ctx["backend"] = False
        tasks.append(asyncio.create_task(relay.run()))
        print("Backend relay: forwarding band audio, taps and activity to", args.backend)

    try:
        band = await connect_band(args)
        print("Connected to", band.name)
        recall.ctx.update(connected=True, band=band.name)
        store.add_event("connect", band.name)

        async def on_activity(e):
            await recall.on_activity(e)
            if relay:
                await relay.activity(e)

        async def on_tap(e):
            await recall.on_tap(e)
            if relay:
                await relay.event("tap")

        async def on_double_tap(e):
            await recall.on_double_tap(e)
            if relay:
                await relay.event("double-tap")

        async def on_other_event(e):
            if relay:
                await relay.event(e.kind)
            if e.kind == "free-fall":
                await recall.broadcast("event", store.add_event("free-fall", "the band fell or the wearer did"))

        band.on("activity", on_activity)
        band.on("battery", recall.on_battery)
        band.on("temperature", recall.on_temperature)
        band.on("tap", on_tap)
        band.on("double-tap", on_double_tap)
        band.on("free-fall", on_other_event)
        band.on("tilt", on_other_event)

        async def on_disconnect(e):
            recall.ctx.update(connected=False, mic=False)
            await recall.push_ctx()

        band.on("disconnect", on_disconnect)
        await band.configure(events=True, activity=True, battery=True, temperature=30)

        if voice or relay:
            decoder = None
            if voice or args.backend_pcm:
                from vexo_open.audio import PcmDecoder

                print("Loading the sound decoder...")
                decoder = await asyncio.to_thread(PcmDecoder)
            if voice:
                await voice.transport.input().ready.wait()

            async def on_audio(a):
                pcm = decoder.feed(a) if decoder else None
                if voice:
                    await voice.feed(pcm)
                if relay:
                    await relay.audio(a, pcm)

            band.on("audio", on_audio)
            where = []
            if voice:
                where.append("Deepgram (deepgram.com), and the text to Google Gemini")
            if relay:
                where.append(f"the team backend at {args.backend}")
            print("Note: the band's microphone is on. What it hears is sent over the internet to "
                  + "; and to ".join(where) + ". Tell the people near the band.")
            await band.configure(audio=True)  # solid blue light: mic on, LED locked
            recall.ctx["mic"] = True
        await recall.push_ctx()
    except Exception as e:  # a band problem: keep the page up so typed notes still work
        print("Band not connected:", getattr(e, "message", None) or e)
        recall.ctx["connected"] = False
        await recall.push_ctx()

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        if band:
            try:
                await band.configure(audio=False)
                await band.disconnect()
            except Exception:
                pass
        if voice:
            await voice.stop()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
