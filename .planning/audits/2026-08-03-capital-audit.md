# Capital Audit — 2026-08-03

**Invariant under test:** real account equity is $100 USDT, sourced from one place.

## Summary

- **P0 (order-size path, strict litmus): 0.** Every candidate that looked like a live sizing defect was traced to its call site and failed the litmus (`does a paper or live order's size depend on this value at runtime?`) — see "Traced and cleared" below. The one genuinely wired, high-consequence defect found (`kill_switch.py` safety threshold) does not size an order, it gates whether one halts, so it is reported separately rather than mislabeled P0.
- **P1 (backtest/walk-forward/metrics default): 8 locations** (some with multiple line hits) — trading-engine's own backtester, risk-metrics-service's backtester and live VaR/CVaR fallback, two repo-root Monte-Carlo/risk-of-ruin simulators, technical-analysis's standalone backtester, and one dead `.env` key.
- **P2 (test fixture): 55 hits across 11 files** in `services/*/tests/` matched the literal assignment pattern; a broader (noisier) sweep for any capital-shaped literal anywhere under a `test_*.py` name returned 180 files — not opened individually, see Method note.
- **P3 (docstring/comment/example, incl. one dead-code / one dead-logic item): 10 locations**, capped list below.
- **Single source of truth for account size: NO.** At least five independent mechanisms currently determine "account size" at runtime or in config, with no shared module: trading-engine `Settings.paper_initial_balance` (env `PAPER_INITIAL_BALANCE`, correctly 100.0), portfolio-manager `Settings.initial_capital` (env `INITIAL_CAPITAL`, unset anywhere, defaults correctly to 100.0), risk-metrics-service's per-call fallback to a portfolio-manager API field (defaults to 10000 on missing data), the `portfolios` Postgres table's `initial_balance` column (see DB-state finding below), and two unrelated dataclass defaults (`OrchestratorConfig.total_capital`, `BudgetConfig.total_capital`) both hardcoded to 100000.0. `shared/account.py` does not exist anywhere in the repo — confirmed via `find`.
- **Raw hits scanned:** 861 lines matched the capital-related variable-name grep (`initial_capital|initial_balance|starting_capital|account_balance|account_equity|portfolio_value|PAPER_TRADING_INITIAL_BALANCE|BACKTEST_INITIAL_CAPITAL`); 2,293 lines matched the bare numeric-literal grep (`10000|10_000|10000.0|100000|50000|1000.0`) across `.py`/`.yml`/`.yaml`/`.json`/`.md`. These overlap substantially and were triaged by directory/live-wiring rather than opened one by one — see Method note.

### Method note (read before the tables)

Given the volume (≈3,000 raw grep lines), every P0/P1 row below was opened and traced to its call site — that work is described inline. The P2/P3 buckets were triaged at the directory/file level (ranked by hit density, e.g. `grep -c` per file) rather than every one of the ~235 P2/P3 lines being individually read; the rows given are the highest-confidence, highest-reinfection-risk representatives, not an exhaustive audit of every test and docstring. Do not read the P2/P3 counts as precise line-by-line-verified totals the way the P0/P1 rows are.

**NOT A DEFECT:** not separately counted as a global number — the numeric-literal sweep is dominated by timeouts, ms/byte values, row limits (e.g. `portfolio-manager/app/services/performance_history.py:303` `"all": 10000  # Large number to get all data`), port numbers, and rate/array bounds that happen to contain `1000`/`10000`. Spot-checks across `bybit-connector`, `market-data-service`, `ml-prediction-service`, `sentiment-analysis-service`, and `api-gateway` found **zero** capital-shaped hits in any `app/` directory for those five services — the defect surface is concentrated entirely in `trading-engine`, `portfolio-manager`, and `risk-metrics-service`.

---

## P0 — order-size path (strict litmus)

**None.** Traced every plausible candidate to its call site; none reach the actual order-execution function.

