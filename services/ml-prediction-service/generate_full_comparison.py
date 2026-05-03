#!/usr/bin/env python3
"""
Generate comprehensive 16 GRU vs 16 LSTM comparison report
"""
import os
import json
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
from datetime import datetime
from typing import Dict, List, Tuple

# Model directory
MODELS_DIR = (_REPO_ROOT / 'services/ml-prediction-service/models')

# All 16 symbols
SYMBOLS = [
    'ADAUSDT', 'APTUSDT', 'ARBUSDT', 'AVAXUSDT', 'BNBUSDT', 'BTCUSDT',
    'DOGEUSDT', 'DOTUSDT', 'ETHUSDT', 'LINKUSDT', 'LTCUSDT', 'OPUSDT',
    'POLUSDT', 'SOLUSDT', 'SUIUSDT', 'XRPUSDT'
]

def load_model_metadata(symbol: str, model_type: str) -> Dict:
    """Load metadata for a model"""
    if model_type == 'gru':
        metadata_file = MODELS_DIR / f'{symbol}_60m_gru_metadata.json'
    else:  # lstm
        metadata_file = MODELS_DIR / f'lstm_{symbol}_60m_metadata.json'

    if not metadata_file.exists():
        return None

    with open(metadata_file, 'r') as f:
        return json.load(f)

def get_model_info(symbol: str) -> Tuple[Dict, Dict, bool, bool]:
    """Get info for both GRU and LSTM models"""
    gru_meta = load_model_metadata(symbol, 'gru')
    lstm_meta = load_model_metadata(symbol, 'lstm')

    gru_exists = (MODELS_DIR / f'{symbol}_60m_gru.keras').exists()
    lstm_exists = (MODELS_DIR / f'lstm_{symbol}_60m.h5').exists()

    return gru_meta, lstm_meta, gru_exists, lstm_exists

def format_r2(value: float) -> str:
    """Format R² with color emoji"""
    if value >= 0.95:
        return f"🟢 {value:.4f}"
    elif value >= 0.85:
        return f"🟡 {value:.4f}"
    elif value >= 0.75:
        return f"🟠 {value:.4f}"
    else:
        return f"🔴 {value:.4f}"

def calculate_improvement(lstm_val: float, gru_val: float) -> str:
    """Calculate improvement percentage"""
    if lstm_val == 0:
        return "N/A"

    improvement = ((gru_val - lstm_val) / abs(lstm_val)) * 100
    if improvement > 0:
        return f"+{improvement:.2f}%"
    else:
        return f"{improvement:.2f}%"

