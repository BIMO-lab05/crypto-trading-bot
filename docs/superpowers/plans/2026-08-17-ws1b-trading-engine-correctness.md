# WS1-B: Trading-Engine Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair fifteen correctness defects in the trading-engine so that risk gates measure what they claim, cost accounting is complete, sizing statistics are honest, reported backtest fills are the fills the strategy asked for, and dead code stops pretending to be alive — making every subsequent measurement of the system trustworthy.

**Architecture:** Fifteen independent, surgical changes to an existing service. One new capability (perp funding accrual on paper closes), one deletion (an unreachable volume-profile pipeline), one safety fence (the LIVE engine), and twelve repairs. Each task is test-first: write a test that fails against current code, make it pass with the minimal edit, commit. No refactors, no new abstractions.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2 / pydantic-settings v2, `Decimal` for money, pytest (`asyncio_mode = auto`), `unittest.mock`.

## Global Constraints

These apply to **every** task and are not repeated per step.

- **The account is $100.** Never write an account-size literal anywhere, tests included — `tests/test_account_size_invariant.py` enforces it. Host-run tests import the real figure:
  ```python
  import sys
  from pathlib import Path
  _REPO_ROOT = Path(__file__).resolve().parents[3]
  sys.path.insert(0, str(_REPO_ROOT))
  from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402
  ```
  `parents[3]` is correct **only for a file at `tests/` depth**. From `tests/unit/` it resolves to `services/`, not the repo root — use `parents[4]` there, or omit the block entirely when the file never imports `shared.account` (Task 6's test is the one such file in this plan). Do **not** copy the `Decimal("10000.00")` fixtures that still live in `tests/conftest.py` (lines 299, 304, 333–334) — those are a known residual, not a pattern.
- **Run every test from the service directory:** `cd services/trading-engine`. `config.py` declares `env_file=".env"`, which pydantic-settings resolves relative to CWD.
- **Always pass `--no-cov`.** The service `pytest.ini` injects `--cov=app`; the repo-root one injects coverage reporting and `--strict-config`.
- **These tests cannot run in-container.** The image copies `app/` only — no `tests/`, no `shared/`.
- **Never export env vars to steer Settings.** pydantic-settings v2 **deep-merges** `Dict` fields across sources, so an exported `SYMBOL_ALLOCATIONS` unions with the dotenv value and the allocations sum to 1.25 instead of 1.0. `tests/conftest.py` already pins `Settings.model_config["env_file"] = None` at import time — rely on that.
- **New test files must pre-import `app.main` and `app.core.metrics` before `app.auto_trader`**, or prometheus raises `Duplicated timeseries`. Copy the header from `tests/test_exposure_gate_all_paths.py:40-45`.
- **Known-failure baseline: 13 failures out of 2642 collected** — 11 × `test_pairs_trading` (pandas 3 removed the `'H'` resample alias) and 2 × `tests/integration/test_connector_contract.py::TestLiveTradingResponseEnvelope` (stubs mock the retired `risk_manager.can_open_position` API). **Both `TestLiveTradingResponseEnvelope` failures were verified red before any of this work began** — say so when reporting Task 10, or the LIVE fence gets blamed for them. Collection itself is clean: zero errors, 5 permanently-skipped integration modules. One known timing flake to ignore: `tests/unit/test_signal_cache.py::TestSignalCache::test_cache_entries_isolated`.
- **Beware wholesale-skipped test files.** `tests/test_risk_manager.py`, `tests/test_paper_trading.py`, `tests/test_aggregation.py`, `tests/test_multi_timeframe.py`, `tests/unit/test_live_trading_maker.py`, and `tests/risk/test_kelly_position_sizing.py` all carry a module-level `pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")`. **A new test added to any of them silently skips.** Put new tests in new files. The live risk-manager suite is `tests/unit/test_risk_manager.py`.
- **Units are a live trap.** `max_risk_per_trade` is a **fraction** (`0.10`); `max_daily_loss_pct`, `max_position_size_pct`, `max_total_exposure_pct`, `default_stop_loss_pct` are **percents** (`12.0`, `10.0`, `80.0`, `2.0`). Never compare across them without normalizing. Never delete a `* 100` or a `/ 100.0` without proving the other side moved — this class of bug has shipped here before.
- **`remaining_quantity` is read through a None-guard ternary, always.** `Position.__init__` backfills it, but pydantic v2 `from_attributes` hydration can bypass `__init__`, and test mocks may not set it:
  ```python
  qty = (
      pos.remaining_quantity
      if getattr(pos, "remaining_quantity", None) is not None
      else pos.quantity
  )
  ```
- **The format hook runs ruff at 88 columns vs the repo's 100 and has stripped imports before.** Make surgical single-line edits; `git diff` for import churn before every commit.
- **`git status` exceeds 60 seconds on this NTFS/WSL mount.** Never bare `git status`, never `git add -A`. Commit with explicit pathspecs.
- **One task per commit**, `fix(trading-engine): …` / `feat(trading-engine): …` / `refactor(trading-engine): …`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `app/risk_manager.py` | Pre-trade exposure gate. | 1 |
| `app/paper_trading.py` | Paper fills, commission, slippage, cash ledger, performance summary. | 1, 7 |
| `app/position_sizing.py` | `PositionSizer` + its module-global factory. The only production caller is `auto_trader._execute_trade`. | 2 |
| `app/auto_trader.py` | The trading loop. Three entry paths: standard (`_execute_trade`), research/hybrid (`_execute_trade_with_setup`), ensemble. | 3, 4, 5, 6, 12 |
| `app/performance_tracker.py` | `add_trade` records the TradeMetrics that feed Kelly sizing. | 6 |
| `app/risk/funding_gate.py` | `FundingRateClient` — owns the connector base URL and HTTP lifecycle. | 7 |
| `app/costs.py` | Pure, stdlib-only, **nothing is fetched**. Already contains `funding_cost` and `FundingSettlement`. | 7 (read-only) |
| `app/signal_aggregator.py` | Engine-side `SignalAggregator`: fetches indicator legs, plus the dead VP pipeline. | 8, 12 |
| `app/aggregation/voter.py` | Vote weights and category diversity. | 8 |
| `app/aggregation/enhanced_aggregator.py` | Phase-3 combiner incl. the MTF leg. | 11 |
| `app/config.py` | Settings. | 7, 9 |
| `app/live_trading.py` | LIVE engine — fenced, not repaired. | 10 |
| `app/strategies/{momentum_breakout,trend_following,support_resistance}_strategy.py`, `app/utils/support_resistance_detector.py` | Dormant strategy layer carrying price-domain rounding. | 13 |
| `tests/test_price_rounding_invariant.py` (repo root) | AST guard created by Plan A, including its `ALLOW_MARKER` opt-out. | 14 |
| `app/backtesting/backtest_engine.py` | In-service backtester. HTTP-reachable via `/api/v1/backtest/*`; prices every exit off `bar.close`. | 15 |

---

# Part 1 — Live money path (Tasks 1–7)

## Task 1: Exposure gate measures remaining quantity, not original (LIVE)

`check_position_limits` multiplies `entry_price * quantity` — the **original** fill size. A position that scaled out 66% through TP1/TP2 still occupies 100% of its entry notional against the 80% exposure cap, so new entries are rejected too early.

The sibling gate `auto_trader._passes_exposure_gate` was already fixed and is the pattern to mirror; today the two gates **disagree after any partial exit**, and both run on the paper entry path.

**Files:**
- Modify: `app/risk_manager.py:252-256`, `app/paper_trading.py:637-639`
- Modify (existing tests that this fix breaks): `tests/unit/test_risk_manager.py:254`, `:269`
- Test: `tests/test_exposure_remaining_quantity.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: `check_position_limits(current_positions, account_balance) -> Tuple[bool, Optional[str]]` — signature unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_exposure_remaining_quantity.py`:

```python
"""
Exposure must be measured on REMAINING quantity, not original.

A position that scaled out via TP1/TP2 occupies only what is left. Counting
its full entry notional overstates exposure and rejects new entries early.
auto_trader._passes_exposure_gate was already fixed this way; before this
change the two gates disagree after any partial exit, and both run on the
paper entry path.
"""

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))


def _position(entry_price: str, quantity: str, remaining: str | None = None):
    p = MagicMock()
    p.entry_price = Decimal(entry_price)
    p.quantity = Decimal(quantity)
    p.remaining_quantity = Decimal(remaining) if remaining is not None else None
    p.status = Mock(value="OPEN")
    return p


@pytest.fixture
def risk_manager():
    from app.risk_manager import RiskManager

    settings = Mock()
    settings.max_total_exposure_pct = 80.0
    # The ALLOW path of check_position_limits does not return at the exposure
    # branch - it falls through to should_halt_trading() (risk_manager.py:269),
    # which evaluates
    #   Decimal(str(settings.paper_initial_balance))
    #     * Decimal(str(settings.max_daily_loss_pct / 100))
    # at risk_manager.py:87-89. A bare Mock raises InvalidOperation there, so
    # these two lines are what make the post-fix green state reachable at all.
    # 12.0 is the ADR-028 daily-loss breaker; daily_pnl is Decimal("0") so the
    # branch clears. max_open_positions is NOT read by check_position_limits.
    settings.paper_initial_balance = float(ACCOUNT_EQUITY_USD)
    settings.max_daily_loss_pct = 12.0
    with patch("app.risk_manager.get_settings", return_value=settings):
        yield RiskManager()


def test_scaled_out_position_frees_its_exposure(risk_manager):
    """Original notional breaches the cap; remaining does not."""
    # $90 original on a $100 account = 90% > 80% cap.
    # After a 2/3 scale-out only $30 (30%) is still open.
    position = _position("900", "0.1", remaining="0.0333333")

    allowed, reason = risk_manager.check_position_limits(
        current_positions=[position], account_balance=BALANCE
    )

    assert allowed is True, (
        f"a two-thirds scaled-out position still occupied its full entry "
        f"notional: {reason}"
    )


def test_unscaled_position_still_breaches(risk_manager):
    """The gate must still bite when nothing has been scaled out."""
    position = _position("900", "0.1", remaining="0.1")

    allowed, reason = risk_manager.check_position_limits(
        current_positions=[position], account_balance=BALANCE
    )

    assert allowed is False
    assert "Total exposure" in reason


def test_missing_remaining_quantity_falls_back_to_original(risk_manager):
    """DB-hydrated rows can bypass __init__; None must mean 'use quantity'."""
    position = _position("900", "0.1", remaining=None)

    allowed, reason = risk_manager.check_position_limits(
        current_positions=[position], account_balance=BALANCE
    )

    assert allowed is False, "None remaining_quantity must fall back to quantity"
```

- [ ] **Step 2: Run it and watch the first test fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_exposure_remaining_quantity.py --no-cov -q
```

Expected: `test_scaled_out_position_frees_its_exposure` FAILS (the gate rejects); the other two pass.

Pre-fix the position is $90 of notional against a $100 account — 90% > the 80% cap — so `check_position_limits` returns at the exposure branch and never reaches `should_halt_trading`. After Step 3 it *does* reach it, which is the only reason the fixture must set `paper_initial_balance` and `max_daily_loss_pct`.

- [ ] **Step 3: Fix the gate**

In `app/risk_manager.py`, replace lines 252–256:

```python
        total_exposure = sum(
            pos.entry_price * pos.quantity
            for pos in current_positions
            if pos.status.value == "OPEN"
        )
```

with:

```python
        # Exposure is measured on REMAINING quantity — a position that has
        # taken partial exits occupies only what is left. Original quantity
        # overstates a scaled-out position and rejects new entries early.
        # Mirrors auto_trader._passes_exposure_gate, which both gates must
        # agree with: they run on the same paper entry path.
        total_exposure = sum(
            pos.entry_price
            * (
                pos.remaining_quantity
                if getattr(pos, "remaining_quantity", None) is not None
                else pos.quantity
            )
            for pos in current_positions
            if pos.status.value == "OPEN"
        )
```

Do **not** touch lines 258–266. The `* 100` at line 259 and the percent comparison at line 263 are already correct and consistent — deleting either silently disarms the gate.

- [ ] **Step 4: Fix the reporting site the same way**

In `app/paper_trading.py`, replace lines 637–639:

```python
        total_exposure = sum(
            float(pos.entry_price * pos.quantity) for pos in open_positions
        )
```

with:

```python
        total_exposure = sum(
            float(
                pos.entry_price
                * (
                    pos.remaining_quantity
                    if getattr(pos, "remaining_quantity", None) is not None
                    else pos.quantity
                )
            )
            for pos in open_positions
        )
```

This is a live API surface (`handlers/performance.py:62`, `handlers/performance_dashboard.py:1046`) — reported `total_exposure` will drop for scaled-out books. That is the intended correction.

- [ ] **Step 5: Repair the two existing tests this fix breaks — this is part of the task, not a follow-up**

`tests/unit/test_risk_manager.py` builds positions as bare `Mock()` with only `entry_price`, `quantity`, and `status` set. After the fix, `getattr(mock, "remaining_quantity", None)` returns an **auto-created child Mock** (not `None`), and `Decimal * Mock` raises `TypeError`.

In `test_check_position_limits_within_limits` (line ~254) and `test_check_position_limits_exceeds_exposure` (line ~269), add one line to each position mock immediately after its `quantity` assignment:

```python
        open_position.remaining_quantity = open_position.quantity
```

Do not change their assertions or their (grandfathered) balance literals.

- [ ] **Step 6: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_exposure_remaining_quantity.py tests/unit/test_risk_manager.py tests/test_exposure_gate_all_paths.py --no-cov -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git commit -m "fix(trading-engine): exposure gate measures remaining quantity

check_position_limits multiplied entry_price by the ORIGINAL fill size, so a
position that scaled out via TP1/TP2 still occupied its full entry notional
against the 80% cap and rejected new entries early. The sibling gate
auto_trader._passes_exposure_gate was already fixed this way; the two
disagreed after any partial exit and both run on the paper entry path.

Also fixes the same overstatement in paper_trading.get_performance_summary,
a live dashboard surface.

Two existing tests built bare Mock() positions, so getattr returned a child
Mock and Decimal * Mock raised TypeError - updated in the same commit." -- app/risk_manager.py app/paper_trading.py tests/unit/test_risk_manager.py tests/test_exposure_remaining_quantity.py
```

---

## Task 2: Position-sizing risk clamp fires (LIVE) — **read the trap first**

> ### DO NOT DO THIS
> The obvious fix — multiplying `auto_trader`'s fraction stop by 100 to match the docstring's "percent" contract while leaving the `position_sizing.py` formula unchanged — is **wrong by a factor of 100**. `10.0 / 2.0 = 5.0` would cut every 10% position to 5%, i.e. **$5 on the $100 account, exactly the Bybit minimum notional**; anything with a wider stop drops below the floor and gets rejected by the min-notional gate. That halts the paper trader.
>
> The dimensionally correct cap in percent-position terms is `risk_percent / stop_FRACTION`, equivalently `risk_pct / stop_pct * 100`. The checked in-repo reference is `app/risk/kelly_position_sizing.py:366`:
> ```python
>             max_position_by_risk = max_risk_pct / stop_loss_pct * 100
> ```
> For the same inputs (2% budget, 5% stop) both sizers must produce `max_position_by_risk == 40.0`.

Two defects compound to make the clamp vacuous:

1. `auto_trader` passes `stop_loss_pct` as a **fraction** (`abs(price - stop) / price`, e.g. `0.02`), while the docstring declares percent.
2. `get_position_sizer` injects `s.max_risk_per_trade * 100.0` — that is the per-trade **notional cap** (0.10 = 10%), documented as such in `config.py:349-359` — into a parameter the class documents as the **loss-at-stop budget** (2%).

Result: `max_position_by_risk = 10.0 / 0.02 = 500.0`, while `position_pct` never exceeds ~18. `17 > 500` is never true. The clamp has never fired, and its log string hardcodes `"(2% max)"` while the injected budget is 10 — the log lies.

**What this fix does and does not change:** at realistic 1–3% stops a 10% position risks 0.1–0.3% of equity, far under any sane budget, so post-fix the clamp still does not bind on ordinary trades. Its real role is a **wide-stop guard**. The ADR-010 per-trade $10 notional cap is enforced independently at lines 223–225 by `max_position_pct` and is unaffected. Do not "strengthen" the clamp to make it fire on normal trades.

**Files:**
- Modify: `app/position_sizing.py:150` (docstring), `:213-220` (clamp), `:453` (factory injection), `:438-443` (the **whole** `get_position_sizer` docstring — it opens at `:438` and closes at `:443`; replacing a narrower span leaves a nested docstring and a stray `"""`, i.e. a SyntaxError)
- Test: `tests/test_position_sizer_risk_clamp.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: `PositionSizer.calculate_position_size(...) -> PositionSizeResult` — signature unchanged. `stop_loss_pct` is now contractually a **fraction**, with values `>= 0.5` auto-normalized as percent (the ranges are disjoint: percent-valued stops in Settings are bounded `ge=0.5` — `default_stop_loss_pct` at `config.py:414` and `short_stop_loss_pct` at `config.py:522` — while real stop fractions are 0.005–0.10). Do **not** write "every `*_pct` Settings field carries `ge=0.5`": `max_position_size_pct` is `ge=0.1` (`config.py:341`) and `ensemble_min_position_pct` is `ge=0.0` (`config.py:372`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_position_sizer_risk_clamp.py`:

```python
"""
The loss-at-stop clamp must actually fire.

Two defects made it vacuous: auto_trader passes stop_loss_pct as a FRACTION
while the docstring declared percent, and get_position_sizer injected the
per-trade NOTIONAL cap (0.10 -> 10.0) into a parameter documented as the
loss-at-stop budget (2.0). max_position_by_risk = 10.0 / 0.02 = 500 against
a position_pct that never exceeds ~18.

Reference semantics: app/risk/kelly_position_sizing.py:366 computes
max_risk_pct / stop_loss_pct * 100. For a 2% budget and a 5% stop both
sizers must produce 40.0.

Balances here are arbitrary and deliberately not account-size literals - the
assertions are percentage math and balance-independent.
"""

from decimal import Decimal

import pytest

from app.position_sizing import (
    PositionSizer,
    SizingMethod,
    get_position_sizer,
    reset_position_sizer,
)


def _sizer(budget: float = 1.0) -> PositionSizer:
    return PositionSizer(
        min_position_pct=1.0,
        max_position_pct=50.0,
        default_position_pct=50.0,
        max_risk_per_trade_pct=budget,
    )


def _size(sizer: PositionSizer, stop):
    return sizer.calculate_position_size(
        method=SizingMethod.FIXED,
        current_balance=Decimal("200"),
        current_price=Decimal("50000"),
        signal_confidence=0.75,
        stop_loss_pct=stop,
    )


def test_clamp_fires_when_loss_at_stop_exceeds_budget():
    """1% budget, 5% stop -> at most a 20% position."""
    result = _size(_sizer(budget=1.0), 0.05)

    assert result.position_size_pct == pytest.approx(20.0), (
        f"clamp did not bind: got {result.position_size_pct}%, expected 20%"
    )
    assert result.position_size_pct * 0.05 <= 1.0 + 1e-9, (
        "loss at stop exceeds the budget after clamping"
    )
    assert "Risk-limited" in result.reasoning


def test_clamp_inert_at_the_exact_boundary():
    """The comparison is strict >; at equality nothing is clamped."""
    result = _size(_sizer(budget=1.0), 0.02)  # 1.0 / 0.02 == 50.0 == position

    assert result.position_size_pct == pytest.approx(50.0)
    assert "Risk-limited" not in result.reasoning


def test_percent_input_normalizes_to_the_same_answer():
    """0.05 and 5.0 must mean the same stop; the ranges are disjoint."""
    as_fraction = _size(_sizer(budget=1.0), 0.05)
    as_percent = _size(_sizer(budget=1.0), 5.0)

    assert as_percent.position_size_pct == pytest.approx(
        as_fraction.position_size_pct
    )


def test_reasoning_states_the_real_budget_not_a_hardcoded_two_percent():
    # 0.10 stays a FRACTION under the >= 0.5 normalization rule, so the cap is
    # 3.0 / 0.10 = 30 < the 50% FIXED position and the clamp binds. Do NOT use
    # 0.5 here: it lands exactly on the percent-normalization threshold, giving
    # a 600% cap that never binds, and the "fix" that makes it bind is the
    # factor-of-100 error the DO NOT DO THIS box above exists to prevent.
    result = _size(_sizer(budget=3.0), 0.10)

    assert "(2% max)" not in result.reasoning, (
        "the log hardcoded 2% while the injected budget was something else"
    )
    assert "3.0% max" in result.reasoning


def test_factory_injects_the_loss_at_stop_budget_not_the_notional_cap():
    """max_risk_per_trade is the NOTIONAL cap (config.py:349-359) - feeding it
    here as a loss-at-stop budget is what made the clamp structurally dead."""
    reset_position_sizer()
    try:
        sizer = get_position_sizer()
        assert sizer.max_risk_per_trade_pct == pytest.approx(2.0), (
            f"factory injected {sizer.max_risk_per_trade_pct} as the "
            "loss-at-stop budget; the notional cap belongs in max_position_pct"
        )
        assert sizer.max_position_pct == pytest.approx(10.0)
    finally:
        reset_position_sizer()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_position_sizer_risk_clamp.py --no-cov -q
```

Expected red — **exactly these three**:

- `test_percent_input_normalizes_to_the_same_answer`: pre-fix `stop=5.0` gives `1.0 / 5.0 = 0.2`, min-clamped to **1.0**, while `stop=0.05` gives **20.0**.
- `test_reasoning_states_the_real_budget_not_a_hardcoded_two_percent`: the string is the hardcoded `"(2% max)"`.
- `test_factory_injects_the_loss_at_stop_budget_not_the_notional_cap`: **10.0** is injected (`.env` `MAX_RISK_PER_TRADE=0.10`, `config.py:349` `default=0.10`, `× 100.0`).

Expected **green before the change, and it must stay green**:

- `test_clamp_fires_when_loss_at_stop_exceeds_budget` → **20.0**, reasoning `Fixed sizing at 50.00% | Risk-limited (2% max): 50.00% -> 20.00%`. The old formula `max_risk_per_trade_pct / stop_loss_pct` = `1.0 / 0.05` = 20 already binds on a **directly-constructed** sizer.
- `test_clamp_inert_at_the_exact_boundary` → **50.0**, no clamp (`1.0 / 0.02 = 50.0`).

That is the point worth internalizing before touching code: the vacuousness comes from the **factory injection**, not from a directly-constructed sizer. Seeing the headline clamp test pass here is expected and is **not** evidence that the defect does not exist.

- [ ] **Step 3: Fix the clamp**

In `app/position_sizing.py`, replace lines 213–220:

```python
        # Apply risk-per-trade limit if stop loss provided
        # RESEARCH-BASED: This ensures we never risk more than 2% per trade
        if stop_loss_pct is not None and stop_loss_pct > 0:
            max_position_by_risk = self.max_risk_per_trade_pct / stop_loss_pct
            if position_pct > max_position_by_risk:
                original_pct = position_pct
                position_pct = max_position_by_risk
                reasoning += f" | Risk-limited (2% max): {original_pct:.2f}% -> {position_pct:.2f}%"
```

with:

```python
        # Cap the loss taken if the stop is hit.
        #
        # stop_loss_pct is a FRACTION of entry price (0.02 = 2%) - that is what
        # auto_trader._execute_trade passes (abs(price - stop) / price). The
        # percent-valued stop settings are bounded ge=0.5 (default_stop_loss_pct
        # config.py:414, short_stop_loss_pct config.py:522), so the two ranges
        # are disjoint and a value >= 0.5 unambiguously means percent.
        #
        # loss_at_stop(% of equity) = position_pct * stop_fraction, capped at
        # max_risk_per_trade_pct. Equivalent to kelly_position_sizing.py:366's
        # max_risk_pct / stop_loss_pct * 100 for percent input.
        if stop_loss_pct is not None and stop_loss_pct > 0:
            stop_fraction = (
                stop_loss_pct / 100.0 if stop_loss_pct >= 0.5 else stop_loss_pct
            )
            max_position_by_risk = self.max_risk_per_trade_pct / stop_fraction
            if position_pct > max_position_by_risk:
                original_pct = position_pct
                position_pct = max_position_by_risk
                reasoning += (
                    f" | Risk-limited ({self.max_risk_per_trade_pct:.1f}% max): "
                    f"{original_pct:.2f}% -> {position_pct:.2f}%"
                )
```

Then update the parameter docstring at line 150:

```python
            stop_loss_pct: Stop loss distance as a FRACTION of entry price
                (0.02 = 2%). Values >= 0.5 are treated as percent and
                normalized - the ranges are disjoint.
```

- [ ] **Step 4: Fix the factory injection**

In `app/position_sizing.py`, replace lines 450–454:

```python
            _position_sizer = PositionSizer(
                max_position_pct=s.max_position_size_pct,
                default_position_pct=s.max_position_size_pct,
                max_risk_per_trade_pct=s.max_risk_per_trade * 100.0,
            )
```

with:

```python
            _position_sizer = PositionSizer(
                max_position_pct=s.max_position_size_pct,
                default_position_pct=s.max_position_size_pct,
                # max_risk_per_trade is the per-trade NOTIONAL cap
                # (config.py:349-359, a fraction), NOT a loss-at-stop budget.
                # Injecting it here made the clamp structurally dead: it could
                # only bind at a stop 100% away from entry. The notional cap is
                # already enforced below via max_position_pct. The constructor
                # default (2.0) is the documented loss-at-stop budget.
            )
```

Replace the factory docstring **in full — lines 438–443**, from `"""Get or create global position sizer instance.` down to and including its closing `"""`. (Replacing only the `Reads from settings …` sentence leaves the old opening line above your new block and the old closing `"""` below it: a nested docstring plus a stray terminator, i.e. a SyntaxError that makes every Step 5 test fail for an unrelated reason.) `MAX_RISK_PER_TRADE` no longer reaches this sizer (it still feeds the ensemble cascade and other risk gates):

```python
    """Get or create global position sizer instance.

    Reads MAX_POSITION_SIZE_PCT from settings so the per-trade notional cap
    takes effect at boot. MAX_RISK_PER_TRADE deliberately does NOT feed
    max_risk_per_trade_pct: it is a notional cap, not a loss-at-stop budget
    (it still reaches the ensemble sizing cascade and the risk gates).
    Falls back to PositionSizer defaults if settings are unavailable.
    """
```

- [ ] **Step 5: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_position_sizer_risk_clamp.py tests/test_sizing_caps_phase1.py tests/test_auto_trader_min_notional.py tests/unit/test_auto_trader.py --no-cov -q
```

Expected: all pass. `test_sizing_caps_phase1.py` and `test_auto_trader_min_notional.py` in particular prove the $10 per-trade cap still binds — if either moves, the notional cap was disturbed and the fix is wrong.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix(trading-engine): loss-at-stop clamp can actually fire

Two defects made it vacuous. auto_trader passes stop_loss_pct as a FRACTION
(abs(price-stop)/price) while the docstring declared percent, and
get_position_sizer injected max_risk_per_trade - the per-trade NOTIONAL cap,
0.10 - x100 into a parameter documented as the loss-at-stop budget. That
gave max_position_by_risk = 10.0/0.02 = 500 against a position_pct that
never exceeds ~18, so the clamp had never fired, and its log hardcoded
\"(2% max)\" while the budget was 10.

The clamp now takes the fraction contract explicitly (normalizing >= 0.5 as
percent; the ranges are disjoint) and the factory lets the documented 2.0
loss-at-stop default stand. Semantics now match kelly_position_sizing.py:366:
a 2% budget with a 5% stop caps the position at 40%.

Behavior at realistic 1-3% stops is unchanged - a 10% position risks
0.1-0.3% of equity. The clamp's role is a wide-stop guard; the ADR-010 \$10
per-trade notional cap is enforced separately by max_position_pct." -- app/position_sizing.py tests/test_position_sizer_risk_clamp.py
```

---

## Task 3: Standard-mode entries respect the daily trade limit (LIVE)

`_execute_trade` — the path taken by the **default** `strategy_mode="standard"` — never calls `_check_daily_trade_limit()` and never calls `_record_trade()`. Two consequences:

1. Standard mode can open unlimited trades per day; `max_daily_trades` (default 50) is never consulted, and standard fills never consume the budget the other two paths gate on.
2. The cooldown check that *is* present reads `last_trade_time_per_symbol`, which only `_record_trade` writes — so in a standard-only session that branch always passes. (A separate 60s open-cooldown in `_last_open_at` partly masks this, which is why the test must assert on the counters, not merely on whether a second trade is blocked.)

Both the research/hybrid and ensemble paths already do this correctly; mirror them.

**Files:**
- Modify: `app/auto_trader.py:3899` (insert before), `:4113-4115` (insert after)
- Test: `tests/test_standard_path_daily_limit.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: `_execute_trade(symbol, action, confidence, signal)` — signature unchanged; now increments `daily_trades_count` and stamps `last_trade_time_per_symbol[symbol]` on a fill.

- [ ] **Step 1: Write the failing test**

Model the harness on `tests/test_exposure_gate_all_paths.py`, which already drives `_execute_trade` end-to-end with every dependency stubbed. Create `tests/test_standard_path_daily_limit.py`:

```python
"""
Standard-mode entries must respect the daily trade limit and record the trade.

_execute_trade is the default strategy_mode="standard" path. It never called
_check_daily_trade_limit and never called _record_trade, so standard mode
could open unlimited trades per day and its fills never consumed the budget
the research/hybrid and ensemble paths gate on. The cooldown check that IS
present reads last_trade_time_per_symbol, which only _record_trade writes.

Assert on the counters, not merely on whether a second trade is blocked: a
separate 60s open-cooldown in _last_open_at masks the missing cooldown.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402  - prometheus duplicate-registration guard
import app.core.metrics  # noqa: F401,E402

from unittest.mock import Mock, patch  # noqa: E402

import pytest  # noqa: E402

# Reuse the fully-stubbed harness that already drives this exact path.
# `trader` is a FIXTURE and must be imported by name: pytest resolves fixtures
# from the test module's namespace, its conftest chain, or plugins — and it is
# defined per-module at test_exposure_gate_all_paths.py:84-94, not in
# tests/conftest.py. Without this import both tests ERROR at setup with
# "fixture 'trader' not found". The `# noqa: F401` is load-bearing: the ruff
# format hook strips bare imports and would reintroduce that failure. This is
# the established house pattern — see tests/test_cash_conservation_invariant.py
# :26-30, tests/test_stops_persistence.py:18.
from tests.test_exposure_gate_all_paths import (  # noqa: E402,F401  - fixture reuse
    _drive_default_path,
    _signal,
    _PermissiveInstrumentsCache,
    trader,
)


@pytest.mark.asyncio
async def test_filled_standard_entry_feeds_the_daily_counter(trader):
    engine, sizer, mgr = _drive_default_path(trader, [])
    before = trader.daily_trades_count

    with (
        patch("app.auto_trader.get_paper_engine", return_value=engine),
        patch("app.auto_trader.get_position_manager", return_value=mgr),
        patch("app.auto_trader.get_risk_manager", return_value=Mock()),
        patch("app.auto_trader.get_position_sizer", return_value=sizer),
        patch("app.main.get_instruments_cache", lambda: _PermissiveInstrumentsCache()),
    ):
        await trader._execute_trade("BTCUSDT", "BUY", 0.85, _signal())

    assert trader.daily_trades_count == before + 1, (
        "a filled standard-mode entry did not consume the daily budget"
    )
    assert "BTCUSDT" in trader.last_trade_time_per_symbol, (
        "the trade was not recorded, so the general cooldown can never fire"
    )


@pytest.mark.asyncio
async def test_daily_limit_blocks_a_standard_entry(trader):
    engine, sizer, mgr = _drive_default_path(trader, [])
    # daily_trades_date is stamped with today at __init__, so the new-day reset
    # inside _check_daily_trade_limit (auto_trader.py:1448-1454) will not undo
    # this assignment.
    trader.daily_trades_count = trader.max_daily_trades

    with (
        patch("app.auto_trader.get_paper_engine", return_value=engine),
        patch("app.auto_trader.get_position_manager", return_value=mgr),
        patch("app.auto_trader.get_risk_manager", return_value=Mock()),
        patch("app.auto_trader.get_position_sizer", return_value=sizer),
        patch("app.main.get_instruments_cache", lambda: _PermissiveInstrumentsCache()),
    ):
        await trader._execute_trade("BTCUSDT", "BUY", 0.85, _signal())

    engine.execute_market_order.assert_not_awaited()
```

The four imported names exist verbatim in `tests/test_exposure_gate_all_paths.py`: `_PermissiveInstrumentsCache` `:54`, `trader` `:84`, `_signal` `:174`, `_drive_default_path` `:187` (returns `(engine, sizer, position_mgr)` at `:212`). That file also defines `_open_position` `:69`, which this task deliberately does **not** import — no open positions are needed here. The `get_risk_manager` patch mirrors that file's own `_execute_trade` drivers at `:230` / `:256`; `risk_mgr` is bound at `auto_trader.py:3916` and unused on this path, so the patch is defensive parity, not a behavioral requirement.

- [ ] **Step 2: Run it and watch both tests fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_standard_path_daily_limit.py --no-cov -q
```

Expected: both **FAIL on their assertions** — `daily_trades_count` is unchanged and `last_trade_time_per_symbol` is empty in the first; `execute_market_order` was awaited despite the limit in the second. A setup **ERROR** rather than a failure means the `trader` fixture import above was dropped (the ruff hook strips it without the `F401`) — fix the import, do not start editing `auto_trader.py` blind.

- [ ] **Step 3: Add the daily-limit check**

In `app/auto_trader.py`, insert immediately **before** line 3899's cooldown check (limit first, matching the research path's ordering, and before `_claim_open_slot` so a guaranteed rejection never burns a slot):

```python
        # Daily trade limit. The research/hybrid (:1891) and ensemble (:4648)
        # paths already gate here; standard mode did not, so it could open
        # unlimited trades per day and its fills never consumed the budget the
        # other paths measure against.
        if not self._check_daily_trade_limit():
            logger.info(f"Daily trade limit reached, skipping {symbol}")
            self.total_trades_rejected += 1
            return

        if not self._check_symbol_cooldown(symbol):
```

(the existing `if not self._check_symbol_cooldown(symbol):` line and its body stay exactly as they are.)

- [ ] **Step 4: Record the trade on fill**

At line 4113–4115, add one line, exactly as the research path does at `:2243`:

```python
            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                opened = True  # arm dedup cooldown for this symbol
                self._record_trade(symbol)  # Track for daily limit and cooldown
```

- [ ] **Step 5: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_standard_path_daily_limit.py tests/test_exposure_gate_all_paths.py tests/test_ensemble_gates.py --no-cov -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix(trading-engine): standard-mode entries honor the daily trade limit

_execute_trade - the default strategy_mode=standard path - never called
_check_daily_trade_limit and never called _record_trade. Standard mode could
therefore open unlimited trades per day, and its fills never consumed the
budget the research/hybrid and ensemble paths gate on. The cooldown check
that was present reads last_trade_time_per_symbol, which only _record_trade
writes, so in a standard-only session that branch always passed.

Mirrors the research path: limit checked before the open-slot claim so a
guaranteed rejection never burns a slot; trade recorded on FILLED." -- app/auto_trader.py tests/test_standard_path_daily_limit.py
```

---

## Task 4: Portfolio-heat gate is fed the order the engine actually places (LIVE)

The research/hybrid gate at `auto_trader.py:1844-1857` computes `proposed_risk_pct` from `trade_setup.position_size_pct * 100 * (settings.default_stop_loss_pct / 100)`. Three fictions:

- **Size:** `trade_setup.position_size_pct` is the strategy's Kelly fraction, which the sizing block never reads. Actual notional is `paper_initial_balance × symbol_allocation × leverage × heat_multiplier`, vol-parity-adjusted, then cap-clamped. `test_te_cap_05_log_survival.py:100-102` says it outright: *"position_size_pct … is decorative."*
- **Stop:** `default_stop_loss_pct` is not the position's stop. The position gets `trade_setup.stop_loss` (an ATR stop), further regime-adjusted, via `set_position_stops`.
- **Side:** omitted entirely, so `can_open_trade`'s pyramiding / no-hedging branch can never fire on this path.

Meanwhile the post-fill ledger books the **real** quantity and stop, so total heat drifts from what the gate believed it approved. The ensemble path at `:4698-4729` already does this correctly and its comment names this exact site as the broken sibling.

**Files:**
- Modify: `app/auto_trader.py` — delete `1844-1862`, insert after the cap clamp (~`:2143`, before `_passes_exposure_gate` at `:2148`)
- Test: `tests/test_heat_gate_fed_real_order.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: no signature change. `can_open_trade` is now called with `side=` and a stop-distance-based `proposed_risk_pct`, matching `PositionRisk.risk_pct` semantics (percent of equity).

- [ ] **Step 1: Read the two call sites side by side before editing**

```bash
cd services/trading-engine && sed -n '1840,1895p;2100,2150p;4690,4732p' app/auto_trader.py
```

Confirm three things before touching anything: (a) the `heat_multiplier` returned at `:1851` is unconditionally overwritten at `:1888` by `combined_multiplier` — that is what makes moving the gate behavior-preserving for sizing; (b) `side` is the string `"LONG"`/`"SHORT"` from `:1911` until it is rebound to an `OrderSide` at `:2199`, so inserted code between the clamp and `:2199` may use the string; (c) the exact current line numbers, which drift.

- [ ] **Step 2: Write the failing test**

Create `tests/test_heat_gate_fed_real_order.py`:

```python
"""
The portfolio-heat gate must be fed the order the engine actually places.

The research/hybrid gate computed proposed_risk_pct from
trade_setup.position_size_pct (decorative - the sizing block never reads it)
and settings.default_stop_loss_pct (not the position's stop - it gets the ATR
stop from trade_setup, regime-adjusted). It also omitted side=, so
can_open_trade's pyramiding / no-hedging branch could never fire.

The post-fill ledger books the REAL quantity and stop, so total heat drifted
from what the gate approved. The ensemble path at :4698-4729 already does
this correctly and its comment names this site as the broken sibling.

proposed_risk_pct is percent-of-equity and stop-distance based, matching
PositionRisk.risk_pct. A raw notional percent would be 10.0 and would trip
max_per_trade_pct=2.0 on every entry.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

# Reuse the harness that already drives _execute_trade_with_setup end to end.
# `trader` is a module-local FIXTURE (test_te_cap_05_log_survival.py:82-85), not
# a conftest one, so it must be imported by name or pytest errors with
# "fixture 'trader' not found". The `# noqa: F401` is load-bearing: the ruff
# format hook strips bare imports. Same pattern as
# tests/test_cash_conservation_invariant.py:26-30.
from tests.test_te_cap_05_log_survival import (  # noqa: E402,F401  - fixture reuse
    _make_trade_setup,
    _patch_breach_path_deps,
    trader,
)


@pytest.mark.asyncio
async def test_heat_gate_receives_stop_distance_risk_and_side(trader, monkeypatch):
    # _patch_breach_path_deps is a PLAIN FUNCTION taking (monkeypatch, trader)
    # in that order and returning the 2-tuple (paper_engine, position_mgr)
    # (test_te_cap_05_log_survival.py:119, :201). It is NOT a context manager
    # and NOT a fixture - `with` on it raises TypeError, and swapping the args
    # calls monkeypatch.setattr on the AutoTrader.
    #
    # Call it FIRST: it stubs get_combined_size_multiplier (:165-174, returns a
    # (float, dict) 2-tuple the sizing path unpacks) and get_summary_dict
    # (:175-182) on trader.portfolio_heat_manager. Replacing that manager with a
    # bare MagicMock would strip those stubs - override only the one method
    # under test.
    _patch_breach_path_deps(monkeypatch, trader)
    heat = trader.portfolio_heat_manager
    heat.can_open_trade = MagicMock(return_value=(True, None, 1.0))

    # Side-effect-free post-FILLED stubs, mirroring
    # test_te_cap_05_log_survival.py:223-227.
    trader.notification_client = MagicMock()
    trader.notification_client.notify_trade_open = AsyncMock(
        return_value={"success": True}
    )
    trader.kill_switch.update_metrics = MagicMock(return_value=[])

    setup = _make_trade_setup()  # entry_price 60000, stop_loss = entry * 0.98

    # The helper stubs only the PRE-cap-check path; get_aggregator,
    # set_position_stops and partial_profit_taker stay live downstream, so a
    # bare await raises before the assertions run. Both existing tests in that
    # file swallow the same way (:242-247, :336-341). Safe here: the heat gate
    # fires before order placement, so call_args is already captured when the
    # downstream raises.
    try:
        await trader._execute_trade_with_setup(symbol="BTCUSDT", trade_setup=setup)
    except Exception:
        pass

    heat.can_open_trade.assert_called_once()
    kwargs = heat.can_open_trade.call_args.kwargs

    assert kwargs["side"] in ("LONG", "SHORT"), (
        "side= was omitted, so the pyramiding / no-hedging branch never fired"
    )

    stop_fraction = abs(setup.entry_price - setup.stop_loss) / setup.entry_price
    equity = kwargs["equity"]
    # risk% = (notional / equity) * stop_fraction * 100, and the notional is
    # clamped to the per-trade cap, so the fed risk cannot exceed
    # cap_fraction * stop_fraction * 100. Derive cap_fraction from the trader's
    # own settings (auto_trader.py:2111-2118) rather than hardcoding it, exactly
    # as test_te_cap_05_log_survival.py:277-280 does. The pre-fix call feeds
    # 1.0 (= position_size_pct 0.5 * 100 * default_stop_loss_pct/100) against a
    # post-fix bound of 0.2, so this assertion genuinely discriminates.
    cap_fraction = float(trader.settings.max_risk_per_trade)
    if str(trader.settings.trading_mode).upper() == "LIVE":
        cap_fraction = min(cap_fraction, 0.02)
    assert kwargs["proposed_risk_pct"] <= cap_fraction * stop_fraction * 100.0 + 1e-9, (
        f"fed risk {kwargs['proposed_risk_pct']} exceeds what a cap-clamped "
        f"order with a {stop_fraction:.1%} stop can possibly risk"
    )
    assert kwargs["proposed_risk_pct"] > 0.0
    assert equity > 0
```

Every name above was checked against the real file — do not "correct" them back: the setup factory is `_make_trade_setup` at `test_te_cap_05_log_survival.py:88` (no symbol `_trade_setup` exists anywhere in the repo), and `_patch_breach_path_deps` at `:119` has exactly one keyword-only parameter, `balance`. Its two in-repo call sites are `:216` and `:303`, both plain unpacking calls. Do **not** modify that shared helper.

- [ ] **Step 3: Run it and watch it fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_heat_gate_fed_real_order.py --no-cov -q
```

Expected: FAIL on `kwargs["side"]` with a `KeyError` — the current call at `:1851` passes only `symbol`, `proposed_risk_pct` and `equity`. (A setup ERROR instead means the `trader` fixture import was stripped; an `ImportError` means someone "corrected" `_make_trade_setup` back to `_trade_setup`.)

- [ ] **Step 4: Delete the old gate feed**

In `app/auto_trader.py`, delete lines 1844–1862 in full: the `proposed_risk_pct` computation, the `can_open_trade` call, and its `if not can_trade:` block. `heat_multiplier` continues to be defined at `:1888` from `combined_multiplier`, which is what sizing at `:2043` consumes.

One thing above the deletion **does** have to change: the four-line banner at `:1837-1840` (`# ====` / `# PORTFOLIO HEAT CHECK (2025-12-02)` / `# Block trades if portfolio heat is too high` / `# ====`) would otherwise sit over nothing but `:1841-1842`'s `paper_engine = get_paper_engine()` and `current_equity = float(paper_engine.get_balance())`, which are kept because the moved gate consumes `current_equity`. Retitle it to say what remains, e.g.:

```python
            # Equity read for sizing and for the portfolio-heat gate, which now
            # runs after final sizing (see the [HEAT] block below the per-trade
            # cap clamp) so it sees the order actually placed.
```

Nothing else in that region changes.

- [ ] **Step 5: Insert the corrected gate after the cap clamp**

Insert immediately after the cap-clamp block (after the `quantity = (...)` reassignment around `:2143`) and **before** `_passes_exposure_gate`:

```python
            # Portfolio heat gate, fed the ACTUAL order: the cap-clamped
            # notional and the ATR stop the position will carry. Stop-distance
            # based to match PositionRisk.risk_pct (percent of equity) - a raw
            # notional percent would be 10.0 and would trip max_per_trade_pct
            # (2.0) on every single entry. The regime adjustment happens
            # post-fill, so this uses the pre-adjustment stop, exactly as the
            # ensemble path does with its own.
            stop_distance_frac = (
                abs(trade_setup.entry_price - trade_setup.stop_loss)
                / trade_setup.entry_price
                if trade_setup.entry_price
                else 0.0
            )
            proposed_risk_pct = (
                (position_value / current_equity) * stop_distance_frac * 100.0
                if current_equity
                else 0.0
            )
            can_trade, heat_reason, _heat_mult = (
                self.portfolio_heat_manager.can_open_trade(
                    symbol=symbol,
                    proposed_risk_pct=proposed_risk_pct,
                    equity=current_equity,
                    side=side,
                )
            )
            if not can_trade:
                logger.warning(f"[HEAT] Trade BLOCKED for {symbol}: {heat_reason}")
                self.total_trades_rejected += 1
                return
```

Behavioral note to carry into the commit message: at CRITICAL heat the old code blocked at `:1851`; post-move, `get_combined_size_multiplier` drives `position_value` toward zero and the trade is rejected by the min-notional/zero-quantity gates or by this moved gate. Still no order — but the rejection reason string changes.

- [ ] **Step 6: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_heat_gate_fed_real_order.py tests/test_te_cap_05_log_survival.py tests/test_ensemble_gates.py --no-cov -q
```

Expected: all pass. `_patch_breach_path_deps` stubs `can_open_trade` permissively, so moving the call site does not break it.

- [ ] **Step 7: Commit**

```bash
git commit -m "fix(trading-engine): heat gate is fed the order actually placed

The research/hybrid gate computed proposed_risk_pct from
trade_setup.position_size_pct - decorative, the sizing block never reads it -
and settings.default_stop_loss_pct, which is not the position's stop (it gets
the ATR stop from the setup, regime-adjusted). side= was omitted entirely, so
can_open_trade's pyramiding / no-hedging branch could never fire on this path.

