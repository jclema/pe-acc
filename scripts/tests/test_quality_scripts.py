"""Check quality orchestration through controlled command executables."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "ci"


class QualityScriptsTest(unittest.TestCase):
    def run_suite(self, suite, fail=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for command in ["uv", "npm", "npx"]:
                stub = root / command
                stub.write_text(
                    '#!/bin/sh\n'
                    'printf "%s\\n" "$(basename "$0") $*" >> "$QUALITY_TEST_LOG"\n'
                    '[ "$*" != "$QUALITY_TEST_FAIL" ]\n')
                stub.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       QUALITY_TEST_LOG=str(root / "commands.log"), QUALITY_TEST_FAIL=fail)
            result = subprocess.run(["bash", str(SCRIPTS / f"{suite}_quality.sh")],
                                    cwd=root, env=env, capture_output=True, check=False)
            return result.returncode, (root / "commands.log").read_text().splitlines()

    def test_python_uses_frozen_environment_for_all_gates(self):
        code, calls = self.run_suite("python")
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["uv sync --frozen --extra dev",
                                "uv run --frozen ruff check src/ tests/",
                                "uv run --frozen mypy src/", "uv run --frozen pytest -q"])

    def test_python_install_failure_does_not_use_stale_environment(self):
        code, calls = self.run_suite("python", "sync --frozen --extra dev")
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, ["uv sync --frozen --extra dev"])

    def test_frontend_includes_build_without_fetching_missing_tools(self):
        code, calls = self.run_suite("frontend")
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["npm ci", "npx --no-install eslint src/",
                                "npx --no-install tsc --noEmit", "npm test -- --run",
                                "npm run build"])

    def test_frontend_install_failure_stops_gates(self):
        code, calls = self.run_suite("frontend", "ci")
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, ["npm ci"])

    def test_gate_failure_is_reported_and_remaining_diagnostics_run(self):
        for suite, fail, final in [
            ("python", "run --frozen ruff check src/ tests/", "uv run --frozen pytest -q"),
            ("frontend", "--no-install eslint src/", "npm run build"),
            ("frontend", "run build", "npm run build"),
        ]:
            with self.subTest(suite=suite, fail=fail):
                code, calls = self.run_suite(suite, fail)
                self.assertNotEqual(code, 0)
                self.assertEqual(calls[-1], final)


if __name__ == "__main__":
    unittest.main()
