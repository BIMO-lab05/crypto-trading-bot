"""
Simple validation script to check that the strategic improvements were implemented correctly
"""

import os
import sys
import inspect
import importlib.util
from pathlib import Path

# Resolve project root from this file's location so the script works on any
# machine (was hardcoded to /mnt/d/Bimo_max/crypto-trading-bot).
PROJECT_ROOT = str(Path(__file__).resolve().parent)

def validate_file_exists(filepath):
    """Check if file exists"""
    if os.path.exists(filepath):
        print(f"  ✓ File exists: {filepath}")
        return True
    else:
        print(f"  ✗ File missing: {filepath}")
        return False

def validate_module_can_be_imported(filepath, module_name):
    """Try to import a module and check for syntax errors"""
    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"  ✓ Module imports successfully: {module_name}")
        return module
    except Exception as e:
        print(f"  ✗ Module import failed: {module_name} - Error: {e}")
        return None

def validate_class_exists(module, class_name):
    """Check if a class exists in the module"""
    if hasattr(module, class_name):
        cls = getattr(module, class_name)
        if inspect.isclass(cls):
            print(f"  ✓ Class exists: {class_name}")
            return True
        else:
            print(f"  ✗ Not a class: {class_name}")
            return False
    else:
        print(f"  ✗ Class not found: {class_name}")
        return False

def validate_function_exists(module, function_name):
    """Check if a function exists in the module"""
    if hasattr(module, function_name):
        func = getattr(module, function_name)
        if inspect.isfunction(func) or inspect.isbuiltin(func):
            print(f"  ✓ Function exists: {function_name}")
            return True
        else:
            print(f"  ✗ Not a function: {function_name}")
            return False
    else:
        print(f"  ✗ Function not found: {function_name}")
        return False

def main():
    print("Validating strategic improvements implementation...\n")
    
    all_validated = True
    
    # 1. Enhanced Mean Reversion Strategy
    print("1. Validating Enhanced Mean Reversion Strategy...")
    mean_rev_path = f"{PROJECT_ROOT}/backtesting/strategies/enhanced_mean_reversion_strategy.py"
    if validate_file_exists(mean_rev_path):
        mean_rev_module = validate_module_can_be_imported(mean_rev_path, "enhanced_mean_reversion_strategy")
        if mean_rev_module:
            class_ok = validate_class_exists(mean_rev_module, "EnhancedMeanReversionStrategy")
            func_ok = validate_function_exists(mean_rev_module, "create_enhanced_mean_reversion_strategy")
            all_validated = all_validated and class_ok and func_ok
        else:
            all_validated = False
    else:
        all_validated = False
    print()
    
    # 2. Enhanced Breakout Strategy
    print("2. Validating Enhanced Breakout Strategy...")
    breakout_path = f"{PROJECT_ROOT}/services/trading-engine/app/strategies/enhanced_breakout_strategy.py"
    if validate_file_exists(breakout_path):
        breakout_module = validate_module_can_be_imported(breakout_path, "enhanced_breakout_strategy")
        if breakout_module:
            class_ok = validate_class_exists(breakout_module, "EnhancedBreakoutStrategy")
            func_ok = validate_function_exists(breakout_module, "create_enhanced_breakout_strategy")
            all_validated = all_validated and class_ok and func_ok
        else:
            all_validated = False
    else:
        all_validated = False
    print()
    
    # 3. Market Regime Detection
    print("3. Validating Market Regime Detection...")
    regime_path = f"{PROJECT_ROOT}/services/trading-engine/app/adaptive_strategy_controller.py"
    if validate_file_exists(regime_path):
        regime_module = validate_module_can_be_imported(regime_path, "adaptive_strategy_controller")
        if regime_module:
            class_ok = validate_class_exists(regime_module, "AdaptiveStrategyController")
            func_ok = validate_function_exists(regime_module, "adapt_strategy_for_regime")
            all_validated = all_validated and class_ok and func_ok
        else:
            all_validated = False
    else:
        all_validated = False
    print()
    
    # 4. Multi-Timeframe Testing
    print("4. Validating Multi-Timeframe Testing...")
    timeframe_path = f"{PROJECT_ROOT}/backtesting/multi_timeframe_tester.py"
    if validate_file_exists(timeframe_path):
        timeframe_module = validate_module_can_be_imported(timeframe_path, "multi_timeframe_tester")
        if timeframe_module:
            class_ok = validate_class_exists(timeframe_module, "MultiTimeframeTester")
            func_ok = validate_function_exists(timeframe_module, "create_multi_timeframe_tester")
            all_validated = all_validated and class_ok and func_ok
        else:
            all_validated = False
    else:
        all_validated = False
    print()
    
    # 5. ML-Based Ensemble Methods
    print("5. Validating ML-Based Ensemble Methods...")
    ensemble_path = f"{PROJECT_ROOT}/services/ml-prediction-service/app/ensemble_strategy.py"
    if validate_file_exists(ensemble_path):
        ensemble_module = validate_module_can_be_imported(ensemble_path, "ensemble_strategy")
        if ensemble_module:
            class_ok = validate_class_exists(ensemble_module, "EnsembleStrategy")
            func_ok = validate_function_exists(ensemble_module, "create_ensemble_strategy")
            all_validated = all_validated and class_ok and func_ok
        else:
            all_validated = False
    else:
        all_validated = False
    print()
    
    # 6. Configuration System
    print("6. Validating Configuration System...")
    config_path = f"{PROJECT_ROOT}/services/trading-engine/app/strategy_config_system.py"
    if validate_file_exists(config_path):
        config_module = validate_module_can_be_imported(config_path, "strategy_config_system")
        if config_module:
            class_ok = validate_class_exists(config_module, "StrategyConfigurationSystem")
            func_ok = validate_function_exists(config_module, "create_strategy_configuration_system")
            all_validated = all_validated and class_ok and func_ok
        else:
            all_validated = False
    else:
        all_validated = False
    print()
    
    # Summary
    print("="*60)
    if all_validated:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("All strategic improvements have been successfully implemented.")
        print("Files are in place with expected classes and functions.")
    else:
        print("❌ SOME VALIDATIONS FAILED!")
        print("Some components may not be properly implemented.")
    print("="*60)

if __name__ == "__main__":
    main()