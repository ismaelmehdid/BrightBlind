"""Protocol integration tests run real Pipecat; providers and wearables are explicit fixtures."""
import base64
import os
import tempfile
import time
import unittest
import math
import struct
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

os.environ.update(HOST='127.0.0.1', LIVE_ONLY='0', DEEPGRAM_API_KEY='', ELEVENLABS_API_KEY='',
                  BAND_RELAY_TOKEN='', GLASSES_RELAY_TOKEN='', DASHBOARD_TOKENS='')
from server import make_app
from pipecat.frames.frames import TTSStartedFrame, TTSStoppedFrame, OutputAudioRawFrame

class Fixtures:
    async def close(self): pass
    async def plan(self, text):
        return {'scene': text if text in ('fridge', 'shelf', 'bus', 'scene') else 'reply',
                'target': 'dark chocolate', 'reply': 'This answer passed through Pipecat.'}
    async def vision(self, scene, image, target):
        return {'description': 'A milk carton is visible.', 'visible': ['milk'], 'hazards': [], 'uncertain': False}
    async def transit(self, origin, destination): raise RuntimeError('Fixture does not make Maps calls')
    async def recall(self, text): return 'Fixture memory'

def message(message_type, **fields):
    return {'type': message_type, 'ts': round(time.time()*1000), **fields}

