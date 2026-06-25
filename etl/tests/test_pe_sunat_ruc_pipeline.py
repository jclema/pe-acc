from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from bracc_etl.pipelines.pe_sunat_ruc import PeSunatRucPipeline

FIXTURES = Path(__file__).parent / "fixtures"


def _make_pipeline() -> PeSunatRucPipeline:
    driver = MagicMock()
    return PeSunatRucPipeline(driver=driver, data_dir=str(FIXTURES.parent))  # type: ignore[arg-type]


def _load_fixture_data(pipeline: PeSunatRucPipeline) -> None:
    pipeline._raw_providers = pd.read_csv(
        FIXTURES / "pe_sunat_ruc_providers.csv",
        dtype=str,
        keep_default_na=False,
    )


def test_pipeline_metadata() -> None:
    assert PeSunatRucPipeline.name == "pe_sunat_ruc"
    assert PeSunatRucPipeline.source_id == "sunat_ruc"


def test_transform_filters_invalid_ruc() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    assert len(pipeline.providers) == 2
    assert {row["ruc"] for row in pipeline.providers} == {"20123456789", "20654321987"}


def test_transform_normalizes_names() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    provider = pipeline.providers[0]
    assert provider["legal_name"] == provider["legal_name"].upper()
    assert "Á" not in provider["legal_name"]


def test_transform_parses_extraction_date() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    dates = {row["extraction_date"] for row in pipeline.providers}
    assert "2026-04-01" in dates


def test_transform_maps_real_sunat_columns() -> None:
    pipeline = _make_pipeline()
    pipeline._raw_providers = pd.DataFrame(
        [
            {
                "RUC": "10000000146",
                "Estado": "ACTIVO",
                "Condicion": "HABIDO",
                "Tipo": "PERSONA NATURAL SIN NEGOCIO",
                "Actividad_Economica_CIIU_revision3_Principal": "ACTIVIDADES JURIDICAS",
                "Actividad_Economica_CIIU_revision3_Secundaria": "NO DISPONIBLE",
                "Actividad_Economica_CIIU_revision4_Principal": "ACTIVIDADES JURIDICAS",
                "NroTrab": "NO DISPONIBLE",
                "TipoFacturacion": "MANUAL",
                "TipoContabilidad": "MANUAL",
                "ComercioExterior": "SIN ACTIVIDAD",
                "UBIGEO": "250101",
                "Departamento": "UCAYALI",
                "Provincia": "CORONEL PORTILLO",
                "Distrito": "CALLERIA",
                "PERIODO_PUBLICACION": "202603",
            },
        ],
    )

    pipeline.transform()

    assert len(pipeline.providers) == 1
    provider = pipeline.providers[0]
    assert provider["ruc"] == "10000000146"
    assert provider["legal_name"] == "RUC 10000000146"
    assert provider["provider_type"] == "PERSONA NATURAL SIN NEGOCIO"
    assert provider["tax_status"] == "ACTIVO"
    assert provider["tax_condition"] == "HABIDO"
    assert provider["ubigeo"] == "250101"
    assert provider["extraction_date"] == "2026-03-01"


def test_transform_raw_csv_writes_normalized_output(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "pe" / "sunat_ruc"
    raw_dir.mkdir(parents=True)
    raw_csv = raw_dir / "PadronRUC_202603.csv"
    raw_csv.write_text(
        "\n".join(
            [
                "RUC,Estado,Condicion,Tipo,Actividad_Economica_CIIU_revision3_Principal,Actividad_Economica_CIIU_revision3_Secundaria,Actividad_Economica_CIIU_revision4_Principal,NroTrab,TipoFacturacion,TipoContabilidad,ComercioExterior,UBIGEO,Departamento,Provincia,Distrito,PERIODO_PUBLICACION",
                "10000000065,ACTIVO,HABIDO,PERSONA NATURAL SIN NEGOCIO,OTRAS ACTIVIDADES,NO DISPONIBLE,NO DISPONIBLE,NO DISPONIBLE,MANUAL,MANUAL,SIN ACTIVIDAD,250101,UCAYALI,CORONEL PORTILLO,CALLERIA,202603",
                "10000000065,ACTIVO,HABIDO,PERSONA NATURAL SIN NEGOCIO,OTRAS ACTIVIDADES,NO DISPONIBLE,NO DISPONIBLE,NO DISPONIBLE,MANUAL,MANUAL,SIN ACTIVIDAD,250101,UCAYALI,CORONEL PORTILLO,CALLERIA,202603",
                "10000000146,ACTIVO,HABIDO,PERSONA NATURAL SIN NEGOCIO,ACTIVIDADES JURIDICAS,NO DISPONIBLE,ACTIVIDADES JURIDICAS,NO DISPONIBLE,MANUAL,MANUAL,SIN ACTIVIDAD,250101,UCAYALI,CORONEL PORTILLO,CALLERIA,202603",
            ],
        ),
        encoding="latin-1",
    )

    driver = MagicMock()
    pipeline = PeSunatRucPipeline(driver=driver, data_dir=str(tmp_path))  # type: ignore[arg-type]
    pipeline.extract()
    pipeline.transform()

    assert pipeline.normalized_csv_path is not None
    assert pipeline.normalized_csv_path.exists()
    assert pipeline.rows_loaded == 2

    with pipeline.normalized_csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["ruc"] == "10000000065"
    assert rows[0]["source_dataset"] == "PadronRUC_202603.csv"
    assert rows[0]["extraction_date"] == "2026-03-01"


def test_load_creates_provider_nodes() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()
    pipeline.load()

    session_mock = pipeline.driver.session.return_value.__enter__.return_value
    run_calls = session_mock.run.call_args_list
    provider_calls = [call for call in run_calls if "MERGE (n:Provider" in str(call)]
    assert provider_calls, "Expected Provider MERGE calls"
