"""Mock backend for the glasses relay: speaks the README WebSocket contract so ios/ can be
tested without backend/. Run:  uv run --with websockets ios/tools/mock_backend.py [port]
On every glasses `hello` it runs one scripted pass: say → capture → stream on 15 s → stream off,
prints timings, and saves photos/frames to ./mock-out/. Button presses trigger a capture."""
import asyncio, base64, json, os, sys, time
import websockets

OUT = "mock-out"; os.makedirs(OUT, exist_ok=True)
def now(): return time.strftime("%H:%M:%S")
def log(*a): print(now(), *a, flush=True)

async def handle(ws):
    log("client connected", ws.remote_address)
    st = {"frames": 0, "t_capture": None, "first_frame": None}
    async def send(**m):
        m["ts"] = int(time.time() * 1000); await ws.send(json.dumps(m)); log("->", {k: v for k, v in m.items() if k != "ts"})
    async def script():
        await asyncio.sleep(1)
        await send(type="say", text="Mock backend connected. Taking a photo.", interrupt=True)
        await asyncio.sleep(3)
        st["t_capture"] = time.time(); await send(type="capture", req_id="mock-1", quality="medium")
        await asyncio.sleep(15)
        st["frames"] = 0; st["first_frame"] = None; st["t_stream"] = time.time()
        await send(type="stream", on=True, fps=2)
        await asyncio.sleep(20)
        log(f"STREAM RESULT: {st['frames']} frames in 20 s, first after "
            f"{(st['first_frame'] - st['t_stream']) if st['first_frame'] else float('nan'):.1f} s")
        st["t_capture"] = time.time(); await send(type="capture", req_id="mock-2", quality="medium")
        await asyncio.sleep(6)
        await send(type="stream", on=False)
        await send(type="say", text=f"Test done. {st['frames']} frames received.", interrupt=True)
    task = None
    try:
        async for raw in ws:
            m = json.loads(raw); t = m.get("type")
            if t == "hello":
                log("<- hello", m.get("client"), m.get("caps"))
                if m.get("client") == "glasses" and task is None: task = asyncio.create_task(script())
            elif t in ("photo", "frame"):
                data = base64.b64decode(m["jpeg_b64"])
                if t == "photo":
                    dt = time.time() - st["t_capture"] if st["t_capture"] else float("nan")
                    name = f"{OUT}/photo-{int(time.time())}-{m.get('source')}.jpg"
                    open(name, "wb").write(data)
                    log(f"<- PHOTO {m.get('source')} {len(data)//1024} KB {m.get('w')}x{m.get('h')} req={m.get('req_id')} after {dt:.1f} s -> {name}")
                else:
                    st["frames"] += 1; st["first_frame"] = st["first_frame"] or time.time()
                    open(f"{OUT}/frame-latest.jpg", "wb").write(data)
                    if st["frames"] % 5 == 1: log(f"<- frame #{m.get('seq')} {len(data)//1024} KB {m.get('w')}x{m.get('h')} (total {st['frames']})")
            elif t == "button":
                log("<- button", m.get("press")); st["t_capture"] = time.time()
                await send(type="capture", req_id="button", quality="medium")
            else:
                log("<-", {k: v for k, v in m.items() if k != "ts"})
    except websockets.ConnectionClosed:
        pass
    finally:
        if task: task.cancel()
        log("client gone")

async def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    async with websockets.serve(handle, "0.0.0.0", port, max_size=32 * 1024 * 1024):
        log(f"mock backend on ws://0.0.0.0:{port}/ws"); await asyncio.Future()
asyncio.run(main())