The post-fill ledger books the real quantity and stop, so total heat drifted
from what the gate approved, and the per-trade / portfolio heat limits were
enforced against fiction.

Moved below final sizing so it sees the cap-clamped notional and the real ATR
stop. Safe because the multiplier the gate returns was already dead code,
unconditionally overwritten by combined_multiplier. Matches the ensemble
path, whose comment named this site as the broken sibling.

At CRITICAL heat the trade is still rejected, but by the size multiplier
collapsing the notional rather than by this gate - the reason string changes." -- app/auto_trader.py tests/test_heat_gate_fed_real_order.py
```

---

## Task 5: Slippage statistics measure the real fill (LIVE)

`record_execution` is fed `trade_setup.entry_price` as **both** expected and actual, so every `SlippageRecord` has `slippage_pct = 0.0` and `was_rejected = False`. The comment claims *"Actual price is same as expected for market orders in simulation"* — false since PAPER-01 landed (2026-08-03, `fb45efe`): the paper engine applies `paper_slippage.py` and returns the adjusted fill on `executed_order.filled_price`.

The adaptive machinery — per-symbol history, `should_use_limit_order`, the 0.50% rejection threshold, `get_status()` — therefore measures a constant zero and can never learn, warn, or recommend limit orders, while the engine genuinely charges slippage on every fill.

**Files:**
- Modify: `app/auto_trader.py:2268-2278`
- Test: `tests/test_slippage_stats_real_fill.py` (**NEW**)

**Interfaces:**
- Consumes: `executed_order.filled_price` (`Optional[Decimal]`, `models/order.py:75`), already set by the paper engine at `paper_trading.py:297` and by the LIVE maker path.
- Produces: no signature change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_slippage_stats_real_fill.py`:

