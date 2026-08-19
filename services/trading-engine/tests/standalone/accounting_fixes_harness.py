"""
Standalone verification harness for the 2026-07-28 accounting fixes.

Runs WITHOUT pytest/fastapi/sqlalchemy — plain asserts, stdlib + pydantic only
(the sandbox used to author these fixes has no package registry access).

Run:  python3 tests/standalone/accounting_fixes_harness.py
from the services/trading-engine directory.

NOT a pytest module — renamed off the test_*.py pattern on 2026-08-08. It
installs a stub into sys.modules["app.repositories"] at import time (below),
which pytest used to execute merely by COLLECTING the file, replacing the real
repository classes for every test collected afterwards; that poisoned all 21
tests in tests/unit/test_repositories.py. Collection found no tests here to
offset it either — every check runs through the plain-assert `check()` helper,
so `--collect-only` reported 0 items. Do not rename it back.

Covers:
  T1  LONG win round-trip credits margin + P&L - commissions
  T2  SHORT win round-trip credits margin + P&L - commissions (was inverted)
  T3  SHORT loss round-trip debits the loss (was credited)
  T4  reduce_only with no matching position is REJECTED (was opening a flip)
  T5  partial close credits proportional margin + P&L, position reduced
  T6  close after partial exits does not double-count realized P&L
  T7  scale-in (DCA) averages entry on the SAME position (no duplicates)
  T8  leveraged round trip nets exactly P&L - commissions
  T9  kill switch: no false daily-loss trigger on open (equity semantics),
      loss streak survives interleaved opens
  T10 risk manager daily P&L rolls over on UTC date change
  T11 position_id-targeted close closes THAT position
"""

import asyncio
import sys
import types
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Stub out DB-touching modules BEFORE importing app code (sqlalchemy absent).
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class _AsyncNoop:
    def __getattr__(self, name):
        async def _noop(*args, **kwargs):
            return None

        return _noop


repo_stub = types.ModuleType("app.repositories")
repo_stub.get_trade_repository = lambda: _AsyncNoop()
repo_stub.get_portfolio_repository = lambda: _AsyncNoop()
repo_stub.get_position_repository = lambda: _AsyncNoop()


class _FakeRepoClasses:
    pass


repo_stub.PositionRepository = _FakeRepoClasses
repo_stub.TradeRepository = _FakeRepoClasses
repo_stub.PortfolioRepository = _FakeRepoClasses
sys.modules["app.repositories"] = repo_stub

from app.models import OrderCreate, OrderSide, OrderType, OrderStatus, PositionSide  # noqa: E402
from app.paper_trading import PaperTradingEngine  # noqa: E402
import app.paper_trading as paper_mod  # noqa: E402
import app.position_manager as pm_mod  # noqa: E402
from app.position_manager import PositionManager  # noqa: E402
from app.risk_manager import RiskManager  # noqa: E402
from app.trading_enhancements.kill_switch import KillSwitch, KillSwitchConfig  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def fresh_engine(leverage=None):
    """Build an isolated engine + position manager pair."""
    pm_mod._position_manager = None
    paper_mod._paper_engine = None
    import app.risk_manager as rm_mod

    rm_mod._risk_manager = None if hasattr(rm_mod, "_risk_manager") else None
    engine = PaperTradingEngine()
    # PAPER-01 (2026-08-03): paper fills are adverse per-symbol by default.
    # This harness pins the 2026-07-28 *accounting* arithmetic (which side is
    # credited, margin vs notional, no double-counted realized P&L), not fill
    # realism, so it opts out of slippage explicitly -- the same escape hatch
    # an A/B run uses. Fill realism lives in tests/unit/test_paper_slippage.py.
    engine.slippage.enabled = False
    # Fresh position manager wired into the engine
    engine.position_manager = PositionManager()
    pm_mod._position_manager = engine.position_manager
    if leverage is not None:
        # Stage 0 (2026-08-07): paper_trading now gates its leverage read on
        # leverage_enabled, the way auto_trader always has. Without this the
        # assignment below is inert and every leg silently posts full notional.
        engine.settings.leverage_enabled = True
        engine.settings.default_leverage = leverage
    return engine


def D(x):
    return Decimal(str(x))


