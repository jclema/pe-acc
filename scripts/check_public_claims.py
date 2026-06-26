#!/usr/bin/env python3
"""Validate PE-ACC public docs/claims consistency and onboarding parity."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+):")
MAKE_COMMAND_LINE_RE = re.compile(r"^\s*make\s+([A-Za-z0-9_.-]+)\b")
MAKE_COMMAND_INLINE_RE = re.compile(r"`make\s+([A-Za-z0-9_.-]+)\b")

REQUIRED_README_MARKERS = [
    "PE-ACC",
    "Quick Start",
    "docs/source_registry_pe_v1.csv",
    "API MVP",
    "Seguridad y alcance",
]


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def parse_make_targets(makefile_path: Path) -> set[str]:
    targets: set[str] = set()
    for raw in makefile_path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#") or raw.startswith("\t"):
            continue
        match = MAKE_TARGET_RE.match(raw)
        if match:
            target = match.group(1)
            if target != ".PHONY":
                targets.add(target)
    return targets


def parse_make_commands(text: str) -> set[str]:
    commands: set[str] = set()
    for raw in text.splitlines():
        line_match = MAKE_COMMAND_LINE_RE.search(raw)
        if line_match:
            commands.add(line_match.group(1))
        for inline_match in MAKE_COMMAND_INLINE_RE.finditer(raw):
            commands.add(inline_match.group(1))
    return commands


def compute_registry_counts(registry_path: Path) -> dict[str, int]:
    rows = list(csv.DictReader(registry_path.open(encoding="utf-8", newline="")))
    universe = [row for row in rows if parse_bool(row.get("in_universe_v1", ""))]
    status_counts = Counter((row.get("status") or "").strip() for row in universe)
    load_counts = Counter((row.get("load_state") or "").strip() for row in universe)
    implemented = [row for row in universe if (row.get("implementation_state") or "").strip() == "implemented"]

    return {
        "universe": len(universe),
        "implemented": len(implemented),
        "loaded": load_counts.get("loaded", 0),
        "partial_load": load_counts.get("partial", 0),
        "not_loaded": load_counts.get("not_loaded", 0),
        "status_loaded": status_counts.get("loaded", 0),
        "status_partial": status_counts.get("partial", 0),
        "status_stale": status_counts.get("stale", 0),
        "status_blocked_external": status_counts.get("blocked_external", 0),
        "status_not_built": status_counts.get("not_built", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PE-ACC public claims and docs consistency")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--registry-path", default="docs/source_registry_pe_v1.csv")
    parser.add_argument("--readme", default="README.md")
    parser.add_argument("--reference-metrics", default="docs/reference_metrics.md")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    makefile_path = root / "Makefile"
    registry_path = root / args.registry_path
    readme_path = root / args.readme
    reference_metrics_path = root / args.reference_metrics

    errors: list[str] = []

    if not makefile_path.exists():
        errors.append("Makefile is missing")
    else:
        targets = parse_make_targets(makefile_path)
        en_commands = parse_make_commands(readme_path.read_text(encoding="utf-8"))
        missing = sorted(en_commands - targets)
        if missing:
            errors.append(f"README references undefined Makefile targets: {missing}")

    readme_text = readme_path.read_text(encoding="utf-8")

    for marker in REQUIRED_README_MARKERS:
        if marker.lower() not in readme_text.lower():
            errors.append(f"README.md missing required marker: {marker}")

    registry_counts = compute_registry_counts(registry_path)
    if registry_counts["universe"] < 1:
        errors.append(f"{args.registry_path} must include at least one in-universe source")
    if registry_counts["implemented"] < 1:
        errors.append(f"{args.registry_path} must include at least one implemented pipeline")
    if "brunoclz/br-acc" in readme_text:
        errors.append("README.md still references upstream brunoclz/br-acc as project identity")

    metrics_text = reference_metrics_path.read_text(encoding="utf-8") if reference_metrics_path.exists() else ""
    if metrics_text and "as_of_utc" not in metrics_text.lower() and "as-of (utc)" not in metrics_text.lower():
        errors.append("docs/reference_metrics.md must include explicit timestamp metadata")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
