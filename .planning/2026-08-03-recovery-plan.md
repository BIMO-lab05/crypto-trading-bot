# Recovery Plan — 2026-08-03

Source: capital audit (`.planning/audits/2026-08-03-capital-audit.md`) + operator brief.

## Reframe: what is actually wrong

The operator states three problems. After the audit, they rank differently than stated.

| Stated problem | Reality | Effort |
|---|---|---|
| "System thinks it has $10,000" | **Mostly false.** Order sizing correctly reads `settings.paper_initial_balance = 100.0`. P0 = 0. Real defects: 10 P1 sites + 1 inert safety arm + 4 dead env keys. | ~1 session |
| "Claude doesn't understand $100" | **True, and it is a context problem, not a prompting problem.** 87 agent personas + 26.7 KB CLAUDE.md + 1,175 markdown files, many contradictory. The model reads 40 files saying `10000` and one line saying `$100`. | ~0.5 session |
| "Too many/unorganized docs" | **True.** 1,175 md. Also the *cause* of the row above. | ~1 session, batched |
| (unstated, largest) "Most trades lose" | **True and not an engineering problem.** Every strategy has negative Sharpe; the paper engine has no slippage model, so those numbers are already optimistic. | ongoing research |

## P1 — Make $100 real and enforced

**Blocker found: the supplied `shared/account.py` would make things worse, not better.**

It invents env var names that do not match the codebase:

| `shared/account.py` reads | Codebase actually reads | Unit conflict |
|---|---|---|
| `ACCOUNT_EQUITY_USD` | `PAPER_INITIAL_BALANCE` → `settings.paper_initial_balance` | — |
| `MAX_DAILY_LOSS` (fraction, `0.05`) | `MAX_DAILY_LOSS_PCT` → `max_daily_loss_pct` (**percent**, `5.0`) | **100×** |
| `MAX_POSITION_SIZE` (fraction, `0.10`) | `MAX_POSITION_SIZE_PCT` → `max_position_size_pct` (**percent**, `10.0`) | **100×** |
| `MAX_RISK_PER_TRADE` (fraction, `0.10`) | `MAX_RISK_PER_TRADE` (fraction) | ok |

Dropped in as-is it becomes a **sixth** independent source of truth that silently disagrees with `Settings` by 100× on two risk caps. Must be rewritten to read the real keys with the real units, and `Settings` must derive from it (or assert equality at boot) — otherwise "single source of truth" is a slogan, not a fact.

Tasks, in order:

1. Rewrite `shared/account.py` against real key names + units. Keep the good parts: `risk_budget_usd()`, `assert_capital_is_sane()`, `capital_config_warnings()`, the min-notional and fee-drag checks.
2. `Settings` (trading-engine `config.py`) derives defaults from `shared.account`; boot asserts they agree.
3. `tests/test_account_size_invariant.py` — fails on any capital-named variable assigned a bare literal. Validate against known-good lines (`REDIS_MAX_CONNECTIONS=50`, `WS_MAX_RECONNECT_ATTEMPTS=10`) to confirm zero false positives.
4. **Safety, highest value:** `trading_enhancements/kill_switch.py:65` `max_position_value = 100000.0`, never overridden at `auto_trader.py:342`. On $100 this arm can never fire. Derive from equity.
5. `handlers/performance_dashboard.py:491` — pass `initial_balance`; delete the `10000.0` default so omission is a TypeError.
6. `handlers/statistical_arbitrage.py:49` `total_capital = 100000.0` (1000× off) and `managers/statistical_arbitrage_manager.py:90` (`10000.0`).
7. `.env` hygiene: `MAX_DAILY_LOSS=0.10` is dead twice (wrong name AND fails `ge=1.0` validation) → operator's intended 10% daily limit **has never been in effect**; effective is 5.0%. Delete dead `PAPER_TRADING_INITIAL_BALANCE`, `BACKTEST_INITIAL_CAPITAL`.
8. Remaining 8 P1 backtest/metrics defaults.

**Operator decision required at step 7:** per-trade cap 10% vs daily breaker 5% — one max-size loser trips the breaker. Raise equity, lower per-trade, or widen daily deliberately + file an ADR. Not an engineering call.

## P2 — Fix Claude's context

This is the real fix for "the brain doesn't understand".

- CLAUDE.md: **merge, do not replace.** The supplied 7 KB version was written without reading the current one and drops load-bearing facts (ADR-010 cap, kill-switch resume semantics, 2026-04-25 testnet-pollution cutoff, `docker-compose.unified.yml` vs `docker-compose.yml`, the `Path.write_text` mocking trap, api-gateway container-vs-host fastapi). Put the money constraint first; keep the gotchas.
- Park 87 personas → keep ~8 that touch a trading bot. Reversible (`git mv` to `_parked/`).
- Scoped instructions so deep guidance loads only when relevant, instead of every session.

## P3 — Docs cull

1,175 md → target ~200. Contradiction table first (docs claiming what code refutes), then a `git mv` script, approved one directory per batch. Nothing deleted. `wiki/` stays the only ADR home.

## P4 — The trading problem

Not fixable by agents or docs. Sequence:

1. Add a slippage model to the paper engine (PAPER-01) — modelled on real Bybit spreads per symbol, not a flat constant. Without it every number is optimistic.
2. Re-run backtests at $100 with min-notional rejection + round-trip fees. **Expect worse, not better.**
3. Gate every result on DSR/CPCV before it is called an edge.

Do not add a sixth indicator to five losing indicators. The infrastructure's value right now is killing bad strategies cheaply.

## Sequencing

P1 → P2 → (P3 ‖ P4). P3 and P4 touch disjoint files and can run in parallel worktrees.
