"""The actual Pipecat path: band PCM -> Deepgram Flux -> planner -> TTS -> relay MP3."""
import array
import collections
import asyncio
import base64
import os
import shutil
import time
import aiohttp
from dataclasses import dataclass
from pipecat.frames.frames import (InputAudioRawFrame, TranscriptionFrame, InterimTranscriptionFrame,
    TTSSpeakFrame, OutputAudioRawFrame, TTSStartedFrame, TTSStoppedFrame, InterruptionFrame, ErrorFrame, TextFrame, MetricsFrame)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.workers.runner import WorkerRunner


@dataclass
class TypedQuestion(TextFrame):
    pass


def mp3_with_pyav(pcm, sample_rate):
    """PCM s16le mono -> MP3 with PyAV (libmp3lame inside its wheel), for machines without the ffmpeg command,
    such as a team laptop running this backend locally. Docker keeps using ffmpeg."""
    import io
    import av
    import numpy as np
    out = io.BytesIO()
    container = av.open(out, 'w', format='mp3')
    stream = container.add_stream('libmp3lame', rate=sample_rate)
    stream.layout = 'mono'
    samples = np.frombuffer(pcm[:len(pcm) - len(pcm) % 2], dtype='<i2').reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(samples, format='s16', layout='mono')
    frame.sample_rate = sample_rate
    for packet in stream.encode(frame): container.mux(packet)
    for packet in stream.encode(None): container.mux(packet)
    container.close()
    return out.getvalue()


class PlannerInput(FrameProcessor):
    def __init__(self, coordinator):
        super().__init__(); self.coordinator = coordinator

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame): return
        if isinstance(frame, (TypedQuestion, TranscriptionFrame)) and direction == FrameDirection.DOWNSTREAM:
            typed = isinstance(frame, TypedQuestion)
            who = 'wearer' if typed else self.coordinator.voice.speaker_guess()
            await self.coordinator.submit(frame.text, 'typed' if typed else 'band', who)
            return
        await self.push_frame(frame, direction)


