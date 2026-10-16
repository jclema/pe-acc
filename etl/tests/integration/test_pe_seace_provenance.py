import json
from pathlib import Path

import pandas as pd
import pytest

from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline
from bracc_etl.pipelines.pe_seace_conosce import PeSeaceConoscePipeline
from bracc_etl.pipelines.pe_sunat_ruc import PeSunatRucPipeline


@pytest.mark.integration
def test_official_awards_reach_graph_without_duplicate_item_amounts(
    neo4j_driver, tmp_path, monkeypatch,
):
    from tests.test_seace_acquisition import official_input

    def mutate(rows):
        for row in rows:
            row["CODIGOCONVOCATORIA"] = "900001"
    official_input(tmp_path, monkeypatch, mutate)
    pipeline = PeSeaceConoscePipeline(neo4j_driver, str(tmp_path))
    pipeline.extract()
    pipeline.transform()
    for _ in range(2):
        pipeline.load()
    with neo4j_driver.session() as session:
        rows = session.run(
            "MATCH (:Entity)-[:PUBLISHED]->(:ProcurementProcess {process_id:'SEACE-900001'})"
            "-[:HAS_AWARD]->(a:Award)-[:WINNER]->(p:Provider) "
            "RETURN a.amount AS amount, a.currency AS currency, a.source_row AS row, "
            "p.ruc AS ruc ORDER BY row",
        ).data()
    assert rows == [
        {"amount": 100, "currency": "PEN", "row": "2", "ruc": "20999999991"},
        {"amount": 200, "currency": "PEN", "row": "3", "ruc": "20999999992"},
    ]


@pytest.mark.integration
@pytest.mark.parametrize("reverse", [False, True])
def test_seace_keeps_identity_all_observations_and_procurement_links(neo4j_driver, reverse):
    seace = PeSeaceConoscePipeline(neo4j_driver, chunk_size=1)
    seace._raw_rows = pd.read_csv(
        Path(__file__).parents[1] / "fixtures/pe_seace_conosce_processes.csv",
        dtype=str, keep_default_na=False,
    )
    # Isolate each order from other tests in the disposable graph.
    ruc = f"209977770{11 + int(reverse):02d}"
    for column in ("entity_id", "process_id", "award_id"):
        seace._raw_rows[column] += f"-order-{reverse}"
    seace._raw_rows = seace._raw_rows[seace._raw_rows.provider_ruc == "20123456789"].copy()
    seace._raw_rows["provider_ruc"] = ruc
    seace.transform()
    sunat = PeSunatRucPipeline(neo4j_driver)
    sunat._raw_providers = pd.DataFrame([{
        "ruc": ruc, "legal_name": "IDENTIDAD SUNAT", "trade_name": "MARCA SUNAT",
        "source_url": "https://example.test/sunat", "extraction_date": "2026-01-01",
    }])
    sunat.transform()
    osce = PeOsceSanctionsPipeline(neo4j_driver)
    osce._raw_sanctions = pd.DataFrame([{
        "ruc": ruc, "provider_name": "DECLARADO OSCE", "sanction_id": "SEACE-TEST",
        "source_url": "https://example.test/osce", "extraction_date": "2026-02-01",
    }])
    osce.transform()
    ordered = [seace, osce, sunat] if reverse else [sunat, osce, seace]
    previous = None
    for _ in range(2):
        for pipeline in ordered:
            pipeline.load()
        with neo4j_driver.session() as session:
            props = session.run("MATCH (p:Provider {ruc:$ruc}) RETURN properties(p) AS p",
                                ruc=ruc).single()["p"]
            paths = session.run(
                "MATCH (e:Entity)-[:PUBLISHED]->(p:ProcurementProcess)-[:HAS_AWARD]->"
                "(a:Award)-[:WINNER]->(:Provider {ruc:$ruc}) "
                "RETURN e.entity_id AS entity, p.process_id AS process, a.award_id AS award, "
                "a.amount AS amount ORDER BY award", ruc=ruc,
            ).data()
            sanctions = session.run(
                "MATCH (:Provider {ruc:$ruc})-[:HAS_SANCTION]->(s:Sanction) "
                "RETURN s.ruc AS ruc", ruc=ruc,
            ).data()
        assert props["legal_name"] == props["name"] == "IDENTIDAD SUNAT"
        assert props["trade_name"] == "MARCA SUNAT" and props["source"] == "sunat_ruc"
        assert props["sources"] == ["osce_sanctions", "seace_conosce", "sunat_ruc"]
        records = [json.loads(value) for value in props["provider_source_records"]]
        evidence = [row for row in records if row["source"] == "seace_conosce"]
        assert {row["source_url"] for row in evidence} == {
            "https://example.gob.pe/seace/1", "https://example.gob.pe/seace/3",
        }
        assert all(row["source_dataset"] == "processes.csv" for row in evidence)
        assert all(row["extraction_date"] == "2026-04-01" for row in evidence)
        assert json.loads(props["provider_field_sources"])["legal_name"]["source"] == "sunat_ruc"
        assert sanctions == [{"ruc": ruc}]
        assert [path["amount"] for path in paths] == [2500000, 1800000]
        snapshot = props, paths, sanctions
        if previous is not None:
            assert snapshot == previous
        previous = snapshot