```python
"""
Slippage stats must compare the reference price against the real fill.

record_execution was fed trade_setup.entry_price as BOTH expected and actual,
so every record carried slippage_pct = 0.0. The comment claimed actual equals
expected "for market orders in simulation" - false since PAPER-01 (fb45efe,
2026-08-03): the paper engine applies paper_slippage.py and returns the
adjusted fill on executed_order.filled_price.

The adaptive machinery (per-symbol history, should_use_limit_order, the 0.50%
rejection threshold, get_status) therefore measured a constant zero.
"""

import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

# `trader` is a module-local FIXTURE (test_te_cap_05_log_survival.py:82-85), not
# a conftest one, so it must be imported by name. `# noqa: F401` is load-bearing
# against the ruff import-stripping hook. Same pattern as
# tests/test_stops_persistence.py:18.
from tests.test_te_cap_05_log_survival import (  # noqa: E402,F401  - fixture reuse
    _make_trade_setup,
    _patch_breach_path_deps,
    trader,
)


@pytest.mark.asyncio
async def test_record_execution_gets_the_real_fill(trader, monkeypatch):
    setup = _make_trade_setup(entry_price=60000.0)

    # _patch_breach_path_deps is a PLAIN FUNCTION taking (monkeypatch, trader)
    # and returning (paper_engine, position_mgr) — not a context manager, and it
    # has no `filled_price` parameter (its only keyword-only argument is
    # `balance`). See test_te_cap_05_log_survival.py:119, :201.
    paper_engine, _ = _patch_breach_path_deps(monkeypatch, trader)

    # The helper hardcodes filled_price = Decimal("60000") at :135, which is
    # numerically EQUAL to _make_trade_setup's default entry_price of 60000.0 —
    # it supplies NO divergence. Override the returned mock's fill here (do not
    # modify the shared helper); `filled_order` itself is a helper-local the
    # test cannot reach, but paper_engine.execute_market_order is
    # AsyncMock(return_value=(filled_order, None)) at :137, so index into it.
    # 5 bps worse than the reference the order was submitted at.
    fill = Decimal(str(setup.entry_price)) * Decimal("1.0005")
    paper_engine.execute_market_order.return_value[0].filled_price = fill

    recorder = MagicMock()
    trader.slippage_manager.record_execution = recorder

    # record_execution sits downstream of kill_switch.update_metrics
    # (auto_trader.py:2257-2265), so stub that and the notification client the
    # way test_te_cap_05_log_survival.py:223-227 does.
    trader.notification_client = MagicMock()
    trader.notification_client.notify_trade_open = AsyncMock(
        return_value={"success": True}
    )
    trader.kill_switch.update_metrics = MagicMock(return_value=[])

    # The helper stubs only the PRE-cap-check path; set_position_stops and
    # partial_profit_taker run live AFTER record_execution and raise. Both
    # existing tests in that file swallow identically (:242-247, :336-341), and
    # the swallow cannot mask the assertions below because record_execution is
    # already captured by the time the downstream raises.
    try:
        await trader._execute_trade_with_setup(symbol="BTCUSDT", trade_setup=setup)
    except Exception:
        pass

    recorder.assert_called_once()
    kwargs = recorder.call_args.kwargs
    assert kwargs["expected_price"] == Decimal(str(setup.entry_price))
    assert kwargs["actual_price"] == fill, (
        f"actual_price {kwargs['actual_price']} is the reference price, not "
        "the engine's slippage-adjusted fill - the stats measure zero"
    )
    assert kwargs["actual_price"] != kwargs["expected_price"]
