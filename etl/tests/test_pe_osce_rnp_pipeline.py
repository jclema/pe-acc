import hashlib
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bracc_etl.pipelines.pe_osce_rnp import FILES, SOURCE_URL, PeOsceRnpPipeline, read_rnp

FIXTURES = Path(__file__).parent / "fixtures" / "pe_osce_rnp"


@pytest.mark.parametrize("filename", FILES)
def test_exports_preserve_identity_and_provenance(filename: str) -> None:
    rows, count = read_rnp(FIXTURES / filename)
    assert count == len(rows)
    assert all(row["type"] == FILES[filename][0] for row in rows)
    assert all(
        row["source_dataset"] == filename and row["source_url"] == SOURCE_URL for row in rows
    )
    digest = hashlib.sha256((FIXTURES / filename).read_bytes()).hexdigest()
    assert all(row["file_sha256"] == digest for row in rows)
    if filename == "Socios.csv":
        assert rows[0]["document"] == "00000001"
        assert rows[1]["label"] == "Provider"
    if filename == "representantes.csv":
        assert rows[1]["label"] == "Person" and rows[1]["key"] == "ruc"
    if filename == "organos.csv":
        assert {row["cargo"] for row in rows} == {"DIRECTOR", "GERENTE"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("Tipo_Documento", "PASAPORTE"),
        ("Tipo_Documento", "CARNET DE EXTRANJERIA"),
        ("Nro_Documento", ""),
        ("Nro_Documento", "X00000001"),
        ("Nro_Documento", "0000-0001"),
        ("Nro_Documento", "²²²²²²²²"),
        ("Ruc_Proveedor", "123"),
        ("Ruc_Proveedor", "99999999999"),
        ("Ruc_Proveedor", "10999999991"),
        ("Nombre_o_RazonSocial", " "),
    ],
)
def test_invalid_identity_is_skipped(tmp_path: Path, field: str, value: str) -> None:
    columns = (FIXTURES / "Socios.csv").read_text().splitlines()[0].split("|")
    row = dict(
        zip(
            columns,
            ["DOC. NACIONAL DE IDENTIDAD", "00000001", "SINTETICA", "20999999991"],
            strict=True,
        )
    )
    row[field] = value
    path = tmp_path / "Socios.csv"
    path.write_text("|".join(columns) + "\n" + "|".join(row.values()), encoding="cp1252")
    assert read_rnp(path) == ([], 1)


@pytest.mark.parametrize(
    "content",
    [
        "Tipo_Documento|Nro_Documento\n",
        "Tipo_Documento,Tipo_Documento\n",
        (FIXTURES / "Socios.csv").read_text().splitlines()[0] + "\nDNI|1|X\n",
        (FIXTURES / "Socios.csv").read_text().splitlines()[0] + "\nDNI|1|X|123|extra\n",
    ],
)
def test_bad_schema_or_row_fails(tmp_path: Path, content: str) -> None:
    path = tmp_path / "Socios.csv"
    path.write_text(content)
    with pytest.raises(ValueError):
        read_rnp(path)


def test_pipeline_requires_complete_inputs_and_resets(tmp_path: Path) -> None:
    pipeline = PeOsceRnpPipeline(MagicMock(), str(tmp_path), limit=2)
    with pytest.raises(FileNotFoundError):
        pipeline.extract()
    shutil.copytree(FIXTURES, tmp_path / "raw" / "pe" / "osce_rnp")
    pipeline.extract()
    pipeline.transform()
    original = pipeline.records.copy()
    pipeline.transform()
    assert pipeline.records == original and pipeline.rows_in == 7
    assert len(pipeline.records) == pipeline.rows_loaded == 2


@pytest.mark.parametrize("filename", FILES)
def test_schema_is_validated_for_each_export(tmp_path: Path, filename: str) -> None:
    path = tmp_path / filename
    path.write_bytes((FIXTURES / filename).read_bytes().replace(b"Tipo_Documento", b"Wrong"))
    with pytest.raises(ValueError):
        read_rnp(path)


def test_runner_registration() -> None:
    from bracc_etl.runner import PIPELINES

    assert PIPELINES["pe_osce_rnp"] is PeOsceRnpPipeline
    assert PeOsceRnpPipeline.source_id == "osce_rnp"
