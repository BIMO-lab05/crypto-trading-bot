"""
Basic Handler Coverage Tests
Purpose: Quick tests to boost handler coverage
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from app.models import (
    HealthResponse, StatusResponse, SignalAction, TradingSignal,
    Position, PositionStatus, OrderType
)


@pytest.mark.asyncio
async def test_health_check_handler():
    """Test health check endpoint"""
    from app.handlers import health
    
    # Mock dependencies
    mock_health_monitor = Mock()
    mock_health = Mock()
    mock_health.status = Mock(value="healthy")
    mock_health.dependencies = {}
    mock_health.metrics = {}
    mock_health_monitor.get_cached_health = AsyncMock(return_value=mock_health)
    
    with patch('app.handlers.health.get_health_monitor', return_value=mock_health_monitor):
        result = await health.health_check()
        
    assert isinstance(result, HealthResponse)


@pytest.mark.asyncio
async def test_status_handler():
    """Test status endpoint"""
    from app.handlers import health
    
    mock_aggregator = Mock()
    mock_aggregator.get_aggregated_stats = Mock(return_value={})
    
    mock_pm = Mock()
    mock_pm.get_all_positions = Mock(return_value=[])
    mock_pm.get_metrics = Mock(return_value={})
    
    mock_paper = Mock()
    mock_paper.is_running = False
    mock_paper.get_execution_stats = Mock(return_value={})
    
    with patch('app.handlers.health.get_aggregator', return_value=mock_aggregator), \
         patch('app.handlers.health.get_position_manager', return_value=mock_pm), \
         patch('app.handlers.health.get_paper_engine', return_value=mock_paper):
        result = await health.get_status()
        
    assert isinstance(result, StatusResponse)


@pytest.mark.asyncio
async def test_signals_get_current():
    """Test get current signal"""
    from app.handlers import signals
    
    mock_signal = TradingSignal(
        symbol="BTCUSDT",
        timestamp=1234567890,
        action=SignalAction.BUY,
        confidence=0.75,
        indicators={},
        aggregated_score=0.8,
        consensus_count=5,
        metadata={}
    )
    
    mock_agg = Mock()
    mock_agg.get_latest_signal = Mock(return_value=mock_signal)
    
    with patch('app.handlers.signals.get_aggregator', return_value=mock_agg):
        result = await signals.get_current_signal("BTCUSDT")
        
    assert result.action == SignalAction.BUY


@pytest.mark.asyncio
async def test_positions_get_open():
    """Test get open positions"""
    from app.handlers import positions
    
    mock_pos = Position(
        id="pos1",
        symbol="BTCUSDT",
        side="BUY",
        entry_price=Decimal("50000.0"),
        quantity=Decimal("0.1"),
        status=PositionStatus.OPEN,
        timestamp=1234567890,
        order_type=OrderType.MARKET
    )
    
    mock_pm = Mock()
    mock_pm.get_open_positions = Mock(return_value=[mock_pos])
    
    with patch('app.handlers.positions.get_position_manager', return_value=mock_pm):
        result = await positions.get_open_positions()
        
    assert len(result) == 1


@pytest.mark.asyncio
async def test_trading_control_start():
    """Test start trading"""
    from app.handlers import trading_control
    
    mock_trader = Mock()
    mock_trader.is_running = False
    mock_trader.start = AsyncMock()
    
    with patch('app.handlers.trading_control.get_auto_trader', return_value=mock_trader):
        result = await trading_control.start_trading()
        
    assert result["status"] == "started"


@pytest.mark.asyncio
async def test_trading_control_stop():
    """Test stop trading"""
    from app.handlers import trading_control
    
    mock_trader = Mock()
    mock_trader.is_running = True
    mock_trader.stop = AsyncMock()
    
    with patch('app.handlers.trading_control.get_auto_trader', return_value=mock_trader):
        result = await trading_control.stop_trading()
        
    assert result["status"] == "stopped"


@pytest.mark.asyncio
async def test_performance_get_metrics():
    """Test get performance metrics"""
    from app.handlers import performance
    
    mock_agg = Mock()
    mock_agg.get_signal_metrics = Mock(return_value={
        "total_signals": 100,
        "buy_signals": 40,
        "sell_signals": 35,
        "hold_signals": 25,
        "avg_confidence": 0.75
    })
    
    with patch('app.handlers.performance.get_aggregator', return_value=mock_agg):
        result = await performance.get_performance_metrics()
        
    assert result is not None


@pytest.mark.asyncio
async def test_phase1_get_stats():
    """Test get phase1 stats"""
    from app.handlers import phase1
    
    mock_agg = Mock()
    mock_agg.get_aggregated_stats = Mock(return_value={
        "gatekeeper": {"total": 100},
        "validator": {"total": 80}
    })
    
    with patch('app.handlers.phase1.get_aggregator', return_value=mock_agg):
        result = await phase1.get_phase1_statistics()
        
    assert result["gatekeeper"]["total"] == 100
