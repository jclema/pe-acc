from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from bracc_etl.pipelines.pe_osce_rnp import FILES, SOURCE_URL, PeOsceRnpPipeline

if TYPE_CHECKING:
    from neo4j import Driver

FIXTURES = Path(__file__).parents[1] / "fixtures" / "pe_osce_rnp"


@pytest.mark.integration
def test_rnp_preserves_providers_and_idempotent_links(neo4j_driver: Driver) -> None:
    with neo4j_driver.session() as session:
        session.run(
            "CREATE (p:Provider {ruc:'20999999991', name:'PREEXISTENTE', "
            "legal_name:'NOMBRE SUNAT', source:'sunat_ruc', "
            "source_url:'https://example.test/sunat'}) "
            "CREATE (p)-[:HAS_SANCTION {source:'osce_sanctions'}]->"
            "(:Sanction {sanction_id:'rnp-synthetic-existing'}) "
            "CREATE (:Provider {ruc:'20999999992'})",
        ).consume()
    expected = {
        ("00000001", "20999999991", "SOCIO_DE", ""),
        ("20999999992", "20999999991", "SOCIO_DE", ""),
        ("00000002", "20999999992", "REPRESENTA_A", ""),
        ("10999999991", "20999999991", "REPRESENTA_A", ""),
        ("00000001", "20999999992", "MIEMBRO_ORGANO_DE", "DIRECTOR"),
        ("00000001", "20999999992", "MIEMBRO_ORGANO_DE", "GERENTE"),
    }
    previous = None
    for filenames in (list(FILES), list(reversed(FILES))):
        pipeline = PeOsceRnpPipeline(neo4j_driver, chunk_size=1)
        pipeline.raw_files = [FIXTURES / filename for filename in filenames]
        pipeline.transform()
        pipeline.records.reverse()
        pipeline.load()
        with neo4j_driver.session() as session:
            links = session.run(
                "MATCH (a)-[r]->(p:Provider) WHERE r.source='osce_rnp' "
                "RETURN coalesce(a.dni,a.ruc) AS document, p.ruc AS target, "
                "type(r) AS type, properties(r) AS props, labels(a) AS labels "
                "ORDER BY r.record_id",
            ).data()
            query = Path(__file__).parents[3] / "api/src/bracc/queries/public_graph_provider.cypher"
            public = session.run(
                query.read_text(), provider_id="", provider_identifier="20999999991", depth=2
            ).single()
            assert public is not None and all("Person" not in n.labels for n in public["nodes"])
            assert len(public["relationships"]) == 2  # corporate RNP link and prior sanction
            providers = session.run(
                "MATCH (p:Provider) WHERE p.ruc IN ['20999999991','20999999992'] "
                "RETURN properties(p) AS props ORDER BY p.ruc",
            ).data()
            assert (
                session.run(
                    "MATCH (:Provider {ruc:'20999999991'})-[:HAS_SANCTION]->"
                    "(:Sanction {sanction_id:'rnp-synthetic-existing'}) RETURN count(*) AS n",
                ).single()["n"]
                == 1
            )
        assert len(links) == pipeline.rows_loaded == 6
        assert {
            (r["document"], r["target"], r["type"], r["props"]["cargo"]) for r in links
        } == expected
        for link in links:
            props = link["props"]
            assert props["source_url"] == SOURCE_URL and len(props["file_sha256"]) == 64
            assert props["source_dataset"] in FILES and props["declared_name"]
            assert ("Person" in link["labels"]) == (link["document"] != "20999999992")
        assert providers[0]["props"].items() >= {
            "ruc": "20999999991",
            "name": "NOMBRE SUNAT",
            "legal_name": "NOMBRE SUNAT",
            "source": "sunat_ruc",
            "source_url": "https://example.test/sunat",
        }.items()
        assert providers[1]["props"]["name"] == "ENTIDAD SINTETICA B"
        snapshot = (links, providers)
        if previous is not None:
            assert snapshot == previous
        previous = snapshot


