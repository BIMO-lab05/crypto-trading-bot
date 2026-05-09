---
phase: 03
slug: tournament-harness-core
status: secured
threats_open: 0
asvs_level: not_set
block_on: high
created: 2026-05-09
updated: 2026-05-09
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time across 9 PLAN.md `<threat_model>` blocks; verified by
> `gsd-security-auditor` against implementation files.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| docker.sock → tournament-harness | Orchestrator launches experiment containers via Docker SDK (D-02) | container spec (no secrets); load-bearing per profile gate |
| TimescaleDB → experiment container | `tournament_reader` SELECT-only role on `klines` (D-09) | OHLCV historical bars; no write path |
| experiment container → orchestrator | Untrusted `/output/result.json` payload | metric numbers; size + schema validated before SQL |
| operator → CLI | `tournament.yaml` config + `--where` query DSL | grid spec; whitelisted columns/ops only |
| CI runner → repo | Workflow execution surface | tests; no `pull_request_target`, no auto-merge |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-03-01 | Elevation of Privilege | `/var/run/docker.sock` bind-mount | mitigate | `docker-compose.unified.yml:738` `profiles: [tournament]` keeps service off by default + single-image runner pattern | closed |
| T-03-02 | Tampering | YAML config parsing path | mitigate | `requirements.txt:27` `pyyaml==6.0.1` pinned; loaders use `yaml.safe_load` only | closed |
| T-03-03 | Information Disclosure | TimescaleDB password env var | accept | Standard 12-factor secret handling — same pattern as POSTGRES_PASSWORD; .env gitignored | closed |
| T-03-04 | Tampering | hp dict values consumed by builders | mitigate | `gru.py:_validate_hp()` and siblings — bounds units/dropout/lr/horizon, raise ValueError early | closed |
| T-03-05 | Denial of Service | Transformer/TCN nested HP | mitigate | `transformer.py`/`tcn.py` `_validate_hp()` — n_heads/kernel_size/dilation_base whitelists | closed |
| T-03-06 | Repudiation | model compile contract drift | mitigate | `03-02-SUMMARY.md` — Adam(lr) + loss=mse + metrics=[mae] preserved; 167 tests pass | closed |
| T-03-07 | Denial of Service | Untrusted result.json size | mitigate | `result_schema.py:MAX_RESULT_BYTES = 262_144`; size check before `json.load` | closed |
| T-03-08 | Tampering | SQL injection through failure_reason / failure_stderr_tail | mitigate | `0001_initial.sql` enum CHECK constraint + `LeaderboardDB.insert_run` parameterised SQL | closed |
| T-03-09 | Information Disclosure | Leaderboard SQLite world-readable | mitigate | `db.py` — `os.chmod(db_path, 0o600)` on first create + drift detection on subsequent opens (commit `859d51b`) | closed |
| T-03-10 | Denial of Service | 1GB result.json crashes orchestrator | mitigate | `ingest.py` — `path.stat().st_size > MAX_RESULT_BYTES` before `read_bytes()` | closed |
| T-03-11 | Tampering | YAML loader code-execution surface | mitigate | `tournament_loader.py:52` — `yaml.safe_load(raw)` with explicit T-03-11 comment | closed |
| T-03-12 | Denial of Service | Pathological grid blowup | mitigate | `tournament_loader.py` — `if len(experiments) > spec.max_experiments: raise ValueError` | closed |
| T-03-13 | Information Disclosure (operator-supplied YAML secrets) | accept | Documented "secrets via env vars not YAML" warning in `example_tournament.yaml` (commit `aca88bc`) | closed |
| T-03-14 | Tampering | Symbol injection (non-Bybit-format) | mitigate | `tournament_loader.py:SYMBOL_RE = ^[A-Z0-9]{2,12}USDT$` per-symbol gate | closed |
| T-03-15 | Elevation of Privilege | Postgres role over-privileged | mitigate | `005_tournament_reader.sql` — `GRANT SELECT ON klines` only; REVOKE INSERT/UPDATE/DELETE/TRUNCATE; REVOKE CREATE | closed |
| T-03-16 | Information Disclosure | Postgres role default password | mitigate | `005_tournament_reader.sql` — placeholder `CHANGE_ME_VIA_ENV`; role unusable until operator runs ALTER ROLE | closed |
| T-03-17 | Information Disclosure | klines schema leakage to read-only role | accept | Documented in 03-05-PLAN.md — historical OHLCV not sensitive | closed |
| T-03-18 | Repudiation | Postgres audit-trail gap on role usage | accept | Documented in 03-05-PLAN.md — TimescaleDB audit-trail extension deferred to v2 | closed |
| T-03-19 | Tampering | Runner spec-json injection | mitigate | `runner/__main__.py` — `json.loads(args.spec_json)` + required-key validation list before any use | closed |
| T-03-20 | Information Disclosure | Runner env-var pass-through | accept | Documented in 03-04-PLAN.md — only GIT_SHA/TS_START logged; no password echo | closed |
| T-03-21 | Information Disclosure | stderr leak of TIMESCALE_PASSWORD via failure_stderr_tail | mitigate | `ingest.py:PASSWORD_SCRUB_RE` + `_scrub(stderr_tail)` before persist | closed |
| T-03-22 | Tampering | Partial result.json on container kill | mitigate | `runner/__main__.py:_atomic_write_result()` — `tempfile.mkstemp` + `os.fsync` + `os.replace` | closed |
| T-03-23 | Tampering | Look-ahead leak via shuffled split | mitigate | `runner/__main__.py` — `train_test_split(..., shuffle=False)` hardcoded; `metrics_bridge.py` import-only TOURN-07 barrier | closed |
| T-03-24 | Elevation of Privilege | Experiment container escape | mitigate | `launcher.py` — `read_only=True`, `cap_drop=["ALL"]`, `tmpfs={"/tmp":"size=512m"}` in `containers.run()` | closed |
| T-03-25 | Tampering | failure_reason enum bypass | mitigate | `failure.py:VALID_FAILURE_REASONS` set + `classify()` enum-only mapping | closed |
| T-03-26 | Information Disclosure | TOURNAMENT_READER_PASSWORD echo via stderr | mitigate | `ingest.py:PASSWORD_SCRUB_RE` regex scrub before DB persist | closed |
| T-03-27 | Denial of Service | Hung experiment container | mitigate | `launcher.py:container.wait(timeout=timeout)` → SIGTERM → sleep(10) → SIGKILL → `remove(force=True)` | closed |
| T-03-28 | Repudiation | Out-of-bounds metric write | mitigate | `result_schema.py:METRIC_RANGES` — psr/dsr ∈ [0,1]; raises ValueError before insert | closed |
| T-03-29 | Tampering | SQL injection through `--where` DSL | mitigate | `queries.py` — `ALLOWED_FILTER_COLS`/`ALLOWED_OPS`/`ALLOWED_ORDER_BY` whitelists; tokeniser; all values via `?` params | closed |
| T-03-30 | Information Disclosure | YAML config secrets-in-comments | mitigate | `example_tournament.yaml` warning comment (commit `aca88bc`); plus T-03-29 whitelist gates field names | closed |
| T-03-31 | Denial of Service | Unbounded `--top` query | mitigate | `queries.py:top = max(1, min(int(top), 10_000))` | closed |
| T-03-32 | Tampering | Partial JSON snapshot on crash | mitigate | `snapshot.py:68-77` — `tempfile.mkstemp` + `os.fsync` + `os.replace` | closed |
| T-03-33 | Repudiation | TOURN-07 grep gate bypass | mitigate | `.github/workflows/tournament-harness.yml:tourn07-grep-gate` job — exits 1 on any forbidden `def` pattern | closed |
| T-03-34 | Tampering | CI workflow elevation surface | accept | Documented in 03-09-PLAN.md — no `pull_request_target`, no auto-merge, repo-scoped secrets only | closed |
| T-03-35 | Information Disclosure | CI test fixtures leaking real creds | mitigate | `tournament-harness.yml` — synthetic password `tournament_test_pwd` in test fixtures only | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-03 | TimescaleDB password follows project-wide 12-factor pattern; rotated via .env (gitignored) | Phase 3 plan author | 2026-05-08 |
| AR-03-02 | T-03-13 | Operator may inadvertently put credentials in YAML; advisory comment in `example_tournament.yaml` warns against this. Whitelist gates in tournament_loader prevent unknown fields | Phase 3 plan author | 2026-05-08 |
| AR-03-03 | T-03-17 | Historical OHLCV bars are non-sensitive; SELECT-only role on `klines` does not expose secrets | Phase 3 plan author | 2026-05-08 |
| AR-03-04 | T-03-18 | TimescaleDB role-usage audit trail deferred to v2 | Phase 3 plan author | 2026-05-08 |
| AR-03-05 | T-03-20 | Runner env-var pass-through limited to GIT_SHA + TS_START; no password echo path | Phase 3 plan author | 2026-05-08 |
| AR-03-06 | T-03-34 | CI uses default `pull_request` trigger only; no `pull_request_target`, no auto-merge, repo-scoped secrets only | Phase 3 plan author | 2026-05-08 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-09 | 35 | 32 | 3 | gsd-security-auditor (initial run) |
| 2026-05-09 | 35 | 35 | 0 | post-fix verification (T-03-09 drift detect + T-03-13/T-03-30 yaml warning) |
