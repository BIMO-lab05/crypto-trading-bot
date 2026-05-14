---
phase: 06-dashboard-audit-safety-state
plan: 01
status: complete
completed: 2026-05-13
duration: ~30min
requirements: [DASH-01]
---

# Plan 06-01 — Tile Audit & Audit Script (DASH-01)

## Objective

Inventory every dashboard tile in the React frontend, document its backing
endpoint + verified response shape, assign one of three verdicts
{FIXED, LABELED_STALE, REMOVED} per D-02, and ship a runtime probe script
(`scripts/audit_tiles.py`) that future CI can run against the recorded-tape
stack. The inventory drives Plan 6-05's tile refactor scope.

## What was built

### Audit artifacts
- `06-TILE-AUDIT.md` — operator-readable markdown table (15 tile rows, 4 page-level grouping headers, verdict legend, summary, operator audit log).
- `06-TILE-AUDIT.json` — machine-readable sidecar parseable by `audit_tiles.py`. Each row carries `tile`, `component`, `endpoint`, `expected_shape`, `verdict`, `last_updated_at_emitter`, and (for resolved PENDING rows) `operator_resolved` date.

### Runtime probe
- `scripts/audit_tiles.py` — CLI probe with `argparse`-driven `--against <baseurl>` argument (fail-closed: exits 2 if neither env var nor flag set, per D-09 audit security threat-model). Loads `06-TILE-AUDIT.json`, filters to FIXED-verdict rows, hits each documented endpoint, asserts shape match, prints PASS/FAIL per tile, exits non-zero on any FAIL.
- `scripts/test_audit_tiles.py` — pytest coverage: 5 cases (happy path, shape mismatch, HTTP 503, fail-closed missing target, FIXED-only filter).
- `scripts/__init__.py` — package init for pytest discovery.

## Verdict distribution

| Verdict | Count | Notes |
|---|---|---|
| FIXED | 10 | Endpoint returns 200 with documented shape. Plan 6-05 wires `<TileState/>`. |
| LABELED_STALE | 5 | 1 design-stale (Phase3Dashboard ML+sentiment off) + 4 operator-resolved (market-data + portfolio-manager containers unhealthy at audit time). Plan 6-05 wires `<TileState forceStale={true}/>`. |
| REMOVED | 0 | No dead-tile candidates surfaced. |

## Operator decisions (Task 3 checkpoint, 2026-05-13)

4 PENDING-OPERATOR rows resolved → all LABELED_STALE:

- **PriceTickerGrid** — `/api/market/ticker/{symbol}` returns 503; market-data container `unhealthy`. Decision: LABELED_STALE; market-data restoration is an ops fix tracked outside Phase 6.
- **PriceChart** — `/api/market/klines/{symbol}` (same container). LABELED_STALE.
- **Sparkline** — same endpoint as PriceChart. LABELED_STALE.
- **Portfolio (page)** — `/api/portfolio` returns 503; portfolio-manager container `unhealthy`. Decision: LABELED_STALE; `usePortfolio` hook stays. Ops fix restores backing endpoint; no migration to trading-engine endpoints in this phase.

Phase3Dashboard `LABELED_STALE` confirmed (ML + sentiment intentionally off per `ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`).

## Verification

- `python3 scripts/audit_tiles.py --against http://localhost:8000` against live stack: `9/9 FIXED probeable tiles PASS`, exit 0 (10th FIXED row `Phase1Dashboard` is page-level composition — not probed; covered by Test 6).
- `pytest scripts/test_audit_tiles.py`: 5 passed.
- `06-TILE-AUDIT.json` parseable via `python3 -c "import json; json.load(open('.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json'))"`.
- Verdict counts in JSON match counts in markdown.

## Key files created

- `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md`
- `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json`
- `scripts/audit_tiles.py`
- `scripts/test_audit_tiles.py`
- `scripts/__init__.py`

## Commits

- `d3479b9` docs(06-01): add tile audit table + JSON sidecar (DASH-01)
- `62c7842` test(06-01): add failing tests for audit_tiles CLI (DASH-01 RED)
- `993f9c1` feat(06-01): implement audit_tiles CLI probe (DASH-01 GREEN)
- `f4f62b3` docs(06-01): resolve 4 PENDING-OPERATOR verdicts to LABELED_STALE

## Threat model status

- T-06-01-01 (audit script targeting wrong host) — MITIGATED via fail-closed `--against` flag.
- T-06-01-02 (shape-assert false negative on optional fields) — ACCEPTED (`expected_shape` only asserts presence of required keys, ignores extras).

## Deviations

- 4 PENDING-OPERATOR rows resolved at the human-verify checkpoint as expected — no plan deviation.
- `last_updated_at_emitter` column populated per W-02 scope-down (0 `yes`, 9 `no`, 6 `n/a`). Phase 7 D-15 backlog inventory is now machine-readable.

## Self-Check: PASSED

All `must_haves.truths` from frontmatter satisfied; verification commands pass; no orchestrator-artifact modifications.
