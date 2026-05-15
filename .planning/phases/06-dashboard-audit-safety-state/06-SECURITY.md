---
phase: 6
slug: dashboard-audit-safety-state
status: verified
threats_open: 0
threats_total: 8
threats_closed: 8
asvs_level: 1
block_on: high
created: 2026-05-15
verified: 2026-05-15
auditor: gsd-security-auditor (retroactive backfill, milestone-audit follow-up)
register_authored_at_plan_time: false
note: "Retroactive backfill per v1.0 milestone audit. Pre-existing project pattern: dashboard endpoints unauthenticated for solo-operator deployment (CONTEXT 06-CONTEXT.md). LIVE-flip smoke (OP-01) operator-only by safety-classifier."
---

# Phase 06 — Security (dashboard-audit-safety-state)

**Plans audited:** 06-01 (tile audit + audit script), 06-02 (backend safety-state endpoint), 06-03 (config-driven URLs), 06-04 (StatusBar pills + viewport border), 06-05 (TileState state machine)
**ASVS Level:** L1 · **Block-on:** high · **Auditor:** gsd-security-auditor · **Date:** 2026-05-15
**Verdict:** SECURED — 8/8 threats CLOSED

---

## Summary

Phase 06 introduces a single new HTTP surface (`GET /api/config/safety-state`)
plus a polled-frontend hook + StatusBar surface + viewport tint. No new
authentication paths, no new write surfaces, no PII or balance disclosure.
Plan-level threat registers (T-06-01-01/02, T-06-03-01..03, T-06-05-01..05)
were closed at plan time; this retroactive cross-phase register (T-06-NN-01..08)
covers the 5-plan composite surface and the 8 KEY THREATS surfaced by the
milestone audit.

All 8 threats are CLOSED. Six are MITIGATED via code/test grep with file:line
citations; two are formally ACCEPTED (dashboard-auth deferral and
ENABLE_ML_PREDICTIONS visibility) under the documented solo-operator
deployment pattern (06-CONTEXT.md L75 + L135).

The LIVE-flip operator smoke (OP-01) is operator-action-driven; the
StatusBar pill + safety-border code path is unit-test-covered (16 vitest
cases in plan 06-04) and the visual smoke is recorded in
06-VERIFICATION.md `human_verification[0]`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser → api-gateway (Plan 06-02, 06-04) | Frontend axios client polls `/api/config/safety-state` every 5s | safety-posture JSON (D-08 schema) |
| api-gateway → trading-engine (Plan 06-02) | Gateway fan-out `proxy_request` to `/status` + `/api/v1/risk/budget/current` | internal service-to-service JSON, intra-cluster |
| api-gateway env → handler (Plan 06-02) | `os.getenv("TRADING_MODE"/...)` reads at request time | config flag values from compose `${VAR:-default}` substitution |
| Filesystem → trading-engine (Plan 06-02) | `auto_trader.emergency_stop_file.is_file()` + `Path.stat().st_mtime` | EMERGENCY_STOP file presence + mtime |
| Operator shell → dashboard process (Plan 06-04) | Operator flips `TRADING_MODE=PAPER↔LIVE` in `.env` and restarts api-gateway | env-var change reflected in next 5s poll |
| Tile React Query → backend endpoint (Plan 06-05) | Per-tile React Query hooks → axios → gateway → service | per-tile JSON; error envelope on failure |
| Audit-script CLI → live stack (Plan 06-01) | `python3 scripts/audit_tiles.py --against <url>` | per-tile probe results to stdout |
| Frontend bundle → window (Plan 06-03) | `import.meta.env.VITE_WS_URL` baked into client JS at build time | dev-only fallback string |

---

