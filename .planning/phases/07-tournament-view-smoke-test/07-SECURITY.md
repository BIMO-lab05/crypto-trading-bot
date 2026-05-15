---
phase: 7
slug: tournament-view-smoke-test
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
note: "Retroactive backfill per v1.0 milestone audit. Frontend trusts gateway-validated tournament data; gateway is the security boundary."
---

# Phase 07 — Security (tournament-view-smoke-test)

**Plans audited:** 07-01 (gateway snapshot routes + RO bind-mount), 07-02 (frontend hooks — no new surface), 07-03 (data-testid wiring — no new surface), 07-04 (Tournament dashboard + 6 components), 07-05 (smoke fixture + audit-driven Playwright test), 07-06 (CI install + dependency pin)
**ASVS Level:** L1 · **Block-on:** high · **Auditor:** gsd-security-auditor · **Date:** 2026-05-15
**Verdict:** SECURED — 8/8 threats CLOSED

---

## Summary

Retroactive STRIDE pass over Phase 07 surfaces. Phase 07 ships two HTTP read endpoints
(`GET /api/tournament/snapshots[/{id}]`), a RO bind-mount of the committed snapshots
directory, six presentational React components fed by URL state, and a Playwright smoke
that boots the recorded-tape stack. **Trust model:** the gateway is the security boundary;
the frontend assumes gateway-validated tournament data is truthful because it is git-tracked
and produced upstream by `tournament-harness`. Significance/contamination labels are
*operator-facing visual cues*, not security controls — their threat dispositions are
`accept` with the upstream tournament-harness writer + git-tracked snapshots forming the
control surface.

Plans 07-02 + 07-03 introduce no new attack surface (pure plumbing + attribute-only edits)
per their SUMMARY `## Threat Surface Scan` sections. The 8 threats below cover Plans 07-01,
07-04, and 07-06.

---

## Trust Boundaries

| # | Boundary | Description | Data Crossing |
|---|----------|-------------|---------------|
| TB-01 | Operator → committed snapshots dir | Operator (or `tournament-harness` job under operator-controlled profile) writes JSON files into `services/tournament-harness/data/snapshots/` and commits them to git | tournament snapshot rows + ensemble + significance JSON |
| TB-02 | Snapshots dir → api-gateway | Docker RO bind-mount `./services/tournament-harness/data/snapshots:/app/snapshots:ro` (`docker-compose.unified.yml:309`) | filesystem reads via `Path.glob` / `Path.read_text` |
| TB-03 | api-gateway → frontend | `GET /api/tournament/snapshots[/{tournament_id}]` JSON over HTTP, unauthenticated (D-09 carryforward from Phase 6) | tournament_id, summary block, full snapshot, ensemble, significance |
| TB-04 | Frontend `useSearchParams` → React state | Operator-supplied URL params (`tournament_id`, `symbol`, `arch`, `status`, `sort`, `dir`) drive table sort/filter and gateway query | URL query string |
| TB-05 | GitHub Actions secrets → workflow runner | `secrets.TEST_TELEGRAM_BOT_TOKEN` / `secrets.TEST_TELEGRAM_CHAT_ID` exported into stack-boot env for Phase 2 + 7 integration runs | test-namespace Telegram credentials |
| TB-06 | PyPI → CI runner | `pip install -r tests/integration/requirements.txt` pulls `pytest-playwright>=0.5,<1.0` + transitive deps | Python wheels |

---

## Threat Register — 8/8 CLOSED

