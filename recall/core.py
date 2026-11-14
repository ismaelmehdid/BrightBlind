"""The memory layer's heart: band context, what to store, when to distill, how to answer.

Band, Pipecat pipeline and web page all talk to one Recall object on one asyncio loop.
"""
import asyncio
import json
import time

DISTILL_EVERY = 30        # seconds between distill passes
DISTILL_QUIET = 6         # wait until nobody spoke for this long (a thought is finished)
ASK_WINDOW = 20           # after a double-tap, the next sentence within this many seconds is a question
ASK_SETTLE = 1.5          # a sentence that ends this soon after the double-tap was begun before it: not the question
ASK_MIN_WORDS = 3         # shorter sentences ("um", "okay so") do not use up the question
BOOKMARK_SECONDS = 30     # a tap keeps the last 30 seconds of speech
ANSWER_SECONDS = 20       # longest wait for Gemini's answer (the team backend gives up after 25 s)


class Recall:
    def __init__(self, store, brain, brain_problem=None):
        self.store = store
        self.brain = brain
        self.brain_problem = brain_problem
        self.clients = set()                  # open web pages (aiohttp WebSocketResponse)
        self.speak = None                     # async fn(text), set by the voice pipeline when it runs
        self.glasses = None                   # recall.glasses.Glasses: voice and camera when the phone is connected
        self.mirror = None                    # recall.mirror.Mirror: copies lines and taps to the Recall on Railway
        # With the team backend connected, it owns the conversation (double-tap, speech in the glasses) and
        # asks Recall over /ws when a question is about memory. Recall then stays silent and only remembers.
        self.defer_to_backend = False
        self.ctx = {"activity": None, "steps": None, "cadence": None, "battery": None,
                    "temperature": None, "band": None, "connected": False, "mic": False,
                    "voice": False, "brain": brain is not None, "ask_armed": False}
        self._first_steps = None
        self._ask_until = 0.0
        self._ask_ready = 0.0                 # sentences ending before this belong to what was said before the double-tap
        self._last_speech = 0.0
        self._distilling = False

    # --- pushing to the web page ---------------------------------------------------------

    async def broadcast(self, kind, data):
        msg = json.dumps({"type": kind, "data": data})
        for ws in list(self.clients):
            try:
                await ws.send_str(msg)
            except Exception:
                self.clients.discard(ws)

    async def push_ctx(self):
        self.ctx["ask_armed"] = time.time() < self._ask_until
        await self.broadcast("ctx", self.ctx)

    def snapshot(self):
        return {"ctx": self.ctx, "memories": self.store.memories(), "utterances": self.store.utterances(),
                "events": self.store.events(), "answers": self.store.answers(), "counts": self.store.counts(),
                "brain_problem": self.brain_problem}

    # --- band data -----------------------------------------------------------------------

    async def on_activity(self, e):
        if self._first_steps is None:
            self._first_steps = e.steps
        old = self.ctx["activity"]
        self.ctx.update(activity=e.state, steps=e.steps - self._first_steps, cadence=e.cadence)
        if old is not None and old != e.state:
            await self.broadcast("event", self.store.add_event("activity", f"{old} -> {e.state}"))
        await self.push_ctx()

    async def on_battery(self, e):
        self.ctx["battery"] = getattr(e, "percent", None)
        await self.push_ctx()

    async def on_temperature(self, e):
        self.ctx["temperature"] = round(getattr(e, "celsius", getattr(e, "value", 0)) or 0, 1)
        await self.push_ctx()

    async def on_tap(self, _e=None):
        """One tap: keep the last moments, even if they sound small."""
        n = self.store.bookmark_recent(BOOKMARK_SECONDS)
        if self.mirror is not None:
            self.mirror.bookmark(BOOKMARK_SECONDS)
        await self.broadcast("event", self.store.add_event("tap", f"bookmarked {n} line(s)"))
        await self.broadcast("bookmark", {"count": n})
        photo = self.glasses is not None and await self.glasses.capture("tap")
        await self._say("Saved, and looking." if photo else "Saved.")
        self._last_speech = 0                 # distill the bookmark on the next pass

    async def on_photo(self, jpeg, name):
        """A photo from the glasses: Gemini says what is in it, and that is kept as a bookmarked memory."""
        if not self.brain:
            text = "A photo was taken through the glasses."
        else:
            try:
                text = "Seen through the glasses: " + await asyncio.to_thread(self.brain.describe_photo, jpeg)
            except Exception as e:
                print("Photo description failed:", type(e).__name__, str(e)[:200])
                text = "A photo was taken through the glasses."
        u = self.store.add_utterance(text, "glasses", self.ctx, bookmarked=True, photo=name)
        if self.mirror is not None:
            self.mirror.utterance(u)
        await self.broadcast("utterance", u)
        self._last_speech = 0
        await self.distill_now()

    async def on_double_tap(self, _e=None):
        """Double-tap: the next sentence is a question to the memory."""
        if self.defer_to_backend:               # the backend's double-tap: capture + its own listening window
            await self.broadcast("event", self.store.add_event("double-tap", "handled by the team backend"))
            return
        self._ask_ready = time.time() + ASK_SETTLE
        self._ask_until = self._ask_ready + ASK_WINDOW
        await self.broadcast("event", self.store.add_event("double-tap", "ask mode"))
        await self.push_ctx()
        await self._say("Yes?")

    # --- speech --------------------------------------------------------------------------

    async def on_interim(self, text):
        await self.broadcast("interim", {"text": text})

    async def on_transcript(self, text, source="band"):
        text = text.strip()
        if not text:
            return
        self._last_speech = time.time()
        # A double-tap armed a question. A sentence that ends right after the tap was already being
        # spoken before it, and a two-word fragment is not a question: both are stored as speech,
        # and the window stays open for the real question.
        is_question = (self._ask_ready <= time.time() < self._ask_until
                       and (source != "band" or len(text.split()) >= ASK_MIN_WORDS))
        if is_question:
            self._ask_until = 0
            await self.push_ctx()
            await self.ask(text, source="voice")
            return
        u = self.store.add_utterance(text, source, self.ctx)
        if self.mirror is not None:
            self.mirror.utterance(u)
        await self.broadcast("utterance", u)

    async def from_mirror(self, item):
        """On the Railway side: a line or a tap copied from the laptop (recall/mirror.py)."""
        if item.get("kind") == "bookmark":
            n = self.store.bookmark_recent(float(item.get("seconds") or BOOKMARK_SECONDS))
            await self.broadcast("event", self.store.add_event("tap", f"bookmarked {n} line(s) (from the laptop)"))
            self._last_speech = 0
            return True
        text = str(item.get("text") or "").strip()[:4000]
        if item.get("kind") != "utterance" or not text:
            return False
        ctx = {k: item.get(k) for k in ("activity", "steps", "cadence")}
        u = self.store.add_utterance(text, str(item.get("source") or "band")[:20], ctx,
                                     bookmarked=bool(item.get("bookmarked")), ts=item.get("ts"))
        self._last_speech = time.time()
        await self.broadcast("utterance", u)
        return True

    async def ask(self, question, source="typed"):
        if not self.brain:
            answer = "I can't think yet: " + (self.brain_problem or "Gemini is off") + "."
        else:
            try:
                # The team backend gives up after 25 s; a rate-limited Gemini (429) can retry for minutes.
                answer = await asyncio.wait_for(asyncio.to_thread(
                    self.brain.answer, question, self.store.memories(),
                    self.store.utterances(limit=150), self.store.events(limit=150)), ANSWER_SECONDS)
            except asyncio.TimeoutError:
                answer = "My memory is busy right now. Please ask again in a minute."
            except Exception as e:
                answer = f"Gemini failed ({type(e).__name__})."
        row = self.store.add_answer(question, answer, source)
        await self.broadcast("answer", row)
        if source == "voice":
            await self._say(answer)
        return row

    async def _say(self, text):
        """Speak in the glasses when the phone is connected, else on the laptop."""
        if self.defer_to_backend:               # one voice only: the backend's, in the glasses
            return
        if self.glasses is not None and self.glasses.connected:
            if await self.glasses.say(text):
                return
        if self.speak:
            try:
                await self.speak(text)
            except Exception as e:
                print("Could not speak:", type(e).__name__)

    # --- distilling ----------------------------------------------------------------------

    async def distill_now(self):
        if not self.brain or self._distilling:
            return []
        rows = self.store.undistilled()
        if not rows:
            return []
        self._distilling = True
        try:
            items = await asyncio.to_thread(self.brain.distill, rows)
            made = self.store.add_memories(items, [r["id"] for r in rows])
            for m in made:
                await self.broadcast("memory", m)
            await self.broadcast("distilled", {"lines": len(rows), "memories": len(made)})
            return made
        except Exception as e:
            print("Distill failed:", type(e).__name__, str(e)[:200])
            return []
        finally:
            self._distilling = False

    async def distill_loop(self):
        while True:
            await asyncio.sleep(DISTILL_EVERY)
            if time.time() - self._last_speech >= DISTILL_QUIET:
                await self.distill_now()
            if self.ctx["ask_armed"] and time.time() >= self._ask_until:
                await self.push_ctx()         # the ask window ran out
