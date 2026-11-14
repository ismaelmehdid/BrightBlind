"""One wearer, two relays. Slow agents run independently of the voice transport."""
import asyncio
import base64
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from transit_speech import transit_speech


class Coordinator:
    def __init__(self, providers):
        self.providers = providers
        directory = Path(os.getenv('BACKEND_DATA_DIR', '.data'))
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / 'backend.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, data TEXT)')
        self.clients = {}
        self.tasks = set()
        self.voice = None
        self.epoch = 0
        self.plan_version = 0
        self.route_version = 0
        self.scene = 'scene'
        self.target = ''
        self.streaming = False
        self.pending = {}
        self.bus = None
        self.activity = {}
        self.frame_busy = False
        self.last_frame = 0
        self.last_summary = ''
        self.latest_image = None
        self.listen_until = 0
        self.glasses_state = 'disconnected'
        self.providers.audit = self.log

    def live_missing(self, require_band=True):
        roles = ('band', 'glasses') if require_band else ('glasses',)
        missing = [role + ' relay' for role in roles if role not in self.clients]
        if self.glasses_state not in ('connected', 'streaming'): missing.append('Meta camera connection')
        required = ['DEEPGRAM_API_KEY', 'GEMINI_API_KEY']
        if os.getenv('VOICE_TTS_PROVIDER') == 'elevenlabs': required.append('ELEVENLABS_API_KEY')
        missing.extend(key for key in required if not os.getenv(key))
        return missing

    def log(self, agent, event, detail, **extra):
        row = {'ts': round(time.time() * 1000), 'agent': agent, 'event': event, 'detail': detail, **extra}
        self.db.execute('INSERT INTO events(data) VALUES(?)', (json.dumps(row),))
        self.db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 300)')
        self.db.commit()

    def snapshot(self):
        return {'clients': list(self.clients), 'scene': self.scene, 'target': self.target,
                'live_only': os.getenv('LIVE_ONLY', '1') == '1', 'live_missing': self.live_missing(),
                'streaming': self.streaming, 'activity': self.activity, 'transit': self.bus,
                'image': self.latest_image, 'providers': {
                    'deepgram': bool(os.getenv('DEEPGRAM_API_KEY')),
                    **({'elevenlabs': bool(os.getenv('ELEVENLABS_API_KEY'))} if os.getenv('VOICE_TTS_PROVIDER') == 'elevenlabs' else {}),
                    'gemini': bool(os.getenv('GEMINI_API_KEY')), 'maps': bool(os.getenv('GOOGLE_MAPS_API_KEY')),
                    'recall': bool(os.getenv('RECALL_WS_URL'))},
                'events': [json.loads(row[0]) for row in self.db.execute('SELECT data FROM events ORDER BY id DESC LIMIT 80')]}

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def send(self, role, message):
        socket = self.clients.get(role)
        if not socket: return False
        try:
            await asyncio.wait_for(socket.send_json({'ts': round(time.time() * 1000), **message}), 3)
            return True
        except Exception:
            self.log('Transport', 'send_failed', role)
            return False

    async def say(self, text):
        text = str(text)[:700]
        self.log('Coordinator', 'reply', text)
        await self.voice.say(text)

    async def acknowledge_view(self):
        self.log('Coordinator', 'acknowledgement', 'Camera request sent; visual analysis is pending.')
        await self.voice.say('Looking now.')

    async def stop(self):
        self.epoch += 1
        self.plan_version += 1
        self.route_version += 1
        self.streaming = False
        self.pending.clear()
        await self.send('glasses', {'type': 'stream', 'on': False, 'fps': 1})
        await self.send('glasses', {'type': 'stop_speaking'})
        await self.send('band', {'type': 'led', 'color': '#2266ff'})
        self.log('Coordinator', 'stopped', 'Camera tasks invalidated; late results will be discarded.')

    async def submit(self, text, source='typed'):
        text = text.strip()[:1000]
        if not text: return
        self.log('Deepgram' if source == 'band' else 'Dashboard', 'transcript', text)
        if text.lower() in ('stop', 'got it', 'stop looking', 'stop watching', 'hold on'):
            await self.stop()
            await self.voice.interrupt()
            return
        missing = self.live_missing(require_band=source == 'band')
        if os.getenv('LIVE_ONLY', '1') == '1' and missing:
            self.log('Coordinator', 'blocked', 'Live workflow missing: ' + ', '.join(missing))
            return
        if source == 'band':
            addressed = re.match(r'^(?:hey\s+)?second\s*vision[\s,:]+(.+)$', text, re.I)
            if addressed: text = addressed[1]
            elif os.getenv('REQUIRE_WAKE_WORD', '0') == '1' and time.monotonic() > self.listen_until: return
        self.plan_version += 1
        self.spawn(self.plan(text, self.plan_version))

    async def plan(self, text, version):
        try:
            started = time.monotonic()
            plan = await self.providers.plan(text)
            if version != self.plan_version: return
            scene = plan.get('scene')
            self.log('Planner · '+plan.get('source', 'Gemini'), 'decision', scene, reason=plan.get('reply', ''), ms=round((time.monotonic()-started)*1000))
            if scene == 'stop': await self.stop(); return
            if scene == 'reply': await self.say(plan.get('reply') or 'Please ask me to read a view or plan a route.'); return
            if scene == 'memory':
                self.log('Researcher · Recall', 'started', text)
                answer = await self.providers.recall(text)
                if version == self.plan_version:
                    self.log('Researcher · Recall', 'evidence', answer)
                    await self.say(answer)
                return
            if scene == 'bus_timing':
                if not self.bus:
                    await self.say('First tell me your starting address and destination so I can find the bus and its departure stop.')
                    return
                await self.say('Checking the latest Maps departure estimate.')
                self.route_version += 1
                self.spawn(self.transit(self.bus['origin'], self.bus['destination'], self.route_version))
                return
            if scene == 'transit':
                if not plan.get('origin') or not plan.get('destination'):
                    await self.say('Tell me the starting address and destination so I can find the bus route.'); return
                await self.say('I’m checking Google Maps for the bus route.')
                self.route_version += 1
                self.spawn(self.transit(plan['origin'], plan['destination'], self.route_version)); return
            if scene not in ('fridge', 'label', 'bus', 'shelf', 'scene'): raise RuntimeError('Planner returned an unsupported action.')
            self.epoch += 1
            self.pending.clear()
            if self.streaming and scene in ('fridge', 'label'):
                await self.send('glasses', {'type': 'stream', 'on': False, 'fps': 1})
                self.streaming = False
            self.scene, self.target = scene, str(plan.get('target', ''))[:250]
            if scene == 'bus' and self.bus:
                self.target = self.bus['line'] + ' toward ' + self.bus.get('headsign', '')
            if scene in ('fridge', 'label'):
                await self.capture(self.epoch)
            else:
                await self.stream(self.epoch, 30)
        except Exception as error:
            self.log('Planner', 'failed', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
            if version == self.plan_version: await self.say('I could not complete that request. Check the provider status on the dashboard.')

    async def capture(self, epoch=None):
        if os.getenv('LIVE_ONLY', '1') == '1' and self.live_missing(require_band=False):
            self.log('Vision', 'blocked', 'Live capture missing: ' + ', '.join(self.live_missing(require_band=False)))
            return
        epoch = self.epoch if epoch is None else epoch
        req_id = str(uuid.uuid4())
        self.pending = {req_id: {'epoch': epoch, 'at': time.monotonic(), 'scene': self.scene, 'target': self.target}}
        if not await self.send('glasses', {'type': 'capture', 'req_id': req_id, 'quality': 'medium'}):
            self.pending.clear(); await self.say('The glasses relay is disconnected.'); return
        await self.send('band', {'type': 'led', 'color': '#00bb66'})
        self.log('Vision', 'capture_requested', self.scene, req_id=req_id)
        await self.acknowledge_view()

    async def stream(self, epoch, duration):
        if epoch != self.epoch: return
        if os.getenv('LIVE_ONLY', '1') == '1' and self.live_missing(require_band=False):
            self.log('Vision', 'blocked', 'Live stream missing: ' + ', '.join(self.live_missing(require_band=False)))
            return
        socket = self.clients.get('glasses')
        if not socket: await self.say('Connect the glasses relay before starting a camera session.'); return
        reuse = self.streaming and self.glasses_state == 'streaming'
        self.streaming = True
        if not reuse and not await self.send('glasses', {'type': 'stream', 'on': True, 'fps': 1}):
            self.streaming = False
            return
        await self.send('band', {'type': 'led', 'color': '#00bb66'})
        self.log('Vision', 'stream_reused' if reuse else 'stream_requested', f'{self.scene}: 1 fps requested, at most one model call at a time.')
        await self.acknowledge_view()
        async def expire():
            await asyncio.sleep(duration)
            if epoch == self.epoch and self.streaming:
                await self.stop()
                await self.say('The short camera session has ended.')
        self.spawn(expire())

    async def transit(self, origin, destination, version):
        try:
            self.log('Transit · Google Maps', 'started', origin + ' → ' + destination)
            route = await self.providers.transit(origin, destination)
            if version != self.route_version: return
            self.bus = route
            self.log('Transit · Google Maps', 'route_ready', f"Line {route['line']}, stop {route['stop']}", departure=route['departure_time'])
            await self.say(transit_speech(route))
            if route.get('departure_time'):
                departure = datetime.fromisoformat(route['departure_time'].replace('Z', '+00:00')).timestamp()
                delay = max(0, departure - time.time() - 60)
                if delay <= 1800:
                    self.log('Coordinator', 'bus_watch_scheduled', 'Start camera at estimated departure minus 60 seconds; this is not a verified arrival feed.')
                    async def watch():
                        await asyncio.sleep(delay)
                        if version == self.route_version:
                            self.epoch += 1
                            self.scene, self.target = 'bus', route['line'] + ' ' + route['headsign']
                            await self.stream(self.epoch, 90)
                    self.spawn(watch())
        except Exception as error:
            self.log('Transit · Google Maps', 'failed', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
            if version == self.route_version: await self.say('Google Maps could not provide that route. Check the addresses and Maps credentials.')

    async def image(self, message):
        now = time.time()*1000
        if not isinstance(message.get('ts'), (int, float)) or not -5000 <= now-message['ts'] <= 5000:
            self.log('Vision', 'frame_rejected', 'Missing or stale timestamp'); return
        if message['type'] == 'photo':
            request = self.pending.pop(message.get('req_id'), None)
            if not request or request['epoch'] != self.epoch or time.monotonic()-request['at'] > 20:
                self.log('Vision', 'photo_rejected', 'No matching current capture request'); return
        elif not self.streaming or self.frame_busy or time.monotonic()-self.last_frame < 2:
            return
        value = message.get('jpeg_b64', '')
        if not isinstance(value, str) or len(value) > 4_000_000: return
        try:
            data = base64.b64decode(value, validate=True)
            if not data.startswith(b'\xff\xd8'): return
        except Exception: return
        if self.frame_busy: return
        self.frame_busy = True
        self.last_frame = time.monotonic()
        epoch, scene, target = self.epoch, self.scene, self.target
        self.latest_image = {'jpeg_b64': value, 'ts': message['ts'], 'scene': scene}
        self.spawn(self.analyze(value, message['ts'], epoch, scene, target))

    async def analyze(self, image, captured_at, epoch, scene, target):
        started = time.monotonic()
        try:
            result = await self.providers.vision(scene, image, target)
            if epoch != self.epoch: return
            age_ms = round(time.time()*1000 - captured_at)
            if scene in ('scene', 'bus', 'shelf') and age_ms > 8000:
                self.log('Vision · Gemini', 'stale_result_discarded', 'Analysis arrived too late for a current scene description.', age_ms=age_ms)
                await self.say('This view took too long to process and is no longer current. Please pause for a fresh view.')
                return
            self.log('Vision · Gemini', 'observation', result['description'], visible=result['visible'],
                     hazards=result['hazards'], captured_at=captured_at, ms=round((time.monotonic()-started)*1000))
            summary = result['description']
            if scene == 'bus' and self.bus:
                # A number match is evidence, never permission to board or cross.
                matched = any(re.search(r'(?<!\w)' + re.escape(self.bus['line']) + r'(?!\w)', item, re.I) for item in result['visible']) if self.bus['line'] else False
                summary += ' The visible number matches the planned line; confirm the direction and boarding with the driver.' if matched else ' I have not confirmed a match to your planned bus.'
            if summary != self.last_summary:
                self.last_summary = summary; await self.say(summary)
        except Exception as error:
            self.log('Vision · Gemini', 'failed', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
            if epoch == self.epoch: await self.say('I could not read this view reliably. Please pause and try a clearer view.')
        finally:
            self.frame_busy = False

    async def close(self):
        await self.stop()
        for task in list(self.tasks): task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.db.close()
