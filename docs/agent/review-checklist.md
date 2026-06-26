# Agent Review Checklist

Use this before opening or updating a PR.

## Scope

- [ ] Change matches the requested problem.
- [ ] No unrelated refactor or generated churn.
- [ ] Upstream BR-ACC behavior was kept only when useful for PE-ACC.

## Correctness

- [ ] Relevant source, tests, and nearby patterns were read.
- [ ] Edge cases are handled: missing data, empty results, failed service, invalid input.
- [ ] Public endpoint contracts are covered by tests when changed.
- [ ] ETL joins and IDs are deterministic and traceable.

## Public Safety

- [ ] No new secrets, private data, or production dumps.
- [ ] No accusatory wording or corruption ranking.
- [ ] `PUBLIC_MODE` and person-data restrictions were reviewed when relevant.
- [ ] Source limitations, cutoff dates, and provenance are visible for data changes.

## Verification

- [ ] Minimum relevant gate ran and passed.
- [ ] Broader gate ran for cross-stack changes.
- [ ] Skipped checks are listed with reason.
- [ ] Manual MVP path was tested for demo-impacting changes.

## PR Notes

- [ ] Summary explains user impact.
- [ ] Validation commands are listed.
- [ ] Risks and rollback are explicit.
- [ ] Docs were updated when commands, workflows, source contracts, or public behavior changed.
