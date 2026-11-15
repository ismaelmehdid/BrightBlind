"""Team contract v0. /ws JSON messages match the repository README."""
import asyncio
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from loguru import logger
from coordinator import Coordinator
from providers import Providers
from voice import Voice

logger.remove()
logger.add(lambda message: print(message, end=''), level='WARNING')
ROOT = Path(__file__).parent

def matches(value, expected):
    return bool(expected) and secrets.compare_digest(value.encode(), expected.encode())

class Question(BaseModel):
    text: str = Field(min_length=1, max_length=1000)

def make_app(providers=None):
    tokens = {role: os.getenv(role.upper() + '_RELAY_TOKEN', '') for role in ('band', 'glasses')}
    dashboards = [token for token in os.getenv('DASHBOARD_TOKENS', '').split(',') if token]
    guarded = any(tokens.values()) or bool(dashboards)
    if os.getenv('HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost', '::1') and (
        any(len(value) < 24 for value in tokens.values()) or not dashboards or any(len(value) < 24 for value in dashboards)):
        raise RuntimeError('Network listening requires relay tokens and dashboard tokens (24+ characters).')

    @asynccontextmanager
    async def lifespan(app):
        adapters = providers or Providers()
        coordinator = Coordinator(adapters)
        voice = Voice(coordinator)
        coordinator.voice = voice
        app.state.coordinator = coordinator
        coordinator.spawn(coordinator.memory.loop())   # Recall: distills new lines into memories
        yield
        await coordinator.stop()
        await voice.close()
        await coordinator.close()
        await adapters.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def security(request, call_next):
        if request.url.path.startswith('/api/') and guarded:
            token = request.headers.get('authorization', '').removeprefix('Bearer ')
            if not any(matches(token, candidate) for candidate in dashboards):
                return JSONResponse({'detail': 'Dashboard token required'}, status_code=401)
        if request.method == 'POST' and request.headers.get('origin'):
            from urllib.parse import urlsplit
            if urlsplit(request.headers['origin']).netloc != request.headers.get('host'):
                return JSONResponse({'detail': 'Foreign browser origin rejected'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; object-src 'none'"
        return response

    @app.get('/healthz')
    async def health():
        return {'ok': True, 'service': 'secondvision-backend', 'protocol': 'v0', 'voice': 'pipecat'}

    @app.get('/')
    async def index(): return FileResponse(ROOT / 'static' / 'index.html')

    @app.get('/dashboard.js')
    async def script(): return FileResponse(ROOT / 'static' / 'dashboard.js', media_type='text/javascript')

    @app.get('/dashboard.css')
    async def styles(): return FileResponse(ROOT / 'static' / 'dashboard.css', media_type='text/css')

    @app.get('/api/state')
    async def state(): return app.state.coordinator.snapshot()

    @app.post('/api/question', status_code=202)
    async def question(body: Question):
        missing = app.state.coordinator.live_missing(require_band=False)
        if os.getenv('LIVE_ONLY', '1') == '1' and missing:
            return JSONResponse({'detail': 'Live workflow missing: ' + ', '.join(missing)}, status_code=503)
        await app.state.coordinator.voice.question(body.text)
        return {'accepted': True, 'path': 'pipecat → planner → glasses'}

    @app.get('/api/audio')
    async def audio_list():
        folder = app.state.coordinator.log_dir.parent / 'audio'
        return [{'name': f.name, 'bytes': f.stat().st_size} for f in sorted(folder.glob('*.mp3'))] if folder.is_dir() else []

    @app.get('/api/audio/{name}')
    async def audio_file(name: str):
        path = app.state.coordinator.log_dir.parent / 'audio' / name
        if '/' in name or '..' in name or not path.is_file(): return JSONResponse({'detail': 'No such clip'}, status_code=404)
        return FileResponse(path, media_type='audio/mpeg')

    @app.post('/api/memory/reset')
    async def memory_reset():
        app.state.coordinator.recent_lines = []
        return app.state.coordinator.memory.clear()

    @app.get('/api/sessions')
    async def sessions():
        files = sorted(app.state.coordinator.log_dir.glob('*.jsonl'), reverse=True)
        return [{'name': f.name, 'bytes': f.stat().st_size} for f in files[:200]]

    @app.get('/api/sessions/{name}')
    async def session(name: str):
        path = app.state.coordinator.log_dir / name
        if '/' in name or '..' in name or not path.is_file(): return JSONResponse({'detail': 'No such session'}, status_code=404)
        return FileResponse(path, media_type='application/x-ndjson')

    @app.post('/api/stop')
    async def stop():
        app.state.coordinator.warm_until = 0
        await app.state.coordinator.stop()
        await app.state.coordinator.voice.interrupt()
        return {'stopped': True}

    @app.websocket('/ws')
    async def relay(socket: WebSocket):
        token = socket.headers.get('authorization', '').removeprefix('Bearer ') or socket.query_params.get('token', '')
        if guarded and not any(matches(token, candidate) for candidate in tokens.values()):
            await socket.close(code=1008)
            return
        await socket.accept()
        role = None
        coordinator = app.state.coordinator
        try:
            raw = await asyncio.wait_for(socket.receive_text(), 5)
            if len(raw) > 8000: raise ValueError('hello too large')
            hello = json.loads(raw)
            role = hello.get('client')
            if hello.get('type') != 'hello' or role not in ('band', 'glasses'):
                raise ValueError('First message must be hello with band or glasses client')
            if guarded and not matches(token, tokens[role]): raise ValueError('Token does not match role')
            if role in coordinator.clients:
                await coordinator.clients[role].close(code=1001, reason='Relay replaced by new connection')
            coordinator.clients[role] = socket
            if role == 'band':
                coordinator.voice.reset_audio()
                await coordinator.voice.start()
            coordinator.log('Transport', 'connected', role, caps=hello.get('caps', []))
            if role == 'band': await coordinator.send('band', {'type': 'led', 'color': '#2266ff'})
            else:
                await coordinator.send('glasses', {'type': 'stop_speaking'})
                if os.getenv('WARM_STREAM', '0') == '1':
                    # Demo mode: camera stream on from the moment the glasses connect, so the first request is fast too.
                    coordinator.warm_until = time.monotonic() + 600
                    await coordinator.send('glasses', {'type': 'stream', 'on': True, 'fps': 1})
                    coordinator.spawn(coordinator.cooldown())
            allowed = {'band': {'audio', 'event', 'activity'}, 'glasses': {'photo', 'frame', 'state', 'button'}}
            async for raw in socket.iter_text():
                if len(raw) > 5_000_000: raise ValueError('Message too large')
                message = json.loads(raw)
                if not isinstance(message, dict) or message.get('type') not in allowed[role]:
                    raise ValueError('Message type is not permitted for this client')
                kind = message['type']
                if kind == 'audio':
                    await coordinator.voice.feed(message)
                elif kind == 'activity':
                    if message.get('state') not in ('still', 'walk', 'run'): raise ValueError('Invalid activity')
                    coordinator.activity = {key: message.get(key) for key in ('state', 'steps', 'cadence', 'ts')}
                elif kind in ('photo', 'frame'):
                    await coordinator.image(message)
                elif kind == 'state':
                    coordinator.glasses_state = message.get('glasses', 'disconnected')
                    coordinator.log('Meta glasses', 'state', message.get('glasses'), battery=message.get('battery'))
                elif kind in ('event', 'button'):
                    event = message.get('kind') if kind == 'event' else message.get('press')
                    coordinator.log('Vexo band' if role == 'band' else 'Meta glasses', 'gesture', event)
                    if event in ('double-tap', 'double', 'short'):
                        # A double tap only opens the ear for the next sentence. It no longer takes a photo by
                        # itself: the band also reports double taps from ordinary arm movement, and each one
                        # made the glasses describe the desk.
                        coordinator.listen_until = time.monotonic() + 10
                        await coordinator.voice.interrupt()
                        if event == 'short': await coordinator.capture()      # the glasses' own button still means "look" 
                    elif event == 'hold': await coordinator.stop()
                    elif event == 'free-fall':
                        await coordinator.stop()
                        await coordinator.send('band', {'type': 'led', 'color': '#dd3333'})
                        await coordinator.say('The band reported a possible fall. Are you okay? Ask someone nearby for help if needed.')
                    elif event == 'tap' and role == 'band':
                        coordinator.memory.bookmark()      # Recall: a tap keeps the last 30 seconds (memory.py)
        except (ValueError, json.JSONDecodeError, TimeoutError):
            await socket.close(code=1008, reason='Invalid message or handshake')
        except WebSocketDisconnect:
            pass
        except Exception as error:
            coordinator.log('Transport', 'disconnected', type(error).__name__)
        finally:
            if role and coordinator.clients.get(role) is socket:
                del coordinator.clients[role]
                coordinator.log('Transport', 'disconnected', role)
                if role == 'glasses':
                    coordinator.glasses_state = 'disconnected'
                    coordinator.streaming = False
                    coordinator.pending.clear()
                    coordinator.epoch += 1
                if role == 'band': coordinator.voice.reset_audio()

    return app

app = make_app()
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8765')),
                ws_max_size=5_000_000, ws_max_queue=8, access_log=False)
