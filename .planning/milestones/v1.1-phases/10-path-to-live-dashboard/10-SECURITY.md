---
phase: 10
slug: path-to-live-dashboard
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-17
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Phase 10 shipped the Path-to-LIVE dashboard tile + `/api/preflight/carry-ins` endpoint
> + `dashboard-smoke.yml` CI workflow. Three plans, 18 declared threats, all classified.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| public HTTP -> api-gateway `/api/preflight/carry-ins` | Unauthenticated read-only endpoint; any caller on the network can read carry-in descriptions, `_state` timestamps, and the joined live_readiness payload. | Operator-state JSON (carry-in descriptions, ISO timestamps, per-check PASS/FAIL/UNKNOWN). No secrets, no PII. |
| api-gateway -> `/app/planning_state/carry_ins.json` | RW bind-mount inside container; api-gateway process is the sole writer in production. | `_state` object (api-gateway writes), `carry_ins[]` array (Phase 11 writes via git diff). |
| api-gateway -> trading-engine `/api/preflight/live-readiness` | Service-to-service over docker-compose network. | Preflight check status payload (6 checks of {check, status, detail}). |
| Host filesystem `.planning/state/` -> container `/app/planning_state/` | WSL bind-mount; host operator (`git diff` / manual edit) and container process share the file. | JSON state file. Tampering means git-diff-visible commit. |
| browser -> api-gateway (carry-ins + live-readiness endpoints) | Unauthenticated read-only fetches from dashboard. | Same payloads above; rendered via JSX text escaping. |
| api-gateway JSON response -> React DOM (carry-in descriptions, `check.detail`) | Server-controlled strings rendered via React JSX. | React default text escaping is the sole sanitisation; no raw-HTML injection prop is used. |
| GitHub Actions runner -> bootstrap.sh stack (paper mode) | CI ephemeral runner; no real Bybit credentials. | Test-only env vars; logs uploaded as 14d artifacts on failure. |
| GitHub event payload -> workflow shell | Workflow only interpolates `${{ github.ref }}` in concurrency.group — Actions-sanitised context. | No PR title/body/commit message reaches shell. |
| test fixture -> docker compose force-recreate trading-engine with LIVE env | `all_preflight_checks_passing` fixture flips trading-engine LIVE-mode env mid-test. | `MARKET_DATA_SOURCE` deliberately absent -> tape mode preserved -> no real Bybit orders. |

---

## Threat Register

### Plan 10-01 — Carry-ins endpoint + state file

| Threat ID | Category | Component | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|-------------|------------------------|--------|
| T-10-01-01 | Information disclosure | `/api/preflight/carry-ins` response (carry-in descriptions reveal LIVE-flip operator workflow + OP-04 billing status) | accept | Operator-state surface intentional (D-10-02 locked schema). No PII, no secrets. Matches Phase 8 `/api/preflight/live-readiness` + Phase 9 `/api/preflight/ml-gate-reason-counts` unauth-read-only precedent. Reverse proxy / WAF in production deployment is operator's responsibility (ADR-007). | closed |
| T-10-01-02 | Tampering | `_state.first_all_pass_at` host-FS write could be falsified to force ALMOST/READY prematurely | accept | RW bind-mount blast radius bound to single repo file. Host write privileges already imply repo write privileges (git diff audit trail). The "force ALMOST/READY" path is documented operator emergency-override (CONTEXT.md Deferred Ideas). Safety property lives in Phase 8 preflight (trading-engine refuses to boot in LIVE with cap > 2%), not in `_state` JSON tamper-evidence. | closed |
| T-10-01-03 | DoS | Torn writes to `carry_ins.json` could crash handler on next read | mitigate | Atomic temp+rename: `tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))` + `os.fdopen(fd, "w")` + `f.flush()` + `os.fsync(f.fileno())` + `os.replace(tmp_name, path)`. Evidence: `services/api-gateway/app/routes/preflight_carry_ins.py:51-78` (`_atomic_write_json`). File-read failure path falls back to default state without raising at lines 142-170. Handler never raises on happy path. | closed |
| T-10-01-04 | Spoofing / fabrication of PASS | trading-engine unreachable could be exploited to claim all checks PASS and unlock READY | mitigate | UNKNOWN-from-upstream counts as not-PASS (D-10-08). trading-engine-unreachable maps to `overall="DO_NOT_FLIP"` (D-10-11). Evidence: `preflight_carry_ins.py:29-39` (`_DEGRADED_CHECKS` all UNKNOWN), `:172-174` (`len(checks) >= 6` guard plus all-PASS test), `:201-207` (DO_NOT_FLIP when `not all_pass`). The degraded payload's UNKNOWN status falls into `not all_pass` and emits DO_NOT_FLIP automatically. | closed |
| T-10-01-05 | Elevation of privilege | Endpoint no auth — any caller can read state | accept | Matches Phase 8 PREFLIGHT-01 + Phase 9 MLGATE-03 unauth read-only precedent. Endpoint read-only; reveals only state already observable in repo files (`.planning/state/carry_ins.json` is committed). No write surface exposed. | closed |
| T-10-01-06 | Tampering (supply chain) | Future autoflake pass strips `from app.routes.preflight_carry_ins import ...` line in main.py, silently disabling endpoint | mitigate | `# noqa: E402` pinned at the import site. Evidence: `services/api-gateway/app/main.py:1235` — `from app.routes.preflight_carry_ins import router as preflight_carry_ins_router  # noqa: E402` and `:1237` — `app.include_router(preflight_carry_ins_router)`. Grep gate in Plan 10-03 catches removal: `tests/integration/test_dashlive_grep_gates.py::test_carry_ins_endpoint_referenced`. | closed |

