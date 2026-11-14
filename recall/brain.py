"""Gemini 4: turns raw speech + band context into memories, and answers questions from them.

No vector search: a day of memories fits easily in Gemini 4's 1M-token context, so every
question gets the whole memory, the recent transcript and the band's activity log.
"""
import json
import os
import time
from datetime import datetime

MODEL = os.getenv("GEMINI_MODEL", "gemini-4-hydrogen")  # free tier; one place to change it

KINDS = ["task", "plan", "person", "fact", "idea", "feeling", "moment"]

MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "utterance_id": {"type": "integer", "description": "id of the line it comes from"},
                    "kind": {"type": "string", "enum": KINDS},
                    "text": {"type": "string", "description": "one short sentence, third person, about the wearer"},
                    "people": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "integer", "description": "1 small talk .. 5 must not forget"},
                    "context": {"type": "string", "description": "what the wearer was doing, from the band data"},
                },
                "required": ["utterance_id", "kind", "text", "people", "importance", "context"],
            },
        }
    },
    "required": ["memories"],
}

DISTILL_INSTRUCTIONS = """You are the memory of a person wearing a wristband with a microphone and a motion sensor.
You get lines of speech the band heard, each with the time and what the wearer's body was doing
(still, walking, running, steps). Pull out only what is worth remembering later: tasks and promises,
plans and dates, people and what they said or want, facts, ideas, strong feelings.
Skip filler, greetings and small talk. Lines marked BOOKMARKED were kept on purpose by a tap on the band:
always make at least one memory from them, with importance 4 or more.
Write each memory as one short, concrete sentence ("Sam asked the wearer to send the deck by Friday").
Return an empty list when nothing is worth keeping."""

ANSWER_INSTRUCTIONS = """You are the memory of a person wearing a wristband. Answer their question from the memories,
transcript and band activity below, and nothing else. Mention when it happened (time of day) and,
when it helps, what they were doing (walking, sitting still). If the memory does not hold the answer,
say so in one sentence. The answer is spoken aloud: one to three short sentences, no lists, no markdown."""


PHOTO_INSTRUCTIONS = """You are the eyes of a person who wears camera glasses and may not see well. Describe this photo
for their memory in two or three plain sentences: where they are, the main things in front of them, and every
item, label, price, sign or number you can read (for a fridge or a shelf, list the items). No guesses about people's
identity, no markdown."""


def _clock(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _context_words(u):
    bits = []
    if u.get("activity"):
        bits.append(u["activity"])
    if u.get("steps") is not None:
        bits.append(f"{u['steps']} steps since start")
    return ", ".join(bits) or "no band data"


class Brain:
    def __init__(self):
        from google import genai  # imported here so the app still starts without the package

        self.client = genai.Client()  # reads GEMINI_API_KEY from the environment / .env
        self.ready = True

    def _generate(self, instructions, text, schema=None, thinking="low"):
        """One Gemini call. Interactions API first (the current one), generate_content as fallback."""
        if hasattr(self.client, "interactions"):
            args = dict(model=MODEL, system_instruction=instructions, input=text,
                        generation_config={"thinking_level": thinking})
            if schema:
                args["response_format"] = {"type": "text", "mime_type": "application/json", "schema": schema}
            return self.client.interactions.create(**args).output_text
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=instructions)
        if schema:
            config.response_mime_type = "application/json"
            config.response_json_schema = schema
        return self.client.models.generate_content(model=MODEL, contents=text, config=config).text

    def describe_photo(self, jpeg):
        """A JPEG from the glasses -> a short description to keep as a memory."""
        import base64

        if hasattr(self.client, "interactions"):
            parts = [{"type": "text", "text": "Describe this photo."},
                     {"type": "image", "data": base64.b64encode(jpeg).decode(), "mime_type": "image/jpeg"}]
            return self.client.interactions.create(
                model=MODEL, system_instruction=PHOTO_INSTRUCTIONS, input=parts,
                generation_config={"thinking_level": "low"}).output_text.strip()
        from google.genai import types

        return self.client.models.generate_content(
            model=MODEL, contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), "Describe this photo."],
            config=types.GenerateContentConfig(system_instruction=PHOTO_INSTRUCTIONS)).text.strip()

    def distill(self, utterances):
        """Utterance rows -> list of memory dicts (with ts and bookmarked filled in)."""
        lines = []
        for u in utterances:
            mark = " BOOKMARKED" if u["bookmarked"] else ""
            lines.append(f"[id {u['id']}] {_clock(u['ts'])} ({_context_words(u)}){mark}: {u['text']}")
        raw = self._generate(DISTILL_INSTRUCTIONS, "\n".join(lines), schema=MEMORY_SCHEMA)
        by_id = {u["id"]: u for u in utterances}
        out = []
        for m in json.loads(raw).get("memories", []):
            src = by_id.get(m.get("utterance_id")) or utterances[-1]
            m["ts"] = src["ts"]
            m["bookmarked"] = bool(src["bookmarked"])
            if m.get("kind") not in KINDS:
                m["kind"] = "fact"
            out.append(m)
        return out

    def answer(self, question, memories, utterances, events):
        now = datetime.now().strftime("%A %H:%M")
        mem = "\n".join(
            f"- {_clock(m['ts'])} [{m['kind']}, importance {m['importance']}"
            f"{', bookmarked' if m['bookmarked'] else ''}] {m['text']} (doing: {m['context']})"
            for m in sorted(memories, key=lambda m: m["ts"])
        ) or "(none yet)"
        said = "\n".join(f"- {_clock(u['ts'])} ({_context_words(u)}): {u['text']}" for u in utterances) or "(none)"
        body = "\n".join(f"- {_clock(e['ts'])} {e['kind']} {e['detail'] or ''}" for e in events) or "(none)"
        text = (f"Now: {now}\n\nMEMORIES:\n{mem}\n\nRECENT TRANSCRIPT:\n{said}\n\n"
                f"BAND ACTIVITY LOG:\n{body}\n\nQUESTION: {question}")
        return self._generate(ANSWER_INSTRUCTIONS, text, thinking="low").strip()


def make_brain():
    """A Brain, or None with the reason, so the app runs (store only) without a Gemini key."""
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        return None, "no GEMINI_API_KEY: memories are stored but not distilled, questions are not answered"
    try:
        return Brain(), None
    except Exception as e:  # never print the key, only the kind of problem
        return None, f"Gemini not available ({type(e).__name__})"


if __name__ == "__main__":  # quick check: python -m recall.brain
    from dotenv import load_dotenv

    load_dotenv()
    b, why = make_brain()
    if not b:
        raise SystemExit(why)
    fake = [{"id": 1, "ts": time.time(), "text": "Remind me to call Sam about the demo at five.",
             "activity": "walk", "steps": 40, "bookmarked": 1}]
    print(b.distill(fake))
