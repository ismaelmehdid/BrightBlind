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

    async def tap():
        await recall.on_tap()

    async def double_tap():
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

    try:
        band = await connect_band(args)
        print("Connected to", band.name)
        recall.ctx.update(connected=True, band=band.name)
        store.add_event("connect", band.name)

        band.on("activity", recall.on_activity)
        band.on("battery", recall.on_battery)
        band.on("temperature", recall.on_temperature)
        band.on("tap", recall.on_tap)
        band.on("double-tap", recall.on_double_tap)

        async def on_disconnect(e):
            recall.ctx.update(connected=False, mic=False)
            await recall.push_ctx()

        band.on("disconnect", on_disconnect)
        await band.configure(events=True, activity=True, battery=True, temperature=30)

        if voice:
            from vexo_open.audio import PcmDecoder

            print("Loading the sound decoder...")
            decoder = await asyncio.to_thread(PcmDecoder)
            await voice.transport.input().ready.wait()

            async def on_audio(a):
                await voice.feed(decoder.feed(a))

            band.on("audio", on_audio)
            print("Note: the band's microphone is on. What it hears is sent over the internet to Deepgram "
                  "(deepgram.com), and the text to Google Gemini. Tell the people near the band.")
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
