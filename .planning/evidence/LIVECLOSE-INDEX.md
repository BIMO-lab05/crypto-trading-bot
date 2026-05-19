# LIVECLOSE Carry-In Closure Index

This index lists the five v1.0 carry-in closure harnesses delivered in Phase 11.1.
Each row pairs a `LIVECLOSE-0X` identifier with the operator-runnable harness command,
the target evidence path (under `.planning/evidence/LIVECLOSE-0X/`), and the
`human_needed` checkpoint flag — `true` when a wall-clock operator action is still
required AFTER harness execution (LIVE-flip smoke, GitHub Actions billing recovery,
7-day forward-paper-test accrual, etc.). Plan 11.1-07 (Wave 3) populates the
real harness paths once Wave 2 (Plans 11.1-02..06) has landed.

## Carry-Ins

Each carry-in below lists the harness command and evidence target on separate
lines. The summary table at the end recaps the same data inline.

### LIVECLOSE-01

- Description: Fresh-clone bootstrap checkpoint (INFRA-02) — `bash bootstrap.sh` × 2 from `mktemp -d`
- Harness Command: `bash scripts/closure/liveclose-01-fresh-clone.sh`
- Evidence Target: `.planning/evidence/LIVECLOSE-01/run-<utc_ts>.json`
- human_needed: true
- Status: open
- Diagnose / Action: Operator runs the harness from inside a clean checkout to confirm `bash bootstrap.sh` is idempotent and the recorded-tape source is wired in. After it exits AWAITING_HUMAN, commit the evidence JSON and flip `INFRA-02` in `.planning/state/carry_ins.json` to `state: closed`.

### LIVECLOSE-02

- Description: First green CI run of integration-ml-on.yml nightly variant
- Harness Command: `bash scripts/closure/liveclose-02-record-ci.sh --url <green-run-url>`
- Evidence Target: `.planning/evidence/LIVECLOSE-02/{ci-url.txt, evidence-<utc_ts>.json}`
- human_needed: true
- Status: open
- Diagnose / Action: After OP-04 (GitHub Actions billing) is unblocked and `integration-ml-on.yml` goes green on a nightly run, paste the run URL into the harness. It validates the URL via `gh api`, writes `ci-url.txt` + a schema-valid evidence JSON, and exits AWAITING_HUMAN. Operator commits both and flips `OP-04` to `closed`.

### LIVECLOSE-03

- Description: ≥7-day forward-paper-test PSR-CI accrual evidence export
- Harness Command: `python -m scripts.closure.liveclose_03_psr_evidence --db-path /data/tournament.db`
- Evidence Target: `.planning/evidence/LIVECLOSE-03/psr-evidence-<utc_ts>.json`
- human_needed: true
- Status: open
- Diagnose / Action: After the forward-paper-test loop accrues `ACCRUAL_WINDOW_DAYS` (=7) consecutive UTC-calendar-day rows with `psr_ci_published=1` in some natural-key group, run the harness. INSUFFICIENT_DATA means the window hasn't filled yet — wait and rerun. AWAITING_HUMAN means commit the evidence JSON and flip the corresponding `OP-` row.

### LIVECLOSE-04

- Description: T0.1.x sweep terminal verdict (not INSUFFICIENT_DATA) + bootstrap p-value
- Harness Command: `python -m scripts.closure.liveclose_04_sweep_verdict`
- Evidence Target: `.planning/evidence/LIVECLOSE-04/verdict-<utc_ts>.json`
- human_needed: true
- Status: open
- Diagnose / Action: After OP-02 (migration 005) and OP-03 (TOURNAMENT_READER_PASSWORD) are satisfied, re-run the T0.1.x sweep and open-pr `--dry-run`, then update `.planning/evidence/t0_1_x/decision_note.md` final line to `EDGE_FOUND` or `NO_EDGE_FOUND`. Run this harness to capture the verdict.json. AWAITING_HUMAN means commit the verdict and flip the corresponding `OP-` row.

### LIVECLOSE-05

