from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
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


@pytest.mark.integration
def test_api_download_repeated_load_is_idempotent(neo4j_driver, tmp_path, monkeypatch):
    names = ("sancionados.csv", "inhabilitaciones_judiciales.csv")
    def handler(request):
        if request.url.path.endswith("/attachment"):
            return httpx.Response(200, json={"results": [
                {"title": name, "_links": {"download": f"/download/{name}"}}
                for name in names], "_links": {}})
        return httpx.Response(200, content=b"RUC,NUMERO_RESOLUCION\n20987654321,API-DEMO\n")
    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: client(
        transport=httpx.MockTransport(handler), **kw))
    p = PeOsceSanctionsPipeline(neo4j_driver, data_dir=str(tmp_path), source_mode="api")
    for _ in range(2):
        p.extract()
        p.transform()
        p.load()
        with neo4j_driver.session() as session:
            rows = session.run(
                "MATCH (p:Provider {ruc: '20987654321'})-[:HAS_SANCTION]->(s:Sanction) "
                "WHERE s.resolution_number = 'API-DEMO' "
                "RETURN s.ruc AS ruc, s.sanction_source AS source, s.source_url AS url",
            ).data()
        assert len(rows) == 2
        assert {row["source"] for row in rows} == {"OSCE_TCP", "PODER_JUDICIAL"}
        assert all(row["ruc"] == "20987654321" and row["url"] for row in rows)


@pytest.mark.integration
def test_official_api_real_data_load_is_idempotent(neo4j_driver, tmp_path):
    import json
    import os

    if os.getenv('PE_OSCE_LIVE_TEST') != '1':
        pytest.skip('Opt-in real API test: PE_OSCE_LIVE_TEST=1')
    p = PeOsceSanctionsPipeline(neo4j_driver, data_dir=str(tmp_path), source_mode='api')
    p.extract()
    assert p.extraction_status['mode'] == 'api', 'Live test must not accept a fallback'
    p.transform()
    assert p.sanctions and len(p.raw_files) == 2
    ids = [s['sanction_id'] for s in p.sanctions]
    previous = None
    for _ in range(2):
        p.load()
        with neo4j_driver.session() as session:
            links = session.run(
                'MATCH (p:Provider)-[r:HAS_SANCTION]->(s:Sanction) '
                'WHERE s.sanction_id IN $ids '
                'RETURN p.ruc AS provider, s.ruc AS ruc, s.sanction_id AS id, '
                's.source_url AS url, r.source AS source ORDER BY id, provider', ids=ids,
            ).data()
            count = session.run(
                'MATCH (s:Sanction) WHERE s.sanction_id IN $ids RETURN count(s) AS n', ids=ids,
            ).single()['n']
        assert count == len(ids) and len(links) == len(ids)
        assert all(row['provider'] == row['ruc'] and row['url'] for row in links)
        if previous is not None:
            assert links == previous
        previous = links
    manifest = json.loads((p.raw_files[0].parent / 'manifest.json').read_text())
    print(json.dumps({'rows_in': p.rows_in, 'providers': len(p.providers),
                      'sanctions': len(ids), 'links': len(links), 'manifest': manifest}))
