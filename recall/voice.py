"""Pipecat voice pipeline: band microphone -> Deepgram Flux (speech to text) -> Recall -> Deepgram TTS -> laptop speaker.

    BandInput --PCM 16 kHz--> DeepgramFluxSTT --TranscriptionFrame--> RecallBridge --TTSSpeakFrame--> DeepgramTTS
        --> LocalAudioOutput (laptop speaker) --> SpeakingWatch (mutes the band mic while the laptop talks)

The LLM step is not a Pipecat LLM service on purpose: most speech is only stored (ambient memory),
and only a sentence after a double-tap becomes a question to Gemini (recall/brain.py).
"""
import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pyaudio
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.local.audio import LocalAudioOutputTransport, LocalAudioTransportParams
from pipecat.workers.runner import WorkerRunner

SAMPLE_RATE = 16000                     # the band's microphone, after PcmDecoder
CHUNK = 2560                            # 80 ms of 16-bit PCM: the chunk size Flux wants
ECHO_TAIL = 0.4                         # keep the mic muted this long after the laptop stops talking
VOICE = os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en")


class BandInput(BaseInputTransport):
    """Pipecat input fed by the band's decoded microphone audio."""

    def __init__(self, params):
        super().__init__(params)
        self.ready = asyncio.Event()
        self.muted_until = 0.0          # set by SpeakingWatch: the laptop speaker is talking
        self.bot_speaking = False
        self._buf = bytearray()

    async def start(self, frame):
        await super().start(frame)
        await self.set_transport_ready(frame)
        self.ready.set()

    async def push_pcm(self, pcm):
        if self.bot_speaking or time.time() < self.muted_until:
            pcm = bytes(len(pcm))       # silence, not nothing: Flux keeps its turn timing and its socket
        self._buf.extend(pcm)
        while len(self._buf) >= CHUNK:
            chunk, self._buf = bytes(self._buf[:CHUNK]), self._buf[CHUNK:]
            await self.push_audio_frame(InputAudioRawFrame(audio=chunk, sample_rate=SAMPLE_RATE, num_channels=1))


class Speaker(LocalAudioOutputTransport):
    """The laptop speaker, able to come back after a stall.

    When one write to the sound card blocks for more than 10 s (the laptop stalls, the network
    drops for a moment, headphones are plugged in), Pipecat marks the output unusable for good
    and the memory goes silent until a restart. Here the speaker opens a fresh audio stream on a
    fresh thread instead, then reports itself usable again.
    """

    RETRY_SECONDS = 2

    def __init__(self, params):
        super().__init__(pyaudio.PyAudio(), params)
        self._recovering = False

    async def set_usable(self, is_usable):
        await super().set_usable(is_usable)
        if not is_usable and not self._recovering:
            self._recovering = True
            asyncio.create_task(self._recover())

    def _open_stream(self, py_audio):
        stream = py_audio.open(format=py_audio.get_format_from_width(2), channels=self._params.audio_out_channels,
                               rate=self.sample_rate, output=True,
                               output_device_index=self._params.output_device_index)
        stream.start_stream()
        return stream

    async def _recover(self):
        while True:
            await asyncio.sleep(self.RETRY_SECONDS)
            try:
                py_audio = await asyncio.to_thread(pyaudio.PyAudio)   # fresh device list
                stream = await asyncio.to_thread(self._open_stream, py_audio)
            except Exception as e:
                print("Speaker: still not available:", type(e).__name__)
                continue
            old_stream, old_executor = self._out_stream, self._executor
            self._py_audio, self._out_stream = py_audio, stream
            self._executor = ThreadPoolExecutor(max_workers=1)        # the old thread may still be stuck
            old_executor.shutdown(wait=False)
            if old_stream:
                threading.Thread(target=_close_quietly, args=(old_stream,), daemon=True).start()
            self._recovering = False
            await super().set_usable(True)
            print("Speaker: reopened the laptop's audio output")
            return


def _close_quietly(stream):
    try:
        stream.stop_stream()
        stream.close()
    except Exception:
        pass


class BandTransport(BaseTransport):
    def __init__(self, params):
        super().__init__()
        self._in = BandInput(params)
        self._out = Speaker(params)

    def input(self):
        return self._in

    def output(self):
        return self._out


class RecallBridge(FrameProcessor):
    """Hands every transcript to the memory layer. Transcripts stop here: the TTS must never read them aloud."""

    def __init__(self, recall):
        super().__init__()
        self.recall = recall

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            asyncio.create_task(self.recall.on_transcript(frame.text, source="band"))
            return
        if isinstance(frame, InterimTranscriptionFrame):
            await self.recall.on_interim(frame.text)
            return
        await self.push_frame(frame, direction)


class SpeakingWatch(FrameProcessor):
    """Sits after the speaker: mutes the band mic while the laptop talks, so the memory does not hear itself."""

    def __init__(self, band_input):
        super().__init__()
        self.band_input = band_input

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self.band_input.bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self.band_input.bot_speaking = False
            self.band_input.muted_until = time.time() + ECHO_TAIL
        await self.push_frame(frame, direction)


class Voice:
    """Builds and runs the pipeline. `feed(pcm)` takes 20 ms band packets once decoded."""

    def __init__(self, recall):
        key = os.environ["DEEPGRAM_API_KEY"]
        params = LocalAudioTransportParams(audio_in_enabled=True, audio_in_sample_rate=SAMPLE_RATE,
                                           audio_out_enabled=True)
        self.transport = BandTransport(params)
        stt = DeepgramFluxSTTService(
            api_key=key, mip_opt_out=True, sample_rate=SAMPLE_RATE,
            settings=DeepgramFluxSTTService.Settings(model="flux-general-en", eot_threshold=0.75,
                                                     keyterm=["Vexo", "Recall"]))
        tts = DeepgramTTSService(api_key=key, mip_opt_out=True, settings=DeepgramTTSService.Settings(voice=VOICE))
        pipeline = Pipeline([self.transport.input(), stt, RecallBridge(recall), tts,
                             self.transport.output(), SpeakingWatch(self.transport.input())])
        # idle_timeout_secs=None: ambient listening can be quiet for long stretches, the worker must not end
        self.worker = PipelineWorker(pipeline, params=PipelineParams(), idle_timeout_secs=None)
        self.runner = WorkerRunner(handle_sigint=False)
        recall.speak = self.say

    async def say(self, text):
        await self.worker.queue_frames([TTSSpeakFrame(text)])

    async def feed(self, pcm):
        await self.transport.input().push_pcm(pcm)

    async def run(self):
        await self.runner.add_workers(self.worker)
        await self.runner.run()

    async def stop(self):
        try:
            await self.worker.queue_frames([EndFrame()])
        except Exception:
            pass


__all__ = ["Voice", "FrameDirection"]
