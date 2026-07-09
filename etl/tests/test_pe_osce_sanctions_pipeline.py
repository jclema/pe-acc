from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline

FIXTURES = Path(__file__).parent / "fixtures"


def _make_pipeline() -> PeOsceSanctionsPipeline:
    driver = MagicMock()
    return PeOsceSanctionsPipeline(driver=driver, data_dir=str(FIXTURES.parent))  # type: ignore[arg-type]


def _load_fixture_data(pipeline: PeOsceSanctionsPipeline) -> None:
    pipeline._raw_sanctions = pd.read_csv(
        FIXTURES / "pe_osce_sanctions.csv",
        dtype=str,
        keep_default_na=False,
    )


def test_pipeline_metadata() -> None:
    assert PeOsceSanctionsPipeline.name == "pe_osce_sanctions"
    assert PeOsceSanctionsPipeline.source_id == "osce_sanctions"


def test_transform_builds_provider_and_sanction_records() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    assert len(pipeline.providers) == 2
    assert len(pipeline.sanctions) == 2
    assert len(pipeline.provider_sanctions) == 2


def test_transform_keeps_ruc_linkage() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    rel = pipeline.provider_sanctions[0]
    assert rel["source_key"] == "20123456789"
    assert rel["target_key"] == "OSCE-001"
    assert rel["confidence"] == 1.0


def test_load_creates_has_sanction_relationship() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()
    pipeline.load()

    session_mock = pipeline.driver.session.return_value.__enter__.return_value
    run_calls = session_mock.run.call_args_list
    rel_calls = [call for call in run_calls if "MERGE (a)-[r:HAS_SANCTION]->(b)" in str(call)]
    assert rel_calls, "Expected HAS_SANCTION MERGE calls"


def test_transform_keeps_fixture_source_url() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    assert pipeline.sanctions[0]["source_url"] == "https://example.gob.pe/osce/001"
    assert pipeline.providers[0]["source_url"] == "https://example.gob.pe/osce/001"


def test_transform_falls_back_to_registry_source_url() -> None:
    pipeline = _make_pipeline()
    pipeline.raw_files = []
    pipeline._raw_sanctions = pd.DataFrame(
        [
            {
                "FECHA_CORTE": "20260404",
                "RUC": "20100994128",
                "NOMBRE_RAZONODENOMINACIONSOCIAL": "CONSTRUCTORA DOS DE MAYO S.A.",
                "FECHA_INICIO": "19980806",
                "FECHA_FIN": "",
                "NUMERO_RESOLUCION": "074-1998-TL",
                "ID_MOTIVO_INFRACCION": "12",
                "DE_MOTIVO_INFRACCION": "RESCISION ADMINISTRATIVA DEL CONTRATO",
            },
        ],
    )

    pipeline.transform()

    source_url = pipeline.sanctions[0]["source_url"]
    assert source_url
    assert source_url.startswith("https://")
    assert pipeline.providers[0]["source_url"] == source_url


def test_transform_maps_real_tcp_columns() -> None:
    pipeline = _make_pipeline()
    pipeline.raw_files = []
    pipeline._raw_sanctions = pd.DataFrame(
        [
            {
                "FECHA_CORTE": "20260404",
                "RUC": "20100994128",
                "NOMBRE_RAZONODENOMINACIONSOCIAL": "CONSTRUCTORA DOS DE MAYO S.A.",
                "FECHA_INICIO": "19980806",
                "FECHA_FIN": "",
                "NUMERO_RESOLUCION": "074-1998-TL",
                "ID_MOTIVO_INFRACCION": "12",
                "DE_MOTIVO_INFRACCION": "RESCISION ADMINISTRATIVA DEL CONTRATO",
            },
        ],
    )

    pipeline.transform()

    assert len(pipeline.providers) == 1
    assert len(pipeline.sanctions) == 1
    sanction = pipeline.sanctions[0]
    assert sanction["sanction_id"] == "074-1998-TL"
    assert sanction["sanction_source"] == "OSCE_TCP"
    assert sanction["date_start"] == "1998-08-06"
    assert sanction["extraction_date"] == "2026-04-04"


def test_transform_maps_real_judicial_columns() -> None:
    """Real OSCE export uses RUC/DNI, RazonSocial/Nombre, NumeroResolucion,
    OrganoJurisdiccional, Periodo, FechaInicioInhabilitacion, FechaFinInhabilitacion
    (not the RUC_DNI / ORGANO_JURISDICCIONAL / FECHA_INICIO names used elsewhere)."""
    pipeline = _make_pipeline()
    pipeline.raw_files = []
    pipeline._raw_sanctions = pd.DataFrame(
        [
            {
                "RUC/DNI": "10308354194",
                "RazonSocial/Nombre": "MELO JUANA",
                "NumeroResolucion": "SENTENCIA DE FECHA 28.09.2017",
                "OrganoJurisdiccional": "Corte Superior de Justicia de Arequipa",
                "Periodo": "48 MES(ES)",
                "FechaInicioInhabilitacion": "08/11/2017",
                "FechaFinInhabilitacion": "08/11/2021",
            },
        ],
    )

    provider, sanction, _ = pipeline._normalize_sanction_row(
        pipeline._raw_sanctions.iloc[0].to_dict(),
        0,
        source_kind="judicial",
        source_file="inhabilitaciones_judiciales.csv",
    )

    assert provider is not None
    assert provider["ruc"] == "10308354194"
    assert sanction is not None
    assert sanction["provider_name"] == "MELO JUANA"
    assert sanction["sanction_source"] == "PODER_JUDICIAL"
    assert sanction["reason"] == "Corte Superior de Justicia de Arequipa"
    assert sanction["resolution_number"] == "SENTENCIA DE FECHA 28.09.2017"
    assert sanction["date_start"] == "2017-11-08"
    assert sanction["date_end"] == "2021-11-08"