## Threat Register — 8/8 CLOSED

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-06-NN-01 | Information Disclosure | accept | closed | `GET /api/config/safety-state` is unauthenticated by deliberate D-09 default. Route declared at `services/api-gateway/app/main.py:1049` with NO `Depends(get_current_admin_user)` (compare admin-guarded `/api/portfolio/emergency-stop` POST at line ~598). Disclosed fields are operational config flags only — no balances, no positions, no API keys, no PnL absolute values (only percent). Documented in handler docstring `services/api-gateway/app/main.py:1066-1067` ("Unauthenticated (D-09): read-only config disclosure. No secrets, no balances, no positions. Threat T-06-02-01 explicitly accepted."). Pattern matches pre-existing dashboard read-routes per 06-CONTEXT.md:135. AR-06-01 below. |
| T-06-NN-02 | Tampering / Spoofing | mitigate | closed | Stale safety-state poll → operator acts on outdated mode. TileState state machine forces error-precedence: `frontend/src/components/TileState.jsx:235-241` (Branch 1: `query.isError` → Failed UI wins) is BEFORE the stale-overlay branch at L286. `useSafetyState` hook configured `refetchInterval: 5000, staleTime: 5000, retry: 2` at `frontend/src/hooks/useSafetyState.js:41-44` so a transient failure cycles to stale-then-error within ≤7s. `last_updated_at` is gateway-stamped at `services/api-gateway/app/main.py:1164` (`datetime.now(_tz.utc).isoformat()`), giving the UI a freshness anchor. F-05 precedence pair (TileState.test.jsx tests 10+11) verifies stale-overlay can NEVER silence an error. |
| T-06-NN-03 | Race Condition / TOCTOU | mitigate | closed | EMERGENCY_STOP file presence check uses `is_file()` NOT `exists()` at `services/trading-engine/app/handlers/health.py:221`, with `try/except Exception` wrapping `p.stat().st_mtime` at L219-228 so a vanish-between-check-and-stat race returns `mtime: None` rather than 500. Plus the WSL bind-mount race documented in CLAUDE.md is handled — when the bind-mount yields a directory rather than a file, `is_file()` returns False and `mtime_iso` stays `None` (verified in 06-VERIFICATION.md spot-check: live `curl :8005/status` shows `emergency_stop.mtime: null`). 4 dedicated tests in `services/trading-engine/tests/test_health_status.py` (per 06-02-SUMMARY.md L82). |
| T-06-NN-04 | Tampering (regression) | mitigate | closed | Hardcoded URL regression gate. `frontend/scripts/check-no-hardcoded-urls.sh` is the load-bearing regression guard, wired as `npm run check-no-hardcoded-urls` at `frontend/package.json:15`. Path-scoped allowlist (NOT universal-comment-pass) — verified by Plan 06-03 negative-test 2 (URL in comment in non-allowlisted file → exit 1). Live: `bash frontend/scripts/check-no-hardcoded-urls.sh` exits 0; raw localhost-grep on frontend/src returns exactly 2 documented dev defaults: `frontend/src/hooks/useGatewayWebSocket.js:34` (env-fallback after `\|\|`) and `frontend/src/services/api.js:7` (JSDoc continuation). vite.config.js DASH-02 doc block at L42-75 declares the convention + threat note. WR-07 hardened the awk pre-pass for multi-line block-comment URLs. |
| T-06-NN-05 | Information Disclosure (error-message leak) | mitigate | closed | TileState `ErrorState` rendering at `frontend/src/components/TileState.jsx:150-158` enforces D-14 fallback chain: `response.data.detail` → `response.statusText` → literal `"request failed"`. NEVER raw axios message field (which can contain stack-trace fragments per axios config). Grep gate verified: counting `error\.message` occurrences in `TileState.jsx` returns 0 (per 06-05-SUMMARY.md L160). Plan 06-05 Auto-fix #2 reworded doc-comments to remove the literal substring so the gate stays clean. T-06-05-02 disposition. |
| T-06-NN-06 | Spoofing (UI signal bypass) | mitigate | closed | LIVE-flip visual signal — operator must not miss MODE flip. Two redundant affordances driven from same single 5s poll: (1) StatusBar MODE pill at `frontend/src/components/StatusBar.jsx:173-179` with `accent={modeAccent}` where `modeAccent = tradingMode === 'LIVE' ? '#fb7185' : '#5eead4'` at L88; (2) viewport `outline:` (NOT `border:` — no layout shift) at `frontend/src/styles/safety-border.css` driven by App.jsx className at `frontend/src/App.jsx:285` (`safety-border safety-border--${mode}`, mode derived from same `useSafetyState` data at L279-280). Both consume `safety.trading_mode` from one queryKey so they cannot disagree mid-poll. 5 vitest cases in `frontend/src/__tests__/App.test.jsx` cover PAPER/LIVE className flip + CSS-uses-outline-not-border. Operator visual smoke (OP-01) recorded in 06-VERIFICATION.md `human_verification[0]` — accepted as operator-action-driven (AR-06-03). |
| T-06-NN-07 | Cross-site scripting via tile content | mitigate | closed | Axios responses rendered inside TileState use React JSX text-child interpolation only — `frontend/src/components/TileState.jsx:181` (`Failed ({code}): {message}`) and `:141` (`<div>No data yet</div>`). React's default escaping handles all string content. Confirmed by grep across `TileState.jsx` / `StatusBar.jsx` / `App.jsx` for raw-HTML injection sinks (the well-known unsafe React prop, the corresponding DOM API, and dynamic-code constructors) → 0 matches. StatusBar value cells at `frontend/src/components/StatusBar.jsx:43-53` also use JSX text children only — no raw HTML sinks. Same baseline as pre-existing cells. |
| T-06-NN-08 | Client-side state injection | mitigate | closed | TileState consumes only React Query result objects passed by parent components — no direct URL-param reads, no `useSearchParams`/`useLocation`/`window.location` access. Confirmed by grep across `frontend/src/components/TileState.jsx` for those identifiers → 0 matches. The `lastUpdatedAt` prop is parsed via `Date.parse()` at `frontend/src/components/TileState.jsx:71` with `Number.isFinite(t)` guard returning false on malformed input — no exception path, no injection vector. `forceStale` is consumed as `Boolean(forceStale)` at L282. No client-side state derived from untrusted input. |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-NN-01 | Dashboard endpoint authentication is deferred for the solo-operator deployment topology (single laptop, no shared access). The new `/api/config/safety-state` route deliberately follows the pre-existing dashboard read-route pattern (06-CONTEXT.md:135). Operational config flags are not secrets; absolute balances/positions/PnL stay behind the existing portfolio-manager surfaces. Any organizational scaling MUST add an authn layer (or block the route at nginx) before exposing the dashboard publicly — at that point this AR triggers a re-review. | operator | 2026-05-15 |
| AR-06-02 | T-06-NN-01 | `ENABLE_ML_PREDICTIONS` visibility is informational, not actionable: the flag is `false` by default (gated off per CLAUDE.md ML rule) and toggling it requires service restart with new env. Disclosing the flag value cannot itself cause a model to run; the value tells an attacker only that the operator has chosen to disable a deprecated subsystem. No exploit path. | operator | 2026-05-15 |
| AR-06-03 | T-06-NN-06 | LIVE-flip operator smoke (OP-01 in 06-VERIFICATION.md `human_verification[0]`) is operator-action-driven by safety-classifier — it requires editing `.env`, force-recreating the api-gateway, and visually inspecting both pill flip and viewport tint at the edge. Cannot be asserted via curl alone (visual rendering at viewport edge could clip via outline-offset). The underlying logic IS unit-test-covered (16 vitest cases in plan 06-04: PAPER/LIVE className flip + CSS outline-not-border). Phase 7 DASH-06 Playwright work will close the visual gap. | operator | 2026-05-15 |

