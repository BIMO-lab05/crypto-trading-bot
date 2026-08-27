"""
Portfolio Heat Manager - Total Exposure Risk Control
Research Source: Hedge Fund Risk Management Best Practices (2025-12-02)

Purpose:
- Track total capital at risk across all open positions
- Prevent over-exposure by enforcing portfolio heat limits
- Manage correlation risk between crypto assets
- Implement tiered position reduction during high exposure

Key Features:
- Portfolio heat = sum of all position risks as % of equity
- Maximum portfolio heat limit (default: 8%)
- Correlation-adjusted exposure for crypto pairs
- Dynamic position sizing based on current heat level
- BTC correlation tracking (all cryptos correlate with BTC during stress)

Research Findings Applied:
- Conservative hedge funds: 6-8% max portfolio heat
- Standard institutional: 8-10% max
- Single position limit: 5-10% max
- Correlated exposure limit: 5-6% max
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)


class HeatLevel(Enum):
    """Portfolio heat level classification"""
    LOW = "low"           # < 4% - Full trading allowed
    MODERATE = "moderate"  # 4-6% - Normal trading
    ELEVATED = "elevated"  # 6-8% - Reduced position sizes
    HIGH = "high"         # > 8% - Block new trades
    CRITICAL = "critical"  # > 10% - Emergency reduction


@dataclass
class PortfolioHeatConfig:
    """
    Configuration for portfolio heat management

    Research-backed defaults (2025-12-02):
    - Max portfolio heat: 8% (conservative institutional standard)
    - Max per trade: 2% (industry standard)
    - Max correlated exposure: 5% (crypto BTC correlation risk)
    - Max single asset: 10% (diversification requirement)
    """
    # Primary limits
    max_portfolio_heat_pct: float = 8.0       # Max total risk exposure
    max_per_trade_pct: float = 2.0            # Max risk per single trade
    max_correlated_exposure_pct: float = 5.0  # Max in highly correlated assets
    max_single_asset_pct: float = 10.0        # Max allocation to single asset

    # Heat level thresholds
    low_heat_threshold: float = 4.0           # Below this = low heat
    moderate_heat_threshold: float = 6.0      # Below this = moderate
    elevated_heat_threshold: float = 8.0      # Below this = elevated
    critical_heat_threshold: float = 10.0     # Above this = critical

    # Position size multipliers by heat level
    heat_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "low": 1.0,        # Full size
        "moderate": 0.85,  # 15% reduction
        "elevated": 0.60,  # 40% reduction
        "high": 0.25,      # 75% reduction
        "critical": 0.0    # No new trades
    })

    # Correlation thresholds
    high_correlation_threshold: float = 0.70   # Consider highly correlated
    medium_correlation_threshold: float = 0.50  # Moderately correlated

    # Correlation-based position sizing (2025-12-02)
    # Reduce position size when adding correlated assets
    correlation_size_adjustments: Dict[str, float] = field(default_factory=lambda: {
        "very_high": 0.50,   # Correlation > 0.85: 50% size reduction
        "high": 0.70,        # Correlation 0.70-0.85: 30% size reduction
        "medium": 0.85,      # Correlation 0.50-0.70: 15% size reduction
        "low": 1.0           # Correlation < 0.50: full size
    })

    # BTC correlation assumptions for major cryptos (research-based)
    # During market stress, these can spike to 0.85+
    btc_correlations: Dict[str, float] = field(default_factory=lambda: {
        "ETHUSDT": 0.85,   # Very high correlation
        "BNBUSDT": 0.75,   # High correlation
        "SOLUSDT": 0.80,   # High correlation
        "ADAUSDT": 0.70,   # High correlation
        "DOGEUSDT": 0.65,  # Moderate-high
        "AVAXUSDT": 0.75,  # High correlation
        "LINKUSDT": 0.70,  # High correlation
        "POLUSDT": 0.70,   # High correlation
        "DOTUSDT": 0.75,   # High correlation
        "LTCUSDT": 0.80,   # High correlation
        "ARBUSDT": 0.75,   # High correlation
        "OPUSDT": 0.75,    # High correlation
        "APTUSDT": 0.70,   # High correlation
        "SUIUSDT": 0.70,   # High correlation
        "BTCUSDT": 1.0,    # Perfect correlation with itself
    })

    # 🆕 Pyramiding / Multiple Positions Settings (OPTIONAL - 2025-12-04)
    # Allow adding to winning positions (conservative pyramiding)
    # DISABLED by default - enable after validating hybrid optimization
    allow_pyramiding: bool = False  # Set to True to enable multiple positions per symbol
    max_positions_per_symbol: int = 2  # Maximum concurrent positions in same symbol
    pyramiding_same_direction_only: bool = True  # Only allow same direction (no hedging)
    pyramiding_require_profit: bool = True  # Second position only if first is profitable
    pyramiding_min_profit_pct: float = 1.0  # First position must be +1% to pyramid
    max_symbol_exposure_pct: float = 15.0  # Maximum total exposure to single symbol


@dataclass
class PositionRisk:
    """Risk metrics for a single position"""
    symbol: str
    side: str  # LONG or SHORT
    entry_price: float
    current_price: float
    quantity: float
    stop_loss: float
    position_value: float
    risk_amount: float       # $ at risk (entry to stop loss)
    risk_pct: float          # Risk as % of portfolio
    btc_correlation: float   # Correlation with BTC
    unrealized_pnl: float
    unrealized_pnl_pct: float


@dataclass
class PortfolioHeatStatus:
    """Current portfolio heat status"""
    total_heat_pct: float
    heat_level: HeatLevel
    position_count: int
    total_exposure_value: float
    total_risk_amount: float
    correlated_heat_pct: float  # Heat in BTC-correlated positions
    available_heat_pct: float   # Remaining heat capacity
    position_size_multiplier: float  # Recommended size multiplier
    can_open_new_trade: bool
    blocking_reason: Optional[str] = None
    positions: List[PositionRisk] = field(default_factory=list)


class PortfolioHeatManager:
    """
    Portfolio Heat Manager - Controls total risk exposure

    Research-backed implementation (2025-12-02):
    - Tracks total capital at risk across all positions
    - Enforces maximum portfolio heat (8% default)
    - Adjusts position sizes based on current heat
    - Tracks correlation risk (BTC-correlated exposure)

    Usage:
        from app.config import get_settings

        heat_manager = PortfolioHeatManager(config)

        # Before opening a trade. `equity` is account equity: resolve it from
        # this service's own Settings, never from a literal. A bare 10000 is
        # numerically correct for the $10,000 research account (ADR-029) and
        # is STILL a defect — it bypasses the declared config and silently
        # decouples on the next re-scale. In-container code reads
        # Settings.paper_initial_balance and must never `import
        # shared.account` (.claude/rules/money.md).
        can_trade, reason, multiplier = heat_manager.can_open_trade(
            symbol="ETHUSDT",
            proposed_risk_pct=1.5,
            equity=get_settings().paper_initial_balance
        )

        if can_trade:
            adjusted_size = original_size * multiplier
            # Execute trade with adjusted_size

        # After trade execution
        heat_manager.add_position(position_risk)

        # Get current status
        status = heat_manager.get_status(
            equity=get_settings().paper_initial_balance
        )
    """

    def __init__(self, config: Optional[PortfolioHeatConfig] = None):
        """Initialize Portfolio Heat Manager"""
        self.config = config or PortfolioHeatConfig()
        self.positions: Dict[str, PositionRisk] = {}
        self._last_update: Optional[datetime] = None

        logger.info(
            f"PortfolioHeatManager initialized: "
            f"max_heat={self.config.max_portfolio_heat_pct}%, "
            f"max_per_trade={self.config.max_per_trade_pct}%, "
            f"max_correlated={self.config.max_correlated_exposure_pct}%"
        )

    def calculate_position_risk(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        current_price: float,
        equity: float
    ) -> PositionRisk:
        """
        Calculate risk metrics for a position

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            entry_price: Entry price
            quantity: Position quantity
            stop_loss: Stop loss price
            current_price: Current market price
            equity: Total account equity

        Returns:
            PositionRisk object with all risk metrics
        """
        position_value = current_price * quantity

        # Calculate risk amount (distance to stop loss)
        if side == "LONG":
            risk_per_unit = entry_price - stop_loss
            unrealized_pnl = (current_price - entry_price) * quantity
        else:
            risk_per_unit = stop_loss - entry_price
            unrealized_pnl = (entry_price - current_price) * quantity

        risk_amount = abs(risk_per_unit * quantity)
        risk_pct = (risk_amount / equity) * 100 if equity > 0 else 0
        unrealized_pnl_pct = (unrealized_pnl / (entry_price * quantity)) * 100 if entry_price > 0 else 0

        # Get BTC correlation
        btc_correlation = self.config.btc_correlations.get(symbol, 0.60)

        return PositionRisk(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=current_price,
            quantity=quantity,
            stop_loss=stop_loss,
            position_value=position_value,
            risk_amount=risk_amount,
            risk_pct=risk_pct,
            btc_correlation=btc_correlation,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct
        )

    def add_position(self, position: PositionRisk):
        """Add or update a position in tracking"""
        self.positions[position.symbol] = position
        self._last_update = datetime.now()

        logger.info(
            f"[HEAT] Position added: {position.symbol} | "
            f"Risk: {position.risk_pct:.2f}% | "
            f"Value: ${position.position_value:.2f}"
        )

    def remove_position(self, symbol: str):
        """Remove a position from tracking"""
        if symbol in self.positions:
            del self.positions[symbol]
            self._last_update = datetime.now()
            logger.info(f"[HEAT] Position removed: {symbol}")

    def update_position_price(self, symbol: str, current_price: float, equity: float):
        """Update position with current price and recalculate risk"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            updated = self.calculate_position_risk(
                symbol=pos.symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                quantity=pos.quantity,
                stop_loss=pos.stop_loss,
                current_price=current_price,
                equity=equity
            )
            self.positions[symbol] = updated

    def get_total_heat(self) -> float:
        """Get total portfolio heat (sum of all position risks)"""
        return sum(pos.risk_pct for pos in self.positions.values())

    def get_correlated_heat(self, threshold: float = 0.70) -> float:
        """
        Get heat from highly BTC-correlated positions

        Args:
            threshold: Correlation threshold for "highly correlated"

        Returns:
            Sum of risk_pct for positions with BTC correlation >= threshold
        """
        return sum(
            pos.risk_pct
            for pos in self.positions.values()
            if pos.btc_correlation >= threshold
        )

    def get_heat_level(self, total_heat: float) -> HeatLevel:
        """Classify current heat level"""
        if total_heat >= self.config.critical_heat_threshold:
            return HeatLevel.CRITICAL
        elif total_heat >= self.config.elevated_heat_threshold:
            return HeatLevel.HIGH
        elif total_heat >= self.config.moderate_heat_threshold:
            return HeatLevel.ELEVATED
        elif total_heat >= self.config.low_heat_threshold:
            return HeatLevel.MODERATE
        else:
            return HeatLevel.LOW

    def get_position_multiplier(self, heat_level: HeatLevel) -> float:
        """Get recommended position size multiplier based on heat level"""
        return self.config.heat_multipliers.get(heat_level.value, 1.0)

    def calculate_portfolio_correlation(self, symbol: str) -> Tuple[float, Dict[str, float]]:
        """
        Calculate correlation between new symbol and existing portfolio positions

        Uses BTC as a proxy for correlation measurement since all cryptos
        correlate with BTC (research: 0.65-0.87 correlation during stress).

        The effective correlation is calculated as:
        - Get BTC correlation of new symbol
        - Get weighted average BTC correlation of existing positions
        - Correlation = min(1.0, correlation_product)

        Args:
            symbol: Symbol to check correlation for

        Returns:
            Tuple of (average_correlation, correlation_breakdown_by_symbol)
        """
        if not self.positions:
            return 0.0, {}

        new_symbol_btc_corr = self.config.btc_correlations.get(symbol, 0.60)

        correlations = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for pos_symbol, pos in self.positions.items():
            # Calculate implied correlation between two assets via BTC
            # corr(A,B) ≈ corr(A,BTC) * corr(B,BTC) for BTC-correlated assets
            pos_btc_corr = pos.btc_correlation
            implied_correlation = min(1.0, new_symbol_btc_corr * pos_btc_corr)

            # Weight by position risk
            weight = pos.risk_pct
            weighted_sum += implied_correlation * weight
            total_weight += weight

            correlations[pos_symbol] = round(implied_correlation, 3)

        avg_correlation = weighted_sum / total_weight if total_weight > 0 else 0.0

        return round(avg_correlation, 3), correlations

    def get_correlation_size_multiplier(self, symbol: str) -> Tuple[float, str]:
        """
        Get position size multiplier based on correlation with existing portfolio

        Research (2025-12-02):
        - Adding highly correlated assets increases portfolio risk non-linearly
        - Position size should be reduced when correlation is high
        - This promotes diversification and reduces drawdown during market stress

        Args:
            symbol: Symbol to get multiplier for

        Returns:
            Tuple of (multiplier, correlation_level_description)
        """
        avg_correlation, _ = self.calculate_portfolio_correlation(symbol)

        # Determine correlation level and multiplier
        if avg_correlation >= 0.85:
            multiplier = self.config.correlation_size_adjustments.get("very_high", 0.50)
            level = "VERY_HIGH"
        elif avg_correlation >= 0.70:
            multiplier = self.config.correlation_size_adjustments.get("high", 0.70)
            level = "HIGH"
        elif avg_correlation >= 0.50:
            multiplier = self.config.correlation_size_adjustments.get("medium", 0.85)
            level = "MEDIUM"
        else:
            multiplier = self.config.correlation_size_adjustments.get("low", 1.0)
            level = "LOW"

        logger.info(
            f"[CORRELATION] {symbol}: avg_corr={avg_correlation:.2f}, "
            f"level={level}, size_multiplier={multiplier:.0%}"
        )

        return multiplier, level

    def get_combined_size_multiplier(
        self,
        symbol: str,
        equity: float
    ) -> Tuple[float, Dict[str, float]]:
        """
        Get combined position size multiplier from all factors

        Combines:
        1. Heat-based multiplier (based on total portfolio heat)
        2. Correlation-based multiplier (based on correlation with existing positions)

        The final multiplier is the product of both (more conservative).

        Args:
            symbol: Symbol to size position for
            equity: Current account equity

        Returns:
            Tuple of (final_multiplier, breakdown_dict)
        """
        # Get heat-based multiplier
        total_heat = self.get_total_heat()
        heat_level = self.get_heat_level(total_heat)
        heat_multiplier = self.get_position_multiplier(heat_level)

        # Get correlation-based multiplier
        correlation_multiplier, corr_level = self.get_correlation_size_multiplier(symbol)

        # Combined multiplier (product of both - more conservative)
        combined_multiplier = heat_multiplier * correlation_multiplier

        breakdown = {
            "heat_multiplier": heat_multiplier,
            "heat_level": heat_level.value,
            "correlation_multiplier": correlation_multiplier,
            "correlation_level": corr_level,
            "combined_multiplier": combined_multiplier,
            "total_heat_pct": total_heat
        }

        avg_corr, corr_breakdown = self.calculate_portfolio_correlation(symbol)
        breakdown["avg_portfolio_correlation"] = avg_corr
        breakdown["correlation_breakdown"] = corr_breakdown

        logger.info(
            f"[SIZE] {symbol}: heat={heat_multiplier:.0%} x corr={correlation_multiplier:.0%} "
            f"= {combined_multiplier:.0%} combined multiplier"
        )

        return combined_multiplier, breakdown

    def can_open_trade(
        self,
        symbol: str,
        proposed_risk_pct: float,
        equity: float,
        btc_correlation: Optional[float] = None,
        side: Optional[str] = None  # 🆕 "LONG" or "SHORT" for pyramiding logic
    ) -> Tuple[bool, Optional[str], float]:
        """
        Check if a new trade can be opened

        Args:
            symbol: Symbol to trade
            proposed_risk_pct: Proposed risk as % of equity
            equity: Total account equity
            btc_correlation: BTC correlation (uses default if not provided)
            side: Trade direction ("LONG" or "SHORT") - required for pyramiding

        Returns:
            Tuple of (can_trade, blocking_reason, size_multiplier)
        """
        # Get current heat
        total_heat = self.get_total_heat()
        heat_level = self.get_heat_level(total_heat)
        multiplier = self.get_position_multiplier(heat_level)

        # 🆕 PYRAMIDING LOGIC (OPTIONAL - 2025-12-04)
        # Check existing positions in this symbol
        if symbol in self.positions:
            # If pyramiding disabled, block all duplicate positions
            if not self.config.allow_pyramiding:
                return False, f"Already have open position in {symbol}", 0.0

            # Pyramiding enabled - check constraints
            symbol_positions = self.positions[symbol] if isinstance(self.positions[symbol], list) else [self.positions[symbol]]

            # Check max positions per symbol limit
            if len(symbol_positions) >= self.config.max_positions_per_symbol:
                return False, f"Max {self.config.max_positions_per_symbol} positions per symbol reached for {symbol}", 0.0

            # Check same direction only (no hedging)
            if self.config.pyramiding_same_direction_only and side:
                existing_sides = {pos.side for pos in symbol_positions}
                if side not in existing_sides and len(existing_sides) > 0:
                    return False, f"Cannot open {side} position - already have {existing_sides.pop()} position in {symbol} (no hedging allowed)", 0.0

            # Check profitability requirement for additional positions
            if self.config.pyramiding_require_profit and len(symbol_positions) > 0:
                # Get first position profitability
                first_pos = symbol_positions[0]
                profit_pct = ((first_pos.current_price - first_pos.entry_price) / first_pos.entry_price * 100) if first_pos.side == "LONG" else ((first_pos.entry_price - first_pos.current_price) / first_pos.entry_price * 100)

                if profit_pct < self.config.pyramiding_min_profit_pct:
                    return False, f"First position must be +{self.config.pyramiding_min_profit_pct}% to pyramid (current: {profit_pct:+.2f}%)", 0.0

            # Check total symbol exposure limit
            total_symbol_risk = sum(pos.risk_pct for pos in symbol_positions) + proposed_risk_pct
            if total_symbol_risk > self.config.max_symbol_exposure_pct:
                available = self.config.max_symbol_exposure_pct - sum(pos.risk_pct for pos in symbol_positions)
                return False, f"Would exceed {symbol} exposure limit ({total_symbol_risk:.2f}% > {self.config.max_symbol_exposure_pct}%). Available: {available:.2f}%", 0.0

            logger.info(f"✅ PYRAMIDING: Adding {side} position #{len(symbol_positions)+1} to {symbol}")

        # Check per-trade limit
        if proposed_risk_pct > self.config.max_per_trade_pct:
            return False, f"Risk {proposed_risk_pct:.2f}% exceeds per-trade limit {self.config.max_per_trade_pct}%", 0.0

        # Check portfolio heat limit
        new_total_heat = total_heat + proposed_risk_pct
        if new_total_heat > self.config.max_portfolio_heat_pct:
            available = max(0, self.config.max_portfolio_heat_pct - total_heat)
            return False, f"Would exceed portfolio heat limit. Available: {available:.2f}%", 0.0

        # Check correlated exposure
        correlation = btc_correlation or self.config.btc_correlations.get(symbol, 0.60)
        if correlation >= self.config.high_correlation_threshold:
            correlated_heat = self.get_correlated_heat()
            new_correlated = correlated_heat + proposed_risk_pct

            if new_correlated > self.config.max_correlated_exposure_pct:
                available = max(0, self.config.max_correlated_exposure_pct - correlated_heat)
                return False, f"Would exceed correlated exposure limit. Available: {available:.2f}%", 0.0

        # Check heat level allows trading
        if heat_level == HeatLevel.CRITICAL:
            return False, "Portfolio heat CRITICAL - no new trades allowed", 0.0

        # Trade allowed with size adjustment
        if multiplier < 1.0:
            logger.info(
                f"[HEAT] Trade allowed with reduced size: "
                f"{multiplier:.0%} due to {heat_level.value} heat level"
            )

        return True, None, multiplier

    def get_status(self, equity: float) -> PortfolioHeatStatus:
        """
        Get comprehensive portfolio heat status

        Args:
            equity: Current account equity

        Returns:
            PortfolioHeatStatus with all heat metrics
        """
        total_heat = self.get_total_heat()
        heat_level = self.get_heat_level(total_heat)
        multiplier = self.get_position_multiplier(heat_level)
        correlated_heat = self.get_correlated_heat()

        total_exposure = sum(pos.position_value for pos in self.positions.values())
        total_risk = sum(pos.risk_amount for pos in self.positions.values())

        available_heat = max(0, self.config.max_portfolio_heat_pct - total_heat)
        can_trade = heat_level not in [HeatLevel.CRITICAL]

        blocking_reason = None
        if not can_trade:
            blocking_reason = f"Heat level {heat_level.value} - trading blocked"

        return PortfolioHeatStatus(
            total_heat_pct=total_heat,
            heat_level=heat_level,
            position_count=len(self.positions),
            total_exposure_value=total_exposure,
            total_risk_amount=total_risk,
            correlated_heat_pct=correlated_heat,
            available_heat_pct=available_heat,
            position_size_multiplier=multiplier,
            can_open_new_trade=can_trade,
            blocking_reason=blocking_reason,
            positions=list(self.positions.values())
        )

    def get_recommended_risk_pct(
        self,
        base_risk_pct: float,
        symbol: str,
        equity: float
    ) -> float:
        """
        Get recommended risk percentage after heat adjustments

        Args:
            base_risk_pct: Original intended risk %
            symbol: Trading symbol
            equity: Account equity

        Returns:
            Adjusted risk percentage
        """
        total_heat = self.get_total_heat()
        heat_level = self.get_heat_level(total_heat)
        multiplier = self.get_position_multiplier(heat_level)

        # Apply heat-based reduction
        adjusted_risk = base_risk_pct * multiplier

        # Ensure within limits
        adjusted_risk = min(adjusted_risk, self.config.max_per_trade_pct)

        # Check available heat
        available = self.config.max_portfolio_heat_pct - total_heat
        adjusted_risk = min(adjusted_risk, available)

        # Check correlated limit
        correlation = self.config.btc_correlations.get(symbol, 0.60)
        if correlation >= self.config.high_correlation_threshold:
            correlated_available = self.config.max_correlated_exposure_pct - self.get_correlated_heat()
            adjusted_risk = min(adjusted_risk, correlated_available)

        return max(0, adjusted_risk)

    def sync_with_positions(
        self,
        open_positions: List,
        equity: float
    ):
        """
        Sync internal tracking with actual open positions

        Args:
            open_positions: List of position objects from position manager
            equity: Current account equity
        """
        # Build set of current position symbols
        current_symbols = set()

        for pos in open_positions:
            symbol = pos.symbol
            current_symbols.add(symbol)

            # Calculate and update position risk
            position_risk = self.calculate_position_risk(
                symbol=symbol,
                side=pos.side,
                entry_price=float(pos.entry_price),
                quantity=float(pos.quantity),
                stop_loss=float(pos.stop_loss) if pos.stop_loss else float(pos.entry_price) * 0.98,
                current_price=float(pos.current_price) if hasattr(pos, 'current_price') else float(pos.entry_price),
                equity=equity
            )
            self.positions[symbol] = position_risk

        # Remove positions that are no longer open
        closed_symbols = set(self.positions.keys()) - current_symbols
        for symbol in closed_symbols:
            del self.positions[symbol]
            logger.debug(f"[HEAT] Removed closed position: {symbol}")

        self._last_update = datetime.now()

    def get_summary_dict(self) -> Dict:
        """Get status as dictionary for API responses"""
        total_heat = self.get_total_heat()
        heat_level = self.get_heat_level(total_heat)

        return {
            "total_heat_pct": round(total_heat, 2),
            "heat_level": heat_level.value,
            "position_count": len(self.positions),
            "correlated_heat_pct": round(self.get_correlated_heat(), 2),
            "available_heat_pct": round(max(0, self.config.max_portfolio_heat_pct - total_heat), 2),
            "position_size_multiplier": self.get_position_multiplier(heat_level),
            "can_open_new_trade": heat_level not in [HeatLevel.CRITICAL],
            "limits": {
                "max_portfolio_heat": self.config.max_portfolio_heat_pct,
                "max_per_trade": self.config.max_per_trade_pct,
                "max_correlated": self.config.max_correlated_exposure_pct,
                "max_single_asset": self.config.max_single_asset_pct
            },
            "correlation_size_adjustments": {
                "very_high_corr_multiplier": self.config.correlation_size_adjustments.get("very_high", 0.50),
                "high_corr_multiplier": self.config.correlation_size_adjustments.get("high", 0.70),
                "medium_corr_multiplier": self.config.correlation_size_adjustments.get("medium", 0.85),
                "low_corr_multiplier": self.config.correlation_size_adjustments.get("low", 1.0)
            },
            "positions": {
                symbol: {
                    "risk_pct": round(pos.risk_pct, 2),
                    "btc_correlation": pos.btc_correlation,
                    "unrealized_pnl_pct": round(pos.unrealized_pnl_pct, 2)
                }
                for symbol, pos in self.positions.items()
            },
            "last_update": self._last_update.isoformat() if self._last_update else None
        }


# Global instance
_portfolio_heat_manager: Optional[PortfolioHeatManager] = None


def get_portfolio_heat_manager(
    config: Optional[PortfolioHeatConfig] = None
) -> PortfolioHeatManager:
    """Get or create global portfolio heat manager"""
    global _portfolio_heat_manager
    if _portfolio_heat_manager is None:
        _portfolio_heat_manager = PortfolioHeatManager(config)
    return _portfolio_heat_manager


def reset_portfolio_heat_manager():
    """Reset portfolio heat manager (for testing)"""
    global _portfolio_heat_manager
    _portfolio_heat_manager = None
