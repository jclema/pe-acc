from unittest.mock import MagicMock

import httpx
import pytest

from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline

CSV = b"RUC,NUMERO_RESOLUCION\n20123456789,DEMO-001\n"
NAMES = ("sancionados.csv", "inhabilitaciones_judiciales.csv")


def serve(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: client(
            transport=httpx.MockTransport(handler),
            **kw,
        ),
    )


def listing(names=NAMES, **links):
    return {
        "results": [{"title": name, "_links": {"download": f"/download/{name}"}} for name in names],
        "_links": links,
    }


def pipeline(tmp_path, **kwargs):
    return PeOsceSanctionsPipeline(MagicMock(), data_dir=str(tmp_path), **kwargs)


def test_api_paginates_and_normalizes_both_sources(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/attachment"):
            assert request.url.params["limit"] == "50"
            return httpx.Response(200, json=listing(NAMES[:1], next="/next"))
        if request.url.path == "/wiki/next":
            return httpx.Response(200, json=listing(NAMES[1:]))
        assert request.url.path in {f"/wiki/download/{name}" for name in NAMES}
        return httpx.Response(200, content=CSV)

    serve(monkeypatch, handler)
    p = pipeline(tmp_path, source_mode="api")
    p.extract()
    p.transform()
    assert {path.name for path in p.raw_files} == set(NAMES)
    assert {s["sanction_source"] for s in p.sanctions} == {"OSCE_TCP", "PODER_JUDICIAL"}
    assert len({s["sanction_id"] for s in p.sanctions}) == 2
    assert all(s["source_url"] for s in p.sanctions)


@pytest.mark.parametrize("failure", ["timeout", "status", "missing", "invalid", "partial", "title"])
def test_api_failure_preserves_local_fallback(tmp_path, monkeypatch, failure, caplog):
    raw = tmp_path / "raw/pe/osce_sanctions"
    raw.mkdir(parents=True)
    local = raw / "sancionados.csv"
    local.write_bytes(CSV)

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "status":
            return httpx.Response(503)
        if request.url.path.endswith("/attachment"):
            if failure == "title":
                return httpx.Response(200, json={"results": [{"title": []}], "_links": {}})
            return httpx.Response(200, json=listing(NAMES[:1] if failure == "missing" else NAMES))
        if failure == "partial" and request.url.path.endswith(NAMES[1]):
            return httpx.Response(503)
        return httpx.Response(200, content=b"<html>error</html>" if failure == "invalid" else CSV)

    serve(monkeypatch, handler)
    p = pipeline(tmp_path, source_mode="api")
    p.extract()
    assert p.raw_files == [local]
    assert local.read_bytes() == CSV
    assert not list(raw.glob("api/*"))
    assert "fallback" in caplog.text


def test_api_failure_without_local_files_raises(tmp_path, monkeypatch):
    serve(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(RuntimeError, match="local"):
        pipeline(tmp_path, source_mode="api").extract()


def test_file_default_skips_empty_raw_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("PE_OSCE_SOURCE_MODE", raising=False)
    (tmp_path / "raw/pe/osce_sanctions").mkdir(parents=True)
    demo = tmp_path / "pe/osce_sanctions"
    demo.mkdir(parents=True)
    path = demo / "sancionados.csv"
    path.write_bytes(CSV)

    def forbidden(request):
        pytest.fail("file mode must not request the network")

    serve(monkeypatch, forbidden)
    p = pipeline(tmp_path)
    p.extract()
    assert p.raw_files == [path]


def test_mode_from_environment_and_invalid_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("PE_OSCE_SOURCE_MODE", "invalid")
    with pytest.raises(ValueError, match="source_mode"):
        pipeline(tmp_path)
    monkeypatch.setenv("PE_OSCE_SOURCE_MODE", "api")
    serve(
        monkeypatch,
        lambda request: (
            httpx.Response(200, json=listing())
            if request.url.path.endswith("/attachment")
            else httpx.Response(200, content=CSV)
        ),
    )
    p = pipeline(tmp_path)
    p.extract()
    assert len(p.raw_files) == 2


def test_api_outage_reuses_only_completed_snapshot(tmp_path, monkeypatch):
    serve(
        monkeypatch,
        lambda request: (
            httpx.Response(200, json=listing())
            if request.url.path.endswith("/attachment")
            else httpx.Response(200, content=CSV)
        ),
    )
    p = pipeline(tmp_path, source_mode="api")
    p.extract()
    previous = p.raw_files.copy()
    # Reconfigure the transport without wrapping the previous monkeypatch.
    monkeypatch.undo()
    serve(monkeypatch, lambda request: httpx.Response(503))
    p.extract()
    assert p.raw_files == previous
    assert all(path.read_bytes() == CSV for path in previous)


def test_file_mode_accepts_uppercase_csv_and_ignores_directories(tmp_path, monkeypatch):
    monkeypatch.delenv("PE_OSCE_SOURCE_MODE", raising=False)
    raw = tmp_path / "raw/pe/osce_sanctions"
    raw.mkdir(parents=True)
    path = raw / "sancionados.CSV"
    path.write_bytes(CSV)
    (raw / "not-a-file.csv").mkdir()
    p = pipeline(tmp_path)
    p.extract()
    assert p.raw_files == [path]


def test_download_records_verifiable_freshness(tmp_path, monkeypatch):
    import hashlib
    import json
    from datetime import UTC, datetime

    serve(monkeypatch, lambda request: (
        httpx.Response(200, json=listing()) if request.url.path.endswith('/attachment')
        else httpx.Response(200, content=CSV)
    ))
    p = pipeline(tmp_path, source_mode='api')
    before = datetime.now(UTC)
    p.extract()
    manifest = json.loads((p.raw_files[0].parent / 'manifest.json').read_text())
    assert before <= datetime.fromisoformat(manifest['downloaded_at']) <= datetime.now(UTC)
    assert manifest['files']['sancionados.csv']['sha256'] == hashlib.sha256(CSV).hexdigest()
    assert manifest['files']['sancionados.csv']['bytes'] == len(CSV)
    assert p.extraction_status['mode'] == 'api'


def test_fallback_reports_known_age_without_claiming_source_cutoff(tmp_path, monkeypatch, caplog):
    import hashlib
    import json

    raw = tmp_path / 'raw/pe/osce_sanctions/api/snapshot-old'
    raw.mkdir(parents=True)
    for name in NAMES:
        (raw / name).write_bytes(CSV)
    (raw / 'manifest.json').write_text(json.dumps({
        'downloaded_at': '2020-01-01T00:00:00+00:00',
        'files': {name: {'bytes': len(CSV), 'sha256': hashlib.sha256(CSV).hexdigest()}
                  for name in NAMES},
    }))
    serve(monkeypatch, lambda request: httpx.Response(503))
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    assert p.extraction_status['mode'] == 'fallback'
    assert p.extraction_status['downloaded_at'].startswith('2020-01-01')
    assert p.extraction_status['age_seconds'] > 86400
    assert '2020-01-01' in caplog.text


def test_local_fallback_without_manifest_has_unknown_download_date(tmp_path, monkeypatch):
    raw = tmp_path / 'osce_sanctions'
    raw.mkdir()
    (raw / 'sancionados.csv').write_bytes(CSV)
    serve(monkeypatch, lambda request: httpx.Response(503))
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    assert p.extraction_status['downloaded_at'] is None
    assert p.extraction_status['age_seconds'] is None


def test_retention_keeps_latest_complete_snapshots_and_unmanaged_files(tmp_path, monkeypatch):
    monkeypatch.setenv('PE_OSCE_SNAPSHOT_KEEP', '2')
    serve(monkeypatch, lambda request: (
        httpx.Response(200, json=listing()) if request.url.path.endswith('/attachment')
        else httpx.Response(200, content=CSV)
    ))
    p = pipeline(tmp_path, source_mode='api')
    root = tmp_path / 'raw/pe/osce_sanctions/api'
    root.mkdir(parents=True)
    unmanaged = root / 'snapshot-unmanaged'
    unmanaged.mkdir()
    (unmanaged / 'notes.txt').write_text('preserve')
    old_paths = []
    for _ in range(4):
        p.extract()
        old_paths.append(p.raw_files[0].parent)
    assert not old_paths[0].exists() and not old_paths[1].exists()
    assert old_paths[2].exists() and old_paths[3].exists()
    assert (unmanaged / 'notes.txt').read_text() == 'preserve'
    monkeypatch.undo()
    serve(monkeypatch, lambda request: httpx.Response(503))
    p.extract()
    assert p.raw_files[0].parent == old_paths[3]


@pytest.mark.parametrize('keep', ['0', '-1', 'invalid'])
def test_invalid_retention_rejected_before_download(tmp_path, monkeypatch, keep):
    monkeypatch.setenv('PE_OSCE_SNAPSHOT_KEEP', keep)
    with pytest.raises(ValueError, match='PE_OSCE_SNAPSHOT_KEEP'):
        pipeline(tmp_path, source_mode='api')


@pytest.mark.parametrize('metadata', [[], {}, {'downloaded_at': 'bad'},
                                    {'downloaded_at': '2099-01-01T00:00:00+00:00'}])
def test_unusable_metadata_does_not_claim_freshness(tmp_path, monkeypatch, metadata):
    import json

    raw = tmp_path / 'osce_sanctions'
    raw.mkdir()
    (raw / 'sancionados.csv').write_bytes(CSV)
    (raw / 'manifest.json').write_text(json.dumps(metadata))
    p = pipeline(tmp_path, source_mode='file')
    p.extract()
    assert p.extraction_status['downloaded_at'] is None


def test_retention_failure_does_not_switch_successful_download_to_fallback(tmp_path, monkeypatch):
    import shutil

    monkeypatch.setenv('PE_OSCE_SNAPSHOT_KEEP', '1')
    serve(monkeypatch, lambda request: (
        httpx.Response(200, json=listing()) if request.url.path.endswith('/attachment')
        else httpx.Response(200, content=CSV)
    ))
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    original_rmtree = shutil.rmtree
    def denied(path, **kwargs):
        if str(path).split('/')[-1].startswith('snapshot-'):
            raise PermissionError('retention unavailable')
        return original_rmtree(path, **kwargs)
    monkeypatch.setattr(shutil, 'rmtree', denied)
    p.extract()
    assert p.extraction_status['mode'] == 'api'
    assert all(path.exists() for path in p.raw_files)


def test_retention_preserves_tampered_and_symlinked_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv('PE_OSCE_SNAPSHOT_KEEP', '1')
    serve(monkeypatch, lambda request: (
        httpx.Response(200, json=listing()) if request.url.path.endswith('/attachment')
        else httpx.Response(200, content=CSV)
    ))
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    older = p.raw_files[0].parent
    (older / 'sancionados.csv').write_bytes(b'altered')
    alias = older.with_name('snapshot-link')
    alias.symlink_to(older, target_is_directory=True)
    p.extract()
    assert (older / 'sancionados.csv').read_bytes() == b'altered'
    assert alias.is_symlink()
    assert p.raw_files[0].parent != older


@pytest.mark.parametrize('damage', ['csv', 'size', 'date', 'shape', 'symlink'])
def test_fallback_skips_invalid_managed_snapshot(tmp_path, monkeypatch, damage):
    import json
    import shutil

    serve(monkeypatch, lambda request: (
        httpx.Response(200, json=listing()) if request.url.path.endswith('/attachment')
        else httpx.Response(200, content=CSV)
    ))
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    valid = p.raw_files.copy()
    bad = valid[0].parent.with_name('snapshot-damaged')
    shutil.copytree(valid[0].parent, bad)
    manifest = bad / 'manifest.json'
    meta = json.loads(manifest.read_text())
    if damage == 'csv':
        (bad / NAMES[0]).write_bytes(CSV + b'20654321987,OTHER\n')
    elif damage == 'size':
        meta['files'][NAMES[0]]['bytes'] = 0
    elif damage == 'date':
        meta['downloaded_at'] = 'bad'
    elif damage == 'shape':
        meta = []
    else:
        (bad / NAMES[0]).unlink()
        (bad / NAMES[0]).symlink_to(valid[0].parent / NAMES[0])
    (bad.parent / 'snapshot-dangling').symlink_to(bad.parent / 'missing')
    manifest.write_text(json.dumps(meta))
    p.raw_files = [bad / name for name in NAMES]
    p._report_extraction('fallback')
    assert p.extraction_status['downloaded_at'] is None
    monkeypatch.undo()
    serve(monkeypatch, lambda request: httpx.Response(503))
    p.extract()
    assert p.raw_files == valid
    p.snapshot_keep = 1
    p._prune_snapshots(bad.parent, valid[0].parent)
    assert bad.exists()  # Invalid files require manual inspection, never deletion.


def test_legacy_snapshot_without_manifest_remains_available(tmp_path, monkeypatch):
    raw = tmp_path / 'raw/pe/osce_sanctions/api/snapshot-legacy'
    raw.mkdir(parents=True)
    for name in NAMES:
        (raw / name).write_bytes(CSV)
    serve(monkeypatch, lambda request: httpx.Response(503))
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    assert len(p.raw_files) == 2 and p.extraction_status['downloaded_at'] is None
