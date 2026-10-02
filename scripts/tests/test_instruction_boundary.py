"""Validate the instruction boundary against real temporary Git indexes."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_instruction_boundary.py"


class InstructionBoundaryTest(unittest.TestCase):
    def run_gate(self, tracked, untracked=(), symlink=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in [*tracked, *untracked]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("public test fixture\n")
            if symlink:
                (root / "AGENTS.md").unlink()
                (root / "AGENTS.md").symlink_to("README.md")
            if tracked:
                subprocess.run(["git", "-C", str(root), "add", "--", *tracked], check=True)
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--repo-root", str(root)],
                capture_output=True, text=True, check=False)

    def test_root_public_map_and_regular_docs_pass(self):
        result = self.run_gate(["AGENTS.md", "README.md", "docs/agent/index.md"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_internal_names_are_still_rejected(self):
        for name in ["CLAUDE.md", "docs/CLAUDE.md", "AGENTS.private.md",
                     "nested/AGENTS.md", "nested/AGENTS-local.md", "a b/AGENTS.md"]:
            with self.subTest(name=name):
                result = self.run_gate(["AGENTS.md", name])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stdout)

    def test_untracked_internal_files_are_not_published(self):
        result = self.run_gate(["AGENTS.md"], untracked=["CLAUDE.md"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_root_map_cannot_be_a_symlink(self):
        result = self.run_gate(["AGENTS.md", "README.md"], symlink=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AGENTS.md", result.stdout)

    def test_non_repository_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo-root", directory],
                capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
