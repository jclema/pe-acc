import json
from pathlib import Path

import httpx
import pytest

from bracc_etl import rnp_acquisition as acquisition
from bracc_etl.pipelines.pe_osce_rnp import FILES, PeOsceRnpPipeline

ORIGINAL_CLIENT = httpx.Client
FIXTURES = Path(__file__).parent / "fixtures/pe_osce_rnp"


def serve(monkeypatch, failure=""):

    def handler(request):
        if failure == "network":
            return httpx.Response(503)
        if request.url.path.endswith("/attachment"):
            names = list(FILES)[:1] if failure == "missing" else list(FILES)
            entries = [{"title": name, "extensions": {"fileSize": (FIXTURES / name).stat().st_size},
                        "_links": {"download": f"/download/{name}"},
                        "version": {"when": "2021-11-11T21:38:16Z"}} for name in names]
            if failure == "duplicate":
                entries += entries[:1]
            if failure == "external":
                entries[0]["_links"]["download"] = "https://other.test/file"
            if failure == "bad_metadata":
                entries[0]["extensions"] = None
            links = {"next": acquisition.LISTING} if failure == "loop" else {}
            return httpx.Response(200, json={"results": entries, "_links": links})
        name = request.url.path.rsplit("/", 1)[-1]
        assert name in FILES
        content = (FIXTURES / name).read_bytes()
        if name == "organos.csv":
            if failure == "partial":
                return httpx.Response(503)
            if failure == "schema":
                content = content.replace(b"Cargo", b"Wrong")
            if failure == "empty":
                content = content.split(b"\n")[0] + b"\n"
            if failure == "truncated":
                content = content[:-1]
        return httpx.Response(200, content=content)

    monkeypatch.setattr(httpx, "Client", lambda **kw: ORIGINAL_CLIENT(
        transport=httpx.MockTransport(handler), **kw,
    ))


def test_complete_snapshot_hashes_and_local_pipeline_compatibility(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    serve(monkeypatch)
    snapshot = acquisition.acquire(tmp_path)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["scope"] == "historical_three_files"
    assert manifest["source_cutoff"] is None and manifest["license"] == "unspecified"
    assert set(manifest["files"]) == set(FILES)
    assert acquisition.valid_snapshot(snapshot)
    pipeline = PeOsceRnpPipeline(MagicMock())
    pipeline.raw_files = [snapshot / name for name in FILES]
    pipeline.transform()
    assert pipeline.rows_loaded == 6
    assert {row["source_dataset"] for row in pipeline.records} == set(FILES)
    (snapshot / "Socios.csv").write_bytes(b"tampered")
    assert not acquisition.valid_snapshot(snapshot)


@pytest.mark.parametrize("failure", ["missing", "duplicate", "external", "partial", "schema",
                                      "empty", "truncated", "network", "loop", "bad_metadata"])
def test_failure_never_publishes_partial_snapshot(tmp_path, monkeypatch, failure):
    serve(monkeypatch, failure)
    with pytest.raises((ValueError, httpx.HTTPError)):
        acquisition.acquire(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_fallback_requires_intact_complete_snapshot(tmp_path, monkeypatch):
    serve(monkeypatch)
    snapshot = acquisition.acquire(tmp_path)
    serve(monkeypatch, "network")
    assert acquisition.acquire(tmp_path) == snapshot
    (snapshot / "organos.csv").unlink()
    with pytest.raises(httpx.HTTPError):
        acquisition.acquire(tmp_path)


def test_snapshot_rejects_symlink_and_forged_manifest(tmp_path, monkeypatch):
    serve(monkeypatch)
    snapshot = acquisition.acquire(tmp_path)
    (tmp_path / "snapshot-link").symlink_to(snapshot, target_is_directory=True)
    assert not acquisition.valid_snapshot(tmp_path / "snapshot-link")
    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest["downloaded_at"] = "2999-01-01T00:00:00Z"
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    assert not acquisition.valid_snapshot(snapshot)
