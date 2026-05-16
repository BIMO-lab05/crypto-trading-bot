# Requirements — Milestone v1.1 Path to LIVE

> Active requirements for v1.1. Ratified via `/gsd-new-milestone` on 2026-05-16.
>
> Source: `.planning/PROJECT.md` Current Milestone section + v1.0 carry-in list + path-to-LIVE checklist in CLAUDE.md.

## Active

### LIVECLOSE — Close v1.0 operator-blocked carry-ins

Each carry-in needs an operator-runnable closure path with verifiable evidence row, not "code complete pending operator".

- [ ] **LIVECLOSE-01**: Operator executes INFRA-02 fresh-clone bootstrap checkpoint (Plan 01-03 Task 4) — runs `bash bootstrap.sh` against a fresh `git clone` into a tmp directory **twice**, captures `BYBIT_PRICE_SOURCE: mode=tape` log line + 15-service health snapshot per run, and commits the evidence under `.planning/evidence/LIVECLOSE-01/`.
- [ ] **LIVECLOSE-02**: INFRA-01 live-stack ML-on nightly variant produces its first green CI run on GitHub Actions (after OP-04 billing recovery); CI URL + green-badge evidence linked in OP-04 close note.
- [ ] **LIVECLOSE-03**: MLCL-01 forward-paper-test apparatus accrues ≥7 consecutive trading days of evidence with PSR-CI published per feature; evidence row visible in tournament leaderboard with `psr_ci_published=true`.
- [ ] **LIVECLOSE-04**: MLCL-02 T0.1.x `different_horizon` sweep re-runs after OP-02 (migration 005) + OP-03 (reader password); verdict transitions from `INSUFFICIENT_DATA` to `PASS` or `FAIL` with bootstrap p-value persisted in `tournament_results`.
- [ ] **LIVECLOSE-05**: DASH-03 LIVE-flip manual smoke executed — operator force-recreates api-gateway with `TRADING_MODE=LIVE`, captures screenshot showing rose viewport outline + red MODE pill + KILL-SWITCH state, reverts, and commits screenshot under `.planning/evidence/LIVECLOSE-05/`.

### PREFLIGHT — Code-enforced LIVE preconditions

The point: by the end of v1.1, flipping `TRADING_MODE=LIVE` without preflight passing must be impossible at the trading-engine boot path, not merely discouraged in docs.