### Plan 10-02 — PathToLiveTile component

| Threat ID | Category | Component | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|-------------|------------------------|--------|
| T-10-02-01 | Tampering | Compromised api-gateway returns fabricated `overall="READY"` to unlock LIVE-flip messaging | accept | Tile is visibility surface, not enforcement. Phase 8 PREFLIGHT-02 refuses to boot trading-engine in LIVE with cap > 2% regardless of dashboard render. Four-flag LIVE gate (CLAUDE.md §"Trading-mode flags") is the control plane; tile is informational. | closed |
| T-10-02-02 | Information disclosure (XSS) | XSS via crafted carry-in `description` or `check.detail` rendered into the DOM | mitigate | All text via JSX text interpolation; React escapes by default. No raw-HTML injection prop is used, no direct DOM write, no JS-code-string execution primitives. Evidence: `frontend/src/components/PathToLiveTile.jsx:152` (`{bannerLabel}` interpolation), `:196` (`{chk.check}`), `:203` (`{chk.detail}`), `:232` (`{ci.id}`), `:239` (`{ci.description}`). Grep for forbidden patterns returns only one hit at line 23 — inside the JSDoc comment documenting the mitigation. | closed |
| T-10-02-03 | DoS | Tile crash on null/malformed payload could blank dashboard | mitigate | Tile wrapped in `<TileState query={carryInsQuery} thresholdKey="default" ...>`; on `query.isError` TileState renders Failed/Retry UI and children never render (D-14 from Phase 6). Optional-chaining used throughout. Evidence: `PathToLiveTile.jsx:117-124` (`carryInsQuery.data?.live_readiness?.checks`, `carryInsQuery.data?.carry_ins`, `carryInsQuery.data?.overall`, `carryInsQuery.data?.window`), `:138` (`carryInsQuery.data?.evaluated_at`), `:139` (`isEmpty={(data) => !data || !data.carry_ins}`). | closed |
| T-10-02-04 | Spoofing | Client recomputes `overall` and disagrees with server, misleading operator | mitigate | Component reads `carryInsQuery.data?.overall` directly per D-10-04. No client-side recomputation. Evidence: `PathToLiveTile.jsx:123` — `const overall = carryInsQuery.data?.overall || 'DO_NOT_FLIP'`. D-10-16 authority rule documented in `frontend/src/hooks/useCarryIns.js:44-49` JSDoc ("AUTHORITATIVE source for `overall` and `window`"). useLiveReadiness only consulted as fallback for per-check detail rows at `PathToLiveTile.jsx:119`. | closed |
| T-10-02-05 | Repudiation | Operator state diverges from server log without trace | accept | Each api-gateway response includes `evaluated_at` ISO timestamp; server logs warnings on every degraded path (`preflight_carry_ins.py:134, 160-162, 194-196, 221-223`). Tile shows `evaluated_at` via TileState `lastUpdatedAt` prop (`PathToLiveTile.jsx:138`) so operator can correlate. | closed |