### Plan 07-01 — gateway snapshot routes + RO bind-mount

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-07-01-01 | Tampering (path traversal via `{tournament_id}`) | mitigate | closed | Two-layer defense in `services/api-gateway/app/main.py`: (a) regex gate `^[A-Za-z0-9_\-]+$` at L1266 raises 400 on any non-alphanumeric/_/- char (rejects `.`, `/`, `\\`, `..`, URL-encoded `%2F`); (b) defense-in-depth `snap_path.is_relative_to(base)` at L1274 catches any future regex regression. Module-level seam `_TOURNAMENT_SNAPSHOTS_DIR = Path("/app/snapshots")` at L1174. Test `test_detail_returns_400_on_path_traversal_attempt` at `services/api-gateway/tests/test_tournament_snapshots.py:189-222` exercises `..`, `.`, URL-encoded `..%2Fetc%2Fpasswd`, and `foo%2Fbar`. |
| T-07-01-02 | Elevation of Privilege (RO bind-mount escape / write attempt) | mitigate | closed | `docker-compose.unified.yml:309` declares mount with `:ro` flag — kernel enforces read-only at the mount layer regardless of gateway code. Gateway code never opens snapshot files for write (`grep -n "write_text\|open(.*'w'\|open(.*\"w\"" services/api-gateway/app/main.py` over the tournament routes returns 0). Comment at L302-308 documents intent: "RO ensures the gateway can't corrupt the committed artifact." Size-cap at L1283 (`stat().st_size > _TOURNAMENT_MAX_FILE_BYTES = 50 MiB`) caps DoS-via-poisoned-file (covered by `test_detail_returns_500_when_file_exceeds_50mb` at tests/test_tournament_snapshots.py:225-257). |

### Plan 07-04 — Tournament dashboard + 6 presentational components

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-07-04-01 | Tampering (stored XSS via leaderboard rows — `architecture` / `symbol` / `failure_reason` / `tournament_id`) | mitigate | closed | All 6 new files render gateway-supplied strings exclusively via React text-node interpolation (`{value}`), which auto-escapes. `frontend/src/components/TournamentLeaderboard.jsx:327` text rendering, L304 failure_reason, L320 status, L366 row testid template-literal-into-attribute (numeric+alpha id only — no React-prop sink). `SignificanceBadge.jsx:118-138` and `ContaminatedWindowWarning.jsx:55,65` likewise use only text nodes / native `title` attribute. 07-VERIFICATION.md spot-check at L181 confirms `grep -nE 'dangerouslySet\|innerHTML\s*=' frontend/src/components/Tournament*.jsx frontend/src/components/SignificanceBadge.jsx frontend/src/components/ContaminatedWindowWarning.jsx frontend/src/pages/TournamentDashboard.jsx` returns 0 matches. 07-04-SUMMARY.md L177 confirms enforcement. |
| T-07-04-02 | Tampering (URL-state injection via `useSearchParams` — `sort`, `dir`, `symbol`, `arch`, `status`, `tournament_id`) | mitigate | closed | Whitelist clamps in `frontend/src/pages/TournamentDashboard.jsx:51-58`: `SORT_WHITELIST` (6 columns) + `DIR_WHITELIST` (`asc`/`desc`) → `clampSort(raw)` defaults to `dsr`, `clampDir(raw)` defaults to `desc` for any non-whitelisted value. `parseList` at `TournamentFilterChips.jsx:42-44` strips empty/whitespace tokens; selected values render only via React text nodes (chip labels). `tournament_id` is forwarded into the gateway URL where it hits the regex gate at main.py:1266 (T-07-01-01) — defense-in-depth across the trust boundary. |
| T-07-04-03 | Spoofing (contaminated-window warning bypass — corrupt snapshot omits `train_window_includes_contaminated=true`) | accept | closed | Warning is a *visual operator cue*, not a security control. Source of truth is the upstream tournament-harness writer (Phase 3 D-08) under operator-controlled profile (`docker-compose.unified.yml:772-793`), and snapshots are git-tracked under `services/tournament-harness/data/snapshots/`. Component render gate is permissive-by-default: `ContaminatedWindowWarning.jsx:30-31` returns `null` when `visible !== true`; computation `rows.some((r) => r?.train_window_includes_contaminated === true)` lives at `TournamentDashboard.jsx:149-152` (`===` strict equality — false/missing/null all suppress warning). Threat reduces to "operator commits a corrupt snapshot to git and trusts their own corrupt artifact" — acceptable under solo-founder trust model. See AR-07-01. |
| T-07-04-04 | Spoofing (significance badge — corrupt snapshot fakes `win_gate_passed=true` or ensemble membership) | accept | closed | Same trust model as T-07-04-03: badge reflects gateway-supplied data which originates from operator-committed snapshot + sidecar JSONs. `SignificanceBadge.jsx:50-52` requires *both* `inEnsemble && winGatePassed` to render the pass pill; `TournamentLeaderboard.jsx:269-278` short-circuits `failed`-status rows to em-dash (cannot fake green pill on a failed row). The badge is operator decision-support, not a release/promotion gate — promotion to ensemble lives in Phase 4 tournament-harness with its own register (Phase 04 SECURITY). See AR-07-02. |

