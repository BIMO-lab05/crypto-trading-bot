# Phase 8 Context — Pre-LIVE Preflight

> Captured 2026-05-16 via `/gsd-discuss-phase 8` in no-questions mode (user instruction: make reasonable calls, redirect if wrong). All decisions below are recommendations grounded in existing code; flag any that should be revisited before planning.

## Domain

This phase makes the path to LIVE enforced in code, not only in docs. By end of Phase 8:
- A `preflight_live.py` CLI and a `GET /api/preflight/live-readiness` HTTP endpoint both return per-check PASS/FAIL/UNKNOWN JSON for the 6 LIVE preconditions.
- `services/trading-engine` refuses to boot in `TRADING_MODE=LIVE` when `max_risk_per_trade > 0.02`, logging `LIVE_PREFLIGHT_REJECTED reason=cap_too_high`.
- A CI workflow `preflight-live-readiness.yml` blocks PRs labelled `live: requested` if any check fails.
- `RUNBOOK.md` gains a Pre-LIVE Operator Checklist (Diagnose/Action/Verification per precondition).
- Two CI grep gates ensure neither the `LIVE_PREFLIGHT_REJECTED` log emission nor the boot-path enforcement can be silently removed.

This phase produces the FOUNDATION layer that Phase 9 (MLGATE) and Phase 10 (DASHLIVE) build on. Phase 8 wires the surface; downstream phases wire the gates that feed it.

## Locked Requirements (from REQUIREMENTS.md)