def test_transform_raw_files_handles_tcp_and_judicial(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)

    (raw_dir / "sancionados.csv").write_text(
        "\n".join(
            [
                "FECHA_CORTE|RUC|NOMBRE_RAZONODENOMINACIONSOCIAL|FECHA_INICIO|FECHA_FIN|NUMERO_RESOLUCION|ID_MOTIVO_INFRACCION|DE_MOTIVO_INFRACCION",
                "20260404|20100994128|CONSTRUCTORA DOS DE MAYO S.A.|19980806||074-1998-TL|12|RESCISION ADMINISTRATIVA DEL CONTRATO",
            ],
        ),
        encoding="latin-1",
    )

    (raw_dir / "inhabilitaciones_judiciales.csv").write_text(
        "\n".join(
            [
                "FECHA_CORTE|RUC_DNI|NOMBRE_RAZONODENOMINACIONSOCIAL|ORGANO_JURISDICCIONAL|NUMERO_RESOLUCION|FECHA_INICIO|FECHA_FIN",
                "20260401|10040039711|BARRETO MARCELO TEODORO|Corte Superior de Justicia de Pasco|SENTENCIA DE FECHA 28.04.2017|20170428|20250428",
                "20260401|1010900768|JOSE ANTONIO CORONADO HURTADO|Lima Norte|s/n de fecha 23.08.2018|20190214|20240214",
            ],
        ),
        encoding="latin-1",
    )

    driver = MagicMock()
    pipeline = PeOsceSanctionsPipeline(driver=driver, data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()
    pipeline.transform()

    assert pipeline.normalized_csv_path is not None
    assert pipeline.normalized_csv_path.exists()
    assert len(pipeline.providers) == 2
    assert len(pipeline.sanctions) == 2
    assert all(rel["confidence"] == 1.0 for rel in pipeline.provider_sanctions)

    with pipeline.normalized_csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    by_source = {row["sanction_source"]: row for row in rows}
    assert by_source["OSCE_TCP"]["ruc"] == "20100994128"
    assert by_source["PODER_JUDICIAL"]["ruc"] == "10040039711"
    assert all(row["source_url"] for row in rows)


def test_default_source_mode_is_file() -> None:
    pipeline = _make_pipeline()
    assert pipeline.source_mode == "file"


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


def test_extract_via_api_downloads_known_attachments(tmp_path: Path) -> None:
    listing = {
        "results": [
            {
                "title": "sancionados.csv",
                "_links": {"download": "/rest/api/content/1/child/attachment/att1/download"},
            },
            {
                "title": "inhabilitaciones_judiciales.csv",
                "_links": {"download": "/rest/api/content/1/child/attachment/att2/download"},
            },
            {
                "title": "Socios.csv",
                "_links": {"download": "/rest/api/content/1/child/attachment/att3/download"},
            },
        ],
    }
    tcp_body = (
        b"FECHA_CORTE|RUC|NOMBRE_RAZONODENOMINACIONSOCIAL|FECHA_INICIO|FECHA_FIN|"
        b"NUMERO_RESOLUCION|ID_MOTIVO_INFRACCION|DE_MOTIVO_INFRACCION\n"
    )
    judicial_body = (
        b"RUC/DNI|RazonSocial/Nombre|NumeroResolucion|OrganoJurisdiccional|Periodo|"
        b"FechaInicioInhabilitacion|FechaFinInhabilitacion\n"
    )

    responses = [
        _mock_response(json_body=listing),
        _mock_response(content=tcp_body),
        _mock_response(content=judicial_body),
    ]

    driver = MagicMock()
    pipeline = PeOsceSanctionsPipeline(driver=driver, data_dir=str(tmp_path), source_mode="api")  # type: ignore[arg-type]

    with patch("httpx.get", side_effect=responses) as mock_get:
        pipeline.extract()

    assert mock_get.call_count == 3
    assert {p.name for p in pipeline.raw_files} == {
        "sancionados.csv", "inhabilitaciones_judiciales.csv",
    }
    for path in pipeline.raw_files:
        assert path.exists()
    assert (tmp_path / "raw" / "pe" / "osce_sanctions" / "sancionados.csv").read_bytes() == tcp_body


def test_extract_falls_back_to_file_mode_on_api_failure(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "sancionados.csv").write_text(
        "FECHA_CORTE|RUC|NOMBRE_RAZONODENOMINACIONSOCIAL|FECHA_INICIO|FECHA_FIN|NUMERO_RESOLUCION|"
        "ID_MOTIVO_INFRACCION|DE_MOTIVO_INFRACCION\n",
        encoding="latin-1",
    )

    driver = MagicMock()
    pipeline = PeOsceSanctionsPipeline(driver=driver, data_dir=str(tmp_path), source_mode="api")  # type: ignore[arg-type]

    with patch("httpx.get", side_effect=RuntimeError("network down")):
        pipeline.extract()

    assert pipeline.raw_files == [raw_dir / "sancionados.csv"]


def test_extract_via_api_raises_when_no_attachments_found(tmp_path: Path) -> None:
    responses = [_mock_response(json_body={"results": []})]

    driver = MagicMock()
    pipeline = PeOsceSanctionsPipeline(driver=driver, data_dir=str(tmp_path), source_mode="api")  # type: ignore[arg-type]

    with patch("httpx.get", side_effect=responses):
        pipeline.extract()

    # No attachments found -> API path raises internally and extract() falls back to file mode
    assert pipeline.raw_files == []
