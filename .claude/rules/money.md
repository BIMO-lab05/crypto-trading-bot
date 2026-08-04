---
paths:
  - "services/trading-engine/**/*.py"
  - "services/portfolio-manager/**/*.py"
  - "services/risk-metrics-service/**/*.py"
  - "backtesting/**/*.py"
  - "scripts/*backtest*.py"
  - "scripts/test_*.py"
  - "shared/**/*.py"
---

# Money rules — you are editing a file that sizes or accounts for real capital

## Account size

The account is **$100 USDT**. `shared/account.py` is the declaration of record. Never write the number as a literal.

**How you reference it depends on where the file runs — this is not stylistic.**

| Location | In a container? | Rule |
|---|---|---|
| `services/*/app/**` | **YES** | Read the service's own `Settings` (`settings.paper_initial_balance`). **Never `import shared.account`** — it will `ImportError` at runtime. |
| `backtesting/**`, `services/*/backtesting/**`, `tests/**`, `services/*/tests/**` | no (host-run) | `from shared.account import ...` directly. |

Why: every service builds with `context: ./services/<name>`, so repo-root `shared/` is outside the build context, and all Dockerfiles `COPY` only `app/`. The apparent precedent in `portfolio-manager/app/handlers/health.py:48` is a **dead** import — its Dockerfile does `RUN mkdir -p ./shared` (empty) and the import sits inside `except ImportError`. Agreement between `Settings` and `shared/account.py` is enforced by `tests/test_account_config_sync.py`, not by a shared import.

Forbidden in any file matching these paths:

```python
initial_capital: float = 10000.0        # NO
initial_balance = 10000                 # NO
portfolio_value: float = 10000.0        # NO
config = BacktestConfig(initial_capital=10000)   # NO
calc = AdvancedMetricsCalculator(initial_capital=10000.0)  # NO
```

Required instead — **host-run** files (`backtesting/`, `tests/`):

```python
from shared.account import ACCOUNT_EQUITY_USD

initial_capital: float = ACCOUNT_EQUITY_USD
```

**In-container** files (`services/*/app/**`) — resolve from Settings, and never at import time:

```python
from app.config import get_settings

def size_trade(capital: float | None = None) -> Decimal:
    capital = get_settings().paper_initial_balance if capital is None else capital
```

Never `def f(x = get_settings().y)` — Python evaluates default arguments **once at import**, freezing the value and making it invisible to the AST detector in `tests/test_account_size_invariant.py`.

This also applies to **docstring examples** — a docstring showing `initial_capital=10000.0` is how the wrong number keeps propagating back into new code. Use `ACCOUNT_EQUITY_USD` in examples too.

Known offender files (audit before editing near them):
`services/trading-engine/app/strategies/backtester.py`, `app/analytics/advanced_metrics.py`,
`app/analytics/attribution.py`, `app/handlers/performance_dashboard.py`,
`app/risk/kelly_position_sizing.py`, `app/risk/dynamic_budget.py`, `app/risk/dynamic_risk_budget.py`,
`app/risk/sector_exposure.py`, `app/risk/correlation_manager.py`, `app/risk/diversification_calculator.py`,
`app/risk/funding_gate.py`, `app/strategies/pairs_trading.py`, `app/strategies/funding_rate_arbitrage.py`,
`services/risk-metrics-service/app/backtest_models.py`, `services/portfolio-manager/app/config.py`.

## Sizing math must survive $100

Before returning a position size, the code must reject the trade rather than shrink below the venue floor:

1. Compute risk budget = `equity * max_risk_per_trade` (**fraction**, `0.10` = 10%).
2. Compute quantity from risk budget and stop distance.
3. Compute notional = `quantity * price`.
4. If `notional < min_notional(symbol)` → **return no-trade with a reason**, do not clamp up to the minimum. Clamping up is how a 10% cap silently becomes a 40% cap.
5. If `notional > equity * max_position_size_pct / 100` → clamp down.

**Units are the trap here — get them wrong and the check silently never fires.**

| Field | Unit | Default | Env key |
|---|---|---|---|
| `max_risk_per_trade` | **fraction** | `0.10` | `MAX_RISK_PER_TRADE` |
| `max_daily_loss_pct` | **percent** | `12.0` (ADR-028) | `MAX_DAILY_LOSS_PCT` |
| `max_position_size_pct` | **percent** | `10.0` | `MAX_POSITION_SIZE_PCT` |
| `max_total_exposure_pct` | **percent** | `80.0` | `MAX_TOTAL_EXPOSURE_PCT` |

Comparing a fraction to a percent (`max_risk_per_trade > max_daily_loss_pct` → `0.10 > 12.0` → always False) is a real bug that shipped once. Normalize first — `shared.account.max_daily_loss_fraction()` exists for this.

`LIVE_MAX_RISK_PER_TRADE = 0.02` is non-negotiable and unchanged. On $100 that is $2, below the ~$5 venue minimum, so **LIVE is not mechanically viable at this account size** regardless of edge.

Never let rounding produce a quantity of `0` that is then treated as a filled order.

## Fees and slippage are not optional

Any P&L number — backtest, walk-forward, paper, dashboard — must be net of:

- taker fee both legs (Bybit linear perp, ~0.055% per side),
- funding if the position crosses a funding timestamp,
- a slippage model.

The paper engine **has a slippage model** as of 2026-08-03 (`fb45efe`, PAPER-01) — `services/trading-engine/app/paper_slippage.py`, gated by `paper_slippage_enabled`. *(This file said "no slippage model yet" until 2026-08-04; corrected against the filesystem. Do not restore the old wording.)* Two things still hold: every backtest figure produced **before** 2026-08-03 was measured through a frictionless engine and is optimistic, so re-run before citing; and when the flag is off, label the P&L *gross of slippage* wherever it is reported.

## Decimal, not float, for money

Use `Decimal` for balances, P&L, and order quantities. `float` is acceptable for indicator math only. Do not mix them in the same expression without an explicit conversion.

## Price rounding

`round(price, 2)` is wrong for crypto — it destroys ADA/SOL precision. Use the symbol's tick size from the instrument info. There are 22 known offending sites across 7 files (`PRICE-01/02`); fix them when you touch them, and do not add new ones.
