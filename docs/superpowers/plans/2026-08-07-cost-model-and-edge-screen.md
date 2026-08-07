# Cost Model + Edge Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one cost model that both the live paper engine and the research backtester call, and a screen that kills any candidate strategy whose gross edge does not clear twice its all-in trading cost — in seconds, before any statistics are run.

**Architecture:** A single stdlib-only `services/trading-engine/app/costs.py` owns fees (maker and taker separately), per-symbol slippage, tick and lot quantization, min-notional rejection, and **signed** funding. Every rate and venue spec arrives as an explicit parameter — the module never fetches, never imports `app.config`, and never touches the network, so it unit-tests without Docker. It ships inside the trading-engine image (`COPY app/`) and is loaded host-side by file path under a non-`app` module name, because `app` is already claimed by technical-analysis in the backtesting process. On top of it, `backtesting/screen.py` turns a signal series into a PASS/KILL verdict against the cost hurdle, and is validated by reproducing the committed H3-secondary figures exactly.

**Tech Stack:** Python 3.12, `decimal` / `dataclasses` / `typing` only in `costs.py`; pandas in `screen.py`; pytest host-run.

## Global Constraints

- **Account is $100.** No account-size literals. Host-run code may `from shared.account import ...`; `services/*/app/**` may **not**.
- **`costs.py` imports stdlib only** — `decimal`, `dataclasses`, `typing`, `enum`. Two hard reasons, both verified empirically:
  - `from app.config import get_settings` executed from repo-root cwd raises `pydantic_settings.exceptions.SettingsError: error parsing value for field "cors_origins"` (`env_file=".env"` is cwd-relative).
  - `instruments_cache.get()` performs an HTTP GET on miss/TTL-expiry and **fails open**, returning `None` or a stale entry, never raising. A `costs.py` that reached for it would silently lose *all* quantization in unit tests while every assertion still passed.
- **Test invocation:** `cd services/trading-engine && python3 -m pytest <paths> --no-cov -q` for engine tests; `python3 -m pytest tests/<path> --no-cov -q` from the repo root for `tests/` and `backtesting/` tests. Never prefix `MAX_TOTAL_EXPOSURE_PCT=` / `PAPER_INITIAL_BALANCE=` (retired 2026-08-04; exporting env vars now corrupts Dict settings).
- **`@pytest.mark.golden` is available at the repo root only**, not inside `services/trading-engine/tests/`.
- **Never run `git status` bare or `git add -A`.** Commit with an explicit pathspec.
- **Money is `Decimal`.** No float money anywhere in `costs.py`.
- **Min-notional is REJECT, never clamp up** (CLAUDE.md §1). Clamping a $10 cap up to clear a $60 floor turns a 10% cap into a 60% cap.
- **Branch:** `feature/engine-repair-edge-search`.
- **Prerequisite:** this plan assumes `docs/superpowers/plans/2026-08-07-stage0-engine-correctness.md` has landed. Task 5 wires `costs.py` into `paper_trading.py`, which Stage 0 Task 3 also edits.

## Verified interface facts (read before any task; source of truth for signatures)

**Where `costs.py` lives, and how each side imports it.** This was tested, not assumed:
- Repo-root `shared/costs.py` is **impossible in-container**: build context is `./services/trading-engine` (`docker-compose.unified.yml:639`) and the Dockerfile does `COPY --chown=appuser:appuser app/ ./app/` plus a decoy `RUN mkdir -p ./shared` that creates an **empty** directory.
- `services/trading-engine/app/costs.py` imported host-side as `from app.costs import ...` is **also impossible**: `services/technical-analysis/app/__init__.py` exists, making `app` a *regular* (non-namespace) package, and `backtesting/prod_indicators.py:37-38` and `backtesting/run_walk_forward_ensemble.py:62` both claim `app` for technical-analysis. Reproduced: after inserting the TA path and importing `app`, `import app.paper_slippage` raises `ModuleNotFoundError`.
- **Resolution.** File: `services/trading-engine/app/costs.py`. In-container: `from app.costs import ...` — works, no change needed. Host: load by path under a **non-`app`** module name, using the mechanism that already exists at `backtesting/run_walk_forward_ensemble.py:96-104`. Because `costs.py` is stdlib-only it needs no `sys.path` manipulation at all:

```python
import importlib.util
from pathlib import Path

_COSTS_PATH = Path(__file__).resolve().parents[1] / "services" / "trading-engine" / "app" / "costs.py"


def _load_costs():
    spec = importlib.util.spec_from_file_location("te_costs", _COSTS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

**Seven live commission values, disagreeing.** The only figure that agrees across all three sources is the taker rate:
| Source | Value | Unit | Notes |
|---|---|---|---|
| `services/trading-engine/app/config.py:575` `paper_commission_pct` | `0.055` | **percent** | converted at `paper_trading.py:78` to `0.00055` fraction |
| `shared/account.py:103` `TAKER_FEE_PER_SIDE` | `0.00055` | fraction | agrees |
| `backtesting/backtest_engine.py:139` `bybit_taker_fee` | `0.00055` | fraction | agrees, but only when `fee_mode='bybit_perp'` |
| `backtesting/backtest_engine.py` `commission` | `0.001` | fraction | **the DEFAULT path** (`fee_mode='fixed'`) — 10 bps, 1.8× the real rate |
| `services/trading-engine/app/backtesting` `BacktestConfig.commission_pct` | `0.1` | percent | 10 bps; re-hardcoded at `handlers/backtest.py:53,:380,:548` and `grid_trading.py:80,:98` |
| `execution_optimizer.py:130-131`, `exchanges/router.py:399`, `smart_order_router.py:820` | maker `0.0001` / taker `0.0006` | fraction | 1 bp / 6 bps |
| `analytics/post_trade_analysis.py:429-430` | maker `2.0` / taker `5.0` | **bps** | |

The 0.1% vs 0.055% gap is the exact 1.8× over-charge `AUDIT §6.2` fixed in the paper engine on 2026-08-04 and never fixed anywhere else.

**The maker sign is self-contradictory, and this plan resolves it as a CHARGE.**
- `services/trading-engine/app/config.py:176` (comment): *"Bybit perp economics: taker 0.055% / maker 0.020% → ~7 bps round-trip saved"* — maker is a **positive charge**.
- `backtesting/backtest_engine.py:140`: `bybit_maker_fee: float = -0.0001,  # -0.01% maker rebate` — a **credit**.

`config.py:176` is correct. Bybit's standard USDT-perpetual schedule is taker 0.055% / **maker 0.020%, both charges**; maker rebates exist only at market-maker/high-VIP tiers, which a $100 account cannot reach. The backtester's negative value is a defect with a compounding consequence — see the next fact.

**Two free lunches in the research backtester** (`backtesting/backtest_engine.py:443-480`), both to be fixed in Task 6:
1. `stop_loss` / `take_profit` exits fill at the pre-set level with **zero slippage** — the comment at `:450-452` acknowledges it. A Bybit conditional stop becomes a *market* order when triggered: it is taker and it gaps.
2. Line 474 classifies those same exits as `'LIMIT'` ⇒ maker, so with `bybit_maker_fee=-0.0001` **every stop-out credits the account**.

**Funding is longs-only, single-rate, and off by default.** `backtest_engine._apply_funding` (`:214-226`) charges only when `order_type == OrderType.BUY and self.funding_long_pays` — a short **never receives** funding. Cadence is hardcoded `_bar_count % 8`; rate is the constant `funding_rate_per_8h=0.0001`; `funding_enabled` defaults `False`, so **no published figure in this repo has ever paid funding**. The live paper engine has no funding at all — `auto_trader.py:1922`'s funding code is an *entry gate* and is additionally gated to `trading_mode == "LIVE"`.

**Real funding rates, measured live 2026-08-07 over 200 settlements per symbol:**
| symbol | mean /8h | annualized | min | max |
|---|---|---|---|---|
| BTCUSDT | 0.00278% | 3.04% | −0.0075% | 0.0100% |
| ETHUSDT | 0.00191% | 2.09% | −0.0096% | 0.0100% |
| SOLUSDT | **−0.00086%** | **−0.95%** | −0.0328% | 0.0100% |
| BNBUSDT | 0.00319% | 3.50% | −0.0256% | 0.0100% |
| ADAUSDT | 0.00137% | 1.50% | −0.0232% | 0.0100% |

The `0.0100%` ceiling on all five is the base-rate clip. The backtester's hardcoded `0.0001` (= 0.01%/8h) is therefore the **worst case**, not the norm — it overstates typical funding by 3–7×, and it has the wrong sign for a SOL long.

**Funding data does not exist anywhere in the repo.** TimescaleDB `market_data` holds only `klines`, `orderbook_snapshots`, `tickers`. The fetch path works: `GET http://localhost:8001/api/v1/market/funding-rate/history?symbol=<S>&category=linear&start=<ms>&end=<ms>&limit=200` → Bybit `/v5/market/funding/history` (`services/bybit-connector/app/main.py:917`, client at `bybit_rest_client.py:635`). Query params are **`start`/`end`**, not `start_time`/`end_time`. Response is `{"success": true, "data": [{"symbol", "fundingRate", "fundingRateTimestamp"}, ...]}`, **newest-first**, `fundingRate` a **stringified decimal** — feed it to `Decimal`, never `float`. Rate limit 200/min. 365 days ≈ 1,095 settlements/symbol ≈ 6 paginated calls/symbol, 30 calls total.

**Per-symbol slippage, one-way** (`paper_slippage.py:92-103`): BTCUSDT 5, ETHUSDT 5, SOLUSDT 5, BNBUSDT 10, ADAUSDT 10 bps; fallback 10 (`FALLBACK_SLIPPAGE_BPS`). The module's own docstring flags the taker-impact component as an **estimate never measured on this account** and names SOLUSDT@5 as the least-supported figure. Competing values elsewhere: `backtesting/backtest_engine.py` `slippage=0.0005` fraction, engine `BacktestConfig.slippage_pct=0.05` percent, `slippage_manager` `base_tolerance_pct=0.15` percent — same magnitudes, three different units.

**The tick table is duplicated ON PURPOSE.** `paper_slippage.DEFAULT_TICK_SIZE` (`:109-114`) hardcodes the same `priceFilter.tickSize` values `instruments_cache` fetches live, because (docstring `:38-40`) the cache is network-backed and fail-open and is *"deliberately NOT called from the fill path"*. `costs.py` must not collapse them — it takes tick size as a **parameter**, so callers keep a synchronous offline-safe source. Note `DEFAULT_TICK_SIZE["BNBUSDT"] = 0.01` while the live venue reports `0.10` (defect E14, deferred to Stage 2): callers must pass the venue value, and `costs.py` inherits nothing.

**Min-notional: the declared constant and the enforced constant never meet.** `shared/account.py:159` `MIN_NOTIONAL_USD = 5.0`, but its only consumer is `capital_config_warnings()`, a host-run `RuntimeWarning`. The enforced gate at `auto_trader.py:1636` reads `spec.min_notional` from `InstrumentSpec`, where `min_notional: Optional[Decimal] = None` **because Bybit omits `lotSizeFilter.minNotionalValue` on many perps**. There is **no $5 fallback in the enforced path** — when the field is absent the notional check is skipped entirely and only the `min_order_qty` check survives. `costs.py` must take min-notional as an explicit `Optional[Decimal]` and make the absent case a caller decision, not a silent skip.

**`tests/test_account_config_sync.py:100-105` pins the `shared/account.py` key set:**
```python
covered = {key for key, _ in FIELD_PAIRS.values()}
venue_only = {"MIN_NOTIONAL_USD", "TAKER_FEE_PER_SIDE"}
assert set(DEFAULTS) == covered | venue_only
```
Adding any new `DEFAULTS` key fails this **by design**. `MAKER_FEE_PER_SIDE` belongs in `venue_only`, mirroring `TAKER_FEE_PER_SIDE` — both describe Bybit, not the account, and neither has a unit-compatible `Settings` counterpart (`paper_commission_pct` is a *percent*, the constants are *fractions*, which is exactly why they were never paired).

**Test-stub template for venue specs:** `services/trading-engine/tests/test_sizing_caps_phase1.py:65-102` — `_spec(symbol, min_qty, qty_step, tick, min_notional="5") -> InstrumentSpec` and `_StubInstrumentsCache`. `BTC_SPEC = _spec("BTCUSDT", "0.001", "0.001", "0.10")`, `SOL_SPEC = _spec("SOLUSDT", "0.1", "0.1", "0.010")`.

