"""The actual Pipecat path: band PCM -> Deepgram Flux -> planner -> TTS -> relay MP3."""
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
            await self.coordinator.submit(frame.text, 'typed' if isinstance(frame, TypedQuestion) else 'band')
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
        processors = []
        self.audio_ready = bool(os.getenv('DEEPGRAM_API_KEY'))
        if self.audio_ready:
            from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
            stt = DeepgramFluxSTTService(api_key=os.environ['DEEPGRAM_API_KEY'], sample_rate=16000,
                mip_opt_out=True, settings=DeepgramFluxSTTService.Settings(model='flux-general-en', eot_threshold=.75),
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

    async def question(self, text):
        await self.start()
        await self.worker.queue_frame(TypedQuestion(text=text))

    async def say(self, text):
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
        self.last_seq = seq
        if time.monotonic() < self.muted_until: pcm = bytes(len(pcm))
        self.buffer.extend(pcm)
        while len(self.buffer) >= 2560:
            packet = bytes(self.buffer[:2560]); del self.buffer[:2560]
            await self.worker.queue_frame(InputAudioRawFrame(audio=packet, sample_rate=16000, num_channels=1))
