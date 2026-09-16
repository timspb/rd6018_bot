import asyncio
import unittest

from runtime.background import start_background_tasks


class RuntimeBackgroundTests(unittest.TestCase):
    def test_callbacks_start_in_declared_order(self):
        seen = []

        async def first():
            seen.append("first")

        async def second():
            seen.append("second")

        async def run():
            tasks = start_background_tasks(first, second)
            await asyncio.gather(*tasks)
            return tasks

        tasks = asyncio.run(run())
        self.assertEqual(seen, ["first", "second"])
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(task.done() for task in tasks))

    def test_primitive_has_no_domain_dependencies(self):
        from pathlib import Path

        source = (Path(__file__).parents[1] / "runtime" / "background.py").read_text(encoding="utf-8")
        for forbidden in ("bot_legacy", "HassClient", "ChargeController", "SafeOutputCoordinator"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
