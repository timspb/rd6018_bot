import asyncio
import pathlib
import unittest

from runtime import LifecycleState, RuntimeApp, RuntimeDependencies


class RuntimeAppSkeletonTests(unittest.TestCase):
    def test_app_is_constructible_with_explicit_dependency_container(self):
        dependencies = RuntimeDependencies()
        app = RuntimeApp(dependencies)

        self.assertIs(app.dependencies, dependencies)
        self.assertIs(app.lifecycle.state, LifecycleState.CREATED)

    def test_start_and_stop_own_lifecycle(self):
        app = RuntimeApp()

        asyncio.run(app.start())
        self.assertIs(app.state, LifecycleState.RUNNING)
        asyncio.run(app.start())
        self.assertIs(app.state, LifecycleState.RUNNING)

        asyncio.run(app.stop())
        self.assertIs(app.state, LifecycleState.STOPPED)
        asyncio.run(app.stop())
        self.assertIs(app.state, LifecycleState.STOPPED)

    def test_runtime_package_does_not_import_bot_legacy(self):
        runtime_root = pathlib.Path(__file__).parents[1] / "runtime"
        for path in runtime_root.glob("*.py"):
            self.assertNotIn("bot_legacy", path.read_text(encoding="utf-8"))

    def test_skeleton_has_no_actuator_capability(self):
        app = RuntimeApp()

        self.assertIsNone(app.dependencies.hass)
        self.assertFalse(any(name in dir(app) for name in ("turn_on", "turn_off")))

    def test_dependency_container_has_infrastructure_slots_only(self):
        dependencies = RuntimeDependencies()

        for name in ("config", "storage", "persistence", "hass", "logger", "clock"):
            self.assertTrue(hasattr(dependencies, name))
        for forbidden in ("controller", "telegram", "output", "lease", "esp"):
            self.assertFalse(hasattr(dependencies, forbidden))

    def test_runtime_does_not_construct_actuator_dependencies(self):
        app = RuntimeApp()

        self.assertIsNone(app.dependencies.config)
        self.assertIsNone(app.dependencies.storage)
        self.assertIsNone(app.dependencies.persistence)
        self.assertIsNone(app.dependencies.hass)


if __name__ == "__main__":
    unittest.main()
