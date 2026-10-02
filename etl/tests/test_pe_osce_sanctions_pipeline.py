from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

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
    assert rel["target_key"] == pipeline.sanctions[0]["sanction_id"]
    assert pipeline.sanctions[0]["resolution_number"] == "OSCE-001"
    assert rel["confidence"] == 1.0


def _collision_rows() -> list[dict[str, str]]:
    return [
        {
            "ruc": ruc,
            "provider_name": name,
            "sanction_id": "SENTENCIA DE FECHA 01.01.2020",
            "sanction_type": "MANDATO_JUDICIAL",
            "source_url": f"https://example.gob.pe/osce/{ruc}",
        }
        for ruc, name in [("20123456789", "Proveedor Uno"), ("20654321987", "Proveedor Dos")]
    ]


@pytest.mark.parametrize("raw_csv", [False, True])
def test_same_resolution_keeps_provider_sanctions_separate(
    tmp_path: Path, raw_csv: bool,
) -> None:
    pipeline = PeOsceSanctionsPipeline(driver=MagicMock(), data_dir=str(tmp_path))
    rows = _collision_rows()
    if raw_csv:
        raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
        raw_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_csv(raw_dir / "judicial.csv", index=False)
        pipeline.extract()
    else:
        pipeline._raw_sanctions = pd.DataFrame(rows)
    pipeline.transform()

    assert len(pipeline.providers) == len(pipeline.sanctions) == 2
    assert pipeline.rows_loaded == 2
    sanctions = {row["sanction_id"]: row for row in pipeline.sanctions}
    assert len(sanctions) == 2
    for relationship, original in zip(pipeline.provider_sanctions, rows, strict=True):
        sanction = sanctions[relationship["target_key"]]
        assert sanction["ruc"] == relationship["source_key"] == original["ruc"]
        assert sanction["provider_name"] == original["provider_name"].upper()
        assert sanction["source_url"] == original["source_url"]
        assert sanction["resolution_number"] == original["sanction_id"]
        assert sanction["sanction_id"].startswith("osce_sanctions:v1:")
    if pipeline.normalized_csv_path:
        with pipeline.normalized_csv_path.open(encoding="utf-8", newline="") as csv_file:
            exported = list(csv.DictReader(csv_file))
        assert {row["sanction_id"] for row in exported} == set(sanctions)
        assert all(row["resolution_number"] == rows[0]["sanction_id"] for row in exported)


def test_sanction_ids_are_stable_across_reprocessing_and_row_order() -> None:
    first = _make_pipeline()
    rows = _collision_rows()
    first._raw_sanctions = pd.DataFrame(rows)
    first.transform()
    expected = {row["ruc"]: row["sanction_id"] for row in first.sanctions}
    first.transform()
    assert {row["ruc"]: row["sanction_id"] for row in first.sanctions} == expected

    second = _make_pipeline()
    second._raw_sanctions = pd.DataFrame(list(reversed(rows)) + [rows[0]])
    second.transform()
    assert {row["ruc"]: row["sanction_id"] for row in second.sanctions} == expected
    assert len(expected) == 2


@pytest.mark.parametrize(
    "change", [{"source_kind": "judicial"}, {"sanction_type": "OTRO_TIPO"},
               {"sanction_id": "OTRA RESOLUCION"}],
)
def test_sanction_identity_distinguishes_source_type_and_resolution(
    change: dict[str, str],
) -> None:
    pipeline = _make_pipeline()
    row = _collision_rows()[0]
    _, original, _ = pipeline._normalize_sanction_row(row, 0)
    _, changed, _ = pipeline._normalize_sanction_row(
        row | change, 0, source_kind=change.get("source_kind"),
    )
    assert original is not None and changed is not None
    assert original["sanction_id"] != changed["sanction_id"]