### Traced and cleared (why they are NOT P0)

| Candidate | File:Line | Why it fails the litmus |
|---|---|---|
| SQZMOM manual-trade endpoint | `services/trading-engine/app/main.py:1079-1148` | `account_balance: float = Query(default=10000.0, ...)` feeds `calculate_position_size(...)`, but the endpoint's own response says `"note": "This is a simulated trade - actual execution not implemented yet"` (line 1174). It returns computed JSON; it does not call `execute_market_order`. |
| Auto-trader slippage estimate | `services/trading-engine/app/auto_trader.py:1839-1848` | `position_value_estimate = entry_price * position_size_pct * 10000` feeds `should_use_limit_order(...)`, but `should_use_limit` is only ever read once more — inside `if should_use_limit: logger.info(...)` at line 1847. Confirmed via `grep -n should_use_limit auto_trader.py`: two occurrences total, both at the computation site. It controls a log line, nothing else. Reclassified to P3 below. |
| Statistical-arbitrage endpoints | `services/trading-engine/app/main.py:1309-1310` (`total_capital` default 100000.0), `main.py:1419-1420` (`max_position_size` default 10000.0), `managers/statistical_arbitrage_manager.py:90`, `strategies/funding_rate_arbitrage.py:252`, `strategies/pairs_trading.py:259` | `grep -rn "place_order\|execute_trade\|open_position\|submit_order\|paper_engine\.\|position_manager\.(open\|execute)"` across `handlers/statistical_arbitrage.py`, `handlers/orchestration.py`, `managers/statistical_arbitrage_manager.py`, `orchestration/orchestrator.py` returned zero order-placement calls. These endpoints compute and return allocations/signals over HTTP only. |
| Strategy Orchestrator | `services/trading-engine/app/orchestration/models.py:678` (`OrchestratorConfig.total_capital = 100000.0`), instantiated via `get_strategy_orchestrator()` with no override anywhere (`grep` for `get_strategy_orchestrator\|OrchestratorConfig` in `main.py`/`auto_trader.py`/`lifespan/*.py` = 0 hits) | Router is live-mounted (`main.py:460 app.include_router(orchestration_router)`), and every handler calls `get_strategy_orchestrator()` with no args, so `total_capital` is permanently stuck at 100000.0. But same order-placement grep above returned nothing — it manages allocation bookkeeping and rebalance signals only, no execution path. |

### Highest-impact live-wired defect (fails the strict P0 litmus on a technicality — gates execution, not size)

`services/trading-engine/app/trading_enhancements/kill_switch.py:65`
```
max_position_value: float = 100000.0  # Stop if single position exceeds value
```
`KillSwitchConfig` is instantiated at `auto_trader.py:342`:
```python
self.kill_switch = get_kill_switch(
    KillSwitchConfig(
        max_daily_loss_pct=self.settings.max_daily_loss_pct,
    )
)
```
Only `max_daily_loss_pct` is overridden — `max_position_value` keeps its 100000.0 default. It is checked at `kill_switch.py:249` (`if position_value >= self.config.max_position_value: triggered.append("max_position_value")`), and `should_halt_trading()` gates every trade attempt at `auto_trader.py:908` and `auto_trader.py:1700`. On a $100 account no position can ever reach $100,000 — this specific kill-switch trigger is permanently dead. It does not affect order *size*, so it is excluded from the P0 count by the letter of the litmus, but it is the single highest-consequence capital-scale defect in the repo: one of the safety net's stop conditions cannot fire.

### DB-state defect (documented in a code comment, not independently verified — Postgres was not running to check)

