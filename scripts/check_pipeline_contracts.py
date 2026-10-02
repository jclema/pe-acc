#!/usr/bin/env python3
"""Validate Peru runnable states and the explicit retained legacy catalog."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from pathlib import Path

ID_RE = re.compile(r"[a-z][a-z0-9_]*")
STATES = {"implemented", "scaffolded", "not_implemented"}


def parse_registry(path: Path) -> dict[str, str]:
    states: dict[str, str] = {}
    sources: set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"source_id", "pipeline_id", "in_universe_v1", "implementation_state"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("invalid registry: missing required columns")
        for row in reader:
            source = (row.get("source_id") or "").strip()
            pipeline = (row.get("pipeline_id") or "").strip()
            state = (row.get("implementation_state") or "").strip()
            universe = (row.get("in_universe_v1") or "").strip().lower()
            if (not source or source in sources or not ID_RE.fullmatch(pipeline)
                    or not pipeline.startswith("pe_") or pipeline in states
                    or state not in STATES or universe not in {"true", "false"}):
                raise ValueError(f"invalid registry: source={source!r} pipeline={pipeline!r}")
            sources.add(source)
            states[pipeline] = state if universe == "true" else "not_implemented"
    if not states:
        raise ValueError("invalid registry: empty registry")
    return states


def parse_runner_pipelines(path: Path) -> set[str]:
    definitions = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(target, ast.Name) and target.id == "PIPELINES" for target in targets):
            definitions.append(node.value)
    if len(definitions) != 1 or not isinstance(definitions[0], ast.Dict):
        raise ValueError("invalid runner: expected one literal PIPELINES dictionary")
    pipelines: set[str] = set()
    for key in definitions[0].keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise ValueError("invalid runner: expected literal pipeline IDs")
        if not ID_RE.fullmatch(key.value):
            raise ValueError(f"invalid runner ID: {key.value!r}")
        if key.value in pipelines:
            raise ValueError(f"duplicate runner key: {key.value}")
        pipelines.add(key.value)
    if not pipelines:
        raise ValueError("invalid runner: empty PIPELINES dictionary")
    return pipelines


def parse_legacy(path: Path) -> set[str]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(entries, list)
            or any(not isinstance(item, str) or not ID_RE.fullmatch(item)
                   or item.startswith("pe_") for item in entries)
            or len(entries) != len(set(entries))):
        raise ValueError("invalid legacy catalog: unique non-Peru IDs required")
    return set(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-path", default="docs/source_registry_pe_v1.csv")
    parser.add_argument("--runner-path", default="etl/src/bracc_etl/runner.py")
    parser.add_argument("--legacy-catalog-path", default="config/legacy_pipeline_catalog.json")
    args = parser.parse_args()
    try:
        states = parse_registry(Path(args.registry_path))
        runner = parse_runner_pipelines(Path(args.runner_path))
        legacy = parse_legacy(Path(args.legacy_catalog_path))
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"FAIL\n- {exc}")
        return 1
    implemented = {key for key, value in states.items() if value == "implemented"}
    scaffolded = {key for key, value in states.items() if value == "scaffolded"}
    expected = implemented | scaffolded | legacy
    print(f"implemented={len(implemented)} scaffolded={len(scaffolded)} "
          f"legacy={len(legacy)} runner={len(runner)}")
    missing, unexpected = sorted(expected - runner), sorted(runner - expected)
    if missing or unexpected:
        print(f"FAIL\n- missing={missing}\n- unexpected={unexpected}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
