"""Live provider benchmark with a neutral test phrase. No camera or relay is contacted."""
import asyncio
import json
import os
import time
from pathlib import Path
import aiohttp
from dotenv import load_dotenv
from pipecat.frames.frames import TTSSpeakFrame, OutputAudioRawFrame, TTSStoppedFrame, ErrorFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.deepgram.flux.tts import DeepgramFluxTTSService
from pipecat.services.deepgram.tts import DeepgramHttpTTSService

PHRASE = 'This is a speech latency check for the wearable assistant. The next message will come from the live camera after the view is available.'

class Measure(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.done = None
    def begin(self):
        self.started = time.perf_counter()
        self.first = None
        self.last = None
        self.size = 0
        self.rate = 24000
        self.done = asyncio.get_running_loop().create_future()
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame) and self.done and not self.done.done():
            self.first = self.first or time.perf_counter()
            self.last = time.perf_counter()
            self.size += len(frame.audio)
            self.rate = frame.sample_rate
        if isinstance(frame, TTSStoppedFrame) and self.size and not self.done.done():
            self.done.set_result({'first_audio_ms':round((self.first-self.started)*1000),
                'last_audio_ms':round((self.last-self.started)*1000),
                'complete_ms':round((time.perf_counter()-self.started)*1000),
                'audio_seconds':round(self.size/(self.rate*2),2)})
        if isinstance(frame, ErrorFrame) and self.done and not self.done.done():
            self.done.set_exception(RuntimeError('Speech provider returned an error.'))
        await self.push_frame(frame, direction)

async def measure(service):
    sink = Measure()
    worker = PipelineWorker(Pipeline([service,sink]), enable_rtvi=False, idle_timeout_secs=None,
                            params=PipelineParams(audio_out_sample_rate=24000))
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    task = asyncio.create_task(runner.run())
    results = []
    try:
        for _ in range(3):
            sink.begin()
            await worker.queue_frame(TTSSpeakFrame(text=PHRASE))
            results.append(await asyncio.wait_for(sink.done, 25))
        return results
    finally:
        await runner.cancel()
        await task

async def main():
    load_dotenv(Path(__file__).with_name('.env'))
    key = os.environ['DEEPGRAM_API_KEY']
    async with aiohttp.ClientSession() as session:
        flux = DeepgramFluxTTSService(api_key=key, mip_opt_out=True,
            settings=DeepgramFluxTTSService.Settings(voice='flux-heather-en'))
        aura = DeepgramHttpTTSService(api_key=key, mip_opt_out=True, aiohttp_session=session,
            settings=DeepgramHttpTTSService.Settings(voice='aura-2-thalia-en'))
        report = {'phrase':PHRASE, 'scope':'Pipecat output timing; no camera, relay, or speaker playback',
                  'flux_websocket':await measure(flux), 'aura_http':await measure(aura)}
        Path(__file__).with_name('speech-latency-benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))

if __name__ == '__main__': asyncio.run(main())