`services/trading-engine/app/repositories.py:367-370`:
```
initial_balance: Initial balance for new portfolio. Defaults to the
    configured paper-trading balance (``PAPER_INITIAL_BALANCE``).
    The previous hardcoded $10,000 default is what wrote the stale
    `portfolios.initial_balance = 10000` row on 2026-04-27.
```
The code is already fixed (`get_or_create` now reads `settings.paper_initial_balance`), but `get_or_create` only creates a row if one doesn't already exist — it never repairs an existing row. If the `portfolio_id='paper_trading'` row was created before the 2026-04-27 fix and the service has run continuously since, that row's `initial_balance` is still 10000 today, which would poison every ROI%/drawdown calculation derived from it by 100x. **Status: unverified — no live DB to query.** Verify with:
```sql
SELECT portfolio_id, initial_balance FROM portfolios WHERE portfolio_id = 'paper_trading';
```

---

## P1 — backtest / walk-forward / metrics default

| Priority | File:Line | Current value | What it controls | Replacement |
|---|---|---|---|---|
| P1 | `services/trading-engine/app/strategies/backtester.py:131-133,216,294,1007` | `initial_capital: float = 10000.0` (repeated across `BacktestResult`, `BacktestConfig`, factory default) | All P&L%, drawdown%, and daily-loss% math in trading-engine's own backtest engine | `100.0`, sourced from `get_settings().paper_initial_balance` |
| P1 | `services/risk-metrics-service/app/backtest_models.py:16` | `initial_capital: Decimal = Field(default=Decimal("10000"))` | Starting capital for risk-metrics-service backtests | `Decimal("100")` |
| P1 | `services/risk-metrics-service/app/backtesting.py:126` | `initial_capital: Decimal = Decimal("10000")` (default param of `run_multiple`) | Multi-strategy backtest comparison capital base | `Decimal("100")` |
| P1 | `services/risk-metrics-service/app/main.py:529,667,704,740,788,853,940` | `Decimal(str(portfolio.get("total_value", 10000)))` (7 identical call sites) | **Live** VaR/CVaR/risk-dashboard fallback when the portfolio-manager API response is missing `total_value` — not historical, but a metrics computation, not an order-sizing path | `Decimal(str(portfolio.get("total_value", 100)))`, or fail loudly instead of silently defaulting |
| P1 | `backtesting/simulators/risk_of_ruin.py:37,168,518` | `initial_capital: float = 10000.0` | Repo-root Monte-Carlo risk-of-ruin simulator's capital base | `100.0` |
| P1 | `backtesting/simulators/monte_carlo.py:37,421` | `initial_capital: float = 10000.0` | Repo-root Monte-Carlo equity-curve simulator's capital base | `100.0` |
| P1 | `services/technical-analysis/backtesting/sqzmom_backtest.py:135,149,156` | `initial_capital: float = 10000.0` (default param, then stored) | Standalone SQZMOM backtester used by `run_backtest.py`, `run_btc_eth_backtest.py`, `quick_test.py`, `optimize_parameters.py` (all call it with the same literal explicitly) | `100.0` |
| P1 | `.env:299`, `.env.example:288` | `BACKTEST_INITIAL_CAPITAL=10000.0` | Nothing currently — confirmed via `grep -rn "BACKTEST_INITIAL_CAPITAL"` across the tree: zero Python references. Dead key that looks authoritative to an operator | Either wire it up as `100.0` or delete it |

---

## P2 — test fixture (top rows; 55 hits / 11 files matched the strict pattern in `services/*/tests/`; 180 files matched a broader "any capital literal in a test-named file" sweep across the repo, not individually opened)