async def t1_long_win():
    print("T1: LONG win round-trip")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    comm = e.commission_pct
    o = OrderCreate(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=D(1)
    )
    order, err = await e.execute_market_order(o, D(100))
    check("open filled", err is None and order.status == OrderStatus.FILLED)
    c = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D(1),
        reduce_only=True,
    )
    order2, err2 = await e.execute_market_order(c, D(110))
    check("close filled", err2 is None and order2.status == OrderStatus.FILLED)
    expected = D(1000) + D(10) - (D(100) * comm) - (D(110) * comm)
    check(
        "balance = initial + pnl - commissions",
        abs(e.balance - expected) < D("1e-9"),
        f"(got {e.balance}, want {expected})",
    )
    pos = e.position_manager.get_closed_positions()[0]
    check("realized pnl == +10", pos.realized_pnl == D(10), f"(got {pos.realized_pnl})")


async def t2_short_win():
    print("T2: SHORT win round-trip (previously inverted)")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    comm = e.commission_pct
    o = OrderCreate(
        symbol="ETHUSDT", side=OrderSide.SELL, type=OrderType.MARKET, quantity=D(1)
    )
    await e.execute_market_order(o, D(100))
    c = OrderCreate(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=D(1),
        reduce_only=True,
    )
    await e.execute_market_order(c, D(90))
    expected = D(1000) + D(10) - (D(100) * comm) - (D(90) * comm)
    check(
        "winning short INCREASES balance",
        abs(e.balance - expected) < D("1e-9"),
        f"(got {e.balance}, want {expected})",
    )


async def t3_short_loss():
    print("T3: SHORT loss round-trip (previously credited)")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    comm = e.commission_pct
    o = OrderCreate(
        symbol="ETHUSDT", side=OrderSide.SELL, type=OrderType.MARKET, quantity=D(1)
    )
    await e.execute_market_order(o, D(100))
    c = OrderCreate(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=D(1),
        reduce_only=True,
    )
    await e.execute_market_order(c, D(110))
    expected = D(1000) - D(10) - (D(100) * comm) - (D(110) * comm)
    check(
        "losing short DECREASES balance",
        abs(e.balance - expected) < D("1e-9"),
        f"(got {e.balance}, want {expected})",
    )


async def t4_reduce_only_rejected():
    print("T4: reduce_only with no position is rejected (no flip)")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    c = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D(1),
        reduce_only=True,
    )
    order, err = await e.execute_market_order(c, D(50))
    check("order FAILED", order.status == OrderStatus.FAILED and err is not None)
    check("no position opened", len(e.position_manager.get_open_positions()) == 0)
    check("balance untouched", e.balance == D(1000))


async def t5_partial_close():
    print("T5: partial close credits proportional margin + P&L")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    comm = e.commission_pct
    o = OrderCreate(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=D(1)
    )
    _, _ = await e.execute_market_order(o, D(100))
    bal_after_open = e.balance
    pos = e.position_manager.get_open_positions()[0]
    c = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D("0.4"),
        reduce_only=True,
        position_id=pos.id,
    )
    order, err = await e.execute_market_order(c, D(110))
    check("partial fill ok", err is None and order.status == OrderStatus.FILLED)
    check(
        "remaining 0.6",
        pos.remaining_quantity == D("0.6"),
        f"(got {pos.remaining_quantity})",
    )
    check("still open", len(e.position_manager.get_open_positions()) == 1)
    expected = (
        bal_after_open + D("40") + D("4") - (D("44") * comm)
    )  # margin 40 + pnl 4 - comm
    check(
        "proportional credit",
        abs(e.balance - expected) < D("1e-9"),
        f"(got {e.balance}, want {expected})",
    )
    check(
        "partial realized recorded",
        pos.realized_pnl == D("4"),
        f"(got {pos.realized_pnl})",
    )


async def t6_no_double_count():
    print("T6: close after partial does not double count")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    o = OrderCreate(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=D(1)
    )
    await e.execute_market_order(o, D(100))
    pos = e.position_manager.get_open_positions()[0]
    c1 = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D("0.4"),
        reduce_only=True,
        position_id=pos.id,
    )
    await e.execute_market_order(c1, D(110))
    c2 = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D("0.6"),
        reduce_only=True,
        position_id=pos.id,
    )
    await e.execute_market_order(c2, D(120))
    # realized = 0.4*10 + 0.6*20 = 16 (NOT 10*1 + overwrite etc.)
    check(
        "realized accumulates correctly",
        pos.realized_pnl == D("16"),
        f"(got {pos.realized_pnl})",
    )
    check("position closed", len(e.position_manager.get_open_positions()) == 0)