*Any organizational scaling beyond solo-founder on localhost requires revisiting AR-06-01 specifically — the public-Internet variant of this surface MUST authn the route or block it at nginx.*

---

## Per-Plan Verification Summary

| Plan | Plan-time threats | Cross-phase threats covered | Test Run |
|------|-------------------|------------------------------|----------|
| 06-01 | T-06-01-01 (audit-script tampering, mitigated via fail-closed `--against`), T-06-01-02 (shape-assert false-neg, accepted) | T-06-NN-04 (audit-side regression gate) | 6/6 audit_tiles pytest |
| 06-02 | T-06-02-01 (info disclosure of operator config, accepted) | T-06-NN-01, T-06-NN-02, T-06-NN-03 | 19/19 in-container pytest (4 health + 4 risk + 11 safety-state) |
| 06-03 | T-06-03-01 (VITE_WS_URL build-time override, mitigated), T-06-03-02 (grep-gate evasion, accepted), T-06-03-03 (VITE_* in client JS, accepted) | T-06-NN-04 | bash gate exit 0 + 2 negative tests |
| 06-04 | T-06-04-01..05 (stale-poll, injection on trading_mode, etc. — all mitigated/baseline) | T-06-NN-06 | 16/16 vitest (StatusBar 9 + App 5 + useSafetyState 2) |
| 06-05 | T-06-05-01..05 (HTML injection, raw-message leak, refetch DoS, F-05 precedence, audit-coverage) | T-06-NN-05, T-06-NN-07, T-06-NN-08 | 12/12 vitest (TileState — incl. F-05 precedence pair) |
| **Total** | **18 plan-time** | **8 cross-phase** | **53 tests pass** |

