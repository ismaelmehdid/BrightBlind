import asyncio
import sqlite3
import unittest

from memory import Memory


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.memory = Memory(self.db, self, lambda *args, **kwargs: None)

    async def test_reset_invalidates_in_flight_distillation(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def gemini(*args):
            started.set()
            await release.wait()
            return {'memories': [
                {'line_id': 1, 'text': 'Old memory', 'kind': 'fact', 'people': [], 'importance': 2}
            ]}

        self.gemini = gemini
        self.memory.keep('Old words', 'band', {})
        task = asyncio.create_task(self.memory.distill())
        await started.wait()
        self.memory.clear()
        self.memory.keep('New words', 'band', {})
        release.set()
        await task
        self.assertEqual(self.memory.snapshot(), {'lines': 1, 'memories': []})
        self.assertEqual(self.db.execute('SELECT distilled FROM lines').fetchone(), (0,))

    async def test_invalid_model_batch_does_not_persist_partial_memories(self):
        async def gemini(*args):
            valid = {'line_id': 1, 'text': 'Valid', 'kind': 'fact', 'people': [], 'importance': 2, 'context': ''}
            return {'memories': [valid, dict(valid, line_id=999)]}

        self.gemini = gemini
        self.memory.keep('Something worth keeping', 'band', {})
        await self.memory.distill()
        self.memory.keep('A later line', 'band', {})
        self.assertEqual(self.memory.snapshot(), {'lines': 2, 'memories': []})
        self.assertEqual(self.db.execute('SELECT SUM(distilled) FROM lines').fetchone(), (0,))
