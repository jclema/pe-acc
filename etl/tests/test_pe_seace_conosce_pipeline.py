from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from bracc_etl.pipelines.pe_seace_conosce import PeSeaceConoscePipeline

FIXTURES = Path(__file__).parent / "fixtures"


def _make_pipeline() -> PeSeaceConoscePipeline:
    driver = MagicMock()
    return PeSeaceConoscePipeline(driver=driver, data_dir=str(FIXTURES.parent))  # type: ignore[arg-type]


def _load_fixture_data(pipeline: PeSeaceConoscePipeline) -> None:
    pipeline._raw_rows = pd.read_csv(
        FIXTURES / "pe_seace_conosce_processes.csv",
        dtype=str,
        keep_default_na=False,
    )


def test_pipeline_metadata() -> None:
    assert PeSeaceConoscePipeline.name == "pe_seace_conosce"
    assert PeSeaceConoscePipeline.source_id == "seace_conosce"


def test_transform_builds_entities_processes_awards_and_providers() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    assert len(pipeline.entities) == 2
    assert len(pipeline.providers) == 2
    assert len(pipeline.processes) == 3
    assert len(pipeline.awards) == 3


def test_transform_parses_dates_and_normalizes_names() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    process = next(row for row in pipeline.processes if row["process_id"] == "PROC-002")
    assert process["call_date"] == "2026-02-15"
    assert process["title"] == process["title"].upper()


def test_transform_keeps_provider_linkage() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()

    rel = pipeline.award_provider_rels[0]
    assert rel["target_key"] == "20123456789"
    assert rel["source_key"] == "AWD-001"


def test_load_creates_procurement_relationships() -> None:
    pipeline = _make_pipeline()
    _load_fixture_data(pipeline)
    pipeline.transform()
    pipeline.load()

    session_mock = pipeline.driver.session.return_value.__enter__.return_value
    run_calls = session_mock.run.call_args_list
    assert any("MERGE (n:Entity" in str(call) for call in run_calls)
    assert any("MERGE (n:ProcurementProcess" in str(call) for call in run_calls)
    assert any("MERGE (n:Award" in str(call) for call in run_calls)
    assert any("MERGE (a)-[r:PUBLISHED]->(b)" in str(call) for call in run_calls)
    assert any("MERGE (a)-[r:HAS_AWARD]->(b)" in str(call) for call in run_calls)
    assert any("MERGE (a)-[r:WINNER]->(b)" in str(call) for call in run_calls)
