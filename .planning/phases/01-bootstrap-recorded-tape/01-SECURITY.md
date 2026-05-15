---
phase: 01
slug: bootstrap-recorded-tape
status: verified
threats_open: 0
threats_total: 20
threats_closed: 20
asvs_level: 1
block_on: high
created: 2026-05-15
verified: 2026-05-15
auditor: gsd-security-auditor (retroactive backfill, milestone-audit follow-up)
register_authored_at_plan_time: false
note: "Retroactive backfill per v1.0 milestone audit; no STRIDE pass at plan time."
---

# Phase 01 — Security (bootstrap-recorded-tape)

**Plans audited:** 01-01 (tape fixtures capture), 01-02 (bybit-connector tape mode), 01-03 (bootstrap.sh), 01-04 (live-smoke workflow)
**ASVS Level:** L1 · **Block-on:** high · **Auditor:** gsd-security-auditor (retroactive)
**Verdict:** SECURED — 20/20 threats CLOSED

---

## Summary

Retroactive STRIDE pass over the 4 plans that shipped Phase 01. No plan-time
threat register existed; this file fills that gap per the v1.0 milestone audit.

All 20 declared threats are CLOSED. Mitigate-disposition rows are pinned to
file:line in the live tree at HEAD (verification cross-checked against
`01-VERIFICATION.md`). Accept-disposition rows are documented controls that the
project has chosen to live with (operator runbook items, GitHub-platform-level
guarantees, or threats that became moot under the chosen design).

No unregistered surface surfaced — the 4 SUMMARYs and 01-VERIFICATION evidence
table account for every code/config artifact added by the phase.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Bybit mainnet public REST → `scripts/tape/capture_bybit.py` | Capture script pulls public klines + tickers (no auth) | HTTPS GET responses |
| Capture script → `tests/fixtures/tape/{klines,ticker}/*.jsonl` | Disk write of per-symbol JSONL fixtures | JSONL bytes |
| Host filesystem → bybit-connector container | RO bind-mount `./tests/fixtures/tape:/app/tests/fixtures/tape:ro` | file bytes (read-only) |
| Container disk → `TapeReplayClient._load_fixtures()` | Eager JSONL parse at lifespan init | parsed dicts/lists |
| Operator env (`.env` / compose) → `Settings.market_data_source` | Selector drives lifespan branch + `/admin/tape/reset` 403 gate | env var (string) |
| docker network → bybit-connector :8001 `/admin/tape/reset` | Container-internal callers reach state-mutating admin route | HTTP POST (no body) |
| Operator shell → `bootstrap.sh` | Operator-supplied argv (only `--no-build`); env inherited | argv + env |
| `bootstrap.sh` → `cp -n .env.example .env` | Idempotent `.env` provision (no-clobber) | file bytes |
| `bootstrap.sh` → `touch EMERGENCY_STOP` | Pre-compose-up race guard for auto-trader | empty file |
| `bootstrap.sh` → `docker compose up -d --build` | Subprocess inherits operator env, image build context | env + build context |
| `bootstrap.sh` → `docker compose logs --tail 50` (failure path) | Container stdout/stderr → operator terminal | log bytes |
| GitHub Actions cron + `workflow_dispatch` → `live-smoke.yml` | Scheduled runner inherits encrypted secrets | env var (encrypted) |
| `secrets.BYBIT_API_*` → `live-smoke.yml` `.env` write | Secret injected via `printf` into runner-local `.env` | env var → file |
| Runner → `api.bybit.com` (testnet) | Live REST probe with hardcoded `BYBIT_TESTNET=true` | HTTPS w/ key |
| Runner → `actions/upload-artifact@v4` | `live-smoke-logs.txt` (full compose logs) uploaded to GH | log file |

---

## Threat Register — 20/20 CLOSED