### Plan 07-06 — CI install + dependency pin

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-07-06-01 | Information disclosure (Playwright smoke against live stack leaks production credentials in CI) | mitigate | closed | `.github/workflows/integration.yml:48-50` (and L58-60 for ml-on variant) export only `TEST_TELEGRAM_BOT_TOKEN` / `TEST_TELEGRAM_CHAT_ID` into the stack — both are explicitly test-namespace secrets, separate from any production Bybit / Telegram credentials. No `BYBIT_API_KEY*` / `BYBIT_API_SECRET*` injected. Stack boots with `MARKET_DATA_SOURCE=tape` + `PAPER_TRADING_MODE=true` + `TRADING_MODE=PAPER` (L42-44). Failure artifacts upload via `actions/upload-artifact@v4` with 14d retention; `--screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure` capture only browser-visible content (gateway-origin only — no `:3000` vite-dev origin per smoke at `tests/integration/test_dashboard_smoke.py:67`). |
| T-07-06-02 | Tampering (supply-chain — `pytest-playwright>=0.5` floating minor pulls compromised release) | mitigate | closed | Pin in `tests/integration/requirements.txt`: `pytest-playwright>=0.5,<1.0` — caps at sub-1.0 major boundary. Upstream `playwright` Python package + Chromium browser bundle pulled by `playwright install --with-deps chromium` at workflow L38. Risk acknowledged: floating minor allows >=0.5.0 patches without lockfile. Acceptable under repo's existing dep-pin posture (no `pip-tools`/`poetry.lock` in this worktree); L1 ASVS does not require SBOM. Tightening to exact pin or hash-lock is operator decision per AR-07-03. |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-04-03 | Contaminated-window warning is operator-facing visual cue, not security control. Source of truth is git-tracked snapshot JSON committed by upstream tournament-harness under operator profile. Solo-operator honour-system applies (analogous to AR-05-01). | operator | 2026-05-15 |
| AR-07-02 | T-07-04-04 | Significance badge is decision-support, not a promotion/release gate. Promotion lives in Phase 4 tournament-harness with its own register. Frontend trust model assumes gateway-validated git-tracked data is truthful. | operator | 2026-05-15 |
| AR-07-03 | T-07-06-02 | Repo-wide convention is loose-pin (no lockfile). Phase 07 inherits posture; tightening to hash-pin out of scope per L1 ASVS. Re-visit if SLSA / supply-chain tier escalation enters scope. | operator | 2026-05-15 |

*Any organizational scaling beyond solo-founder requires revisiting AR-07-01 and AR-07-02 — both lean on the operator-as-trusted-snapshot-author trust model.*

---