```

The override two lines above the `try` is **not optional**. `_patch_breach_path_deps` sets `filled_order.filled_price = Decimal("60000")` (`test_te_cap_05_log_survival.py:135`) and `_make_trade_setup` defaults `entry_price=60000.0` (`:88`); `Decimal("60000") == Decimal("60000.0")` is `True`, so without the override the final assertion fails **even against a correct Step 3 fix** — a false negative on a correct implementation. Do not modify the shared helper to fix this; override the returned mock, as above.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_slippage_stats_real_fill.py --no-cov -q
```

Expected: FAIL on `assert kwargs["actual_price"] == fill` — the pre-fix code feeds `trade_setup.entry_price` (60000.0) as both `expected_price` and `actual_price`, while `fill` is 60030. A setup ERROR instead means the `trader` fixture import was stripped.

- [ ] **Step 3: Feed the real fill**

In `app/auto_trader.py`, replace lines 2268–2278:

```python
                # Record expected vs actual for slippage tracking
                # (Actual price is same as expected for market orders in simulation)
                self.slippage_manager.record_execution(
                    symbol=symbol,
                    expected_price=Decimal(str(trade_setup.entry_price)),
                    actual_price=Decimal(
                        str(trade_setup.entry_price)
                    ),  # Same for simulated market orders
                    side=action,
                    quantity=Decimal(str(quantity)),
                )
```

with:

```python
                # Record expected vs actual for slippage tracking. expected is
                # the reference price the order was submitted at; actual is the
                # engine's slippage-adjusted fill. These stopped being equal
                # when PAPER-01 landed (fb45efe): paper_trading applies
                # paper_slippage and returns the fill on filled_price. Feeding
                # the reference as both made every record read 0.0 slippage.
                actual_fill = (
                    executed_order.filled_price
                    if executed_order.filled_price is not None
                    else Decimal(str(trade_setup.entry_price))
                )
                self.slippage_manager.record_execution(
                    symbol=symbol,
                    expected_price=Decimal(str(trade_setup.entry_price)),
                    actual_price=actual_fill,
                    side=action,
                    quantity=Decimal(str(quantity)),
                )
```

- [ ] **Step 4: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_slippage_stats_real_fill.py tests/test_te_cap_05_log_survival.py --no-cov -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(trading-engine): slippage stats compare reference price to real fill

record_execution was fed trade_setup.entry_price as both expected and actual,
so every SlippageRecord carried slippage_pct 0.0 and was_rejected False. The
comment claiming actual equals expected \"in simulation\" has been false since
PAPER-01 (fb45efe): the paper engine applies paper_slippage and returns the
adjusted fill on executed_order.filled_price.

The adaptive machinery - per-symbol history, should_use_limit_order, the
0.50% rejection threshold, get_status - was measuring a constant zero while
the engine genuinely charged slippage on every fill.

Stats only: record_execution may now log SLIPPAGE REJECTED on a large
simulated slippage, but it never cancels an already-filled order." -- app/auto_trader.py tests/test_slippage_stats_real_fill.py
```

---

## Task 6: Performance tracker records net P&L, so Kelly stops sizing on a mirage (LIVE)

`add_trade` recomputes P&L as `(exit_price - entry_price) * position.quantity` — **gross** of fees and slippage, on the **original** quantity. For a position that took partial exits, the final leg is computed as if 100% rode to the final price, and the partial legs' actual P&L at their own exit prices is discarded.

Every Kelly input inherits the bias: `is_winner = pnl > 0` counts fee-laden scratch trades as wins, `avg_win` is too high, `avg_loss` too shallow. Kelly `= W − (1−W)/R` then sizes up on a stats mirage. On $100 with ~0.11% round-trip taker fees, this is exactly the regime where gross-versus-net flips a trade's sign.

**The critical subtlety:** you cannot fix this by recomputing on `remaining_quantity` — `close_position` sets it to `Decimal("0")` *before* `add_trade` runs, so that yields exactly 0. The correct net figure already exists on the object: `position.realized_pnl`, which `close_position` computes as `pnl_on_remaining − close_commission − entry_fee_portion` and **accumulates** across partial legs.

**Files:**
- Modify: `app/performance_tracker.py:19` (import), `:185-191` (P&L), `app/auto_trader.py:3169-3173` (exit price/time)
- Test: `tests/unit/test_performance_tracker_net_pnl.py` (**NEW**)

**Interfaces:**
- Consumes: `Position.realized_pnl` (net), `Position.exit_price` (the slipped fill), `Position.closed_at`.
- Produces: `add_trade(position, exit_price, exit_time) -> TradeMetrics` — signature unchanged. `TradeMetrics.pnl` is now net; `is_winner` and every Kelly statistic inherit that automatically, so `position_sizing.get_performance_stats_from_tracker` needs **no** change.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_performance_tracker_net_pnl.py`:

```python
"""
TradeMetrics must record NET P&L, because Kelly sizes on these numbers.

add_trade recomputed (exit - entry) * position.quantity: gross of fees and
slippage, on the ORIGINAL quantity. For a scaled-out position the final leg
was computed as if the full size rode to the final price, and the partial
legs' own P&L was discarded.

It cannot be fixed by recomputing on remaining_quantity: close_position zeroes
that before add_trade runs. The net figure already exists on the object -
realized_pnl, which close_position computes net of entry and exit commissions
and accumulates across partial legs.

The headline case: a trade whose gross P&L is positive but whose realized P&L
is negative once fees are paid must count as a LOSS.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import PositionSide, PositionStatus
from app.performance_tracker import PerformanceTracker


def _closed_position(gross_positive: bool, realized: str):
    """A CLOSED position whose gross recompute disagrees with realized_pnl."""
    from unittest.mock import MagicMock

    p = MagicMock()
    p.symbol = "ADAUSDT"
    p.strategy = "test"
    p.side = PositionSide.LONG
    p.status = PositionStatus.CLOSED
    p.entry_price = Decimal("0.6000")
    p.quantity = Decimal("16")
    p.remaining_quantity = Decimal("0")  # close_position zeroes this
    p.realized_pnl = Decimal(realized)
    p.opened_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    p.closed_at = datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    p.exit_price = Decimal("0.6010") if gross_positive else Decimal("0.5990")
    return p


def test_fee_eaten_winner_is_recorded_as_a_loss():
    """Gross +0.16%, realized negative after fees. Kelly must see a LOSS."""
    tracker = PerformanceTracker()
    position = _closed_position(gross_positive=True, realized="-0.004")

    trade = tracker.add_trade(
        position, Decimal("0.6010"), datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    )

    assert trade.pnl == Decimal("-0.004"), (
        f"recorded {trade.pnl}; gross recompute would give +0.016 and count a "
        "fee-eaten scratch as a win"
    )
    assert trade.is_winner is False


def test_scaled_out_position_uses_accumulated_realized_pnl():
    """realized_pnl spans all legs; a gross recompute on original quantity
    would price the whole size at the final leg's exit."""
    tracker = PerformanceTracker()
    position = _closed_position(gross_positive=True, realized="0.25")

    trade = tracker.add_trade(
        position, Decimal("0.6010"), datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    )

    assert trade.pnl == Decimal("0.25")
    assert trade.is_winner is True


def test_open_position_falls_back_to_remaining_quantity_gross():
    """Non-CLOSED callers have no realized figure; gross on REMAINING is the
    best available estimate - never on the original quantity."""
    from unittest.mock import MagicMock

    tracker = PerformanceTracker()
    p = MagicMock()
    p.symbol = "ADAUSDT"
    p.strategy = "test"
    p.side = PositionSide.LONG
    p.status = PositionStatus.OPEN
    p.entry_price = Decimal("0.6000")
    p.quantity = Decimal("16")
    p.remaining_quantity = Decimal("8")  # half already scaled out
    p.realized_pnl = Decimal("0")
    p.opened_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    p.closed_at = None
    p.exit_price = None

    trade = tracker.add_trade(
        p, Decimal("0.6100"), datetime(2026, 8, 17, 4, tzinfo=timezone.utc)
    )

    assert trade.pnl == pytest.approx(Decimal("0.08")), (
        f"expected gross on the remaining 8 units (0.01 * 8), got {trade.pnl}"
    )
```

**No `_REPO_ROOT` / `sys.path` block in this one file** — deliberately, and it is the only Task in this plan where that is true. This test lives at `tests/unit/`, one level deeper than the `tests/`-depth files the Global Constraints header was written for, so `parents[3]` there resolves to `services/`, not the repo root. It also imports nothing from `shared.account` (it declares no account size), so it needs no repo-root path at all. Deleting all four lines — `import sys`, `from pathlib import Path`, the `_REPO_ROOT` assignment and the `sys.path.insert` — is the fix; leaving `import sys` and `from pathlib import Path` behind would make both unused and hand the ruff hook (F401 is in its default set) a reason to churn the import block.

- [ ] **Step 2: Run it and watch the first two fail**

```bash
cd services/trading-engine && python3 -m pytest tests/unit/test_performance_tracker_net_pnl.py --no-cov -q
```

Expected: the fee-eaten-winner and scaled-out tests FAIL; the open-position test also fails (it currently uses original quantity, giving 0.16).

- [ ] **Step 3: Fix the recording**

In `app/performance_tracker.py`, extend the import at line 19:

```python
from app.models import Position, PositionSide, PositionStatus
```

Then replace lines 185–191:

```python
        # Calculate P&L
        if position.side == PositionSide.LONG:
            pnl = (exit_price - position.entry_price) * position.quantity
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * position.quantity

        pnl_pct = float((pnl / (position.entry_price * position.quantity)) * 100)
```

with:

```python
        # P&L: trust the position's own accounting. For a CLOSED position,
        # realized_pnl is NET of entry and exit commissions, computed on the
        # actually-closed quantity at the slipped fill price, and it
        # ACCUMULATES partial-exit legs (position_manager.close_position).
        # Recomputing gross-on-original-quantity here fed Kelly optimistic
        # stats: fee-eaten scratch trades counted as wins, avg_win too high,
        # avg_loss too shallow.
        #
        # remaining_quantity is NOT usable for CLOSED positions - close_position
        # zeroes it before this runs. It is only the fallback basis for a
        # caller that hands over a still-open position.
        if position.status == PositionStatus.CLOSED:
            pnl = position.realized_pnl
        else:
            qty = (
                position.remaining_quantity
                if getattr(position, "remaining_quantity", None) is not None
                else position.quantity
            )
            if position.side == PositionSide.LONG:
                pnl = (exit_price - position.entry_price) * qty
            else:  # SHORT
                pnl = (position.entry_price - exit_price) * qty

        pnl_pct = float((pnl / (position.entry_price * position.quantity)) * 100)
```

Keep the `pnl_pct` denominator on the **full** entry notional: for a closed position `realized_pnl` spans every leg, so full notional is the correct base, and it matches `Position.pnl_percentage`.

- [ ] **Step 4: Give the tracker the real exit price**

In `app/auto_trader.py`, replace lines 3169–3173:

```python
                perf_tracker.add_trade(
                    closed,
                    Decimal(str(current_price)),
                    datetime.now(timezone.utc),
                )
```

with:

```python
                perf_tracker.add_trade(
                    closed,
                    # The slipped fill the engine recorded, not the pre-trade
                    # reference tick. getattr-with-fallback because the
                    # get_position miss above can hand back the pre-close
                    # object, whose exit_price is still None.
                    getattr(closed, "exit_price", None) or Decimal(str(current_price)),
                    getattr(closed, "closed_at", None) or datetime.now(timezone.utc),
                )
```

This also normalizes exit-price provenance across all four close paths — market and LIVE closes passed the reference tick while limit-fill and market-fallback passed the actual fill.

- [ ] **Step 5: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/unit/test_performance_tracker_net_pnl.py tests/test_ensemble_attribution_learning_loop.py tests/test_sizing_caps_phase1.py --no-cov -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix(trading-engine): performance tracker records net P&L for Kelly

add_trade recomputed (exit - entry) * original quantity: gross of fees and
slippage, and for a scaled-out position it priced the whole size at the final
leg's exit while discarding the partial legs entirely.

Every Kelly input inherited the bias - is_winner counted fee-eaten scratch
trades as wins, avg_win too high, avg_loss too shallow - so Kelly sized up on
a mirage. At \$100 with ~0.11% round-trip taker fees this is exactly the
regime where gross-versus-net flips a trade's sign.

Fixed by reading position.realized_pnl for CLOSED positions: net of both
commissions, on the actually-closed quantity, accumulated across legs.
remaining_quantity is unusable here - close_position zeroes it first - so it
serves only as the fallback basis for a still-open position.

