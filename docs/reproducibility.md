# Reproducibility

## Quick Local Demo (Deterministic)

```bash
cp .env.example .env
make bootstrap-demo
```

Expected results:
- `http://localhost:8000/health` returns `{"status":"ok"}`.
- Neo4j Browser is available at `http://localhost:7474`.
- Demo graph seed is loaded via `infra/scripts/seed-dev.sh`.

## One-Script End-to-End Orchestration

```bash
# Demo profile
bash scripts/bootstrap_public_demo.sh --profile demo

# Full profile (orchestrates docker + ETL loop)
bash scripts/bootstrap_public_demo.sh --profile full --pipelines cnpj,tse,transparencia,sanctions --download

# Heavy one-command full ingestion (all implemented pipelines from contract)
make bootstrap-all

# Noninteractive heavy run (CI/automation)
make bootstrap-all-noninteractive
```

Notes:
- `full` profile runtime depends on external data source availability and your machine resources.
- Some pipelines require credentials, API keys, or source-specific access preconditions.
- `bootstrap-all` uses Dockerized ETL (no host `uv` required), prompts for reset by default, and writes run evidence to `audit-results/bootstrap-all/<UTC_STAMP>/summary.{json,md}`.
- `bootstrap-all` defaults to full historical attempts and can be very long-running.

## BYO-Data Ingestion

Para RNP, consultar el [contrato y verificación aislada de OSCE RNP](osce_rnp.md).

Use ETL directly:

```bash
cd etl
uv sync
uv run bracc-etl sources
uv run bracc-etl run --source cnpj --neo4j-password "$NEO4J_PASSWORD" --data-dir ../data
```

## OSCE sanction identity and existing data reload

Follow-up: [issue #2](https://github.com/jclema/pe-acc/issues/2).
The previous `sanction_id` was the resolution text. Different providers with the
same resolution could share one node and inherit another provider's properties.

The new identifier is `osce_sanctions:v1:<sha256>`. The digest covers the UTF-8
JSON array `[source_id, sanction_source, type, ruc, resolution_number]`, with
`ensure_ascii=False` and separators `(',', ':')`. RUC uses the existing document
normalization and resolution text is trimmed. The full digest is retained.
Source/type distinguishes tribunal and judicial records. The same components
produce the same ID across runs and row order; identical rows MERGE into the
same node. Provider name, URL, extraction date and filename are not identity
components (filenames still select the existing tribunal/judicial input format).
`resolution_number` retains the original trimmed resolution in Neo4j and the
normalized CSV. When present in input it takes precedence over `sanction_id`,
which remains supported as a legacy raw CSV column containing resolution text.

This changes existing node keys. It does not change constraints or automatically
delete old nodes. Running the new pipeline alone would leave legacy sanctions
and their relationships alongside the new nodes. Do not rename legacy nodes:
deduplication may already have discarded another provider's sanction properties.
Rebuild from the original complete raw source files, not from the old normalized
CSV or graph alone. Keep judicial filenames recognizable by `judicial`.

### Controlled reload

1. Before broader judicial ingestion, prepare the complete previously loaded
   OSCE input set and verify it with the corrected pipeline in an isolated graph.
2. Pause OSCE ingestion and public access during the maintenance window. Make a
   restorable database backup and retain the old code and raw inputs. Verify the
   restore procedure for that deployment before deleting any records.
3. In the intended Neo4j database, inspect legacy nodes and mismatched RUC links:

   ```cypher
   MATCH (s:Sanction)
   WHERE s.source = 'osce_sanctions'
     AND NOT (coalesce(s.sanction_id, '') STARTS WITH 'osce_sanctions:v1:')
   OPTIONAL MATCH (p:Provider)-[:HAS_SANCTION]->(s)
   RETURN count(DISTINCT s) AS legacy_nodes, count(p) AS links,
     sum(CASE WHEN p.ruc <> s.ruc THEN 1 ELSE 0 END) AS mismatched_links;
   ```

4. Inspect other references. If this query returns rows, stop and review those
   consumers before deleting their target nodes. Missing relationship provenance
   is also treated as an external reference:

   ```cypher
   MATCH (s:Sanction)-[r]-(n)
   WHERE s.source = 'osce_sanctions'
     AND NOT (coalesce(s.sanction_id, '') STARTS WITH 'osce_sanctions:v1:')
     AND (type(r) <> 'HAS_SANCTION'
       OR coalesce(r.source, '') <> 'osce_sanctions' OR NOT n:Provider)
   RETURN s.sanction_id, type(r), labels(n), r.source;
   ```

5. After backup and review, remove only legacy OSCE sanction nodes and their
   links. This is a destructive maintenance step; Providers, other sources and
   new versioned sanction nodes remain. The guard preserves external references:

   ```cypher
   MATCH (s:Sanction)
   WHERE s.source = 'osce_sanctions'
     AND NOT (coalesce(s.sanction_id, '') STARTS WITH 'osce_sanctions:v1:')
     AND NOT EXISTS {
       MATCH (s)-[r]-(n)
       WHERE type(r) <> 'HAS_SANCTION'
         OR coalesce(r.source, '') <> 'osce_sanctions' OR NOT n:Provider
     }
   DETACH DELETE s;
   ```

6. Repeat step 3; legacy_nodes must be zero. Reload all raw inputs without
   `--limit`, using the corrected code and the intended URI/database:

   ```bash
   cd etl
   uv run bracc-etl run --source pe_osce_sanctions \
     --neo4j-uri bolt://localhost:7687 --neo4j-database neo4j \
     --neo4j-password "$NEO4J_PASSWORD" --data-dir ../data
   ```

7. Check each `Provider -> HAS_SANCTION -> Sanction` RUC matches, resolution and
   source link remain visible, and graph counts match the distinct identity
   tuples in the validated input. Load the same inputs again: node/relationship
   counts and identifiers must stay unchanged. Run step 3 again (zero legacy
   nodes and mismatched legacy links). Reopen public access only after validation.

   ```cypher
   MATCH (p:Provider)-[:HAS_SANCTION]->(s:Sanction)
   WHERE s.source = 'osce_sanctions'
   RETURN count(*) AS links,
     sum(CASE WHEN p.ruc = s.ruc THEN 0 ELSE 1 END) AS mismatched_links;
   ```

   `mismatched_links` must be zero, including newly versioned sanctions.

Existing Neo4j element IDs and saved graph links may change during reload.
Rollback after data maintenance requires restoring the backup together with the
old code; reverting code alone does not restore old keys or relationships.

## What This Does Not Reproduce Automatically

- Production-scale graph counters (see `docs/reference_metrics.md` for reference production snapshot).
- Guaranteed success for every external source in every run (blocked/failing sources are explicitly reported).
- Private/institutional modules outside public boundary.