### Plan 01-01 — Tape fixtures capture

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01-01 | T (tampering) | tape JSONL fixtures | mitigate | `tape_version=1` header pinned on every file (D-07); `TapeReplayClient._load_fixtures()` raises `ValueError` on header mismatch — `services/bybit-connector/app/tape_replay_client.py:81-85,97-101`; fixtures committed to git (any tamper = visible diff) | closed |
| T-01-01-02 | I (info disclosure) | capture script credentials | mitigate | `scripts/tape/capture_bybit.py` uses public Bybit V5 endpoints only — verified by 01-01 SUMMARY self-check `grep -r "BYBIT_API_KEY\|api_key" scripts/tape/` → empty | closed |
| T-01-01-03 | T (path traversal at load) | `_load_fixtures` glob | mitigate | Loader uses `Path.glob("*.jsonl")` against fixed `klines_dir` / `ticker_dir`, no operator-supplied filename interpolation — `services/bybit-connector/app/tape_replay_client.py:72,88`; symbol derived from `Path.stem` of trusted committed file | closed |
| T-01-01-04 | T (RO mount bypass) | bind-mount mutability | mitigate | `docker-compose.unified.yml:385` mounts `./tests/fixtures/tape:/app/tests/fixtures/tape:ro` — RO at the docker layer; `TapeReplayClient` performs zero writes (read-only loader, in-memory cursors) | closed |

### Plan 01-02 — Bybit connector tape mode

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-02-01 | E (elevation) | POST `/admin/tape/reset` | mitigate | HTTP 403 when `settings.market_data_source != "tape"` — `services/bybit-connector/app/main.py:1039-1043`; gate fires BEFORE client lookup at line 1044 | closed |
| T-01-02-02 | T (tampering) | TapeReplayClient state via reset | mitigate | `reset()` touches only in-memory cursors — `services/bybit-connector/app/tape_replay_client.py:124-136`; fixture bytes never mutated; RO bind-mount enforced at compose layer | closed |
| T-01-02-03 | D (DoS) | reset endpoint flood | mitigate | `@limiter.limit("60/minute")` decorator — `services/bybit-connector/app/main.py:1027` | closed |
| T-01-02-04 | I (log injection) | reset log line | mitigate | Static log `TAPE_REPLAY: cursor reset` at `services/bybit-connector/app/main.py:1050` — parameter-free, no operator input | closed |
| T-01-02-05 | R (repudiation) | unaudited reset | accept | In-memory cursor zeroing only; uvicorn access log + `TAPE_REPLAY` warning sufficient | closed |
| T-01-02-06 | S (spoofing) | no-auth network exposure on :8001 | accept | bybit-connector has no auth middleware (project pattern); `MARKET_DATA_SOURCE` selector + production-must-not-set-tape runbook discipline are the boundary | closed |

### Plan 01-03 — bootstrap.sh

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-03-01 | T (tampering) | `.env` overwrite of operator credentials | mitigate | `cp -n` no-clobber semantics at `bootstrap.sh:36`; idempotent if-guard at `bootstrap.sh:35-40` echoes "preserving operator edits" on second run | closed |
| T-01-03-02 | E (auto-trader race) | `EMERGENCY_STOP` armed before compose up | mitigate | `touch "$REPO_ROOT/EMERGENCY_STOP"` at `bootstrap.sh:54` — D-11; compose up runs at `bootstrap.sh:60-62` *after* the touch; trading-engine RO bind-mount sees the file at boot and holds the loop at STEP-0 | closed |
| T-01-03-03 | I (info disclosure on failure) | `docker compose logs --tail 50` may print env-derived secrets | mitigate | No `echo $BYBIT_API_KEY` / `echo $BYBIT_API_SECRET` in script — verified by 01-03 SUMMARY gate `! grep -E 'echo.*\$BYBIT_(API_KEY\|API_SECRET)' bootstrap.sh`; failure log stream depends on each service's own logging discipline (operator-local TTY, not uploaded) | closed |
| T-01-03-04 | T (env tamper) | `DOCKER_BUILDKIT=0` only when unset | mitigate | `[ -z "${DOCKER_BUILDKIT+x}" ]` guard at `bootstrap.sh:44` — script honours operator-pre-exported value, never silently overrides | closed |
| T-01-03-05 | E (escape outside repo) | path scope of file ops | mitigate | `cd "$REPO_ROOT"` at `bootstrap.sh:20` after `SCRIPT_DIR` resolution at line 18; all writes scoped to `$REPO_ROOT/.env` and `$REPO_ROOT/EMERGENCY_STOP`; no `sudo`, no `git clean` (negative-grep verified) | closed |