async def t7_scale_in():
    print("T7: DCA scale-in averages the SAME position")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(1000)
    o = OrderCreate(
        symbol="ADAUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=D(10)
    )
    await e.execute_market_order(o, D(10))
    pos = e.position_manager.get_open_positions()[0]
    dca = OrderCreate(
        symbol="ADAUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=D(10),
        position_id=pos.id,
    )
    order, err = await e.execute_market_order(dca, D(8))
    check("scale-in filled", err is None and order.status == OrderStatus.FILLED)
    check(
        "ONE position (no duplicate)", len(e.position_manager.get_open_positions()) == 1
    )
    check("avg entry 9.0", pos.entry_price == D("9"), f"(got {pos.entry_price})")
    check("qty 20", pos.remaining_quantity == D(20), f"(got {pos.remaining_quantity})")


async def t8_leverage_roundtrip():
    print("T8: leveraged (10x) round trip nets pnl - commissions")
    e = fresh_engine(leverage=10)
    e.balance = e.initial_balance = D(1000)
    comm = e.commission_pct
    o = OrderCreate(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=D(1)
    )
    await e.execute_market_order(o, D(100))
    # margin 10 deducted, not 100
    check(
        "margin-only deduction",
        abs(e.balance - (D(1000) - D(10) - D(100) * comm)) < D("1e-9"),
        f"(got {e.balance})",
    )
    c = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D(1),
        reduce_only=True,
    )
    await e.execute_market_order(c, D(105))
    expected = D(1000) + D(5) - (D(100) * comm) - (D(105) * comm)
    check(
        "no phantom notional credit",
        abs(e.balance - expected) < D("1e-9"),
        f"(got {e.balance}, want {expected})",
    )


def t9_kill_switch():
    print("T9: kill switch equity semantics + streak accounting")
    ks = KillSwitch(KillSwitchConfig())
    ks.initialize_balance(100.0)
    # Open a position: equity unchanged (100), not cash-after-margin (90)
    trig = ks.update_metrics(current_balance=100.0, was_loss=False, position_value=10.0)
    check(
        "no false daily-loss trigger on open",
        "daily_loss_limit" not in trig,
        f"(got {trig})",
    )
    # 3 losing closes with an open in between — streak must reach 3
    ks.update_metrics(99.0, trade_pnl=-1, was_loss=True, is_trade_close=True)
    ks.update_metrics(99.0, was_loss=False)  # position open — must NOT reset streak
    ks.update_metrics(98.0, trade_pnl=-1, was_loss=True, is_trade_close=True)
    ks.update_metrics(97.0, trade_pnl=-1, was_loss=True, is_trade_close=True)
    check(
        "streak survives interleaved opens",
        ks.state.current_consecutive_losses == 3,
        f"(got {ks.state.current_consecutive_losses})",
    )
    # a winning close resets
    ks.update_metrics(98.0, trade_pnl=+1, was_loss=False, is_trade_close=True)
    check("winning close resets streak", ks.state.current_consecutive_losses == 0)


def t10_daily_rollover():
    print("T10: risk manager daily P&L rolls over on UTC date change")
    rm = RiskManager()
    rm.update_daily_pnl(D("-3"))
    check("daily pnl tracked", rm.daily_pnl == D("-3"))
    # simulate: the window was opened yesterday
    from datetime import timedelta

    rm._daily_pnl_date = rm._daily_pnl_date - timedelta(days=1)
    rm.update_daily_pnl(D("-1"))
    check("rolled over to new day", rm.daily_pnl == D("-1"), f"(got {rm.daily_pnl})")


async def t11_position_targeted_close():
    print("T11: position_id-targeted close closes THAT position")
    e = fresh_engine(leverage=1)
    e.balance = e.initial_balance = D(10000)
    # Two LONGs on the same symbol
    o1 = OrderCreate(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=D(1)
    )
    await e.execute_market_order(o1, D(100))
    p1 = e.position_manager.get_open_positions()[0]
    # second long: no position_id → engine would close p1; use direct create to
    # simulate a second position instead
    p2 = e.position_manager.create_position(
        symbol="BTCUSDT", side=PositionSide.LONG, entry_price=D(200), quantity=D(1)
    )
    c = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=D(1),
        reduce_only=True,
        position_id=p2.id,
    )
    await e.execute_market_order(c, D(210))
    open_ids = {p.id for p in e.position_manager.get_open_positions()}
    check("p2 closed, p1 still open", p2.id not in open_ids and p1.id in open_ids)


async def main():
    await t1_long_win()
    await t2_short_win()
    await t3_short_loss()
    await t4_reduce_only_rejected()
    await t5_partial_close()
    await t6_no_double_count()
    await t7_scale_in()
    await t8_leverage_roundtrip()
    t9_kill_switch()
    t10_daily_rollover()
    await t11_position_targeted_close()
    print(f"\n{'=' * 50}\nRESULT: {PASS} passed, {FAIL} failed\n{'=' * 50}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
