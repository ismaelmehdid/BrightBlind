"""SQLite memory store: what was said, what the body was doing, and the memories Gemini made of it.

Three layers:
  utterances  every finished turn of speech (or typed note), with the band's context at that moment
  events      band moments: taps, double-taps, activity changes (still / walk / run)
  memories    short facts Gemini distilled from the utterances (task, person, fact, plan, ...)
"""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS utterances (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,            -- 'band' (microphone) or 'typed'
    activity TEXT,                   -- still / walk / run, from the band
    steps INTEGER,                   -- steps since the app connected
    cadence REAL,
    bookmarked INTEGER DEFAULT 0,    -- the wearer tapped the band to keep this moment
    distilled INTEGER DEFAULT 0,     -- already turned into memories
    photo TEXT                       -- file name in photos/ when the line describes a glasses photo
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,              -- tap, double-tap, activity, connect, ...
    detail TEXT
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,                -- when it was said
    kind TEXT NOT NULL,              -- task, plan, person, fact, idea, feeling, moment
    text TEXT NOT NULL,
    people TEXT,                     -- JSON list of names
    importance INTEGER DEFAULT 2,    -- 1 low .. 5 high
    context TEXT,                    -- what the body was doing, in words
    bookmarked INTEGER DEFAULT 0,
    utterance_ids TEXT               -- JSON list
);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source TEXT NOT NULL             -- 'voice' or 'typed'
);
"""


class Store:
    def __init__(self, path):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()  # Gemini calls run on worker threads
        with self._lock:
            self._db.executescript(SCHEMA)
            cols = [r[1] for r in self._db.execute("PRAGMA table_info(utterances)")]
            if "photo" not in cols:            # databases made before photos existed
                self._db.execute("ALTER TABLE utterances ADD COLUMN photo TEXT")
            self._db.commit()

    def _run(self, sql, args=()):
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    def _rows(self, sql, args=()):
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    # --- writing ---------------------------------------------------------------------------

    def add_utterance(self, text, source, ctx, bookmarked=False, photo=None, ts=None):
        """ts: when it was said (a mirrored line keeps the laptop's time); now when left out."""
        try:
            ts = float(ts) if ts is not None else time.time()
        except (TypeError, ValueError):
            ts = time.time()
        cur = self._run(
            "INSERT INTO utterances (ts, text, source, activity, steps, cadence, bookmarked, photo)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (ts, text, source, ctx.get("activity"), ctx.get("steps"), ctx.get("cadence"),
             int(bookmarked), photo),
        )
        return self.utterance(cur.lastrowid)

    def add_event(self, kind, detail=None):
        cur = self._run("INSERT INTO events (ts, kind, detail) VALUES (?,?,?)", (time.time(), kind, detail))
        return {"id": cur.lastrowid, "ts": time.time(), "kind": kind, "detail": detail}

    def bookmark_recent(self, seconds=30):
        """Mark the last `seconds` of speech as kept on purpose. Returns how many were marked."""
        since = time.time() - seconds
        cur = self._run("UPDATE utterances SET bookmarked = 1, distilled = 0 WHERE ts >= ?", (since,))
        return cur.rowcount

    def add_memories(self, items, utterance_ids):
        out = []
        for m in items:
            cur = self._run(
                "INSERT INTO memories (ts, kind, text, people, importance, context, bookmarked, utterance_ids)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (m["ts"], m["kind"], m["text"], json.dumps(m.get("people", [])), int(m.get("importance", 2)),
                 m.get("context", ""), int(bool(m.get("bookmarked"))), json.dumps(utterance_ids)),
            )
            out.append(self.memory(cur.lastrowid))
        if utterance_ids:
            marks = ",".join("?" * len(utterance_ids))
            self._run(f"UPDATE utterances SET distilled = 1 WHERE id IN ({marks})", utterance_ids)
        return out

    def add_answer(self, question, answer, source):
        cur = self._run("INSERT INTO answers (ts, question, answer, source) VALUES (?,?,?,?)",
                        (time.time(), question, answer, source))
        return {"id": cur.lastrowid, "ts": time.time(), "question": question, "answer": answer, "source": source}

    def forget_memory(self, memory_id):
        self._run("DELETE FROM memories WHERE id = ?", (memory_id,))

    # --- reading ---------------------------------------------------------------------------

    def utterance(self, uid):
        rows = self._rows("SELECT * FROM utterances WHERE id = ?", (uid,))
        return rows[0] if rows else None

    def memory(self, mid):
        rows = self._rows("SELECT * FROM memories WHERE id = ?", (mid,))
        return _memory_out(rows[0]) if rows else None

    def undistilled(self, limit=60):
        return self._rows("SELECT * FROM utterances WHERE distilled = 0 ORDER BY ts LIMIT ?", (limit,))

    def utterances(self, limit=200):
        return list(reversed(self._rows("SELECT * FROM utterances ORDER BY ts DESC LIMIT ?", (limit,))))

    def memories(self, limit=500):
        return [_memory_out(r) for r in self._rows("SELECT * FROM memories ORDER BY ts DESC LIMIT ?", (limit,))]

    def events(self, limit=200):
        return list(reversed(self._rows("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))))

    def answers(self, limit=50):
        return self._rows("SELECT * FROM answers ORDER BY ts DESC LIMIT ?", (limit,))

    def counts(self):
        with self._lock:
            q = lambda t: self._db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
            return {t: q(t) for t in ("utterances", "events", "memories", "answers")}


def _memory_out(row):
    row["people"] = json.loads(row["people"] or "[]")
    row["utterance_ids"] = json.loads(row["utterance_ids"] or "[]")
    return row
