# OSCE legacy migration: preparation and approval boundary

Status: preparation only. No user or production database has been migrated.
PR #17 (quality/dependencies) must be integrated before release; this change is
stacked on `fix/restore-green-ci` (#17). PR #6 must not load real data before approval.

## Inventory and read-only preflight

Obtain ALL previously loaded original CSVs, including historical, judicial and
variant files, plus load history. Keep judicial filenames recognizable. Do not
reconstruct missing inputs from collided nodes or normalized output. The operator
must attest completeness; a match to remaining graph tuples cannot prove it.
Record each file's origin URL, cutoff, license, limitations and load state in a
private operator manifest. Missing cutoff/source metadata requires investigation.
Store raw inputs, dumps and reports outside Git with restricted access; reports
contain RUCs and internal node IDs and are not intended for public publication.

```bash
cd etl
uv run python -m bracc_etl.osce_migration --raw-dir "$OSCE_RAW_DIR" \
  --uri "$OSCE_URI" --database "$OSCE_DATABASE" > "$OSCE_REPORT"
```

Password comes from `NEO4J_PASSWORD`; use a read-only account where available.
The command reads every CSV in the specified directory using the corrected
pipeline parser, produces no normalized files and performs no database writes.
It reports SHA256, delimiter/encoding, valid/rejected rows, distinct identities,
cutoffs/source URLs and the complete legacy scope, protected references, crossed
links (including NULL RUC), shared sanctions and missing/unexpected v1 IDs.
Coverage by `(RUC,resolution)` is necessary, not sufficient: legacy source/type
may have been overwritten. Inspect every unmatched row and rejected input;
never interpret a nonempty report or exit code 0 as permission to delete.

## Rehearsal and backup/rollback

```bash
cd etl
uv run --extra dev pytest tests/integration/test_osce_migration.py -m integration -q
```

This test creates two independent Docker Neo4j data stores. It creates synthetic
legacy collisions, NULL RUC, missing relationship provenance, a reverse link,
another source and a protected v1 node. It audits without mutation, stops only
its own source container, dumps it offline, restores into a separate store,
checks the original anomalies survived restore, tests scoped deletion and loads
all fixture files twice without a limit. Provider properties are preserved.
Run the same rehearsal against a verified restore of the real backup and complete
input set before requesting execution. Synthetic success is not a real restore.

For the actual deployment, record image digest/version, DB name, store mounts,
code SHA, backup filename/SHA256 and all baseline counts. Stop ingestion/public
access for the approved maintenance window. Stop only the identified DB service;
run `neo4j-admin database dump <database> --to-path=<backup-directory>` with its
store mounted and the matching image. Load that dump into a NEW empty isolated
store using `neo4j-admin database load <database> --from-path=<backup-directory>`.
Never overwrite the user store during a restore test. Verify counts, properties,
relationships, IDs and provenance against the baseline, not just dump exit status.
Real service/mount details and backup `pe-acc-pre-rnp-20261001` remain unverified.

## Human approval and controlled operation

Present the exact target URI/database, code SHA, input manifest, maintenance
window, restored backup evidence, expected before/after counts and explicit
legacy element IDs for approval. Resolve uncovered rows, rejected inputs,
protected references and unexpected v1 IDs first. Approved exclusions must remain
visible; protected legacy means the complete migration is still incomplete.
Re-read the graph under maintenance immediately before executing. Element IDs
are local to that database snapshot; never reuse them after restore or mutation.
Use `DELETE_SCOPED` from `bracc_etl.osce_migration` only with approved `$ids`.
Its guard requires OSCE source, legacy ID and only incoming Provider HAS_SANCTION
links with OSCE provenance; approval and coverage checks remain separate.

Rebuild sanctions/links using the corrected pipeline with no limit. The guarded
reload pattern (only after approval and Provider coverage verification) is:

```python
os.environ["NEO4J_DATABASE"] = approved_database
with GraphDatabase.driver(approved_uri, auth=(user, password)) as driver:
    pipeline = PeOsceSanctionsPipeline(driver, data_dir=approved_data_root)
    pipeline.extract()
    pipeline.transform()
    pipeline.providers = []
    pipeline.load()
```

Preserve existing Providers: do not call its ordinary full `load()` against production,
which overwrites provider source/name properties. Use `pipeline.providers = []`
only after verifying all input Providers exist (otherwise stop and review missing
providers). The rehearsal exercises this sanctioned subset of the existing loader.
Verify exact input IDs/counts/properties, one correct link per sanction, zero
NULL/crossed RUC links, zero shared nodes and zero legacy across the agreed full
scope. A second load must leave nodes, links and provenance unchanged.
Stop on any anomaly and keep public access paused. Roll back by stopping the
service, restoring the verified pre-maintenance dump into a replacement store,
restoring the recorded code/config and checking the baseline before reopening.
Reverting code alone cannot restore deleted identities. No operation is approved
until the human explicitly accepts the concrete deployment-specific proposal.