@pytest.mark.integration
@pytest.mark.parametrize("reverse", [False, True])
def test_rnp_keeps_sunat_osce_identity_and_evidence(neo4j_driver, tmp_path, reverse):
    import json

    import pandas as pd

    from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline
    from bracc_etl.pipelines.pe_sunat_ruc import PeSunatRucPipeline

    target, corporate = (f"209988880{n + 10 * int(reverse):02d}" for n in (11, 12))
    raw = tmp_path / "raw/pe/osce_rnp"
    raw.mkdir(parents=True)
    for filename in FILES:
        content = (FIXTURES / filename).read_text()
        content = content.replace("20999999991", target).replace("20999999992", corporate)
        (raw / filename).write_text(content, encoding="cp1252")
    rnp = PeOsceRnpPipeline(neo4j_driver, data_dir=str(tmp_path), chunk_size=1)
    rnp.extract()
    rnp.transform()
    sunat = PeSunatRucPipeline(neo4j_driver)
    sunat._raw_providers = pd.DataFrame([
        {"ruc": ruc, "legal_name": "IDENTIDAD SUNAT", "tax_status": "ACTIVO",
         "source_url": "https://example.test/sunat", "extraction_date": "2026-09-01"}
        for ruc in (target, corporate)
    ])
    sunat.transform()
    osce = PeOsceSanctionsPipeline(neo4j_driver)
    osce._raw_sanctions = pd.DataFrame([
        {"ruc": ruc, "provider_name": "DECLARADO OSCE", "sanction_id": "RNP-TEST",
         "source_url": "https://example.test/osce", "extraction_date": "2026-10-01"}
        for ruc in (target, corporate)
    ])
    osce.transform()
    ordered = [rnp, osce, sunat] if reverse else [sunat, osce, rnp]
    previous = None
    for _ in range(2):
        for pipeline in ordered:
            pipeline.load()
        with neo4j_driver.session() as session:
            providers = session.run(
                "MATCH (p:Provider) WHERE p.ruc IN $rucs "
                "RETURN properties(p) AS p ORDER BY p.ruc", rucs=[target, corporate],
            ).data()
            sanctions = session.run(
                "MATCH (p:Provider)-[:HAS_SANCTION]->(s:Sanction) WHERE p.ruc IN $rucs "
                "RETURN p.ruc AS provider, s.ruc AS sanctioned ORDER BY p.ruc",
                rucs=[target, corporate],
            ).data()
            links = session.run(
                "MATCH (a)-[r]->(p:Provider) WHERE p.ruc IN $rucs AND r.source='osce_rnp' "
                "RETURN r.record_id AS id, properties(r) AS r ORDER BY id",
                rucs=[target, corporate],
            ).data()
        assert len(providers) == len(sanctions) == 2 and len(links) == 6
        assert all(row["provider"] == row["sanctioned"] for row in sanctions)
        for entry in providers:
            props = entry["p"]
            assert props["legal_name"] == props["name"] == "IDENTIDAD SUNAT"
            assert props["source"] == "sunat_ruc" and props["tax_status"] == "ACTIVO"
            assert props["sources"] == ["osce_rnp", "osce_sanctions", "sunat_ruc"]
            records = [json.loads(value) for value in props["provider_source_records"]]
            evidence = [row for row in records if row["source"] == "osce_rnp"]
            assert evidence and all(row["source_url"] == SOURCE_URL for row in evidence)
            assert all(len(row["file_sha256"]) == 64 for row in evidence)
            assert all("extraction_date" not in row for row in evidence)
            if props["ruc"] == target:
                assert all("name" not in row and "legal_name" not in row for row in evidence)
            else:
                assert any(row.get("name") == "ENTIDAD SINTETICA B" for row in evidence)
            fields = json.loads(props["provider_field_sources"])
            assert fields["legal_name"]["source"] == "sunat_ruc"
        snapshot = providers, sanctions, links
        if previous is not None:
            assert snapshot == previous
        previous = snapshot