### Plan 01-04 — live-smoke workflow

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-04-01 | I (info disclosure) | Bybit API key leak via runner logs | mitigate | Secret injection via `printf 'BYBIT_API_KEY=%s\n'` (not `echo`) at `.github/workflows/live-smoke.yml:42-43`; passes anti-echo gate; GitHub Actions auto-masks `secrets.*` in any log line | closed |
| T-01-04-02 | E (PR-from-fork attack) | malicious PR triggers workflow with secrets | mitigate | Triggers limited to `schedule:` + `workflow_dispatch:` only — `.github/workflows/live-smoke.yml:8-11`; NO `pull_request` / `push` trigger (D-16 invariant); fork-PR cannot reach the workflow | closed |
| T-01-04-03 | T (silent failure masking) | `continue-on-error: true` hides regressions | mitigate | Probe step is intentionally advisory — `.github/workflows/live-smoke.yml:54`; final "Surface probe result" step at `:80-87` emits explicit `::warning` annotation on failure so operator sees status in Actions UI; deterministic-CI lane is decoupled by design (D-16) | closed |
| T-01-04-04 | T (real-money order via leaked key) | testnet vs mainnet drift | mitigate | Triple-belt: `BYBIT_TESTNET: 'true'` hardcoded at `.github/workflows/live-smoke.yml:29` + `PAPER_TRADING_MODE: 'true'` at `:32` + `AUTO_TRADING_ENABLED: 'false'` at `:34`; operator instruction in 01-04 SUMMARY mandates testnet-read-only key (no Trade permission) | closed |
| T-01-04-05 | I (artifact contains secrets) | `live-smoke-logs.txt` uploaded with full compose logs | accept | GitHub Actions auto-masks `secrets.*` in artifact text; bybit-connector logs `bot_token_set=True` boolean style only; artifact retention 14 days behind GitHub repo ACL — same trust boundary as the secret store itself | closed |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-02-05 | Reset is non-destructive (in-memory cursor zeroing); uvicorn access log + `TAPE_REPLAY` warning line sufficient. No PII / financial impact. Same pattern as AR-02-01. | gsd-security-auditor (retro) | 2026-05-15 |
| AR-01-02 | T-01-02-06 | bybit-connector has no auth middleware (existing project pattern; protected upstream at api-gateway). `/admin/tape/reset` reachable only inside docker network when `MARKET_DATA_SOURCE=tape`. Production deploys MUST NOT set `MARKET_DATA_SOURCE=tape` (operator runbook responsibility — `RUNBOOK.md`). Inherits AR-02-02. | gsd-security-auditor (retro) | 2026-05-15 |
| AR-01-03 | T-01-04-05 | Artifact `live-smoke-logs.txt` is gated by GitHub repo ACL (same trust boundary as `secrets.BYBIT_API_*`). GH Actions auto-masks any `secrets.*` substring in stdout/stderr. notification-service / connector log secrets as boolean-set markers, never the raw value. Same pattern as AR-02-19. | gsd-security-auditor (retro) | 2026-05-15 |

*Solo-operator scope. Any organizational scaling re-opens AR-01-02 (multi-tenant docker-network isolation) and AR-01-03 (artifact-access governance).*

---

## Operator Actions Required (out-of-code controls)

| Action | Rationale | Plan | Owner |
|--------|-----------|------|-------|
| Production deploys MUST NOT set `MARKET_DATA_SOURCE=tape` | Tape mode unlocks `/admin/tape/reset`. Production must run with `live` so the gate rejects with 403 (T-01-02-01). | 01-02 | release operator |
| Production deploys MUST NOT bind-mount `./tests/fixtures/tape:/app/tests/fixtures/tape:ro` | RO bind-mount is dev/CI-only; production has no fixture surface. | 01-03 | release operator |
| GitHub repo secrets `BYBIT_API_KEY` + `BYBIT_API_SECRET` MUST be Bybit *testnet* keys with read-only market-data permission (no Trade) | Defense-in-depth around the triple-belt safety in `.github/workflows/live-smoke.yml`. Docs at 01-04 SUMMARY "User Setup Required". | 01-04 | repo admin |
| Tape fixture refresh = re-run `python3 scripts/tape/capture_bybit.py` + commit (no automated refresh) | Per D-06 fixtures are frozen at capture time; a forged commit substituting fixture content is the only tamper vector and shows up as a code-review-visible diff. | 01-01 | release operator |

---

## Verification Gates (greps / tests that pin the controls)

