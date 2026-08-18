"""
Paper Trading Engine
Purpose: Simulate trading without real money
Enhanced: Database persistence for trades and positions
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional
from app.config import get_settings
from app.models import (
    Order,
    OrderCreate,
    OrderStatus,
    OrderSide,
    PositionSide,
    PositionStatus,
)
from app.position_manager import get_position_manager, _as_utc, _spawn_persist
from app.paper_slippage import build_slippage_model
from app.risk_manager import get_risk_manager
from app.repositories import get_trade_repository, get_portfolio_repository

logger = logging.getLogger(__name__)


def _trade_log_done(task: "asyncio.Task") -> None:
    """asyncio.Task done-callback: surface log_trade exceptions LOUDLY.

    Without this, fire-and-forget create_task() swallows coroutine errors —
    the GIGO chain that left `trades` empty for weeks despite a working
    log_trade() function.
    """
    try:
        exc = task.exception()
    except (asyncio.CancelledError, asyncio.InvalidStateError):
        return
    if exc is not None:
        logger.error("log_trade task failed: %s", exc, exc_info=exc)


def _spawn_trade_log(coro) -> None:
    """Schedule log_trade coro with error-visible done-callback."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_trade_log_done)


class PaperTradingEngine:
    """
    Simulates trading without real money

    Features:
    1. Virtual account balance
    2. Simulated order execution
    3. Commission simulation
    4. Per-symbol slippage simulation (PAPER-01)
    5. Position tracking
    6. Balance sync with database positions on startup

    Fill semantics (2026-08-03, PAPER-01): fills are no longer frictionless.
    Every market order fills at an adverse, per-symbol, tick-quantized price —
    BUY pays up, SELL gets less — so entry and exit both cost, for LONG and
    SHORT alike. The per-symbol basis-point figures and the sourcing for each
    (tick-derived half-spread floor, plus a taker-impact/latency allowance
    that is an ESTIMATE needing calibration) are documented in
    ``app/paper_slippage.py``. This supersedes the zero-slippage half of
    ADR-011; that ADR needs amending.
    """

    def __init__(self):
        """Initialize paper trading engine with database persistence"""
        self.settings = get_settings()
        self.initial_balance = Decimal(str(self.settings.paper_initial_balance))
        self.balance = (
            self.initial_balance
        )  # Will be adjusted in sync_balance_with_positions
        # `/ 100` after the Decimal wrap, not before: the old form did the
        # division in float and handed Decimal an already-lossy value.
        self.commission_pct = Decimal(
            str(self.settings.paper_commission_pct)
        ) / Decimal("100")
        self.slippage = build_slippage_model(self.settings)
        self._funding_client = None  # built lazily; PAPER-02
        self.position_manager = get_position_manager()
        self.risk_manager = get_risk_manager()

        # Database repositories for persistence
        self.trade_repo = get_trade_repository()
        self.portfolio_repo = get_portfolio_repository()

        logger.info("Paper Trading Engine initialized")
        logger.info(f"  Initial balance: ${self.initial_balance}")
        logger.info(f"  Commission: {self.settings.paper_commission_pct}%")
        logger.info(f"  Slippage: {self.slippage.describe()}")
        logger.info("  Database persistence: ENABLED")

    def _open_position_cost(self, positions) -> Decimal:
        """Margin + commission actually debited when these positions opened.

        Stage 0 (2026-08-07): reads the margin each position RECORDED at open
        rather than recomputing it from the current settings.default_leverage.
        The previous form made this docstring false — after the 2026-08-04
        DEFAULT_LEVERAGE 10.0 -> 1.0 flip it over-deducted for every 10x-era
        position on every restart.

        Fix round (2026-08-08): the commission term had the SAME defect one
        line below the one being fixed. It recomputed
        entry_price*qty*commission_pct from the CURRENT rate while
        positions.entry_fee holds what was actually debited, so changing
        PAPER_COMMISSION_PCT mis-deducted for every pre-change position on
        every restart — structurally identical to the leverage flip that
        caused this whole repair. Both terms now read what was recorded.

        The fee term is the UNCONSUMED portion, matching the margin term: a
        partial exit returns margin proportionally and charges the matching
        slice of entry fee to that leg's realized P&L, so what remains owed
        against the persisted cash figure is what neither has absorbed. At an
        unchanged commission rate this equals the old recomputation exactly.
        """
        total = Decimal("0")
        for pos in positions:
            posted = getattr(pos, "posted_margin", None) or Decimal("0")
            total += posted + self.position_manager.unconsumed_entry_fee(pos.id)
        return total

    async def sync_balance_with_positions(self):
        """
        Restore cash balance after a restart.

        FIX 2026-07-28: deduct MARGIN (notional / leverage) + commission, matching
        the open-leg accounting in execute_market_order. Previously this deducted
        full notional, so every restart with open positions understated cash.

        FIX 2026-07-31 (audit DL-2): the previous form was
        `initial_balance - open_position_cost`, which reconstructs cash from par
        and therefore discards every realized P&L and every commission ever paid
        on a closed leg. Measured across the 14:26 restart with zero trades in
        between, it invented $2.78 out of nothing -- exactly realized P&L plus
        the commissions of the two closed legs. Because auto_trader seeds the
        kill switch from this number, a drawdown breaker approaching its
        threshold was quietly re-armed toward par by any restart or crash-loop.

        The persisted `portfolios.cash_balance` is the true running ledger. It
        is written on position *close* (position_manager.close_position) and,
        since 2026-08-12, on partial exit and scale-in (execute_market_order
        below) — never on open. So it is accurate as of `portfolios.updated_at`,
        and any position opened after that timestamp has had its margin debited
        in memory but never persisted. Reconstruct as:

            cash_balance - cost(positions opened after portfolios.updated_at)
        """
        open_positions = self.position_manager.get_open_positions()

        portfolio = None
        try:
            portfolio = await self.portfolio_repo.get_or_create(
                portfolio_id="paper_trading"
            )
        except Exception as exc:
            logger.error(f"Could not read persisted portfolio balance: {exc}")

        if portfolio is None or portfolio.cash_balance is None:
            # Degrade to the old reconstruction, but never silently -- this
            # path fabricates cash and the operator needs to know it ran.
            self.balance = self.initial_balance - self._open_position_cost(
                open_positions
            )
            logger.error(
                "⚠️  Falling back to reconstructing cash from initial_balance; "
                "realized P&L and past commissions are NOT reflected. "
                f"Balance set to ${self.balance:.2f}"
            )
            return

        persisted_cash = Decimal(str(portfolio.cash_balance))
        last_write = _as_utc(portfolio.updated_at)

        # Only positions opened after the last persisted write still owe their
        # margin against that figure; anything older is already reflected in it.
        unpersisted = [
            pos
            for pos in open_positions
            if last_write is None
            or (pos.opened_at is not None and _as_utc(pos.opened_at) > last_write)
        ]
        unpersisted_cost = self._open_position_cost(unpersisted)
        self.balance = persisted_cash - unpersisted_cost

        logger.info(
            f"Balance restored from persisted ledger: ${persisted_cash:.2f} "
            f"(as of {last_write})"
        )
        logger.info(
            f"  Open positions: {len(open_positions)}, "
            f"of which opened after last write: {len(unpersisted)}"
        )
        if unpersisted:
            logger.info(f"  Unpersisted margin + commission: ${unpersisted_cost:.2f}")
        logger.info(f"  Restored balance: ${self.balance:.2f}")

    def get_balance(self) -> Decimal:
        """Get current account balance"""
        return self.balance

    def get_initial_balance(self) -> Decimal:
        """Starting equity used to compute returns / drawdown."""
        return self.initial_balance

    def get_total_equity(self) -> Decimal:
        """
        Get total equity (balance + unrealized P&L)
        """
        unrealized_pnl = self.position_manager.get_total_unrealized_pnl()
        return self.balance + unrealized_pnl

    def calculate_commission(self, order_value: Decimal) -> Decimal:
        """Calculate commission for an order"""
        return order_value * self.commission_pct

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

    async def execute_market_order(
        self, order: OrderCreate, current_price: Decimal
    ) -> tuple[Order, Optional[str]]:
        """
        Execute a market order (paper trading simulation)

        Args:
            order: Order to execute
            current_price: Reference market price (the ticker, NOT the fill)

        Returns:
            Tuple of (executed_order, error_message)
        """
        logger.info(
            f"Executing paper market order: {order.side.value} {order.quantity} {order.symbol} @ {current_price}"
        )

        # ====================================================================
        # REWRITTEN 2026-07-28 (accounting audit):
        #   * Closes credit margin_returned + realized_pnl - commission for BOTH
        #     sides (previously SHORT closes credited close-notional — a winning
        #     short REDUCED the balance — and leveraged LONG closes credited
        #     full notional while opens deducted margin only).
        #   * reduce_only is honored: a reduce-only order with no matching open
        #     position is REJECTED instead of silently opening an opposite
        #     position (this was flipping every stop-loss exit into a brand-new
        #     counter-trade).
        #   * order.position_id targets a specific position (no more
        #     open_positions[0] guesswork).
        #   * Partial closes are supported: an order for less than the
        #     remaining quantity reduces the position and credits
        #     proportional margin + P&L.
        #   * Same-side order with explicit position_id scales INTO the
        #     position (DCA averaging) instead of opening a duplicate.
        # ====================================================================
        # ====================================================================
        # SLIPPAGE (PAPER-01, 2026-08-03)
        #
        # `current_price` is the reference ticker; `fill_price` is what the
        # order actually gets. Resolved ONCE here and used for every price
        # downstream — notional, commission, filled_price, realized P&L, the
        # price handed to position_manager, and the trade log. If any of those
        # kept using `current_price`, the model would be wired but never bite:
        # get_performance_summary() reads realized P&L off the *positions*, so
        # a fill price that stops at the cash ledger changes nothing reported.
        # The only surviving uses of `current_price` below are log strings.
        # ====================================================================
        fill_price = self.slippage.fill_price(order.symbol, order.side, current_price)

        order_value = fill_price * order.quantity
        commission = self.calculate_commission(order_value)
        # Stage 0 (2026-08-07): this is the leverage a NEW leg posts margin at.
        # It is stamped onto the position. The CLOSE leg no longer reads it —
        # it consumes position.posted_margin instead. Gated on leverage_enabled
        # AND clamped to [min_leverage, max_leverage] so this derives leverage
        # identically to auto_trader.py:2008-2013 and :4410-4415, the two
        # sizing sites. paper_trading did neither.
        #
        # The clamp is not cosmetic: config.py:617-626 permits default_leverage
        # up to 100 while max_leverage defaults to 20. Unclamped, DEFAULT_LEVERAGE
        # =50 had auto_trader size notional at 20x while this posted notional/50
        # — 40% of the intended margin, so the per-trade cap under-bound by 2.5x
        # in cash terms. Conservation still held (the close credits what was
        # posted), but the sizing contract did not.
        leverage = Decimal("1")
        if getattr(self.settings, "leverage_enabled", False):
            leverage = max(
                Decimal(str(self.settings.min_leverage)),
                min(
                    Decimal(str(self.settings.default_leverage)),
                    Decimal(str(self.settings.max_leverage)),
                ),
            )

        executed_order = Order(
            **order.model_dump(),
            status=OrderStatus.FILLED,
            filled_price=fill_price,
            filled_quantity=order.quantity,
            bybit_order_id=f"PAPER_{order.symbol}_{order.side.value}",
        )

        # Side that this order would CLOSE (SELL closes LONG, BUY closes SHORT)
        close_side = (
            PositionSide.LONG if order.side == OrderSide.SELL else PositionSide.SHORT
        )
        open_side = (
            PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT
        )

        # ---- Resolve the target position ------------------------------------
        target = None
        if order.position_id is not None:
            pos = self.position_manager.get_position(order.position_id)
            if pos is not None and pos.status == PositionStatus.OPEN:
                target = pos
            elif order.reduce_only:
                error_msg = (
                    f"Reduce-only order rejected: position {order.position_id} "
                    f"not found or not open"
                )
                logger.warning(error_msg)
                executed_order.status = OrderStatus.FAILED
                return executed_order, error_msg

        if target is None:
            candidates = [
                pos
                for pos in self.position_manager.get_open_positions()
                if pos.symbol == order.symbol and pos.side == close_side
            ]
            if candidates:
                target = candidates[0]

        # ---- CLOSE / REDUCE path --------------------------------------------
        if target is not None and target.side == close_side:
            qty_open = (
                target.remaining_quantity
                if target.remaining_quantity is not None
                else target.quantity
            )
            close_qty = min(order.quantity, qty_open)
            if close_qty <= 0:
                error_msg = f"Nothing to close on position {target.id}"
                logger.warning(error_msg)
                executed_order.status = OrderStatus.FAILED
                return executed_order, error_msg

            close_value = fill_price * close_qty
            close_commission = self.calculate_commission(close_value)

            # Price-based P&L on the quantity actually closed, at the SLIPPED
            # exit price. A SELL close fills below the ticker and a BUY close
            # (covering a short) fills above it, so the exit costs on both
            # sides — the SHORT leg is the one this repo has inverted before.
            # GROSS here: the position manager nets out this leg's commission
            # plus the proportional entry fee before anything is persisted
            # (AUDIT H7, 2026-08-04).
            if target.side == PositionSide.LONG:
                realized_pnl = (fill_price - target.entry_price) * close_qty
            else:  # SHORT
                realized_pnl = (target.entry_price - fill_price) * close_qty

            # Stage 0 (2026-08-07): return what this position POSTED, not what
            # the current global leverage would imply. The old form recomputed
            # entry_price*close_qty/settings.default_leverage; a position
            # opened at 10x and closed after DEFAULT_LEVERAGE dropped to 1.0
            # credited back 10x its margin (~$177 fabricated on a $100 account).
            # Must run BEFORE close_position/reduce_position touch
            # remaining_quantity.
            margin_returned = self.position_manager.consume_posted_margin(
                target.id, close_qty
            )

            # Perp funding accrued over the hold (PAPER-02). Signed; POSITIVE
            # means this leg PAID. Must reach both ledgers exactly as
            # close_commission does, or it is invisible to reported P&L and
            # the daily-loss breaker (paper_trading.py module docstring).
            funding_paid = await self._funding_for_leg(
                order.symbol,
                target.side,
                target.entry_price * close_qty,
                target.opened_at,
            )

            # Cash ledger: gross P&L minus the exit commission and funding.
            # The entry fee already left the cash balance at open — netting
            # it here again would double-charge cash; it is netted only in
            # REPORTED P&L.
            self.balance += (
                margin_returned + realized_pnl - close_commission - funding_paid
            )

            # Net P&L delta this leg contributes to the position's realized
            # P&L (computed by the position manager, which owns the entry-fee
            # ledger); captured via before/after so the trade log records the
            # same net figure that the position row accumulates.
            realized_before = target.realized_pnl

            full_close = close_qty >= qty_open
            if full_close:
                closed_position = self.position_manager.close_position(
                    target.id,
                    fill_price,
                    reason=f"Market {order.side.value.lower()} order "
                    f"({target.side.value} close)"
                    + (f" [{order.strategy}]" if order.strategy else ""),
                    close_commission=close_commission + funding_paid,
                    exit_kind=order.exit_kind,
                )
                executed_order.position_id = closed_position.id
                net_leg_pnl = closed_position.realized_pnl - realized_before
            else:
                reduced_position = self.position_manager.reduce_position(
                    target.id,
                    close_qty,
                    fill_price,
                    realized_pnl,
                    close_commission=close_commission + funding_paid,
                )
                executed_order.position_id = target.id
                net_leg_pnl = reduced_position.realized_pnl - realized_before

                # Only the full close writes the portfolio ledger. Without this
                # snapshot the partial exit's credit lives in memory alone,
                # while its position — opened before the last persisted write —
                # counts as already reflected, so a restart drops the credit.
                # Cash only: update_balance OVERWRITES realized_pnl, which the
                # eventual close accumulates with this leg already in it.
                _spawn_persist(
                    self.portfolio_repo.update_balance(
                        portfolio_id="paper_trading",
                        cash_balance=self.balance,
                    ),
                    "portfolio cash snapshot (partial exit)",
                )

            executed_order.filled_quantity = close_qty

            logger.info(
                f"✓ {target.side.value} {'closed' if full_close else 'reduced'}: "
                f"{close_qty} {order.symbol} @ {fill_price} "
                f"(ref {current_price}) | "
                f"Margin returned: ${margin_returned:.4f} | "
                f"Gross P&L: ${realized_pnl:.4f} | Net P&L: ${net_leg_pnl:.4f} | "
                f"Commission: ${close_commission:.4f} | Funding: ${funding_paid:.4f} | "
                f"Balance: ${self.balance:.4f}"
            )

            _spawn_trade_log(
                self.trade_repo.log_trade(
                    position_id=target.id,
                    portfolio_id="paper_trading",
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=close_qty,
                    price=fill_price,
                    commission=close_commission,
                    strategy=order.strategy,
                    signal_confidence=order.entry_signal_confidence,
                    realized_pnl=net_leg_pnl,
                )
            )
            return executed_order, None

        # ---- Reduce-only with nothing to reduce → REJECT (never flip) -------
        if order.reduce_only:
            error_msg = (
                f"Reduce-only {order.side.value} for {order.symbol} rejected: "
                f"no open {close_side.value} position to reduce"
            )
            logger.warning(error_msg)
            executed_order.status = OrderStatus.FAILED
            return executed_order, error_msg

        # ---- SCALE-IN path (same-side position explicitly targeted) ---------
        if order.position_id is not None:
            pos = self.position_manager.get_position(order.position_id)
            if (
                pos is not None
                and pos.status == PositionStatus.OPEN
                and pos.side == open_side
                and pos.symbol == order.symbol
            ):
                margin_required = order_value / leverage
                total_cost = margin_required + commission
                if total_cost > self.balance:
                    error_msg = (
                        f"Insufficient balance for scale-in: need ${total_cost}, "
                        f"have ${self.balance}"
                    )
                    logger.warning(error_msg)
                    executed_order.status = OrderStatus.FAILED
                    return executed_order, error_msg

                self.balance -= total_cost
                self.position_manager.scale_in(
                    pos.id,
                    order.quantity,
                    fill_price,
                    entry_fee=commission,
                    posted_margin=margin_required,
                )
                executed_order.position_id = pos.id

                logger.info(
                    f"✓ {pos.side.value} scaled in: +{order.quantity} {order.symbol} "
                    f"@ {fill_price} (ref {current_price}) | "
                    f"New avg entry: {pos.entry_price} | "
                    f"Balance: ${self.balance:.4f}"
                )

                # Same reason as the partial-exit snapshot above, opposite sign:
                # a scale-in debits margin + commission with no close of its own
                # to persist them, so a restart refunds the debit.
                _spawn_persist(
                    self.portfolio_repo.update_balance(
                        portfolio_id="paper_trading",
                        cash_balance=self.balance,
                    ),
                    "portfolio cash snapshot (scale-in)",
                )

                _spawn_trade_log(
                    self.trade_repo.log_trade(
                        position_id=pos.id,
                        portfolio_id="paper_trading",
                        symbol=order.symbol,
                        side=order.side.value,
                        quantity=order.quantity,
                        price=fill_price,
                        commission=commission,
                        strategy=order.strategy,
                        signal_confidence=order.entry_signal_confidence,
                    )
                )
                return executed_order, None

        # ---- OPEN path -------------------------------------------------------
        margin_required = order_value / leverage
        total_cost = margin_required + commission

        if total_cost > self.balance:
            error_msg = (
                f"Insufficient balance: need ${total_cost}, have ${self.balance}"
            )
            logger.warning(error_msg)
            executed_order.status = OrderStatus.FAILED
            return executed_order, error_msg

        self.balance -= total_cost
        logger.debug(
            f"{open_side.value} margin calculation: order_value=${order_value}, "
            f"leverage={leverage}x, margin=${margin_required}, commission=${commission}"
        )

        position = self.position_manager.create_position(
            symbol=order.symbol,
            side=open_side,
            entry_price=fill_price,
            quantity=order.quantity,
            strategy=order.strategy,
            entry_signal_confidence=order.entry_signal_confidence,
            entry_fee=commission,
            posted_margin=margin_required,
            leverage=leverage,
        )

        executed_order.position_id = position.id

        logger.info(
            f"✓ {open_side.value} opened: {order.quantity} {order.symbol} "
            f"@ {fill_price} (ref {current_price}) | "
            f"Position: ${order_value} | Margin: ${margin_required} ({leverage}x leverage) "
            f"+ Commission: ${commission} | Balance: ${self.balance}"
        )

        _spawn_trade_log(
            self.trade_repo.log_trade(
                position_id=position.id,
                portfolio_id="paper_trading",
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                price=fill_price,
                commission=commission,
                strategy=order.strategy,
                signal_confidence=order.entry_signal_confidence,
            )
        )

        return executed_order, None

    def can_open_position(
        self, symbol: str, quantity: Decimal, price: Decimal
    ) -> tuple[bool, Optional[str]]:
        """
        Check if we can open a new position

        Args:
            symbol: Trading symbol
            quantity: Position quantity
            price: Entry price

        Returns:
            Tuple of (can_open, reason if cannot)
        """
        # Calculate required capital
        order_value = quantity * price
        commission = self.calculate_commission(order_value)
        total_cost = order_value + commission

        # Check balance
        if total_cost > self.balance:
            return (
                False,
                f"Insufficient balance: need ${total_cost}, have ${self.balance}",
            )

        # Check position limits
        open_positions = self.position_manager.get_open_positions()
        can_open, reason = self.risk_manager.check_position_limits(
            open_positions, self.get_total_equity()
        )

        if not can_open:
            return False, reason

        return True, None

    def get_performance_summary(self) -> dict:
        """Get performance summary with accurate unrealized PnL"""
        # Get unrealized PnL from open positions
        unrealized_pnl = self.position_manager.get_total_unrealized_pnl()

        # Total equity = cash balance + unrealized PnL
        total_equity = self.balance + unrealized_pnl
        total_pnl = total_equity - self.initial_balance
        roi = (
            (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
        )

        # Calculate realized PnL from closed positions
        closed_positions = self.position_manager.get_closed_positions()
        realized_pnl = sum(pos.realized_pnl for pos in closed_positions)
        winning_trades = sum(1 for pos in closed_positions if pos.realized_pnl > 0)
        losing_trades = sum(1 for pos in closed_positions if pos.realized_pnl < 0)
        total_trades = len(closed_positions)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Get open positions for exposure calculation
        open_positions = self.position_manager.get_open_positions()
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

        return {
            "initial_balance": float(self.initial_balance),
            "current_balance": float(self.balance),
            "total_equity": float(total_equity),
            "total_exposure": float(total_exposure),
            "unrealized_pnl": float(unrealized_pnl),
            "realized_pnl": float(realized_pnl),
            "total_pnl": float(total_pnl),
            "roi": round(float(roi), 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "open_positions": len(open_positions),
        }


# Global paper trading engine instance
_paper_engine: Optional[PaperTradingEngine] = None


def get_paper_engine() -> PaperTradingEngine:
    """Get or create paper trading engine instance"""
    global _paper_engine
    if _paper_engine is None:
        _paper_engine = PaperTradingEngine()
    return _paper_engine