- **PREFLIGHT-01** — `scripts/preflight_live.py` CLI asserts 6 preconditions (cap ≤ 2%, `PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, `EMERGENCY_STOP` absent, DSR > 0.95 row if ML enabled). Structured JSON per check. Exits non-zero on any miss.
- **PREFLIGHT-02** — trading-engine lifespan refuses LIVE boot when `max_risk_per_trade > 0.02`; emits `LIVE_PREFLIGHT_REJECTED reason=cap_too_high`. Unit test asserts both directions (PAPER allows 10%, LIVE rejects 3%).
- **PREFLIGHT-03** — `.github/workflows/preflight-live-readiness.yml` blocks PRs labelled `live: requested` where `preflight_live.py --dry-run --target=HEAD` fails any check; result posted as PR check status.
- **PREFLIGHT-04** — Pre-LIVE Operator Checklist added to `RUNBOOK.md` (Diagnose/Action/Verification per precondition); cross-linked from PROJECT.md's Out of Scope LIVE-default note.

## Decisions

### Architecture — single source of truth for the 6 checks

A shared Python module owns the check logic; CLI and HTTP endpoint both import it. **No subprocess wrapping.**

- New module: `services/trading-engine/app/preflight/checks.py` exporting `run_all() -> PreflightReport` and per-check functions (`check_cap()`, `check_paper_mode()`, `check_trading_mode()`, `check_ack()`, `check_emergency_stop()`, `check_dsr_evidence()`).
- New module: `services/trading-engine/app/preflight/types.py` with dataclasses `CheckResult(check: str, status: Literal["PASS","FAIL","UNKNOWN"], detail: str)` and `PreflightReport(overall: Literal, checks: list[CheckResult], evaluated_at: str)`.
- CLI entry point: `scripts/preflight_live.py` imports from `services.trading-engine.app.preflight` and prints `report.to_json()` to stdout. Exits 1 if `overall != "PASS"`.
- HTTP endpoint: `GET /api/preflight/live-readiness` lives on trading-engine (port 8005), proxied through api-gateway. Reason for trading-engine ownership: the check logic must run in the same process that enforces the LIVE gate, otherwise CLI and runtime drift.
- api-gateway adds a thin proxy route `GET /api/preflight/live-readiness` that fans out to trading-engine and includes the api-gateway-owned env (`TRADING_MODE`, `PAPER_TRADING_MODE`) in the same response, matching the `/api/config/safety-state` pattern at `services/api-gateway/app/main.py:1049`.

### Per-trade cap enforcement point

Enforcement lives at `services/trading-engine/app/main.py:250` lifespan (right next to the existing `LIVE_TRADING_ACK` check). New block runs immediately after the ACK check:

```python
if settings.trading_mode == "LIVE":
    if settings.max_risk_per_trade > 0.02:
        logger.critical(
            "LIVE_PREFLIGHT_REJECTED reason=cap_too_high "
            f"cap={settings.max_risk_per_trade} limit=0.02"
        )
        raise RuntimeError(
            f"Refusing to boot: TRADING_MODE=LIVE with "
            f"max_risk_per_trade={settings.max_risk_per_trade} > 0.02. "
            "Restore the LIVE-strict cap before flipping the mode."
        )
```

**Rationale:** Co-locates with the existing four-flag gate. Keeps paper-relaxed 10% per ADR-010 (PAPER skips the cap check by design — the boundary is the LIVE flip, not the paper config).

### JSON schema

Stable, versioned. Every check row has the same shape so the dashboard tile in Phase 10 doesn't need per-check rendering branches:

```json
{
  "schema_version": 1,
  "overall": "PASS|FAIL|UNKNOWN",
  "evaluated_at": "2026-05-16T14:32:01Z",
  "checks": [
    {"check": "cap",             "status": "PASS", "detail": "max_risk_per_trade=0.02 ≤ 0.02"},
    {"check": "paper_mode",      "status": "PASS", "detail": "PAPER_TRADING_MODE=false"},
    {"check": "trading_mode",    "status": "PASS", "detail": "TRADING_MODE=LIVE"},
    {"check": "ack",             "status": "PASS", "detail": "LIVE_TRADING_ACK present"},
    {"check": "emergency_stop",  "status": "PASS", "detail": "no file at /app/EMERGENCY_STOP"},
    {"check": "dsr_evidence",    "status": "UNKNOWN", "detail": "MLGATE-02 not yet landed (Phase 9)"}
  ]
}
```

`UNKNOWN` is a real terminal state, not "we haven't checked yet". Used for check #6 in Phase 8 because MLGATE-02 (Phase 9) owns the DSR-row staleness rule. Phase 8 reads the latest `leaderboard` row and reports its DSR if ML is enabled; if Phase 9's auto-flip marker (`/run/mlgate_auto_flip.json` — written by Phase 9) is missing, the check is `UNKNOWN`. The dashboard tile (Phase 10) treats `UNKNOWN` as not-yet-PASS, so READY can never light up until Phase 9 closes this loop.

### CLI flags

```
preflight_live.py [--json|--text] [--check=<name>] [--dry-run --target=<ref>]
```

- Default output: human-readable text (one line per check + final OVERALL).
- `--json` emits the schema above.
- `--check=<name>` runs only the named check (used by CI matrix + targeted ops).
- `--dry-run --target=<ref>` reads `MAX_RISK_PER_TRADE`, `TRADING_MODE`, etc. from the `.env` snapshot in the given git ref (uses `git show <ref>:.env.example` since `.env` is gitignored) — for CI gate on PRs.

### CI workflow

`.github/workflows/preflight-live-readiness.yml`:
- Triggers: `pull_request` (all PRs, low cost).
- Single job that always runs: lint + unit tests for the preflight module.
- A second `gate` job runs only when `contains(github.event.pull_request.labels.*.name, 'live: requested')`; executes `preflight_live.py --dry-run --target=HEAD --json` and fails the check on non-zero exit. The labelled-PR result is what blocks the merge.

**Rationale:** "every PR runs the unit tests; the gate only enforces on labelled PRs" is the simplest operator mental model. No skip cost for unlabelled PRs since unit tests are bounded.

### DSR evidence source

REQUIREMENTS.md mentions `tournament_results` table — that table does NOT exist. The schema in `services/tournament-harness/migrations/0001_initial.sql` defines the `leaderboard` table with a `dsr REAL` column (line 23) and an index `idx_leaderboard_dsr` on `(tournament_id, dsr DESC)` (line 41).

Phase 8 decision: read from `leaderboard` directly, not from a non-existent `tournament_results` table. **REQUIREMENTS.md should be updated in the Phase 8 plan** to reflect the actual table name; current language is a wording bug, not a schema requirement. The DSR check #6 in Phase 8 is best-effort: query the latest row from `leaderboard`, report DSR, mark `UNKNOWN` if the table is empty or unreachable. The 14-day staleness rule and the `psr_ci_published` column belong to MLGATE-01/MLGATE-02 (Phase 9).

### RUNBOOK section

Append "Pre-LIVE Operator Checklist" to existing `RUNBOOK.md` (top-level repo file, established by v1.0 Phase 2). Format matches existing 6-symptom Diagnose/Action/Verification template. Cross-linked from PROJECT.md "Out of Scope (v1.0)" line about LIVE-default — same line where the four-flag gate is documented.

### Grep gates (defence-in-depth)

Two CI grep gates, both as pytest tests under `tests/integration/test_preflight_grep_gates.py`. The integration-fake-docker CI step already runs `tests/integration/` per the v1.0 pattern; no new CI infra needed.

1. `test_live_preflight_rejected_log_exists` — `grep -r "LIVE_PREFLIGHT_REJECTED" services/trading-engine/app/` must return ≥1 match. Fails if someone removes the log emission silently.
2. `test_preflight_module_imports_at_lifespan` — assert `from app.preflight import` appears in `services/trading-engine/app/main.py`. Defence against the metrics_bridge eager-import-swallowed-ImportError pattern flagged in v1.0 retrospective.

### Test surface

- Unit tests: `services/trading-engine/tests/test_preflight_*.py` for each check function (PASS + FAIL + UNKNOWN paths). Use existing fastapi 0.109 fixture + pydantic settings override pattern.
- Lifespan integration test: spin trading-engine with `TRADING_MODE=LIVE` + `MAX_RISK_PER_TRADE=0.03`; assert RuntimeError raised and log emitted. Uses testcontainers pattern from v1.0 INFRA-03.
- HTTP route test: `GET /api/preflight/live-readiness` returns 200 with valid schema in PAPER mode and FAIL on at least one check; uses `admin_client` fixture from api-gateway/conftest.py (admin-guarded route per PROJECT.md's pattern). **Actually — preflight should be unauthenticated read-only like `/api/config/safety-state`** (decision: matches D-09 pattern from Phase 6). Confirm in plan phase.
- CLI test: `subprocess.run([sys.executable, "scripts/preflight_live.py", "--json"])` returns valid JSON; exit code matches expected.

## Specifics

- Module path: `services/trading-engine/app/preflight/` (new package; `__init__.py`, `checks.py`, `types.py`).
- CLI path: `scripts/preflight_live.py` (project-root scripts dir).
- HTTP route registration: `services/trading-engine/app/main.py` adds router; api-gateway `services/api-gateway/app/main.py` adds proxy after the `safety-state` route around line 1049 (same fan-out pattern).
- CI workflow path: `.github/workflows/preflight-live-readiness.yml`.
- Grep-gate test path: `tests/integration/test_preflight_grep_gates.py`.
- RUNBOOK section anchor: heading `## Pre-LIVE Operator Checklist` placed after the existing 6-symptom section.

## Boundaries (what Phase 8 does NOT do)

- Does NOT add `tournament_results` table or `psr_ci_published` column — MLGATE-01 (Phase 9) scope.
- Does NOT implement the 14-day DSR staleness rule — MLGATE-02 (Phase 9) scope. Phase 8 ships DSR check as UNKNOWN unless Phase 9 already landed at plan time.
- Does NOT build the `PathToLiveTile.jsx` dashboard component — DASHLIVE-01 (Phase 10) scope.
- Does NOT close OP-* carry-ins — LIVECLOSE-* (Phase 11) scope.
- Does NOT restore the per-trade cap permanently to 2% in paper mode — paper stays at 10% per ADR-010 (REQUIREMENTS.md "Out of Scope (v1.1)").
- Does NOT add `LIVE_TRADING_ACK` check — already exists at `services/trading-engine/app/main.py:250` (load-bearing, do not duplicate).
- Does NOT add a new auth requirement to the preflight endpoint — unauthenticated read-only, matching the `safety-state` D-09 pattern.

## Canonical Refs (MANDATORY)

Downstream planner + researcher MUST read:

- `.planning/PROJECT.md` — Project context, Current Milestone v1.1 section, validated requirements pre-v1 + v1.0.
- `.planning/REQUIREMENTS.md` — Phase 8 owns PREFLIGHT-01..04 specifically.
- `.planning/ROADMAP.md` — Phase 8 Goal + Success Criteria (6 criteria).
- `services/trading-engine/app/main.py:235-258` — existing lifespan + `LIVE_TRADING_ACK` boot-time check. New cap-check block belongs at line 258 (after ACK).
- `services/trading-engine/app/config.py:321` — `max_risk_per_trade` Pydantic field; reads `MAX_RISK_PER_TRADE` env. Default 0.10 per ADR-010.
- `services/api-gateway/app/main.py:1049` — `/api/config/safety-state` fan-out pattern. Preflight proxy follows same shape (unauthenticated, graceful degradation on trading-engine unreachable, JSON schema versioned, 5s frontend poll cadence assumed).
- `services/tournament-harness/migrations/0001_initial.sql:23,41` — `leaderboard.dsr` column + index. DSR check #6 reads from here.
- `RUNBOOK.md` — existing 6-symptom Diagnose/Action/Verification template (referenced from CLAUDE.md). New "Pre-LIVE Operator Checklist" section follows this format.
- `CLAUDE.md` "Trading-mode flags" section — four deliberate steps to LIVE. Preflight enforces preconditions; does not change the flags themselves.
- ADR-010 (live in `wiki/decisions/` or `docs/decisions/`) — paper-relaxed 10% cap rationale. Phase 8 strictness applies only in LIVE mode.
- `.planning/RETROSPECTIVE.md` — v1.0 lessons that shape Phase 8 plan:
  - Pair every "removed permanently" claim with a CI grep gate (see TOURN-07 model).
  - Defence-in-depth boot-path assertions at FastAPI lifespan + CLI `main()` + grep gate (single boot-path check is fragile).
  - Mark operator-execution criteria `human_needed` in VERIFICATION.md — NOT applicable here (Phase 8 has no operator-action criterion; all 6 SC are code/CI verifiable).

## Code Context (reusable assets)

- **`/api/config/safety-state` fan-out pattern** (api-gateway:1049) — adopt the same shape for `/api/preflight/live-readiness`: graceful degradation, unauthenticated, versioned schema, no secrets in response.
- **Existing `LIVE_TRADING_ACK` lifespan check** (trading-engine:250) — extend, do NOT duplicate. The cap check sits adjacent.
- **Pydantic Settings model** (trading-engine/app/config.py) — `max_risk_per_trade` field already binds `MAX_RISK_PER_TRADE` env. No new config plumbing needed.
- **`tests/integration/` pattern** (TOURN-07, MLCL-03 grep gates from v1.0) — pytest tests that invoke `subprocess.run(["grep", ...])`. Phase 8's two grep gates mirror this shape.
- **`admin_client` fixture** (api-gateway tests/conftest.py) — overrides `get_current_admin_user` for protected routes. Preflight endpoint is UNauthenticated, so use plain `test_client` instead.
- **`pathlib.Path.is_file()`** for `EMERGENCY_STOP` check — matches existing trading-engine handling (main.py:282) of the WSL bind-mount-directory edge case (do not use `.exists()`).
- **`PATH_INTERNAL` deferred from Phase 7** (per safety-state docstring) — `live_trading_acknowledged` flag for `LIVE_TRADING_ACK` env var. Phase 8 adds this. Specifically, the safety-state endpoint is the natural surface for it; preflight is the structured check, safety-state surfaces the binary "ack present" on the dashboard.

## Deferred Ideas (out of Phase 8)

- **Single boolean LIVE-gate replacing four flags** — explicitly Out of Scope per REQUIREMENTS.md (intentional friction).
- **Backporting preflight to historic commits** — Out of Scope per REQUIREMENTS.md (forward-only).
- **Auto-merge of `live: requested` PRs when preflight passes** — confirmed unsafe; humans merge (TOURN-06 no-auto-merge gate is permanent).
- **Slack notification on preflight FAIL** — Telegram pipeline exists; defer until dashboard tile (Phase 10) is live, then revisit if operator wants push notifications.
- **History tracking for preflight evaluations** (24h continuous-PASS window) — DASHLIVE-03 (Phase 10) owns the 24h window logic; Phase 8 returns the point-in-time snapshot only.

## Open Question (one)

The preflight endpoint must read `LIVE_TRADING_ACK` from the trading-engine process env, not from the api-gateway process env. Otherwise the dashboard could show "ACK present" while trading-engine refuses to boot (the exact failure mode the safety-state docstring deferred in v1.0 Phase 7). **Locked decision for the plan:** the HTTP endpoint route lives on trading-engine; api-gateway only proxies. If trading-engine is unreachable, all 6 checks return `UNKNOWN` and `overall=UNKNOWN`, not PASS-on-fallback. This is the safe default.

---
*Phase 8 context written 2026-05-16 in no-questions mode. Revisit any locked decision flagged with "decision:" or "Locked decision" if downstream planning surfaces a conflict.*