| Priority | File:Line | Current value | What it controls | Replacement |
|---|---|---|---|---|
| P2 | `services/trading-engine/tests/strategies/test_funding_rate_arbitrage.py:122` (+12 more in file) | `portfolio_value = 10000.0` | Locks funding-rate-arb sizing tests to a $10k basis | `100.0` |
| P2 | `services/trading-engine/tests/analytics/test_advanced_metrics.py:152` (+8 more, incl. a `50000.0` at line 184/197/205) | `initial_capital=10000.0` | Advanced-metrics calculator test suite | `100.0` |
| P2 | `services/trading-engine/tests/strategies/test_pairs_trading.py:239` (+6 more) | `portfolio_value=10000.0` | Pairs-trading sizing tests | `100.0` |
| P2 | `services/trading-engine/tests/integration/test_statistical_arbitrage_integration.py:138` (+6 more) | `portfolio_value=10000.0` | Stat-arb integration tests | `100.0` |
| P2 | `services/trading-engine/tests/risk/test_sector_exposure.py:272` (+5 more) | `portfolio_value = 100000` | Sector-exposure concentration tests | `100.0` |
| P2 | `services/trading-engine/tests/test_multi_strategy_orchestration.py:627,639,658` | `initial_capital=10000.0` | Multi-strategy orchestration tests | `100.0` |
| P2 | `services/trading-engine/tests/analytics/test_attribution.py:61,852,859` | `initial_capital=10000.0` | Attribution-analyzer test fixtures | `100.0` |
| P2 | `services/trading-engine/tests/test_sqzmom_strategy.py:160,172` | `account_balance=10000.0` | SQZMOM position-sizing tests | `100.0` |
| P2 | `services/trading-engine/tests/risk/test_diversification_calculator.py:650` (+1 more) | `portfolio_value=100000` | Diversification/concentration tests | `100.0` |
| P2 | `services/portfolio-manager/tests/test_portfolio_optimizer.py:305,556` | `portfolio_value = 10000.0` | Portfolio-optimizer rebalance tests | `100.0` |
| P2 | `services/trading-engine/tests/unit/test_advanced_metrics.py:61` | `initial_capital=10000.0` | Duplicate of the analytics suite above under `unit/` | `100.0` |

Remaining count: **~169 additional files** matched the broader test-file sweep (root-level `test_*.py`, `run_*.py`, walk-forward scripts such as `test_sr_strategy_walkforward.py`, `test_loss_fixes.py`, `run_walk_forward*.py`) not enumerated here.

---

## P3 — docstring / comment / example (capped at 15; some entries are dead code / dead logic, flagged as such — high reinfection risk because they read as working examples)

| Priority | File:Line | Current value | What it controls | Replacement |
|---|---|---|---|---|
| P3 | `services/trading-engine/app/handlers/risk_kelly.py:110-111,162,164,182-183,209` | `capital=10000`, `current_price=50000` (`Field` default on `KellySimulateRequest` + `json_schema_extra` examples) | Kelly "what-if" simulate endpoint's default and OpenAPI example — not the real `kelly-calculate` endpoint, whose `capital` field is required (`Field(..., gt=0)`, no default) | `100`, `~60000` |
| P3 | `services/trading-engine/app/handlers/risk_budget.py:79,235,359` | `"base_equity": 100000.0` (all inside `Config.json_schema_extra` response examples) | OpenAPI docs only | `100.0` |
| P3 | `services/trading-engine/app/risk/diversification_calculator.py:1204,1255` | `position_value=10000`, `portfolio_value=100000` | `if __name__ == "__main__"` demo block | `100.0`-scale example |
| P3 | `services/trading-engine/app/risk/sector_exposure.py:1272-1298` | `position_value=50000`, `entry_price=100000`, `portfolio_value = 100000` | `__main__` demo block | `100.0`-scale example |
| P3 | `services/trading-engine/app/risk/kelly_position_sizing.py:155-156,829-830` | `capital=10000`, `current_price=50000` | Docstring/demo defaults | `100`-scale example |
| P3 | `services/trading-engine/app/risk/dynamic_budget.py:69,121` | `total_capital: float = 100000.0` | **Dead code** — `grep -rn "from app.risk.dynamic_budget import"` outside the file itself returns zero hits; superseded by `dynamic_risk_budget.py` (which is correctly wired to `RISK_BUDGET_INITIAL`, default `100.0`, and is what `lifespan/risk.py` actually calls). Recommend deleting the module, not fixing the literal | n/a — delete |
| P3 | `services/trading-engine/app/auto_trader.py:1840` | `entry_price * position_size_pct * 10000` | Dead logic — only feeds a log line (see P0-cleared table above) | Remove the `* 10000` or wire it to real position value; currently misleading to read as functional |
| P3 | `services/technical-analysis/backtesting/README.md:92`, `DELIVERY_SUMMARY.md:242`, `BACKTEST_IMPLEMENTATION_COMPLETE.md:227` | `initial_capital=10000.0` | Doc examples for the standalone SQZMOM backtester | `100.0` |
| P3 | `database/migrations/005_seed_data.sql:35` | `RAISE NOTICE '... Default portfolio created with $10,000 balance'` | Log message only — the actual `INSERT` two lines above correctly uses `100.00`; the notice text is simply stale/wrong | Fix the string to say `$100` |