### Plan 10-03 — CI smoke + grep gates

| Threat ID | Category | Component | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|-------------|------------------------|--------|
| T-10-03-01 | Tampering / supply chain | CI workflow uses unpinned third-party actions | mitigate | All actions pinned to major-version tags per Phase 8 supply-chain decision (STATE.md 08-04). Evidence: `.github/workflows/dashboard-smoke.yml:37` (`actions/checkout@v4`), `:40` (`actions/setup-python@v5`), `:82` (`actions/upload-artifact@v4`). | closed |
| T-10-03-02 | Injection | CI workflow shell steps interpolate user-controlled event payload | mitigate | Only `${{ github.ref }}` interpolated, in `concurrency.group` only (Actions-sanitised context). Security-note comment block preserved verbatim from `preflight-live-readiness.yml` analog. Evidence: `dashboard-smoke.yml:5-10` (security-note block), `:26` (only `${{ github.ref }}` use). No PR title/body/commit-message reaches a shell step. | closed |
| T-10-03-03 | Information disclosure | CI logs uploaded as artifact could expose secrets | mitigate | Workflow runs paper mode with no Bybit credentials. Evidence: `dashboard-smoke.yml:51-57` env block — `MARKET_DATA_SOURCE: tape`, `PAPER_TRADING_MODE: 'true'`, `TRADING_MODE: PAPER`, `AUTO_TRADING_ENABLED: 'false'`, `ENABLE_ML_PREDICTIONS: 'false'`. `.env.example` is the seed (`:59` — `cp .env.example .env`), not the operator's `.env`. Logs retention bounded to 14 days (`:86`). | closed |
| T-10-03-04 | Bypass of grep gates | Grep widened to repo root would mask production removal | mitigate | Both gates scoped narrowly: `frontend/src/` (Gate #1) and `services/api-gateway/app/` (Gate #2). Evidence: `tests/integration/test_dashlive_grep_gates.py:38` — `FRONTEND_SRC = REPO_ROOT / "frontend" / "src"`, `:39` — `API_GATEWAY_APP = REPO_ROOT / "services" / "api-gateway" / "app"`. `/tests/` and `node_modules` excluded (`:66, :118`). Subprocess grep at `:84-87, :135-138` uses the same narrow scope dirs (NOT REPO_ROOT). Scope discipline rationale documented in module docstring (`:8-10, :30-35`). | closed |
| T-10-03-05 | Tampering | Fixture-seeded DSR row persists across runs | mitigate | `leaderboard_dsr_seeded` fixture scope is `function`. Evidence: `tests/e2e/conftest.py:401` — `@pytest.fixture(scope="function")` decorator on `def leaderboard_dsr_seeded()` at line 402. Each test re-seeds from scratch; CI uses fresh `bootstrap.sh` boot. No production DB touched. | closed |
| T-10-03-06 | Information disclosure | Smoke screenshots could leak sensitive state | accept | Screenshots are `--screenshot=only-on-failure` (`dashboard-smoke.yml:73`). Content is dashboard UI state (preflight check results, carry-in descriptions — all non-secret operator-visible data). Retention bounded to 14 days. Same threat profile as Phase 7's existing dashboard smoke. | closed |
| T-10-03-07 | Elevation of privilege (test fixture) | `all_preflight_checks_passing` flips trading-engine LIVE; if `MARKET_DATA_SOURCE` also flipped to live, real Bybit orders could fire | mitigate | Committed override `tests/e2e/fixtures/test-live-trading.override.yml` deliberately does NOT set `MARKET_DATA_SOURCE` (verified by YAML parse — env keys are `PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, `MAX_POSITION_RISK_PCT=2`, `ENABLE_ML_PREDICTIONS=true` — no `MARKET_DATA_SOURCE` key). `MARKET_DATA_SOURCE` appears only in YAML comments (`:4-5`) explaining the absence. bootstrap.sh boots `MARKET_DATA_SOURCE=tape` and the override leaves it untouched. Teardown re-applies base compose without override to restore PAPER (`tests/e2e/conftest.py:656-672`). Fixture documents tape-safety property at `:591-593`. | closed |

*Status: open / closed*
*Disposition: mitigate (implementation required) / accept (documented risk) / transfer (third-party)*

---

## Unregistered Threat Flags

- **10-01-SUMMARY** §Threat Flags: "No new security surface beyond what the plan's threat model already covers (T-10-01-01 through T-10-01-06)." — informational, no new attack surface.
- **10-02-SUMMARY** §Threat Flags: All five threats mapped explicitly in a table; "No new network endpoints, auth paths, or file access patterns introduced." — informational.
- **10-03-SUMMARY**: no `## Threat Flags` section present. Confirmed during read; not a blocker — summary uses frontmatter `key_decisions` and inline body discussion of the LIVE-flip safety property (T-10-03-07) instead.

**Observation (non-blocking):** the committed override `tests/e2e/fixtures/test-live-trading.override.yml` adds a 5th env var `ENABLE_ML_PREDICTIONS=true` beyond the four cited in T-10-03-07's mitigation plan. This is documented in 10-03-SUMMARY `key_decisions` and is required for the DSR check to read the seeded leaderboard row (D-10-18 #6). It does NOT break T-10-03-07 — `MARKET_DATA_SOURCE` remains absent, tape mode preserved, no Bybit calls possible. Logged for audit visibility; classified as drift-within-scope, not unregistered surface.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-10-01 | T-10-01-01 | `/api/preflight/carry-ins` is an unauthenticated read-only operator-state endpoint. Payload contains carry-in descriptions + ISO timestamps + joined preflight checks. No PII, no secrets. Matches Phase 8 + Phase 9 unauth-read-only precedent. Reverse proxy / WAF for production internet exposure is operator responsibility (ADR-007). | gsd-security-auditor | 2026-05-17 |
| AR-10-02 | T-10-01-02 | RW bind-mount to `.planning/state/carry_ins.json` blast radius is one file in a repo subdirectory. Host write access already implies repo write privileges (git diff audit trail visible). Forcing ALMOST/READY via state edit is the documented operator emergency-override (CONTEXT.md Deferred Ideas). Safety property is Phase 8 preflight enforcement, not `_state` JSON tamper-evidence. | gsd-security-auditor | 2026-05-17 |
| AR-10-03 | T-10-01-05 | Endpoint requires no auth — matches Phase 8/9 precedent. Read-only, no write surface, no secrets, payload reflects state already observable in committed `.planning/state/carry_ins.json`. | gsd-security-auditor | 2026-05-17 |
| AR-10-04 | T-10-02-01 | PathToLiveTile is a visibility surface, not an enforcement surface. Even if a compromised api-gateway returned fabricated `overall="READY"`, trading-engine refuses to boot in LIVE with cap > 2% (PREFLIGHT-02) and the four-flag LIVE gate in CLAUDE.md is the actual control plane. Tile is informational only. | gsd-security-auditor | 2026-05-17 |
| AR-10-05 | T-10-02-05 | Each api-gateway response carries `evaluated_at` ISO; degraded paths log warnings server-side; TileState surfaces `lastUpdatedAt` to operator. Sufficient audit trail for a visibility surface. | gsd-security-auditor | 2026-05-17 |
| AR-10-06 | T-10-03-06 | Smoke screenshots are `only-on-failure`. Content is dashboard UI state (preflight check results, carry-in descriptions — operator-visible non-secret data). Retention 14 days. Same threat profile as Phase 7's accepted equivalent. | gsd-security-auditor | 2026-05-17 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-17 | 18 | 18 | 0 | gsd-security-auditor (Claude Opus 4.7 1M) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer): 12 mitigate, 6 accept, 0 transfer
- [x] Accepted risks documented in Accepted Risks Log (AR-10-01..06)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-17