def generate_report():
    """Generate comprehensive comparison report"""

    print("="*100)
    print("COMPREHENSIVE GRU vs LSTM COMPARISON - ALL 16 SYMBOLS")
    print("="*100)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Models Directory: {MODELS_DIR}")
    print("="*100)
    print()

    # Collect data
    results = []
    gru_wins = 0
    lstm_wins = 0
    both_missing = []

    for symbol in SYMBOLS:
        gru_meta, lstm_meta, gru_exists, lstm_exists = get_model_info(symbol)

        if not gru_exists and not lstm_exists:
            both_missing.append(symbol)
            continue

        # Extract metrics (handle different metadata formats)
        if gru_meta:
            gru_r2 = gru_meta.get('validation_r2_score', gru_meta.get('test_r2', 0))
            gru_mae = gru_meta.get('validation_mae', gru_meta.get('test_mae', 0))
            gru_rmse = gru_meta.get('validation_rmse', gru_meta.get('test_rmse', 0))
        else:
            gru_r2 = gru_mae = gru_rmse = 0

        if lstm_meta:
            lstm_r2 = lstm_meta.get('validation_r2_score', lstm_meta.get('test_r2', 0))
            lstm_mae = lstm_meta.get('validation_mae', lstm_meta.get('test_mae', 0))
            lstm_rmse = lstm_meta.get('validation_rmse', lstm_meta.get('test_rmse', 0))
        else:
            lstm_r2 = lstm_mae = lstm_rmse = 0

        # Determine winner
        if gru_exists and lstm_exists:
            if gru_r2 > lstm_r2:
                winner = "GRU"
                gru_wins += 1
            elif lstm_r2 > gru_r2:
                winner = "LSTM"
                lstm_wins += 1
            else:
                winner = "TIE"
        elif gru_exists:
            winner = "GRU (only)"
        else:
            winner = "LSTM (only)"

        results.append({
            'symbol': symbol,
            'gru_exists': gru_exists,
            'lstm_exists': lstm_exists,
            'gru_r2': gru_r2,
            'lstm_r2': lstm_r2,
            'gru_mae': gru_mae,
            'lstm_mae': lstm_mae,
            'gru_rmse': gru_rmse,
            'lstm_rmse': lstm_rmse,
            'winner': winner
        })

    # Sort by GRU R² score (descending)
    results.sort(key=lambda x: x['gru_r2'], reverse=True)

    # Print detailed comparison table
    print("\n" + "="*100)
    print("DETAILED MODEL COMPARISON")
    print("="*100)
    print(f"{'Symbol':<12} {'LSTM R²':<15} {'GRU R²':<15} {'Improvement':<12} {'Winner':<12}")
    print("-"*100)

    for r in results:
        lstm_r2_str = format_r2(r['lstm_r2']) if r['lstm_exists'] else "N/A"
        gru_r2_str = format_r2(r['gru_r2']) if r['gru_exists'] else "N/A"
        improvement = calculate_improvement(r['lstm_r2'], r['gru_r2']) if r['lstm_exists'] and r['gru_exists'] else "N/A"

        print(f"{r['symbol']:<12} {lstm_r2_str:<15} {gru_r2_str:<15} {improvement:<12} {r['winner']:<12}")

    # Summary statistics
    print("\n" + "="*100)
    print("SUMMARY STATISTICS")
    print("="*100)

    both_exist = [r for r in results if r['gru_exists'] and r['lstm_exists']]
    print(f"\nModels with both GRU and LSTM: {len(both_exist)}")
    print(f"GRU wins: {gru_wins}")
    print(f"LSTM wins: {lstm_wins}")
    print(f"Win rate: {(gru_wins/(gru_wins+lstm_wins)*100) if (gru_wins+lstm_wins) > 0 else 0:.1f}% for GRU")

    if both_exist:
        avg_lstm_r2 = sum(r['lstm_r2'] for r in both_exist) / len(both_exist)
        avg_gru_r2 = sum(r['gru_r2'] for r in both_exist) / len(both_exist)
        avg_improvement = ((avg_gru_r2 - avg_lstm_r2) / abs(avg_lstm_r2)) * 100 if avg_lstm_r2 != 0 else 0

        print(f"\nAverage LSTM R²: {avg_lstm_r2:.4f}")
        print(f"Average GRU R²: {avg_gru_r2:.4f}")
        print(f"Average Improvement: {avg_improvement:+.2f}%")

    # GRU-only models
    gru_only = [r for r in results if r['gru_exists'] and not r['lstm_exists']]
    if gru_only:
        print(f"\n{'='*100}")
        print("GRU-ONLY MODELS (No LSTM comparison available)")
        print('='*100)
        for r in gru_only:
            print(f"{r['symbol']:<12} GRU R²={r['gru_r2']:.4f}, MAE={r['gru_mae']:.6f}, RMSE={r['gru_rmse']:.6f}")

    # Quality tiers
    print(f"\n{'='*100}")
    print("QUALITY TIERS (GRU Models)")
    print('='*100)

    excellent = [r for r in results if r['gru_exists'] and r['gru_r2'] >= 0.95]
    very_good = [r for r in results if r['gru_exists'] and 0.85 <= r['gru_r2'] < 0.95]
    good = [r for r in results if r['gru_exists'] and 0.75 <= r['gru_r2'] < 0.85]
    below = [r for r in results if r['gru_exists'] and r['gru_r2'] < 0.75]

    print(f"\n🟢 Excellent (R² ≥0.95): {len(excellent)} models")
    for r in excellent[:5]:  # Top 5
        print(f"   • {r['symbol']}: {r['gru_r2']:.4f}")

    print(f"\n🟡 Very Good (0.85 ≤ R² <0.95): {len(very_good)} models")
    for r in very_good:
        print(f"   • {r['symbol']}: {r['gru_r2']:.4f}")

    print(f"\n🟠 Good (0.75 ≤ R² <0.85): {len(good)} models")
    for r in good:
        print(f"   • {r['symbol']}: {r['gru_r2']:.4f}")

    if below:
        print(f"\n🔴 Below Target (R² <0.75): {len(below)} models")
        for r in below:
            print(f"   • {r['symbol']}: {r['gru_r2']:.4f}")

    # Deployment recommendations
    print(f"\n{'='*100}")
    print("DEPLOYMENT RECOMMENDATIONS")
    print('='*100)

    tier1 = [r for r in results if r['gru_exists'] and r['gru_r2'] >= 0.90]
    tier2 = [r for r in results if r['gru_exists'] and 0.85 <= r['gru_r2'] < 0.90]
    tier3 = [r for r in results if r['gru_exists'] and 0.75 <= r['gru_r2'] < 0.85]

    print(f"\n✅ Tier 1 - Deploy Immediately (R² ≥0.90): {len(tier1)} models")
    print(f"   Symbols: {', '.join([r['symbol'] for r in tier1])}")

    print(f"\n⚠️  Tier 2 - Deploy with Monitoring (0.85 ≤ R² <0.90): {len(tier2)} models")
    print(f"   Symbols: {', '.join([r['symbol'] for r in tier2])}")

    print(f"\n🔶 Tier 3 - Deploy with Caution (0.75 ≤ R² <0.85): {len(tier3)} models")
    print(f"   Symbols: {', '.join([r['symbol'] for r in tier3])}")

    if below:
        print(f"\n❌ Do Not Deploy (R² <0.75): {len(below)} models")
        print(f"   Symbols: {', '.join([r['symbol'] for r in below])}")
        print(f"   Action: Retrain with more data or different hyperparameters")

    print("\n" + "="*100)
    print("REPORT COMPLETE")
    print("="*100)

    # Save to markdown file
    output_file = MODELS_DIR.parent / 'COMPLETE_GRU_LSTM_COMPARISON_2025-12-10.md'
    print(f"\nSaving detailed report to: {output_file}")

    # Generate markdown report (abbreviated here)
    with open(output_file, 'w') as f:
        f.write(f"# Complete GRU vs LSTM Comparison Report\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- **Total Symbols**: 16\n")
        f.write(f"- **GRU Models**: {len([r for r in results if r['gru_exists']])}\n")
        f.write(f"- **LSTM Models**: {len([r for r in results if r['lstm_exists']])}\n")
        f.write(f"- **GRU Wins**: {gru_wins}/{len(both_exist)} ({(gru_wins/len(both_exist)*100) if len(both_exist) > 0 else 0:.1f}%)\n\n")

        f.write(f"## Detailed Comparison\n\n")
        f.write(f"| Symbol | LSTM R² | GRU R² | Improvement | Winner |\n")
        f.write(f"|--------|---------|--------|-------------|--------|\n")
        for r in results:
            lstm_str = f"{r['lstm_r2']:.4f}" if r['lstm_exists'] else "N/A"
            gru_str = f"{r['gru_r2']:.4f}" if r['gru_exists'] else "N/A"
            imp_str = calculate_improvement(r['lstm_r2'], r['gru_r2']) if r['lstm_exists'] and r['gru_exists'] else "N/A"
            f.write(f"| {r['symbol']} | {lstm_str} | {gru_str} | {imp_str} | {r['winner']} |\n")

    print(f"✅ Markdown report saved: {output_file}")

if __name__ == '__main__':
    generate_report()
