"""Exercise the contract CLI with independent registry and runner fixtures."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_pipeline_contracts.py"
ROOT = SCRIPT.parent.parent
FIELDS = ["source_id", "pipeline_id", "in_universe_v1", "implementation_state"]


class PipelineContractsTest(unittest.TestCase):
    def run_gate(self, rows=None, runner=None, legacy=None):
        if rows is None:
            rows = ["sunat,pe_sunat,true,implemented", "seace,pe_seace,true,scaffolded",
                    "mef,pe_mef,true,not_implemented"]
        if runner is None:
            runner = ["pe_sunat", "pe_seace", "cnpj"]
        if legacy is None:
            legacy = ["cnpj"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (root / "registry.csv").open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(FIELDS)
                writer.writerows(row.split(",") for row in rows)
            (root / "runner.py").write_text(
                "PIPELINES: dict[str, type] = {\n" +
                "".join(f'    "{name}": Pipeline,\n' for name in runner) + "}\n")
            (root / "legacy.json").write_text(json.dumps(legacy))
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--registry-path", str(root / "registry.csv"),
                 "--runner-path", str(root / "runner.py"),
                 "--legacy-catalog-path", str(root / "legacy.json")],
                capture_output=True, text=True, check=False)

    def test_implemented_and_scaffolded_are_runnable(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("implemented=1 scaffolded=1 legacy=1 runner=3", result.stdout)

    def test_missing_implemented_pipeline_fails(self):
        result = self.run_gate(runner=["pe_seace", "cnpj"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['pe_sunat']", result.stdout)

    def test_unregistered_peru_pipeline_fails(self):
        result = self.run_gate(runner=["pe_sunat", "pe_seace", "pe_unknown", "cnpj"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected=['pe_unknown']", result.stdout)

    def test_not_implemented_pipeline_cannot_be_runnable(self):
        result = self.run_gate(runner=["pe_sunat", "pe_seace", "pe_mef", "cnpj"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected=['pe_mef']", result.stdout)

    def test_legacy_changes_require_catalog_update(self):
        for runner, message in [(["pe_sunat", "pe_seace"], "missing=['cnpj']"),
                                (["pe_sunat", "pe_seace", "cnpj", "unknown"],
                                 "unexpected=['unknown']")]:
            with self.subTest(runner=runner):
                result = self.run_gate(runner=runner)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)

    def test_invalid_registry_rows_fail(self):
        for rows in [["a,pe_a,true,unknown"], ["a,,true,implemented"],
                     ["a,pe_a,maybe,implemented"], ["a,cnpj,true,implemented"],
                     ["a,pe_a,true,implemented", "b,pe_a,true,implemented"],
                     ["a,pe_a,true,implemented", "a,pe_b,true,implemented"]]:
            with self.subTest(rows=rows):
                result = self.run_gate(rows=rows)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid registry", result.stdout)

    def test_duplicate_runner_key_fails(self):
        result = self.run_gate(runner=["pe_sunat", "pe_sunat", "pe_seace", "cnpj"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate runner", result.stdout)

    def test_legacy_catalog_cannot_mask_peru_or_duplicates(self):
        for legacy in [["cnpj", "pe_sunat"], ["cnpj", "cnpj"]]:
            with self.subTest(legacy=legacy):
                result = self.run_gate(legacy=legacy)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid legacy catalog", result.stdout)

    def test_default_gate_matches_repository(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("implemented=3 scaffolded=1 legacy=47 runner=51", result.stdout)


if __name__ == "__main__":
    unittest.main()