def test_sanction_identity_ignores_file_name_and_mutable_metadata() -> None:
    pipeline = _make_pipeline()
    row = _collision_rows()[0]
    _, original, _ = pipeline._normalize_sanction_row(row, 0, source_file="original.csv")
    _, changed, _ = pipeline._normalize_sanction_row(
        row | {"provider_name": "Nombre actualizado", "source_url": "https://example.gob.pe/new",
               "extraction_date": "2026-09-29"},
        99, source_file="renamed.csv",
    )
    assert original is not None and changed is not None
    assert original["sanction_id"] == changed["sanction_id"]


def test_original_resolution_takes_precedence_over_technical_id() -> None:
    pipeline = _make_pipeline()
    row = _collision_rows()[0] | {"resolution_number": "RESOLUCION ORIGINAL"}
    pipeline._raw_sanctions = pd.DataFrame([row])
    pipeline.transform()
    assert pipeline.sanctions[0]["resolution_number"] == "RESOLUCION ORIGINAL"


def test_transform_keeps_row_source_url() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    expected_url = "https://example.gob.pe/osce/001"
    assert pipeline.providers[0]["source_url"] == expected_url
    assert pipeline.sanctions[0]["source_url"] == expected_url


def test_transform_uses_registered_source_url_when_row_has_none() -> None:
    pipeline = _make_pipeline()
    pipeline._raw_sanctions = pd.DataFrame(
        [{"ruc": "20100994128", "sanction_id": "074-1998-TL"}],
    )

    pipeline.transform()

    source_url = pipeline.sanctions[0]["source_url"]
    assert source_url == (
        "https://osce-gob-pe.atlassian.net/wiki/pages/viewpage.action?pageId=106889269"
    )
    assert pipeline.providers[0]["source_url"] == source_url


def test_load_creates_has_sanction_relationship() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()
    pipeline.load()

    session_mock = pipeline.driver.session.return_value.__enter__.return_value
    run_calls = session_mock.run.call_args_list
    rel_calls = [call for call in run_calls if "MERGE (a)-[r:HAS_SANCTION]->(b)" in str(call)]
    assert rel_calls, "Expected HAS_SANCTION MERGE calls"


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
    assert sanction["resolution_number"] == "074-1998-TL"
    assert sanction["sanction_source"] == "OSCE_TCP"
    assert sanction["date_start"] == "1998-08-06"
    assert sanction["extraction_date"] == "2026-04-04"


def test_transform_maps_real_judicial_columns() -> None:
    pipeline = _make_pipeline()
    row = {
        "RUC/DNI": "10308354194",
        "RazonSocial/Nombre": "MELO JUANA",
        "NumeroResolucion": "SENTENCIA DE FECHA 28.09.2017",
        "OrganoJurisdiccional": "Corte Superior de Justicia de Arequipa",
        "FechaInicioInhabilitacion": "08/11/2017",
        "FechaFinInhabilitacion": "08/11/2021",
    }

    provider, sanction, relationship = pipeline._normalize_sanction_row(
        row,
        0,
        source_kind="judicial",
        source_file="inhabilitaciones_judiciales.csv",
    )

    assert provider is not None
    assert sanction is not None
    assert relationship is not None
    assert provider["ruc"] == "10308354194"
    assert sanction["provider_name"] == "MELO JUANA"
    assert sanction["sanction_source"] == "PODER_JUDICIAL"
    assert sanction["reason"] == "Corte Superior de Justicia de Arequipa"
    assert sanction["date_start"] == "2017-11-08"
    assert sanction["date_end"] == "2021-11-08"


