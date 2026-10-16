import io
import json
import zipfile

import httpx
import pytest

from bracc_etl import seace_acquisition as acquisition

CLIENT = httpx.Client
# Literal header checked against the official 2026 workbook using bounded HTTP ranges.
HEADER = [
    'CODIGOENTIDAD', 'ENTIDAD_RUC', 'ENTIDAD', 'TIPOENTIDAD', 'ENTIDAD_DEPARTAMENTO',
    'CODIGOCONVOCATORIA', 'OBJETOCONTRACTUAL', 'TIPOPROCESOSELECCION', 'PROCESO',
    'DESCRIPCION_PROCESO', 'N_ITEM', 'DESCRIPCION_ITEM', 'ESTADO_ITEM',
    'CANTIDAD_ADJUDICADO_ITEM', 'MONTO_REFERENCIAL_ITEM_SOLES', 'MONTO_ADJUDICADO_ITEM_SOLES',
    'DEPARTAMENTO_ITEM', 'MONEDA', 'UNIDAD_MEDIDA', 'RUC PROVEEDOR', 'PROVEEDOR',
    'TIPO_PROVEEDOR', 'FECHA_CONVOCATORIA', 'FECHA_BUENAPRO', 'FECHA_CONSENTIMIENTO_BP'
]
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def workbook(failure="", rows=None):
    stream = io.BytesIO()
    header = HEADER.copy()
    if failure == "schema":
        header[19] = "WRONG_RUC"
    if failure == "duplicate":
        header[-1] = header[0]
    from xml.sax.saxutils import escape
    values = header + [value for row in (rows or []) for value in row.values()]
    strings = "".join(f"<si><t>{escape(value)}</t></si>" for value in values)
    if failure == "shared_xml":
        strings += "<broken>"
    cells = "".join(f'<c t="s"><v>{i}</v></c>' for i in range(len(header)))
    body = '<row r="2"><c><v>20999999991</v></c></row>'
    if rows is not None:
        body = ""
        for number, row in enumerate(rows, 2):
            cells_for_row = "".join(
                (f'<c r="{chr(65+i)}{number}"><v>{row[key]}</v></c>'
                 if key == "MONTO_ADJUDICADO_ITEM_SOLES" and row[key].isdigit()
                 else f'<c r="{chr(65+i)}{number}" t="s"><v>{values.index(row[key])}</v></c>')
                for i, key in enumerate(header) if row.get(key)
            )
            body += f'<row r="{number}">{cells_for_row}</row>'
    if failure in ('xml', 'empty'):
        body = '<broken>' if failure == 'xml' else ''
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{NS}" xmlns:r="{rel}"><sheets>'
                   '<sheet name="Adjudicaciones" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" '
                   'Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("_rels/.rels", '<Relationships/>')
        z.writestr("[Content_Types].xml", '<Types/>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{NS}">{strings}</sst>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet xmlns="{NS}"><sheetData><row r="1">{cells}</row>{body}'
                   '</sheetData></worksheet>')
    return stream.getvalue()


def serve(monkeypatch, content, status=200):
    def handler(request):
        assert str(request.url) == (
            "https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/"
            "adjudicaciones/2026/CONOSCE_ADJUDICACIONES2026_0.xlsx"
        )
        return httpx.Response(status, content=content, headers={
            "Content-Length": str(len(content)), "Last-Modified": "Fri, 09 Oct 2026 20:47:00 GMT",
        })
    monkeypatch.setattr(httpx, "Client", lambda **kw: CLIENT(
        transport=httpx.MockTransport(handler), **kw,
    ))


def test_single_year_snapshot_integrity_and_no_local_csv_conversion(tmp_path, monkeypatch):
    content = workbook()
    serve(monkeypatch, content)
    snapshot = acquisition.acquire(tmp_path, 2026)
    assert {p.name for p in snapshot.iterdir()} == {
        "CONOSCE_ADJUDICACIONES2026_0.xlsx", "manifest.json",
    }
    meta = json.loads((snapshot / "manifest.json").read_text())
    assert meta["mode"] == "official_xlsx_download" and meta["year"] == 2026
    assert meta["source_cutoff"] is None and meta["license"] == "unspecified"
    assert meta["last_modified"] == "Fri, 09 Oct 2026 20:47:00 GMT"
    assert acquisition.valid_snapshot(snapshot)
    (snapshot / "CONOSCE_ADJUDICACIONES2026_0.xlsx").write_bytes(b"changed")
    assert not acquisition.valid_snapshot(snapshot)


@pytest.mark.parametrize("failure", ["schema", "duplicate", "empty", "zip", "http", "xml",
                                      "shared_xml"])
def test_incomplete_or_incompatible_download_never_publishes(tmp_path, monkeypatch, failure):
    content = b"<html>error</html>" if failure == "zip" else workbook(failure)
    serve(monkeypatch, content, 503 if failure == "http" else 200)
    with pytest.raises((ValueError, httpx.HTTPError)):
        acquisition.acquire(tmp_path, 2026)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("year", [2017, 2999])
def test_unpublished_year_is_rejected_before_http(tmp_path, year):
    with pytest.raises(ValueError):
        acquisition.acquire(tmp_path, year)


