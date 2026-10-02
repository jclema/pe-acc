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
    (raw / NAMES[1]).write_bytes(CSV)

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
    assert p.raw_files == sorted(raw / name for name in NAMES)
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


@pytest.mark.parametrize('empty_name', NAMES)
def test_empty_attachment_keeps_previous_complete_snapshot(tmp_path, monkeypatch, empty_name):
    empty = False
    def handler(request):
        if request.url.path.endswith('/attachment'):
            return httpx.Response(200, json=listing())
        body = (CSV.splitlines()[0] + b'\n'
                if empty and request.url.path.endswith(empty_name) else CSV)
        return httpx.Response(200, content=body)
    serve(monkeypatch, handler)
    p = pipeline(tmp_path, source_mode='api')
    p.extract()
    previous = p.raw_files.copy()
    empty = True
    p.extract()
    assert p.raw_files == previous
    assert len(list(previous[0].parent.parent.iterdir())) == 1


@pytest.mark.parametrize('names', [NAMES[:1], NAMES])
def test_api_failure_rejects_incomplete_or_empty_local_backup(tmp_path, monkeypatch, names):
    raw = tmp_path / 'osce_sanctions'
    raw.mkdir()
    for name in names:
        (raw / name).write_bytes(CSV if name == NAMES[0] else CSV.splitlines()[0] + b'\n')
    serve(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(RuntimeError, match='fallback'):
        pipeline(tmp_path, source_mode='api').extract()