- Description: LIVE-flip manual smoke (dashboard rose viewport + red MODE pill)
- Harness Command: `LIVECLOSE_05_SUPERVISED_RUN=1 LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY bash scripts/closure/liveclose-05-live-flip-smoke.sh`
- Evidence Target: `.planning/evidence/LIVECLOSE-05/{screenshot-<utc_ts>.png, evidence-<utc_ts>.json}`
- human_needed: true
- Status: open
- Diagnose / Action: Supervised-only — operator must export `LIVECLOSE_05_SUPERVISED_RUN=1` and `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` and stay attended. The harness force-recreates api-gateway with `TRADING_MODE=LIVE`, probes `/api/preflight/live-readiness`, and reverts to PAPER on EXIT (any signal). Operator captures the dashboard screenshot manually, commits it under the evidence target, and flips `OP-01` to `closed`. See [docs/runbooks/LIVECLOSE-05.md](../../docs/runbooks/LIVECLOSE-05.md).

### Summary Table

| ID | Description | Harness Command | Evidence Target | human_needed | Status |
|----|-------------|-----------------|-----------------|--------------|--------|
| LIVECLOSE-01 | Fresh-clone bootstrap checkpoint (INFRA-02) — `bash bootstrap.sh` × 2 from `mktemp -d` | `bash scripts/closure/liveclose-01-fresh-clone.sh` | `.planning/evidence/LIVECLOSE-01/run-<utc_ts>.json` | true | open |
| LIVECLOSE-02 | First green CI run of integration-ml-on.yml nightly variant | `bash scripts/closure/liveclose-02-record-ci.sh --url <green-run-url>` | `.planning/evidence/LIVECLOSE-02/{ci-url.txt, evidence-<utc_ts>.json}` | true | open |
| LIVECLOSE-03 | ≥7-day forward-paper-test PSR-CI accrual evidence export | `python -m scripts.closure.liveclose_03_psr_evidence --db-path /data/tournament.db` | `.planning/evidence/LIVECLOSE-03/psr-evidence-<utc_ts>.json` | true | open |
| LIVECLOSE-04 | T0.1.x sweep terminal verdict (not INSUFFICIENT_DATA) + bootstrap p-value | `python -m scripts.closure.liveclose_04_sweep_verdict` | `.planning/evidence/LIVECLOSE-04/verdict-<utc_ts>.json` | true | open |
| LIVECLOSE-05 | LIVE-flip manual smoke (dashboard rose viewport + red MODE pill) | `LIVECLOSE_05_SUPERVISED_RUN=1 LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY bash scripts/closure/liveclose-05-live-flip-smoke.sh` | `.planning/evidence/LIVECLOSE-05/{screenshot-<utc_ts>.png, evidence-<utc_ts>.json}` | true | open |

## Orchestrator

Use `bash scripts/closure/run-all.sh --list` to see the harness commands and current state in one place. See `bash scripts/closure/run-all.sh --help` for the flag reference. The orchestrator is read-mostly — it does NOT auto-execute LIVECLOSE-05 (LIVE-flip smoke), which must be operator-supervised (see [docs/runbooks/LIVECLOSE-05.md](../../docs/runbooks/LIVECLOSE-05.md)).

## Wave-3 Closure Contract

Each harness writes evidence files validated against [.planning/evidence/_schema.json](_schema.json). The operator's final closure step for each carry-in:

1. Commit the evidence file(s) under the listed target path.
2. Flip the row in `.planning/state/carry_ins.json` from `state: open` to `state: closed`, setting `closed_at` (ISO-8601 UTC) and `evidence_path` (repo-relative). The dashboard PathToLiveTile (Phase 10 DASHLIVE) re-polls every 5s and reflects the close.

Note on ID mapping: `.planning/state/carry_ins.json` tracks the operator-action carry-ins under their original IDs (`OP-01`..`OP-04` and `INFRA-02`), not under `LIVECLOSE-0X`. LIVECLOSE-01 corresponds to `INFRA-02`; LIVECLOSE-05 corresponds to `OP-01`; LIVECLOSE-02/03/04 hold the evidence backing the closure of `OP-04`/`OP-02`/`OP-03` (or any future `OP-` row added for forward-paper-test accrual).

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
- Each harness invocation writes a timestamped JSON file validated by `scripts.closure._common.write_evidence()`.
- Harness scripts live under `scripts/closure/liveclose-0X-*.{sh,py}`. Python harnesses (LIVECLOSE-03, LIVECLOSE-04) use underscore-form filenames per the Python import contract — on disk: `scripts/closure/liveclose_03_psr_evidence.py` and `scripts/closure/liveclose_04_sweep_verdict.py`. They are invoked as `python -m scripts.closure.liveclose_03_psr_evidence` and `python -m scripts.closure.liveclose_04_sweep_verdict`. Bash harnesses (LIVECLOSE-01, LIVECLOSE-02, LIVECLOSE-05) use hyphen-form.
