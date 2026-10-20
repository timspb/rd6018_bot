"""Offline source-to-release barriers for D123 Sprint 60 / P5."""
import ast
from pathlib import Path
import tempfile
import unittest

from tools.node104_atomic_deploy import source_manifest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class Sprint60SourceReleaseTests(unittest.TestCase):
    def test_existing_release_artifact_is_exact_tracked_git_archive(self):
        deploy = read("tools/node104_atomic_deploy.py")
        manifest = deploy.split("def source_manifest(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn('"archive", "--format=tar", actual', manifest)
        self.assertIn('"files": files', manifest)
        self.assertIn('"archive_sha256": archive_sha', manifest)
        # git archive is the inclusion boundary: untracked fixtures and local
        # test-authority files cannot enter the install artifact.
        self.assertNotIn("rglob(", manifest)
        self.assertIn("requirements.txt", [p.name for p in ROOT.glob("requirements*.txt")])

    def test_untracked_authority_fixture_is_excluded_by_existing_archiver(self):
        with tempfile.TemporaryDirectory(prefix="d123-untracked-", dir=ROOT) as name:
            fixture = ROOT / name / "tests" / "untracked_authority.py"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("DENY_ALL = True\n", encoding="utf-8")
            manifest = source_manifest(ROOT, "HEAD")
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertNotIn(fixture.relative_to(ROOT).as_posix(), paths)

    def test_one_controller_and_one_canonical_session_writer(self):
        runtime = ast.parse(read("runtime/production_runtime.py"))
        factories = [n for n in ast.walk(runtime) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name)
                     and n.func.id in {"ManagedChargeController", "create_production_charge_host"}]
        self.assertEqual(len(factories), 1)
        self.assertEqual(factories[0].func.id, "create_production_charge_host")
        atomic = ast.parse(read("runtime/charge/session_atomic.py"))
        writers = [n for n in ast.walk(atomic) if isinstance(n, ast.FunctionDef)
                   and n.name == "atomic_session_write"]
        self.assertEqual(len(writers), 1)
        self.assertEqual(read("runtime/charge/persistence.py").count("def restore_session("), 1)

    def test_guarded_restore_stays_off_and_production_resume_endpoint_uninstalled(self):
        port = read("application/execution_port.py")
        self.assertIn("self._guarded_resume_endpoint = None", port)
        self.assertIn("if endpoint is None", port)
        self.assertNotIn("_guarded_resume_endpoint =", read("runtime/production_runtime.py"))
        recovery = read("runtime/startup_recovery.py")
        activation = recovery.split("async def replay_deferred_startup_restore", 1)[1].split(
            "async def guarded_physical_resume", 1)[0]
        self.assertIn("mark_guarded_restore_activated_off", activation)
        self.assertIn("guarded_restore_activated_off", activation)
        self.assertNotIn("execute_guarded_physical_resume", activation)

    def test_existing_ci_matrix_is_three_supported_python_versions(self):
        workflow = read(".github/workflows/ci.yml")
        self.assertIn("python-version: ['3.10', '3.11', '3.12']", workflow)
        requirements = read("requirements.txt")
        self.assertIn('python_version < "3.11"', requirements)
        self.assertIn('python_version >= "3.11"', requirements)


if __name__ == "__main__":
    unittest.main()