## Verification Gates (spot-checks)

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| RO bind-mount declared with `:ro` | `grep -n 'tournament-harness/data/snapshots:/app/snapshots' docker-compose.unified.yml` | match ends with `:ro` | L309 ends `:ro` ✓ |
| Path-traversal regex present | `grep -n '\^\[A-Za-z0-9_\\\\-\]\+\$' services/api-gateway/app/main.py` | 1 match in tournament route | L1266 ✓ |
| `is_relative_to` defense-in-depth present | `grep -n 'is_relative_to' services/api-gateway/app/main.py` | match in tournament route | L1274 ✓ |
| Size-cap guard present | `grep -n '_TOURNAMENT_MAX_FILE_BYTES' services/api-gateway/app/main.py` | constant + use site | L1177 + L1283 ✓ |
| Snapshot test covers traversal | `grep -n 'test_detail_returns_400_on_path_traversal_attempt' services/api-gateway/tests/test_tournament_snapshots.py` | 1 def | L189 ✓ |
| Snapshot test covers size-cap | `grep -n 'test_detail_returns_500_when_file_exceeds_50mb' services/api-gateway/tests/test_tournament_snapshots.py` | 1 def | L225 ✓ |
| Zero HTML-injection sinks in new files | `grep -nE 'dangerouslySet\|innerHTML\s*=' frontend/src/components/Tournament*.jsx frontend/src/components/SignificanceBadge.jsx frontend/src/components/ContaminatedWindowWarning.jsx frontend/src/pages/TournamentDashboard.jsx` | 0 matches | 0 matches (07-VERIFICATION L181) ✓ |
| URL sort whitelist present | `grep -n 'SORT_WHITELIST\|clampSort' frontend/src/pages/TournamentDashboard.jsx` | def + 1+ use | L51, L54-56, L92 ✓ |
| URL dir whitelist present | `grep -n 'DIR_WHITELIST\|clampDir' frontend/src/pages/TournamentDashboard.jsx` | def + 1+ use | L52, L57-59, L93 ✓ |
| Gateway routes unauthenticated by intent | `grep -n 'D-09 carryforward\|Unauthenticated' services/api-gateway/app/main.py` (tournament block) | comment present | L1189, L1258 ✓ |
| CI uses TEST_-namespaced secrets only | `grep -nE 'BYBIT_API|MAINNET' .github/workflows/integration.yml` | 0 matches | 0 matches ✓ |
| pytest-playwright capped below 1.0 | `grep pytest-playwright tests/integration/requirements.txt` | `>=0.5,<1.0` pin present | line 7 ✓ |
| Smoke targets gateway origin only | `grep -n 'localhost:3000' tests/integration/test_dashboard_smoke.py` | 0 matches | 0 matches (07-VERIFICATION L183) ✓ |

---

## Per-Plan Verification Summary

| Plan | Threats | All CLOSED? | Evidence |
|------|---------|-------------|----------|
| 07-01 | 2 | yes | 9/9 in-container unit tests pass per 07-01-SUMMARY; path-traversal + size-cap tests directly cover both threats |
| 07-02 | 0 | n/a | 07-02-SUMMARY L135: "No new attack surface introduced. Pure frontend data plumbing." |
| 07-03 | 0 | n/a | Attribute-only edits (data-testid wiring); no logic / no new endpoints |
| 07-04 | 4 | yes | 07-04-SUMMARY L177-184 enforces T-07-11 (XSS); T-07-04-03/04 accepted under documented trust model |
| 07-05 | 0 | n/a | Test scaffolding only (smoke + fixtures + conftest fixture); P07.1 local run: 1 passed in 135.05s |
| 07-06 | 2 | yes | Test-namespace secrets only; pytest-playwright capped <1.0 |
| **Total** | **8** | **8 / 8** | — |

---

## Unregistered Threat Flags

None. Plan SUMMARY `## Threat Surface Scan` / `## Threat Flags` sections in 07-01, 07-02, 07-04, 07-05, 07-06 either declare "no new surface" or map cleanly into the register above. 07-03 + 07-05 have no security surface (data-testid attribute additions; test scaffolding).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-15 | 8 | 8 | 0 | gsd-security-auditor (retroactive backfill) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (3 entries)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-15

---

## Operator Notes

- The trust model — "frontend trusts gateway-validated tournament data; gateway is the security boundary" — is load-bearing for AR-07-01 and AR-07-02. Both accepted risks lean on the operator being the only writer of git-tracked snapshot JSON. Re-visit if the tournament-harness profile is exposed to untrusted contributors or if snapshots are ever consumed from a non-git source.
- T-07-06-02 (supply-chain) is mitigated to L1 ASVS but not to L2/L3 — escalation to hash-locked deps is a repo-wide decision, not a Phase 07 regression.
- The 07-VERIFICATION.md `human_needed` items (CI billing unblock, async-fixture remediation if it surfaces in CI, operator visual confirm) are operational, not security blockers — they do not affect the closed status of any threat in this register.
