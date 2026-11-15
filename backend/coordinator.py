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
from memory import Memory


# Sentences that are clearly a request to the device, accepted without the wake word or a double tap.
DIRECT_REQUEST = re.compile(
    r"\bwhat(?:'s| is| kind of| type of)?\b.*\b(am i holding|in my hand|in front of me|around me|am i looking at)\b"
    r"|\bis (this|it) (what|the one|the right)\b"
    r"|\b(where|find|show me)\b.*\b(exit|way out|door)\b|\bi (want|need) to (leave|get out|go out)\b"
    r"|\b(read|scan)\b.*\b(label|price|sign)\b"
    r"|\bwhat did\b.*\b(want|ask|say|tell)\b", re.I)

class Coordinator:
    def __init__(self, providers):
        self.providers = providers
        directory = Path(os.getenv('BACKEND_DATA_DIR', '.data'))
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / 'backend.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, data TEXT)')
        # Full session logs: one JSONL file per session, never trimmed (the events table keeps only 300).
        # A session starts when the server starts and again whenever a relay connects after both were away.
        self.log_dir = directory / 'sessions'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = None
        self.new_session('server start')
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
        self.last_key = None
        self.recent_lines = []
        self.fresh_frame = None
        self.want_frame = None
        self.quiet_replies = False     # True while the current request came from the band: no "I didn't catch that" chatter
        self.warm_until = 0            # keep the glasses stream on until then: a still from a live stream takes ~2 s, a cold photo 3-6 s
        self.last_said = 0
        self.latest_image = None
        self.listen_until = 0
        self.glasses_state = 'disconnected'
        self.providers.audit = self.log
        self.memory = Memory(self.db, providers, self.log)     # Recall: the wearer's long-term memory

    def live_missing(self, require_band=True):
        roles = ('band', 'glasses') if require_band else ('glasses',)
        missing = [role + ' relay' for role in roles if role not in self.clients]
        if self.glasses_state not in ('connected', 'streaming'): missing.append('Meta camera connection')
        required = ['DEEPGRAM_API_KEY', 'GEMINI_API_KEY']
        if os.getenv('VOICE_TTS_PROVIDER') == 'elevenlabs': required.append('ELEVENLABS_API_KEY')
        missing.extend(key for key in required if not os.getenv(key))
        return missing

    def new_session(self, why):
        name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.jsonl'
        self.session_file = self.log_dir / name
        with open(self.session_file, 'a') as f:
            f.write(json.dumps({'ts': round(time.time() * 1000), 'agent': 'Session', 'event': 'started', 'detail': why}) + '\n')

    def log(self, agent, event, detail, **extra):
        row = {'ts': round(time.time() * 1000), 'agent': agent, 'event': event, 'detail': detail, **extra}
        if agent == 'Transport' and event == 'connected' and len(self.clients) <= 1 \
                and self.session_file and self.session_file.stat().st_size > 400:
            self.new_session(f'{detail} relay connected')
        try:
            with open(self.session_file, 'a') as f: f.write(json.dumps(row, default=str) + '\n')
        except OSError: pass
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
                    'recall': True},
                'memory': self.memory.snapshot(),
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

    async def stop(self):
        self.epoch += 1
        self.plan_version += 1
        self.route_version += 1
        self.streaming = False
        self.pending.clear()
        if time.monotonic() >= self.warm_until:
            await self.send('glasses', {'type': 'stream', 'on': False, 'fps': 1})
        else:
            self.spawn(self.cooldown())
        await self.send('glasses', {'type': 'stop_speaking'})
        await self.send('band', {'type': 'led', 'color': '#2266ff'})
        self.log('Coordinator', 'stopped', 'Camera tasks invalidated; late results will be discarded.')

    async def submit(self, text, source='typed', speaker='unknown'):
        text = text.strip()[:1000]
        if not text: return
        self.log('Deepgram' if source == 'band' else 'Dashboard', 'transcript', text)
        if source == 'band':
            # Recall: everything the band hears is remembered, also talk the planner ignores (wake word).
            tag = {'wearer': 'close voice, probably the wearer', 'nearby': 'farther voice, probably someone else'}.get(speaker, 'unknown voice')
            self.memory.keep(f'[{tag}] {text}', 'band', self.activity)
            self.recent_lines = (self.recent_lines + [f'{speaker}: {text}'])[-6:]
        if text.lower() in ('stop', 'got it', 'stop looking', 'stop watching', 'hold on'):
            self.warm_until = 0                 # an explicit stop also turns the warm stream off
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
            elif time.monotonic() <= self.listen_until:
                self.listen_until = 0                    # the double-tap window is for one sentence
            elif os.getenv('REQUIRE_WAKE_WORD', '0') == '1' and time.monotonic() > self.listen_until:
                # Not addressed by name and no double tap. Fast path: the last sentence is plainly a request.
                sentences = [part.strip() for part in re.split(r'(?<=[.?!])\s+', text) if part.strip()]
                request = next((part for part in reversed(sentences[-2:]) if DIRECT_REQUEST.search(part)), None)
                if request:
                    text = request
                else:
                    # Otherwise the gate agent decides (one Gemini call, off the audio path).
                    self.spawn(self.gate(text, speaker))
                    return
        await self.accept(text, quiet=source == 'band')

    async def gate(self, text, speaker):
        try:
            started = time.monotonic()
            addressed, request = await self.providers.addressed(text, speaker, self.recent_lines[:-1], self.streaming)
            self.log('Gate · Gemini', 'decision', 'request' if addressed else 'ignored', heard=text[:160], speaker=speaker,
                     ms=round((time.monotonic() - started) * 1000))
            if addressed: await self.accept(request, quiet=True)
        except Exception as error:
            self.log('Gate · Gemini', 'failed', type(error).__name__)

    async def accept(self, text, quiet=False):
        self.quiet_replies = quiet
        # Tell the wearer at once that the request was heard; the answer follows.
        if os.getenv('WARM_STREAM', '0') == '1': self.warm_until = max(self.warm_until, time.monotonic() + 300)
        self.spawn(self.voice.say('Okay.'))
        await self.send('band', {'type': 'led', 'color': '#00bb66'})
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
            if scene == 'reply':
                if self.quiet_replies:
                    self.log('Coordinator', 'no_reply', 'Planner found no request in this sentence; staying silent.')
                else:
                    await self.say(plan.get('reply') or 'Please ask me to read a view or plan a route.')
                return
            if scene == 'memory':
                self.log('Researcher · Recall', 'started', text)
                try:
                    answer = await self.memory.answer(text)      # in-process (memory.py)
                except Exception:
                    if not os.getenv('RECALL_WS_URL'): raise
                    answer = await self.providers.recall(text)   # fallback: a separate Recall server
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
            if scene not in ('fridge', 'label', 'bus', 'shelf', 'scene', 'exit', 'match'): raise RuntimeError('Planner returned an unsupported action.')
            self.epoch += 1
            self.pending.clear()
            if self.streaming and scene in ('fridge', 'label', 'match'):
                self.streaming = False          # frames stop being analysed; the stream itself stays warm
            self.scene, self.target = scene, str(plan.get('target', ''))[:250]
            if scene == 'bus' and self.bus:
                self.target = self.bus['line'] + ' toward ' + self.bus.get('headsign', '')
            if scene in ('fridge', 'label', 'match'):
                await self.capture(self.epoch)
            else:
                # The agent ends the session itself (answer given, goal reached, "stop"); this is only a safety cap.
                self.last_summary, self.last_key, self.last_said = '', None, 0
                await self.stream(self.epoch, 180)
        except Exception as error:
            self.log('Planner', 'failed', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
            if version == self.plan_version: await self.say('I could not complete that request. Check the provider status on the dashboard.')

    async def cooldown(self):
        """Turn the warm stream off once no request has come for a while."""
        while time.monotonic() < self.warm_until: await asyncio.sleep(5)
        if not self.streaming and 'glasses' in self.clients:
            await self.send('glasses', {'type': 'stream', 'on': False, 'fps': 1})
            self.log('Vision', 'stream_cooled', 'No request for two minutes: camera off.')

    async def capture(self, epoch=None):
        if os.getenv('LIVE_ONLY', '1') == '1' and self.live_missing(require_band=False):
            self.log('Vision', 'blocked', 'Live capture missing: ' + ', '.join(self.live_missing(require_band=False)))
            return
        epoch = self.epoch if epoch is None else epoch
        if self.fresh_frame and time.monotonic() - self.fresh_frame[0] < 1.6 and not self.frame_busy:
            message = self.fresh_frame[1]
            self.frame_busy = True
            self.last_frame = time.monotonic()
            self.latest_image = {'jpeg_b64': message['jpeg_b64'], 'ts': message['ts'], 'scene': self.scene}
            self.log('Vision', 'frame_from_live_stream', self.scene, age_ms=round((time.monotonic() - self.fresh_frame[0]) * 1000))
            self.spawn(self.analyze(message['jpeg_b64'], message['ts'], epoch, self.scene, self.target))
            return
        if self.glasses_state == 'streaming' and not self.frame_busy:
            # Stream is running but the newest frame is old: take the next one (they come every second).
            self.want_frame = (epoch, time.monotonic())
            self.log('Vision', 'waiting_for_stream_frame', self.scene)
            return
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
                await self.say('Camera off.')
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
            self.log('Vision', 'photo_received', message.get('source', '?'), ms=round((time.monotonic()-request['at'])*1000))
            if self.glasses_state != 'streaming' and time.monotonic() < self.warm_until:
                await self.send('glasses', {'type': 'stream', 'on': True, 'fps': 1})      # next still comes from the live stream
                self.spawn(self.cooldown())
        else:
            self.fresh_frame = (time.monotonic(), message)        # newest stream frame, kept even when not analysed
            if self.want_frame and self.want_frame[0] == self.epoch and time.monotonic() - self.want_frame[1] < 6 and not self.frame_busy:
                self.want_frame = None
                self.frame_busy = True
                self.last_frame = time.monotonic()
                self.latest_image = {'jpeg_b64': message['jpeg_b64'], 'ts': message['ts'], 'scene': self.scene}
                self.log('Vision', 'frame_from_live_stream', self.scene, age_ms=0)
                self.spawn(self.analyze(message['jpeg_b64'], message['ts'], self.epoch, self.scene, self.target))
                return
            if not self.streaming or self.frame_busy or time.monotonic()-self.last_frame < 2:
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
            if scene == 'match':
                result = await self.providers.match(image, target, self.memory.context())     # eyes + memory, one call
            else:
                result = await self.providers.vision(scene, image, target)
            if epoch != self.epoch: return
            age_ms = round(time.time()*1000 - captured_at)
            if scene == 'exit' and age_ms > 8000: return      # wearer is turning: an old frame is just dropped
            if scene in ('scene', 'bus', 'shelf') and age_ms > 8000:
                self.log('Vision · Gemini', 'stale_result_discarded', 'Analysis arrived too late for a current scene description.', age_ms=age_ms)
                await self.say('This view took too long to process and is no longer current. Please pause for a fresh view.')
                return
            self.log('Vision · Gemini', 'observation', result['description'], visible=result['visible'],
                     hazards=result['hazards'], captured_at=captured_at, ms=round((time.monotonic()-started)*1000))
            seen = ', '.join(result['visible']) if scene == 'shelf' and result['visible'] else result['description']
            self.memory.keep(f'Seen through the glasses ({scene}): {seen}', 'glasses', self.activity)
            summary = result['description']
            if scene == 'shelf' and result.get('found'):
                # Guide: the target is reached; end the camera session after saying so.
                self.log('Guide · Gemini', 'goal_reached', target)
                await self.stop()
                await self.say(summary)
                return
            if scene == 'bus' and self.bus:
                # A number match is evidence, never permission to board or cross.
                matched = any(re.search(r'(?<!\w)' + re.escape(self.bus['line']) + r'(?!\w)', item, re.I) for item in result['visible']) if self.bus['line'] else False
                summary += ' The visible number matches the planned line; confirm the direction and boarding with the driver.' if matched else ' I have not confirmed a match to your planned bus.'
            if scene == 'match':
                self.log('Researcher · Recall', 'evidence', summary, item=', '.join(result['visible']))
                await self.say(summary)
                return
            if scene == 'exit':
                if result.get('found'):
                    self.log('Guide · Gemini', 'goal_reached', 'exit ' + str(result.get('position')))
                    await self.stop()                      # the agent closes the camera once it has the answer
                    await self.say(summary)
                elif time.monotonic() - self.last_said > 7 or summary != self.last_summary:
                    self.last_summary, self.last_said = summary, time.monotonic()
                    await self.say(summary)
                return
            if scene == 'scene':
                # "What is in front of me" is one question: answer once and close the camera.
                await self.stop()
                await self.say(summary)
                return
            # Same content in a different word order is still a repeat.
            key = frozenset(re.findall(r'[a-z0-9]+', summary.lower()))
            if key != self.last_key:
                self.last_key, self.last_summary = key, summary
                await self.say(summary)
        except Exception as error:
            self.log('Vision · Gemini', 'failed', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
            if epoch == self.epoch: await self.say('I could not read this view reliably. Please pause and try a clearer view.')
        finally:
            self.frame_busy = False

    async def close(self):
        await self.stop()
        for task in list(self.tasks): task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.memory.close()
        self.db.close()
