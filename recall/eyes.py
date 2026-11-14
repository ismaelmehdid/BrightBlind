"""Two agents that give Recall eyes on demand, through the glasses' photo burst.

  Watcher  reads every finished sentence of the transcript and decides: start the burst (with the goal,
           "find the dark chocolate"), stop it ("got it", "never mind", the user walked off), or leave it.
  Guide    gets each burst photo while the burst runs and turns it into one short spoken direction toward
           the goal ("higher", "a bit left", "that one"). It says when the goal is reached, and the burst stops.

The burst itself lives in Andrii's app (ios/). Glasses.burst(on) starts and stops it; its photos come back
to Recall as photo/frame messages and land in Eyes.on_image. Only one Gemini call runs per agent at a time:
the Watcher keeps the newest sentence that arrived while it was busy, the Guide drops photos while it thinks
(old frames are useless for live guidance).
"""
import asyncio
import json
import time

CONTEXT_LINES = 8         # transcript lines the Watcher reads with each new sentence
MAX_BURST = 120           # seconds: a burst nobody stopped ends by itself
GUIDE_GAP = 1.5           # seconds between guidance calls, at least
REPEAT_GAP = 6            # seconds before the same direction is spoken again
STALE_PHOTO = 6           # seconds: a guidance answer about an older photo is not spoken
STOP_WORDS = ("got it", "stop looking", "stop the camera", "stop watching", "never mind", "nevermind",
              "that's it", "found it")

WATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["start", "stop", "none"]},
        "goal": {"type": "string", "description": "with start: what to find or check, in a few words"},
        "say": {"type": "string", "description": "with start or stop: a very short spoken line, or empty"},
    },
    "required": ["action", "goal", "say"],
}

WATCH_INSTRUCTIONS = """You control the camera of glasses worn by a person who cannot see well. A wristband microphone
hears everything around them, so most sentences are ordinary conversation: ignore those (action "none").

Choose "start" only when the wearer asks for live visual help that needs several looks: finding or reaching
an object ("where is the dark chocolate", "help me find my keys"), lining up with something ("is the door in
front of me", "which way is the exit"), reading something they are moving toward, watching for a bus number.
goal: what to find or check, a few words ("dark chocolate bar on the shelf"). say: a two to four word
acknowledgement ("Looking now.").

Choose "stop" when a burst is running and the wearer has what they need or no longer wants it ("got it",
"thanks", "forget it", they move on to another topic, they ask for something else). say: "" or "Okay."

If a burst is running and the wearer changes the target ("no, the milk chocolate"), answer "start" with the
new goal. A single question about what is in front of them right now is not a burst: answer "none".
Return "none" with empty goal and say when unsure."""

GUIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "say": {"type": "string", "description": "one short spoken direction, or empty to stay quiet"},
        "done": {"type": "boolean", "description": "true when the goal is reached or clearly found and held"},
        "seen": {"type": "string", "description": "a few words on what the photo shows, for the log"},
    },
    "required": ["say", "done", "seen"],
}

GUIDE_INSTRUCTIONS = """You guide a person who cannot see well, through a photo from their camera glasses (the camera
sees what their face points at). You get the goal, what they said recently, and what you told them last.

Give ONE short spoken direction toward the goal, at most eight words, as directions relative to their head
and hand: "turn a little right", "higher", "a bit left", "reach forward", "your hand is on it". If the goal is
not in view, say how to look ("turn slowly left", "look down a bit"). Read out a label or number when it
decides the goal ("this is the 38"). If nothing changed since your last direction, return say "" to stay quiet.
Mention a hazard right in front of them (step, edge, obstacle) before anything else.
Never say a street, a crossing or a path is safe, never tell them to cross or to board: say what you see and
let them decide. done: true only when the goal is in their hand or clearly reached; then say a final line
("That's it, you have it.")."""