**The committed artifacts `screen.py` must reproduce.** Both verified 2026-08-07 by summing the per-trade CSVs and matching the published verdict exactly:

`.planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_1.5x.csv` — columns `ambiguous_bars, atr_daily, bars_held, exit_price, exit_reason, fees_bybit_est, fees_modelled, funding_est, gross_pnl, position_id, resolution, side, stop, symbol, tp`:

| quantity | 1.5× ATR | 2.5× ATR |
|---|---|---|
| n | 12297 | 12297 |
| `SUM(gross_pnl)` | **41.870782** | 10.974434 |
| gross expectancy | **0.0034049591** | 0.0008924481 |
| `SUM(fees_bybit_est)` | 94.3604 | 94.3433 |
| `SUM(fees_modelled)` | 171.5643 | 171.5332 |
| `SUM(funding_est)` | 48.6160 | 50.8002 |
| net (bybit est.) | **−52.4896** | −83.3689 |
| net (modelled) | −129.6936 | −160.5588 |
| mean leg notional | 6.975 | 6.9746 |
| gross edge, % of leg notional | **0.0488%** | 0.0128% |
| exit reasons | `max_hold 10578, stop_loss 1402, take_profit 292, end_of_data 25` | `max_hold 11813, stop_loss 414, take_profit 45, end_of_data 25` |

`fees_modelled = (notional_in + notional_out) × 0.001` and `fees_bybit_est = (notional_in + notional_out) × 0.00055`. Mean leg notional therefore derives as `SUM(fees_modelled) / 0.001 / (2 × n)`.

`.planning/evidence/killtests/signal-series.csv` — 42,295 rows, header `symbol,ts_ms,action,confidence,aggregated_score,consensus_count,ens_action,ens_confidence,ens_position_size_pct,close`. Note ADA trades near `0.90` at the series start (2025-08) and near `0.20` at the end — a genuine year-long downtrend, not a data error.

**Candle data is already in place:** `backtesting/data/` holds 5 symbols × 4 timeframes × 365 days (2025-08-06 → 2026-08-06), **zero gaps**, hashed in `.planning/evidence/killtests/backfill-manifest-2026-08.md` (`15m` 35,039 rows, `60m` 8,759, `240m` 2,189, `1440m` 364 per symbol).

**⚠ Do not run `scripts/repair_testnet_pollution.sql`.** Its own postcondition (`:131-135`, "expect 0") currently returns **131,910 rows** — all carrying `created_at = 1786026362487`, the legitimate 2026-08-06 mainnet backfill of 174,776 bars. Re-running `:61-65` would demote exactly the 15m/240m/daily history this plan depends on.

**Adjacent defect, explicitly out of scope but do not "fix" it silently:** `backtesting/backtest_engine.py:676` annualizes with `np.sqrt(365)` and the comment *"assuming daily returns"*, but `equity_curve` is appended once per bar (`:296`) and `_apply_funding` treats `_bar_count % 8` as an 8-hour cadence — i.e. hourly bars. If so, every Sharpe through that path understates magnitude by ~√24 ≈ 4.9×, which would make the CLAUDE.md §2 table materially *more* negative. Verify the bar interval each strategy is actually fed before touching it; that is its own change with its own evidence burden.

---

### Task 1: `costs.py` — fees, stdlib-only, everything a parameter

**Files:**
- Create: `services/trading-engine/app/costs.py`
- Modify: `shared/account.py` (`DEFAULTS` and the `__all__` at `:76-78`)
- Modify: `tests/test_account_config_sync.py` (`venue_only` at `:101`)
- Test: `services/trading-engine/tests/test_costs_fees.py` (new)

**Interfaces:**
- Produces:
  - `class Liquidity(str, Enum)` with `MAKER = "MAKER"`, `TAKER = "TAKER"`.
  - `@dataclass(frozen=True) class FeeSchedule: taker: Decimal; maker: Decimal` — **fractions**, e.g. `Decimal("0.00055")` / `Decimal("0.00020")`. Classmethod `FeeSchedule.bybit_linear_perp() -> FeeSchedule`.
  - `@dataclass(frozen=True) class VenueSpec: symbol: str; tick_size: Decimal; qty_step: Decimal; min_order_qty: Decimal; min_notional: Optional[Decimal]`
  - `fee(notional: Decimal, liquidity: Liquidity, schedule: FeeSchedule) -> Decimal`
  - `slippage_bps(symbol: str, table: Mapping[str, Decimal], fallback: Decimal) -> Decimal`
  - `round_trip_cost_bps(symbol, *, entry_liquidity, exit_liquidity, schedule, slippage_table, slippage_fallback) -> Decimal` — fees + slippage only; **funding is not in here** (it is signed and position-dependent, Task 3).

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_costs_fees.py`:

```python
"""
costs.py fee layer.

Two properties this pins, both of which the repo currently violates somewhere:
  * maker is a CHARGE, not a rebate. config.py:176 says taker 0.055% /
    maker 0.020%; backtesting/backtest_engine.py:140 says maker = -0.0001, a
    CREDIT. Bybit's standard USDT-perp schedule charges both; rebates exist
    only at market-maker tiers a $100 account cannot reach. The negative value
    makes every backtested stop-out credit the account.
  * costs.py imports STDLIB ONLY. Importing app.config from repo-root cwd
    raises SettingsError, and instruments_cache fails OPEN (returns None) on a
    network miss, which would silently delete quantization from every test
    while leaving the assertions green.
"""

from decimal import Decimal

import pytest

from app.costs import FeeSchedule, Liquidity, fee, round_trip_cost_bps, slippage_bps


SLIPPAGE = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}
FALLBACK = Decimal("10")


def test_costs_module_imports_stdlib_only():
    """A single non-stdlib import makes this module unusable host-side."""
    import ast
    import pathlib
    import sys

    src = pathlib.Path(__import__("app.costs", fromlist=["costs"]).__file__).read_text()
    tree = ast.parse(src)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])

    assert roots <= set(sys.stdlib_module_names), (
        f"costs.py must import stdlib only; found {sorted(roots - set(sys.stdlib_module_names))}"
    )


def test_bybit_schedule_charges_both_sides():
    s = FeeSchedule.bybit_linear_perp()
    assert s.taker == Decimal("0.00055")
    assert s.maker == Decimal("0.00020")
    assert s.maker > 0, "maker is a CHARGE on the standard schedule, not a rebate"


def test_fee_is_notional_times_rate():
    s = FeeSchedule.bybit_linear_perp()
    assert fee(Decimal("10"), Liquidity.TAKER, s) == Decimal("0.0055")
    assert fee(Decimal("10"), Liquidity.MAKER, s) == Decimal("0.0020")


def test_fee_rejects_negative_notional():
    s = FeeSchedule.bybit_linear_perp()
    with pytest.raises(ValueError):
        fee(Decimal("-1"), Liquidity.TAKER, s)


def test_slippage_is_per_symbol_with_a_wider_fallback():
    assert slippage_bps("BTCUSDT", SLIPPAGE, FALLBACK) == Decimal("5")
    assert slippage_bps("ADAUSDT", SLIPPAGE, FALLBACK) == Decimal("10")
    # An unvalidated symbol gets the wider alt bucket, never the majors bucket:
    # being wrong conservatively understates P&L, which is the safe error.
    assert slippage_bps("XRPUSDT", SLIPPAGE, FALLBACK) == Decimal("10")


