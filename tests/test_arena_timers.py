"""Regression: a turn timeout must not cancel its own task.

`_finish_match()` calls `_cancel_timer()` from inside the timer task. If that
cancelled the current task, the finish would abort and timeouts would silently
stop working.
"""

import asyncio
import unittest

from features.arena import handlers


class TimerCancelTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_does_not_cancel_current_task(self):
        handlers._timers.clear()
        done = {"ok": False}

        async def job():
            handlers._timers["m"] = asyncio.current_task()
            handlers._cancel_timer("m")  # must NOT cancel ourselves
            await asyncio.sleep(0)
            done["ok"] = True

        await asyncio.create_task(job())
        self.assertTrue(done["ok"])
        self.assertNotIn("m", handlers._timers)


if __name__ == "__main__":
    unittest.main()
