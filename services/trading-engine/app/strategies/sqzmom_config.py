"""
SQZMOM Strategy Configuration
Purpose: Optimized parameters from backtesting and live paper trading validation
Date: 2025-11-20
Updated: 2026-04-25 - Aligned with validated 3-symbol config (SOL, BNB, ADA)

Paper Trading Validation (Dec 3-13, 2025 - 89+ trades):
- SOLUSDT: +$55.90 profit, 60% win rate - BEST performer
- BNBUSDT: +$44.22 profit, 64.3% win rate - 2nd best
- ADAUSDT: +$27.43 profit, 75% win rate - 3rd best (highest WR)
- DOGEUSDT: Removed - marginal performance in live trading

Excluded symbols (validated losers):
- XRPUSDT: -$39.73, 23.1% WR | ETHUSDT: -$23.65 | BTCUSDT: -$10.59

3-Symbol Focus Improvement: 3.29x P&L improvement validated by data
- Top 3 symbols: +$127.55 total, 66.4% win rate
- Bottom 4 symbols: -$88.79 total, 31.6% win rate

Optimized Parameters:
- bb_length: 20
- kc_length: 20
- min_momentum_threshold: 0.3 (reduced from 0.5)
- stop_loss_pct: 1.5% (tighter than default 2.0%)
- take_profit_pct: 3.0% (tighter than default 4.0%)
- require_squeeze_release: False (more entry opportunities)
- require_volume_confirmation: False (avoid missing signals)

Trading Mode:
- auto_trading: True (enabled for automatic trade execution)
- min_confidence: 0.5 (lowered from 0.7 for more trade opportunities)
- paper_trading: True (safety mode for simulated trades)
"""

from typing import Dict, List
from pydantic import BaseModel, Field


class SQZMOMConfig(BaseModel):
    """
    SQZMOM Strategy Configuration

    This configuration uses optimized parameters discovered through
    extensive backtesting across multiple symbols and timeframes.

    Only profitable symbols are enabled by default.
    """

    # Enabled symbols (validated by paper trading Dec 2025)
    enabled_symbols: List[str] = Field(
        default=["SOLUSDT", "BNBUSDT", "ADAUSDT"],
        description="Symbols to trade with SQZMOM strategy (validated profitable symbols)"
    )

    # Indicator parameters (optimized through backtesting)
    bb_length: int = Field(
        default=20,
        description="Bollinger Bands period (optimized)"
    )
    bb_mult: float = Field(
        default=2.0,
        description="BB standard deviation multiplier"
    )
    kc_length: int = Field(
        default=20,
        description="Keltner Channel period (optimized)"
    )
    kc_mult: float = Field(
        default=1.5,
        description="KC ATR multiplier"
    )
    use_true_range: bool = Field(
        default=True,
        description="Use True Range for Keltner Channels"
    )

    # Strategy parameters (optimized for profitability)
    min_momentum_threshold: float = Field(
        default=0.3,
        description="Minimum momentum for entry (optimized from 0.5 to 0.3)"
    )
    stop_loss_pct: float = Field(
        default=1.5,
        description="Stop loss percentage (optimized from 2.0 to 1.5)"
    )
    take_profit_pct: float = Field(
        default=3.0,
        description="Take profit percentage (optimized from 4.0 to 3.0)"
    )
    require_squeeze_release: bool = Field(
        default=False,
        description="Require squeeze to release before entry (False = more opportunities)"
    )
    require_volume_confirmation: bool = Field(
        default=False,
        description="Require volume confirmation (False = avoid missing signals)"
    )

    # Risk management
    position_size_pct: float = Field(
        default=2.0,
        ge=0.5,
        le=10.0,
        description="Position size as % of capital per trade (default: 2%)"
    )
    max_positions: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum concurrent positions across all symbols"
    )
    min_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum signal confidence to execute trade (lowered from 0.7 to 0.5 for more trades)"
    )

    # Trading mode - AUTO TRADING ENABLED
    paper_trading: bool = Field(
        default=True,
        description="Enable paper trading mode (True = simulated trades for safety)"
    )
    auto_trading: bool = Field(
        default=True,
        description="Enable automatic trade execution (True = trades execute automatically)"
    )

    # Symbol-specific overrides (validated by paper trading Dec 2025)
    symbol_config: Dict[str, Dict] = Field(
        default={
            "SOLUSDT": {
                # Best performer: +$55.90 profit, 60% WR, 15 trades
                "position_size_pct": 2.5,  # Largest position (best performer)
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3.0,
                "min_confidence": 0.45,
                "description": "Best performer: +$55.90, 60% WR, 15 trades (paper trading validated)"
            },
            "BNBUSDT": {
                # 2nd best: +$44.22 profit, 64.3% WR, 14 trades
                "position_size_pct": 2.0,  # Standard position
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3.0,
                "min_confidence": 0.50,
                "description": "2nd best: +$44.22, 64.3% WR, 14 trades (paper trading validated)"
            },
            "ADAUSDT": {
                # 3rd best: +$27.43 profit, 75% WR, 4 trades (highest win rate)
                "position_size_pct": 1.5,  # Smaller position (fewer trades, less data)
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3.0,
                "min_confidence": 0.55,  # Slightly higher confidence (fewer historical trades)
                "description": "3rd best: +$27.43, 75% WR, 4 trades (paper trading validated)"
            }
        },
        description="Symbol-specific parameter overrides validated by paper trading"
    )

    # Timeframe
    default_interval: str = Field(
        default="60",
        description="Default timeframe in minutes (60 = 1 hour)"
    )

    # Service URL
    technical_analysis_url: str = Field(
        default="http://localhost:8004",
        description="Technical Analysis Service URL"
    )

    class Config:
        """Pydantic configuration"""
        json_schema_extra = {
            "example": {
                "enabled_symbols": ["SOLUSDT", "BNBUSDT", "ADAUSDT"],
                "min_momentum_threshold": 0.3,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3.0,
                "position_size_pct": 2.0,
                "max_positions": 3,
                "paper_trading": True,
                "auto_trading": True,
                "min_confidence": 0.5
            }
        }


# Singleton configuration instance
sqzmom_config = SQZMOMConfig()
