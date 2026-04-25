"""
Strategy Registry
==================
Purpose: Central registry for managing strategy definitions and metadata

The Strategy Registry provides:
1. Strategy registration and versioning
2. Strategy metadata management
3. Strategy lookup and discovery
4. Configuration validation
5. Strategy lifecycle management

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, List, Optional, Any, Callable, Type
from dataclasses import dataclass
import json
import hashlib

from app.orchestration.models import (
    StrategyMetadata,
    StrategyConfig,
    StrategyType,
    RiskProfile,
    Timeframe,
    StrategyStatus,
    RegisterStrategyRequest,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# STRATEGY VERSION MANAGEMENT
# =============================================================================

@dataclass
class StrategyVersion:
    """
    Tracks version history for a strategy

    Enables:
    - Rollback to previous versions
    - A/B testing between versions
    - Audit trail of changes
    """
    version: str
    metadata: StrategyMetadata
    config: StrategyConfig
    created_at: datetime
    created_by: str
    change_notes: str
    checksum: str  # Hash of config for integrity verification

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "change_notes": self.change_notes,
            "checksum": self.checksum,
        }


# =============================================================================
# STRATEGY FACTORY
# =============================================================================

class StrategyFactory:
    """
    Factory for creating strategy instances

    Maps strategy types to their implementation classes
    and handles instantiation with proper configuration.
    """

    def __init__(self):
        """Initialize factory with empty registry"""
        # Map strategy IDs to their class types
        self._strategy_classes: Dict[str, Type] = {}

        # Map strategy IDs to factory functions
        self._factory_functions: Dict[str, Callable] = {}

        logger.info("StrategyFactory initialized")

    def register_class(self, strategy_id: str, strategy_class: Type) -> None:
        """
        Register a strategy class

        Args:
            strategy_id: Unique identifier for strategy
            strategy_class: Class to instantiate
        """
        self._strategy_classes[strategy_id] = strategy_class
        logger.info(f"Registered strategy class: {strategy_id} -> {strategy_class.__name__}")

    def register_factory(self, strategy_id: str, factory_func: Callable) -> None:
        """
        Register a factory function for creating strategy instances

        Args:
            strategy_id: Unique identifier
            factory_func: Function that returns strategy instance
        """
        self._factory_functions[strategy_id] = factory_func
        logger.info(f"Registered strategy factory: {strategy_id}")

    def create_instance(self, strategy_id: str, config: Optional[Dict] = None) -> Any:
        """
        Create a strategy instance

        Args:
            strategy_id: Strategy identifier
            config: Optional configuration overrides

        Returns:
            Strategy instance
        """
        # Try factory function first
        if strategy_id in self._factory_functions:
            return self._factory_functions[strategy_id](config)

        # Try class instantiation
        if strategy_id in self._strategy_classes:
            strategy_class = self._strategy_classes[strategy_id]
            if config:
                return strategy_class(**config)
            return strategy_class()

        raise ValueError(f"Unknown strategy: {strategy_id}")

    def get_registered_strategies(self) -> List[str]:
        """Get list of registered strategy IDs"""
        return list(set(self._strategy_classes.keys()) | set(self._factory_functions.keys()))


# =============================================================================
# STRATEGY REGISTRY
# =============================================================================

class StrategyRegistry:
    """
    Central Registry for Strategy Management

    The Strategy Registry serves as the single source of truth for:
    - All registered strategies and their metadata
    - Strategy versions and configurations
    - Strategy status and availability

    Features:
    1. Strategy Registration:
       - Register new strategies with metadata
       - Validate strategy configurations
       - Assign unique identifiers

    2. Version Management:
       - Track version history
       - Support rollback to previous versions
       - Compute checksums for integrity

    3. Strategy Discovery:
       - Find strategies by type, symbol, timeframe
       - Filter by risk profile or status
       - Get recommended strategies for conditions

    4. Configuration Validation:
       - Validate strategy parameters
       - Check symbol support
       - Verify required dependencies

    Usage:
        registry = StrategyRegistry()

        # Register a strategy
        metadata = StrategyMetadata(
            strategy_id="trend_following_v1",
            name="Trend Following Strategy",
            strategy_type=StrategyType.TREND_FOLLOWING,
            supported_symbols=["BTCUSDT", "ETHUSDT"]
        )
        registry.register_strategy(metadata)

        # Find strategies
        trend_strategies = registry.find_strategies_by_type(StrategyType.TREND_FOLLOWING)
        btc_strategies = registry.find_strategies_by_symbol("BTCUSDT")

        # Get strategy
        strategy = registry.get_strategy("trend_following_v1")
    """

    def __init__(self):
        """Initialize the strategy registry"""
        # Thread safety lock
        self._lock = RLock()

        # Primary storage
        self._strategies: Dict[str, StrategyMetadata] = {}
        self._configs: Dict[str, StrategyConfig] = {}

        # Version history
        self._versions: Dict[str, List[StrategyVersion]] = {}

        # Indexes for fast lookup
        self._by_type: Dict[StrategyType, set] = {t: set() for t in StrategyType}
        self._by_symbol: Dict[str, set] = {}
        self._by_timeframe: Dict[Timeframe, set] = {t: set() for t in Timeframe}
        self._by_risk_profile: Dict[RiskProfile, set] = {r: set() for r in RiskProfile}

        # Factory for creating instances
        self._factory = StrategyFactory()

        # Registration callbacks
        self._on_register_callbacks: List[Callable] = []
        self._on_update_callbacks: List[Callable] = []
        self._on_unregister_callbacks: List[Callable] = []

        logger.info("StrategyRegistry initialized")

    # =========================================================================
    # REGISTRATION
    # =========================================================================

    def register_strategy(
        self,
        metadata: StrategyMetadata,
        config: Optional[StrategyConfig] = None,
        created_by: str = "system",
        change_notes: str = "Initial registration"
    ) -> Dict[str, Any]:
        """
        Register a new strategy or update existing

        Args:
            metadata: Strategy metadata
            config: Optional configuration (uses defaults if not provided)
            created_by: Who registered the strategy
            change_notes: Notes about this registration

        Returns:
            Registration result dictionary
        """
        with self._lock:
            strategy_id = metadata.strategy_id

            # Check if updating existing
            is_update = strategy_id in self._strategies

            # Create config if not provided
            if config is None:
                config = StrategyConfig(
                    metadata=metadata,
                    enabled_symbols=set(metadata.supported_symbols)
                )

            # Validate configuration
            validation_result = self._validate_strategy(metadata, config)
            if not validation_result["valid"]:
                logger.error(f"Strategy validation failed: {validation_result['errors']}")
                return {
                    "success": False,
                    "strategy_id": strategy_id,
                    "errors": validation_result["errors"]
                }

            # Update metadata timestamp
            metadata.last_updated = datetime.now(timezone.utc)
            if not is_update:
                metadata.created_at = metadata.last_updated

            # Store strategy
            self._strategies[strategy_id] = metadata
            self._configs[strategy_id] = config

            # Create version entry
            version = self._get_next_version(strategy_id)
            checksum = self._compute_checksum(metadata, config)

            version_entry = StrategyVersion(
                version=version,
                metadata=metadata,
                config=config,
                created_at=datetime.now(timezone.utc),
                created_by=created_by,
                change_notes=change_notes,
                checksum=checksum
            )

            if strategy_id not in self._versions:
                self._versions[strategy_id] = []
            self._versions[strategy_id].append(version_entry)

            # Update indexes
            self._update_indexes(strategy_id, metadata)

            # Fire callbacks
            if is_update:
                for callback in self._on_update_callbacks:
                    try:
                        callback(strategy_id, metadata, config)
                    except Exception as e:
                        logger.error(f"Update callback error: {e}")
            else:
                for callback in self._on_register_callbacks:
                    try:
                        callback(strategy_id, metadata, config)
                    except Exception as e:
                        logger.error(f"Register callback error: {e}")

            logger.info(
                f"{'Updated' if is_update else 'Registered'} strategy: {strategy_id} "
                f"(type={metadata.strategy_type.value}, version={version})"
            )

            return {
                "success": True,
                "strategy_id": strategy_id,
                "version": version,
                "is_update": is_update,
                "checksum": checksum
            }

    def register_from_request(
        self,
        request: RegisterStrategyRequest,
        created_by: str = "api"
    ) -> Dict[str, Any]:
        """
        Register strategy from API request

        Args:
            request: Registration request
            created_by: Who made the request

        Returns:
            Registration result
        """
        # Convert request to metadata
        try:
            strategy_type = StrategyType(request.strategy_type)
        except ValueError:
            strategy_type = StrategyType.TREND_FOLLOWING

        try:
            risk_profile = RiskProfile(request.risk_profile)
        except ValueError:
            risk_profile = RiskProfile.MODERATE

        try:
            timeframe = Timeframe(request.primary_timeframe)
        except ValueError:
            timeframe = Timeframe.H1

        metadata = StrategyMetadata(
            strategy_id=request.strategy_id,
            name=request.name,
            description=request.description,
            strategy_type=strategy_type,
            risk_profile=risk_profile,
            supported_symbols=request.supported_symbols,
            primary_timeframe=timeframe,
            priority=request.priority
        )

        config = StrategyConfig(
            metadata=metadata,
            target_allocation_pct=request.target_allocation_pct,
            enabled_symbols=set(request.supported_symbols)
        )

        return self.register_strategy(
            metadata=metadata,
            config=config,
            created_by=created_by,
            change_notes="Registered via API"
        )

    def unregister_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Unregister a strategy

        Args:
            strategy_id: Strategy to unregister

        Returns:
            Unregistration result
        """
        with self._lock:
            if strategy_id not in self._strategies:
                return {
                    "success": False,
                    "error": f"Strategy not found: {strategy_id}"
                }

            # Get metadata before removal
            metadata = self._strategies[strategy_id]

            # Remove from primary storage
            del self._strategies[strategy_id]
            del self._configs[strategy_id]

            # Remove from indexes
            self._remove_from_indexes(strategy_id, metadata)

            # Keep version history for audit

            # Fire callbacks
            for callback in self._on_unregister_callbacks:
                try:
                    callback(strategy_id, metadata)
                except Exception as e:
                    logger.error(f"Unregister callback error: {e}")

            logger.info(f"Unregistered strategy: {strategy_id}")

            return {
                "success": True,
                "strategy_id": strategy_id
            }

    # =========================================================================
    # RETRIEVAL
    # =========================================================================

    def get_strategy(self, strategy_id: str) -> Optional[StrategyMetadata]:
        """Get strategy metadata by ID"""
        with self._lock:
            return self._strategies.get(strategy_id)

    def get_config(self, strategy_id: str) -> Optional[StrategyConfig]:
        """Get strategy configuration by ID"""
        with self._lock:
            return self._configs.get(strategy_id)

    def get_all_strategies(self) -> Dict[str, StrategyMetadata]:
        """Get all registered strategies"""
        with self._lock:
            return dict(self._strategies)

    def get_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs"""
        with self._lock:
            return list(self._strategies.keys())

    def get_version_history(self, strategy_id: str) -> List[Dict[str, Any]]:
        """Get version history for a strategy"""
        with self._lock:
            if strategy_id not in self._versions:
                return []
            return [v.to_dict() for v in self._versions[strategy_id]]

    def get_latest_version(self, strategy_id: str) -> Optional[str]:
        """Get latest version number for a strategy"""
        with self._lock:
            if strategy_id not in self._versions or not self._versions[strategy_id]:
                return None
            return self._versions[strategy_id][-1].version

    # =========================================================================
    # DISCOVERY / SEARCH
    # =========================================================================

    def find_strategies_by_type(self, strategy_type: StrategyType) -> List[StrategyMetadata]:
        """Find all strategies of a given type"""
        with self._lock:
            strategy_ids = self._by_type.get(strategy_type, set())
            return [self._strategies[sid] for sid in strategy_ids if sid in self._strategies]

    def find_strategies_by_symbol(self, symbol: str) -> List[StrategyMetadata]:
        """Find all strategies that support a given symbol"""
        with self._lock:
            strategy_ids = self._by_symbol.get(symbol, set())
            return [self._strategies[sid] for sid in strategy_ids if sid in self._strategies]

    def find_strategies_by_timeframe(self, timeframe: Timeframe) -> List[StrategyMetadata]:
        """Find all strategies using a given timeframe"""
        with self._lock:
            strategy_ids = self._by_timeframe.get(timeframe, set())
            return [self._strategies[sid] for sid in strategy_ids if sid in self._strategies]

    def find_strategies_by_risk_profile(self, risk_profile: RiskProfile) -> List[StrategyMetadata]:
        """Find all strategies with a given risk profile"""
        with self._lock:
            strategy_ids = self._by_risk_profile.get(risk_profile, set())
            return [self._strategies[sid] for sid in strategy_ids if sid in self._strategies]

    def find_strategies(
        self,
        strategy_type: Optional[StrategyType] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None,
        risk_profile: Optional[RiskProfile] = None,
        min_priority: Optional[int] = None,
        max_priority: Optional[int] = None
    ) -> List[StrategyMetadata]:
        """
        Find strategies matching multiple criteria

        Args:
            strategy_type: Filter by strategy type
            symbol: Filter by symbol support
            timeframe: Filter by timeframe
            risk_profile: Filter by risk profile
            min_priority: Minimum priority
            max_priority: Maximum priority

        Returns:
            List of matching strategies
        """
        with self._lock:
            # Start with all strategies
            candidates = set(self._strategies.keys())

            # Apply filters
            if strategy_type is not None:
                candidates &= self._by_type.get(strategy_type, set())

            if symbol is not None:
                candidates &= self._by_symbol.get(symbol, set())

            if timeframe is not None:
                candidates &= self._by_timeframe.get(timeframe, set())

            if risk_profile is not None:
                candidates &= self._by_risk_profile.get(risk_profile, set())

            # Get matching strategies
            results = [self._strategies[sid] for sid in candidates if sid in self._strategies]

            # Apply priority filters
            if min_priority is not None:
                results = [s for s in results if s.priority >= min_priority]

            if max_priority is not None:
                results = [s for s in results if s.priority <= max_priority]

            # Sort by priority (descending)
            results.sort(key=lambda s: s.priority, reverse=True)

            return results

    def get_recommended_strategies(
        self,
        symbol: str,
        timeframe: Timeframe,
        max_strategies: int = 5
    ) -> List[StrategyMetadata]:
        """
        Get recommended strategies for a symbol and timeframe

        Returns strategies sorted by:
        1. Priority (higher first)
        2. Expected Sharpe (higher first)
        3. Expected win rate (higher first)

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            max_strategies: Maximum number to return

        Returns:
            List of recommended strategies
        """
        strategies = self.find_strategies(symbol=symbol, timeframe=timeframe)

        # Sort by composite score
        def score(s: StrategyMetadata) -> float:
            return (
                s.priority * 0.4 +
                s.expected_sharpe * 20 +
                s.expected_win_rate * 50 +
                s.expected_profit_factor * 10
            )

        strategies.sort(key=score, reverse=True)

        return strategies[:max_strategies]

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_strategy(
        self,
        metadata: StrategyMetadata,
        config: StrategyConfig
    ) -> Dict[str, Any]:
        """
        Validate strategy configuration

        Returns:
            Dictionary with 'valid' boolean and 'errors' list
        """
        errors = []

        # Validate strategy ID
        if not metadata.strategy_id:
            errors.append("Strategy ID is required")
        elif not metadata.strategy_id.replace("_", "").replace("-", "").isalnum():
            errors.append("Strategy ID must be alphanumeric with underscores/hyphens")

        # Validate name
        if not metadata.name:
            errors.append("Strategy name is required")

        # Validate allocation percentages
        if config.target_allocation_pct < 0 or config.target_allocation_pct > 100:
            errors.append("Target allocation must be 0-100%")

        if config.min_allocation_pct > config.max_allocation_pct:
            errors.append("Min allocation cannot exceed max allocation")

        if config.target_allocation_pct < config.min_allocation_pct:
            errors.append("Target allocation cannot be less than minimum")

        if config.target_allocation_pct > config.max_allocation_pct:
            errors.append("Target allocation cannot exceed maximum")

        # Validate risk parameters
        if metadata.max_position_size_pct <= 0 or metadata.max_position_size_pct > 100:
            errors.append("Max position size must be 0-100%")

        if metadata.max_drawdown_pct <= 0 or metadata.max_drawdown_pct > 100:
            errors.append("Max drawdown must be 0-100%")

        # Validate priority
        if metadata.priority < 1 or metadata.priority > 100:
            errors.append("Priority must be 1-100")

        # Validate symbols
        if not metadata.supported_symbols:
            errors.append("At least one supported symbol is required")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def validate_strategy_config(self, strategy_id: str) -> Dict[str, Any]:
        """
        Validate an existing strategy's configuration

        Args:
            strategy_id: Strategy to validate

        Returns:
            Validation result
        """
        with self._lock:
            if strategy_id not in self._strategies:
                return {"valid": False, "errors": ["Strategy not found"]}

            metadata = self._strategies[strategy_id]
            config = self._configs[strategy_id]

            return self._validate_strategy(metadata, config)

    # =========================================================================
    # CONFIGURATION UPDATE
    # =========================================================================

    def update_config(
        self,
        strategy_id: str,
        updates: Dict[str, Any],
        updated_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Update strategy configuration

        Args:
            strategy_id: Strategy to update
            updates: Dictionary of updates
            updated_by: Who made the update

        Returns:
            Update result
        """
        with self._lock:
            if strategy_id not in self._configs:
                return {"success": False, "error": "Strategy not found"}

            config = self._configs[strategy_id]
            metadata = self._strategies[strategy_id]

            # Apply updates to config
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                elif hasattr(metadata, key):
                    setattr(metadata, key, value)

            # Validate updated config
            validation = self._validate_strategy(metadata, config)
            if not validation["valid"]:
                return {
                    "success": False,
                    "errors": validation["errors"]
                }

            # Update timestamp
            metadata.last_updated = datetime.now(timezone.utc)

            # Create new version
            version = self._get_next_version(strategy_id)
            checksum = self._compute_checksum(metadata, config)

            version_entry = StrategyVersion(
                version=version,
                metadata=metadata,
                config=config,
                created_at=datetime.now(timezone.utc),
                created_by=updated_by,
                change_notes=f"Config update: {list(updates.keys())}",
                checksum=checksum
            )
            self._versions[strategy_id].append(version_entry)

            # Update indexes
            self._update_indexes(strategy_id, metadata)

            # Fire update callbacks
            for callback in self._on_update_callbacks:
                try:
                    callback(strategy_id, metadata, config)
                except Exception as e:
                    logger.error(f"Update callback error: {e}")

            logger.info(f"Updated config for {strategy_id}: {list(updates.keys())}")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "version": version,
                "updated_fields": list(updates.keys())
            }

    # =========================================================================
    # VERSION MANAGEMENT
    # =========================================================================

    def _get_next_version(self, strategy_id: str) -> str:
        """Get next version number for a strategy"""
        if strategy_id not in self._versions or not self._versions[strategy_id]:
            return "1.0.0"

        last_version = self._versions[strategy_id][-1].version
        parts = last_version.split(".")

        if len(parts) == 3:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{major}.{minor}.{patch + 1}"

        return "1.0.0"

    def _compute_checksum(
        self,
        metadata: StrategyMetadata,
        config: StrategyConfig
    ) -> str:
        """Compute checksum for strategy configuration"""
        data = json.dumps({
            "metadata": metadata.to_dict(),
            "config": config.to_dict()
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def rollback_to_version(
        self,
        strategy_id: str,
        target_version: str
    ) -> Dict[str, Any]:
        """
        Rollback strategy to a previous version

        Args:
            strategy_id: Strategy to rollback
            target_version: Version to rollback to

        Returns:
            Rollback result
        """
        with self._lock:
            if strategy_id not in self._versions:
                return {"success": False, "error": "Strategy not found"}

            # Find target version
            target = None
            for v in self._versions[strategy_id]:
                if v.version == target_version:
                    target = v
                    break

            if target is None:
                return {"success": False, "error": f"Version not found: {target_version}"}

            # Restore version
            self._strategies[strategy_id] = target.metadata
            self._configs[strategy_id] = target.config

            # Update indexes
            self._update_indexes(strategy_id, target.metadata)

            logger.info(f"Rolled back {strategy_id} to version {target_version}")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "restored_version": target_version
            }

    # =========================================================================
    # INDEX MANAGEMENT
    # =========================================================================

    def _update_indexes(self, strategy_id: str, metadata: StrategyMetadata) -> None:
        """Update all indexes for a strategy"""
        # Remove from all indexes first
        self._remove_from_indexes(strategy_id, metadata)

        # Add to type index
        self._by_type[metadata.strategy_type].add(strategy_id)

        # Add to symbol indexes
        for symbol in metadata.supported_symbols:
            if symbol not in self._by_symbol:
                self._by_symbol[symbol] = set()
            self._by_symbol[symbol].add(strategy_id)

        # Add to timeframe index
        self._by_timeframe[metadata.primary_timeframe].add(strategy_id)
        for tf in metadata.supported_timeframes:
            self._by_timeframe[tf].add(strategy_id)

        # Add to risk profile index
        self._by_risk_profile[metadata.risk_profile].add(strategy_id)

    def _remove_from_indexes(self, strategy_id: str, metadata: StrategyMetadata) -> None:
        """Remove strategy from all indexes"""
        # Remove from type index
        for type_set in self._by_type.values():
            type_set.discard(strategy_id)

        # Remove from symbol indexes
        for symbol_set in self._by_symbol.values():
            symbol_set.discard(strategy_id)

        # Remove from timeframe indexes
        for tf_set in self._by_timeframe.values():
            tf_set.discard(strategy_id)

        # Remove from risk profile indexes
        for rp_set in self._by_risk_profile.values():
            rp_set.discard(strategy_id)

    # =========================================================================
    # FACTORY INTEGRATION
    # =========================================================================

    def register_strategy_class(self, strategy_id: str, strategy_class: Type) -> None:
        """Register a strategy implementation class"""
        self._factory.register_class(strategy_id, strategy_class)

    def register_strategy_factory(self, strategy_id: str, factory_func: Callable) -> None:
        """Register a factory function for creating strategy instances"""
        self._factory.register_factory(strategy_id, factory_func)

    def create_strategy_instance(
        self,
        strategy_id: str,
        config_overrides: Optional[Dict] = None
    ) -> Any:
        """Create an instance of a registered strategy"""
        return self._factory.create_instance(strategy_id, config_overrides)

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def on_register(self, callback: Callable) -> None:
        """Register callback for strategy registration"""
        self._on_register_callbacks.append(callback)

    def on_update(self, callback: Callable) -> None:
        """Register callback for strategy updates"""
        self._on_update_callbacks.append(callback)

    def on_unregister(self, callback: Callable) -> None:
        """Register callback for strategy unregistration"""
        self._on_unregister_callbacks.append(callback)

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """Get registry state for persistence"""
        with self._lock:
            return {
                "strategies": {
                    sid: s.to_dict() for sid, s in self._strategies.items()
                },
                "configs": {
                    sid: c.to_dict() for sid, c in self._configs.items()
                },
                "versions": {
                    sid: [v.to_dict() for v in versions]
                    for sid, versions in self._versions.items()
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        with self._lock:
            return {
                "total_strategies": len(self._strategies),
                "by_type": {
                    t.value: len(ids) for t, ids in self._by_type.items()
                },
                "by_risk_profile": {
                    r.value: len(ids) for r, ids in self._by_risk_profile.items()
                },
                "symbols_covered": len(self._by_symbol),
                "total_versions": sum(len(v) for v in self._versions.values())
            }


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global registry instance
_strategy_registry: Optional[StrategyRegistry] = None


def get_strategy_registry() -> StrategyRegistry:
    """Get or create global strategy registry instance"""
    global _strategy_registry
    if _strategy_registry is None:
        _strategy_registry = StrategyRegistry()
    return _strategy_registry


def reset_strategy_registry() -> None:
    """Reset global strategy registry instance"""
    global _strategy_registry
    _strategy_registry = None
    logger.info("Strategy registry instance reset")
