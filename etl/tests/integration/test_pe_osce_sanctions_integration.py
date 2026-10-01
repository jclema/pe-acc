from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline

if TYPE_CHECKING:
    from neo4j import Driver


@pytest.mark.integration
def test_osce_collision_and_repeated_load_keep_correct_graph(neo4j_driver: Driver) -> None:
    """Verify MERGE writes two sanctions and never crosses provider provenance."""
    rows = [
        {"ruc": ruc, "provider_name": name,
         "sanction_id": "SENTENCIA DE FECHA 01.01.2020",
         "source_url": f"https://example.gob.pe/osce/{ruc}"}
        for ruc, name in [("20123456789", "Proveedor Uno"), ("20654321987", "Proveedor Dos")]
    ]
    expected_ids: set[str] = set()
    for ordered_rows in (rows, list(reversed(rows)) + [rows[0]]):
        pipeline = PeOsceSanctionsPipeline(driver=neo4j_driver)
        pipeline._raw_sanctions = pd.DataFrame(ordered_rows)
        pipeline.transform()
        pipeline.load()
        ids = {row["sanction_id"] for row in pipeline.sanctions}
        assert len(ids) == 2
        if expected_ids:
            assert ids == expected_ids
        expected_ids = ids

        with neo4j_driver.session() as session:
            links = session.run(
                "MATCH (p:Provider)-[r:HAS_SANCTION]->(s:Sanction) "
                "WHERE s.sanction_id IN $ids "
                "RETURN p.ruc AS provider_ruc, s.ruc AS sanction_ruc, "
                "s.provider_name AS name, s.source_url AS url, "
                "s.resolution_number AS resolution",
                ids=list(ids),
            ).data()
            count = session.run(
                "MATCH (s:Sanction) WHERE s.sanction_id IN $ids RETURN count(s) AS total",
                ids=list(ids),
            ).single()
        assert count is not None and count["total"] == 2
        assert len(links) == 2
        originals = {row["ruc"]: row for row in rows}
        for link in links:
            original = originals[link["provider_ruc"]]
            assert link["provider_ruc"] == link["sanction_ruc"]
            assert link["name"] == original["provider_name"].upper()
            assert link["url"] == original["source_url"]
            assert link["resolution"] == original["sanction_id"]