def test_transform_raw_files_handles_comma_delimiter(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "sanctions.csv").write_text(
        "\n".join(
            [
                "ruc,provider_name,sanction_id,sanction_type,sanction_reason,start_date,end_date,source_url,extraction_date",
                "20123456789,Constructora Andina S.A.C.,OSCE-001,INHABILITACION,Informacion publicada,2026-03-15,2026-09-15,https://example.gob.pe/osce/001,2026-04-01",
            ],
        ),
        encoding="latin-1",
    )

    pipeline = PeOsceSanctionsPipeline(driver=MagicMock(), data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()
    pipeline.transform()

    assert len(pipeline.sanctions) == 1
    assert pipeline.sanctions[0]["resolution_number"] == "OSCE-001"
    assert pipeline.sanctions[0]["type"] == "INHABILITACION"


def test_transform_rejects_missing_required_columns(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "invalid.csv").write_text(
        "provider_name,start_date\nProveedor,2026-01-01\n",
        encoding="latin-1",
    )
    pipeline = PeOsceSanctionsPipeline(driver=MagicMock(), data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()

    with pytest.raises(ValueError) as exc_info:
        pipeline.transform()

    message = str(exc_info.value)
    assert "invalid.csv" in message
    assert "missing required OSCE columns" in message


def test_transform_rejects_unsupported_delimiter(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "invalid.csv").write_text(
        "ruc;provider_name;sanction_id\n20123456789;Proveedor;OSCE-001\n",
        encoding="latin-1",
    )
    pipeline = PeOsceSanctionsPipeline(driver=MagicMock(), data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()

    with pytest.raises(ValueError, match="unsupported CSV delimiter"):
        pipeline.transform()


def test_transform_rejects_file_when_every_row_is_invalid(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "invalid.csv").write_text(
        "ruc,provider_name,sanction_id\n123,Documento invalido,OSCE-INVALID\n",
        encoding="latin-1",
    )
    pipeline = PeOsceSanctionsPipeline(driver=MagicMock(), data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()

    with pytest.raises(ValueError, match="no valid sanction rows"):
        pipeline.transform()


def test_transform_skips_incomplete_rows_when_valid_rows_exist(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "sanctions.csv").write_text(
        "\n".join(
            [
                "ruc,provider_name,sanction_id",
                "123,Documento invalido,OSCE-INVALID",
                "20123456789,Resolucion ausente,",
                "20654321987,Proveedor valido,OSCE-VALID",
            ],
        ),
        encoding="latin-1",
    )
    pipeline = PeOsceSanctionsPipeline(driver=MagicMock(), data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()
    pipeline.transform()

    assert [row["resolution_number"] for row in pipeline.sanctions] == ["OSCE-VALID"]
    assert [row["ruc"] for row in pipeline.providers] == ["20654321987"]


def test_transform_raw_files_handles_tcp_and_judicial(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "osce_sanctions"
    raw_dir.mkdir(parents=True)

    (raw_dir / "sancionados.csv").write_text(
        "\n".join(
            [
                "FECHA_CORTE|RUC|NOMBRE_RAZONODENOMINACIONSOCIAL|FECHA_INICIO|FECHA_FIN|NUMERO_RESOLUCION|ID_MOTIVO_INFRACCION|DE_MOTIVO_INFRACCION",
                "20260404|20100994128|CONSTRUCTORA DOS DE MAYO S.A.|19980806||"
                "074-1998-TL|12|RESCISION ADMINISTRATIVA DEL CONTRATO",
            ],
        ),
        encoding="latin-1",
    )

    (raw_dir / "inhabilitaciones_judiciales.csv").write_text(
        "\n".join(
            [
                "FECHA_CORTE|RUC_DNI|NOMBRE_RAZONODENOMINACIONSOCIAL|ORGANO_JURISDICCIONAL|NUMERO_RESOLUCION|FECHA_INICIO|FECHA_FIN",
                "20260401|10040039711|BARRETO MARCELO TEODORO|"
                "Corte Superior de Justicia de Pasco|SENTENCIA DE FECHA 28.04.2017|"
                "20170428|20250428",
                "20260401|1010900768|JOSE ANTONIO CORONADO HURTADO|Lima Norte|"
                "s/n de fecha 23.08.2018|20190214|20240214",
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
