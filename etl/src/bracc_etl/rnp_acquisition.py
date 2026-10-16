"""Acquire an explicit current or historical RNP snapshot via official metadata."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from bracc_etl.pipelines.pe_osce_rnp import CONSOLIDATED, FILES, SOURCE_URL, read_rnp

BASE = "https://osce-gob-pe.atlassian.net/wiki"
LISTING = f"{BASE}/rest/api/content/106889267/child/attachment?limit=50&expand=version"
MAX_BYTES = 64 * 1024 * 1024
MAX_CURRENT_BYTES = 256 * 1024 * 1024
logger = logging.getLogger(__name__)


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Invalid RNP metadata object")
    return value


def _official_url(link: Any) -> str:
    if not isinstance(link, str) or not link:
        raise ValueError("Invalid RNP attachment link")
    url = link if link.startswith("https://") else f"{BASE}/{link.lstrip('/')}"
    if not url.startswith(f"{BASE}/") or "/../" in url:
        raise ValueError("RNP metadata link outside official API")
    return url


def valid_snapshot(path: Path) -> bool:
    """Accept only complete, parsed, unaltered snapshots, never loose-file fallbacks."""
    try:
        if path.is_symlink():
            return False
        if any(p.is_symlink() or not p.is_file() for p in path.iterdir()):
            return False
        meta = json.loads((path / "manifest.json").read_text())
        current = meta["scope"] == "current_consolidated_corporate"
        names = {CONSOLIDATED} if current else set(FILES)
        cap = MAX_CURRENT_BYTES if current else MAX_BYTES
        if {p.name for p in path.iterdir()} != {*names, "manifest.json"}:
            return False
        stamp = datetime.fromisoformat(meta["downloaded_at"])
        if (stamp.tzinfo is None or stamp > datetime.now(UTC)
                or meta["scope"] not in {"historical_three_files", "current_consolidated_corporate"}
                or set(meta["files"]) != names):
            return False
        for name in names:
            file = path / name
            info = meta["files"][name]
            _official_url(info["url"])
            if not 0 < file.stat().st_size == info["bytes"] <= cap:
                return False
            with file.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != info["sha256"]:
                    return False
            if not read_rnp(file, limit=1 if current else None)[0]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, csv.Error):
        return False


def _download(root: Path, current: bool = False) -> Path:
    downloads: dict[str, dict[str, Any]] = {}
    names = {CONSOLIDATED} if current else set(FILES)
    cap = MAX_CURRENT_BYTES if current else MAX_BYTES
    url = LISTING
    visited: set[str] = set()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        while url:
            if url in visited or len(visited) >= 20:
                raise ValueError("Invalid RNP attachment pagination")
            visited.add(url)
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ValueError("Invalid RNP attachment listing")
            for item in payload["results"]:
                if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                    raise ValueError("Invalid RNP attachment metadata")
                name = item["title"]
                if name not in names:
                    continue
                size = _mapping(item.get("extensions")).get("fileSize")
                if name in downloads or type(size) is not int or not 0 < size <= cap:
                    raise ValueError("Duplicate or oversized RNP attachment")
                downloads[name] = {
                    "url": _official_url(_mapping(item.get("_links")).get("download")),
                    "bytes": size,
                    "attachment_updated_at": _mapping(item.get("version", {})).get("when"),
                }
            links = payload.get("_links", {})
            if not isinstance(links, dict):
                raise ValueError("Invalid RNP pagination links")
            url = _official_url(links["next"]) if links.get("next") else ""
        total_cap = cap if current else 96*1024**2
        if set(downloads) != names or sum(d["bytes"] for d in downloads.values()) > total_cap:
            raise ValueError("RNP requires the complete bounded contract for the selected scope")
        with tempfile.TemporaryDirectory(dir=root, prefix="pending-") as directory:
            staging = Path(directory)
            for name, info in downloads.items():
                path = staging / name
                with client.stream("GET", info["url"]) as response, path.open("wb") as stream:
                    response.raise_for_status()
                    count = 0
                    for chunk in response.iter_bytes():
                        count += len(chunk)
                        if count > info["bytes"]:
                            raise ValueError("RNP attachment exceeds declared size")
                        stream.write(chunk)
                if count != info["bytes"] or not read_rnp(path, limit=1 if current else None)[0]:
                    raise ValueError("Empty, truncated or invalid RNP attachment")
                with path.open("rb") as stream:
                    info["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            manifest = {"source_page": SOURCE_URL, "downloaded_at": datetime.now(UTC).isoformat(),
                        "scope": ("current_consolidated_corporate" if current
                                  else "historical_three_files"), "source_cutoff": None,
                        "license": "unspecified", "files": downloads,
                        "limitations": ("Corporate declarations only; no proof of current control"
                                        if current else "Historical three-file attachments")}
            (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            snapshot = staging.with_name(staging.name.replace("pending-", "snapshot-", 1))
            staging.rename(snapshot)
            return snapshot


def acquire(root: Path, *, current: bool = False) -> Path:
    """Publish atomically, or select a complete verified historical snapshot on failure."""
    root.mkdir(parents=True, exist_ok=True)
    try:
        return _download(root, current)
    except (httpx.HTTPError, ValueError, OSError, csv.Error):
        scope = "current_consolidated_corporate" if current else "historical_three_files"
        candidates = [p for p in root.glob("snapshot-*") if valid_snapshot(p)
                      and json.loads((p / "manifest.json").read_text())["scope"] == scope]
        if not candidates:
            raise
        snapshot = max(candidates, key=lambda p: json.loads(
            (p / "manifest.json").read_text(),
        )["downloaded_at"])
        logger.warning("RNP acquisition failed; verified %s fallback: %s", scope, snapshot)
        return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--historical-three-files", action="store_true",
                        help="Acknowledge historical attachments, not current consolidated RNP")
    mode.add_argument("--current-consolidated", action="store_true",
                      help="Acquire consolidated RNP; loader accepts corporate declarations only")
    args = parser.parse_args()
    print(acquire(args.output_dir, current=args.current_consolidated))