| Gate | Command | Expected | Pins |
|------|---------|----------|------|
| `/admin/tape/reset` 403 in live mode | `grep -n 'tape/reset only available' services/bybit-connector/app/main.py` | hit at line 1042 | T-01-02-01 |
| `/admin/tape/reset` rate-limited | `grep -n '@limiter.limit' services/bybit-connector/app/main.py` | hit at line 1027 | T-01-02-03 |
| Tape bind-mount is RO | `grep -n 'tests/fixtures/tape:/app/tests/fixtures/tape:ro' docker-compose.unified.yml` | line 385 | T-01-01-04 |
| Tape header validated at load | `grep -n 'tape_version' services/bybit-connector/app/tape_replay_client.py` | lines 81, 97 | T-01-01-01 |
| Capture script has no creds | `grep -r 'BYBIT_API_KEY\|api_key' scripts/tape/` | empty | T-01-01-02 |
| `bootstrap.sh` no-clobber `.env` | `grep -n 'cp -n' bootstrap.sh` | line 36 | T-01-03-01 |
| `bootstrap.sh` EMERGENCY_STOP before compose | `grep -nE 'touch.*EMERGENCY_STOP\|docker compose.*up' bootstrap.sh` | touch (54) before up (60-62) | T-01-03-02 |
| `bootstrap.sh` no echo of secret env | `! grep -E 'echo.*\$BYBIT_(API_KEY\|API_SECRET)' bootstrap.sh` | exit 0 | T-01-03-03 |
| `bootstrap.sh` honours pre-set BUILDKIT | `grep -n '\[ -z "\${DOCKER_BUILDKIT+x}"' bootstrap.sh` | line 44 | T-01-03-04 |
| `bootstrap.sh` no `git clean`, no `sudo`, no `down` | `! grep -E 'git clean\|sudo\|docker compose.*down' bootstrap.sh` | exit 0 | T-01-03-05 |
| live-smoke triggers exclude push/PR | `python3 -c "import yaml; w=yaml.safe_load(open('.github/workflows/live-smoke.yml')); assert set(w['on'].keys())=={'schedule','workflow_dispatch'}"` | exit 0 | T-01-04-02 |
| live-smoke uses printf not echo for secrets | `! grep -nE 'echo.*BYBIT_API' .github/workflows/live-smoke.yml` | exit 0 | T-01-04-01 |
| live-smoke triple-belt safety | `grep -nE "BYBIT_TESTNET.*'true'\|PAPER_TRADING_MODE.*'true'\|AUTO_TRADING_ENABLED.*'false'" .github/workflows/live-smoke.yml` | 3 hits (29, 32, 34) | T-01-04-04 |
| live-smoke probe is advisory | `grep -n 'continue-on-error: true' .github/workflows/live-smoke.yml` | line 54 | T-01-04-03 |

Static unit-test gates already in tree (per 01-VERIFICATION):

- `tests/test_bootstrap_script_static.py` — 13/13 (pins T-01-03-01..05)
- `services/bybit-connector/tests/test_tape_replay_client.py` — 11/11 (pins T-01-01-01, T-01-01-03, T-01-01-04)
- `tests/test_live_smoke_workflow.py` — 14/14 (pins T-01-04-01..04)
- `tests/test_tape_fixtures.py` — 35/35 (pins T-01-01-01, T-01-01-02)

---

## Unregistered Threat Flags

None. The 4 plans introduced no surface beyond what is registered above:

- 01-01 SUMMARY: capture script + 10 fixture files; no network endpoint, no auth path.
- 01-02 SUMMARY: 1 new admin endpoint (`/admin/tape/reset`) + 1 lifespan branch + Settings selector — all registered.
- 01-03 SUMMARY: 1 shell script + 2 env keys + compose passthrough/RO mount — all registered.
- 01-04 SUMMARY explicit "Threat Surface": "no new code surface; secrets via `${{ secrets.* }}` only".

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By | Note |
|------------|---------------|--------|------|--------|------|
| 2026-05-15 | 20 | 20 | 0 | gsd-security-auditor | Retroactive backfill per v1.0 milestone audit; no plan-time STRIDE pass existed |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (3 entries)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] Every mitigate row cites file:line at HEAD
- [x] Verification gates section provides re-runnable greps for each control

**Approval:** verified 2026-05-15
