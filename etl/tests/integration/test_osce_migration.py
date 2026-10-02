from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from neo4j import GraphDatabase

from bracc_etl.osce_migration import DELETE_SCOPED, inspect_graph, inventory
from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline

Neo4jContainer = pytest.importorskip("testcontainers.neo4j").Neo4jContainer

if TYPE_CHECKING:
    from pathlib import Path


def docker(*args: str) -> None:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
def test_guarded_reload_preserves_protected_graph_and_is_idempotent(tmp_path: Path) -> None:
    raw = tmp_path / "raw/pe/osce_sanctions"
    raw.mkdir(parents=True)
    for name, delim in [("historico.csv", ","), ("judicial.csv", "|")]:
        (raw / name).write_text(
            delim.join(["ruc", "sanction_id", "provider_name"]) + "\n"
            + delim.join(["20123456789", "SHARED", "Uno"]) + "\n"
            + delim.join(["20654321987", "SHARED", "Dos"]) + "\n"
            + delim.join(["bad", "INVALID", "Rechazado"]) + "\n", encoding="latin-1",
        )
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    for directory in (backup, restored):
        directory.mkdir(mode=0o777)
        directory.chmod(0o777)
    try:
        with Neo4jContainer("neo4j:5-community").with_volume_mapping(
            str(backup), "/backups", "rw",
        ) as container, GraphDatabase.driver(
            container.get_connection_url(), auth=("neo4j", container.password),
        ) as driver:
            pipeline = PeOsceSanctionsPipeline(driver, data_dir=str(tmp_path))
            report, sanctions = inventory(raw, pipeline)
            assert report["distinct_ids"] == 4
            assert [f["valid"] for f in report["files"]] == [2, 2]
            assert [f["rejected"] for f in report["files"]] == [1, 1]
            with driver.session() as session:
                session.run("""
                    CREATE (a:Provider {ruc:'20123456789', source:'sunat', marker:'keep'}),
                      (b:Provider {ruc:'20654321987'}),
                      (s:Sanction {sanction_id:'SHARED',ruc:'20123456789',source:'osce_sanctions'}),
                      (a)-[:HAS_SANCTION {source:'osce_sanctions'}]->(s),
                      (b)-[:HAS_SANCTION {source:'osce_sanctions'}]->(s),
                      (n:Sanction {sanction_id:'NULL',source:'osce_sanctions'}),
                      (a)-[:HAS_SANCTION {source:'osce_sanctions'}]->(n),
                    (x:Sanction {sanction_id:'external',ruc:'20123456789',source:'osce_sanctions'}),
                      (a)-[:HAS_SANCTION]->(x),
                      (y:Sanction {sanction_id:'reverse',source:'osce_sanctions'}),
                      (y)-[:HAS_SANCTION {source:'osce_sanctions'}]->(a),
                      (:Sanction {sanction_id:'other',source:'other'}),
                    (:Sanction {sanction_id:'osce_sanctions:v1:protected',source:'osce_sanctions'})
                """).consume()
                graph_query = """MATCH (n) OPTIONAL MATCH (n)-[r]->(m)
                    RETURN labels(n), properties(n), type(r), properties(r), properties(m)
                    ORDER BY elementId(n), elementId(r)"""
                baseline = session.run(graph_query).data()
                before = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
                audit = inspect_graph(session, sanctions)
                assert session.run("MATCH (n) RETURN count(n) AS n").single()["n"] == before
                assert audit["legacy"] == 4 and len(audit["eligible"]) == 2
                assert len(audit["blocked"]) == 2
                assert audit["mismatched_links"] == 2 and audit["shared"] == 1
                assert len(audit["uncovered"]) == 3  # NULL and external rows lack coverage.
                scope = [row["element_id"] for row in audit["eligible"] if row["id"] == "SHARED"]
                # Even a mistakenly broad scope must preserve external/v1/other nodes.
                all_ids = [r["id"] for r in session.run("MATCH (n) RETURN elementId(n) AS id")]
            # Offline dump BEFORE maintenance, then restore into a different /data directory.
            wrapped = container.get_wrapped_container()
            wrapped.stop()
            docker("run", "--rm", "--volumes-from", wrapped.id, "neo4j:5-community",
                   "neo4j-admin", "database", "dump", "neo4j", "--to-path=/backups")
            wrapped.start()
            docker("run", "--rm", "-v", f"{backup}:/backups:ro", "-v", f"{restored}:/data",
                   "neo4j:5-community", "neo4j-admin", "database", "load", "neo4j",
                   "--from-path=/backups")
            with Neo4jContainer("neo4j:5-community").with_volume_mapping(
                str(restored), "/data", "rw",
            ) as recovery, GraphDatabase.driver(
                recovery.get_connection_url(), auth=("neo4j", recovery.password),
            ) as recovery_driver, recovery_driver.session() as recovery_session:
                restored_audit = inspect_graph(recovery_session, sanctions)
                assert restored_audit["legacy"] == 4
                assert restored_audit["mismatched_links"] == 2
                assert restored_audit["shared"] == 1
                assert recovery_session.run(graph_query).data() == baseline
            with GraphDatabase.driver(
                container.get_connection_url(), auth=("neo4j", container.password),
            ) as driver:
                pipeline.driver = driver
                driver.verify_connectivity()
                with driver.session() as session:
                    session.run(DELETE_SCOPED, ids=all_ids).consume()
                    assert session.run("MATCH (n) RETURN count(n) AS n").single()["n"] == before - 2
                    assert len(scope) == 1
                    assert session.run("MATCH (p:Provider) RETURN count(p) AS n").single()["n"] == 2
                pipeline.extract()
                pipeline.transform()
                # Reload sanctions/links only: preserve existing provider properties.
                pipeline.providers = []
                snapshots = []
                for _ in range(2):
                    pipeline.load()
                    with driver.session() as session:
                        audit = inspect_graph(session, sanctions)
                        assert audit["mismatched_links"] == 0 and audit["shared"] == 0
                        assert set(audit["v1_ids"]) == {*sanctions, "osce_sanctions:v1:protected"}
                        assert audit["legacy"] == 2 and len(audit["blocked"]) == 2
                        assert audit["eligible"] == []
                        assert session.run(
                            "MATCH (p:Provider {marker:'keep'}) RETURN p.source AS source",
                        ).single()["source"] == "sunat"
                        snapshots.append(session.run("""
                            MATCH (s:Sanction) WHERE s.sanction_id IN $ids
                            OPTIONAL MATCH (p:Provider)-[r:HAS_SANCTION]->(s)
                            RETURN properties(s) AS s, p.ruc AS ruc, properties(r) AS r
                            ORDER BY s.sanction_id, ruc
                        """, ids=list(sanctions)).data())
                assert len(snapshots[0]) == 4 and snapshots[0] == snapshots[1]
    finally:
        docker("run", "--rm", "--user", "0", "--entrypoint", "chown", "-v", f"{restored}:/data",
               "neo4j:5-community", "-R", f"{os.getuid()}:{os.getgid()}", "/data")
