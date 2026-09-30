from pathlib import Path

import pytest

from bracc_etl.pipelines.pe_osce_rnp import FILES, SOURCE_URL, read_rnp

FIXTURES = Path(__file__).parent / "fixtures" / "pe_osce_rnp"


@pytest.mark.parametrize("filename", FILES)
def test_exports_preserve_identity_and_provenance(filename: str) -> None:
    rows, count = read_rnp(FIXTURES / filename)
    assert count == len(rows)
    assert all(row["type"] == FILES[filename][0] for row in rows)
    assert all(
        row["source_dataset"] == filename and row["source_url"] == SOURCE_URL for row in rows
    )
    assert all(len(row["file_sha256"]) == 64 for row in rows)
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
    path.write_text(
        "|".join(columns) + "\n" + "|".join(row.values()), encoding="cp1252"
    )
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
