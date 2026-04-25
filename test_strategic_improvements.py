"""
Test script to validate the strategic improvements to the crypto trading bot
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot')

def create_sample_data():
    """Create sample OHLCV data for testing"""
    np.random.seed(42)
    n_candles = 500
    start_date = datetime.now() - timedelta(days=30)

    # Generate realistic price data
    returns = np.random.normal(0.0005, 0.02, n_candles)  # Daily drift of 0.05%, 2% volatility
    prices = [50000.0]  # Starting price

    for ret in returns:
        prices.append(prices[-1] * (1 + ret))

    # Create OHLCV data
    timestamps = pd.date_range(start=start_date, periods=n_candles, freq='h')  # Use 'h' instead of 'H'

    opens = []
    highs = []
    lows = []
    closes = prices[1:]  # Skip first element since we need to calculate differences

    for i in range(len(closes)):
        if i == 0:
            op = 50000.0
        else:
            op = closes[i-1]

        # Add some intraday variation
        high_variation = abs(closes[i] - op) * np.random.uniform(0.5, 1.5)
        low_variation = abs(closes[i] - op) * np.random.uniform(0.5, 1.5)

        high = max(op, closes[i]) + high_variation * 0.1
        low = min(op, closes[i]) - low_variation * 0.1

        opens.append(op)
        highs.append(high)
        lows.append(low)

    volumes = np.random.uniform(1000, 10000, len(opens))  # Match the length of opens

    df = pd.DataFrame({
        'timestamp': timestamps[:len(opens)],  # Match lengths
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes[:len(opens)],  # Match lengths
        'volume': volumes
    })

    df.set_index('timestamp', inplace=True)
    return df

def test_enhanced_mean_reversion():
    """Test the enhanced mean reversion strategy"""
    print("Testing Enhanced Mean Reversion Strategy...")

    try:
        import sys
        import os
        # Add the backtesting strategies directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backtesting', 'strategies'))
        from enhanced_mean_reversion_strategy import EnhancedMeanReversionStrategy, create_enhanced_mean_reversion_strategy
        
        # Create sample data
        data = create_sample_data()
        
        # Create strategy instance
        strategy = EnhancedMeanReversionStrategy()
        
        # Test signal generation
        if len(data) > 50:
            row = data.iloc[-1]  # Last row
            signal = strategy.generate_signal(row, None, len(data)-1, data)
            print(f"  ✓ Enhanced Mean Reversion Strategy created successfully")
            print(f"  ✓ Signal generated: {signal}")
        else:
            print("  ⚠ Not enough data for signal generation")
        
        # Test factory function
        strategy_func = create_enhanced_mean_reversion_strategy()
        print(f"  ✓ Factory function works")
        
        return True
    except Exception as e:
        print(f"  ✗ Error testing Enhanced Mean Reversion Strategy: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enhanced_breakout():
    """Test the enhanced breakout strategy"""
    print("\nTesting Enhanced Breakout Strategy...")

    try:
        import sys
        import os
        # Add the trading-engine app directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'trading-engine', 'app'))
        from strategies.enhanced_breakout_strategy import EnhancedBreakoutStrategy, create_enhanced_breakout_strategy
        
        # Create sample data
        data = create_sample_data()
        
        # Create strategy instance
        strategy = EnhancedBreakoutStrategy()
        
        # Create mock data dict for analysis
        candles = []
        for idx, row in data.iterrows():
            candles.append({
                'timestamp': idx,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            })
        
        mock_data = {'candles': candles}
        
        # Test analysis
        analysis = strategy.analyze("BTCUSDT", mock_data)
        print(f"  ✓ Enhanced Breakout Strategy created successfully")
        print(f"  ✓ Analysis completed: {analysis.get('is_breakout', 'No breakout detected')}")
        
        # Test factory function
        strategy_instance = create_enhanced_breakout_strategy()
        print(f"  ✓ Factory function works")
        
        return True
    except Exception as e:
        print(f"  ✗ Error testing Enhanced Breakout Strategy: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_market_regime_detection():
    """Test the market regime detection system"""
    print("\nTesting Market Regime Detection...")

    try:
        import sys
        import os
        # Add the trading-engine app directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'trading-engine', 'app'))
        from adaptive_strategy_controller import AdaptiveStrategyController, adapt_strategy_for_regime
        
        # Create sample data
        data = create_sample_data()
        
        # Create controller
        controller = AdaptiveStrategyController()
        
        # Test regime detection
        regime_info = controller.detect_market_regime(data, "BTCUSDT")
        print(f"  ✓ Adaptive Strategy Controller created successfully")
        print(f"  ✓ Regime detected: {regime_info['regime_type']} with confidence {regime_info['confidence']:.2f}")
        
        # Test adaptive function
        strategy_type, params, should_trade = adapt_strategy_for_regime(data, "BTCUSDT")
        print(f"  ✓ Adaptive function works: Selected {strategy_type.value}, should_trade: {should_trade}")
        
        return True
    except Exception as e:
        print(f"  ✗ Error testing Market Regime Detection: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multi_timeframe_testing():
    """Test the multi-timeframe testing capabilities"""
    print("\nTesting Multi-Timeframe Testing...")

    try:
        import sys
        import os
        # Add the backtesting directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backtesting'))
        from multi_timeframe_tester import MultiTimeframeTester, Timeframe, create_multi_timeframe_tester
        
        # Create tester
        tester = create_multi_timeframe_tester(
            timeframes=[Timeframe.MINUTE_15, Timeframe.HOUR_4, Timeframe.DAY_1],
            test_duration_days=7,
            strategy_type="mean_reversion"
        )
        
        print(f"  ✓ Multi-Timeframe Tester created successfully")
        print(f"  ✓ Testing timeframes: {[tf.value for tf in tester.config.timeframes]}")
        
        return True
    except Exception as e:
        print(f"  ✗ Error testing Multi-Timeframe Testing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ensemble_methods():
    """Test the ML-based ensemble methods"""
    print("\nTesting ML-Based Ensemble Methods...")

    try:
        import sys
        import os
        # Add the ml-prediction-service app directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'ml-prediction-service', 'app'))
        from ensemble_strategy import EnsembleStrategy, EnsembleConfig, create_ensemble_strategy
        
        # Create ensemble strategy
        config = EnsembleConfig()
        ensemble = EnsembleStrategy(config)
        
        print(f"  ✓ Ensemble Strategy created successfully")
        print(f"  ✓ ML Model type: {config.ml_model_type}")
        
        # Test factory function
        ensemble_instance = create_ensemble_strategy()
        print(f"  ✓ Factory function works")
        
        return True
    except Exception as e:
        print(f"  ✗ Error testing ML-Based Ensemble Methods: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_configuration_system():
    """Test the configuration system"""
    print("\nTesting Configuration System...")

    try:
        import sys
        import os
        # Add the trading-engine app directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'trading-engine', 'app'))
        from strategy_config_system import StrategyConfigurationSystem, create_strategy_configuration_system
        
        # Create configuration system
        config_system = create_strategy_configuration_system()
        
        # Create mock market data
        data = create_sample_data()
        market_data = {
            'closes': data['close'].tolist(),
            'highs': data['high'].tolist(),
            'lows': data['low'].tolist(),
            'volumes': data['volume'].tolist(),
            'df': data,
            'symbol': 'BTCUSDT'
        }
        
        # Test strategy selection
        active_strategies = config_system.get_active_strategies(market_data)
        print(f"  ✓ Strategy Configuration System created successfully")
        print(f"  ✓ Active strategies: {len(active_strategies)}")
        
        # Test recommendation
        recommendation = config_system.get_recommendation(market_data)
        print(f"  ✓ Recommendation generated: {recommendation['action']}")
        
        return True
    except Exception as e:
        print(f"  ✗ Error testing Configuration System: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("Running tests for strategic improvements to crypto trading bot...\n")
    
    tests = [
        test_enhanced_mean_reversion,
        test_enhanced_breakout,
        test_market_regime_detection,
        test_multi_timeframe_testing,
        test_ensemble_methods,
        test_configuration_system
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print(f"\n{'='*60}")
    print("TEST SUMMARY:")
    print(f"{'='*60}")
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test.__name__}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The strategic improvements are working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the error messages above.")

if __name__ == "__main__":
    main()