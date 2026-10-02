from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bracc_etl.osce_migration import inventory
from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline


def test_inventory_requires_original_rows_and_never_writes_normalized(tmp_path: Path) -> None:
    pipeline = PeOsceSanctionsPipeline(MagicMock(), data_dir=str(tmp_path))
    with pytest.raises(ValueError, match="No original"):
        inventory(tmp_path, pipeline)
    raw = tmp_path / "judicial.csv"
    raw.write_text("ruc|sanction_id\n20123456789|RES\n20123456789|RES\n", encoding="latin-1")
    report, sanctions = inventory(tmp_path, pipeline)
    assert report["distinct_ids"] == 1
    assert report["files"][0]["valid"] == 2
    assert report["files"][0]["rejected"] == 0
    assert report["files"][0]["cutoffs"] == [""]
    assert next(iter(sanctions.values()))["sanction_source"] == "PODER_JUDICIAL"
    assert not (tmp_path / "normalized").exists()
    raw.write_text("ruc|sanction_id\nbad|RES\n", encoding="latin-1")
    with pytest.raises(ValueError, match="no valid"):
        inventory(tmp_path, pipeline)