def receive_after_ack(socket):
    for _ in range(6):
        message = socket.receive_json()
        if message.get('text') not in ('Looking now.', 'Okay.'):
            return message
    raise AssertionError('Expected a result after the acknowledgement')

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'BACKEND_DATA_DIR': self.directory.name})
        self.env.start()
    def tearDown(self):
        self.env.stop(); self.directory.cleanup()

    def test_typed_question_runs_pipecat_and_matches_existing_glasses_relay(self):
        with TestClient(make_app(Fixtures())) as client:
            with client.websocket_connect('/ws') as glasses:
                glasses.send_json(message('hello', client='glasses', caps=['capture', 'stream', 'say']))
                self.assertEqual(glasses.receive_json()['type'], 'stop_speaking')
                self.assertEqual(client.post('/api/question', json={'text': 'hello'}).status_code, 202)
                reply = receive_after_ack(glasses)
                self.assertEqual(reply['type'], 'say')
                self.assertIn('Pipecat', reply['text'])
                self.assertIsInstance(reply['ts'], int)
                state = client.get('/api/state').json()
                self.assertTrue(any(event['agent'] == 'Planner · Gemini' for event in state['events']))

    def test_correlated_capture_freshness_and_stop(self):
        with TestClient(make_app(Fixtures())) as client:
            with client.websocket_connect('/ws') as glasses:
                glasses.send_json(message('hello', client='glasses', caps=['capture', 'stream', 'say']))
                glasses.receive_json()
                client.post('/api/question', json={'text': 'fridge'})
                capture = glasses.receive_json()
                self.assertEqual(capture['type'], 'capture')
                jpeg = base64.b64encode(b'\xff\xd8fixture\xff\xd9').decode()
                glasses.send_json(message('photo', jpeg_b64=jpeg, w=10, h=10, source='capture', req_id='wrong'))
                time.sleep(.05)
                self.assertIsNone(client.get('/api/state').json()['image'])
                glasses.send_json(message('frame', jpeg_b64='bad jpeg'))
                glasses.send_json(message('photo', jpeg_b64='bad jpeg', req_id=capture['req_id']))
                glasses.send_json(message('photo', jpeg_b64=jpeg, w=10, h=10, source='capture', req_id=capture['req_id']))
                self.assertIn('milk', receive_after_ack(glasses)['text'])
                client.post('/api/question', json={'text': 'shelf'})
                stream = glasses.receive_json()
                self.assertEqual((stream['type'], stream['on'], stream['fps']), ('stream', True, 1))
                client.post('/api/stop', json={})
                self.assertFalse(receive_after_ack(glasses)['on'])
                self.assertEqual(receive_after_ack(glasses)['type'], 'stop_speaking')
                self.assertFalse(client.get('/api/state').json()['streaming'])

    def test_replacement_glasses_never_reuse_previous_relay_frame(self):
        app = make_app(Fixtures())
        with TestClient(app) as client, client.websocket_connect('/ws') as old:
            old.send_json(message('hello', client='glasses'))
            old.receive_json()
            jpeg = base64.b64encode(b'\xff\xd8fixture\xff\xd9').decode()
            old.send_json(message('frame', jpeg_b64=jpeg))
            self.assertEqual(client.get('/api/state').status_code, 200)
            with client.websocket_connect('/ws') as new:
                new.send_json(message('hello', client='glasses'))
                new.receive_json()
                client.post('/api/question', json={'text': 'fridge'})
                self.assertEqual(new.receive_json()['type'], 'capture')
                self.assertIsNone(client.get('/api/state').json()['image'])

    def test_band_gesture_and_reconnect(self):
        with TestClient(make_app(Fixtures())) as client:
            with client.websocket_connect('/ws') as glasses, client.websocket_connect('/ws') as band:
                glasses.send_json(message('hello', client='glasses', caps=['capture']))
                glasses.receive_json()
                band.send_json(message('hello', client='band', caps=['audio', 'events', 'activity']))
                self.assertEqual(band.receive_json()['type'], 'led')
                band.send_json(message('activity', state='walk', steps=4, cadence=80))
                # A double tap opens the ear for one sentence; the glasses' own button ("short") takes the photo.
                band.send_json(message('event', kind='double-tap'))
                glasses.send_json(message('button', press='short'))
                first = glasses.receive_json()
                if first['type'] == 'stop_speaking': first = glasses.receive_json()
                self.assertEqual(first['type'], 'capture')
                self.assertEqual(client.get('/api/state').json()['activity']['state'], 'walk')
            with client.websocket_connect('/ws') as replacement:
                replacement.send_json(message('hello', client='band', caps=['audio']))
                self.assertEqual(replacement.receive_json()['type'], 'led')

    def test_hold_turns_off_warm_camera_and_cancels_speech(self):
        with patch.dict(os.environ, {'WARM_ON_CONNECT': '1'}):
            with TestClient(make_app(Fixtures())) as client, client.websocket_connect('/ws') as glasses:
                glasses.send_json(message('hello', client='glasses'))
                glasses.receive_json()
                self.assertTrue(glasses.receive_json()['on'])
                glasses.send_json(message('button', press='hold'))
                self.assertFalse(glasses.receive_json()['on'])
                self.assertEqual(glasses.receive_json()['type'], 'stop_speaking')

    def test_role_tokens_and_browser_origin(self):
        with patch.dict(os.environ, {'BAND_RELAY_TOKEN': 'b'*32, 'GLASSES_RELAY_TOKEN': 'g'*32, 'DASHBOARD_TOKENS': 'd'*32}):
            with TestClient(make_app(Fixtures())) as client:
                self.assertEqual(client.get('/api/state').status_code, 401)
                self.assertEqual(client.get('/api/state', headers={'Authorization': 'Bearer '+'d'*32}).status_code, 200)
                response = client.post('/api/question', json={'text': 'hello'}, headers={'Authorization': 'Bearer '+'d'*32, 'Origin': 'https://evil.test'})
                self.assertEqual(response.status_code, 403)
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect('/ws?token='+'b'*32) as wrong:
                        wrong.send_json(message('hello', client='glasses', caps=[]))
                        wrong.receive_json()

    def test_pipecat_audio_is_encoded_as_relay_mp3(self):
        app = make_app(Fixtures())
        with TestClient(app) as client:
            with client.websocket_connect('/ws') as glasses:
                glasses.send_json(message('hello', client='glasses', caps=['say']))
                glasses.receive_json()
                pcm = b''.join(struct.pack('<h', int(1000*math.sin(2*math.pi*440*i/24000))) for i in range(12000))
                client.portal.call(app.state.coordinator.voice.start)
                client.portal.call(app.state.coordinator.voice.worker.queue_frames, [
                    TTSStartedFrame(), OutputAudioRawFrame(audio=pcm, sample_rate=24000, num_channels=1), TTSStoppedFrame()])
                reply = glasses.receive_json()
                self.assertEqual(reply['type'], 'say')
                self.assertTrue(base64.b64decode(reply['audio_b64']).startswith(b'ID3'))
                self.assertTrue(reply['interrupt'])

    def test_live_mode_refuses_missing_hardware_instead_of_fallback(self):
        with patch.dict(os.environ, {'LIVE_ONLY': '1'}):
            with TestClient(make_app(Fixtures())) as client:
                response = client.post('/api/question', json={'text': 'read the label'})
                self.assertEqual(response.status_code, 503)
                self.assertIn('glasses relay', response.json()['detail'])
                self.assertIn('Meta camera connection', response.json()['detail'])
                self.assertTrue(client.get('/api/state').json()['live_only'])

    def test_typed_live_check_needs_real_glasses_but_not_a_fake_band(self):
        from coordinator import Coordinator
        with patch.dict(os.environ, {'DEEPGRAM_API_KEY': 'fixture', 'GEMINI_API_KEY': 'fixture'}):
            coordinator = Coordinator(Fixtures())
            try:
                coordinator.clients['glasses'] = object()
                coordinator.glasses_state = 'connected'
                self.assertEqual(coordinator.live_missing(require_band=False), [])
                self.assertIn('band relay', coordinator.live_missing())
                coordinator.glasses_state = 'disconnected'
                self.assertIn('Meta camera connection', coordinator.live_missing(require_band=False))
            finally:
                coordinator.db.close()

if __name__ == '__main__': unittest.main()
