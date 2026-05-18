# LIVECLOSE Carry-In Closure Index

This index lists the five v1.0 carry-in closure harnesses delivered in Phase 11.1.
Each row pairs a `LIVECLOSE-0X` identifier with the operator-runnable harness command,
the target evidence path (under `.planning/evidence/LIVECLOSE-0X/`), and the
`human_needed` checkpoint flag — `true` when a wall-clock operator action is still
required AFTER harness execution (LIVE-flip smoke, GitHub Actions billing recovery,
7-day forward-paper-test accrual, etc.). Plan 11.1-07 (Wave 3) replaces the
`<filled-by-plan-7>` placeholders with the real harness paths once Wave 2
(Plans 11.1-02..06) lands.

## Carry-Ins

Each carry-in below lists the harness command and evidence target on separate
lines (Plan 11.1-07 replaces each `<filled-by-plan-7>` token with the real
path). The summary table at the end recaps the same data inline.

### LIVECLOSE-01

- Description: Fresh-clone bootstrap checkpoint (INFRA-02) — `bash bootstrap.sh` × 2 from `mktemp -d`
- Harness Command: `<filled-by-plan-7>`
- Evidence Target: `<filled-by-plan-7>`
- human_needed: true
- Status: open

### LIVECLOSE-02

- Description: First green CI run of integration-ml-on.yml nightly variant
- Harness Command: `<filled-by-plan-7>`
- Evidence Target: `<filled-by-plan-7>`
- human_needed: true
- Status: open

### LIVECLOSE-03

- Description: ≥7-day forward-paper-test PSR-CI accrual evidence export
- Harness Command: `<filled-by-plan-7>`
- Evidence Target: `<filled-by-plan-7>`
- human_needed: true
- Status: open

### LIVECLOSE-04

- Description: T0.1.x sweep terminal verdict (not INSUFFICIENT_DATA) + bootstrap p-value
- Harness Command: `<filled-by-plan-7>`
- Evidence Target: `<filled-by-plan-7>`
- human_needed: true
- Status: open

### LIVECLOSE-05

- Description: LIVE-flip manual smoke (dashboard rose viewport + red MODE pill)
- Harness Command: `<filled-by-plan-7>`
- Evidence Target: `<filled-by-plan-7>`
- human_needed: true
- Status: open

### Summary Table

| ID | Description | Harness Command | Evidence Target | human_needed | Status |
|----|-------------|-----------------|-----------------|--------------|--------|
| LIVECLOSE-01 | Fresh-clone bootstrap checkpoint (INFRA-02) — `bash bootstrap.sh` × 2 from `mktemp -d` | see above | see above | true | open |
| LIVECLOSE-02 | First green CI run of integration-ml-on.yml nightly variant | see above | see above | true | open |
| LIVECLOSE-03 | ≥7-day forward-paper-test PSR-CI accrual evidence export | see above | see above | true | open |
| LIVECLOSE-04 | T0.1.x sweep terminal verdict (not INSUFFICIENT_DATA) + bootstrap p-value | see above | see above | true | open |
| LIVECLOSE-05 | LIVE-flip manual smoke (dashboard rose viewport + red MODE pill) | see above | see above | true | open |

## Evidence Schema

All evidence files validate against [.planning/evidence/_schema.json](_schema.json) (status, timestamp, evidence_paths, human_needed, liveclose_id; schema_version=1).

## Status Enum

The `status` field of every evidence file is one of:

- **COMPLETE** — Harness ran and emitted all required evidence; the carry-in is closed.
- **AWAITING_HUMAN** — Harness ran successfully but a wall-clock operator action is still required (e.g. CI billing recovery, LIVE-flip smoke).
- **INSUFFICIENT_DATA** — Harness ran but the input data is below the closure threshold (e.g. fewer than 7 PSR-CI rows for LIVECLOSE-03).
- **FAILED** — Harness errored before it could emit full evidence; rerun after fixing the root cause.

## Conventions

- Evidence directories live at `.planning/evidence/LIVECLOSE-0X/` (one per carry-in).
- Each harness invocation writes a timestamped `run-<utc>.json` validated by `scripts.closure._common.write_evidence()`.
- Harness scripts are added by Plans 11.1-02..06 under `scripts/closure/liveclose-0X-*.{sh,py}`; this file references them after Plan 11.1-07 wires the index.