def _clock(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


class Eyes:
    def __init__(self, recall):
        self.recall = recall
        self.goal = None              # set while a burst runs
        self.started = 0.0
        self.said = []                # the Guide's recent directions: (ts, text)
        self._pending = None          # newest sentence waiting for the Watcher
        self._watching = False
        self._guiding = False
        self._last_guide = 0.0
        self._epoch = 0               # bumps on every start/stop: answers about an older burst are dropped

    @property
    def active(self):
        return self.goal is not None

    def _ready(self):
        g = self.recall.glasses
        return self.recall.brain is not None and g is not None and g.connected

    async def _log(self, kind, detail):
        print(f"Eyes: {kind}: {detail}")
        await self.recall.broadcast("event", self.recall.store.add_event(kind, detail))

    # --- Watcher: transcript -> start / stop -------------------------------------------

    async def heard(self, text):
        """Every finished sentence comes here. Never blocks the transcript."""
        if not self._ready():
            return
        low = text.lower()
        if self.active and any(w in low for w in STOP_WORDS):
            await self.stop("heard: " + text, say="Okay.")
            return
        self._pending = text
        if not self._watching:
            self._watching = True
            asyncio.create_task(self._watch_loop())

    async def _watch_loop(self):
        try:
            while self._pending:
                text, self._pending = self._pending, None
                await self.recall.agent("Watcher", "reading", text)
                try:
                    decision = await asyncio.to_thread(self._decide, text)
                except Exception as e:
                    print("Eyes: Watcher failed:", type(e).__name__, str(e)[:200])
                    await self.recall.agent("Watcher", "failed", type(e).__name__)
                    continue
                action = decision.get("action")
                await self.recall.agent("Watcher", action or "none",
                                        decision.get("goal") if action == "start" else
                                        ("stop the burst" if action == "stop" else "not a visual request"))
                if action == "start" and decision.get("goal"):
                    await self.start(decision["goal"], say=decision.get("say") or "Looking now.")
                elif action == "stop" and self.active:
                    await self.stop("watcher: " + text, say=decision.get("say") or "")
        finally:
            self._watching = False

    def _decide(self, text):
        lines = self.recall.store.utterances(limit=CONTEXT_LINES)
        said = "\n".join(f"- {_clock(u['ts'])} ({u['source']}): {u['text']}" for u in lines) or "(none)"
        state = f'running, goal: "{self.goal}"' if self.active else "off"
        body = f"BURST: {state}\n\nRECENT TRANSCRIPT:\n{said}\n\nNEW SENTENCE: {text}"
        return json.loads(self.recall.brain.json(WATCH_INSTRUCTIONS, body, WATCH_SCHEMA))

    # --- the burst ---------------------------------------------------------------------

    async def start(self, goal, say=""):
        self._epoch += 1
        changed = self.active
        self.goal, self.started, self.said = goal[:200], time.time(), []
        self.recall.ctx["eyes"] = self.goal
        await self.recall.push_ctx()
        await self.recall.agent("Burst", "on", self.goal)
        if not changed:
            await self.recall.glasses.burst(True)
            asyncio.create_task(self._expire(self._epoch))
        await self._log("burst", ("new goal: " if changed else "start: ") + self.goal)
        if say:
            await self.recall._say(say)

    async def stop(self, why, say=""):
        if not self.active:
            return
        self._epoch += 1
        goal, self.goal = self.goal, None
        self.recall.ctx["eyes"] = None
        await self.recall.push_ctx()
        await self.recall.agent("Burst", "off", why)
        if self.recall.glasses is not None:
            await self.recall.glasses.burst(False)
        await self._log("burst", f"stop ({why}) after {int(time.time() - self.started)} s, goal was: {goal}")
        if say:
            await self.recall._say(say)

    async def _expire(self, epoch):
        await asyncio.sleep(MAX_BURST)
        if epoch == self._epoch and self.active:
            await self.stop("timeout", say="Stopping the camera.")

    # --- Guide: burst photo -> one spoken direction ------------------------------------

    async def on_image(self, jpeg):
        """A burst photo. Dropped while the Guide is busy or too soon after the last one."""
        if not self.active or self._guiding or time.time() - self._last_guide < GUIDE_GAP:
            return
        self._guiding, self._last_guide = True, time.time()
        epoch, taken = self._epoch, time.time()
        import base64

        image_id = await self.recall.image(base64.b64encode(jpeg).decode(), "burst", "Guide is looking...")
        await self.recall.agent("Guide", "looking", self.goal)
        try:
            out = await asyncio.to_thread(self._guide, jpeg)
        except Exception as e:
            print("Eyes: Guide failed:", type(e).__name__, str(e)[:200])
            await self.recall.agent("Guide", "failed", type(e).__name__)
            return
        finally:
            self._guiding = False
        if epoch != self._epoch or time.time() - taken > STALE_PHOTO:
            await self.recall.caption(image_id, "Burst already ended." if epoch != self._epoch else "Too late, dropped.")
            return
        say = (out.get("say") or "").strip()
        await self.recall.caption(image_id, f"{out.get('seen', '')} -> {say or '(quiet)'}")
        await self.recall.agent("Guide", "said" if say else "quiet", say or out.get("seen", ""))
        await self._log("guide", f"{out.get('seen', '')} -> {say or '(quiet)'}")
        if say and not any(t == say and time.time() - ts < REPEAT_GAP for ts, t in self.said):
            self.said = (self.said + [(time.time(), say)])[-5:]
            await self.recall._say(say)
        if out.get("done"):
            await self.stop("goal reached")

    def _guide(self, jpeg):
        lines = self.recall.store.utterances(limit=4)
        heard = "\n".join(f"- {u['text']}" for u in lines) or "(none)"
        told = "\n".join(f"- {t}" for _, t in self.said[-3:]) or "(nothing yet)"
        body = f"GOAL: {self.goal}\n\nTHEY SAID RECENTLY:\n{heard}\n\nYOU TOLD THEM LAST:\n{told}"
        return json.loads(self.recall.brain.json(GUIDE_INSTRUCTIONS, body, GUIDE_SCHEMA, jpeg=jpeg, thinking="low"))