def test_taker_round_trip_matches_the_hurdle_table():
    """21 bps majors / 31 bps BNB-ADA — the figures the design spec quotes."""
    s = FeeSchedule.bybit_linear_perp()
    majors = round_trip_cost_bps(
        "BTCUSDT",
        entry_liquidity=Liquidity.TAKER,
        exit_liquidity=Liquidity.TAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    alts = round_trip_cost_bps(
        "ADAUSDT",
        entry_liquidity=Liquidity.TAKER,
        exit_liquidity=Liquidity.TAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    assert majors == Decimal("21")   # 2*5.5 fee + 2*5 slippage
    assert alts == Decimal("31")     # 2*5.5 fee + 2*10 slippage


def test_maker_round_trip_is_fees_only():
    """4 bps. A PostOnly order fills at the price it posted, so no adverse
    slippage — but adverse selection and non-fill are real costs this number
    does NOT capture, which is why the maker hurdle carries a caveat."""
    s = FeeSchedule.bybit_linear_perp()
    got = round_trip_cost_bps(
        "BTCUSDT",
        entry_liquidity=Liquidity.MAKER,
        exit_liquidity=Liquidity.MAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    assert got == Decimal("4")


def test_mixed_liquidity_round_trip():
    """Maker entry, taker exit — the realistic shape for a PostOnly entry with
    a market stop, since a triggered Bybit conditional stop is a taker order."""
    s = FeeSchedule.bybit_linear_perp()
    got = round_trip_cost_bps(
        "SOLUSDT",
        entry_liquidity=Liquidity.MAKER,
        exit_liquidity=Liquidity.TAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    assert got == Decimal("12.5")   # 2 + 5.5 fee + 0 + 5 slippage
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_fees.py --no-cov -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.costs'`.

- [ ] **Step 3: Write the module**

Create `services/trading-engine/app/costs.py`:

```python
"""
One cost model, called by the live paper engine AND the research backtester.

WHY THIS EXISTS. Before it, seven different commission values were live in
this repo, the research backtester's default path charged 0.1%/side (1.8x the
real Bybit taker rate), stop and take-profit exits in that backtester were
classified as MAKER with a NEGATIVE fee so every stop-out CREDITED the
account, funding was charged to longs only at a hardcoded worst-case rate and
was off by default, and nothing anywhere modelled tick or lot quantization.
Every published P&L figure in the repo was produced under some subset of that.

TWO HARD RULES, both load-bearing:

1. STDLIB ONLY. `from app.config import get_settings` raises SettingsError when
   executed from the repo root (env_file=".env" is cwd-relative), and
   `instruments_cache.get()` performs an HTTP GET and FAILS OPEN — it returns
   None on a connector outage and never raises. A costs.py that reached for
   either would work in-container and silently lose all quantization host-side,
   with every assertion still passing. Enforced by a test.

2. NOTHING IS FETCHED. Every rate, tick size, lot step and min-notional arrives
   as an explicit parameter. Callers resolve them: in-container from Settings
   plus instruments_cache; host-side from a fixture or a manifest. This is also
   why the duplicated tick table in paper_slippage.py is NOT collapsed here —
   that duplication is deliberate (paper_slippage.py:38-40), because a network
   call in the fill path was explicitly rejected.

IMPORT PATHS.
  in-container:  from app.costs import FeeSchedule, Liquidity, ...
  host-side:     load by file path under a NON-`app` module name. `app` is a
                 regular package claimed by technical-analysis in the
                 backtesting process, so `from app.costs import ...` resolves
                 to the wrong package or raises ModuleNotFoundError. See
                 backtesting/costs_loader.py.

UNITS. Fee rates are FRACTIONS (0.00055 = 5.5 bps). Slippage is BASIS POINTS.
Conflating fraction and percent is the single most common defect in this
codebase — `max_risk_per_trade` is a fraction while its `*_pct` neighbours are
percents, and that shipped once. Every public name here says which it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional

_BPS = Decimal("10000")


class Liquidity(str, Enum):
    """Which side of the book an order took."""

    MAKER = "MAKER"
    TAKER = "TAKER"


@dataclass(frozen=True)
class FeeSchedule:
    """Per-side fee rates as FRACTIONS of notional. Both are charges."""

    taker: Decimal
    maker: Decimal

    @classmethod
    def bybit_linear_perp(cls) -> "FeeSchedule":
        """Bybit USDT-perpetual standard (non-VIP) schedule.

        taker 0.055%, maker 0.020% — BOTH CHARGES. Recorded at
        services/trading-engine/app/config.py:176.

        backtesting/backtest_engine.py:140 declares `bybit_maker_fee = -0.0001`
        with the comment "maker rebate". That is wrong for this account: Bybit
        pays maker rebates only at market-maker / high-VIP tiers, which $100
        cannot reach. Combined with that file classifying every stop and
        take-profit exit as LIMIT => maker, it made every backtested stop-out
        credit the account. Resolved here in favour of config.py:176.
        """
        return cls(taker=Decimal("0.00055"), maker=Decimal("0.00020"))

    def rate(self, liquidity: Liquidity) -> Decimal:
        return self.taker if liquidity is Liquidity.TAKER else self.maker


@dataclass(frozen=True)
class VenueSpec:
    """Venue constraints for one symbol. Supplied by the caller, never fetched.

    min_notional is Optional BY DESIGN: Bybit omits
    lotSizeFilter.minNotionalValue on many perps, and the live enforced gate
    (auto_trader.py:1636) therefore skips the notional check entirely when it
    is absent — there is no $5 fallback in that path, despite
    shared/account.MIN_NOTIONAL_USD existing. Making the absent case explicit
    here forces the caller to decide rather than inherit a silent skip.
    """

    symbol: str
    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal
    min_notional: Optional[Decimal] = None


def fee(notional: Decimal, liquidity: Liquidity, schedule: FeeSchedule) -> Decimal:
    """Commission on one leg. `notional` is price x quantity, quote currency."""
    if notional < 0:
        raise ValueError(f"notional must be non-negative, got {notional}")
    return notional * schedule.rate(liquidity)


def slippage_bps(
    symbol: str,
    table: Mapping[str, Decimal],
    fallback: Decimal,
) -> Decimal:
    """One-way slippage in BASIS POINTS.

    An unlisted symbol gets `fallback`, which callers should set to the wider
    alt bucket rather than the majors bucket: being wrong conservatively
    understates P&L, which is the safe direction (paper_slippage.py:105-107).

    These figures are ESTIMATES. paper_slippage.py's own docstring flags the
    taker-impact component as never measured on this account and names
    SOLUSDT@5bps as the least-supported value.
    """
    return table.get(symbol, fallback)


def round_trip_cost_bps(
    symbol: str,
    *,
    entry_liquidity: Liquidity,
    exit_liquidity: Liquidity,
    schedule: FeeSchedule,
    slippage_table: Mapping[str, Decimal],
    slippage_fallback: Decimal,
) -> Decimal:
    """Fees + slippage for one full round trip, in BASIS POINTS of notional.

    Funding is deliberately NOT included: it is signed, per-symbol and
    dependent on side and holding period, so it cannot be a constant adder.
    See `funding_cost`.

    A MAKER leg pays no adverse slippage — a PostOnly order fills at the price
    it posted. It does NOT follow that maker execution is free: adverse
    selection and non-fill are real costs this function cannot express, which
    is why a maker-only hurdle carries a fill-realism caveat rather than a
    straight 5x cost reduction.
    """
    slip = slippage_bps(symbol, slippage_table, slippage_fallback)
    fee_bps = (schedule.rate(entry_liquidity) + schedule.rate(exit_liquidity)) * _BPS
    slip_bps = Decimal("0")
    if entry_liquidity is Liquidity.TAKER:
        slip_bps += slip
    if exit_liquidity is Liquidity.TAKER:
        slip_bps += slip
    return fee_bps + slip_bps
```

- [ ] **Step 4: Declare the maker rate in `shared/account.py`**

Add to `DEFAULTS` (around `:103`), next to `TAKER_FEE_PER_SIDE`:

```python
    "MAKER_FEE_PER_SIDE": 0.00020,  # fraction — Bybit linear-perp standard; a CHARGE
```

Add `"MAKER_FEE_PER_SIDE"` to the `__all__` list at `:76-78`, and add the module-level binding next to `TAKER_FEE_PER_SIDE` at `:162`:

```python
MAKER_FEE_PER_SIDE: float = _env_float("MAKER_FEE_PER_SIDE")
```

- [ ] **Step 5: Extend `venue_only` in the same commit**

`tests/test_account_config_sync.py:101` fails on any new `DEFAULTS` key by design. `MAKER_FEE_PER_SIDE` describes Bybit, not the account, and has no unit-compatible `Settings` counterpart — `paper_commission_pct` is a *percent* while these constants are *fractions*, which is precisely why `TAKER_FEE_PER_SIDE` was never paired either. So it belongs in `venue_only`, not `FIELD_PAIRS`:

```python
    venue_only = {"MIN_NOTIONAL_USD", "TAKER_FEE_PER_SIDE", "MAKER_FEE_PER_SIDE"}
```

Update the docstring above it to name all three.

- [ ] **Step 6: Run both test files**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_fees.py --no-cov -q`
Expected: PASS, 8 tests.

Run: `python3 -m pytest tests/test_account_config_sync.py --no-cov -q` (from the **repo root** — this one imports `shared.account`)
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/trading-engine/app/costs.py \
        services/trading-engine/tests/test_costs_fees.py \
        shared/account.py \
        tests/test_account_config_sync.py
git commit -m "feat(costs): single stdlib-only cost model, fee layer

Seven different commission values were live in this repo. The only one that
agreed across sources was the 0.055% taker rate; the research backtester's
DEFAULT path charged 0.1%/side, 1.8x the real rate.

Resolves the maker-sign contradiction in favour of config.py:176: Bybit's
standard USDT-perp schedule charges taker 0.055% and maker 0.020%, both
charges. backtest_engine.py:140's -0.0001 'maker rebate' is unreachable at a
\$100 account and, combined with that file classifying stop/TP exits as
maker, made every backtested stop-out credit the account.

costs.py imports stdlib only, enforced by a test: app.config raises
SettingsError from repo-root cwd, and instruments_cache fails OPEN, so
reaching for either would silently delete quantization host-side while
leaving assertions green. Every rate and venue spec is a parameter." -- \
  services/trading-engine/app/costs.py \
  services/trading-engine/tests/test_costs_fees.py \
  shared/account.py \
  tests/test_account_config_sync.py
```

---

### Task 2: Quantization and min-notional rejection

**Files:**
- Modify: `services/trading-engine/app/costs.py`
- Test: `services/trading-engine/tests/test_costs_quantization.py` (new)

**Interfaces:**
- Consumes: `VenueSpec` from Task 1.
- Produces:
  - `snap_quantity(quantity: Decimal, spec: VenueSpec) -> Decimal` — floors to `qty_step`, **never rounds up**.
  - `quantize_price(price: Decimal, spec: VenueSpec, *, adverse_for_buy: bool) -> Decimal` — quantizes away from mid (ceil for a buy, floor for a sell).
  - `class RejectReason(str, Enum)` with `MIN_QTY`, `MIN_NOTIONAL`, `ZERO_QTY`, `SPEC_UNAVAILABLE`.
  - `check_tradeable(quantity, price, spec) -> Optional[RejectReason]` — `None` means tradeable.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_costs_quantization.py`:

```python
"""
costs.py quantization + venue gates.

CLAUDE.md section 1: a trade below min-notional must be REJECTED with a
reason, never clamped up. Clamping a \$10 per-trade cap up to clear BTC's
~\$62 floor turns a 10% cap into a 62% cap. This is also why snapping is
floor-only.

round(price, 2) is forbidden in the price domain here - it destroyed ADA
precision and caused 30+ flip-flop losses (487d1bd). Quantization is always
to the symbol's tick.
"""

from decimal import Decimal

import pytest

from app.costs import RejectReason, VenueSpec, check_tradeable, quantize_price, snap_quantity


# Live Bybit values fetched 2026-08-04 (AUDIT.md section 3). Note BNBUSDT's
# tick is 0.10 at the venue while paper_slippage.DEFAULT_TICK_SIZE hardcodes
# 0.01 - defect E14. costs.py takes the spec as a parameter and inherits
# neither, which is the point.
BTC = VenueSpec("BTCUSDT", Decimal("0.10"), Decimal("0.001"), Decimal("0.001"), Decimal("5"))
SOL = VenueSpec("SOLUSDT", Decimal("0.010"), Decimal("0.1"), Decimal("0.1"), Decimal("5"))
ADA = VenueSpec("ADAUSDT", Decimal("0.0001"), Decimal("1"), Decimal("1"), Decimal("5"))
BNB = VenueSpec("BNBUSDT", Decimal("0.10"), Decimal("0.01"), Decimal("0.01"), None)


def test_quantity_floors_to_step_never_up():
    assert snap_quantity(Decimal("0.1387"), BNB) == Decimal("0.13")
    assert snap_quantity(Decimal("0.99"), SOL) == Decimal("0.9")
    assert snap_quantity(Decimal("0.0019"), BTC) == Decimal("0.001")


def test_quantity_already_on_step_is_unchanged():
    assert snap_quantity(Decimal("0.3"), SOL) == Decimal("0.3")


def test_quantity_below_one_step_floors_to_zero():
    """A zero quantity must be caught downstream, never become an order."""
    assert snap_quantity(Decimal("0.05"), SOL) == Decimal("0")


def test_price_quantizes_away_from_mid():
    """A buy fills at or above the reference; a sell at or below."""
    assert quantize_price(Decimal("62551.37"), BTC, adverse_for_buy=True) == Decimal("62551.40")
    assert quantize_price(Decimal("62551.37"), BTC, adverse_for_buy=False) == Decimal("62551.30")


def test_sub_dollar_price_keeps_its_precision():
    """round(price, 2) on ADA is the 487d1bd catastrophe."""
    got = quantize_price(Decimal("0.20234"), ADA, adverse_for_buy=True)
    assert got == Decimal("0.2024")
    assert got != Decimal("0.20")


def test_below_min_qty_is_rejected_not_clamped():
    reason = check_tradeable(Decimal("0.05"), Decimal("71.0"), SOL)
    assert reason is RejectReason.MIN_QTY


def test_zero_quantity_is_rejected():
    assert check_tradeable(Decimal("0"), Decimal("71.0"), SOL) is RejectReason.ZERO_QTY


def test_below_min_notional_is_rejected_not_clamped():
    """BTC min qty 0.001 at ~\$62,551 = \$62.55 notional - 62% of a \$100
    account against a \$10 per-trade cap. It must be rejected."""
    reason = check_tradeable(Decimal("0.0005"), Decimal("62551.0"), BTC)
    assert reason is RejectReason.MIN_QTY   # fails the qty floor first


def test_min_notional_gate_fires_when_qty_clears_but_value_does_not():
    reason = check_tradeable(Decimal("1"), Decimal("1.0"), ADA)
    assert reason is RejectReason.MIN_NOTIONAL


def test_absent_min_notional_skips_only_the_notional_check():
    """Bybit omits minNotionalValue on many perps. The live gate then skips
    the notional check entirely (auto_trader.py:1636) - there is no \$5
    fallback. Mirrored here so the two agree; the caller decides."""
    assert check_tradeable(Decimal("0.01"), Decimal("602.69"), BNB) is None
    assert check_tradeable(Decimal("0.001"), Decimal("602.69"), BNB) is RejectReason.MIN_QTY


def test_a_tradeable_order_returns_none():
    assert check_tradeable(Decimal("0.3"), Decimal("72.68"), SOL) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_quantization.py --no-cov -q`
Expected: FAIL — `ImportError: cannot import name 'RejectReason' from 'app.costs'`.

- [ ] **Step 3: Implement**

Append to `services/trading-engine/app/costs.py`:

```python
class RejectReason(str, Enum):
    """Why an order may not be placed. Rejection, never a clamp."""

    ZERO_QTY = "ZERO_QTY"
    MIN_QTY = "MIN_QTY"
    MIN_NOTIONAL = "MIN_NOTIONAL"
    SPEC_UNAVAILABLE = "SPEC_UNAVAILABLE"


def snap_quantity(quantity: Decimal, spec: VenueSpec) -> Decimal:
    """Floor `quantity` to the venue lot step. NEVER rounds up.

    Rounding up is how a 10% per-trade cap silently becomes a 40% cap
    (CLAUDE.md section 1). A quantity below one step floors to zero and must be
    caught by `check_tradeable`, not turned into an order.
    """
    if spec.qty_step <= 0:
        raise ValueError(f"qty_step must be positive for {spec.symbol}")
    steps = (quantity / spec.qty_step).to_integral_value(rounding="ROUND_FLOOR")
    return steps * spec.qty_step


def quantize_price(price: Decimal, spec: VenueSpec, *, adverse_for_buy: bool) -> Decimal:
    """Quantize to the venue tick, AWAY from mid.

    A buy lands at or above the reference, a sell at or below, so the tick
    floor is always a cost and never an accidental gain. Never `round(p, 2)`:
    that erased ADA precision and caused 30+ flip-flop losses (487d1bd).
    """
    if spec.tick_size <= 0:
        raise ValueError(f"tick_size must be positive for {spec.symbol}")
    ticks = price / spec.tick_size
    rounding = "ROUND_CEILING" if adverse_for_buy else "ROUND_FLOOR"
    return ticks.to_integral_value(rounding=rounding) * spec.tick_size


def check_tradeable(
    quantity: Decimal,
    price: Decimal,
    spec: Optional[VenueSpec],
) -> Optional[RejectReason]:
    """None if the order may be placed, else why not.

    Gate order mirrors the live path (auto_trader.py:1611-1657): zero quantity,
    then the minimum lot, then notional. The notional check is SKIPPED when
    spec.min_notional is None, because Bybit omits lotSizeFilter.
    minNotionalValue on many perps and the live enforced path has no fallback.
    That is a faithful mirror, not an endorsement — a caller that needs a floor
    must pass one.
    """
    if spec is None:
        return RejectReason.SPEC_UNAVAILABLE
    if quantity <= 0:
        return RejectReason.ZERO_QTY
    if quantity < spec.min_order_qty:
        return RejectReason.MIN_QTY
    if spec.min_notional is not None and quantity * price < spec.min_notional:
        return RejectReason.MIN_NOTIONAL
    return None
```

- [ ] **Step 4: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_quantization.py tests/test_costs_fees.py --no-cov -q`
Expected: PASS, 19 tests.

- [ ] **Step 5: Commit**

```bash
git add services/trading-engine/app/costs.py \
        services/trading-engine/tests/test_costs_quantization.py
git commit -m "feat(costs): tick/lot quantization and reject-never-clamp venue gates

backtesting/ contains ZERO occurrences of tick_size, qty_step, min_notional
or quantize - the research backtester books trades the live path rejects.

Quantity floors only. Price quantizes away from mid so the tick floor is
always a cost. min_notional stays Optional and its absence skips only the
notional check, faithfully mirroring the live gate: Bybit omits
minNotionalValue on many perps and auto_trader.py:1636 has no \$5 fallback
despite shared.account.MIN_NOTIONAL_USD existing." -- \
  services/trading-engine/app/costs.py \
  services/trading-engine/tests/test_costs_quantization.py
```

---

### Task 3: Signed funding

**Files:**
- Modify: `services/trading-engine/app/costs.py`
- Test: `services/trading-engine/tests/test_costs_funding.py` (new)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class FundingSettlement: ts_ms: int; rate: Decimal` — `rate` is a **fraction per settlement**, signed.
  - `funding_cost(notional, side, settlements, *, entry_ts_ms, exit_ts_ms) -> Decimal` — **positive means the position PAID**. A long pays when the rate is positive; a short is paid.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_costs_funding.py`:

```python
"""
costs.py funding layer.

backtesting/backtest_engine.py:220 charges funding only when
`order_type == BUY and funding_long_pays` - a SHORT never receives it, so the
short side of every backtest is missing a real cash flow. It also hardcodes an
8-bar cadence and a constant 0.0001 rate, and funding_enabled defaults False,
so NO published figure in this repo has ever paid funding.

Measured live 2026-08-07 over 200 settlements/symbol, the mean per 8h is
0.00278% (BTC), 0.00191% (ETH), -0.00086% (SOL), 0.00319% (BNB), 0.00137%
(ADA). The 0.0100% ceiling on all five is the base-rate CLIP, so the
backtester's hardcoded 0.0001 is the worst case, not the norm - and it has
the wrong sign for a SOL long.
"""

from decimal import Decimal

import pytest

from app.costs import FundingSettlement, funding_cost


H8 = 8 * 60 * 60 * 1000

# Three settlements at the measured BTC mean.
POSITIVE = [
    FundingSettlement(ts_ms=1_000 + H8 * i, rate=Decimal("0.0000278"))
    for i in range(3)
]
# SOL's mean is negative - shorts pay, longs are paid.
NEGATIVE = [
    FundingSettlement(ts_ms=1_000 + H8 * i, rate=Decimal("-0.0000086"))
    for i in range(3)
]


def test_long_pays_positive_funding():
    cost = funding_cost(
        Decimal("100"), "LONG", POSITIVE, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    assert cost == Decimal("100") * Decimal("0.0000278") * 3
    assert cost > 0


def test_short_is_paid_positive_funding():
    cost = funding_cost(
        Decimal("100"), "SHORT", POSITIVE, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    assert cost == -(Decimal("100") * Decimal("0.0000278") * 3)
    assert cost < 0, "a short RECEIVES positive funding - the backtester never modelled this"


def test_long_is_paid_negative_funding():
    """SOL's mean rate is negative; a long there is paid, not charged."""
    cost = funding_cost(
        Decimal("100"), "LONG", NEGATIVE, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    assert cost < 0


def test_only_settlements_inside_the_holding_window_count():
    cost = funding_cost(
        Decimal("100"), "LONG", POSITIVE, entry_ts_ms=1_000, exit_ts_ms=1_000 + H8
    )
    # Settlements at t=1000 and t=1000+H8 are both inside [entry, exit].
    assert cost == Decimal("100") * Decimal("0.0000278") * 2


def test_a_position_closed_before_any_settlement_pays_nothing():
    assert funding_cost(Decimal("100"), "LONG", POSITIVE, entry_ts_ms=0, exit_ts_ms=500) == 0


def test_empty_series_is_zero_not_an_assumed_rate():
    """Silence must never become a hardcoded 0.0001 worst case."""
    assert funding_cost(Decimal("100"), "LONG", [], entry_ts_ms=0, exit_ts_ms=H8 * 10) == 0


def test_unknown_side_raises():
    with pytest.raises(ValueError):
        funding_cost(Decimal("100"), "FLAT", POSITIVE, entry_ts_ms=0, exit_ts_ms=H8)


def test_48h_hold_at_the_measured_mean_is_one_to_two_bps():
    """The design spec's claim, checked. Six settlements at the BTC mean is
    1.67 bps - NOT the 6 bps a hardcoded 0.01%/8h implies."""
    six = [FundingSettlement(ts_ms=H8 * i, rate=Decimal("0.0000278")) for i in range(6)]
    cost = funding_cost(Decimal("10000"), "LONG", six, entry_ts_ms=0, exit_ts_ms=H8 * 6)
    bps = cost / Decimal("10000") * Decimal("10000")
    assert Decimal("1.5") < bps < Decimal("2.0")


def test_48h_hold_at_the_base_rate_clip_is_six_bps():
    """0.0100%/8h is the CLIP seen on all five symbols, i.e. the worst case."""
    six = [FundingSettlement(ts_ms=H8 * i, rate=Decimal("0.0001")) for i in range(6)]
    cost = funding_cost(Decimal("10000"), "LONG", six, entry_ts_ms=0, exit_ts_ms=H8 * 6)
    assert cost / Decimal("10000") * Decimal("10000") == Decimal("6")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_funding.py --no-cov -q`
Expected: FAIL — `ImportError: cannot import name 'FundingSettlement' from 'app.costs'`.

- [ ] **Step 3: Implement**

Append to `services/trading-engine/app/costs.py`:

```python
@dataclass(frozen=True)
class FundingSettlement:
    """One funding settlement. `rate` is a SIGNED FRACTION of notional.

    Bybit returns fundingRate as a stringified decimal — feed it to Decimal,
    never float. Settlement cadence is per-symbol (`fundingInterval` in
    instruments-info, 480 minutes on all five validated symbols but 1h or 4h
    on others), which is why this carries a timestamp instead of assuming a
    fixed bar count. backtest_engine.py:218 assumes `_bar_count % 8`.
    """

    ts_ms: int
    rate: Decimal


def funding_cost(
    notional: Decimal,
    side: str,
    settlements: "list[FundingSettlement]",
    *,
    entry_ts_ms: int,
    exit_ts_ms: int,
) -> Decimal:
    """Net funding over a holding period. POSITIVE means the position PAID.

    Signed on BOTH axes, which is the whole point:
      * a LONG pays a positive rate and is paid a negative one;
      * a SHORT is paid a positive rate and pays a negative one.

    backtest_engine.py:220 charges only `BUY and funding_long_pays`, so a short
    never receives funding — the short side of every backtest in this repo is
    missing a real cash flow.

    An empty series returns 0. Silence must never become an assumed rate: the
    hardcoded 0.0001 elsewhere is the base-rate CLIP (the max observed on all
    five symbols), roughly 3-7x the measured means, and it has the wrong sign
    for a SOL long.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")
    if notional < 0:
        raise ValueError(f"notional must be non-negative, got {notional}")

    total = Decimal("0")
    for s in settlements:
        if entry_ts_ms <= s.ts_ms <= exit_ts_ms:
            total += notional * s.rate
    return total if side == "LONG" else -total
```

- [ ] **Step 4: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_funding.py --no-cov -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add services/trading-engine/app/costs.py \
        services/trading-engine/tests/test_costs_funding.py
git commit -m "feat(costs): signed per-symbol funding

backtest_engine.py:220 charges funding only to longs, hardcodes an 8-bar
cadence and a constant 0.0001 rate, and defaults funding_enabled to False -
so no published figure in this repo has ever paid funding, and no short has
ever received it. The live paper engine models funding not at all.

Measured live 2026-08-07 over 200 settlements/symbol, the means are 0.00278%
(BTC), 0.00191% (ETH), -0.00086% (SOL), 0.00319% (BNB), 0.00137% (ADA). The
0.0100% ceiling on all five is the base-rate clip, so the hardcoded value is
the worst case at 3-7x the norm - and the wrong sign for a SOL long.

An empty series returns 0, never an assumed rate." -- \
  services/trading-engine/app/costs.py \
  services/trading-engine/tests/test_costs_funding.py
```

---

### Task 4: Backfill the funding-rate history

**Files:**
- Create: `backtesting/funding_downloader.py`
- Create: `backtesting/costs_loader.py`
- Test: `tests/killtests/test_funding_downloader.py` (new — note this directory deliberately has **no** `__init__.py`)

**Interfaces:**
- Produces:
  - `backtesting/data/funding/<SYMBOL>_funding.csv` with header `symbol,ts_ms,funding_rate,fetched_at`, ascending by `ts_ms`, deduplicated.
  - `FundingDownloader(base_url: str = "http://localhost:8001")` with `download(symbol: str, days: int = 365) -> list[dict]` and `write_csv(symbol, rows, out_dir) -> Path`.
  - `backtesting/costs_loader.py` exposing `load_costs()` (the importlib shim described in the interface facts) and `load_funding(symbol, data_dir) -> list[FundingSettlement]`.

- [ ] **Step 1: Write the failing test**

Create `tests/killtests/test_funding_downloader.py`. Mock the HTTP boundary — this test must not require a live connector:

```python
"""
Funding backfill. Bybit returns newest-first, 200 rows max, fundingRate as a
STRINGIFIED decimal. 365 days is ~1095 settlements/symbol at the 8h cadence,
so ~6 paginated calls per symbol.

The connector route takes `start`/`end` (NOT start_time/end_time) - see
services/bybit-connector/app/main.py:917.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtesting"))

from funding_downloader import FundingDownloader  # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Two pages then empty, newest-first, mirroring Bybit's contract."""

    def __init__(self):
        self.calls = []
        h8 = 8 * 60 * 60 * 1000
        self._pages = [
            [
                {"symbol": "BTCUSDT", "fundingRate": "0.00002780",
                 "fundingRateTimestamp": str(2_000_000 - h8 * i)}
                for i in range(200)
            ],
            [
                {"symbol": "BTCUSDT", "fundingRate": "-0.00000750",
                 "fundingRateTimestamp": str(2_000_000 - 8 * 60 * 60 * 1000 * (200 + i))}
                for i in range(50)
            ],
            [],
        ]

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        page = self._pages[min(len(self.calls) - 1, len(self._pages) - 1)]
        return _FakeResponse({"success": True, "data": page})


def test_paginates_backwards_until_empty():
    client = _FakeClient()
    dl = FundingDownloader(client=client)
    rows = dl.download("BTCUSDT", days=365)

    assert len(client.calls) == 3
    assert len(rows) == 250
    assert all(r["symbol"] == "BTCUSDT" for r in rows)


def test_rows_come_back_ascending_and_deduplicated():
    client = _FakeClient()
    rows = FundingDownloader(client=client).download("BTCUSDT", days=365)
    ts = [r["ts_ms"] for r in rows]
    assert ts == sorted(ts)
    assert len(set(ts)) == len(ts)


def test_rate_is_decimal_not_float():
    from decimal import Decimal

    client = _FakeClient()
    rows = FundingDownloader(client=client).download("BTCUSDT", days=365)
    assert isinstance(rows[0]["funding_rate"], Decimal)
    assert any(r["funding_rate"] < 0 for r in rows), "negative rates must survive"


def test_uses_the_connector_param_names():
    """`start`/`end`, not start_time/end_time (main.py:917)."""
    client = _FakeClient()
    FundingDownloader(client=client).download("BTCUSDT", days=365)
    first = client.calls[0]
    assert set(first) >= {"symbol", "category", "limit"}
    assert "start_time" not in first and "end_time" not in first
    assert first["category"] == "linear"
    assert first["limit"] == 200


def test_write_csv_round_trips(tmp_path):
    from decimal import Decimal

    client = _FakeClient()
    dl = FundingDownloader(client=client)
    rows = dl.download("BTCUSDT", days=365)
    path = dl.write_csv("BTCUSDT", rows, tmp_path)

    text = path.read_text().splitlines()
    assert text[0] == "symbol,ts_ms,funding_rate,fetched_at"
    assert len(text) == len(rows) + 1
    # Precision must survive the round trip - float would lose it.
    assert "0.00002780" in text[1] or Decimal(text[1].split(",")[2]) == Decimal("0.0000278")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/killtests/test_funding_downloader.py --no-cov -q` (from the repo root)
Expected: FAIL — `ModuleNotFoundError: No module named 'funding_downloader'`.

- [ ] **Step 3: Write the downloader**

Create `backtesting/funding_downloader.py`. Route every fetch through bybit-connector, never direct to Bybit (BC-02/D-04 policy — `bybit_data_fetcher.py` already complies):

```python
"""
Backfill Bybit funding-rate history through bybit-connector.

Nothing in this repo stores funding rates: TimescaleDB `market_data` holds
only klines, orderbook_snapshots and tickers. The fetch path exists and works:
  GET {base}/api/v1/market/funding-rate/history
      ?symbol=<S>&category=linear&start=<ms>&end=<ms>&limit=200
-> Bybit /v5/market/funding/history

Contract details that bite:
  * response rows are NEWEST-FIRST;
  * `limit` is hard-capped at 200 by Bybit;
  * `fundingRate` is a STRINGIFIED decimal - Decimal, never float;
  * query params are `start`/`end`, not start_time/end_time;
  * the connector rate-limits this route at 200/minute.

365 days at the 8h cadence is ~1095 settlements/symbol, so ~6 calls/symbol and
30 calls for the validated five. Paginate BACKWARDS from now using the oldest
timestamp of each page as the next `end`.
"""

from __future__ import annotations

import csv
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional

import httpx

_MS_PER_DAY = 24 * 60 * 60 * 1000
_PAGE = 200


class FundingDownloader:
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        client: Optional[object] = None,
        now_ms: Optional[int] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)
        self._now_ms = now_ms

    def _now(self) -> int:
        return self._now_ms if self._now_ms is not None else int(time.time() * 1000)

    def download(self, symbol: str, days: int = 365) -> list[dict]:
        """Every settlement in the window, ascending, deduplicated."""
        end = self._now()
        start = end - days * _MS_PER_DAY
        seen: dict[int, dict] = {}

        cursor = end
        while True:
            params = {
                "symbol": symbol,
                "category": "linear",
                "start": start,
                "end": cursor,
                "limit": _PAGE,
            }
            resp = self._client.get(
                f"{self.base_url}/api/v1/market/funding-rate/history",
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            page = resp.json().get("data") or []
            if not page:
                break

            oldest = cursor
            for row in page:
                ts = int(row["fundingRateTimestamp"])
                seen[ts] = {
                    "symbol": row["symbol"],
                    "ts_ms": ts,
                    # Decimal(str) - a float wrap here silently loses the
                    # eighth decimal that distinguishes 0.00002780 from the
                    # 0.0001 base-rate clip.
                    "funding_rate": Decimal(str(row["fundingRate"])),
                }
                oldest = min(oldest, ts)

            if oldest >= cursor or oldest <= start:
                break
            cursor = oldest - 1

        return [seen[k] for k in sorted(seen)]

    def write_csv(self, symbol: str, rows: list[dict], out_dir) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{symbol}_funding.csv"
        fetched_at = self._now()
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["symbol", "ts_ms", "funding_rate", "fetched_at"])
            for r in rows:
                w.writerow([r["symbol"], r["ts_ms"], r["funding_rate"], fetched_at])
        return path


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Backfill Bybit funding history")
    ap.add_argument("--symbols", nargs="+",
                    default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"])
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out-dir", default="backtesting/data/funding")
    ap.add_argument("--base-url", default="http://localhost:8001")
    args = ap.parse_args()

    dl = FundingDownloader(base_url=args.base_url)
    for sym in args.symbols:
        rows = dl.download(sym, days=args.days)
        path = dl.write_csv(sym, rows, args.out_dir)
        first = rows[0]["ts_ms"] if rows else None
        last = rows[-1]["ts_ms"] if rows else None
        print(f"{sym}: {len(rows)} settlements -> {path} (ts {first}..{last})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the host-side loader shim**

Create `backtesting/costs_loader.py`:

```python
"""
Host-side access to services/trading-engine/app/costs.py.

`from app.costs import ...` DOES NOT WORK from backtesting/.
services/technical-analysis/app/__init__.py exists, making `app` a regular
(non-namespace) package, and backtesting/prod_indicators.py:37-38 and
run_walk_forward_ensemble.py:62 both claim `app` for technical-analysis.
Reproduced: with the TA path loaded first, `import app.paper_slippage` raises
ModuleNotFoundError.

costs.py is stdlib-only, so it needs no sys.path manipulation at all - just a
spec load under a non-`app` name. Same mechanism as
run_walk_forward_ensemble.py:96-104, minus the path juggling.
"""

from __future__ import annotations

import csv
import importlib.util
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COSTS_PATH = _REPO_ROOT / "services" / "trading-engine" / "app" / "costs.py"

_cached = None


def load_costs():
    """The costs module, loaded once per process under the name `te_costs`."""
    global _cached
    if _cached is None:
        spec = importlib.util.spec_from_file_location("te_costs", _COSTS_PATH)
        assert spec is not None and spec.loader is not None, f"cannot load {_COSTS_PATH}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _cached = module
    return _cached


def load_funding(symbol: str, data_dir="backtesting/data/funding") -> list:
    """Settlements for one symbol, ascending. Empty list when absent.

    Deliberately NOT raising on a missing file: funding_cost() treats an empty
    series as zero, which is honest, whereas a hardcoded default rate is not.
    Callers that require funding must check for themselves.
    """
    costs = load_costs()
    path = Path(data_dir) / f"{symbol}_funding.csv"
    if not path.is_file():
        return []
    out = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            out.append(
                costs.FundingSettlement(
                    ts_ms=int(row["ts_ms"]),
                    rate=Decimal(row["funding_rate"]),
                )
            )
    out.sort(key=lambda s: s.ts_ms)
    return out
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/killtests/test_funding_downloader.py --no-cov -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the real backfill and record coverage**

The connector must be up (`docker compose -f docker-compose.unified.yml ps bybit-connector`).

```bash
python3 backtesting/funding_downloader.py --days 365 --out-dir backtesting/data/funding

for s in BTCUSDT ETHUSDT SOLUSDT BNBUSDT ADAUSDT; do
  echo -n "$s "; python3 - "$s" <<'PY'
import csv, sys
from decimal import Decimal
from datetime import datetime, timezone
rows = list(csv.DictReader(open(f"backtesting/data/funding/{sys.argv[1]}_funding.csv")))
r = [Decimal(x["funding_rate"]) for x in rows]
ts = [int(x["ts_ms"]) for x in rows]
fmt = lambda t: datetime.fromtimestamp(t/1000, timezone.utc).strftime("%Y-%m-%d")
print(f"n={len(r)} {fmt(min(ts))}..{fmt(max(ts))} mean={sum(r)/len(r)*100:.5f}%/8h "
      f"min={min(r)*100:.4f}% max={max(r)*100:.4f}% neg={sum(1 for x in r if x<0)}")
PY
done
```

Expected: ~1,095 settlements per symbol spanning ~365 days, with means near the figures in the interface facts and a non-zero negative count on every symbol. Paste this into the commit message — it is the coverage record.

- [ ] **Step 7: Commit**

```bash
git add backtesting/funding_downloader.py \
        backtesting/costs_loader.py \
        tests/killtests/test_funding_downloader.py \
        backtesting/data/funding
git commit -m "feat(backtesting): backfill Bybit funding history and add the host costs loader

Nothing in the repo stored funding rates - market_data holds only klines,
orderbook_snapshots and tickers - so 'signed funding' had no data source.
~1095 settlements per symbol over 365 days, through bybit-connector per the
BC-02/D-04 no-direct-Bybit policy.

Rates are parsed as Decimal from Bybit's stringified decimals: a float wrap
loses the eighth decimal that separates the measured 0.0000278 mean from the
0.0001 base-rate clip.

costs_loader.py spec-loads costs.py under the name te_costs. 'from app.costs
import' cannot work from backtesting/ - technical-analysis owns the `app`
package name in that process." -- \
  backtesting/funding_downloader.py \
  backtesting/costs_loader.py \
  tests/killtests/test_funding_downloader.py \
  backtesting/data/funding
```

---

### Task 5: The paper engine calls `costs.py`

Not a "unify two models" task — there is nothing on the other side for three of the five cost legs. The paper engine has **no** maker/taker distinction (`auto_trader.py:2193` says so in code: *"Paper engine has no maker/taker distinction — keep market path"*), never quantizes price, and has no funding at all. This task makes `costs.py` the single implementation and routes the paper engine through it.

**Files:**
- Modify: `services/trading-engine/app/paper_trading.py` (`calculate_commission` `:198-200`)
- Test: `services/trading-engine/tests/test_costs_paper_parity.py` (new)

**Interfaces:**
- Consumes: `costs.fee`, `costs.FeeSchedule`, `costs.Liquidity`.
- Produces: `PaperTradingEngine.fee_schedule: FeeSchedule` built in `__init__` from Settings; `calculate_commission` delegates to `costs.fee`.

Behavior must be **byte-identical** at the current default, so this commit is a pure refactor. `paper_commission_pct = 0.055` percent → `0.00055` fraction → `costs.FeeSchedule(taker=Decimal("0.00055"), ...)`. Assert that equality in the test rather than assuming it.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_costs_paper_parity.py`:

```python
"""
The paper engine and costs.py must agree to the cent on the DETERMINISTIC
cost legs: fees, quantization, min-notional rejection, signed funding.

DELIBERATE EXCLUSION - stop-fill modelling. auto_trader.py:3311-3313 passes
the STOP PRICE as the fill reference regardless of how far the 1h bar closed
through it, so a bar that gaps 4% through a 2% stop still books exactly -2%.
Requiring parity there would mean building the simulator to reproduce that
optimism, and every screen verdict downstream would inherit an unknown
optimistic bias on exactly the trades that decide the answer. Parity on that
leg is re-enabled only after defect E9 corrects the live side; until then the
divergence is asserted as EXPECTED rather than silently tolerated.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.paper_trading as paper_trading_module
from app.costs import FeeSchedule, Liquidity, fee
from app.paper_trading import PaperTradingEngine
from app.position_manager import PositionManager


class _IdentitySlippage:
    def fill_price(self, symbol, side, price):
        return price

    def describe(self):
        return "identity (test)"


@pytest.fixture
def stack_engine():
    """A real PaperTradingEngine over mocked repos.

    The five getters below are the stable construction contract - patch them
    all or __init__ reaches for a live database. Repeated inline rather than
    imported because tasks may be executed out of order.
    """
    position_repo = MagicMock()
    for name in ("create", "update_price", "close", "record_reduction",
                 "record_scale_in", "update_stops"):
        setattr(position_repo, name, AsyncMock())
    position_repo.get_open_positions = AsyncMock(return_value=[])

    portfolio_repo = MagicMock()
    portfolio_repo.record_position_close = AsyncMock()
    portfolio_repo.get_or_create = AsyncMock()

    trade_repo = MagicMock()
    trade_repo.log_trade = AsyncMock()

    risk_manager = MagicMock()
    risk_manager.calculate_stop_loss = MagicMock(return_value=Decimal("0.00000001"))
    risk_manager.calculate_take_profit = MagicMock(return_value=Decimal("99999999"))
    risk_manager.update_daily_pnl = MagicMock()

    with (
        patch("app.position_manager.get_risk_manager", return_value=risk_manager),
        patch("app.position_manager.get_position_repository", return_value=position_repo),
        patch("app.position_manager.get_portfolio_repository", return_value=portfolio_repo),
    ):
        manager = PositionManager()

    with (
        patch("app.paper_trading.get_position_manager", return_value=manager),
        patch("app.paper_trading.get_risk_manager", return_value=risk_manager),
        patch("app.paper_trading.get_trade_repository", return_value=trade_repo),
        patch("app.paper_trading.get_portfolio_repository", return_value=portfolio_repo),
    ):
        engine = PaperTradingEngine()
    engine.slippage = _IdentitySlippage()

    saved = paper_trading_module._paper_engine
    paper_trading_module._paper_engine = engine
    yield engine
    paper_trading_module._paper_engine = saved


def test_settings_percent_converts_to_the_schedule_fraction():
    """paper_commission_pct is a PERCENT (0.055); the schedule is a FRACTION
    (0.00055). This 100x is the exact unit trap this repo has shipped before."""
    from app.config import Settings

    declared = Settings.model_fields["paper_commission_pct"].default
    assert declared == 0.055
    assert Decimal(str(declared)) / Decimal("100") == FeeSchedule.bybit_linear_perp().taker


def test_engine_commission_equals_costs_fee(stack_engine):
    """Byte-identical at the current default - this refactor changes nothing."""
    engine = stack_engine
    schedule = FeeSchedule.bybit_linear_perp()
    for notional in ("10", "6.0269", "21.804", "62551.30", "0.2023"):
        n = Decimal(notional)
        assert engine.calculate_commission(n) == fee(n, Liquidity.TAKER, schedule)


def test_engine_exposes_its_schedule(stack_engine):
    assert isinstance(stack_engine.fee_schedule, FeeSchedule)
    assert stack_engine.fee_schedule.taker == Decimal("0.00055")


def test_stop_fill_parity_is_a_documented_gap():
    """Executable note. The live engine's stop fill is optimistic by
    construction (auto_trader.py:3311-3313 uses the stop price as the fill
    reference). The offline simulator uses the PESSIMISTIC rule instead - fill
    at bar close when the bar closes through the stop - matching the
    stop-first convention backtesting/killtests/h3_atr_replay.py already
    implements. Delete this test only when E9 lands."""
    pytest.skip(
        "E9: live stop fills use the stop price as the fill reference; parity "
        "on that leg is deliberately out of scope until E9 corrects it"
    )
```

Note the `pytest.skip` here is the one permitted form: it names the tracking ID (E9) and documents a deliberate scope boundary, rather than greening a failure. `.claude/rules/testing.md:28` requires exactly that.

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_paper_parity.py --no-cov -q`
Expected: FAIL — `AttributeError: 'PaperTradingEngine' object has no attribute 'fee_schedule'`.

- [ ] **Step 3: Route the engine through `costs.py`**

In `services/trading-engine/app/paper_trading.py`, add to `__init__` next to `self.commission_pct`:

```python
        # costs.py is the single cost implementation (2026-08-07). commission_pct
        # is retained because tests and log lines read it; it MUST equal
        # fee_schedule.taker or the two models have silently diverged.
        self.fee_schedule = FeeSchedule(
            taker=Decimal(str(self.settings.paper_commission_pct)) / Decimal("100"),
            maker=Decimal(str(getattr(self.settings, "paper_maker_commission_pct",
                                      0.020))) / Decimal("100"),
        )
```

and replace `calculate_commission`:

```python
    def calculate_commission(self, order_value: Decimal) -> Decimal:
        """Commission for one leg.

        TAKER unconditionally: this engine has no maker/taker distinction and
        auto_trader.py:2193 states so in code. When PostOnly entries are wired
        (config.py:173 flags them as plumbing only), this becomes a parameter.
        """
        return fee(order_value, Liquidity.TAKER, self.fee_schedule)
```

Import at the top: `from app.costs import FeeSchedule, Liquidity, fee`.

- [ ] **Step 4: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_costs_paper_parity.py tests/test_accounting_invariants_phase1.py tests/test_posted_margin_ledger.py --no-cov -q`
Expected: PASS (one skipped). The accounting invariants must be **unchanged** — this is a pure refactor at the current default; any movement there means the conversion is wrong.

- [ ] **Step 5: Commit**

```bash
git add services/trading-engine/app/paper_trading.py \
        services/trading-engine/tests/test_costs_paper_parity.py
git commit -m "refactor(trading-engine): paper engine computes fees through costs.py

Pure refactor - byte-identical at the current default, asserted rather than
assumed. The percent-to-fraction conversion (0.055 -> 0.00055) is the exact
100x unit trap this repo has shipped before, so it is pinned by a test.

Parity deliberately EXCLUDES stop-fill modelling. auto_trader.py:3311-3313
passes the stop price as the fill reference regardless of how far the bar
closed through it, so a bar that gaps 4% through a 2% stop still books -2%.
Requiring parity there would build that optimism into the simulator and every
screen verdict would inherit it. Re-enabled when E9 lands." -- \
  services/trading-engine/app/paper_trading.py \
  services/trading-engine/tests/test_costs_paper_parity.py
```

---

### Task 6: The research backtester calls `costs.py`, and its two free lunches die

**Files:**
- Modify: `backtesting/backtest_engine.py` (`:128-148` config, `:195-228` resolvers, `:404-418` entry leg, `:443-480` exit leg)
- Test: `tests/killtests/test_backtest_cost_parity.py` (new)

**Interfaces:**
- Consumes: `backtesting/costs_loader.load_costs`, `load_funding`.
- Produces: `BacktestEngine` resolving fees through `costs.fee`, classifying stop/TP exits as **TAKER** with slippage applied, and charging **signed** funding from the backfilled series.

This is a **behavior change**, not a refactor. Say so in the commit — otherwise it gets read as a bug fix and the resulting P&L movement gets attributed to noise.

- [ ] **Step 1: Write the failing test**

Create `tests/killtests/test_backtest_cost_parity.py`:

```python
"""
The research backtester must charge what the venue charges.

Three defects being killed, all in backtesting/backtest_engine.py:
  * :474 classifies stop_loss/take_profit exits as LIMIT => maker, and
    bybit_maker_fee=-0.0001 is a CREDIT, so every stop-out PAID the account.
    A triggered Bybit conditional stop is a MARKET order: taker, and it gaps.
  * :450-452 applies ZERO slippage to those same exits, on the assumption that
    a stop fills exactly at the stop price - which is precisely what a stop
    does not do.
  * :220 charges funding to LONGS ONLY, at a hardcoded constant, with
    funding_enabled defaulting False.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtesting"))

from costs_loader import load_costs  # noqa: E402

costs = load_costs()


def test_stop_exits_are_taker_not_maker():
    from backtest_engine import BacktestEngine

    eng = BacktestEngine(fee_mode="bybit_perp")
    assert eng._liquidity_for_exit("stop_loss") is costs.Liquidity.TAKER
    assert eng._liquidity_for_exit("take_profit") is costs.Liquidity.TAKER
    assert eng._liquidity_for_exit("signal") is costs.Liquidity.TAKER


def test_no_configuration_makes_a_fee_negative():
    from backtest_engine import BacktestEngine

    eng = BacktestEngine(fee_mode="bybit_perp")
    for liq in (costs.Liquidity.MAKER, costs.Liquidity.TAKER):
        assert eng.fee_schedule.rate(liq) > 0


def test_stop_exits_pay_slippage():
    """A stop does not fill at the stop price."""
    from backtest_engine import BacktestEngine

    eng = BacktestEngine(fee_mode="bybit_perp", slippage_mode="fixed")
    assert eng._exit_slippage("stop_loss") > 0
    assert eng._exit_slippage("take_profit") > 0


def test_funding_is_signed_and_shorts_receive_it():
    from backtest_engine import BacktestEngine

    h8 = 8 * 60 * 60 * 1000
    series = [costs.FundingSettlement(ts_ms=h8 * i, rate=Decimal("0.0000278"))
              for i in range(3)]
    eng = BacktestEngine(fee_mode="bybit_perp", funding_enabled=True)

    long_cost = eng._funding_for(Decimal("100"), "LONG", series, 0, h8 * 3)
    short_cost = eng._funding_for(Decimal("100"), "SHORT", series, 0, h8 * 3)

    assert long_cost > 0
    assert short_cost == -long_cost


def test_default_fee_mode_no_longer_charges_the_legacy_ten_bps():
    """fee_mode='fixed' defaulted to commission=0.001 = 10 bps, 1.8x the real
    Bybit taker rate. Every default-path figure in this repo used it."""
    from backtest_engine import BacktestEngine

    eng = BacktestEngine()
    assert eng.fee_schedule.taker == Decimal("0.00055")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/killtests/test_backtest_cost_parity.py --no-cov -q`
Expected: FAIL — `AttributeError: 'BacktestEngine' object has no attribute '_liquidity_for_exit'`.

- [ ] **Step 3: Read the current cost paths before editing**

```bash
sed -n '128,150p' backtesting/backtest_engine.py
sed -n '195,230p' backtesting/backtest_engine.py
sed -n '400,420p' backtesting/backtest_engine.py
sed -n '440,482p' backtesting/backtest_engine.py
```

Every edit below must preserve the existing call shape — `BacktestEngine` is instantiated by several runner scripts (`run_phase1_backtest.py`, `run_phase_comparison.py`, `run_walk_forward*.py`). Keep the constructor kwargs; change what they resolve to.

- [ ] **Step 4: Replace the three cost resolvers**

In `backtesting/backtest_engine.py`:

**(a)** In `__init__`, after the existing kwargs, build the schedule and drop the maker rebate:

```python
        # 2026-08-07: fees resolve through the single cost model. The former
        # bybit_maker_fee = -0.0001 "maker rebate" is GONE: Bybit pays maker
        # rebates only at market-maker tiers a $100 account cannot reach, and
        # combined with classifying stop/TP exits as maker it made every
        # stop-out CREDIT the account. config.py:176 is the correct schedule.
        from costs_loader import load_costs

        self._costs = load_costs()
        self.fee_schedule = self._costs.FeeSchedule.bybit_linear_perp()
```

Keep `bybit_taker_fee` / `bybit_maker_fee` as constructor kwargs for call-site compatibility, but have them override the schedule **only if positive**, and raise on a negative maker rate with a message naming this change.

**(b)** Add the three helpers:

```python
    def _liquidity_for_exit(self, exit_reason: str):
        """Every exit modelled here is TAKER.

        A Bybit conditional stop becomes a MARKET order when triggered, and a
        take-profit modelled as an immediate exit at the level is likewise
        crossing the book. Line 474 previously classified both as LIMIT, which
        with a negative maker rate credited the account on every stop-out.
        """
        return self._costs.Liquidity.TAKER

    def _exit_slippage(self, exit_reason: str) -> float:
        """Slippage on the exit leg. Stops and targets are NOT exempt.

        The prior code applied zero slippage to stop_loss/take_profit exits on
        the assumption they fill exactly at the level - which is precisely
        what a stop does not do.
        """
        return self.slippage

    def _funding_for(self, notional, side, settlements, entry_ts_ms, exit_ts_ms):
        """Signed funding. Positive means the position PAID."""
        return self._costs.funding_cost(
            notional, side, settlements,
            entry_ts_ms=entry_ts_ms, exit_ts_ms=exit_ts_ms,
        )
```

**(c)** Rewrite `_apply_funding` (`:214-226`) to call `_funding_for` with the backfilled per-symbol series from `costs_loader.load_funding`, replacing both the longs-only branch and the `_bar_count % 8` cadence. If no series is present for a symbol, charge **zero** and log once — never fall back to the old constant.

**(d)** At the exit leg (`:443-480`), apply `_exit_slippage(...)` and `_liquidity_for_exit(...)` and compute the fee with `self._costs.fee(...)`.

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/killtests/test_backtest_cost_parity.py --no-cov -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Quantify the behavior change on a known run**

This is not a refactor, so measure it. Re-run one walk-forward before and after and record both:

```bash
git stash push -- backtesting/backtest_engine.py
python3 backtesting/run_walk_forward.py --symbols SOLUSDT --days 180 2>&1 | tail -20 > /tmp/wf_before.txt
git stash pop
python3 backtesting/run_walk_forward.py --symbols SOLUSDT --days 180 2>&1 | tail -20 > /tmp/wf_after.txt
diff /tmp/wf_before.txt /tmp/wf_after.txt
```

Expected: results move **more negative** — the stop-out credit is gone, stops now pay slippage, and shorts now carry signed funding. Paste the diff into the commit message. If anything moved *less* negative, stop and find out why.

- [ ] **Step 7: Commit**

```bash
git add backtesting/backtest_engine.py \
        tests/killtests/test_backtest_cost_parity.py
git commit -m "fix(backtesting): charge what the venue charges

BEHAVIOR CHANGE, not a refactor - published figures from this engine move,
and they move more negative. Recorded here so the movement is not later
attributed to noise.

Three defects killed:
  * stop_loss/take_profit exits were classified LIMIT => maker, and
    bybit_maker_fee was -0.0001, a CREDIT. Every backtested stop-out paid the
    account. A triggered Bybit conditional stop is a market order.
  * those same exits were given ZERO slippage, on the assumption a stop fills
    exactly at the stop price.
  * funding was charged to LONGS ONLY, at a hardcoded constant, on an assumed
    8-bar cadence, and defaulted off - so no published figure ever paid it and
    no short ever received it.

Fees, slippage classification and signed funding now resolve through
costs.py, the same module the paper engine uses. A missing funding series
charges zero and logs; it never falls back to the old constant." -- \
  backtesting/backtest_engine.py \
  tests/killtests/test_backtest_cost_parity.py
```

---

### Task 7: `screen.py` — the hurdle-first killer

**Files:**
- Create: `backtesting/screen.py`
- Test: `tests/killtests/test_screen.py` (new)

**Interfaces:**
- Consumes: `costs_loader.load_costs`, `load_funding`.
- Produces:
  - `@dataclass ScreenResult: n_trades, gross_total, gross_expectancy, mean_leg_notional, gross_edge_bps, cost_bps_taker, cost_bps_maker, funding_total, net_taker, net_maker, ratio_taker, ratio_maker, verdict` where `verdict ∈ {"PASS", "KILL"}`.
  - `screen_trades(trades, *, schedule, slippage_table, slippage_fallback, hurdle_multiple=Decimal("2")) -> ScreenResult`
  - CLI: `python3 backtesting/screen.py --trades <csv> [--hurdle 2.0]`

A trade row needs `symbol`, `side`, `gross_pnl`, `notional_in`, `notional_out`, `entry_ts_ms`, `exit_ts_ms`. The committed H3-secondary tables carry `gross_pnl`, `fees_modelled` (from which notional derives as `fees_modelled / 0.001 / 2` per leg), `symbol`, `side`, `funding_est` — enough to validate against.

- [ ] **Step 1: Write the failing test**

Create `tests/killtests/test_screen.py`:

```python
"""
The hurdle-first screen. It answers ONE question in seconds, before any
statistics run: does gross edge per trade clear twice the all-in cost?

Hurdle arithmetic (design spec section 5.1):
  taker fees + slippage  21 bps majors / 31 bps BNB-ADA  -> hurdle 0.45-0.65%
  maker fees only        4 bps                            -> hurdle 0.10%
  funding                signed, per-symbol, position-dependent - NOT a
                         constant adder, so it is applied per trade
The current ensemble delivers 0.0488%.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtesting"))

from costs_loader import load_costs  # noqa: E402
from screen import screen_trades  # noqa: E402

costs = load_costs()
SCHEDULE = costs.FeeSchedule.bybit_linear_perp()
SLIP = {"BTCUSDT": Decimal("5"), "SOLUSDT": Decimal("5"), "ADAUSDT": Decimal("10")}
FALLBACK = Decimal("10")


def _trade(symbol="SOLUSDT", side="LONG", gross=Decimal("0"), notional=Decimal("10")):
    return {
        "symbol": symbol,
        "side": side,
        "gross_pnl": gross,
        "notional_in": notional,
        "notional_out": notional,
        "entry_ts_ms": 0,
        "exit_ts_ms": 0,
    }


def _screen(trades, hurdle="2"):
    return screen_trades(
        trades,
        schedule=SCHEDULE,
        slippage_table=SLIP,
        slippage_fallback=FALLBACK,
        hurdle_multiple=Decimal(hurdle),
    )


def test_a_strategy_at_five_bps_of_edge_is_killed():
    """The current ensemble: 0.0488% gross against 21 bps of taker cost."""
    trades = [_trade(gross=Decimal("10") * Decimal("0.000488")) for _ in range(500)]
    r = _screen(trades)
    assert r.verdict == "KILL"
    assert Decimal("4") < r.gross_edge_bps < Decimal("6")
    assert r.cost_bps_taker == Decimal("21")
    assert r.ratio_taker < 1


def test_a_strategy_at_sixty_bps_of_edge_passes_the_taker_hurdle():
    trades = [_trade(gross=Decimal("10") * Decimal("0.0060")) for _ in range(500)]
    r = _screen(trades)
    assert r.verdict == "PASS"
    assert r.ratio_taker >= 2


def test_the_hurdle_multiple_is_configurable():
    trades = [_trade(gross=Decimal("10") * Decimal("0.0030")) for _ in range(500)]
    assert _screen(trades, hurdle="2").verdict == "KILL"    # 30 bps vs 2x21
    assert _screen(trades, hurdle="1").verdict == "PASS"    # 30 bps vs 1x21


def test_cost_is_per_symbol_not_averaged():
    """ADA carries 10 bps of slippage per side, BTC 5."""
    ada = _screen([_trade(symbol="ADAUSDT") for _ in range(10)])
    btc = _screen([_trade(symbol="BTCUSDT") for _ in range(10)])
    assert ada.cost_bps_taker == Decimal("31")
    assert btc.cost_bps_taker == Decimal("21")


def test_maker_hurdle_is_much_lower_but_still_reported_separately():
    trades = [_trade(gross=Decimal("10") * Decimal("0.0012")) for _ in range(500)]
    r = _screen(trades)
    assert r.cost_bps_maker == Decimal("4")
    assert r.ratio_maker >= 2      # 12 bps clears 2x4
    assert r.ratio_taker < 2       # but not 2x21
    assert r.verdict == "KILL", "the headline verdict is the TAKER verdict"


def test_an_empty_trade_list_raises_rather_than_passing_vacuously():
    with pytest.raises(ValueError):
        _screen([])


def test_negative_gross_is_killed_without_arithmetic_gymnastics():
    trades = [_trade(gross=Decimal("-0.05")) for _ in range(100)]
    r = _screen(trades)
    assert r.verdict == "KILL"
    assert r.gross_edge_bps < 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/killtests/test_screen.py --no-cov -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen'`.

- [ ] **Step 3: Write the screen**

Create `backtesting/screen.py`:

```python
"""
Hurdle-first screen: does a candidate's gross edge clear twice its cost?

This runs BEFORE any statistics. Most candidates die here in seconds, which is
the point - CLAUDE.md's stated value of this infrastructure is killing bad
strategies cheaply, and "disproved in an afternoon" is a win.

THE HURDLE. Gross edge per trade must be at least `hurdle_multiple` x the
all-in round-trip cost for that symbol:

    taker fees + slippage   21 bps (BTC/ETH/SOL) / 31 bps (BNB/ADA)
    maker fees only          4 bps  (+ unmodelled adverse selection)
    funding                  signed, per-symbol, per-side, per-holding-period

The headline verdict is the TAKER verdict. A candidate that clears only under
maker-only assumptions is NOT passed here: 4 bps covers explicit fees alone,
and adverse selection and non-fill are real costs this module cannot express.
Such a candidate must separately demonstrate a fill model that accounts for
the orders that never fill. Both ratios are reported so that case is visible.

For reference, the deployed ensemble measures 0.0488% (4.88 bps) of gross edge
per trade against 21-31 bps of cost - a 2.3x to 4.1x shortfall, and the reason
paper trading loses money.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from costs_loader import load_costs

_costs = load_costs()
_BPS = Decimal("10000")


@dataclass(frozen=True)
class ScreenResult:
    n_trades: int
    gross_total: Decimal
    gross_expectancy: Decimal
    mean_leg_notional: Decimal
    gross_edge_bps: Decimal
    cost_bps_taker: Decimal
    cost_bps_maker: Decimal
    funding_total: Decimal
    net_taker: Decimal
    net_maker: Decimal
    ratio_taker: Decimal
    ratio_maker: Decimal
    hurdle_multiple: Decimal
    verdict: str

    def render(self) -> str:
        lines = [
            f"n trades                {self.n_trades}",
            f"gross total             {self.gross_total:.6f}",
            f"gross expectancy/trade  {self.gross_expectancy:.10f}",
            f"mean leg notional       {self.mean_leg_notional:.4f}",
            f"gross edge              {self.gross_edge_bps:.4f} bps",
            f"cost, taker             {self.cost_bps_taker:.4f} bps",
            f"cost, maker             {self.cost_bps_maker:.4f} bps",
            f"funding total           {self.funding_total:.6f}",
            f"net, taker              {self.net_taker:.4f}",
            f"net, maker              {self.net_maker:.4f}",
            f"edge/cost, taker        {self.ratio_taker:.3f}x "
            f"(need {self.hurdle_multiple}x)",
            f"edge/cost, maker        {self.ratio_maker:.3f}x",
            f"VERDICT                 {self.verdict}",
        ]
        return "\n".join(lines)


def screen_trades(
    trades: Sequence[Mapping],
    *,
    schedule,
    slippage_table: Mapping[str, Decimal],
    slippage_fallback: Decimal,
    hurdle_multiple: Decimal = Decimal("2"),
    funding_by_symbol: Mapping[str, list] | None = None,
) -> ScreenResult:
    """Score a trade list against the cost hurdle.

    Each trade needs: symbol, side, gross_pnl, notional_in, notional_out,
    entry_ts_ms, exit_ts_ms.

    An empty list RAISES. A vacuous PASS on zero trades is the single most
    dangerous output this module could produce.
    """
    if not trades:
        raise ValueError("no trades to screen — refusing to render a verdict")

    funding_by_symbol = funding_by_symbol or {}

    n = len(trades)
    gross_total = Decimal("0")
    leg_notional_total = Decimal("0")
    cost_taker_total = Decimal("0")
    cost_maker_total = Decimal("0")
    funding_total = Decimal("0")

    for t in trades:
        symbol = t["symbol"]
        n_in = Decimal(str(t["notional_in"]))
        n_out = Decimal(str(t["notional_out"]))
        gross_total += Decimal(str(t["gross_pnl"]))
        leg_notional_total += (n_in + n_out) / 2

        taker_bps = _costs.round_trip_cost_bps(
            symbol,
            entry_liquidity=_costs.Liquidity.TAKER,
            exit_liquidity=_costs.Liquidity.TAKER,
            schedule=schedule,
            slippage_table=slippage_table,
            slippage_fallback=slippage_fallback,
        )
        maker_bps = _costs.round_trip_cost_bps(
            symbol,
            entry_liquidity=_costs.Liquidity.MAKER,
            exit_liquidity=_costs.Liquidity.MAKER,
            schedule=schedule,
            slippage_table=slippage_table,
            slippage_fallback=slippage_fallback,
        )
        avg_leg = (n_in + n_out) / 2
        cost_taker_total += avg_leg * taker_bps / _BPS
        cost_maker_total += avg_leg * maker_bps / _BPS

        series = funding_by_symbol.get(symbol) or []
        if series:
            funding_total += _costs.funding_cost(
                avg_leg,
                t["side"],
                series,
                entry_ts_ms=int(t["entry_ts_ms"]),
                exit_ts_ms=int(t["exit_ts_ms"]),
            )

    mean_leg = leg_notional_total / n
    gross_edge_bps = (gross_total / leg_notional_total) * _BPS

    # Per-symbol costs are reported as the notional-weighted average, so a
    # mixed-symbol candidate is scored against what it would actually pay.
    cost_bps_taker = (cost_taker_total / leg_notional_total) * _BPS
    cost_bps_maker = (cost_maker_total / leg_notional_total) * _BPS

    ratio_taker = (
        gross_edge_bps / cost_bps_taker if cost_bps_taker > 0 else Decimal("0")
    )
    ratio_maker = (
        gross_edge_bps / cost_bps_maker if cost_bps_maker > 0 else Decimal("0")
    )

    verdict = "PASS" if ratio_taker >= hurdle_multiple else "KILL"

    return ScreenResult(
        n_trades=n,
        gross_total=gross_total,
        gross_expectancy=gross_total / n,
        mean_leg_notional=mean_leg,
        gross_edge_bps=gross_edge_bps,
        cost_bps_taker=cost_bps_taker,
        cost_bps_maker=cost_bps_maker,
        funding_total=funding_total,
        net_taker=gross_total - cost_taker_total - funding_total,
        net_maker=gross_total - cost_maker_total - funding_total,
        ratio_taker=ratio_taker,
        ratio_maker=ratio_maker,
        hurdle_multiple=hurdle_multiple,
        verdict=verdict,
    )


def _rows_from_csv(path: str) -> list[dict]:
    with open(path) as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Hurdle-first edge screen")
    ap.add_argument("--trades", required=True, help="CSV of trades")
    ap.add_argument("--hurdle", default="2", help="required edge/cost multiple")
    ap.add_argument("--funding-dir", default="backtesting/data/funding")
    args = ap.parse_args()

    from costs_loader import load_funding

    rows = _rows_from_csv(args.trades)
    symbols = {r["symbol"] for r in rows}
    funding = {s: load_funding(s, args.funding_dir) for s in symbols}

    slippage = {
        "BTCUSDT": Decimal("5"), "ETHUSDT": Decimal("5"), "SOLUSDT": Decimal("5"),
        "BNBUSDT": Decimal("10"), "ADAUSDT": Decimal("10"),
    }
    result = screen_trades(
        rows,
        schedule=_costs.FeeSchedule.bybit_linear_perp(),
        slippage_table=slippage,
        slippage_fallback=Decimal("10"),
        hurdle_multiple=Decimal(args.hurdle),
        funding_by_symbol=funding,
    )
    print(result.render())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/killtests/test_screen.py --no-cov -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add backtesting/screen.py tests/killtests/test_screen.py
git commit -m "feat(backtesting): hurdle-first edge screen

Answers one question in seconds, before any statistics: does gross edge per
trade clear twice the all-in cost? Most candidates die here, which is the
point - 'disproved in an afternoon' is a win.

The headline verdict is the TAKER verdict. A candidate that clears only
maker-only is not passed: 4 bps covers explicit fees alone, and adverse
selection and non-fill are real costs this module cannot express. Both ratios
are reported so the case stays visible.

An empty trade list raises rather than rendering a vacuous PASS." -- \
  backtesting/screen.py tests/killtests/test_screen.py
```

---

### Task 8: Validate the screen against the committed evidence

The screen is only trustworthy if it reproduces figures produced independently. `.planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_1.5x.csv` holds 12,297 trades generated by the deployed ensemble's own signals, and the published verdict's aggregates were re-derived from it on 2026-08-07 and matched exactly.

**Files:**
- Create: `tests/killtests/test_screen_reproduces_h3.py`
- Create: `.planning/evidence/screen-baseline-2026-08-07.md`

**Interfaces:**
- Consumes: `screen_trades`, the two committed per-trade CSVs.
- Produces: a committed baseline document, and a regression test that fails if the screen's arithmetic ever drifts from the published H3-secondary figures.

- [ ] **Step 1: Write the test**

Create `tests/killtests/test_screen_reproduces_h3.py`:

```python
"""
Regression: the screen must reproduce the committed H3-secondary aggregates.

Source: .planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_*.csv
        (12,297 trades from the deployed ensemble's own fired signals)

Targets verified 2026-08-07 by summing the CSVs; all match the published
verdict markdown exactly. fees_modelled = (notional_in + notional_out) * 0.001
and fees_bybit_est = (notional_in + notional_out) * 0.00055, so leg notional
derives as fees_modelled / 0.001 / 2.
"""

import csv
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from costs_loader import load_costs  # noqa: E402
from screen import screen_trades  # noqa: E402

costs = load_costs()

TABLES = {
    "1.5x": REPO / ".planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_1.5x.csv",
    "2.5x": REPO / ".planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_2.5x.csv",
}

EXPECTED = {
    "1.5x": {
        "n": 12297,
        "gross_total": Decimal("41.870782"),
        "expectancy": Decimal("0.0034049591"),
        "fees_bybit": Decimal("94.3604"),
        "fees_modelled": Decimal("171.5643"),
        "funding": Decimal("48.6160"),
        "mean_leg_notional": Decimal("6.975"),
        "edge_bps": Decimal("4.88"),
    },
    "2.5x": {
        "n": 12297,
        "gross_total": Decimal("10.974434"),
        "expectancy": Decimal("0.0008924481"),
        "fees_bybit": Decimal("94.3433"),
        "fees_modelled": Decimal("171.5332"),
        "funding": Decimal("50.8002"),
        "mean_leg_notional": Decimal("6.9746"),
        "edge_bps": Decimal("1.28"),
    },
}


def _load(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            # Per-leg notional from the recorded modelled fee.
            leg = Decimal(r["fees_modelled"]) / Decimal("0.001") / 2
            rows.append(
                {
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "gross_pnl": Decimal(r["gross_pnl"]),
                    "notional_in": leg,
                    "notional_out": leg,
                    "entry_ts_ms": 0,
                    "exit_ts_ms": 0,
                }
            )
    return rows


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_table_is_present_and_intact(variant):
    assert TABLES[variant].is_file(), f"{TABLES[variant]} missing — coverage would be silent"


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_screen_reproduces_the_published_aggregates(variant):
    rows = _load(TABLES[variant])
    exp = EXPECTED[variant]

    assert len(rows) == exp["n"]

    result = screen_trades(
        rows,
        schedule=costs.FeeSchedule.bybit_linear_perp(),
        slippage_table={
            "BTCUSDT": Decimal("5"), "ETHUSDT": Decimal("5"), "SOLUSDT": Decimal("5"),
            "BNBUSDT": Decimal("10"), "ADAUSDT": Decimal("10"),
        },
        slippage_fallback=Decimal("10"),
    )

    assert abs(result.gross_total - exp["gross_total"]) < Decimal("0.001")
    assert abs(result.gross_expectancy - exp["expectancy"]) < Decimal("0.0000001")
    assert abs(result.mean_leg_notional - exp["mean_leg_notional"]) < Decimal("0.01")
    assert abs(result.gross_edge_bps - exp["edge_bps"]) < Decimal("0.05")


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_the_deployed_ensemble_is_killed_by_the_screen(variant):
    """The whole point. 4.88 bps of gross edge against 21-31 bps of cost."""
    result = screen_trades(
        _load(TABLES[variant]),
        schedule=costs.FeeSchedule.bybit_linear_perp(),
        slippage_table={
            "BTCUSDT": Decimal("5"), "ETHUSDT": Decimal("5"), "SOLUSDT": Decimal("5"),
            "BNBUSDT": Decimal("10"), "ADAUSDT": Decimal("10"),
        },
        slippage_fallback=Decimal("10"),
    )
    assert result.verdict == "KILL"
    assert result.ratio_taker < Decimal("0.3"), (
        "the ensemble earns well under a third of its own cost"
    )


@pytest.mark.parametrize("variant", sorted(TABLES))
def test_recorded_fee_columns_match_the_schedule(variant):
    """fees_bybit_est was recorded at 0.00055/side. If costs.py's taker rate
    ever drifts from that, this catches it."""
    exp = EXPECTED[variant]
    schedule = costs.FeeSchedule.bybit_linear_perp()
    implied_notional = exp["fees_modelled"] / Decimal("0.001")
    assert abs(implied_notional * schedule.taker - exp["fees_bybit"]) < Decimal("0.01")
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/killtests/test_screen_reproduces_h3.py --no-cov -q`
Expected: PASS, 8 tests. A failure here means the screen's arithmetic disagrees with independently-produced evidence — fix the screen, not the expectations.

- [ ] **Step 3: Run the screen against the real evidence and record the baseline**

```bash
python3 - <<'PY' > .planning/evidence/screen-baseline-2026-08-07.md
import csv, sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, "backtesting")
from costs_loader import load_costs
from screen import screen_trades

costs = load_costs()
SLIP = {"BTCUSDT": Decimal("5"), "ETHUSDT": Decimal("5"), "SOLUSDT": Decimal("5"),
        "BNBUSDT": Decimal("10"), "ADAUSDT": Decimal("10")}

print("# Screen baseline — deployed ensemble, 2026-08-07\n")
print("Source: `.planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_*.csv`")
print("(12,297 trades generated by the deployed ensemble's own fired signals)\n")

for variant in ("1.5x", "2.5x"):
    p = Path(f".planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_{variant}.csv")
    rows = []
    for r in csv.DictReader(open(p)):
        leg = Decimal(r["fees_modelled"]) / Decimal("0.001") / 2
        rows.append({"symbol": r["symbol"], "side": r["side"],
                     "gross_pnl": Decimal(r["gross_pnl"]),
                     "notional_in": leg, "notional_out": leg,
                     "entry_ts_ms": 0, "exit_ts_ms": 0})
    res = screen_trades(rows, schedule=costs.FeeSchedule.bybit_linear_perp(),
                        slippage_table=SLIP, slippage_fallback=Decimal("10"))
    print(f"## {variant} ATR variant\n\n```\n{res.render()}\n```\n")

print("Any candidate strategy must beat these numbers by the hurdle multiple ")
print("before it earns a single CPCV/DSR run.")
PY

cat .planning/evidence/screen-baseline-2026-08-07.md
```

Expected: both variants render `VERDICT  KILL` with `edge/cost, taker` well under 0.3×.

- [ ] **Step 4: Commit**

```bash
git add tests/killtests/test_screen_reproduces_h3.py \
        .planning/evidence/screen-baseline-2026-08-07.md
git commit -m "test(backtesting): screen must reproduce the committed H3-secondary figures

Regression against 12,297 trades generated by the deployed ensemble's own
signals. Targets were re-derived from the per-trade CSVs on 2026-08-07 and
match the published verdict exactly: gross expectancy 0.0034049591,
fees_bybit 94.3604, net -52.4896, mean leg notional 6.975.

The baseline document is the number every future candidate must beat. The
deployed ensemble earns under a third of its own cost." -- \
  tests/killtests/test_screen_reproduces_h3.py \
  .planning/evidence/screen-baseline-2026-08-07.md
```

---

## Completion criteria

1. `cd services/trading-engine && python3 -m pytest tests/test_costs_fees.py tests/test_costs_quantization.py tests/test_costs_funding.py tests/test_costs_paper_parity.py --no-cov -q` passes.
2. `python3 -m pytest tests/killtests/ tests/test_account_config_sync.py --no-cov -q` passes.
3. `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q` shows only the known pre-existing failures.
4. `backtesting/data/funding/` holds five CSVs of ~1,095 settlements each, spanning ~365 days, each with a non-zero count of negative rates.
5. `python3 backtesting/screen.py --trades .planning/evidence/killtests/H3-secondary-verdict-20260806-table-per_trade_1.5x.csv` prints `VERDICT  KILL`.
6. The before/after walk-forward diff from Task 6 Step 6 is pasted in that commit and moves **more negative**.
7. `.planning/evidence/screen-baseline-2026-08-07.md` is committed.

## What this plan does not do

It does not find edge. It builds the instrument that can recognise edge if it appears, and that kills a candidate cheaply when it does not.

Still missing after this plan, and required before any "this strategy works" claim (L3/L4 of the design spec, their own plan):
- **A fee-inclusive CPCV/DSR path.** None exists anywhere in the repo today. H4 is fee-free by design; the walk-forward DSR path runs frictionless unless `--realistic-sim` is passed.
- **The DSR z-scaling fix.** `backtesting/run_walk_forward.py:214` multiplies annualized Sharpes by `√(n_obs−1)`, a per-observation factor of 16–33, collapsing DSR into a step function on the sign of the numerator. Every recorded DSR in this repo is `0.000` or exactly `0.500` — no intermediate value is reachable. It is a coin, not a gate. All three local copies also drop the skew/kurtosis denominator that `sharpe_metrics.py:223` has.
- **PBO/CSCV**, absent entirely. Multiple-testing correction exists only as prose.
- **A `num_trials` ledger** spanning the whole project rather than one run's path count.
- **Pre-registration** of candidates: cross-sectional momentum (with its expected tradeable-leg count stated up front — only SOL, BNB and ADA fit a $10 budget against min-notional walls of $62.55 for BTC and $18.36 for ETH), then funding as a directional signal.
