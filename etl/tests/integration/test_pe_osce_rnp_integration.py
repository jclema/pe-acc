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
        assert providers[0]["props"] == {
            "ruc": "20999999991",
            "name": "PREEXISTENTE",
            "legal_name": "NOMBRE SUNAT",
            "source": "sunat_ruc",
            "source_url": "https://example.test/sunat",
        }
        assert providers[1]["props"]["name"] == "ENTIDAD SINTETICA B"
        snapshot = (links, providers)
        if previous is not None:
            assert snapshot == previous
        previous = snapshot
