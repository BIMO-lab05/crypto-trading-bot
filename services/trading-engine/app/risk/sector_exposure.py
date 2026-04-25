"""
Sector Exposure Manager
Purpose: Track and manage sector-based exposure for portfolio risk management

Phase 3.1: Portfolio Correlation Analysis for Enhanced Risk Management
Created: 2025-12-11
Updated: 2025-12-11

This module provides:
1. Automatic sector classification for crypto assets
2. Sector exposure tracking and limits
3. Beta calculation vs BTC/ETH
4. Sector rotation signals
5. Rebalancing recommendations

Sector Categories:
- Layer 1 (L1): BTC, ETH, SOL, ADA, AVAX, DOT, NEAR, APT, SUI
- Layer 2 (L2): ARB, OP, MATIC, IMX, STRK
- DeFi: UNI, AAVE, MKR, CRV, COMP, SNX, DYDX, GMX
- Memes: DOGE, SHIB, PEPE, FLOKI, WIF, BONK
- Infrastructure: LINK, GRT, FIL, AR, RENDER
- Exchange: BNB, FTT, CRO, OKB, KCS
- Gaming/Metaverse: AXS, SAND, MANA, GALA, ENJ, IMX
- Privacy: XMR, ZEC, DASH
- AI: TAO, FET, AGIX, OCEAN, RNDR

Key Features:
- Maximum 40% exposure in any single sector
- Automatic sector classification for new tokens
- Beta tracking vs market (BTC) and ETH
- Sector rotation detection for timing decisions
- API endpoints for sector analytics

Usage:
    manager = get_sector_exposure_manager()

    # Get sector for a symbol
    sector = manager.get_sector("BTCUSDT")

    # Calculate exposure breakdown
    exposure = manager.calculate_sector_exposure(positions)

    # Check if can add position (sector limits)
    can_add, reason = manager.can_add_position("SOLUSDT", positions)

    # Get rebalancing recommendations
    recommendations = manager.get_rebalancing_recommendations(positions)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from decimal import Decimal
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# SECTOR DEFINITIONS
# =============================================================================

class CryptoSector(Enum):
    """
    Crypto asset sector classification

    Based on primary use case and technology layer.
    Used for diversification and concentration risk management.
    """
    # Infrastructure Layers
    LAYER_1 = "layer_1"           # Base blockchain protocols (BTC, ETH, SOL)
    LAYER_2 = "layer_2"           # Scaling solutions (ARB, OP, MATIC)

    # Application Categories
    DEFI = "defi"                 # Decentralized finance protocols
    MEME = "meme"                 # Meme coins (high volatility, high correlation)
    INFRASTRUCTURE = "infra"      # Oracles, storage, indexing
    EXCHANGE = "exchange"         # Exchange tokens
    GAMING = "gaming"             # Gaming and metaverse tokens
    PRIVACY = "privacy"           # Privacy-focused coins
    AI = "ai"                     # AI and machine learning focused

    # Catch-all
    OTHER = "other"               # Unclassified tokens


# Sector classification mapping for major crypto assets
# Symbol -> CryptoSector
SECTOR_MAPPING: Dict[str, CryptoSector] = {
    # Layer 1 - Base protocols
    "BTCUSDT": CryptoSector.LAYER_1,
    "ETHUSDT": CryptoSector.LAYER_1,
    "SOLUSDT": CryptoSector.LAYER_1,
    "ADAUSDT": CryptoSector.LAYER_1,
    "AVAXUSDT": CryptoSector.LAYER_1,
    "DOTUSDT": CryptoSector.LAYER_1,
    "NEARUSDT": CryptoSector.LAYER_1,
    "APTUSDT": CryptoSector.LAYER_1,
    "SUIUSDT": CryptoSector.LAYER_1,
    "ATOMUSDT": CryptoSector.LAYER_1,
    "ALGOUSDT": CryptoSector.LAYER_1,
    "XRPUSDT": CryptoSector.LAYER_1,
    "LTCUSDT": CryptoSector.LAYER_1,
    "BCHUSDT": CryptoSector.LAYER_1,
    "ETCUSDT": CryptoSector.LAYER_1,
    "TONUSDT": CryptoSector.LAYER_1,
    "TRXUSDT": CryptoSector.LAYER_1,
    "XLMUSDT": CryptoSector.LAYER_1,
    "ICPUSDT": CryptoSector.LAYER_1,
    "HBARUSDT": CryptoSector.LAYER_1,
    "VETUSDT": CryptoSector.LAYER_1,
    "KASUSDT": CryptoSector.LAYER_1,
    "SEIUSDT": CryptoSector.LAYER_1,
    "INJUSDT": CryptoSector.LAYER_1,
    "TIAUSDT": CryptoSector.LAYER_1,

    # Layer 2 - Scaling solutions
    "ARBUSDT": CryptoSector.LAYER_2,
    "OPUSDT": CryptoSector.LAYER_2,
    "MATICUSDT": CryptoSector.LAYER_2,
    "POLUSDT": CryptoSector.LAYER_2,
    "IMXUSDT": CryptoSector.LAYER_2,
    "STRKUSDT": CryptoSector.LAYER_2,
    "METISUSDT": CryptoSector.LAYER_2,
    "MANTAUSDT": CryptoSector.LAYER_2,
    "ZKUSDT": CryptoSector.LAYER_2,
    "BLASTUSDT": CryptoSector.LAYER_2,

    # DeFi - Decentralized finance
    "UNIUSDT": CryptoSector.DEFI,
    "AAVEUSDT": CryptoSector.DEFI,
    "MKRUSDT": CryptoSector.DEFI,
    "CRVUSDT": CryptoSector.DEFI,
    "COMPUSDT": CryptoSector.DEFI,
    "SNXUSDT": CryptoSector.DEFI,
    "DYDXUSDT": CryptoSector.DEFI,
    "GMXUSDT": CryptoSector.DEFI,
    "LDOUSDT": CryptoSector.DEFI,
    "SUSHIUSDT": CryptoSector.DEFI,
    "1INCHUSDT": CryptoSector.DEFI,
    "PENDLEUSDT": CryptoSector.DEFI,
    "YFIUSDT": CryptoSector.DEFI,
    "RPLAUSDT": CryptoSector.DEFI,
    "JUPUSDT": CryptoSector.DEFI,
    "RAYUSDT": CryptoSector.DEFI,
    "ENAUSDT": CryptoSector.DEFI,

    # Meme coins - High volatility, high correlation
    "DOGEUSDT": CryptoSector.MEME,
    "SHIBUSDT": CryptoSector.MEME,
    "PEPEUSDT": CryptoSector.MEME,
    "FLOKIUSDT": CryptoSector.MEME,
    "WIFUSDT": CryptoSector.MEME,
    "BONKUSDT": CryptoSector.MEME,
    "MEMEUSDT": CryptoSector.MEME,
    "BOMEUSDT": CryptoSector.MEME,
    "PEOPLEUSDT": CryptoSector.MEME,
    "NOTUSDT": CryptoSector.MEME,

    # Infrastructure - Oracles, storage, indexing
    "LINKUSDT": CryptoSector.INFRASTRUCTURE,
    "GRTUSDT": CryptoSector.INFRASTRUCTURE,
    "FILUSDT": CryptoSector.INFRASTRUCTURE,
    "ARUSDT": CryptoSector.INFRASTRUCTURE,
    "RNDRUSDT": CryptoSector.INFRASTRUCTURE,
    "STORJUSDT": CryptoSector.INFRASTRUCTURE,
    "BANDUSDT": CryptoSector.INFRASTRUCTURE,
    "APIUSDT": CryptoSector.INFRASTRUCTURE,
    "PYTHUSDT": CryptoSector.INFRASTRUCTURE,

    # Exchange tokens
    "BNBUSDT": CryptoSector.EXCHANGE,
    "OKBUSDT": CryptoSector.EXCHANGE,
    "CROUSDT": CryptoSector.EXCHANGE,
    "GTUSDT": CryptoSector.EXCHANGE,
    "MXUSDT": CryptoSector.EXCHANGE,

    # Gaming and Metaverse
    "AXSUSDT": CryptoSector.GAMING,
    "SANDUSDT": CryptoSector.GAMING,
    "MANAUSDT": CryptoSector.GAMING,
    "GALAUSDT": CryptoSector.GAMING,
    "ENJUSDT": CryptoSector.GAMING,
    "ILLUSDT": CryptoSector.GAMING,
    "YGGUSDT": CryptoSector.GAMING,
    "MAGICUSDT": CryptoSector.GAMING,
    "PIXELUSDT": CryptoSector.GAMING,
    "PORTALUSDT": CryptoSector.GAMING,

    # Privacy coins
    "XMRUSDT": CryptoSector.PRIVACY,
    "ZECUSDT": CryptoSector.PRIVACY,
    "DASHUSDT": CryptoSector.PRIVACY,
    "SCRTUSDT": CryptoSector.PRIVACY,

    # AI and Machine Learning
    "TAOUSDT": CryptoSector.AI,
    "FETUSDT": CryptoSector.AI,
    "AGIXUSDT": CryptoSector.AI,
    "OCEANUSDT": CryptoSector.AI,
    "RNDR": CryptoSector.AI,  # Also infrastructure
    "NMRUSDT": CryptoSector.AI,
    "AIUSDT": CryptoSector.AI,
    "ARKMUSDT": CryptoSector.AI,
    "WLDUSDT": CryptoSector.AI,
}


# Sector characteristics - risk profiles
SECTOR_CHARACTERISTICS: Dict[str, Dict[str, Any]] = {
    "layer_1": {
        "name": "Layer 1 Protocols",
        "description": "Base blockchain infrastructure - most established",
        "volatility_factor": 1.0,      # Base volatility
        "correlation_to_btc": 0.85,    # High correlation during stress
        "max_exposure_pct": 50.0,      # Can have more in L1s
        "risk_weight": 0.8,            # Lower risk weight
    },
    "layer_2": {
        "name": "Layer 2 Scaling",
        "description": "Ethereum scaling solutions",
        "volatility_factor": 1.3,      # Higher volatility than L1
        "correlation_to_btc": 0.75,
        "max_exposure_pct": 40.0,
        "risk_weight": 1.0,
    },
    "defi": {
        "name": "DeFi Protocols",
        "description": "Decentralized finance applications",
        "volatility_factor": 1.4,
        "correlation_to_btc": 0.70,
        "max_exposure_pct": 35.0,
        "risk_weight": 1.2,
    },
    "meme": {
        "name": "Meme Coins",
        "description": "High risk meme tokens - extremely volatile",
        "volatility_factor": 2.5,      # Very high volatility
        "correlation_to_btc": 0.60,    # Can decouple
        "max_exposure_pct": 15.0,      # Strict limit for memes
        "risk_weight": 2.0,            # High risk weight
    },
    "infra": {
        "name": "Infrastructure",
        "description": "Blockchain infrastructure services",
        "volatility_factor": 1.2,
        "correlation_to_btc": 0.70,
        "max_exposure_pct": 30.0,
        "risk_weight": 1.0,
    },
    "exchange": {
        "name": "Exchange Tokens",
        "description": "Centralized exchange utility tokens",
        "volatility_factor": 1.1,
        "correlation_to_btc": 0.65,
        "max_exposure_pct": 25.0,
        "risk_weight": 1.1,
    },
    "gaming": {
        "name": "Gaming/Metaverse",
        "description": "Gaming and metaverse tokens",
        "volatility_factor": 1.8,
        "correlation_to_btc": 0.55,
        "max_exposure_pct": 25.0,
        "risk_weight": 1.5,
    },
    "privacy": {
        "name": "Privacy Coins",
        "description": "Privacy-focused cryptocurrencies",
        "volatility_factor": 1.3,
        "correlation_to_btc": 0.50,
        "max_exposure_pct": 20.0,
        "risk_weight": 1.3,
    },
    "ai": {
        "name": "AI Tokens",
        "description": "AI and machine learning focused",
        "volatility_factor": 2.0,
        "correlation_to_btc": 0.55,
        "max_exposure_pct": 30.0,
        "risk_weight": 1.6,
    },
    "other": {
        "name": "Other",
        "description": "Unclassified tokens",
        "volatility_factor": 1.5,
        "correlation_to_btc": 0.60,
        "max_exposure_pct": 20.0,
        "risk_weight": 1.3,
    },
}


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class SectorExposureConfig:
    """
    Configuration for sector exposure management

    Research-based defaults (2025-12):
    - Max single sector: 40% (diversification requirement)
    - Meme coin limit: 15% (high risk containment)
    - Layer 1 can go higher: 50% (more established)
    """
    # Default max exposure per sector (can be overridden per sector)
    default_max_sector_pct: float = 40.0

    # Specific sector limits (overrides default)
    sector_limits: Dict[str, float] = field(default_factory=lambda: {
        "layer_1": 50.0,    # Can have more in L1s
        "layer_2": 40.0,
        "defi": 35.0,
        "meme": 15.0,       # Strict limit on memes
        "infra": 30.0,
        "exchange": 25.0,
        "gaming": 25.0,
        "privacy": 20.0,
        "ai": 30.0,
        "other": 20.0,
    })

    # Minimum number of sectors for diversification
    min_sectors_for_diversification: int = 3

    # Beta calculation settings
    beta_lookback_days: int = 30
    beta_market_symbol: str = "BTCUSDT"

    # Sector rotation detection
    rotation_threshold: float = 0.15  # 15% relative strength change
    rotation_lookback_days: int = 7

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return asdict(self)


@dataclass
class SectorPosition:
    """
    Position data for sector calculation

    Lightweight representation of a position for sector analysis.
    """
    symbol: str                    # Trading symbol (e.g., "BTCUSDT")
    position_value: float          # Current USD value of position
    risk_pct: float               # Risk as % of portfolio
    entry_price: float            # Entry price
    current_price: float          # Current price
    sector: CryptoSector          # Assigned sector
    unrealized_pnl_pct: float = 0.0  # Unrealized P&L percentage


@dataclass
class SectorExposure:
    """
    Exposure breakdown by sector

    Contains detailed analysis of portfolio sector concentration.
    """
    sector: CryptoSector          # Sector enum
    sector_name: str              # Human-readable name
    exposure_pct: float           # Exposure as % of portfolio
    exposure_value: float         # USD value in this sector
    position_count: int           # Number of positions in sector
    positions: List[str]          # List of symbols in sector
    max_allowed_pct: float        # Maximum allowed exposure
    is_over_limit: bool           # Whether exposure exceeds limit
    headroom_pct: float           # Available capacity (can be negative if over)
    weighted_beta: float = 1.0    # Weighted beta to market
    avg_unrealized_pnl: float = 0.0  # Average unrealized P&L

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "sector": self.sector.value,
            "sector_name": self.sector_name,
            "exposure_pct": round(self.exposure_pct, 2),
            "exposure_value": round(self.exposure_value, 2),
            "position_count": self.position_count,
            "positions": self.positions,
            "max_allowed_pct": round(self.max_allowed_pct, 2),
            "is_over_limit": self.is_over_limit,
            "headroom_pct": round(self.headroom_pct, 2),
            "weighted_beta": round(self.weighted_beta, 3),
            "avg_unrealized_pnl": round(self.avg_unrealized_pnl, 2),
        }


@dataclass
class SectorRotationSignal:
    """
    Signal for sector rotation (relative strength changes)

    Used to detect when capital is flowing between sectors.
    """
    sector: CryptoSector
    sector_name: str
    relative_strength: float      # Current relative strength vs market
    strength_change: float        # Change in relative strength
    signal: str                   # "INFLOW", "OUTFLOW", or "NEUTRAL"
    confidence: float             # Signal confidence (0-1)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "sector": self.sector.value,
            "sector_name": self.sector_name,
            "relative_strength": round(self.relative_strength, 4),
            "strength_change": round(self.strength_change, 4),
            "signal": self.signal,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SectorAnalysisResult:
    """
    Complete sector analysis result

    Comprehensive breakdown of portfolio sector exposure with recommendations.
    """
    total_portfolio_value: float
    sector_count: int
    diversification_rating: str   # "EXCELLENT", "GOOD", "MODERATE", "POOR", "CONCENTRATED"
    sector_exposures: List[SectorExposure]
    over_limit_sectors: List[str]
    recommendations: List[str]
    rotation_signals: List[SectorRotationSignal] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_portfolio_value": round(self.total_portfolio_value, 2),
            "sector_count": self.sector_count,
            "diversification_rating": self.diversification_rating,
            "sector_exposures": [e.to_dict() for e in self.sector_exposures],
            "over_limit_sectors": self.over_limit_sectors,
            "recommendations": self.recommendations,
            "rotation_signals": [s.to_dict() for s in self.rotation_signals],
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# SECTOR EXPOSURE MANAGER
# =============================================================================

class SectorExposureManager:
    """
    Sector Exposure Manager

    Tracks and manages sector-based exposure for portfolio risk management.

    Key Features:
    - Automatic sector classification for crypto assets
    - Sector exposure tracking with configurable limits
    - Beta calculation vs BTC/ETH
    - Sector rotation signal detection
    - Rebalancing recommendations

    Usage:
        manager = SectorExposureManager()

        # Get sector for a symbol
        sector = manager.get_sector("BTCUSDT")

        # Calculate full exposure analysis
        analysis = manager.calculate_sector_exposure(positions, portfolio_value)

        # Check if can add position based on sector limits
        can_add, reason = manager.can_add_position("SOLUSDT", positions, portfolio_value)
    """

    def __init__(self, config: Optional[SectorExposureConfig] = None):
        """
        Initialize Sector Exposure Manager

        Args:
            config: Sector exposure configuration (uses defaults if not provided)
        """
        self.config = config or SectorExposureConfig()

        # Custom sector mappings (can be updated dynamically)
        self._custom_mappings: Dict[str, CryptoSector] = {}

        # Price history for beta calculations
        self._price_history: Dict[str, List[float]] = {}

        # Sector performance history for rotation detection
        self._sector_performance: Dict[str, List[Tuple[datetime, float]]] = {}

        logger.info(
            f"SectorExposureManager initialized with config: "
            f"default_max={self.config.default_max_sector_pct}%, "
            f"meme_limit={self.config.sector_limits.get('meme', 15)}%"
        )

    # =========================================================================
    # SECTOR CLASSIFICATION
    # =========================================================================

    def get_sector(self, symbol: str) -> CryptoSector:
        """
        Get sector classification for a symbol

        First checks custom mappings, then built-in mappings, then defaults to OTHER.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")

        Returns:
            CryptoSector enum value
        """
        # Normalize symbol (uppercase, ensure USDT suffix)
        symbol = symbol.upper()
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"

        # Check custom mappings first
        if symbol in self._custom_mappings:
            return self._custom_mappings[symbol]

        # Check built-in mappings
        if symbol in SECTOR_MAPPING:
            return SECTOR_MAPPING[symbol]

        # Default to OTHER
        logger.debug(f"Symbol {symbol} not in sector mapping, defaulting to OTHER")
        return CryptoSector.OTHER

    def set_sector(self, symbol: str, sector: CryptoSector):
        """
        Set custom sector classification for a symbol

        Args:
            symbol: Trading symbol
            sector: CryptoSector to assign
        """
        symbol = symbol.upper()
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"

        self._custom_mappings[symbol] = sector
        logger.info(f"Custom sector mapping set: {symbol} -> {sector.value}")

    def get_sector_characteristics(self, sector: CryptoSector) -> Dict[str, Any]:
        """
        Get characteristics for a sector

        Args:
            sector: CryptoSector enum

        Returns:
            Dictionary with sector characteristics
        """
        return SECTOR_CHARACTERISTICS.get(
            sector.value,
            SECTOR_CHARACTERISTICS["other"]
        )

    def get_sector_max_exposure(self, sector: CryptoSector) -> float:
        """
        Get maximum allowed exposure for a sector

        Args:
            sector: CryptoSector enum

        Returns:
            Maximum exposure percentage
        """
        # Check config sector limits first
        if sector.value in self.config.sector_limits:
            return self.config.sector_limits[sector.value]

        # Fall back to sector characteristics
        chars = self.get_sector_characteristics(sector)
        if "max_exposure_pct" in chars:
            return chars["max_exposure_pct"]

        # Default
        return self.config.default_max_sector_pct

    def get_all_sectors(self) -> List[Dict[str, Any]]:
        """
        Get list of all sectors with their characteristics

        Returns:
            List of sector information dictionaries
        """
        sectors = []
        for sector in CryptoSector:
            chars = self.get_sector_characteristics(sector)
            sectors.append({
                "sector": sector.value,
                "name": chars.get("name", sector.value),
                "description": chars.get("description", ""),
                "max_exposure_pct": self.get_sector_max_exposure(sector),
                "volatility_factor": chars.get("volatility_factor", 1.0),
                "risk_weight": chars.get("risk_weight", 1.0),
            })
        return sectors

    # =========================================================================
    # EXPOSURE CALCULATION
    # =========================================================================

    def calculate_sector_exposure(
        self,
        positions: List[SectorPosition],
        portfolio_value: float
    ) -> SectorAnalysisResult:
        """
        Calculate comprehensive sector exposure breakdown

        Args:
            positions: List of SectorPosition objects
            portfolio_value: Total portfolio value in USD

        Returns:
            SectorAnalysisResult with detailed breakdown
        """
        if portfolio_value <= 0:
            return SectorAnalysisResult(
                total_portfolio_value=0,
                sector_count=0,
                diversification_rating="N/A",
                sector_exposures=[],
                over_limit_sectors=[],
                recommendations=["No portfolio value to analyze"]
            )

        # Group positions by sector
        sector_positions: Dict[CryptoSector, List[SectorPosition]] = {}

        for pos in positions:
            sector = pos.sector if pos.sector else self.get_sector(pos.symbol)

            if sector not in sector_positions:
                sector_positions[sector] = []
            sector_positions[sector].append(pos)

        # Calculate exposure for each sector
        sector_exposures: List[SectorExposure] = []
        over_limit_sectors: List[str] = []

        for sector in CryptoSector:
            positions_in_sector = sector_positions.get(sector, [])
            chars = self.get_sector_characteristics(sector)
            max_allowed = self.get_sector_max_exposure(sector)

            if positions_in_sector:
                # Calculate exposure
                total_value = sum(p.position_value for p in positions_in_sector)
                exposure_pct = (total_value / portfolio_value) * 100

                # Calculate weighted beta
                total_beta_weight = 0
                beta_weighted_sum = 0
                for p in positions_in_sector:
                    weight = p.position_value
                    beta = chars.get("correlation_to_btc", 1.0)  # Use correlation as proxy
                    beta_weighted_sum += beta * weight
                    total_beta_weight += weight

                weighted_beta = beta_weighted_sum / total_beta_weight if total_beta_weight > 0 else 1.0

                # Calculate average unrealized P&L
                avg_pnl = np.mean([p.unrealized_pnl_pct for p in positions_in_sector])

                is_over = exposure_pct > max_allowed
                if is_over:
                    over_limit_sectors.append(sector.value)

                sector_exposure = SectorExposure(
                    sector=sector,
                    sector_name=chars.get("name", sector.value),
                    exposure_pct=exposure_pct,
                    exposure_value=total_value,
                    position_count=len(positions_in_sector),
                    positions=[p.symbol for p in positions_in_sector],
                    max_allowed_pct=max_allowed,
                    is_over_limit=is_over,
                    headroom_pct=max_allowed - exposure_pct,
                    weighted_beta=weighted_beta,
                    avg_unrealized_pnl=avg_pnl,
                )
                sector_exposures.append(sector_exposure)

        # Sort by exposure (highest first)
        sector_exposures.sort(key=lambda x: x.exposure_pct, reverse=True)

        # Count sectors with positions
        sector_count = len([e for e in sector_exposures if e.position_count > 0])

        # Determine diversification rating
        diversification_rating = self._calculate_diversification_rating(
            sector_exposures,
            sector_count,
            over_limit_sectors
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            sector_exposures,
            sector_count,
            over_limit_sectors
        )

        return SectorAnalysisResult(
            total_portfolio_value=portfolio_value,
            sector_count=sector_count,
            diversification_rating=diversification_rating,
            sector_exposures=sector_exposures,
            over_limit_sectors=over_limit_sectors,
            recommendations=recommendations,
        )

    def _calculate_diversification_rating(
        self,
        exposures: List[SectorExposure],
        sector_count: int,
        over_limit: List[str]
    ) -> str:
        """Calculate diversification rating based on sector distribution"""
        # Check for over-limit sectors
        if len(over_limit) > 0:
            return "CONCENTRATED"

        # Check sector count
        if sector_count < self.config.min_sectors_for_diversification:
            return "POOR"

        # Calculate concentration (Herfindahl-like)
        total_exposure = sum(e.exposure_pct for e in exposures if e.position_count > 0)
        if total_exposure == 0:
            return "N/A"

        # Calculate sum of squared shares
        hhi = sum(
            (e.exposure_pct / total_exposure) ** 2
            for e in exposures
            if e.position_count > 0
        )

        # HHI interpretation:
        # < 0.15: Excellent diversification
        # 0.15-0.25: Good diversification
        # 0.25-0.40: Moderate concentration
        # > 0.40: High concentration

        if hhi < 0.15:
            return "EXCELLENT"
        elif hhi < 0.25:
            return "GOOD"
        elif hhi < 0.40:
            return "MODERATE"
        else:
            return "POOR"

    def _generate_recommendations(
        self,
        exposures: List[SectorExposure],
        sector_count: int,
        over_limit: List[str]
    ) -> List[str]:
        """Generate actionable recommendations based on sector analysis"""
        recommendations = []

        # Over-limit warnings
        for sector in over_limit:
            exp = next((e for e in exposures if e.sector.value == sector), None)
            if exp:
                over_by = exp.exposure_pct - exp.max_allowed_pct
                recommendations.append(
                    f"REDUCE: {exp.sector_name} exposure ({exp.exposure_pct:.1f}%) "
                    f"exceeds limit ({exp.max_allowed_pct:.1f}%) by {over_by:.1f}%"
                )

        # Diversification recommendation
        if sector_count < self.config.min_sectors_for_diversification:
            recommendations.append(
                f"DIVERSIFY: Portfolio only has {sector_count} sectors. "
                f"Consider adding positions in {self.config.min_sectors_for_diversification - sector_count} "
                f"additional sectors."
            )

        # Meme concentration warning
        meme_exposure = next(
            (e for e in exposures if e.sector == CryptoSector.MEME),
            None
        )
        if meme_exposure and meme_exposure.exposure_pct > 10:
            recommendations.append(
                f"CAUTION: High meme coin exposure ({meme_exposure.exposure_pct:.1f}%). "
                f"These are highly volatile and correlated during market stress."
            )

        # Sector with most headroom
        sectors_with_headroom = [
            e for e in exposures
            if e.headroom_pct > 10 and e.position_count == 0
        ]
        if sectors_with_headroom:
            best = max(sectors_with_headroom, key=lambda x: x.headroom_pct)
            recommendations.append(
                f"OPPORTUNITY: {best.sector_name} has {best.headroom_pct:.1f}% capacity "
                f"and no current positions."
            )

        # Good diversification message
        if not recommendations:
            recommendations.append(
                "Portfolio sector allocation is well-balanced. No immediate actions needed."
            )

        return recommendations

    # =========================================================================
    # POSITION CHECKS
    # =========================================================================

    def can_add_position(
        self,
        symbol: str,
        current_positions: List[SectorPosition],
        portfolio_value: float,
        proposed_value: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new position can be added based on sector limits

        Args:
            symbol: Symbol of proposed new position
            current_positions: List of current positions
            portfolio_value: Current portfolio value
            proposed_value: Value of proposed new position

        Returns:
            Tuple of (can_add, reason_if_blocked)
        """
        if portfolio_value <= 0:
            return True, None

        # Get sector of new position
        sector = self.get_sector(symbol)
        max_allowed = self.get_sector_max_exposure(sector)

        # Calculate current exposure in this sector
        current_sector_value = sum(
            p.position_value
            for p in current_positions
            if self.get_sector(p.symbol) == sector
        )

        # Calculate new total exposure
        new_total = current_sector_value + proposed_value
        new_exposure_pct = (new_total / portfolio_value) * 100

        if new_exposure_pct > max_allowed:
            chars = self.get_sector_characteristics(sector)
            current_pct = (current_sector_value / portfolio_value) * 100
            return False, (
                f"Cannot add {symbol}: Would exceed {chars.get('name', sector.value)} "
                f"sector limit. Current: {current_pct:.1f}%, After: {new_exposure_pct:.1f}%, "
                f"Max: {max_allowed:.1f}%"
            )

        return True, None

    def get_position_size_adjustment(
        self,
        symbol: str,
        current_positions: List[SectorPosition],
        portfolio_value: float
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Get position size adjustment based on sector exposure

        Returns a multiplier to reduce position size if sector is approaching limits.

        Args:
            symbol: Symbol of proposed position
            current_positions: List of current positions
            portfolio_value: Current portfolio value

        Returns:
            Tuple of (multiplier, details)
        """
        if portfolio_value <= 0:
            return 1.0, {"reason": "No portfolio value"}

        sector = self.get_sector(symbol)
        max_allowed = self.get_sector_max_exposure(sector)
        chars = self.get_sector_characteristics(sector)

        # Calculate current exposure
        current_sector_value = sum(
            p.position_value
            for p in current_positions
            if self.get_sector(p.symbol) == sector
        )
        current_pct = (current_sector_value / portfolio_value) * 100

        # Calculate headroom
        headroom = max_allowed - current_pct

        # Determine multiplier based on headroom
        # Full headroom (>15%): 1.0 multiplier
        # 10-15% headroom: 0.85 multiplier
        # 5-10% headroom: 0.7 multiplier
        # 0-5% headroom: 0.5 multiplier
        # No headroom: 0.0 (blocked)

        if headroom <= 0:
            multiplier = 0.0
        elif headroom <= 5:
            multiplier = 0.5
        elif headroom <= 10:
            multiplier = 0.7
        elif headroom <= 15:
            multiplier = 0.85
        else:
            multiplier = 1.0

        # Also apply sector risk weight
        risk_weight = chars.get("risk_weight", 1.0)
        if risk_weight > 1.2:  # High risk sectors get additional reduction
            multiplier *= (1.0 / risk_weight)

        multiplier = max(0.0, min(1.0, multiplier))

        details = {
            "sector": sector.value,
            "sector_name": chars.get("name", sector.value),
            "current_exposure_pct": round(current_pct, 2),
            "max_allowed_pct": max_allowed,
            "headroom_pct": round(headroom, 2),
            "risk_weight": risk_weight,
            "multiplier": round(multiplier, 2),
        }

        return multiplier, details

    # =========================================================================
    # BETA CALCULATION
    # =========================================================================

    def update_price_history(
        self,
        price_data: Dict[str, List[float]]
    ):
        """
        Update price history for beta calculations

        Args:
            price_data: Dictionary mapping symbol to price list
        """
        for symbol, prices in price_data.items():
            if symbol not in self._price_history:
                self._price_history[symbol] = []

            self._price_history[symbol].extend(prices)

            # Keep only lookback period
            max_history = self.config.beta_lookback_days * 24  # Hourly data
            if len(self._price_history[symbol]) > max_history:
                self._price_history[symbol] = self._price_history[symbol][-max_history:]

    def calculate_beta(
        self,
        symbol: str,
        market_symbol: Optional[str] = None
    ) -> Optional[float]:
        """
        Calculate beta of a symbol relative to market (BTC)

        Beta measures systematic risk:
        - Beta > 1: More volatile than market
        - Beta = 1: Same as market
        - Beta < 1: Less volatile than market
        - Beta < 0: Negative correlation (rare)

        Args:
            symbol: Symbol to calculate beta for
            market_symbol: Market reference symbol (default: BTCUSDT)

        Returns:
            Beta coefficient or None if insufficient data
        """
        market_symbol = market_symbol or self.config.beta_market_symbol

        if symbol not in self._price_history or market_symbol not in self._price_history:
            # Use default from sector characteristics
            sector = self.get_sector(symbol)
            chars = self.get_sector_characteristics(sector)
            return chars.get("correlation_to_btc", 1.0)

        symbol_prices = self._price_history[symbol]
        market_prices = self._price_history[market_symbol]

        # Need at least 20 data points
        min_len = min(len(symbol_prices), len(market_prices))
        if min_len < 20:
            sector = self.get_sector(symbol)
            chars = self.get_sector_characteristics(sector)
            return chars.get("correlation_to_btc", 1.0)

        # Calculate returns
        symbol_returns = np.diff(symbol_prices[-min_len:]) / np.array(symbol_prices[-min_len:-1])
        market_returns = np.diff(market_prices[-min_len:]) / np.array(market_prices[-min_len:-1])

        # Calculate beta = Cov(r_asset, r_market) / Var(r_market)
        try:
            covariance = np.cov(symbol_returns, market_returns)[0, 1]
            market_variance = np.var(market_returns)

            if market_variance == 0:
                return 1.0

            beta = covariance / market_variance
            return float(beta)
        except Exception as e:
            logger.error(f"Error calculating beta for {symbol}: {e}")
            return 1.0

    def calculate_sector_betas(self) -> Dict[str, float]:
        """
        Calculate beta for each sector

        Returns:
            Dictionary mapping sector name to beta
        """
        sector_betas = {}

        for sector in CryptoSector:
            # Get symbols in this sector
            symbols = [
                sym for sym, sec in SECTOR_MAPPING.items()
                if sec == sector and sym in self._price_history
            ]

            if not symbols:
                chars = self.get_sector_characteristics(sector)
                sector_betas[sector.value] = chars.get("correlation_to_btc", 1.0)
                continue

            # Calculate average beta for sector
            betas = [self.calculate_beta(sym) for sym in symbols]
            betas = [b for b in betas if b is not None]

            if betas:
                sector_betas[sector.value] = np.mean(betas)
            else:
                chars = self.get_sector_characteristics(sector)
                sector_betas[sector.value] = chars.get("correlation_to_btc", 1.0)

        return sector_betas

    # =========================================================================
    # SECTOR ROTATION DETECTION
    # =========================================================================

    def update_sector_performance(
        self,
        sector_returns: Dict[str, float]
    ):
        """
        Update sector performance history for rotation detection

        Args:
            sector_returns: Dictionary mapping sector name to return percentage
        """
        timestamp = datetime.now(timezone.utc)

        for sector_name, return_pct in sector_returns.items():
            if sector_name not in self._sector_performance:
                self._sector_performance[sector_name] = []

            self._sector_performance[sector_name].append((timestamp, return_pct))

            # Keep only lookback period
            cutoff = timestamp - timedelta(days=self.config.rotation_lookback_days)
            self._sector_performance[sector_name] = [
                (t, r) for t, r in self._sector_performance[sector_name]
                if t >= cutoff
            ]

    def detect_sector_rotation(self) -> List[SectorRotationSignal]:
        """
        Detect sector rotation signals

        Identifies sectors with significant relative strength changes
        indicating capital flow between sectors.

        Returns:
            List of SectorRotationSignal objects
        """
        signals = []

        if not self._sector_performance:
            return signals

        # Calculate cumulative returns for each sector
        sector_cumulative = {}
        for sector_name, history in self._sector_performance.items():
            if len(history) >= 2:
                cumulative = sum(r for _, r in history)
                sector_cumulative[sector_name] = cumulative

        if not sector_cumulative:
            return signals

        # Calculate market average
        market_avg = np.mean(list(sector_cumulative.values()))

        # Generate signals
        for sector_name, cumulative in sector_cumulative.items():
            relative_strength = cumulative - market_avg

            # Determine signal based on threshold
            if abs(relative_strength) < self.config.rotation_threshold:
                signal_type = "NEUTRAL"
                confidence = 0.3
            elif relative_strength > 0:
                signal_type = "INFLOW"
                confidence = min(0.9, abs(relative_strength) / 0.3)
            else:
                signal_type = "OUTFLOW"
                confidence = min(0.9, abs(relative_strength) / 0.3)

            # Get sector enum
            try:
                sector = CryptoSector(sector_name)
            except ValueError:
                sector = CryptoSector.OTHER

            chars = self.get_sector_characteristics(sector)

            signal = SectorRotationSignal(
                sector=sector,
                sector_name=chars.get("name", sector_name),
                relative_strength=relative_strength,
                strength_change=relative_strength,  # Simplified
                signal=signal_type,
                confidence=confidence,
            )
            signals.append(signal)

        # Sort by absolute strength change
        signals.sort(key=lambda s: abs(s.relative_strength), reverse=True)

        return signals

    # =========================================================================
    # STATUS AND SUMMARY
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get manager status summary"""
        return {
            "sectors_tracked": len(CryptoSector),
            "custom_mappings": len(self._custom_mappings),
            "price_history_symbols": len(self._price_history),
            "sector_performance_tracked": len(self._sector_performance),
            "config": self.config.to_dict(),
        }

    def get_summary(
        self,
        positions: List[SectorPosition],
        portfolio_value: float
    ) -> Dict[str, Any]:
        """
        Get quick summary of sector exposure

        Args:
            positions: List of positions
            portfolio_value: Total portfolio value

        Returns:
            Summary dictionary for API responses
        """
        analysis = self.calculate_sector_exposure(positions, portfolio_value)

        return {
            "total_value": round(portfolio_value, 2),
            "sector_count": analysis.sector_count,
            "rating": analysis.diversification_rating,
            "over_limit_count": len(analysis.over_limit_sectors),
            "top_sectors": [
                {
                    "sector": e.sector.value,
                    "exposure_pct": round(e.exposure_pct, 1),
                    "is_over": e.is_over_limit,
                }
                for e in analysis.sector_exposures[:5]
                if e.position_count > 0
            ],
            "recommendations_count": len(analysis.recommendations),
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_sector_exposure_manager: Optional[SectorExposureManager] = None


def get_sector_exposure_manager(
    config: Optional[SectorExposureConfig] = None
) -> SectorExposureManager:
    """
    Get or create the global SectorExposureManager instance

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        SectorExposureManager singleton instance
    """
    global _sector_exposure_manager
    if _sector_exposure_manager is None:
        _sector_exposure_manager = SectorExposureManager(config)
    return _sector_exposure_manager


def reset_sector_exposure_manager():
    """Reset the global SectorExposureManager instance (for testing)"""
    global _sector_exposure_manager
    _sector_exposure_manager = None


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    def test_sector_manager():
        """Test the sector exposure manager"""
        manager = get_sector_exposure_manager()

        print("\n=== All Sectors ===")
        for sector in manager.get_all_sectors():
            print(f"  {sector['sector']}: {sector['name']} (max: {sector['max_exposure_pct']}%)")

        print("\n=== Symbol Classifications ===")
        test_symbols = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "UNIUSDT", "ARBUSDT", "UNKNOWN"]
        for symbol in test_symbols:
            sector = manager.get_sector(symbol)
            chars = manager.get_sector_characteristics(sector)
            print(f"  {symbol}: {sector.value} ({chars.get('name', 'Unknown')})")

        print("\n=== Portfolio Analysis ===")
        # Create test positions
        positions = [
            SectorPosition(
                symbol="BTCUSDT", position_value=50000, risk_pct=5,
                entry_price=100000, current_price=102000,
                sector=CryptoSector.LAYER_1, unrealized_pnl_pct=2.0
            ),
            SectorPosition(
                symbol="ETHUSDT", position_value=30000, risk_pct=3,
                entry_price=3500, current_price=3600,
                sector=CryptoSector.LAYER_1, unrealized_pnl_pct=2.86
            ),
            SectorPosition(
                symbol="ARBUSDT", position_value=10000, risk_pct=1.5,
                entry_price=1.2, current_price=1.25,
                sector=CryptoSector.LAYER_2, unrealized_pnl_pct=4.17
            ),
            SectorPosition(
                symbol="UNIUSDT", position_value=8000, risk_pct=1,
                entry_price=10, current_price=11,
                sector=CryptoSector.DEFI, unrealized_pnl_pct=10.0
            ),
            SectorPosition(
                symbol="DOGEUSDT", position_value=2000, risk_pct=0.5,
                entry_price=0.1, current_price=0.095,
                sector=CryptoSector.MEME, unrealized_pnl_pct=-5.0
            ),
        ]

        portfolio_value = 100000
        analysis = manager.calculate_sector_exposure(positions, portfolio_value)

        print(f"  Total Value: ${analysis.total_portfolio_value:,.2f}")
        print(f"  Sector Count: {analysis.sector_count}")
        print(f"  Rating: {analysis.diversification_rating}")

        print("\n  Sector Breakdown:")
        for exp in analysis.sector_exposures:
            if exp.position_count > 0:
                status = " [OVER]" if exp.is_over_limit else ""
                print(
                    f"    {exp.sector_name}: {exp.exposure_pct:.1f}% "
                    f"(max: {exp.max_allowed_pct}%, headroom: {exp.headroom_pct:.1f}%){status}"
                )

        print("\n  Recommendations:")
        for rec in analysis.recommendations:
            print(f"    - {rec}")

        print("\n=== Position Check ===")
        # Check if can add more DOGE
        can_add, reason = manager.can_add_position(
            "PEPEUSDT",
            positions,
            portfolio_value,
            proposed_value=15000
        )
        print(f"  Can add $15,000 PEPE: {can_add}")
        if reason:
            print(f"  Reason: {reason}")

        # Get size adjustment
        multiplier, details = manager.get_position_size_adjustment(
            "PEPEUSDT",
            positions,
            portfolio_value
        )
        print(f"\n  Size adjustment for PEPE: {multiplier:.0%}")
        print(f"  Details: {details}")

    test_sector_manager()
