"""Recall inside the backend: the wearer's long-term memory, built from what the band hears.

Ismael's memory layer (recall/ at the repo root) moved here so one server is the brain the glasses
app points at. It keeps:
  lines     every final band transcript (also ambient talk the planner ignores) and every vision
            observation, each with the band's activity at that moment (still / walk / run, steps)
  memories  short facts Gemini distills from the lines: task, plan, person, fact, idea, feeling, moment
A tap on the band bookmarks the last 30 seconds. scene=memory questions are answered here, in-process,
from all memories plus recent lines: a day of memory fits easily in Gemini 4's context, so no search.
"""
import asyncio
import json
import sqlite3
import time
from datetime import datetime

DISTILL_EVERY = 30        # seconds between distill passes (one Gemini call each, only when there are new lines)
DISTILL_QUIET = 6         # wait until nobody spoke for this long
BOOKMARK_SECONDS = 30     # a tap keeps the last 30 seconds
ANSWER_LINES = 150        # recent lines given with every question
KINDS = ['task', 'plan', 'person', 'fact', 'idea', 'feeling', 'moment']

SCHEMA = """
CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY, ts REAL, text TEXT, source TEXT, activity TEXT,
    steps INTEGER, bookmarked INTEGER DEFAULT 0, distilled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, text TEXT, people TEXT,
    importance INTEGER, context TEXT, bookmarked INTEGER DEFAULT 0);
"""

DISTILL_PROMPT = """You are the memory of a person who wears a wristband microphone and camera glasses. Below are
lines it heard or saw, each with the time and what the wearer's body was doing. Keep only what is worth
remembering later: tasks and promises, plans and dates, people and what they said or want, facts, what is
in their fridge or on their shelves, ideas, strong feelings. Skip filler and small talk. Lines marked
BOOKMARKED were kept on purpose by a tap: always make at least one memory from them, importance 4 or more.
Band lines start with a tag: "[close voice, probably the wearer]" or "[farther voice, probably someone else]"
(a loudness guess). Use it to tell the wearer's own words from what another person said or asked for; name the
person if a name was spoken, otherwise say "someone with the wearer". One short concrete sentence per memory, about "the wearer". Return an empty list when nothing is worth it.

LINES:
"""

ANSWER_PROMPT = """You are the memory of a person who wears a wristband and camera glasses and may not see well.
Answer their question only from the memories, lines and activity below. Say when it happened (time of day)
and, when it helps, what they were doing. If the memory does not hold the answer, say so in one sentence.
The answer is spoken aloud: one to three short sentences, no lists.
"""

DISTILL_SCHEMA = {'type': 'OBJECT', 'required': ['memories'], 'properties': {'memories': {'type': 'ARRAY', 'items': {
    'type': 'OBJECT', 'required': ['line_id', 'kind', 'text', 'people', 'importance', 'context'], 'properties': {
        'line_id': {'type': 'INTEGER'}, 'kind': {'type': 'STRING', 'enum': KINDS}, 'text': {'type': 'STRING'},
        'people': {'type': 'ARRAY', 'items': {'type': 'STRING'}}, 'importance': {'type': 'INTEGER'},
        'context': {'type': 'STRING'}}}}}}
ANSWER_SCHEMA = {'type': 'OBJECT', 'required': ['answer'], 'properties': {'answer': {'type': 'STRING'}}}


def _clock(ts):
    return datetime.fromtimestamp(ts).strftime('%H:%M')


