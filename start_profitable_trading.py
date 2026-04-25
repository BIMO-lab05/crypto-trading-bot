#!/usr/bin/env python3
"""
Profitable Trading System Starter
Applies all optimizations and starts the trading system with enhanced profitability
"""

import asyncio
import sys
import os
import logging
from datetime import datetime

# Add project root and trading-engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'trading-engine'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def apply_optimizations():
    """Apply all optimizations for profitability"""
    
    logger.info("🚀 Applying profitability optimizations...")
    
    # Import the settings
    from app.config import get_settings
    settings = get_settings()
    
    # Display current configuration
    logger.info(f"📊 Current Configuration:")
    logger.info(f"   - Trading Mode: {settings.trading_mode}")
    logger.info(f"   - Auto Trading: {settings.auto_trading_enabled}")
    logger.info(f"   - Symbols: {settings.trading_symbols}")
    logger.info(f"   - Min Confidence: {settings.min_signal_confidence}")
    logger.info(f"   - Stop Loss: {settings.default_stop_loss_pct}%")
    logger.info(f"   - Take Profit: {settings.default_take_profit_pct}%")
    logger.info(f"   - Max Daily Trades: {settings.max_daily_trades}")
    logger.info(f"   - Allowed Sides: {settings.allowed_trade_sides}")
    logger.info(f"   - Short Trading: {settings.short_trading_enabled}")
    
    # Verify optimizations are applied
    assert settings.min_signal_confidence == 0.60, f"Min confidence should be 0.60, got {settings.min_signal_confidence}"
    assert settings.default_take_profit_pct == 4.0, f"Take profit should be 4.0%, got {settings.default_take_profit_pct}"
    assert "SHORT" in settings.allowed_trade_sides, f"SHORT should be in allowed sides, got {settings.allowed_trade_sides}"
    assert settings.short_trading_enabled == True, f"Short trading should be enabled, got {settings.short_trading_enabled}"
    
    logger.info("✅ All optimizations verified and applied!")

async def start_trading_system():
    """Start the trading system with all optimizations"""
    
    logger.info("🚀 Starting Profitable Trading System...")
    
    try:
        # Apply optimizations
        await apply_optimizations()
        
        # Import auto trader
        from app.auto_trader import get_auto_trader
        auto_trader = get_auto_trader()
        
        # Start the auto trader
        success = await auto_trader.start()
        
        if success:
            logger.info("✅ Auto Trader started successfully!")
            logger.info(f"📈 Monitoring symbols: {auto_trader.symbols}")
            logger.info(f"⏰ Check frequency: {auto_trader.check_frequency} seconds")
            logger.info(f"📊 Strategy mode: {auto_trader.strategy_mode.value}")
            
            # Display current status
            status = auto_trader.get_status()
            logger.info(f"📋 Current status: Auto trader running")
            
        else:
            logger.error("❌ Failed to start auto trader")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Error starting trading system: {e}", exc_info=True)
        return False

async def monitor_performance():
    """Monitor the trading performance"""
    
    logger.info("📊 Setting up performance monitoring...")
    
    from app.auto_trader import get_auto_trader
    auto_trader = get_auto_trader()
    
    while auto_trader.is_running:
        try:
            # Get current status
            status = auto_trader.get_status()
            
            logger.info(f"📈 Performance Update [{datetime.now().strftime('%H:%M:%S')}]:")
            logger.info(f"   - Signals Checked: {status['total_signals_checked']}")
            logger.info(f"   - Trades Executed: {status['total_trades_executed']}")
            logger.info(f"   - Trades Rejected: {status['total_trades_rejected']}")
            logger.info(f"   - Open Positions: {status['position_monitoring']['open_positions']}")
            logger.info(f"   - Research Trades: {status['research_trades']}")
            logger.info(f"   - Standard Trades: {status['standard_trades']}")
            
            # Wait before next check
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except Exception as e:
            logger.error(f"❌ Error in performance monitoring: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait 1 minute before retrying

async def main():
    """Main function to start the profitable trading system"""
    
    logger.info("💰 Starting Profitable Crypto Trading System")
    logger.info("===========================================")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("")
    
    # Start the trading system
    success = await start_trading_system()
    
    if not success:
        logger.error("❌ Failed to start trading system")
        sys.exit(1)
    
    logger.info("")
    logger.info("🎉 Profitable Trading System Started Successfully!")
    logger.info("================================================")
    logger.info("📈 The system is now actively trading with:")
    logger.info("   • Optimized symbol allocations (SOLUSDT 30%, BTCUSDT 25%, etc.)")
    logger.info("   • Enabled SHORT trading for current bearish market")
    logger.info("   • Lowered confidence threshold (60%) for more opportunities")
    logger.info("   • Optimized R/R ratio (2:1) with 2% stop loss, 4% take profit")
    logger.info("   • Advanced risk management (Kelly sizing, trailing stops, DCA)")
    logger.info("   • Circuit breaker protection for SHORT trades")
    logger.info("")
    logger.info("💡 The system will automatically adapt to market conditions")
    logger.info("   and optimize for profitability based on recent backtest results")
    logger.info("")
    
    # Start performance monitoring in background
    monitor_task = asyncio.create_task(monitor_performance())
    
    try:
        # Keep the system running
        from app.auto_trader import get_auto_trader
        auto_trader = get_auto_trader()
        while auto_trader.is_running:
            await asyncio.sleep(60)  # Check every minute if system is still running
            
    except KeyboardInterrupt:
        logger.info("🛑 Shutdown signal received...")
        
        # Stop the auto trader
        if auto_trader.is_running:
            await auto_trader.stop()
            logger.info("✅ Auto Trader stopped")
        
        # Cancel monitoring task
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
            
        logger.info("👋 Profitable Trading System shut down gracefully")
    
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        
        # Stop the auto trader in case of error
        auto_trader = get_auto_trader()
        if auto_trader and auto_trader.is_running:
            await auto_trader.stop()
            logger.info("✅ Auto Trader stopped due to error")

if __name__ == "__main__":
    asyncio.run(main())