class GlassesOutput(FrameProcessor):
    def __init__(self, owner):
        super().__init__(); self.owner = owner; self.audio = bytearray(); self.sample_rate = 24000
        self.started = 0

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            self.audio.clear()
            await self.owner.coordinator.send('glasses', {'type': 'stop_speaking'})
        elif isinstance(frame, MetricsFrame):
            for metric in frame.data:
                if 'Usage' in type(metric).__name__:
                    self.owner.coordinator.log('Pipecat', 'provider_usage', type(metric).__name__,
                                               usage=metric.model_dump(mode='json'), credit_deduction_verified=False)
        elif isinstance(frame, TTSSpeakFrame):
            # Explicit degraded mode when the selected TTS provider is not configured.
            if os.getenv('LIVE_ONLY', '1') == '1':
                self.owner.coordinator.log('Voice', 'blocked', 'Live-only mode: no system-voice fallback.')
                return
            self.owner.muted_until = time.monotonic() + min(25, len(frame.text.split()) / 2.5 + .5)
            await self.owner.coordinator.send('glasses', {'type': 'say', 'text': frame.text, 'interrupt': True})
            self.owner.coordinator.log('Voice', 'fallback', 'iPhone system voice; selected server TTS is not configured.')
        elif isinstance(frame, TTSStartedFrame):
            self.audio.clear(); self.started = time.monotonic()
        elif isinstance(frame, OutputAudioRawFrame):
            if len(self.audio) < 2_000_000:
                self.audio.extend(frame.audio); self.sample_rate = frame.sample_rate
        elif isinstance(frame, TTSStoppedFrame) and self.audio:
            pcm = bytes(self.audio); self.audio.clear()
            try:
                if shutil.which('ffmpeg'):
                    process = await asyncio.create_subprocess_exec('ffmpeg', '-loglevel', 'error', '-f', 's16le',
                        '-ar', str(self.sample_rate), '-ac', '1', '-i', 'pipe:0', '-f', 'mp3', 'pipe:1',
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    try: audio, _ = await asyncio.wait_for(process.communicate(pcm), 5)
                    except TimeoutError:
                        process.kill(); await process.wait(); raise
                    if process.returncode: audio = b''
                else:   # no ffmpeg command on this machine: same MP3 through PyAV
                    audio = await asyncio.wait_for(asyncio.to_thread(mp3_with_pyav, pcm, self.sample_rate), 5)
                if not audio: raise RuntimeError('MP3 encoding failed')
                try:
                    # Keep every spoken clip (for the demo video): /data/audio/<time>_<first words>.mp3
                    folder = self.owner.coordinator.log_dir.parent / 'audio'
                    folder.mkdir(parents=True, exist_ok=True)
                    words = '-'.join(''.join(ch for ch in self.owner.last_text.lower() if ch.isalnum() or ch == ' ').split()[:8]) or 'clip'
                    name = time.strftime('%H-%M-%S') + f'_{int(time.time() * 1000) % 1000:03d}_{words}.mp3'
                    (folder / name).write_bytes(audio)
                    self.owner.coordinator.log('Voice', 'clip_saved', name, text=self.owner.last_text[:200], bytes=len(audio))
                except OSError: pass
                self.owner.muted_until = time.monotonic() + len(pcm)/(self.sample_rate*2) + .4
                delivered = await self.owner.coordinator.send('glasses', {'type': 'say', 'audio_b64': base64.b64encode(audio).decode(), 'interrupt': True})
                self.owner.coordinator.log(self.owner.tts_name + ' via Pipecat', 'audio_sent' if delivered else 'audio_undelivered', 'MP3 sent to glasses relay' if delivered else 'MP3 generated but relay delivery failed',
                                           tts_to_encoded_audio_ms=round((time.monotonic()-self.started)*1000))
            except Exception:
                self.owner.coordinator.log('Voice', 'failed', 'Could not encode or relay speech audio.')
        elif isinstance(frame, ErrorFrame):
            self.owner.coordinator.log('Voice provider', 'failed', 'Provider error; verify keys, quota and connection.')
        await self.push_frame(frame, direction)


class Voice:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.buffer = bytearray(); self.muted_until = 0; self.last_seq = -1; self.decoder = None
        # Loudness of recent band audio, to guess who spoke a turn: the wearer's mouth is ~40 cm from the
        # wrist, other people are further away, so their turns arrive quieter. An estimate, not diarization
        # (Deepgram Flux has no speaker labels).
        self.last_text = ''
        self.levels = collections.deque(maxlen=1500)      # (monotonic time, rms) per 20 ms packet, ~30 s
        # Noise gate: packets quieter than BAND_NOISE_GATE (rms, 0 = off) are sent to Deepgram as silence, so
        # far-away talk is not transcribed. Live run 11-14: wearer turns 3600-12900, table neighbours 1900-4200.
        self.gate_level = float(os.getenv('BAND_NOISE_GATE', '0') or 0)
        self.gate_open_until = 0.0
        self.gate_preroll = collections.deque(maxlen=4)   # ~80 ms kept so a word's first sound is not cut
        self.loudest_turn = 0.0
        processors = []
        self.audio_ready = bool(os.getenv('DEEPGRAM_API_KEY'))
        if self.audio_ready:
            from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
            stt = DeepgramFluxSTTService(api_key=os.environ['DEEPGRAM_API_KEY'], sample_rate=16000,
                mip_opt_out=True, settings=DeepgramFluxSTTService.Settings(model='flux-general-en', eot_threshold=.75,
                    keyterm=[term.strip() for term in os.getenv('STT_KEYTERMS', 'BrightBlind,Bright Blind,what am I holding,fig bars,raspberry,blueberry,raspberry fig bars,blueberry fig bars,Doritos,exit').split(',') if term.strip()]),
                enable_eager_end_of_turn=False)
            processors.append(stt)
        processors.append(PlannerInput(coordinator))
        provider = os.getenv('VOICE_TTS_PROVIDER', 'deepgram')
        if provider not in ('deepgram', 'elevenlabs'):
            raise RuntimeError('VOICE_TTS_PROVIDER must be deepgram or elevenlabs.')
        self.tts_session = None
        engine = os.getenv('DEEPGRAM_TTS_ENGINE', 'aura_http')
        if engine not in ('aura_http', 'flux'):
            raise RuntimeError('DEEPGRAM_TTS_ENGINE must be aura_http or flux.')
        self.tts_name = ('Deepgram Aura HTTP' if engine == 'aura_http' else 'Deepgram Flux TTS') if provider == 'deepgram' else 'ElevenLabs'
        if provider == 'deepgram' and os.getenv('DEEPGRAM_API_KEY'):
            if engine == 'aura_http':
                from pipecat.services.deepgram.tts import DeepgramHttpTTSService
                self.tts_session = aiohttp.ClientSession()
                processors.append(DeepgramHttpTTSService(api_key=os.environ['DEEPGRAM_API_KEY'],
                    mip_opt_out=True, aiohttp_session=self.tts_session,
                    settings=DeepgramHttpTTSService.Settings(
                        voice=os.getenv('DEEPGRAM_AURA_VOICE', 'aura-2-thalia-en'))))
            else:
                from pipecat.services.deepgram.flux.tts import DeepgramFluxTTSService
                processors.append(DeepgramFluxTTSService(api_key=os.environ['DEEPGRAM_API_KEY'],
                    mip_opt_out=True, settings=DeepgramFluxTTSService.Settings(
                        voice=os.getenv('DEEPGRAM_TTS_VOICE', 'flux-heather-en'))))
        elif provider == 'elevenlabs' and os.getenv('ELEVENLABS_API_KEY'):
            from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
            processors.append(ElevenLabsTTSService(api_key=os.environ['ELEVENLABS_API_KEY'],
                settings=ElevenLabsTTSService.Settings(voice=os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb'),
                    model='eleven_flash_v2_5', apply_text_normalization='on')))
        processors.append(GlassesOutput(self))
        self.worker = PipelineWorker(Pipeline(processors), enable_rtvi=False, idle_timeout_secs=None,
            params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000, enable_metrics=True, enable_usage_metrics=True))
        self.runner = WorkerRunner(handle_sigint=False)
        self.running = None
        self.start_lock = asyncio.Lock()

    async def start(self):
        async with self.start_lock:
            if self.running: return
            await self.runner.add_workers(self.worker)
            self.running = asyncio.create_task(self.runner.run())

    async def close(self):
        if self.running:
            await self.runner.cancel()
            await self.running
        if self.tts_session:
            await self.tts_session.close()

    def speaker_guess(self, window=7.0):
        """'wearer' or 'nearby' for the turn that just ended, from how loud its speech was."""
        now = time.monotonic()
        recent = sorted(level for at, level in self.levels if now - at <= window)
        if len(recent) < 20: return 'unknown'
        floor = recent[len(recent) // 5]                       # quiet 20%: room noise
        voiced = [level for level in recent if level > floor * 2.5 and level > 150]
        if len(voiced) < 8: return 'unknown'
        voiced.sort()
        turn = sum(voiced[len(voiced) // 2:]) / (len(voiced) - len(voiced) // 2)      # mean of the louder half
        self.loudest_turn = max(self.loudest_turn * .995, turn)
        who = 'wearer' if turn >= self.loudest_turn * .5 else 'nearby'
        self.coordinator.log('Voice', 'speaker_guess', who, turn_level=round(turn), loudest=round(self.loudest_turn))
        return who

    async def question(self, text):
        await self.start()
        await self.worker.queue_frame(TypedQuestion(text=text))

    async def say(self, text):
        self.last_text = str(text)
        await self.start()
        await self.worker.queue_frame(TTSSpeakFrame(text=text))

    async def interrupt(self):
        self.muted_until = 0
        if not self.running: return
        await self.worker.queue_frame(InterruptionFrame())

    def reset_audio(self):
        self.buffer.clear(); self.last_seq = -1; self.decoder = None

    async def feed(self, message):
        seq = message.get('seq')
        if not isinstance(seq, int) or seq <= self.last_seq: return
        if not self.audio_ready: return
        encoded = message.get('pcm_b64') or message.get('opus_b64')
        if not isinstance(encoded, str) or len(encoded) > 32000: return
        try:
            data = base64.b64decode(encoded, validate=True)
            if 'pcm_b64' in message:
                if len(data) % 2 or len(data) > 16000: return
                pcm = data
            else:
                import av
                if self.decoder is None:
                    codec = av.CodecContext.create('opus', 'r')
                    codec.extradata = b'OpusHead' + bytes([1, 1]) + b'\x00\x00' + (16000).to_bytes(4, 'little') + b'\x00\x00\x00'
                    self.decoder = (codec, av.AudioResampler(format='s16', layout='mono', rate=16000))
                codec, resampler = self.decoder
                pcm = b''.join(bytes(out.planes[0])[:out.samples*2] for frame in codec.decode(av.Packet(data)) for out in resampler.resample(frame))
        except Exception:
            # A corrupt or partial packet (Bluetooth drops bytes) is skipped, not fatal: PyAV's InvalidDataError is a
            # ValueError, which server.py turns into a 1008 close, and the band would reconnect with an audio gap.
            self.last_seq = seq
            self.dropped_packets = getattr(self, 'dropped_packets', 0) + 1
            return
        self.last_seq = seq
        if time.monotonic() < self.muted_until: pcm = bytes(len(pcm))
        elif len(pcm) >= 2:
            samples = array.array('h'); samples.frombytes(pcm[:len(pcm) // 2 * 2])
            rms = (sum(v * v for v in samples) / len(samples)) ** .5
            self.levels.append((time.monotonic(), rms))
            if self.gate_level:
                now = time.monotonic()
                if rms >= self.gate_level:
                    if now > self.gate_open_until and self.gate_preroll:      # gate opens: replay the lead-in
                        lead = b''.join(self.gate_preroll); self.gate_preroll.clear()
                        self.buffer[-len(lead):] = lead if len(self.buffer) >= len(lead) else self.buffer[-len(lead):]
                    self.gate_open_until = now + .6                          # stay open through pauses in a word
                elif now > self.gate_open_until:
                    self.gate_preroll.append(pcm)
                    pcm = bytes(len(pcm))
        self.buffer.extend(pcm)
        while len(self.buffer) >= 2560:
            packet = bytes(self.buffer[:2560]); del self.buffer[:2560]
            await self.worker.queue_frame(InputAudioRawFrame(audio=packet, sample_rate=16000, num_channels=1))