The caller now passes the recorded exit_price and closed_at rather than the
pre-slippage reference tick, normalizing provenance across all four close
paths. get_performance_stats_from_tracker needs no change; it inherits." -- app/performance_tracker.py app/auto_trader.py tests/unit/test_performance_tracker_net_pnl.py
```

---

## Task 7: Paper engine accrues perp funding — **highest-risk task in this plan**

> ### The trap that must not be repeated
> A funding charge applied **only** to `self.balance` is invisible. `get_performance_summary` reads realized P&L off positions, and the daily-loss breaker is fed by `risk_manager.update_daily_pnl(net_close_pnl)` — neither sees the cash line. This is the exact "wired but never bites" failure documented at `paper_trading.py:256-266` for slippage.
>
> **Funding must flow through BOTH ledgers**, exactly as `close_commission` itself is dual-booked today:
> 1. the cash line at `paper_trading.py:377`, and
> 2. the `close_commission` argument handed to **`close_position`** *and* **`reduce_position`**.

The engine charges commission on both legs and adverse slippage on every fill, but `grep -c funding app/paper_trading.py` returns **0**. Positions live up to the 48h max-hold — up to six Bybit 8h settlements — paying or receiving nothing.

**Do not reimplement the math.** `app/costs.py` already has `funding_cost(notional, side, settlements, *, entry_ts_ms, exit_ts_ms) -> Decimal` — Decimal-based, sign-correct on both axes (LONG pays a positive rate; SHORT is *paid* it), and windowed by settlement timestamp so per-symbol 1h/4h/8h cadences work for free. It is currently called by nothing in the runtime path. `costs.py` is **stdlib-only and nothing is fetched** — the settlements fetch must live elsewhere.

**Do not read `backtesting/data/funding/*.csv` from service code.** The trading-engine Dockerfile copies `app/` only; that would pass host tests and `FileNotFoundError` in the container.

**Files:**
- Modify: `app/config.py` (new Settings field), `app/risk/funding_gate.py` (new client method), `app/paper_trading.py` (`__init__`, new helper, close path)
- Test: `tests/test_paper_funding.py` (**NEW**)

**Interfaces:**
- Consumes: `costs.funding_cost`, `costs.FundingSettlement`; the bybit-connector endpoint `GET /api/v1/market/funding-rate/history?symbol=&category=linear&start=&end=&limit=200`, which returns `{"success": true, "data": [{"symbol", "fundingRate", "fundingRateTimestamp"}]}` newest-first with string values.
- Produces:
  - `Settings.paper_funding_enabled: bool = True`
  - `FundingRateClient.get_settlements(symbol: str, start_ms: int, end_ms: int) -> list[FundingSettlement]` — returns `[]` on any error (fail-open, logged)
  - `PaperTradingEngine._funding_for_leg(symbol, side, notional, opened_at) -> Decimal` — signed; **positive means the position PAID**

- [ ] **Step 1: Write the failing test**

`tests/test_paper_trading.py` is wholesale-skipped — put these in a new file. Create `tests/test_paper_funding.py`:

```python
"""
Paper closes must accrue perp funding, in BOTH ledgers.

The engine charges commission on both legs and slippage on every fill, but
never funding - grep -c funding app/paper_trading.py returned 0. Positions
live up to the 48h max-hold, i.e. up to six Bybit 8h settlements.

The trap: charging only self.balance is invisible. get_performance_summary
reads realized P&L off positions and the daily-loss breaker is fed by
update_daily_pnl(net_close_pnl) - neither sees the cash line. Funding must
also reach position_manager via the close_commission channel, exactly as
close_commission itself is dual-booked (cash at :377, reported P&L at
position_manager.py:510).

Rates here are the measured means recorded in tests/test_costs_funding.py
(module docstring), not invented figures.
"""

import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.costs import FundingSettlement, funding_cost  # noqa: E402

H8 = 8 * 60 * 60 * 1000
BTC_RATE = Decimal("0.0000278")  # BTC mean per 8h, measured 2026-08-07 over 200
#                                  settlements/symbol - tests/test_costs_funding.py:10-14


def _settlements(n: int, rate: Decimal = BTC_RATE, t0: int = 1_000):
    return [FundingSettlement(ts_ms=t0 + H8 * i, rate=rate) for i in range(n)]


@pytest.mark.asyncio
async def test_client_parses_settlements_as_decimal():
    """fundingRate arrives as a STRING; float() would corrupt money math."""
    from app.risk.funding_gate import FundingGateConfig, FundingRateClient

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.00010000",
                    "fundingRateTimestamp": "1672041600000",
                }
            ],
        }
    )
    http = MagicMock()
    http.get = AsyncMock(return_value=response)

    client = FundingRateClient(
        connector_base_url="http://connector",
        config=FundingGateConfig(),
        client=http,
    )
    settlements = await client.get_settlements("BTCUSDT", 0, 1_700_000_000_000)

    assert len(settlements) == 1
    assert settlements[0].rate == Decimal("0.00010000")
    assert isinstance(settlements[0].rate, Decimal)
    assert settlements[0].ts_ms == 1672041600000


@pytest.mark.asyncio
async def test_client_fails_open_to_empty_list():
    """Tape-replay mode stubs this feed to empty; an outage must not raise."""
    from app.risk.funding_gate import FundingGateConfig, FundingRateClient

    http = MagicMock()
    http.get = AsyncMock(side_effect=RuntimeError("connector down"))

    client = FundingRateClient(
        connector_base_url="http://connector",
        config=FundingGateConfig(),
        client=http,
    )

    assert await client.get_settlements("BTCUSDT", 0, 1) == []


def test_long_pays_and_short_is_paid():
    """Sign correctness on both axes - reimplementing this inverts it."""
    settlements = _settlements(3)
    long_cost = funding_cost(
        Decimal("100"), "LONG", settlements, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    short_cost = funding_cost(
        Decimal("100"), "SHORT", settlements, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )

    assert long_cost == Decimal("100") * BTC_RATE * 3
    assert long_cost > 0  # positive means PAID
    assert short_cost == -long_cost


@pytest.mark.asyncio
async def test_close_charges_funding_to_both_ledgers(paper_engine_with_funding):
    """The load-bearing assertion: cash AND reported P&L both move."""
    engine, position_manager, settlements = paper_engine_with_funding

    cash_before = engine.balance
    await engine.execute_market_order(_closing_order(), Decimal("60000"))

    expected = funding_cost(
        Decimal("60000") * Decimal("0.0001"),
        "LONG",
        settlements,
        entry_ts_ms=_ENTRY_MS,
        exit_ts_ms=_EXIT_MS,
    )
    assert expected > 0, "fixture must cross at least one settlement"

    # Ledger 1: cash
    assert engine.balance < cash_before, "funding never reached the cash ledger"

    # Ledger 2: reported P&L, via the close_commission channel
    close_kwargs = position_manager.close_position.call_args.kwargs
    assert close_kwargs["close_commission"] > _commission_only(engine), (
        "funding did not reach position_manager, so reported P&L and the "
        "daily-loss breaker never see it - the 'wired but never bites' trap"
    )
```

The final test needs a fixture wiring a `PaperTradingEngine` with mocked repositories, a mocked `position_manager`, and a stubbed `_funding_for_leg` source. Build it by copying the construction shape from `tests/test_paper_trading.py:62-86` (patching `get_trade_repository`, `get_portfolio_repository`, `get_position_manager`, `get_risk_manager`) — copy the shape, **not** the file, which is skipped. Define `_closing_order`, `_commission_only`, `_ENTRY_MS`, and `_EXIT_MS` in this file. If the end-to-end fixture proves unwieldy, split the assertion: unit-test `_funding_for_leg` directly, and assert the dual-ledger wiring by patching `_funding_for_leg` to return a known `Decimal` and checking both the balance delta and the `close_commission` kwarg. **Do not drop the dual-ledger assertion** — it is the entire point of the task.

- [ ] **Step 2: Run and watch it fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_paper_funding.py --no-cov -q
```

Expected: `test_long_pays_and_short_is_paid` PASSES (that math already exists); everything else fails — `get_settlements` does not exist and no funding reaches either ledger.

- [ ] **Step 3: Add the Settings field**

In `app/config.py`, next to the paper-slippage block:

```python
    # Paper funding (PAPER-02). ON by default: a position held across an 8h
    # Bybit settlement pays or receives funding on the real venue, and omitting
    # it overstates P&L for longs in positive-funding regimes. Fetch failure
    # fails open to zero and LOGS that the leg is gross of funding - silence
    # must never become an assumed rate (costs.py:257-260).
    paper_funding_enabled: bool = Field(
        default=True,
        description=(
            "Charge/credit perp funding on paper closes for each settlement "
            "crossed during the hold"
        ),
    )
```

- [ ] **Step 4: Add the settlements fetch**

In `app/risk/funding_gate.py`, insert after `get_latest_rate` and before `aclose`. Do **not** reuse `get_latest_rate` — it returns a `float` and only the newest rate.

```python
    async def get_settlements(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> "list":
        """Funding settlements in [start_ms, end_ms] as costs.FundingSettlement.

        Returns [] on any error (fail-open, logged), mirroring get_latest_rate.
        Rates are parsed with Decimal, never float: FundingSettlement's
        docstring mandates it and this figure reaches the cash ledger.
        """
        from decimal import Decimal

        from app.costs import FundingSettlement

        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/market/funding-rate/history",
                params={
                    "symbol": symbol,
                    "category": "linear",
                    "start": start_ms,
                    "end": end_ms,
                    "limit": 200,
                },
            )
            response.raise_for_status()
            data = (response.json().get("data") or [])
            return [
                FundingSettlement(
                    ts_ms=int(entry["fundingRateTimestamp"]),
                    rate=Decimal(entry["fundingRate"]),
                )
                for entry in data
                if entry.get("fundingRate") is not None
            ]
        except Exception as e:
            logger.warning(f"[FUNDING] settlements fetch failed for {symbol}: {e}")
            return []
```

The 200 limit is safe: 200 settlements at 8h cadence is ~66 days, and the max-hold is 48h (≤7). No pagination needed.

- [ ] **Step 5: Add the engine helper**

In `app/paper_trading.py`, in `__init__` after `self.slippage = build_slippage_model(self.settings)`:

```python
        self._funding_client = None  # built lazily; PAPER-02
```

Then add a method after `calculate_commission`:

```python
    async def _funding_for_leg(
        self, symbol: str, side: PositionSide, notional: Decimal, opened_at
    ) -> Decimal:
        """Signed funding paid over [opened_at, now]. POSITIVE means PAID.

        Fails open to zero with a loud log - a silent zero would read as
        'no funding was due' rather than 'we could not find out'.
        """
        if not getattr(self.settings, "paper_funding_enabled", False):
            return Decimal("0")

        from datetime import datetime, timezone

        from app.costs import funding_cost
        from app.risk.funding_gate import FundingGateConfig, FundingRateClient

        if self._funding_client is None:
            self._funding_client = FundingRateClient(
                connector_base_url=self.settings.bybit_connector_url,
                config=FundingGateConfig(),
            )

        entry_ts_ms = int(_as_utc(opened_at).timestamp() * 1000)
        exit_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        settlements = await self._funding_client.get_settlements(
            symbol, entry_ts_ms, exit_ts_ms
        )
        if not settlements and exit_ts_ms - entry_ts_ms >= 8 * 3600 * 1000:
            logger.error(
                f"[FUNDING] no settlements fetched for {symbol} over "
                f"{(exit_ts_ms - entry_ts_ms) // 3600000}h hold - this leg's "
                "P&L is GROSS of funding"
            )

        return funding_cost(
            notional,
            side.value,
            settlements,
            entry_ts_ms=entry_ts_ms,
            exit_ts_ms=exit_ts_ms,
        )
```

`_as_utc` is already imported at `paper_trading.py:20`. `side.value` is `"LONG"`/`"SHORT"`, exactly what `funding_cost` validates.

- [ ] **Step 6: Wire BOTH ledgers — the load-bearing step**

In the close path, after `margin_returned = self.position_manager.consume_posted_margin(...)` (~line 372):

```python
            funding_paid = await self._funding_for_leg(
                order.symbol,
                target.side,
                target.entry_price * close_qty,
                target.opened_at,
            )
```

**Ledger 1 — cash.** Replace line 377:

```python
            self.balance += margin_returned + realized_pnl - close_commission
```

with:

```python
            self.balance += (
                margin_returned + realized_pnl - close_commission - funding_paid
            )
```

**Ledger 2 — reported P&L.** Pass `close_commission=close_commission + funding_paid` to **both** `self.position_manager.close_position(...)` (~line 393) and `self.position_manager.reduce_position(...)` (~line 404). This is the only injectable channel that reaches reported realized P&L *and* the daily-loss breaker for both full and partial closes.

`funding_paid` may be **negative** (a SHORT in a positive-funding regime is *paid*); Decimal arithmetic handles that in both ledgers. Add it to the close log line.

- [ ] **Step 7: Verify, including the negative case**

```bash
cd services/trading-engine && python3 -m pytest tests/test_paper_funding.py tests/test_costs_funding.py tests/test_cash_conservation_invariant.py tests/test_accounting_invariants_phase1.py tests/test_partial_exit_cash_persistence.py --no-cov -q
```

Expected: all pass. The cash-conservation and accounting invariants are the real gate here — if either breaks, funding is being double-counted or is reaching only one ledger. Any test asserting an exact post-close balance must set `paper_funding_enabled=False` or stub `_funding_for_leg`.

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(trading-engine): paper closes accrue perp funding

The engine charged commission on both legs and slippage on every fill but
never funding - grep -c funding app/paper_trading.py returned 0 - while
positions live up to the 48h max-hold, i.e. up to six Bybit 8h settlements.

Funding flows through BOTH ledgers, exactly as close_commission already does:
the cash line, and the close_commission argument to close_position AND
reduce_position. Charging only cash would have been invisible -
get_performance_summary reads realized P&L off positions and the daily-loss
breaker is fed by update_daily_pnl - the 'wired but never bites' trap
documented for slippage at paper_trading.py:256-266.

Math is the existing costs.funding_cost: Decimal, sign-correct on both axes
(LONG pays a positive rate, SHORT is paid it), windowed by settlement
timestamp so per-symbol cadence works for free. Rates come from the
bybit-connector funding-rate history endpoint via a new
FundingRateClient.get_settlements, parsed with Decimal, never float.

Fetch failure fails open to zero and logs loudly that the leg is gross of
funding - silence must not become an assumed rate. Tape-replay mode stubs
the feed to empty and is tolerated." -- app/config.py app/risk/funding_gate.py app/paper_trading.py tests/test_paper_funding.py
```

---

# Part 2 — Live signal path (Task 8)

## Task 8: Re-enable the SQZMOM leg and categorize ADX (LIVE)

`signal_aggregator.py:746` has `SQZMOM_ENHANCED` commented out of `fetch_all_indicators` with the reason *"DISABLED: stuck at 0.50 HOLD"*. That root cause was **found and fixed on 2026-05-05** — `indicator_service.py:403-422` documents that the endpoint previously read non-prefixed keys and now correctly reads the `sqz_`-prefixed columns. The fetcher, its 1.4 metadata weight, and its VOLATILITY category all still exist; only the one line keeps it dark.

Separately, ADX (which *does* vote, since 2026-05-06) is missing from `INDICATOR_CATEGORIES`, so `get_indicator_category` returns `"OTHER"` and a lone ADX vote mints its own free category — weakening the min-2-categories diversity gate.

**Do not bundle `RSI_DIVERGENCE`** (disabled the same way at `:744`). Its cause — "stuck at 0.20 confidence" — has no documented fix.

**Files:**
- Modify: `app/signal_aggregator.py:746`, plus its three stale "SQZMOM disabled" wordings at `:719` (docstring), `:726` (log string) and `:789-793` (the shadow-mode comment); `app/aggregation/voter.py:39`
- Test: `tests/test_sqzmom_leg_enabled.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: `fetch_all_indicators` now returns an additional `SQZMOM_ENHANCED` key. Total voting weight grows by 1.4, slightly diluting every other leg — `aggregation_threshold` (0.15) and `min_consensus` (3) are share- and count-based and stay reachable.

- [ ] **Step 1: Write the failing test**

```python
"""
SQZMOM_ENHANCED must vote, and ADX must be categorized.

The leg was commented out of fetch_all_indicators as "stuck at 0.50 HOLD".
That cause was root-caused and fixed 2026-05-05 (indicator_service.py:403-422:
the endpoint read non-prefixed keys and now reads the sqz_-prefixed columns).
The fetcher, its 1.4 metadata weight and its VOLATILITY category all still
exist - only the comment keeps it dark.

ADX votes (since 2026-05-06) but is absent from INDICATOR_CATEGORIES, so
get_indicator_category returns "OTHER" and a lone ADX vote mints its own
category, weakening the min-2-categories diversity gate.

RSI_DIVERGENCE stays disabled: its "stuck at 0.20" cause has no documented fix.
"""

import inspect

from app.aggregation.voter import INDICATOR_CATEGORIES
from app.signal_aggregator import SignalAggregator


def _fetch_entries(source: str, key: str, fetcher: str) -> list[str]:
    """The fetch_all_indicators task-dict entries for one indicator.

    Matched on the fetcher call AND the dict key, never on the bare indicator
    name: other lines inside this same method mention these names in prose -
    the docstring at :719, the log string at :726, and the shadow-mode comment
    at :789-793, which lists RSI_DIVERGENCE and SQZMOM_ENHANCED together. A
    name-only scan trips on that prose and can never go green.
    """
    needle_key = f'"{key}":'
    return [
        line for line in source.splitlines() if needle_key in line and fetcher in line
    ]


def test_sqzmom_enhanced_is_in_the_fetch_set():
    source = inspect.getsource(SignalAggregator.fetch_all_indicators)
    entries = _fetch_entries(source, "SQZMOM_ENHANCED", "fetch_enhanced_sqzmom")

    # Exactly one, or the assertion below is measuring nothing.
    assert len(entries) == 1, f"expected one fetch entry, found {entries!r}"
    assert not entries[0].strip().startswith("#"), (
        "SQZMOM_ENHANCED is still commented out of fetch_all_indicators"
    )


def test_rsi_divergence_stays_disabled():
    """Its disable cause has no documented fix - do not bundle it."""
    source = inspect.getsource(SignalAggregator.fetch_all_indicators)
    entries = _fetch_entries(source, "RSI_DIVERGENCE", "fetch_rsi_divergence")

    assert len(entries) == 1, f"expected one fetch entry, found {entries!r}"
    assert entries[0].strip().startswith("#")


def test_adx_is_categorized_as_trend():
    assert "ADX" in INDICATOR_CATEGORIES["TREND"], (
        "an uncategorized ADX vote counts as its own OTHER category and "
        "weakens the diversity gate"
    )
```

- [ ] **Step 2: Run and watch it fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_sqzmom_leg_enabled.py --no-cov -q
```

Expected: the SQZMOM and ADX tests FAIL; the RSI_DIVERGENCE test passes.

- [ ] **Step 3: Uncomment the leg**

In `app/signal_aggregator.py`, replace line 746:

```python
            # "SQZMOM_ENHANCED": self.fetch_enhanced_sqzmom(symbol, interval),  # DISABLED: stuck at 0.50 HOLD
```

with:

```python
            # Re-enabled 2026-08-17: the "stuck at 0.50 HOLD" cause was fixed
            # 2026-05-05 (indicator_service.py:403-422 — the endpoint read
            # non-prefixed keys; it now reads the sqz_-prefixed columns).
            "SQZMOM_ENHANCED": self.fetch_enhanced_sqzmom(symbol, interval),
```

Then run `grep -n SQZMOM app/signal_aggregator.py` — do **not** work from a line range, because this replacement turns one line into four and every pointer below `:746` shifts by +3 the instant it lands. Three wordings now lie and must be fixed in this same commit:

1. `:719`, inside the `fetch_all_indicators` docstring — `- Advanced: Ichimoku (RSI_DIVERGENCE and SQZMOM_ENHANCED disabled for low confidence)` must stop listing SQZMOM_ENHANCED as disabled.
2. `:726`, the log string — `"  Including advanced indicators: ICHIMOKU (RSI_DIVERGENCE and SQZMOM_ENHANCED disabled for better confidence)"` must name SQZMOM_ENHANCED as *included*.
3. `:789-793`, the shadow-mode comment — "*the False branch is the shadow-mode hook reserved for a follow-up that observes disabled indicators (RSI_DIVERGENCE, SQZMOM_ENHANCED) without counting their vote*". Edit the parenthetical down to `RSI_DIVERGENCE`; do **not** delete the comment, the hook is still real.

**Leave `Total voting indicators: 9` at `:722` exactly as it is.** It counts 9 but only 8 indicators actually vote today (ATR is pulled out separately at `:764-774`; TREND_FILTER and VOLUME_CONFIRMATION are excluded at `:814` and `voter.py:384`), so re-enabling SQZMOM_ENHANCED makes the existing 9 correct. Do not bump it to 10.

- [ ] **Step 4: Categorize ADX**

In `app/aggregation/voter.py`, line 39:

```python
    "TREND": {"SMA", "EMA", "ICHIMOKU", "ADX"},
```

- [ ] **Step 5: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_sqzmom_leg_enabled.py tests/unit/test_voter.py tests/unit/test_signal_aggregator.py tests/unit/test_aggregator_core.py --no-cov -q
```

Expected: all pass. No existing test pins the `fetch_all_indicators` key set.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix(trading-engine): re-enable the SQZMOM leg, categorize ADX

SQZMOM_ENHANCED was commented out of fetch_all_indicators as \"stuck at 0.50
HOLD\". That cause was root-caused and fixed 2026-05-05 - the endpoint read
non-prefixed keys and now reads the sqz_-prefixed columns
(indicator_service.py:403-422). The fetcher, its 1.4 metadata weight and its
VOLATILITY category all still existed; only the comment kept it dark.

ADX has voted since 2026-05-06 but was missing from INDICATOR_CATEGORIES, so
a lone ADX vote minted its own OTHER category and weakened the min-2-category
diversity gate.

RSI_DIVERGENCE deliberately stays disabled - its \"stuck at 0.20\" cause has
no documented fix. Total voting weight grows by 1.4; the aggregation
threshold and min-consensus are share- and count-based and stay reachable." -- app/signal_aggregator.py app/aggregation/voter.py tests/test_sqzmom_leg_enabled.py
```

---

# Part 3 — Config and safety (Tasks 9–10)

## Task 9: `portfolio_manager_url` default points at portfolio-manager

The default is `http://localhost:8006` — the **notification-service** port. Portfolio-manager is 8003. Compose injects the correct value, so the container never sees it; it bites host runs and anyone copying `.env.example` (which regressed to 8006 while older env backups correctly say 8003). The one consumer is `handlers/health.py:268`, which probes what it believes is portfolio-manager.

**Files:** `app/config.py:57-59`, `services/trading-engine/.env.example:15`; test `tests/test_config_service_urls.py` (**NEW**)

- [ ] **Step 1: Write the failing test**

```python
"""portfolio_manager_url must not point at the notification-service port."""

from app.config import Settings


def test_portfolio_manager_url_uses_port_8003():
    settings = Settings()
    assert settings.portfolio_manager_url.endswith(":8003"), (
        f"portfolio_manager_url is {settings.portfolio_manager_url}; "
        "8006 is notification-service"
    )


def test_portfolio_manager_and_notification_urls_differ():
    """The two being equal is exactly the defect."""
    settings = Settings()
    assert settings.portfolio_manager_url != settings.notification_service_url
```

Construct `Settings()` directly rather than `get_settings()` — the latter is a process-lifetime singleton. `conftest.py` pins `env_file=None`, so the test sees the code default, which is what we want to assert.

- [ ] **Step 2: Run, watch both fail, then fix both files**

`app/config.py` line 58: `default="http://localhost:8006"` → `default="http://localhost:8003"`.

`services/trading-engine/.env.example` line 15: `PORTFOLIO_MANAGER_URL=http://localhost:8006` → `...:8003`. The Read/Write tools may be denied on dotfiles here; use Bash with pathlib if so.

- [ ] **Step 3: Verify and commit**

```bash
cd services/trading-engine && python3 -m pytest tests/test_config_service_urls.py tests/test_capital_defaults_phase1.py --no-cov -q
```

```bash
git commit -m "fix(trading-engine): portfolio_manager_url default is port 8003

The default was http://localhost:8006 - the notification-service port.
Compose injects the correct value so the container never saw it, but host
runs and anyone copying .env.example got it wrong (.env.example had
regressed to 8006 while older env backups correctly say 8003).

The one consumer is the detailed-health dependency probe, which reported on
whatever answered 8006 while labelling it portfolio_manager." -- app/config.py .env.example tests/test_config_service_urls.py
```

---

## Task 10: Fence the LIVE trading engine

`LiveTradingEngine` corrupts the books three ways: it stamps `Order.filled_price = current_price` (the caller's reference tick, never the exchange fill), it calls `create_position` without `entry_fee` or `posted_margin` so both default to `Decimal("0")`, and its `close_position` passes no `close_commission` — so a frictionless net P&L feeds the daily-loss breaker **and** `position_manager.close_position` then reads the *paper* engine's cash balance and persists it to the `paper_trading` portfolio row. Live and paper share one `PositionManager` and one DB row.

LIVE is also mechanically impossible at $100 (a 2% cap is $2, below the ~$5 venue minimum) and unreachable via compose (which never passes `TRADING_MODE` to this service). **Fence it; do not build it out.**

**Report honestly:** the two `TestLiveTradingResponseEnvelope` failures in the baseline were verified red *before* this work. They bypass `__init__` via `__new__`, so the fence does not affect them either way.

**Files:** `app/live_trading.py:51-57`; test `tests/unit/test_live_engine_fence.py` (**NEW**)

- [ ] **Step 1: Write the failing test**

```python
"""The LIVE engine must be unconstructible until its accounting is repaired."""

import pytest


def test_live_engine_construction_is_fenced():
    from app.live_trading import LiveTradingEngine

    with pytest.raises(RuntimeError, match="fenced"):
        LiveTradingEngine()


def test_factory_is_fenced_too():
    import app.live_trading as live_trading

    live_trading._live_engine = None
    with pytest.raises(RuntimeError, match="fenced"):
        live_trading.get_live_engine()
```

- [ ] **Step 2: Run, watch it fail, then add the fence**

Insert as the **first statement** of `LiveTradingEngine.__init__`, immediately after the docstring:

```python
        raise RuntimeError(
            "LIVE trading path is fenced off (2026-08-17): LiveTradingEngine "
            "records fills at the reference price with zero fees and zero "
            "posted margin, and its closes write the PAPER cash ledger "
            "(position_manager.close_position -> get_paper_engine()"
            ".get_balance() -> portfolio row 'paper_trading'). LIVE is also "
            "not mechanically viable at the $100 account: the 2% LIVE cap is "
            "$2, below the ~$5 venue min-notional. Repair the accounting and "
            "remove this fence deliberately before any LIVE build-out."
        )
```

Leave the rest of the class in place as the reference for the eventual repair. Do not delete the now-unreachable code and do not refactor.

- [ ] **Step 3: Verify blast radius**

```bash
cd services/trading-engine && python3 -m pytest tests/unit/test_live_engine_fence.py tests/integration/test_connector_contract.py --no-cov -q
```

Expected: the fence tests pass; `TestLiveTradingResponseEnvelope` remains **2 failed — exactly as it was before this plan started.** Confirm that count is unchanged rather than assuming it.

Then confirm the paper loop cannot be crashed by the fence: `get_live_engine` is only reached when `trading_mode == "LIVE"`, and all three call sites are contained: `auto_trader.py:1976` (entry, `_execute_trade_with_setup`) sits under the broad `except Exception` at `:2526`, which logs and increments `total_trades_rejected`; `:3071` (`_close_position`) sits under the broad `except Exception` at `:3117`, which logs and falls out of the function; `:3352` (`_close_position_with_limit_order`) sits in a narrow `try` whose `except Exception as live_err` at `:3359` sets `ok, close_err = False, str(live_err)`, after which the `else:` branch logs the failure and returns at `:3387`.

- [ ] **Step 4: Commit**

```bash
git commit -m "fix(trading-engine): fence the LIVE engine until its accounting is repaired

LiveTradingEngine corrupts the books three ways: it stamps filled_price with
the caller's reference tick rather than the exchange fill; it calls
create_position without entry_fee or posted_margin, so both default to zero;
and its close passes no close_commission, so a frictionless net P&L feeds the
daily-loss breaker AND position_manager then reads the PAPER engine's cash
balance and persists it to the paper_trading portfolio row. Live and paper
share one PositionManager and one DB row.

LIVE is also mechanically impossible at \$100 - a 2% cap is \$2 against a ~\$5
venue minimum - and unreachable via compose, which never passes TRADING_MODE
to this service. Fenced at construction, not built out.

Baseline note: the two TestLiveTradingResponseEnvelope failures were verified
red before this work; they bypass __init__ via __new__ and are unaffected." -- app/live_trading.py tests/unit/test_live_engine_fence.py
```

---

# Part 4 — Dormant code and its guard (Tasks 11–14)

Tasks 11–13 touch code with **no runtime caller**. They are hygiene and parity, and they earn the AST guard extension in Task 14. Label 11–13 DORMANT in any status report; do not describe them as money-path repairs. Task 14 is neither dormant nor a repair — it is the test-only guard extension that locks Task 13's cleanup in place, and it is the one task in this plan whose commit touches a file outside `services/trading-engine/`.

## Task 11: MTF leg — scale and key, in one task (DORMANT)

Two defects that must be fixed together, because either alone still yields a permanently-zero leg and the test stays red:

1. `enhanced_aggregator.py:312/317` compares `alignment_score` (a **0–1 fraction** from the TA payload) against `self.min_alignment_score = 50.0`, so the early return fires on every possible input.
2. `:314` reads `mtf_analysis.get("signal_strength", 0.0)`, a key the TA payload **never contains** — the correct key is `confidence`. The aggregator's own metadata builder at `:478-480` documents this exact mapping.

Dormant: the enhanced path needs `enable_ml_predictions` (default False) *and* `enable_multi_timeframe` (default False). Verifiable only by unit test.

**Files:** `app/aggregation/enhanced_aggregator.py:312`, `:314`; test `tests/test_mtf_leg_scoring.py` (**NEW** — `tests/test_multi_timeframe.py` is wholesale-skipped)

- [ ] **Step 1: Write the failing test**

```python
"""
The Phase-3 MTF leg must contribute a non-zero score.

Two defects, fixed together because either alone leaves the leg at zero:
the 0-1 alignment_score was compared against a 50.0 threshold (so the early
return always fired), and signal_strength was read from a key the TA payload
never contains - the correct key is confidence, as the aggregator's own
metadata builder documents at :478-480.

DORMANT: the enhanced path needs both enable_ml_predictions and
enable_multi_timeframe, which default False. Unit test is the only proof.
"""

import pytest

from app.aggregation.enhanced_aggregator import EnhancedAggregator
from app.models import SignalAction


@pytest.fixture
def aggregator():
    return EnhancedAggregator(settings=None)


def test_aligned_buy_payload_scores_positive(aggregator):
    """A real TA payload: alignment 2/3, confidence 0.8."""
    payload = {"overall_signal": "BUY", "confidence": 0.8, "alignment_score": 0.667}

    score = aggregator._calculate_mtf_score(payload, SignalAction.BUY)

    assert score == pytest.approx(0.8 * 1.2), (
        f"MTF scored {score}; expected confidence x the 20% alignment bonus"
    )


def test_sell_payload_scores_negative(aggregator):
    payload = {"overall_signal": "SELL", "confidence": 0.9, "alignment_score": 0.75}

    score = aggregator._calculate_mtf_score(payload, SignalAction.SELL)

    assert score == pytest.approx(-0.9 * 1.2)


def test_low_alignment_still_returns_zero(aggregator):
    """The threshold must keep working after the scale fix - 1/3 is below 50%."""
    payload = {"overall_signal": "BUY", "confidence": 0.8, "alignment_score": 0.333}

    assert aggregator._calculate_mtf_score(payload, SignalAction.BUY) == 0.0
```

- [ ] **Step 2: Run and watch it fail (score is 0.0), then fix both lines**

Replace line 312:

```python
        alignment_score = mtf_analysis.get("alignment_score", 0.0)
```

with:

```python
        # The TA payload reports alignment as a 0-1 fraction while the
        # threshold below is a percentage. Same normalization the metadata
        # builder already applies at :469-471.
        raw_alignment = mtf_analysis.get("alignment_score", 0.0)
        alignment_score = raw_alignment * 100 if raw_alignment <= 1 else raw_alignment
```

and line 314:

```python
        # The TA payload has no "signal_strength" key; confidence is the
        # equivalent 0-1 figure. See the mapping at _build_enhanced_signal:478.
        signal_strength = mtf_analysis.get("confidence", 0.0)
```

Do **not** change the `50.0` threshold to `0.5` — that would leave the percent-formatted debug log and the `mtf_min_alignment_score` config convention (documented 0–100) wrong.

- [ ] **Step 3: Verify and commit**

```bash
cd services/trading-engine && python3 -m pytest tests/test_mtf_leg_scoring.py --no-cov -q
```

```bash
git commit -m "fix(trading-engine): MTF leg scores instead of returning a hard zero

Two defects, fixed together because either alone leaves the leg at zero. The
alignment gate compared the TA payload's 0-1 alignment_score against a 50.0
threshold, so the early return fired on every possible input; and
signal_strength was read from a key the payload never contains - the correct
key is confidence, as the aggregator's own metadata builder documents.

The 2025-12-01 'correctly map MTF API response fields' fix patched the
metadata builder and never reached the scoring path.

DORMANT: the enhanced path needs both enable_ml_predictions and
enable_multi_timeframe, which default False. Proven by unit test, not by the
live stack. New test file because tests/test_multi_timeframe.py is
wholesale-skipped." -- app/aggregation/enhanced_aggregator.py tests/test_mtf_leg_scoring.py
```

---

## Task 12: Delete the volume-profile pipeline (DORMANT)

Delete rather than repair. Evidence: `enable_volume_profile` defaults False, `get_auto_trader()` never passes it, and no Settings field or env var can flip it — the only way to run VP is editing source. Forced on, it is broken independently at two layers (wrong host, wrong envelope key, wrong element shape; plus `Decimal` used without an import), each collapsing to a silent pass-through. **No pytest test asserts on it** (`pytest.ini` sets `testpaths = tests`), but three files still reference it and are handled below: one collected unit test sets the flag, and two service-root smoke scripts call the producer being deleted. Every consumer already reads `.get("volume_profile", {})`, so removal is a behavioral no-op. Repairing it would activate a latent `TypeError` at `auto_trader.py:4139`, because the producer writes `take_profit` as a dict of levels.

**Files:** delete `app/signal_aggregator.py:1145-1315`; delete `app/auto_trader.py:1168-1177` and the `enable_volume_profile` parameter, its docstring line, `self.enable_vp`, and the two log mentions; delete the now-dead `trader.enable_vp = False` at `tests/unit/test_auto_trader.py:347`; delete the two service-root smoke scripts `test_volume_profile.py` and `test_complete_system.py` and their `verify_system.py:113-114` entries; test `tests/test_vp_pipeline_removed.py` (**NEW**)

- [ ] **Step 1: Write the reachability test first**

```python
"""
The VP pipeline is gone.

Unreachable by any flag or env (enable_volume_profile defaults False and
get_auto_trader never passes it), broken at two independent layers when
forced on, no pytest test asserts on it, and every consumer already reads
.get(..., {}) - so removal is a behavioral no-op. Production behavior was
ALREADY 'VP absent'.
"""

from app.signal_aggregator import SignalAggregator


def test_vp_producer_is_gone():
    assert not hasattr(SignalAggregator, "get_trading_signal_with_vp")
    assert not hasattr(SignalAggregator, "_fetch_candles_for_vp")


def test_auto_trader_has_no_vp_flag():
    import inspect

    from app.auto_trader import AutoTrader

    signature = inspect.signature(AutoTrader.__init__)
    assert "enable_volume_profile" not in signature.parameters
```

- [ ] **Step 2: Run, watch it fail, then delete**

- `app/signal_aggregator.py`: remove lines 1145–1315 — `get_trading_signal_with_vp` and `_fetch_candles_for_vp`, a contiguous block with nothing between them.
- `app/auto_trader.py`: remove the `elif self.enable_vp:` branch at 1168–1177 (a flag-True case that already fell through to the Phase-2 MTF path in practice), the `enable_volume_profile` parameter at `:188`, its docstring line at `:204`, `self.enable_vp = enable_volume_profile` at `:227`, the two log mentions at `:653` and `:831`, and the `if self.enable_vp and vp_data:` head of the log chain at `:1205-1218` — keeping the `elif`/`else` logging branches.
- **Leave** the defensive metadata readers at `:1201`, `:3959-3965`, `:4126-4140`. They no-op; ripping them out touches money-path code for zero behavior change.
- `app/volume_profile.py` and `app/vp_strategy.py` become import-orphans. Delete them in the same commit and drop their two lines from `verify_system.py:88-89`, or leave them and say so — do not leave `verify_system.py` referencing deleted files.
- `tests/unit/test_auto_trader.py:347` sets `trader.enable_vp = False` inside `test_check_and_trade_signal_doesnt_meet_requirements`. `AutoTrader` has no `__slots__`, so the assignment will not raise after the flag is removed — the test stays green while the line becomes a reference to a flag that no longer exists. Delete that one line in this commit.
- Two **service-root smoke scripts** call the producer being deleted and are broken by this change: `test_volume_profile.py:59` and `test_complete_system.py:122` both `await aggregator.get_trading_signal_with_vp(...)`. Delete both files, and drop their two entries from `verify_system.py:113-114` (`"Volume Profile Test"`, `"Complete System Test"`) — otherwise `verify_system.py` keeps reporting `Test Scripts: 5/5` for two scripts that now raise `AttributeError`. Both are unmaintained manual smoke scripts needing the full live stack; `test_complete_system.py:40` additionally hardcodes `balance = Decimal("10000")`, a CLAUDE.md §1 defect on its own. They are **not** collected by pytest (`pytest.ini` sets `testpaths = tests`), so the suite count does not move.
  - If `test_complete_system.py` must be preserved instead of deleted, the minimal correct edit is a **rebind**, not a range deletion: replace `:122-128` with `signal_vp = signal_mtf`. `vp_data` then resolves to `{}`, `conf_change` to `0.0`, `stop_loss_pct` stays `None`, and the downstream uses at `:175`, `:200`, `:212`, `:222`, `:232`, `:288`, `:330` all survive. Do **not** delete `:122-155`: `signal_vp` is a position-sizing argument, not just a logging value, and the VP reporting chain ends at `:166`, not `:155`.
  - Archived references under `docs/archive/**` (`VP_INTEGRATION_GUIDE.md`, `PROJECT_STATUS_VERIFIED.md`, `TEST_INFRASTRUCTURE_ANALYSIS_REPORT.md`) are out of scope — do not add them to the pathspec.

- [ ] **Step 3: Verify and commit**

```bash
cd services/trading-engine && python3 -m pytest tests/test_vp_pipeline_removed.py tests/unit/test_auto_trader.py tests/test_exposure_gate_all_paths.py --no-cov -q
```

```bash
git commit -m "refactor(trading-engine): delete the unreachable volume-profile pipeline

enable_volume_profile defaults False, get_auto_trader never passes it, and no
Settings field or env var can flip it - the only way to run VP was editing
source. Forced on it was broken at two independent layers: the candle fetch
called a route the TA service does not serve, parsed the wrong envelope key,
and indexed dicts as positional lists; and Decimal was used with no import.
Each failure collapsed to a silent pass-through, so VP never emitted one
production data point.

No pytest test asserted on it, and every consumer already reads
.get('volume_profile', {}) - production behavior was already 'VP absent', so
this changes nothing at runtime. Repair would also have activated a latent
TypeError at auto_trader.py:4139: the producer writes take_profit as a dict
of levels while the notify path calls float() on it.

Also removes the three now-dead references the deletion would otherwise
strand: trader.enable_vp = False in tests/unit/test_auto_trader.py, and the
two service-root smoke scripts test_volume_profile.py and
test_complete_system.py, which called the deleted producer and which
verify_system.py advertised as passing test scripts.

Defensive metadata readers are deliberately left in place." -- app/signal_aggregator.py app/auto_trader.py app/volume_profile.py app/vp_strategy.py verify_system.py test_volume_profile.py test_complete_system.py tests/unit/test_auto_trader.py tests/test_vp_pipeline_removed.py
```

---

## Task 13: Remove price-domain rounding from the dormant strategy layer (DORMANT)

Four files, **27** price-domain rounding calls (the per-file enumeration below is authoritative and sums to 27: 5 + 9 + 7 + 6). None has a runtime caller in `app/` — they are exported and exercised by tests only. The fix is parity with the shipped PRICE-01 precedent and a precondition for extending the AST guard.

**Do not blanket-strip every `round()`.** These are non-price and must stay: RSI (0–100), volume ratios, position-size fractions, strength scores, average volumes.

**Files:**
- `app/strategies/momentum_breakout_strategy.py` — price sites at `:1064` (×2), `:1106`, `:1120`, `:1130`. **Keep** `:581` (volume ratio), `:1190` (position fraction).
- `app/strategies/trend_following_strategy.py` — price sites at `:1118`, `:1126`, `:1134`, `:1143`, `:1151`, `:1159`, `:1166` (×2), `:1209`. **Keep** `:635`, `:1210`, `:1262`.
- `app/strategies/support_resistance_strategy.py` — price sites at `:352` (EMA), `:380` (ATR), `:625` (×2), `:663`, `:677`, `:687`. **Keep** `:335` (RSI), `:402` (volume ratio), `:757` (position fraction). Also harden the vacuous guard at `:653`.
- `app/utils/support_resistance_detector.py` — price sites at `:630`, `:636`, `:637`, `:731`, `:737`, `:738`. **Keep** `:631`, `:638`, `:732`, `:739`.
- Test: `tests/strategies/test_dormant_strategy_precision.py` (**NEW**)

**The zero-ATR failure is silent, not a crash.** `round(np.float64, 2)` preserves the numpy type, and numpy scalar division by `np.float64(0.0)` yields `inf` with a RuntimeWarning. The observable failure is `atr_multiple=inf` with TP1/TP2 pinned exactly at entry — an instant fee-burning exit. **Do not write a test expecting `ZeroDivisionError`.**

- [ ] **Step 1: Write the failing test**

Use ADA-scale fixtures (`entry ≈ 0.3512`, `atr ≈ 0.004`). Copy the assertion shapes from `tests/strategies/test_research_optimized_partial_exits.py` — the companion test of the already-shipped fix. Cover:

- **Distinct rungs:** `len({lv.price for lv in levels}) == len(levels)` at ADA scale, for the momentum and trend ladders and the SR ladder. Momentum skips its ladder entirely when `abs(total_distance) < atr * 2`, so the fixture's `final_target` must be at least `entry + 2*ATR` or the test passes **vacuously**.
- **Geometry:** momentum's `PartialExitLevel` carries `atr_multiple` (assert `distance / atr == pytest.approx(level.atr_multiple)`); trend's carries `fib_level` instead, so assert against `swing_range * (FIB_N - 1)`.
- **Stop distance survives:** `abs(entry - stop) / entry == pytest.approx(0.01)` for the SR strategy's 1%-clamped stop — currently ≈0.0034.
- **Zero-ATR degeneracy:** with a flat ADA window, assert TP1 is **not** equal to entry and no `atr_multiple` is `inf`.
- **Detector zones stay open:** with an ADA-scaled fixture, `level.zone_low < level.zone_high` — the existing detector invariant at `test_support_resistance_detector.py:510`, which passes today only because its fixtures use $95–105 prices.

Import the right class: `app/strategies/trend_following.py` defines a **different** `TrendFollowingStrategy`. Use `from app.strategies.trend_following_strategy import TrendFollowingStrategy`.

- [ ] **Step 2: Run and watch it fail, then remove the rounding**

Replace each price-domain `round(x, 2)` with the bare value (or `float(x)` where the source may be `np.float64` — the EMA, ATR, and detector cluster values). Copy the three-line comment from the shipped precedent at `research_optimized_strategy.py:722-724` onto at least the first site in each file.

Additionally, in `support_resistance_strategy.py`, harden the vacuous guard at `:653`:

```python
        if atr <= 0 or abs(total_distance) < atr * 1.5:
            return partial_exits
```

Both detector blocks (support at `:630` and resistance at `:731`) must change in the **same** commit — fixing only one leaves LONG take-profits corrupted through `find_next_resistance`.

- [ ] **Step 3: Verify and commit**

```bash
cd services/trading-engine && python3 -m pytest tests/strategies/ tests/unit/test_support_resistance_detector.py tests/test_capital_defaults_phase1.py --no-cov -q
```

`test_capital_defaults_phase1.py:232-234` asserts these strategies keep `capital` as a required no-default parameter — it must stay green, so change no signatures.

```bash
git commit -m "fix(trading-engine): drop price-domain rounding from the strategy layer

27 sites rounded prices, stops, take-profit ladders, EMAs, ATRs and S/R zone
bounds to 2dp. At ADA scale that collapses adjacent ladder rungs onto one
trigger (the exact PRICE-01 failure already fixed in
research_optimized_strategy.py) and, because the rounded stop feeds
_calculate_position_size, it corrupts risk-based sizing too: a stop rounded
onto entry drives risk_per_unit toward zero.

The zero-ATR path is silent, not a crash: round(np.float64, 2) preserves the
numpy type and division yields inf with a warning, so TP1/TP2 land exactly at
entry with atr_multiple=inf. The vacuous 'skip if target too close' guard is
hardened to catch atr <= 0.

Non-price rounds (RSI, volume ratios, position fractions, strength scores)
are deliberately untouched.

DORMANT: none of these four files has a runtime caller in app/. This is
parity with the shipped fix and the precondition for the AST guard." -- app/strategies/momentum_breakout_strategy.py app/strategies/trend_following_strategy.py app/strategies/support_resistance_strategy.py app/utils/support_resistance_detector.py tests/strategies/test_dormant_strategy_precision.py
```

---

## Task 14: Extend the AST price-rounding guard to the engine files

Plan A created `tests/test_price_rounding_invariant.py` with a bounded `SCANNED_FILES` tuple **and** the line-level `ALLOW_MARKER` opt-out. Now that Task 13 has cleaned the engine's strategy layer, add those four files and mark their legitimate non-price sites. This task **extends** the guard — it does not build any part of it.

**Files:** `tests/test_price_rounding_invariant.py` (repo root); the four Task 13 engine files (annotations only)

- [ ] **Step 1: Append the cleaned files, and re-point the tracking comment**

```python
SCANNED_FILES: tuple[str, ...] = (
    "services/technical-analysis/app/strategies/squeeze_momentum_strategy.py",
    "services/technical-analysis/app/indicators/sqzmom_enhanced.py",
    # WS1-B: dormant strategy layer, cleaned 2026-08-17
    "services/trading-engine/app/strategies/momentum_breakout_strategy.py",
    "services/trading-engine/app/strategies/trend_following_strategy.py",
    "services/trading-engine/app/strategies/support_resistance_strategy.py",
    "services/trading-engine/app/utils/support_resistance_detector.py",
)
```

Directly below that tuple sits the `# Not yet covered, tracked deliberately:` block WS1-A wrote. Its last line becomes false the moment this tuple lands. Replace

```python
#   trading-engine strategy + detector files           (added by WS1-B)
```

with the one engine file that is genuinely still uncovered:

```python
#   services/trading-engine/app/strategies/simple_rsi_strategy.py (2 price sites at 4dp, :121-122)
```

Do **not** delete the line outright, and do **not** add `simple_rsi_strategy.py` to `SCANNED_FILES`. Task 13 does not clean it (its file list is momentum_breakout / trend_following / support_resistance / support_resistance_detector only), and `:121-122` really do round price-domain values — `stop_loss=round(stop_loss, 4)`, `take_profit=round(take_profit, 4)`, both derived from `current_price ± stop_distance` at `:105-111`. Adding it would land the guard red, which is exactly what the guard's own module docstring forbids.

- [ ] **Step 2: Run it — and expect it to be RED**

```bash
python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q
```

The guard bans `round(x, 2)` and `round(x, 4)` **anywhere** in a scanned file, but these four files legitimately keep non-price 2dp rounds (RSI 0–100, volume ratios, strength scores) and 4dp position fractions. So `test_no_price_rounding_in_scanned_files` fails. Resolve it deliberately — do **not** delete files from the tuple, and do **not** re-implement the opt-out.

First confirm the mechanism is already there:

```bash
grep -n 'ALLOW_MARKER' tests/test_price_rounding_invariant.py
```

You must see `ALLOW_MARKER = "# non-price-round"` and its use inside `find_violations`. **If it is absent, WS1-A Task 6 has not landed — stop and coordinate; do not re-add the marker here.** Two independent definitions of the same opt-out is how a guard ends up with two behaviours.

Then annotate each legitimate site in the **four engine files** (the two technical-analysis files are WS1-A's to annotate, and Task 6 does it there), e.g.:

```python
        return round(current_volume / avg_volume, 2)  # non-price-round
```

The sites to mark are exactly Task 13's twelve-line "**Keep**" list: `momentum_breakout_strategy.py` `:581`, `:1190`; `trend_following_strategy.py` `:635`, `:1210`, `:1262`; `support_resistance_strategy.py` `:335`, `:402`, `:757`; `support_resistance_detector.py` `:631`, `:638`, `:732`, `:739`. Task 13's edits shift lines, so locate them by expression, not by number.

**Do not touch `POSITIVE_FIXTURE` and do not change `test_positive_cases_do_trip`'s `assert len(violations) == 4`.** The marker's own fixture coverage — `MARKER_LEAK_FIXTURE` and `test_marker_does_not_leak_to_other_lines`, which proves the opt-out is line-scoped and does not shield the next line — ships with the marker in WS1-A Task 6. Appending a fifth positive case here would turn that pre-existing count assertion red and prove nothing the existing `entry = round(entry_price, 2)` case does not already prove.

- [ ] **Step 3: Verify the guard is green and has teeth**

```bash
python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q
```

Expected: all pass, **including** `test_marker_does_not_leak_to_other_lines` — if that test is missing from the file, say so in the task report rather than adding it here. Then reintroduce one price rounding (e.g. `price=round(tp1_price, 2)` in `momentum_breakout_strategy.py`) **without** the marker and confirm the guard names that exact file and line. Restore.

- [ ] **Step 4: Commit**

```bash
git commit -m "test(price): extend the rounding guard to the trading-engine strategy layer

Adds the four files cleaned in the previous commit to SCANNED_FILES.

Those files legitimately keep non-price rounding (RSI 0-100, volume ratios,
position-size fractions), so each such site carries the guard's line-level
'# non-price-round' opt-out, introduced with the guard itself in WS1-A.
Marking a site at the point of use is deliberate: it keeps the decision
reviewable in the diff instead of silently shrinking the guard's scope, which
is how these guards get hollowed out." -- tests/test_price_rounding_invariant.py services/trading-engine/app/strategies/momentum_breakout_strategy.py services/trading-engine/app/strategies/trend_following_strategy.py services/trading-engine/app/strategies/support_resistance_strategy.py services/trading-engine/app/utils/support_resistance_detector.py
```

---

# Part 5 — In-service backtester (Task 15)

Task 15 is last because it is independent of Tasks 1–14, **not** because it is dormant. It does not belong under Part 4: the code it repairs is reachable over HTTP.

## Task 15: In-service backtester fills stops at the stop price (LIVE — non-money-path route)

`backtest_engine._close_position` prices **every** exit off `bar.close`, including stop-loss and take-profit exits that were triggered *intrabar*. `_check_exit_conditions` fires a stop when `bar.low <= stop_loss` (long) or `bar.high >= stop_loss` (short), then hands the bar to `_close_position`, which books the fill at that bar's close. On a bar that pierces the stop and then runs on, the backtester reports an exit far past the stop — flattering a losing trade or penalising a winning one, and in either direction reporting a fill the strategy never asked for.

**LIVE, non-money-path route:** this engine places no orders, but it is HTTP-reachable — `POST /api/v1/backtest/run` (`app/main.py:1239`), `GET /api/v1/backtest/quick/{strategy}` (`:1256`), `GET /api/v1/backtest/compare` (`:1275`), all routing through `app/handlers/backtest.py`, which constructs `BacktestEngine` at `:276`, `:403`, `:483`, `:698`. Operators call these and read the numbers. Do not label this task DORMANT.

**Three conventions this task pins — write them exactly, or two engineers write two different backtesters:**

1. **Stops are market orders on trigger.** The fill reference is the stop level, **clamped to the bar open** so a gap-through can never fabricate a price the market did not trade: long `min(stop_loss, bar.open)`, short `max(stop_loss, bar.open)`. Adverse slippage then applies on top of the clamped reference. Without the clamp, a long stop at 100 on a bar that opens at 92 and closes at 91 would book 100 — *more* optimistic than the `bar.close` this task exists to remove, i.e. the fix would introduce a fresh optimism bug of its own.
2. **Take-profits are resting limits.** They fill at exactly `take_profit`, with **no** slippage and **no** gap-favourable bonus. A limit fills at its price or better; booking exactly its price means the backtester can never flatter a gap.
3. **The reference is computed at the trigger site, not inside `_close_position`.** `_check_exit_conditions` has already proven the level is non-`None` by comparing against it, so passing the price down eliminates by construction the hazard that `_process_signal` (`:364`, `:368`) forwards an arbitrary `exit_reason` from `signal.metadata` — a strategy emitting the literal string `"stop_loss"` with `stop_loss=None` cannot reach the new pricing, because the new pricing is keyed on the explicit `fill_price` / `apply_slippage` arguments and never on the reason string. Do **not** add an `if exit_reason == "stop_loss"` branch inside `_close_position`; a reviewer flagging the absent `None`-guard should be pointed at this paragraph.

`self._position.stop_loss` **is** the correct field for trailing exits: `_update_trailing_stop` writes the trailing level straight into `stop_loss` at `:533` and `:541`, so trailing exits are already covered by the `"stop_loss"` branch and need no separate handling.

Signal exits (`:364`, `:368`) and the `backtest_end` exit (`:314`) keep `bar.close` — they pass no `fill_price`, so the default carries them unchanged. That is the scope guard for this task.

**Files:**
- Modify: `app/backtesting/backtest_engine.py:422-433` (`_close_position` signature + exit-price block), `:465` (`Trade.slippage`), `:495-519` (the four `_check_exit_conditions` trigger sites — the block opens at `:495` with `if self._position.side == "long":`)
- Test: `tests/test_backtest_engine_stop_fills.py` (**NEW**)

**Interfaces:**
- Consumes: nothing new. `OHLCV.open` is already on the bar (`app/backtesting/strategy_base.py:66-72`).
- Produces: `_close_position(bar, exit_reason, fill_price: Optional[float] = None, apply_slippage: bool = True) -> None` — both new parameters are optional and default to today's behaviour, so `:314`, `:364` and `:368` are untouched. `apply_slippage=False` exists so the take-profit convention is expressed as an argument rather than as a branch on `exit_reason` (see convention 3).

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest_engine_stop_fills.py`:

```python
"""
Stop and take-profit exits must fill at the trigger level, not at bar.close.

_close_position priced EVERY exit off bar.close, including stops and TPs that
_check_exit_conditions had already triggered intrabar (bar.low <= stop_loss for
a long, bar.high >= stop_loss for a short). A bar that pierces the stop and
then runs on reported an exit far past the stop.

Conventions pinned here, and asserted:
  - stop  -> reference = stop level, clamped to bar.open (a gap-through fills
             at the open; the market never traded the stop price after it),
             then adverse slippage on top.
  - TP    -> fills at exactly take_profit. A resting limit fills at its price
             or better; booking exactly its price means a gap can never
             flatter the result. No slippage, no gap bonus.
  - signal / backtest_end exits -> unchanged, still bar.close +/- slippage.

Entry prices are read back off the recorded trade rather than recomputed: the
entry leg still fills off its own bar's close plus slippage, and this task does
not touch that.

Run: cd services/trading-engine && python3 -m pytest \\
     tests/test_backtest_engine_stop_fills.py --no-cov
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytest

from app.backtesting.backtest_engine import BacktestConfig, BacktestEngine
from app.backtesting.strategy_base import OHLCV, Signal, SignalType, StrategyBase

# 0.1% per side, large enough that "stop minus slippage" and "close minus
# slippage" cannot be confused with each other at these price scales.
SLIPPAGE_PCT = 0.1


class _StopScriptedStrategy(StrategyBase):
    """Emits one entry signal carrying explicit stop/TP levels, then nothing.

    tests/test_backtest_engine_cash_ledger.py's ScriptedStrategy attaches no
    stops, so it cannot exercise this path - hence a local strategy here.
    """

    def __init__(
        self,
        symbol: str,
        entry_bar: int,
        signal_type: SignalType,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        exits: Optional[Dict[int, SignalType]] = None,
    ):
        super().__init__(symbol)
        self._entry_bar = entry_bar
        self._signal_type = signal_type
        self._stop_loss = stop_loss
        self._take_profit = take_profit
        self._exits = exits or {}
        self._bar_index = -1

    def get_name(self) -> str:
        return "StopScriptedStrategy"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        self._bar_index += 1
        if self._bar_index == self._entry_bar:
            return Signal(
                signal_type=self._signal_type,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                stop_loss=self._stop_loss,
                take_profit=self._take_profit,
                position_size_pct=100.0,
            )
        exit_type = self._exits.get(self._bar_index)
        if exit_type is not None:
            return Signal(
                signal_type=exit_type,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                position_size_pct=100.0,
            )
        return None


def _ohlc(bars: List[tuple]) -> List[OHLCV]:
    """Explicit (open, high, low, close) bars - intrabar range is the point."""
    start = datetime(2026, 1, 1)
    return [
        OHLCV(
            timestamp=start + timedelta(hours=i),
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=1000.0,
        )
        for i, (o, h, lo, c) in enumerate(bars)
    ]


@pytest.fixture
def config() -> BacktestConfig:
    """initial_equity omitted: BacktestConfig resolves it from Settings."""
    return BacktestConfig(slippage_pct=SLIPPAGE_PCT, position_size_pct=10.0)


def _slippage(reference: float, config: BacktestConfig) -> float:
    return reference * (config.slippage_pct / 100)


def test_long_stop_fills_at_the_stop_not_the_close(config):
    """Bar 1 pierces the stop at 95 and closes at 80: the exit is not 80."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=95.0, take_profit=200.0
    )

    # Bar 1 opens above the stop, so no gap: the reference is the stop itself.
    engine.run(strategy, _ohlc([(100, 100, 100, 100), (99, 99, 78, 80)]))

    assert len(engine._trades) == 1
    trade = engine._trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(95.0 - _slippage(95.0, config)), (
        f"exit booked at {trade.exit_price}; the stop was 95 and the bar closed "
        "at 80 - pricing an intrabar stop off bar.close reports a fill the "
        "strategy never asked for"
    )


def test_long_stop_gaps_through_and_fills_at_the_open(config):
    """Opening below the stop must fill at the OPEN, never at the stop.

    Filling at 95 here would fabricate a price the market did not trade after
    the open - an optimism bug in the opposite direction.
    """
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=95.0, take_profit=200.0
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (90, 91, 85, 88)]))

    trade = engine._trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(90.0 - _slippage(90.0, config))
    assert trade.exit_price < 95.0


def test_short_stop_clamps_to_the_open_on_a_gap_up(config):
    """Mirror case: a short's stop is above, so the clamp takes the MAX."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.SELL, stop_loss=105.0, take_profit=50.0
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (110, 115, 109, 112)]))

    trade = engine._trades[0]
    assert trade.side == "short"
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(110.0 + _slippage(110.0, config))
    assert trade.exit_price > 105.0


def test_take_profit_fills_exactly_at_the_limit(config):
    """A resting limit fills at its price - no slippage, no gap bonus."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=50.0, take_profit=110.0
    )

    # Bar 1 gaps open to 115 and runs to 130: the fill is the limit, not 115
    # and not the close.
    engine.run(strategy, _ohlc([(100, 100, 100, 100), (115, 130, 114, 128)]))

    trade = engine._trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(110.0), (
        f"take-profit booked at {trade.exit_price}; a resting limit fills at "
        "its own price, and honouring the gap would flatter the backtest"
    )


def test_signal_exit_still_prices_off_bar_close(config):
    """Scope guard: only stop/TP exits change."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT",
        0,
        SignalType.BUY,
        stop_loss=None,
        take_profit=None,
        exits={2: SignalType.CLOSE_LONG},
    )

    engine.run(
        strategy, _ohlc([(100, 100, 100, 100), (105, 106, 104, 105), (110, 112, 108, 111)])
    )

    trade = engine._trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_price == pytest.approx(111.0 - _slippage(111.0, config))


def test_backtest_end_exit_still_prices_off_bar_close(config):
    """Scope guard: the final forced close is unchanged."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=None, take_profit=None
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (105, 106, 104, 105)]))

    trade = engine._trades[0]
    assert trade.exit_reason == "backtest_end"
    assert trade.exit_price == pytest.approx(105.0 - _slippage(105.0, config))


def test_recorded_slippage_matches_the_exit_reference(config):
    """Trade.slippage must not keep quoting a bar.close-derived figure."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=95.0, take_profit=200.0
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (99, 99, 78, 80)]))

    trade = engine._trades[0]
    # Entry leg off the RECORDED entry price (bar-0 close plus its own
    # slippage), not off the raw 100 - recomputing it here would be off by the
    # entry slippage itself.
    entry_slippage = _slippage(trade.entry_price, config)
    exit_slippage = _slippage(95.0, config)  # stop reference, not the 80 close
    assert trade.slippage == pytest.approx(entry_slippage + exit_slippage), (
        f"recorded slippage {trade.slippage} still assumes both legs were "
        "priced off the same bar close"
    )
```

- [ ] **Step 2: Run it and watch the stop/TP tests fail**

```bash
cd services/trading-engine && python3 -m pytest tests/test_backtest_engine_stop_fills.py --no-cov -q
```

Expected red: `test_long_stop_fills_at_the_stop_not_the_close` (books `80 - slippage`), `test_long_stop_gaps_through_and_fills_at_the_open` (books `88 - slippage`), `test_short_stop_clamps_to_the_open_on_a_gap_up` (books `112 + slippage`), `test_take_profit_fills_exactly_at_the_limit` (books `128 - slippage`), `test_recorded_slippage_matches_the_exit_reference`. Expected green already: the two scope-guard tests — they pin behaviour that must **not** move.

- [ ] **Step 3: Take an optional fill reference on `_close_position`**

In `app/backtesting/backtest_engine.py`, replace lines 422–433:

```python
    def _close_position(self, bar: OHLCV, exit_reason: str) -> None:
        """Close existing position"""
        if not self._position:
            return

        # Apply slippage to exit price
        slippage_amount = bar.close * (self.config.slippage_pct / 100)
        if self._position.side == "long":
            exit_price = bar.close - slippage_amount
        else:
            exit_price = bar.close + slippage_amount
```

with:

```python
    def _close_position(
        self,
        bar: OHLCV,
        exit_reason: str,
        fill_price: Optional[float] = None,
        apply_slippage: bool = True,
    ) -> None:
        """Close existing position.

        fill_price is the reference the exit actually fills against, supplied
        by the caller that knows why the exit fired:

          - stop exits pass the stop level already clamped to bar.open (a
            gap-through cannot fill at a price the market never traded) and
            leave apply_slippage True: a stop is a market order once
            triggered, so adverse slippage is applied here on top;
          - take-profit exits pass the limit level with apply_slippage=False:
            a resting limit fills at its own price or better, so booking
            exactly its price is the convention that cannot flatter a gap;
          - signal and backtest_end exits pass neither and keep bar.close.

        Deliberately keyed on these arguments and NOT on exit_reason:
        _process_signal forwards an arbitrary reason string out of
        signal.metadata, so a strategy emitting the literal "stop_loss" with
        no stop set must not be able to reach a stop-priced branch.
        """
        if not self._position:
            return

        # Apply slippage to exit price. Stops and TPs hand us their own
        # reference; everything else still fills at the bar close.
        reference = bar.close if fill_price is None else fill_price
        slippage_amount = (
            reference * (self.config.slippage_pct / 100) if apply_slippage else 0.0
        )
        if self._position.side == "long":
            exit_price = reference - slippage_amount
        else:
            exit_price = reference + slippage_amount
```

`Optional` is already imported at `backtest_engine.py:8`.

- [ ] **Step 4: Fix the recorded slippage figure**

At line 465, `slippage=slippage_amount * 2` assumed both legs were priced off the same bar close. That is no longer true — and it was never exact anyway, since the entry leg was priced off *its* bar at `:386`. Replace:

```python
            slippage=slippage_amount * 2,
```

with:

```python
            # Exit-leg slippage is the real figure computed above (zero for a
            # take-profit limit). The entry leg is approximated at the same
            # rate off the entry price, because the entry bar is not retained
            # on the Position - it was previously approximated as this same
            # doubling off the EXIT bar's close, which was worse.
            slippage=slippage_amount
            + self._position.entry_price * (self.config.slippage_pct / 100),
```

Nothing aggregates this field into a reported metric — `performance_metrics.py` and `handlers/backtest.py` never read `Trade.slippage`; the only consumers are `Trade.to_dict` (`:115`) and `tests/test_backtesting.py:684-685`, which asserts only `sum(t.slippage) > 0`. That assertion holds under the new formula for any `slippage_pct > 0`, since the entry term alone is positive. Note that `test_backtest_engine_cash_ledger.py` runs with `slippage_pct = 0.0`, so it cannot distinguish the old `* 2` form from this one — the coverage for this line is `test_recorded_slippage_matches_the_exit_reference` in the new file, not the ledger suite.

- [ ] **Step 5: Pass the trigger reference from the four exit sites**

In `_check_exit_conditions`, replace lines 495–519 in full (verified: this exact block occurs once in the file):

```python
        if self._position.side == "long":
            # Check stop loss
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.low <= self._position.stop_loss:
                    self._close_position(bar, "stop_loss")
                    return

            # Check take profit
            if self.config.use_take_profit and self._position.take_profit:
                if bar.high >= self._position.take_profit:
                    self._close_position(bar, "take_profit")
                    return

        else:  # short position
            # Check stop loss
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.high >= self._position.stop_loss:
                    self._close_position(bar, "stop_loss")
                    return

            # Check take profit
            if self.config.use_take_profit and self._position.take_profit:
                if bar.low <= self._position.take_profit:
                    self._close_position(bar, "take_profit")
                    return
```

with:

```python
        # The fill reference is computed HERE, where the level has just been
        # proven non-None by the trigger comparison. Stops clamp to bar.open so
        # a gap-through fills at the open rather than at a price the market
        # never traded after it. Take-profits are resting limits and fill at
        # their own level.
        if self._position.side == "long":
            # Check stop loss
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.low <= self._position.stop_loss:
                    self._close_position(
                        bar,
                        "stop_loss",
                        fill_price=min(self._position.stop_loss, bar.open),
                    )
                    return

            # Check take profit
            if self.config.use_take_profit and self._position.take_profit:
                if bar.high >= self._position.take_profit:
                    self._close_position(
                        bar,
                        "take_profit",
                        fill_price=self._position.take_profit,
                        apply_slippage=False,
                    )
                    return

        else:  # short position
            # Check stop loss
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.high >= self._position.stop_loss:
                    self._close_position(
                        bar,
                        "stop_loss",
                        fill_price=max(self._position.stop_loss, bar.open),
                    )
                    return

            # Check take profit
            if self.config.use_take_profit and self._position.take_profit:
                if bar.low <= self._position.take_profit:
                    self._close_position(
                        bar,
                        "take_profit",
                        fill_price=self._position.take_profit,
                        apply_slippage=False,
                    )
                    return
```

Do **not** touch the `_close_position` calls at `:314` (`backtest_end`) or `:364` / `:368` (signal exits). They pass no `fill_price` and must keep filling at `bar.close`.

- [ ] **Step 6: Verify**

```bash
cd services/trading-engine && python3 -m pytest tests/test_backtest_engine_stop_fills.py tests/test_backtest_engine_cash_ledger.py tests/test_backtesting.py --no-cov -q
```

Expected: all pass. `test_backtest_engine_cash_ledger.py` is the real gate — its fixtures use flat bars (`high == low == close`) and no stops, so every one of its figures must be bit-for-bit unchanged. If any of it moves, a non-stop exit path was disturbed. The other one to watch is `test_backtesting.py::test_engine_slippage_applied`, which asserts `sum(t.slippage) > 0` at `slippage_pct=1.0` — satisfied by the new formula, since the entry term alone is positive.

- [ ] **Step 7: Commit**

```bash
git commit -m "fix(trading-engine): backtester fills stops at the stop, not the bar close

_close_position priced every exit off bar.close, including stop-loss and
take-profit exits that _check_exit_conditions had already triggered intrabar.
A bar that pierced the stop and then ran on reported an exit far past the
stop - flattering a losing trade or penalising a winning one, and either way
reporting a fill the strategy never asked for.

Exits now carry an explicit fill reference computed at the trigger site,
where the level has just been proven non-None:

  stop        stop level CLAMPED to bar.open (long min, short max), then
              adverse slippage - a stop is a market order once triggered, and
              the clamp stops a gap-through fabricating a price the market
              never traded after the open;
  take_profit exactly the limit level, no slippage and no gap bonus - a
              resting limit fills at its price or better, so booking its
              price is the convention that cannot flatter a gap;
  signal /
  backtest_end unchanged, still bar.close +/- slippage.

Keyed on the new optional fill_price / apply_slippage arguments and never on
exit_reason: _process_signal forwards an arbitrary reason string out of
signal.metadata, so a strategy emitting the literal \"stop_loss\" with no stop
set cannot reach a stop-priced branch. Trailing exits need no special case -
_update_trailing_stop writes the trailing level into stop_loss.

Trade.slippage no longer doubles a bar.close-derived figure; the exit leg is
the real number and the entry leg is approximated off the entry price.

Reachable over HTTP via /api/v1/backtest/run, /quick and /compare - this is a
reported-number correctness fix, not dormant hygiene." -- app/backtesting/backtest_engine.py tests/test_backtest_engine_stop_fills.py
```

---

## Plan B completion checklist

- [ ] Engine suite is **13 failed** — the same 11 `test_pairs_trading` and 2 `TestLiveTradingResponseEnvelope` as before this plan. Any other failure is a regression.
  ```bash
  cd services/trading-engine && python3 -m pytest tests/ --no-cov -q
  ```
- [ ] `python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q` passes from the repo root and has been *seen* to fail on a reintroduced rounding.
- [ ] Fifteen commits, one per task, each with an explicit pathspec; every diff checked for import churn.
- [ ] **Deployment proof — an HTTP 200 is not proof:**
  ```bash
  DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build trading-engine
  curl -sf http://localhost:8005/health && curl -sf http://localhost:8005/ready
  docker compose -f docker-compose.unified.yml logs --tail=200 trading-engine
  ```
  In the logs, confirm: the engine booted (the fenced LIVE path must not be reached in paper mode), signals are being generated with `SQZMOM_ENHANCED` among the legs, and — after a close — a funding line appears. Then prove persistence with a DB query rather than trusting the log:
  ```sql
  SELECT id, symbol, side, entry_price, exit_price, realized_pnl, closed_at
  FROM positions WHERE closed_at IS NOT NULL ORDER BY closed_at DESC LIMIT 5;
  ```
- [ ] **Task 15 is LIVE, so a green unit test is not its proof.** Hit the backtest route on the rebuilt container and read a stop exit back out of the response:
  ```bash
  curl -s -X POST http://localhost:8005/api/v1/backtest/run \
    -H 'Content-Type: application/json' \
    -d '{"strategy":"rsi_momentum","symbol":"BTCUSDT","days":30}' \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print([(t['exit_reason'], t['exit_price']) for t in r.get('trades', [])][:10])"
  ```
  Confirm at least one trade with `exit_reason == "stop_loss"` and that its `exit_price` sits at the stop level (or the bar open on a gap), not at that bar's close. If the run produces no stop exits, say so rather than claiming the proof.
- [ ] Confirm the service was actually restarted. Stale in-memory state is this repo's most common false pass.

## Out of scope, recorded so nobody re-derives it

- `Position.total_value` still uses the original `quantity` — same class as Task 1, not fixed here.
- `risk_manager.check_position_limits` ignores the incoming trade's notional (it checks only pre-existing exposure, unlike `_passes_exposure_gate` which adds `new_notional`), and when `account_balance <= 0` the exposure percentage is `0` so the gate **passes**. Both are pre-existing and deliberately untouched.
- After a fill, `partial_profit_taker`, `dca_manager`, the heat ledger, and the notification all still book `trade_setup.entry_price` rather than the real fill. The position manager already books the real fill internally.
- `get_performance_stats_from_tracker`'s exception fallback hands Kelly optimistic synthetic stats (W=0.5, R=2). Pre-existing, unchanged by Task 6.
- LIVE closes reach `close_position` with `close_commission=0`, so LIVE realized P&L nets entry fees only. Moot behind the Task 10 fence.
- `RESEARCH_WEIGHTS` / `get_research_weight` in `voter.py` are dead code with no callers outside that module, and they disagree with the live `metadata["weight"]` values for SQZMOM (1.5 vs 1.4), ICHIMOKU (0.9 vs 1.3), and RSI_DIVERGENCE (1.3 vs 1.2). Not touched.
- `tests/conftest.py` fixtures `portfolio_repository` and `test_portfolio` still hardcode `Decimal("10000.00")`. Known residual; do not copy, do not fix here.
