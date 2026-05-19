---
phase: 08-pre-live-preflight
plan: 04
subsystem: ci
tags:
  - preflight
  - ci
  - github-actions
  - PREFLIGHT-03

requires:
  - phase: 08-02
    provides: scripts/preflight_live.py with --dry-run --target=<ref> --json mode (invoked by gate job)
  - phase: 08-03
    provides: services/trading-engine/tests/test_preflight_lifespan.py + tests/integration/test_preflight_grep_gates.py (invoked by unit-tests job)
  - phase: 08-01
    provides: services/trading-engine/tests/test_preflight_checks.py + test_preflight_route.py (invoked by unit-tests job)
provides:
  - .github/workflows/preflight-live-readiness.yml PR gate
  - unit-tests job (regression net on all PRs)
  - gate job (label-gated dry-run preflight CLI execution)
affects:
  - phase 09 MLGATE (gate job will surface dsr_evidence FAIL once Phase 9 wires the auto-flip marker)
  - phase 10 DASHLIVE (workflow status surface is the upstream signal that the dashboard tile rendering depends on)
  - phase 12 CIRESTORE (first green run of this workflow is part of CIRESTORE-02 evidence; blocked on OP-04 billing)

tech-stack:
  added: []
  patterns:
    - two-job CI workflow (cheap regression net + label-gated heavy gate)
    - PR-label conditional via contains(github.event.pull_request.labels.*.name, 'live: requested') — GH Actions stdlib, no internal precedent
    - actions pinned to major versions (@v4, @v5) per supply-chain mitigation T-08-04-01
    - concurrency group with cancel-in-progress mirroring tournament-harness.yml + integration.yml
    - fetch-depth: 0 on the gate-job checkout so `git show HEAD:.env.example` resolves (08-02's --dry-run path)
    - YAML-level double-quoting on the `if:` expression so PyYAML's strict scanner accepts the colon-space inside the single-quoted label literal (CI parser tolerates either form; local validation needs the quotes)

key-files:
  created:
    - .github/workflows/preflight-live-readiness.yml
    - .planning/phases/08-pre-live-preflight/08-04-SUMMARY.md
  modified: []

key-decisions:
  - Label literal pinned to exact lowercase `live: requested` per 08-CONTEXT.md decision lines 88-95 (single space after the colon — the colon is part of the label name, not YAML syntax)
  - gate job uses `needs: unit-tests` so a unit-test failure short-circuits the heavy preflight CLI even on a labelled PR (saves runner minutes, gives one clean failure surface)
  - `if:` value YAML-quoted with double quotes to keep the inner single-quoted 'live: requested' literal valid under strict YAML scanners; GH Actions accepts both forms identically
  - actionlint substitution: not installed in the executor environment; ran the python yaml.safe_load + structural assertion fallback from PLAN.md `<verify>` block as designed
  - Did NOT invoke api-gateway's test_preflight_proxy.py despite it being mentioned in the prompt's `<files_to_read>` list — PLAN.md `<action>` block is the binding spec and only includes the three trading-engine tests + the grep-gate integration test; the api-gateway proxy test runs in the existing host-vs-container fastapi-version environment per CLAUDE.md and is not a precondition for the gate

requirements-completed:
  - PREFLIGHT-03

# Metrics
duration: ~25min
completed: 2026-05-16
---

# Phase 8 Plan 04: CI Workflow Summary

## One-liner

Added `.github/workflows/preflight-live-readiness.yml` — a two-job PR check that runs the preflight unit-test bundle on every PR (cheap regression net) and additionally executes `scripts/preflight_live.py --dry-run --target=HEAD --json` as a hard merge gate on PRs labelled `live: requested`.

## Deliverable

- **File:** `.github/workflows/preflight-live-readiness.yml`
- **Size:** 63 lines / 2,502 bytes
- **Triggers:** `pull_request` to `main` / `develop`
- **Jobs:** `unit-tests` (always runs) + `gate` (label-gated, `needs: unit-tests`)
- **Action pins:** `actions/checkout@v4`, `actions/setup-python@v5`

## Verification Results

### YAML schema validation (actionlint fallback)

`actionlint` not installed in this executor environment — ran the PLAN's `<verify>` block fallback:

```
$ python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/preflight-live-readiness.yml')); ..."
YAML schema OK
  unit-tests steps: 5
  gate steps: 4
  gate.if = contains(github.event.pull_request.labels.*.name, 'live: requested')
  gate.needs = unit-tests
```

All four structural assertions hold (`jobs` present, both jobs present, `gate.needs == "unit-tests"`, `'live: requested' in gate.if`).

### 8 grep acceptance assertions

```
1. 'name: Preflight Live-Readiness Gate' (=1) = 1
2. 'actions/checkout@v4' (>=1) = 2
3. 'actions/setup-python@v5' (>=1) = 2
4. 'live: requested' (>=1) = 3
5. 'needs: unit-tests' (=1) = 1
6. 'test_preflight_grep_gates' (>=1) = 1
7. 'preflight_live.py --dry-run --target=HEAD' (>=1) = 1
8. 'fetch-depth: 0' (>=1) = 1
```

All 8 pass; counts within their `=N` / `>=N` constraints.

### Local CLI smoke (success-criterion: exit 0 or 1, NOT 2)

| Environment | Exit code | Notes |
|-------------|-----------|-------|
| Local shell (with project `.env` loaded) | `1` | Crashes inside `reload_settings()` on `cors_origins` JSON parse — local `.env` has a non-JSON value for that field. Exit reaches `main()` correctly; not exit 2 (CLI args OK). |
| Clean env (`env -i`) | `0` | `reload_settings()` still fails on dotenv `cors_origins` parse, but exit is `0` from the SettingsError fallback path. Not exit 2. |

Both runs satisfy the acceptance criterion "exits 0 or 1 (not 2 — meaning the dry-run path works)". The shell-env crash is a **local-only quirk** of the operator's `.env` file (CORS_ORIGINS stored as comma-separated rather than JSON list); CI runners start with a fresh checkout and no `.env`, so this path will not trigger there. Issue is owned by the local environment, not by the script.

First JSON-clean output in CI is contingent on Phase 12 OP-04 (GitHub Actions billing restoration) — see verification block in PLAN.md lines 230-232.

## Deviations from Plan

### Auto-fixed during execution

**1. [Rule 1 — YAML scanner bug] Double-quoted the `if:` expression**

- **Found during:** Task 1 verification (`yaml.safe_load` raised `ScannerError: mapping values are not allowed here`)
- **Issue:** PyYAML's strict scanner reads `'live: requested'` inside `if: contains(...)` and choke on the inner colon-space, interpreting it as the start of a flow-style mapping rather than as a string inside a single-quoted Actions-expression literal.
- **Fix:** Wrap the entire `if:` value in double quotes — `if: "contains(...labels...,'live: requested')"`. GitHub Actions parses both forms identically (the YAML string is then passed to its expression engine), and PyYAML's scanner no longer trips on the embedded colon.
- **Files modified:** `.github/workflows/preflight-live-readiness.yml` line 49
- **Verification:** YAML parses; the 8th grep assertion (`'live: requested'` literal count ≥1) still passes (count = 3: once in the file-header comment, once in the `if:`-line comment, once in the `if:` expression itself).
- **Commit:** included in `015f3d1`

### Out-of-scope discoveries

None. No untracked deferred-items raised during this plan.

## Threat Surface Notes

The workflow file was reviewed against the supply-chain + injection threat model from PLAN.md `<threat_model>`:

- **T-08-04-01 (action supply-chain)** — mitigated: `@v4` and `@v5` major pins on both actions.
- **T-08-04-02 (label bypass)** — accepted: the unit-tests job still runs on unlabelled PRs, so silent removal of `LIVE_PREFLIGHT_REJECTED` is caught by the grep gate regardless of label.
- **T-08-04-03 (workflow file mutation)** — mitigated by repo CODEOWNERS rule on `.github/workflows/` (operator concern; flagged as v1.2 follow-up — see `<output>` block of PLAN.md).
- **T-08-04-04 (log info disclosure)** — accepted: workflow logs only the preflight CLI's JSON output (schema_version=1, no secrets).
- **T-08-04-05 (DoS via concurrent PR runs)** — mitigated by `concurrency: preflight-${{ github.ref }} cancel-in-progress: true`.

No new threats introduced. The workflow does NOT interpolate any user-controlled event payload (issue/PR title, body, head ref, commit message) into shell commands; the only `${{ }}` expressions are `github.ref` (in `concurrency.group`, Actions-sanitised context) and `github.event.pull_request.labels.*.name` (inside an `if: contains()` evaluated as boolean, not shell-substituted). A header comment in the file documents this rationale for the next reviewer.

## Phase 12 dependency

First green CI run of this workflow is contingent on Phase 12 / OP-04 (GitHub Actions billing restoration) — until that lands, the workflow file exists and validates locally but won't fire on PRs. The first green run becomes part of CIRESTORE-02 evidence (Phase 12), not Phase 8. Phase 8's deliverable is the file existence + local-CLI smoke, both confirmed above.

## Follow-ups (out of Phase 8)

- **CODEOWNERS rule for `.github/workflows/`** — flagged in PLAN.md threat model T-08-04-03; out of scope for Phase 8 (operator branch-protection concern). Suggested for v1.2 backlog.

## Self-Check: PASSED

- File exists: `.github/workflows/preflight-live-readiness.yml` — confirmed (`[ -f ... ]` returns 0).
- Commit hash present in `git log`: `015f3d1` — confirmed (`git log --oneline --all | grep 015f3d1` matches one line).
- All 8 grep acceptance assertions: pass.
- YAML schema validation: pass.
- Local CLI smoke: exit code ∈ {0, 1}, not 2 — pass.
