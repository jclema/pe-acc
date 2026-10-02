#!/usr/bin/env python3
"""Allow the public root map while rejecting tracked internal instruction files."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

INTERNAL_NAME = re.compile(r"(^|/)(CLAUDE\.md|AGENTS.*\.md)$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(args.repo_root).resolve()),
             "ls-files", "--stage", "-z"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"FAIL\n- Cannot inspect tracked files: {exc}")
        return 1
    forbidden = set()
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, _, stage = metadata.split()
        if not INTERNAL_NAME.search(path):
            continue
        if path == "AGENTS.md" and mode == "100644" and stage == "0":
            continue
        forbidden.add(path)
    if forbidden:
        print("FAIL\n- Forbidden tracked instruction files: " + ", ".join(sorted(forbidden)))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