Remaining count: not exhaustively enumerated — the P2 sweep above (180 files) and the numeric-literal sweep (2,293 lines) both contain additional docstring/comment matches not individually triaged.

---

## Env drift

| Key | `.env` | `.env.example` | `.env.production.example` | compose (`docker-compose.yml` / `.unified.yml`) | k8s / infrastructure | Read by code? | Correct value |
|---|---|---|---|---|---|---|---|
| `PAPER_INITIAL_BALANCE` (actual field name trading-engine reads) | not set | not set | not set | base: `=100.0`; unified: `=100.0` | `trading-engine-deployment.yaml`="100"; `staging/configmap.yaml`="100" (×2) | **Yes** (`Settings.paper_initial_balance`, `case_sensitive=False`, no alias) | `100.0` — consistent everywhere it's actually read |
| `PAPER_TRADING_INITIAL_BALANCE` (wrong key — extra `_TRADING_`) | `=100.0` | `=10000.0` | not set | not set | not set | **No** — no field named `paper_trading_initial_balance`; silently dropped (`extra="ignore"`) | dead key; delete or rename to `PAPER_INITIAL_BALANCE` |
| `BACKTEST_INITIAL_CAPITAL` | `=10000.0` | `=10000.0` | not set | not set | not set | **No** — zero Python references anywhere | dead key |
| `INITIAL_CAPITAL` (portfolio-manager's actual field name) | not set | not set | not set | not set anywhere | not set | Yes, but never overridden — always falls back to the correct `Field(default=100.0)` | `100.0` (already correct by omission) |
| `MAX_RISK_PER_TRADE` | `=0.10` | `=0.02` | `=0.02` | base: `=0.05`; unified: `=${MAX_RISK_PER_TRADE:-0.10}` (reads `.env`, so effectively `0.10`) | not set anywhere in `infrastructure/` | Yes (`Settings.max_risk_per_trade`, fraction 0–0.5) | Effective (unified compose, canonical): **0.10** |
| `MAX_DAILY_LOSS` (wrong key — missing `_PCT`) | `=0.10` | `=0.05` | not set | not set | `app-config.yaml`="0.05"; `production/configmap.yaml`="0.05" | **No** — field is `max_daily_loss_pct`; dead everywhere it appears | dead key |
| `MAX_DAILY_LOSS_PCT` (correct key) | not set | not set | not set | base: `=5.0`; unified: not set | `trading-engine-deployment.yaml`="3"; `staging/configmap.yaml`="3" (×2) | Yes (`Settings.max_daily_loss_pct`, percent 1–20) | Effective (unified compose, canonical): **5.0 (Settings default, since unified never sets it)** |
| `MAX_DAILY_LOSS_PERCENT` (yet a third variant) | not set | not set | not set | not set | `hardened-deployments.yaml`="5" | **No** — matches no field | dead key |

## Risk-cap reconciliation

As found, canonical (`docker-compose.unified.yml`) path:
- `MAX_RISK_PER_TRADE` → effective **0.10** (10%, via `${MAX_RISK_PER_TRADE:-0.10}` reading `.env`)
- `MAX_DAILY_LOSS_PCT` → effective **5.0** (5%; unified compose sets nothing, so the `Settings` default applies — `.env`'s `MAX_DAILY_LOSS=0.10` never reaches the field because of the name mismatch above)

**Yes** — a single max-risk trade (10% of balance) exceeds the daily-loss circuit breaker (5% of balance). One stopped-out max-size trade alone can blow past the daily kill-switch threshold in a single fill.

---

## Blast radius

Result/report files whose numbers were computed against a $10,000/$100,000 basis and are invalidated for anything claiming relevance to the real $100 account:

- `comprehensive_FINAL_RESULTS.log` (repo root)
- `grid_FINAL_RESULTS.log` (repo root)
- `sr_FINAL_RESULTS.log` (repo root)
- `trend_FINAL_RESULTS.log` (repo root)
- `services/technical-analysis/backtesting/backtest_results.json` (`"initial_capital": 10000.0`)
- `services/technical-analysis/backtesting/backtest_results_OLD_TEST_DATA.json` (`"initial_capital": 10000.0`)
- `services/technical-analysis/backtesting/btc_eth_real_data_results.json` (`"initial_capital": 10000.0`)
- `docs/archive/backtesting-2025/BACKTEST_RESULTS_2025-11-04.md` (`**Initial Capital**: $10,000`)

These are especially misleading given ADR-010: paper-trading's per-trade cap was raised from 2% to 10% specifically to clear Bybit's minimum-notional floor on a $100 balance. Backtests run at $10,000 never hit that constraint, so win-rate/Sharpe/drawdown figures in the files above do not reflect the sizing regime the bot actually trades under.

---

# Verification Addendum (main-thread review, 2026-08-03)

The audit above was spot-checked against the six files named in the original task brief. **The audit never opened any of them.** Five live under `services/trading-engine/app/`. Findings below are verified by reading call sites, not grep lines.

## A1 — MISSED DEFECT, reachable, live API handler

`services/trading-engine/app/handlers/performance_dashboard.py:209`

```python
def calculate_equity_curve_from_trades(
    trades: List[Any], initial_balance: float = 10000.0
) -> List[Dict[str, Any]]:
```

Three call sites in the same file:

| Line | Call | Uses default? |
|---|---|---|
| 491 | `calculate_equity_curve_from_trades(filtered_positions)` | **YES — $10,000** |
| 576 | `calculate_equity_curve_from_trades(filtered_positions, initial_balance)` | no |
| 634 | `calculate_equity_curve_from_trades(filtered_positions, initial_balance)` | no |

Line 491 feeds `calculate_drawdown_series()` → `max_drawdown` returned by a live dashboard endpoint. **Max drawdown on that endpoint is computed against a $10,000 baseline while sibling endpoints use the real balance** — the two disagree by 100×. Not an order-size defect (so not P0 by the litmus), but it is live-reported metric corruption and an internal inconsistency within one file.

**Priority: P1-high. Fix: pass `initial_balance` at line 491; delete the default so omission is a TypeError.**

## A2 — MISSED, $100,000 default (1000× the real account)

`services/trading-engine/app/handlers/statistical_arbitrage.py:49` — `total_capital: float = 100000.0`

Flows: handler:94 → `StatisticalArbitrageManager(total_capital=...)` → manager:311/337 `portfolio_value=self.total_capital * allocation` → `PairsTradingStrategy.generate_signal()` / `FundingRateArbitrageStrategy.generate_signal()`. So this value **does** size stat-arb signals. The audit's claim that stat-arb never reaches `execute_market_order` is what keeps it off P0; the sizing itself is still wrong by 1000×.

`services/trading-engine/app/managers/statistical_arbitrage_manager.py:90` — `total_capital: float = 10000.0` (second, independent wrong default on the same path). Docstring example at `:74` repeats it.

**Priority: P1-high.**

## A3 — Brief was WRONG on these; do not "fix" them

- `kelly_position_sizing.py:311` `calculate_position_size(self, capital: float, ...)` — **no default**. Caller must supply capital. The real Kelly sizing path is clean.
- `kelly_position_sizing.py:829` — `capital: float = 10000` belongs to `simulate_kelly()`, an explicitly hypothetical what-if helper. **P3.**
- `kelly_position_sizing.py:155` — docstring example. **P3.**
- `pairs_trading.py:259` / `funding_rate_arbitrage.py:252` — `portfolio_value: float = 10000.0` defaults are **shadowed**: the manager always passes the argument explicitly. Dead defaults. Fix the source in A2, not these. **P3 (reinfection risk only).**
- `handlers/attribution.py:380` — not a capital literal at all; it is an OpenAPI route description. **NOT A DEFECT.** (Note: two `attribution.py` files exist — `app/handlers/` and `app/analytics/`; the brief did not disambiguate.)
- `analytics/advanced_metrics.py:724` — `PerformanceAnalyzer.__init__(initial_capital: float = 10000.0)`. Grep finds **zero** `PerformanceAnalyzer(` construction sites anywhere in `services/`. Currently dead code. **P3.**

## A4 — Confirmed from the audit, unchanged

- **P0 = 0 stands.** No order-size path depends on a wrong capital literal. `paper_engine` sources balance from `settings.paper_initial_balance` (`config.py:557`, default 100.0).
- `kill_switch.py:65` `max_position_value: float = 100000.0`, never overridden at `auto_trader.py:342` — on a $100 account this threshold is unreachable, so that kill-switch arm is inert. Real, and the single highest-value item in the whole audit.
- `shared/account.py` does not exist. No single source of truth.

## Revised counts

| Priority | Audit said | After verification |
|---|---|---|
| P0 | 0 | 0 (confirmed) |
| P1 | 8 | 10 (+A1, +A2) |
| P3 | 10 | 15 (+5 from A3) |
| NOT A DEFECT | — | +1 (`handlers/attribution.py:380`) |

## Caveat on coverage

The audit missed six files that were handed to it by name. Its P2 accounting is self-reported as partial ("55 hits / 11 files audited, 180 files matched a broader unaudited sweep"). Treat the P2/P3 sections as a sample, not a census. P0/P1 have now been independently checked and are trustworthy.

## A5 — Risk-cap keys verified against `config.py` (units matter)

| Field | `config.py` | Unit | Env key it reads | `.env` sets | In effect? |
|---|---|---|---|---|---|
| `max_risk_per_trade` | :321 default `0.10`, `ge=0.001 le=0.5` | **fraction** | `MAX_RISK_PER_TRADE` | `0.10` ✔ | **yes — 10%** |
| `max_daily_loss_pct` | :364 default `5.0`, `ge=1.0 le=20.0` | **percent** | `MAX_DAILY_LOSS_PCT` | not set | **falls back to 5.0%** |
| `max_position_size_pct` | :311 default `10.0` | percent | `MAX_POSITION_SIZE_PCT` | — | 10% |

`.env` sets `MAX_DAILY_LOSS=0.10`. That key is dead **twice over**: (1) wrong name — the field reads `MAX_DAILY_LOSS_PCT`; (2) wrong unit — `0.10` would fail `ge=1.0` validation even under the right name. **The operator's intended 10% daily-loss limit has never been in effect.** Effective daily loss limit is the code default, 5.0%.

Confirms the audit's "effective 5.0" — and it comes from `Settings`, not from the `KillSwitchConfig.max_daily_loss_pct = 5.0` default at `kill_switch.py:63` (that one *is* overridden, `auto_trader.py:343` passes `settings.max_daily_loss_pct` through).

Consequence, as-found (not fixed here): per-trade cap 10% of balance vs daily-loss breaker 5% — **one maximally-sized losing trade trips the daily breaker**. Downstream of ADR-010. Risk-policy call, left for the operator.
