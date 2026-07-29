# WIP Verification — uncommitted out-of-band work (2026-07-29)

Independent re-run of every claim in `FIXES_2026-07-28_COMPREHENSIVE.md` and
`AUDIT_2026-07-29_PRODUCTION_REVIEW.md`, before deciding whether to commit the
367 uncommitted paths. Nothing below is quoted from those reports — each row is
a command run this session.

**Verdict: the substantive claims hold. No regression traceable to the
uncommitted work. Two report claims are overstated and one documented command
does not work as written.**

---

## 1. Results

| Claim | Verdict | Evidence |
|---|---|---|
| Accounting harness 28/28 | **CONFIRMED** | `python3 tests/standalone/test_accounting_fixes.py` → `RESULT: 28 passed, 0 failed` (host). T1–T11 incl. SHORT round-trips, reduce-only rejection, partial closes, leverage, kill-switch equity semantics, UTC daily rollover |
| Indicator harness 16/16 | **CONFIRMED** | `python3 tests/standalone/test_indicator_fixes.py` → `RESULT: 16 passed, 0 failed` (host) |
| api-gateway pytest 437/437 | **CONFIRMED** | `docker exec -e ENVIRONMENT=test crypto-bot-api-gateway pytest -q` → `437 passed in 51.14s` |
| trading-engine `1403 passed / 628 skipped` | **PARTIALLY CONFIRMED** | Operator's own log `cowork_run/te_pytest2.log` shows `11 failed, 1403 passed, 628 skipped` — the report's §5 accounts for 9 and calls the other 2 "now green on re-run". Independently re-ran those 2 files: green (below). The pass/skip counts are real. |
| "9 pre-existing failures" | **CONSISTENT** (reporting discrepancy elsewhere) | 9 pre-existing + the 2 test-fixes §5 says were made green = the 11 in the log. Arithmetic checks out and both of those 2 are green here. The actual discrepancy is `cowork_run/STATUS.txt` line 5a recording `5a. trading-engine pytest FAILED (exit 2)` while the report presents the suite as validated. |
| Auth is "mode-gated" (open in local paper, enforced otherwise) | **CONFIRMED — fails closed** | `auth_middleware.py:40-64` `api_auth_required()` returns True when `ENVIRONMENT in {production, staging}`, `TRADING_MODE=LIVE`, or `PAPER_TRADING_MODE=false`. Running gateway: `REQUIRE_API_AUTH=<unset> TRADING_MODE=PAPER PAPER_TRADING_MODE=true` → correctly open. Read fresh per call, so a runtime flip is honored. **Residual risk:** an explicit `REQUIRE_API_AUTH=false` wins over LIVE (line 50-52) — documented as "NOT for real money", but it is a real-money footgun worth a boot-time hard-fail like the JWT one. |
| Frontend production build | **CONFIRMED** | `vite build` → `✓ 2635 modules transformed`, exit 0 |
| Frontend lint | **CONFIRMED** | project script `eslint src --ext .js,.jsx,.ts,.tsx` → `0 errors, 67 warnings`, exit 0 |
| 8/9 services HTTP 200 | **CONFIRMED** | 8000/8001/8002/8003/8004/8005/8006/8009 → 200. 8007 (ml-prediction) and 8008 (sentiment) absent/idle by feature gate. Note `:8000/health` takes ~4.1s — a 5s-timeout probe reads it as a failure |
| max mainnet BTC close $82,791 | **CONFIRMED EXACTLY** | `SELECT is_mainnet, count(*), max(close) FROM klines WHERE symbol='BTCUSDT' GROUP BY is_mainnet` → `t: 22417 rows, 82791.20` / `f: 22426 rows, 125981.30`. The $1.76M artefact is gone. Pre-flip rows are **tagged, not deleted** — backtests must filter `is_mainnet=true` |
| Containers carry the uncommitted code | **CONFIRMED** | `reduce_only` count, `content=` HMAC fix, TA candle-validation string, `security/rate_limiter.py` all present in running containers and match host |

## 2. Regression check — is any failure caused by this work?

**No.** Two independent comparisons against a clean `git worktree` at HEAD (`2aac085`):

| File | Working tree | Clean HEAD | Read |
|---|---|---|---|
| `tests/unit/test_repositories.py` (alone) | 21 passed | 21 passed | clean |
| `tests/strategies/test_pairs_trading.py` + `test_handler_endpoints.py` | 11 failed, 33 passed, 1 skipped | **identical** | pre-existing |

The 21 `test_repositories.py` failures that appear in a full-suite host run are
**test-order pollution** — the same file passes 21/21 in isolation on both trees.

Files the uncommitted work modified, plus Phase 18's own tests, run green:

```
tests/test_te_cap_05_log_survival.py    ..        (2)
tests/unit/test_auto_trader.py          ......... (45)
tests/test_performance_dashboard_tz.py  .....     (5)
tests/test_bybit_adapter_contract.py    ...       (3)
tests/test_bybit_adapter_wr01_wr04.py   .......   (7)
                                  62 passed in 120.82s
```

## 3. Real problems found (not in either report)

1. **`docker exec crypto-bot-trading pytest tests/` cannot collect.** Four fatal
   collection errors, so the documented verification command yields zero tests:
   - `tests/integration/conftest.py:47` — `ModuleNotFoundError: No module named 'database'`. It computes `parents[5]/shared`, correct on host, wrong in-container; `/app/shared` exists but is **empty**.
   - `tests/test_bybit_adapter_wr01_wr04.py` and `tests/test_exchanges.py` — `ModuleNotFoundError: No module named 'jwt'` via `app/exchanges/coinbase.py:33`. **PyJWT is missing from the trading-engine image.** Note this kills Phase 18's own e2e test file in-container.
   - `tests/test_config_default_on_gate.py:48` — `IndexError: 3` from `parents[3]`, same host-layout assumption.
2. **`services/trading-engine/.dockerignore` (new, untracked) excludes `tests/standalone/`** — the accounting harness. The running image predates it, so the harness is still there; the next rebuild removes the evidence base from the container.
3. **`.planning/state/carry_ins.json`** is mode `600` owned by uid `999`. It aborted `git diff` this session and will likely break `gsd-sdk query init.resume`.
4. **`frontend/dist/assets` is owned by root** (container-written), so a host `vite build` fails at `emptyDir` with `EACCES`. Building to another `--outDir` succeeds.
5. `GET :8000/ready` returns 404 — CLAUDE.md claims every service exposes `/ready`.

## 4. Provenance

`cowork_run/` holds the original session's evidence: `STATUS.txt` (18-step
runner), `run_all_steps.ps1`, `te_pytest2.log`, `gw_pytest*.log`, `rebuild2.log`.
`_to_delete/` holds 15 transfer tarballs (`round2_audit.tar.gz`, `round3.tar.gz`,
`dockerignore.tar.gz`, `compose_fix.tar.gz`, …). The work was produced by an
external "cowork" agent run on 2026-07-29 between 14:04 and 18:24, transferred
in as tarballs.

## 5. Not run

- `scripts/repair_testnet_pollution.sh` — deletes/retags TimescaleDB rows.
  Operator action (OP-08), needs explicit go-ahead. The DB already shows the
  post-repair state, so it appears to have been run once already.
- Service rebuild/restart (OP-09) — containers already carry the code.
- 2–4 week paper-trading profitability evaluation — wall-clock bound.

---

_Verified: 2026-07-29 · re-run independently, not quoted from the reports_
