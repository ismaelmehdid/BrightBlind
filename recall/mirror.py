"""Copies the laptop's memory to the Recall on Railway (recall/cloud.py), as it happens.

The band is on the laptop, so only the laptop hears the day. The team backend runs on a server and
cannot reach the laptop, so it asks the Railway Recall instead: a fixed public address, no tunnel.
This keeps that copy up to date: every stored line (with what the body was doing) and every tap.
The Railway Recall distills its own memories with its own Gemini key and answers from them.

    RECALL_CLOUD_URL=https://<service>.up.railway.app      in .env (or --mirror)
    RECALL_CLOUD_TOKEN=<the Railway service's RECALL_TOKEN> in .env

Lines wait in a queue while Railway is unreachable and are sent when it comes back.
"""
import asyncio
import collections

import aiohttp

MAX_QUEUE = 5000
RETRY_SECONDS = 5


class Mirror:
    def __init__(self, base_url, token):
        self.base = base_url.rstrip("/")
        self.token = token
        self.queue = collections.deque(maxlen=MAX_QUEUE)   # oldest lines drop first after a very long outage
        self.sent = 0
        self.up = None                                      # unknown until the first send
        self._wake = asyncio.Event()

    # --- what Recall calls ---------------------------------------------------------------

    def utterance(self, u):
        self._push({"kind": "utterance", "text": u["text"], "source": u["source"], "ts": u["ts"],
                    "activity": u.get("activity"), "steps": u.get("steps"), "cadence": u.get("cadence"),
                    "bookmarked": bool(u.get("bookmarked"))})

    def bookmark(self, seconds):
        self._push({"kind": "bookmark", "seconds": seconds})

    def backfill(self, utterances):
        for u in utterances:
            self.utterance(u)

    def _push(self, item):
        self.queue.append(item)
        self._wake.set()

    # --- sending -------------------------------------------------------------------------

    async def run(self):
        headers = {"Authorization": "Bearer " + self.token}
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as s:
            while True:
                if not self.queue:
                    self._wake.clear()
                    await self._wake.wait()
                item = self.queue[0]
                try:
                    async with s.post(self.base + "/api/mirror", json=item) as r:
                        if r.status == 200:
                            self.queue.popleft()
                            self.sent += 1
                            self._set_up(True)
                            continue
                        if r.status in (400, 413):          # this line will never be accepted: skip it
                            print("Mirror: Railway refused a line, status", r.status)
                            self.queue.popleft()
                            continue
                        print("Mirror: Railway answered status", r.status,
                              "(401 = wrong RECALL_CLOUD_TOKEN)" if r.status == 401 else "")
                except Exception as e:
                    if self.up is not False:
                        print("Mirror: Railway not reachable:", type(e).__name__)
                self._set_up(False)
                await asyncio.sleep(RETRY_SECONDS)

    def _set_up(self, up):
        if up != self.up:
            self.up = up
            if up:
                print("Mirror: copying the memory to", self.base)