- [ ] **PREFLIGHT-01**: `scripts/preflight_live.py` CLI asserts all 6 LIVE preconditions and exits non-zero on any miss — (1) per-trade risk cap ≤2%, (2) `PAPER_TRADING_MODE=false`, (3) `TRADING_MODE=LIVE`, (4) `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, (5) `EMERGENCY_STOP` file absent, (6) DSR>0.95 evidence-row exists in `tournament_results` if `ENABLE_ML_PREDICTIONS=true`. Output is structured JSON per check.
- [ ] **PREFLIGHT-02**: trading-engine boot path enforces per-trade cap mode at startup — refuses to boot in `TRADING_MODE=LIVE` with `MAX_POSITION_RISK_PCT > 2`; logs explicit `LIVE_PREFLIGHT_REJECTED reason=cap_too_high` and exits. Unit test asserts both directions (PAPER allows 10%, LIVE rejects 3%).
- [ ] **PREFLIGHT-03**: CI workflow `preflight-live-readiness.yml` runs `preflight_live.py --dry-run --target=HEAD` and blocks any PR labeled `live: requested` that fails any check; result posted as PR check status.
- [ ] **PREFLIGHT-04**: Pre-LIVE operator checklist added to `RUNBOOK.md` (Diagnose/Action/Verification per precondition) and cross-linked from PROJECT.md's Out of Scope LIVE-default note.

### MLGATE — Operator-driven ML re-enablement evidence loop

ML predictions stay off until evidence justifies them — and the gate is in code, not in a Slack message.

- [ ] **MLGATE-01**: `scripts/forward_paper_test/run_evidence_loop.py` driver loops ≥7-day evidence accrual + per-feature PSR-CI publish; idempotent across restart; resumes from last persisted row.
- [ ] **MLGATE-02**: `services/trading-engine` includes a startup check that flips `ENABLE_ML_PREDICTIONS=true` only if a DSR>0.95 evidence row exists in `tournament_results` within the last 14 days; reverts to `false` on DSR drop or stale row; emits `MLGATE_AUTO_FLIP` log event with reason.
- [ ] **MLGATE-03**: Every "ml predictions disabled" event in `technical-analysis` logs a structured reason from a fixed enum: `no_evidence | dsr_below_gate | evidence_stale | regime_shift | manual_override`; Telegram digest aggregates daily counts.

### DASHLIVE — Path-to-LIVE dashboard tile

One screen surfacing every precondition so the operator never flips LIVE blind.

- [ ] **DASHLIVE-01**: New dashboard component `PathToLiveTile.jsx` renders PASS/FAIL/UNKNOWN status of every PREFLIGHT-01 check on a 5-second poll against `GET /api/preflight/live-readiness`.
- [ ] **DASHLIVE-02**: Same tile shows OP-* carry-in close states (OP-01..04 + INFRA-02 checkpoint) sourced from `GET /api/preflight/carry-ins` — file-backed (`.planning/state/carry_ins.json`) or git-tag–backed (`carry-in/closed/<id>`).
- [ ] **DASHLIVE-03**: Tile renders "DO NOT FLIP" (red) until **all** PREFLIGHT checks PASS for ≥24h continuous; "READY" (green) only after the 24h continuous-PASS window holds; partial transitions render "ALMOST" (amber) with count.
- [ ] **DASHLIVE-04**: Playwright smoke `tests/e2e/test_path_to_live_smoke.py` validates the tile renders correctly in PAPER mode and that DSR evidence-row shape is asserted; runs in `dashboard-smoke.yml` CI.

### CIRESTORE — Post-OP-04 CI recovery

Once billing is resolved, the carry-in CI jobs must actually run green and the regression must be detectable next time.

- [ ] **CIRESTORE-01**: Operator confirms GH Actions billing resolved (OP-04 close); close-note committed under `.planning/evidence/OP-04/` with billing-page screenshot timestamp.
- [ ] **CIRESTORE-02**: First green CI run of (a) `integration-ml-on.yml` nightly variant, (b) `tournament-harness.yml`, (c) `dashboard-smoke.yml` — three CI run URLs linked in OP-04 close note.
- [ ] **CIRESTORE-03**: Add `billing-failure-detector.yml` workflow that runs every 6h via `gh run list --status failure --limit 5` filtering for `billing` substring; on detection, posts to Telegram via existing notification path and creates a GitHub Issue with the `ops: billing` label.

## Future Requirements

<!-- Deferred from v1.1 scoping; revisit at v1.2. -->

- Tournament-harness first cross-symbol expansion (XRP/AVAX) — gated on production validation milestone; placeholder noted in v1.0 Out of Scope.
- Multi-horizon production deployment (1h/4h/24h with per-horizon trading paths) — v2 candidate, depends on MLGATE landing first.
- Server-side `/ws/metrics` route + WS subscription layer — v2 (UI-only client polling sufficient through v1.x).
- Mobile-friendly responsive dashboard layout — v2.
- K8s deployment — v2 (compose-only through v1.x per ADR).
- Sentiment-as-filter integration — v2.
- Classification head + calibration — v2.

## Out of Scope (v1.1)

<!-- Explicit exclusions with reasoning. -->

- **Real-money LIVE trading actually flipped on during v1.1** — milestone delivers the *preconditions* and *gates*; flipping the four flags is an operator decision, not a v1.1 deliverable. The success criterion is "preflight blocks LIVE if any precondition fails", not "system is live in production".
- **Restoring per-trade cap permanently to ≤2% in paper mode** — paper-relaxed 10% per ADR-010 stays for paper; PREFLIGHT-02 enforces the strict 2% only when `TRADING_MODE=LIVE`.
- **Replacing the four-flag LIVE gate with a single boolean** — four deliberate flags survive intentional friction; v1.1 adds preflight on top, does not replace the friction.
- **Auto-merging tournament-winning PRs even after MLGATE-02 lands** — `gh pr merge` CI grep gate (TOURN-06) is still load-bearing; auto-flip of `ENABLE_ML_PREDICTIONS=true` happens via env var at runtime, not via merging code.
- **Backporting preflight to historic LIVE-ready commits** — preflight applies forward only; historic commits considered untrusted for LIVE.
- **Rewriting `run_extended_backtest.py` to CoreAggregator** — ADR-012 permanent-divergence decision stands.

## Traceability

<!-- Filled by `gsd-roadmapper` during ROADMAP creation. Maps every REQ-ID to exactly one phase. -->

| REQ-ID | Phase | Status |
|--------|-------|--------|
| LIVECLOSE-01 | Phase 11 | active |
| LIVECLOSE-02 | Phase 11 | active |
| LIVECLOSE-03 | Phase 11 | active |
| LIVECLOSE-04 | Phase 11 | active |
| LIVECLOSE-05 | Phase 11 | active |
| PREFLIGHT-01 | Phase 8 | active |
| PREFLIGHT-02 | Phase 8 | active |
| PREFLIGHT-03 | Phase 8 | active |
| PREFLIGHT-04 | Phase 8 | active |
| MLGATE-01 | Phase 9 | active |
| MLGATE-02 | Phase 9 | active |
| MLGATE-03 | Phase 9 | active |
| DASHLIVE-01 | Phase 10 | active |
| DASHLIVE-02 | Phase 10 | active |
| DASHLIVE-03 | Phase 10 | active |
| DASHLIVE-04 | Phase 10 | active |
| CIRESTORE-01 | Phase 12 | active |
| CIRESTORE-02 | Phase 12 | active |
| CIRESTORE-03 | Phase 12 | active |

---
*Last updated: 2026-05-16 — v1.1 roadmap created; all 19 REQ-IDs mapped to phases 8–12*