---

## Spot-Check Verifications (Live)

| Check | Source | Result |
|-------|--------|--------|
| Safety-state route declared without auth Depends | grep `safety-state` in `services/api-gateway/app/main.py` | line 1049 — bare `@app.get(...)`, no admin-user dependency |
| Live safety-state response shape | `curl http://localhost:8000/api/config/safety-state` | full D-08 JSON (per 06-VERIFICATION.md spot-check 1) |
| No raw axios-message rendering in TileState | `grep -nE 'error\.message' frontend/src/components/TileState.jsx \| wc -l` | 0 |
| No raw-HTML injection sinks in Phase-6 frontend code | grep across `TileState.jsx` / `StatusBar.jsx` / `App.jsx` for unsafe-HTML / dynamic-code identifiers | 0 matches |
| No URL-param injection in TileState | grep across `frontend/src/components/TileState.jsx` for `useSearchParams` / `useLocation` / `window.location` / `URLSearchParams` | 0 matches |
| Hardcoded-URL grep gate | `bash frontend/scripts/check-no-hardcoded-urls.sh` | exit 0 + "OK: no undocumented hardcoded URLs" |
| Hardcoded-URL raw grep | `grep -rn "http://localhost\|ws://localhost" frontend/src/` | 2 documented defaults only (useGatewayWebSocket.js:34, api.js:7) |
| EMERGENCY_STOP file race-safe | `grep -n 'is_file()' services/trading-engine/app/handlers/health.py` | line 221 (`p.is_file()` inside try/except) |
| audit_tiles fail-closed on missing `--against` | per 06-01-SUMMARY Test 6 + scripts/audit_tiles.py:262-269 | exit 2 with stderr message |
| F-05 precedence pair in TileState tests | per 06-05-SUMMARY.md L178-179 | tests 10 (forceStale + isError → Failed wins) + 11 (forceStale + isLoading → skeleton wins) |
| viewport tint uses `outline:` not `border:` | grep border declarations in `frontend/src/styles/safety-border.css` (filtered for comments) | 0 (per 06-04-SUMMARY) |
| api-gateway env block exposes config flags | per 06-02-SUMMARY.md L185-189 | TRADING_MODE / PAPER_TRADING_MODE / ENABLE_ML_PREDICTIONS wired with `${VAR:-default}` |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-13 (plan-time) | 18 (per-plan registers in 06-01..06-05 SUMMARY threat-model blocks) | 18 | 0 | gsd-implementer + gsd-code-fixer |
| 2026-05-15 (cross-phase backfill) | 8 (T-06-NN-01..08) | 8 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All 8 cross-phase threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (3 entries)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] All 18 plan-time threat IDs (T-06-01-01..02, T-06-02-01, T-06-03-01..03, T-06-04-01..05, T-06-05-01..05) cross-referenced in Per-Plan summary
- [x] OP-01 LIVE-flip operator smoke recorded as AR-06-03 (operator-action-driven, not test-coverage gap)

**Approval:** verified 2026-05-15

---

## Operator Notes

- The 4 outstanding `human_verification` items in 06-VERIFICATION.md are
  operator UAT smokes (visual / interaction / LIVE-flip / non-tested
  alignment-score render). They are NOT security gaps — the underlying
  logic is unit-tested. AR-06-03 covers the LIVE-flip half.
- AR-06-01 is the load-bearing accepted risk: the dashboard endpoint
  surface assumes solo-operator-on-localhost. If the dashboard is ever
  exposed beyond `127.0.0.1` (port-forward, ngrok, public ingress), the
  operator MUST add an authn layer or block the route at nginx BEFORE
  flipping `TRADING_MODE=LIVE`. This re-triggers the AR review.
- Phase 7 D-06 (Playwright suite) automates the 4 manual smokes; until
  then they remain operator UAT.