def test_rejects_truncation_and_keeps_previous_snapshot(tmp_path, monkeypatch):
    serve(monkeypatch, workbook())
    previous = acquisition.acquire(tmp_path, 2026)
    serve(monkeypatch, workbook()[:-50])
    with pytest.raises(ValueError):
        acquisition.acquire(tmp_path, 2026)
    assert list(tmp_path.iterdir()) == [previous]
    assert acquisition.valid_snapshot(previous)


def test_size_cap_and_snapshot_metadata_guards(tmp_path, monkeypatch):
    serve(monkeypatch, workbook())
    snapshot = acquisition.acquire(tmp_path, 2026)
    link = tmp_path / "snapshot-link"
    link.symlink_to(snapshot, target_is_directory=True)
    assert not acquisition.valid_snapshot(link)
    meta = json.loads((snapshot / "manifest.json").read_text())
    meta["downloaded_at"] = "2999-01-01T00:00:00Z"
    (snapshot / "manifest.json").write_text(json.dumps(meta))
    assert not acquisition.valid_snapshot(snapshot)
    monkeypatch.setattr(acquisition, "MAX_BYTES", 32)
    with pytest.raises(ValueError, match="size"):
        acquisition.acquire(tmp_path, 2026)
    assert {p.name for p in tmp_path.iterdir()} == {snapshot.name, link.name}


def official_input(tmp_path, monkeypatch, mutate=None):
    import csv
    from pathlib import Path

    with (Path(__file__).parent / "fixtures/pe_seace_official_rows.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    if mutate:
        mutate(rows)
    serve(monkeypatch, workbook(rows=rows))
    snapshot = acquisition.acquire(tmp_path, 2026)
    destination = tmp_path / "pe/seace_conosce/official"
    destination.parent.mkdir(parents=True)
    snapshot.rename(destination)
    return destination


def test_official_workbook_loads_distinct_items_with_source_rows_and_pen(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from bracc_etl.pipelines.pe_seace_conosce import PeSeaceConoscePipeline

    path = official_input(tmp_path, monkeypatch)
    pipeline = PeSeaceConoscePipeline(MagicMock(), str(tmp_path))
    pipeline.extract()
    pipeline.transform()
    assert pipeline.rows_in == 7 and pipeline.rows_loaded == 2
    assert {r["ruc"] for r in pipeline.providers} == {"20999999991", "20999999992"}
    assert [r["award_id"] for r in pipeline.awards] == [
        "SEACE-101-ITEM-1-RUC-20999999991", "SEACE-101-ITEM-2-RUC-20999999992",
    ]
    assert [r["amount"] for r in pipeline.awards] == [100, 200]
    assert pipeline.awards[1]["currency"] == "PEN"
    assert pipeline.awards[1]["original_currency"] == "Dólar Norteamericano"
    assert pipeline.awards[0]["source_row"] == "2"
    assert pipeline.awards[0]["award_title"] == "EQUIPOS FICTICIOS"
    assert pipeline.entities[0]["entity_id"] == "001234"
    assert pipeline.processes[0]["call_date"] == "2026-06-01"
    assert all(r["file_sha256"] == json.loads((path / "manifest.json").read_text())["sha256"]
               and r["source_dataset"] == "CONOSCE_ADJUDICACIONES2026_0.xlsx"
               for r in pipeline.providers)
    assert pipeline.providers[0]["source_url"].endswith("#row=2")
    limited = PeSeaceConoscePipeline(MagicMock(), str(tmp_path), limit=1)
    limited.extract()
    limited.transform()
    assert limited.rows_loaded == 1 and limited.awards == pipeline.awards[:1]


@pytest.mark.parametrize("failure", ["conflict", "amount", "date", "tampered", "overflow"])
def test_ambiguous_or_invalid_official_input_never_falls_back(tmp_path, monkeypatch, failure):
    from unittest.mock import MagicMock

    from bracc_etl.pipelines.pe_seace_conosce import PeSeaceConoscePipeline

    def mutate(rows):
        if failure == "conflict":
            rows.append(rows[0] | {"MONTO_ADJUDICADO_ITEM_SOLES": "999"})
        elif failure == "overflow":
            rows[0]["MONTO_ADJUDICADO_ITEM_SOLES"] = "1e309"
        elif failure in ("amount", "date"):
            rows[0]["MONTO_ADJUDICADO_ITEM_SOLES" if failure == "amount"
                    else "FECHA_BUENAPRO"] = "NaN" if failure == "amount" else "31/02/2026"
    path = official_input(tmp_path, monkeypatch, mutate)
    if failure == "tampered":
        (path / "CONOSCE_ADJUDICACIONES2026_0.xlsx").write_bytes(b"changed")
    (path.parent / "processes.csv").write_text("entity_id\nlegacy\n")
    pipeline = PeSeaceConoscePipeline(MagicMock(), str(tmp_path))
    with pytest.raises(ValueError):
        pipeline.extract()


def test_limit_does_not_hide_later_winners_for_the_same_item(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from bracc_etl.pipelines.pe_seace_conosce import PeSeaceConoscePipeline

    official_input(tmp_path, monkeypatch, lambda rows: rows.append(
        rows[0] | {"RUC PROVEEDOR": "20999999992", "PROVEEDOR": "PROVEEDOR FICTICIO B"},
    ))
    pipeline = PeSeaceConoscePipeline(MagicMock(), str(tmp_path), limit=1)
    pipeline.extract()
    pipeline.transform()
    assert [r["award_id"] for r in pipeline.awards] == ["SEACE-101-ITEM-2-RUC-20999999992"]
