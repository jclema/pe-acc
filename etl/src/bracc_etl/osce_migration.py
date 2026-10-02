"""Read-only OSCE migration inventory; deletion requires separately approved maintenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neo4j import GraphDatabase

from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline

if TYPE_CHECKING:
    from neo4j import Session

LEGACY = "s.source = 'osce_sanctions' AND NOT coalesce(s.sanction_id,'') " \
         "STARTS WITH 'osce_sanctions:v1:'"
EXTERNAL = """EXISTS {
    MATCH (s)-[r]-(n)
    WHERE type(r) <> 'HAS_SANCTION' OR coalesce(r.source,'') <> 'osce_sanctions'
      OR NOT n:Provider OR startNode(r) <> n OR endNode(r) <> s
}"""
DELETE_SCOPED = f"""MATCH (s:Sanction) WHERE elementId(s) IN $ids
    AND {LEGACY} AND NOT {EXTERNAL} DETACH DELETE s"""


def inventory(
    raw_dir: Path, pipeline: PeOsceSanctionsPipeline,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Use the actual parser/identity contract, without normalized output or DB writes."""
    files = sorted(p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    if not files:
        raise ValueError("No original raw CSV files")
    sanctions: dict[str, dict[str, Any]] = {}
    evidence = []
    for path in files:
        content = path.read_bytes()
        frame = pipeline._read_raw_csv(path)
        valid = 0
        ids = set()
        cutoffs = set()
        urls = set()
        for idx, row in frame.iterrows():
            _, sanction, _ = pipeline._normalize_sanction_row(
                {str(k): v for k, v in row.to_dict().items()}, idx,
                source_kind=pipeline._source_kind_for_file(path.name),
                source_file=path.name,
            )
            if sanction is None:
                continue
            valid += 1
            key = sanction["sanction_id"]
            ids.add(key)
            cutoffs.add(sanction["extraction_date"])
            urls.add(sanction["source_url"])
            sanctions[key] = sanction
        if not valid:
            raise ValueError(f"{path}: no valid rows")
        evidence.append({
            "file": path.name, "sha256": hashlib.sha256(content).hexdigest(),
            "encoding": "latin-1", "delimiter": max((",", "|"), key=lambda d:
                content.splitlines()[0].count(d.encode())),
            "rows": len(frame), "valid": valid, "rejected": len(frame) - valid,
            "distinct_ids": len(ids), "cutoffs": sorted(cutoffs), "sources": sorted(urls),
        })
    return {"files": evidence, "distinct_ids": len(sanctions)}, sanctions


def inspect_graph(session: Session, sanctions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return complete legacy scope and coverage candidates; never certify raw completeness."""
    legacy = session.run(f"""
        MATCH (s:Sanction) WHERE {LEGACY}
        OPTIONAL MATCH (p:Provider)-[:HAS_SANCTION]->(s)
        RETURN elementId(s) AS element_id, s.sanction_id AS id,
          coalesce(s.resolution_number,s.sanction_id) AS resolution,
          s.ruc AS ruc, collect(DISTINCT p.ruc) AS provider_rucs, {EXTERNAL} AS blocked
        ORDER BY element_id
    """).data()
    tuples = {(s["ruc"], s["resolution_number"]) for s in sanctions.values()}
    uncovered = [r["element_id"] for r in legacy if
                 not r["ruc"] or (r["ruc"], r["resolution"]) not in tuples
                 or any((ruc, r["resolution"]) not in tuples for ruc in r["provider_rucs"])]
    integrity = session.run("""
        MATCH (p:Provider)-[:HAS_SANCTION]->(s:Sanction) WHERE s.source='osce_sanctions'
        RETURN sum(CASE WHEN p.ruc IS NOT NULL AND s.ruc IS NOT NULL AND p.ruc=s.ruc
                   THEN 0 ELSE 1 END) AS mismatched_links
    """).single()
    shared = session.run("""
        MATCH (p:Provider)-[:HAS_SANCTION]->(s:Sanction) WHERE s.source='osce_sanctions'
        WITH s, count(DISTINCT p) AS rucs WHERE rucs > 1 RETURN count(s) AS n
    """).single()
    ids = session.run("""
        MATCH (s:Sanction) WHERE s.source='osce_sanctions'
          AND s.sanction_id STARTS WITH 'osce_sanctions:v1:'
        RETURN s.sanction_id AS id ORDER BY id
    """).value()
    return {"legacy": len(legacy), "eligible": [r for r in legacy if not r["blocked"]],
            "blocked": [r for r in legacy if r["blocked"]], "uncovered": uncovered,
            "mismatched_links": integrity["mismatched_links"] if integrity else 0,
            "shared": shared["n"] if shared else 0, "v1_ids": ids,
            "missing_input_ids": sorted(set(sanctions) - set(ids)),
            "unexpected_v1_ids": sorted(set(ids) - set(sanctions))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", default="neo4j")
    args = parser.parse_args()
    with GraphDatabase.driver(args.uri, auth=(args.user, os.environ["NEO4J_PASSWORD"])) as driver:
        report, sanctions = inventory(args.raw_dir, PeOsceSanctionsPipeline(driver))
        with driver.session(database=args.database, default_access_mode="READ") as session:
            report["graph"] = inspect_graph(session, sanctions)
        report["target"] = {"uri": args.uri, "database": args.database}
        report["raw_completeness"] = "requires operator attestation and load history"
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
