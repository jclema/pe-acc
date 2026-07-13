from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from bracc_etl.pipelines.pe_osce_rnp import PeOsceRnpPipeline

if TYPE_CHECKING:
    from pathlib import Path


def _make_pipeline(tmp_path: Path) -> PeOsceRnpPipeline:
    driver = MagicMock()
    return PeOsceRnpPipeline(driver=driver, data_dir=str(tmp_path))  # type: ignore[arg-type]


def test_pipeline_metadata() -> None:
    assert PeOsceRnpPipeline.name == "pe_osce_rnp"
    assert PeOsceRnpPipeline.source_id == "osce_rnp"


def test_default_source_mode_is_file(tmp_path: Path) -> None:
    pipeline = _make_pipeline(tmp_path)
    assert pipeline.source_mode == "file"


def _write_pipe_csv(path: Path, header: str, rows: list[str]) -> None:
    path.write_text("\n".join([header, *rows]), encoding="latin-1")


def test_transform_socios_creates_person_relationship(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_rnp"
    raw_dir.mkdir(parents=True)
    _write_pipe_csv(
        raw_dir / "Socios.csv",
        "Tipo_Documento|Nro_Documento|Nombre_o_RazonSocial|Ruc_Proveedor",
        ["DOC. NACIONAL DE IDENTIDAD/LE|08251829|ALFONSO PESCHIERA ALFARO|20100000335"],
    )

    pipeline = _make_pipeline(tmp_path)
    pipeline.raw_files = [raw_dir / "Socios.csv"]
    pipeline.transform()

    assert len(pipeline.persons) == 1
    assert pipeline.persons[0]["dni"] == "08251829"
    assert len(pipeline.companies) == 1
    assert pipeline.companies[0]["ruc"] == "20100000335"
    assert len(pipeline.socio_de) == 1
    rel = pipeline.socio_de[0]
    assert rel["source_key"] == "08251829"
    assert rel["target_key"] == "20100000335"
    assert rel["_label"] == "Person"


def test_transform_representantes_handles_company_socio(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_rnp"
    raw_dir.mkdir(parents=True)
    _write_pipe_csv(
        raw_dir / "representantes.csv",
        "Tipo_Documento|Nro_Documento|Nombre_RazonSocial|Ruc_Proveedor",
        ["REG. UNICO DE CONTRIBUYENTES|20100009999|HOLDING MATRIZ SAC|20100000335"],
    )

    pipeline = _make_pipeline(tmp_path)
    pipeline.raw_files = [raw_dir / "representantes.csv"]
    pipeline.transform()

    assert len(pipeline.persons) == 0
    # Both the "socio" company and the target provider get a company row.
    rucs = {c["ruc"] for c in pipeline.companies}
    assert rucs == {"20100009999", "20100000335"}
    assert len(pipeline.representa_a) == 1
    rel = pipeline.representa_a[0]
    assert rel["source_key"] == "20100009999"
    assert rel["target_key"] == "20100000335"
    assert rel["_label"] == "Provider"


def test_transform_organos_keeps_cargo_property(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_rnp"
    raw_dir.mkdir(parents=True)
    _write_pipe_csv(
        raw_dir / "organos.csv",
        "Tipo_Documento|Nro_Documento|Nombre_RazonSocial|Cargo|Ruc_Proveedor",
        ["DOC. NACIONAL DE IDENTIDAD|09394863|PEDRO BLAY HIDALGO|Director|20100000335"],
    )

    pipeline = _make_pipeline(tmp_path)
    pipeline.raw_files = [raw_dir / "organos.csv"]
    pipeline.transform()

    assert len(pipeline.miembro_organo_de) == 1
    rel = pipeline.miembro_organo_de[0]
    assert rel["cargo"] == "Director"
    assert rel["_label"] == "Person"


def test_transform_skips_foreign_document_and_bad_ruc(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_rnp"
    raw_dir.mkdir(parents=True)
    _write_pipe_csv(
        raw_dir / "Socios.csv",
        "Tipo_Documento|Nro_Documento|Nombre_o_RazonSocial|Ruc_Proveedor",
        [
            # Foreign id, not 8 or 11 digits after stripping -> skipped.
            "CARNET DE EXTRANJERIA|X123AB|JOHN DOE|20100000335",
            # Invalid RUC (not 11 digits) -> skipped.
            "DOC. NACIONAL DE IDENTIDAD|08251829|JANE DOE|12345",
        ],
    )

    pipeline = _make_pipeline(tmp_path)
    pipeline.raw_files = [raw_dir / "Socios.csv"]
    pipeline.transform()

    assert pipeline.socio_de == []
    assert pipeline.persons == []


def test_load_creates_expected_relationship_queries(tmp_path: Path) -> None:
    pipeline = _make_pipeline(tmp_path)
    pipeline.persons = [
        {"dni": "08251829", "name": "ALFONSO PESCHIERA ALFARO", "source": "osce_rnp"},
    ]
    pipeline.companies = [{"ruc": "20100000335", "source": "osce_rnp"}]
    pipeline.socio_de = [
        {
            "source_key": "08251829",
            "target_key": "20100000335",
            "source": "osce_rnp",
            "_label": "Person",
        },
    ]
    pipeline.representa_a = []
    pipeline.miembro_organo_de = []

    pipeline.load()

    session_mock = pipeline.driver.session.return_value.__enter__.return_value
    run_calls = [str(call) for call in session_mock.run.call_args_list]
    assert any("MERGE (n:Person" in call for call in run_calls)
    assert any("MERGE (n:Provider" in call for call in run_calls)
    assert any("MERGE (a)-[r:SOCIO_DE]->(b)" in call for call in run_calls)


def _mock_response(
    *, json_body: object = None, content: bytes = b"", status: int = 200,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.raise_for_status = MagicMock()
    if status >= 400:
        response.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    response.json.return_value = json_body
    response.content = content
    return response


def test_extract_via_api_downloads_rnp_attachments(tmp_path: Path) -> None:
    names = ["Socios.csv", "representantes.csv", "organos.csv"]
    listing = {
        "results": [
            {
                "title": name,
                "_links": {"download": f"/rest/api/content/1/child/attachment/att{i}/download"},
            }
            for i, name in enumerate(names)
        ]
        + [
            {
                "title": "sancionados.csv",
                "_links": {"download": "/rest/api/content/1/child/attachment/att99/download"},
            },
        ],
    }
    responses = [_mock_response(json_body=listing)]
    responses += [_mock_response(content=b"header|col\nrow|value\n") for _ in names]

    driver = MagicMock()
    pipeline = PeOsceRnpPipeline(driver=driver, data_dir=str(tmp_path), source_mode="api")  # type: ignore[arg-type]

    with patch("httpx.get", side_effect=responses) as mock_get:
        pipeline.extract()

    assert mock_get.call_count == 1 + len(names)
    assert {p.name for p in pipeline.raw_files} == set(names)


def test_extract_falls_back_to_file_mode_on_api_failure(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_rnp"
    raw_dir.mkdir(parents=True)
    (raw_dir / "Socios.csv").write_text("Tipo_Documento|Nro_Documento\n", encoding="latin-1")

    driver = MagicMock()
    pipeline = PeOsceRnpPipeline(driver=driver, data_dir=str(tmp_path), source_mode="api")  # type: ignore[arg-type]

    with patch("httpx.get", side_effect=RuntimeError("network down")):
        pipeline.extract()

    assert pipeline.raw_files == [raw_dir / "Socios.csv"]