class Memory:
    def __init__(self, db, providers, log):
        """db: the coordinator's own SQLite connection (backend.sqlite); the memory adds its tables to it."""
        self.db = db
        self.db.executescript(SCHEMA)
        self.providers = providers
        self.log = log                         # Coordinator.log: shows on the judges' dashboard
        self.last_line = 0.0
        self.busy = False
        self.generation = 0

    def _rows(self, sql, args=()):
        cursor = self.db.cursor()
        cursor.row_factory = sqlite3.Row       # on this cursor only: the coordinator's queries stay as they are
        return [dict(r) for r in cursor.execute(sql, args).fetchall()]

    # --- keeping -------------------------------------------------------------------------

    def keep(self, text, source, activity, bookmarked=False):
        text = str(text).strip()[:2000]
        if not text: return
        self.db.execute('INSERT INTO lines(ts, text, source, activity, steps, bookmarked) VALUES(?,?,?,?,?,?)',
                        (time.time(), text, source, (activity or {}).get('state'), (activity or {}).get('steps'),
                         int(bookmarked)))
        self.db.commit()
        self.last_line = time.time()

    def clear(self):
        """Forget everything: heard lines and distilled memories."""
        self.generation += 1
        self.last_line = 0.0
        lines = self.db.execute('DELETE FROM lines').rowcount
        memories = self.db.execute('DELETE FROM memories').rowcount
        self.db.commit()
        self.log('Memory', 'cleared', f'{lines} line(s) and {memories} memory(ies) deleted.')
        return {'lines': lines, 'memories': memories}

    def bookmark(self):
        count = self.db.execute('UPDATE lines SET bookmarked = 1, distilled = 0 WHERE ts >= ?',
                                (time.time() - BOOKMARK_SECONDS,)).rowcount
        self.db.commit()
        self.last_line = 0                     # distill on the next pass
        self.log('Memory', 'bookmark', f'Tap kept the last {BOOKMARK_SECONDS} s ({count} line(s)).')

    # --- distilling ----------------------------------------------------------------------

    async def distill(self):
        if self.busy or not hasattr(self.providers, 'gemini'): return
        rows = self._rows('SELECT * FROM lines WHERE distilled = 0 ORDER BY ts LIMIT 60')
        if not rows: return
        self.busy = True
        generation = self.generation
        try:
            text = DISTILL_PROMPT + '\n'.join(
                f"[line {r['id']}] {_clock(r['ts'])} ({r['activity'] or 'no band data'}, {r['source']})"
                f"{' BOOKMARKED' if r['bookmarked'] else ''}: {json.dumps(r['text'])}" for r in rows)
            result = await self.providers.gemini(text, DISTILL_SCHEMA)
            if generation != self.generation:
                return
            by_id = {r['id']: r for r in rows}
            entries = result.get('memories')
            if not isinstance(entries, list):
                raise ValueError('Expected a list of memories')
            made = []
            with self.db:
                for entry in entries[:20]:
                    source_id = entry.get('line_id') if isinstance(entry, dict) else None
                    if type(source_id) is not int or source_id not in by_id:
                        raise ValueError('Memory must reference a supplied line')
                    src = by_id[source_id]
                    kind = entry.get('kind')
                    text = entry.get('text')
                    people = entry.get('people')
                    importance = entry.get('importance')
                    context = entry.get('context')
                    if (kind not in KINDS or not isinstance(text, str) or not text.strip()
                            or not isinstance(people, list) or not all(isinstance(person, str) for person in people)
                            or type(importance) is not int or not isinstance(context, str)):
                        raise ValueError('Invalid memory result')
                    self.db.execute(
                        'INSERT INTO memories(ts, kind, text, people, importance, context, bookmarked) VALUES(?,?,?,?,?,?,?)',
                        (src['ts'], kind, text[:400], json.dumps([person[:100] for person in people[:8]]),
                         max(1, min(5, importance)), context[:200], src['bookmarked']),
                    )
                    made.append(f"{kind}: {text[:160]}")
                self.db.executemany('UPDATE lines SET distilled = 1 WHERE id = ?', [(r['id'],) for r in rows])
            self.log('Memory · Gemini', 'distilled', f'{len(rows)} line(s) read, {len(made)} memory(ies) kept.',
                     memories=made[:5])
        except Exception as error:
            self.log('Memory · Gemini', 'failed', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
        finally:
            self.busy = False

    async def loop(self):
        while True:
            await asyncio.sleep(DISTILL_EVERY)
            if time.time() - self.last_line >= DISTILL_QUIET:
                await self.distill()

    # --- answering -----------------------------------------------------------------------

    def context(self, lines=30):
        """Memories and recent lines as text, for a prompt that needs them next to an image."""
        memories = self._rows('SELECT * FROM memories ORDER BY ts')
        recent = list(reversed(self._rows('SELECT * FROM lines ORDER BY ts DESC LIMIT ?', (lines,))))
        mem = '\n'.join(f"- [{m['kind']}] {m['text']}" for m in memories) or '(none)'
        said = '\n'.join(f"- {r['text']}" for r in recent if r['source'] == 'band') or '(none)'
        return f'MEMORIES:\n{mem}\n\nRECENT LINES HEARD:\n{said}'

    async def answer(self, question):
        memories = self._rows('SELECT * FROM memories ORDER BY ts')
        lines = list(reversed(self._rows('SELECT * FROM lines ORDER BY ts DESC LIMIT ?', (ANSWER_LINES,))))
        if not memories and not lines:
            return 'I have no memories yet. Talk near the band, or tap it to keep a moment.'
        mem = '\n'.join(f"- {_clock(m['ts'])} [{m['kind']}{', bookmarked' if m['bookmarked'] else ''}] "
                        f"{json.dumps(m['text'])} (doing: {m['context']})" for m in memories) or '(none yet)'
        said = '\n'.join(f"- {_clock(r['ts'])} ({r['activity'] or 'no band data'}, {r['source']}): {json.dumps(r['text'])}"
                         for r in lines) or '(none)'
        prompt = (ANSWER_PROMPT + f"\nNow: {datetime.now().strftime('%A %H:%M')}\n\nMEMORIES:\n{mem}\n\nRECENT LINES:\n{said}"
                  f"\n\nQUESTION: {json.dumps(question)}")
        generation = self.generation
        result = await self.providers.gemini(prompt, ANSWER_SCHEMA)
        if generation != self.generation:
            return "Memory was cleared while I was checking."
        return str(result.get('answer') or 'My memory has no answer for that.')[:700]

    def snapshot(self, limit=12):
        return {'lines': self.db.execute('SELECT COUNT(*) FROM lines').fetchone()[0],
                'memories': [{k: m[k] for k in ('ts', 'kind', 'text', 'importance', 'context', 'bookmarked')}
                             for m in self._rows('SELECT * FROM memories ORDER BY ts DESC LIMIT ?', (limit,))]}

    def close(self):
        pass                                   # the coordinator closes the shared connection
