#!/usr/bin/env python3
"""
LSTM vs GRU Model Comparison Script
Analyzes performance metrics from both model types and generates comparison report

Author: ML Team
Date: 2025-12-10
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Model directories
MODELS_DIR = Path(__file__).parent / 'models'

def load_model_metadata(symbol: str, model_type: str) -> Dict:
    """Load metadata for a specific model"""
    # LSTM metadata files are named differently (without _lstm suffix)
    if model_type.upper() == 'LSTM':
        metadata_file = MODELS_DIR / f"{symbol}_60m_metadata.json"
    else:
        metadata_file = MODELS_DIR / f"{symbol}_60m_{model_type.lower()}_metadata.json"

    if not metadata_file.exists():
        return None

    with open(metadata_file, 'r') as f:
        return json.load(f)

def extract_metrics(metadata: Dict) -> Dict:
    """Extract key metrics from metadata"""
    if not metadata:
        return {}

    stats = metadata.get('training_stats', {})

    return {
        'r2_score': stats.get('r2_score', 0),
        'mae': stats.get('mae', 0),
        'rmse': stats.get('rmse', 0),
        'directional_accuracy': stats.get('directional_accuracy', 0),
        'train_samples': stats.get('train_samples', 0),
        'test_samples': stats.get('test_samples', 0),
        'epochs_trained': stats.get('epochs_trained', 0),
        'total_parameters': stats.get('total_parameters', 0),
        'model_version': metadata.get('model_version', 'unknown'),
        'last_trained': metadata.get('last_trained', 'unknown')
    }

def compare_models():
    """Compare LSTM and GRU models for all symbols"""

    # Get all symbols with both LSTM and GRU models
    lstm_files = list(MODELS_DIR.glob('*_60m_lstm.keras'))
    gru_files = list(MODELS_DIR.glob('*_60m_gru.keras'))

    lstm_symbols = {f.name.split('_')[0] for f in lstm_files}
    gru_symbols = {f.name.split('_')[0] for f in gru_files}

    # Symbols with both models
    common_symbols = sorted(lstm_symbols & gru_symbols)

    # Symbols with only one model type
    lstm_only = sorted(lstm_symbols - gru_symbols)
    gru_only = sorted(gru_symbols - lstm_symbols)

    print("=" * 100)
    print("LSTM vs GRU MODEL COMPARISON REPORT")
    print("=" * 100)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    print(f"Total LSTM models: {len(lstm_symbols)}")
    print(f"Total GRU models: {len(gru_symbols)}")
    print(f"Symbols with both models: {len(common_symbols)}")
    print()

    # Detailed comparison for symbols with both models
    if common_symbols:
        print("=" * 100)
        print("DETAILED COMPARISON (Symbols with both LSTM and GRU)")
        print("=" * 100)
        print()

        comparison_data = []

        for symbol in common_symbols:
            print(f"\n{'='*50}")
            print(f"Symbol: {symbol}")
            print(f"{'='*50}")

            # Load metadata
            lstm_meta = load_model_metadata(symbol, 'LSTM')
            gru_meta = load_model_metadata(symbol, 'GRU')

            # Extract metrics
            lstm_metrics = extract_metrics(lstm_meta)
            gru_metrics = extract_metrics(gru_meta)

            # Display comparison
            print(f"\nLSTM Model:")
            print(f"  R² Score:            {lstm_metrics.get('r2_score', 0):.4f}")
            print(f"  MAE:                 {lstm_metrics.get('mae', 0):.6f}")
            print(f"  RMSE:                {lstm_metrics.get('rmse', 0):.6f}")
            print(f"  Dir. Accuracy:       {lstm_metrics.get('directional_accuracy', 0)*100:.2f}%")
            print(f"  Training Samples:    {lstm_metrics.get('train_samples', 0)}")
            print(f"  Epochs Trained:      {lstm_metrics.get('epochs_trained', 0)}")
            print(f"  Parameters:          {lstm_metrics.get('total_parameters', 0):,}")
            print(f"  Last Trained:        {lstm_metrics.get('last_trained', 'unknown')}")

            print(f"\nGRU Model:")
            print(f"  R² Score:            {gru_metrics.get('r2_score', 0):.4f}")
            print(f"  MAE:                 {gru_metrics.get('mae', 0):.6f}")
            print(f"  RMSE:                {gru_metrics.get('rmse', 0):.6f}")
            print(f"  Dir. Accuracy:       {gru_metrics.get('directional_accuracy', 0)*100:.2f}%")
            print(f"  Training Samples:    {gru_metrics.get('train_samples', 0)}")
            print(f"  Epochs Trained:      {gru_metrics.get('epochs_trained', 0)}")
            print(f"  Parameters:          {gru_metrics.get('total_parameters', 0):,}")
            print(f"  Last Trained:        {gru_metrics.get('last_trained', 'unknown')}")

            # Determine winner
            lstm_r2 = lstm_metrics.get('r2_score', 0)
            gru_r2 = gru_metrics.get('r2_score', 0)

            print(f"\n{'Winner':<20} ", end='')
            if gru_r2 > lstm_r2:
                diff = (gru_r2 - lstm_r2) * 100
                print(f"🏆 GRU (+{diff:.2f}% R²)")
                winner = 'GRU'
            elif lstm_r2 > gru_r2:
                diff = (lstm_r2 - gru_r2) * 100
                print(f"🏆 LSTM (+{diff:.2f}% R²)")
                winner = 'LSTM'
            else:
                print("🤝 TIE")
                winner = 'TIE'

            # Store for summary
            comparison_data.append({
                'symbol': symbol,
                'lstm_r2': lstm_r2,
                'gru_r2': gru_r2,
                'lstm_dir_acc': lstm_metrics.get('directional_accuracy', 0),
                'gru_dir_acc': gru_metrics.get('directional_accuracy', 0),
                'winner': winner
            })

        # Summary statistics
        print("\n\n" + "=" * 100)
        print("SUMMARY STATISTICS")
        print("=" * 100)
        print()

        # Count winners
        gru_wins = sum(1 for d in comparison_data if d['winner'] == 'GRU')
        lstm_wins = sum(1 for d in comparison_data if d['winner'] == 'LSTM')
        ties = sum(1 for d in comparison_data if d['winner'] == 'TIE')

        print(f"GRU Wins:  {gru_wins}/{len(common_symbols)} ({gru_wins/len(common_symbols)*100:.1f}%)")
        print(f"LSTM Wins: {lstm_wins}/{len(common_symbols)} ({lstm_wins/len(common_symbols)*100:.1f}%)")
        print(f"Ties:      {ties}/{len(common_symbols)} ({ties/len(common_symbols)*100:.1f}%)")
        print()

        # Average metrics
        avg_lstm_r2 = sum(d['lstm_r2'] for d in comparison_data) / len(comparison_data)
        avg_gru_r2 = sum(d['gru_r2'] for d in comparison_data) / len(comparison_data)
        avg_lstm_dir = sum(d['lstm_dir_acc'] for d in comparison_data) / len(comparison_data)
        avg_gru_dir = sum(d['gru_dir_acc'] for d in comparison_data) / len(comparison_data)

        print(f"Average LSTM R²:              {avg_lstm_r2:.4f}")
        print(f"Average GRU R²:               {avg_gru_r2:.4f}")
        print(f"Average LSTM Dir. Accuracy:   {avg_lstm_dir*100:.2f}%")
        print(f"Average GRU Dir. Accuracy:    {avg_gru_dir*100:.2f}%")
        print()

        # Overall winner
        print("OVERALL WINNER: ", end='')
        if gru_wins > lstm_wins:
            print("🏆 GRU")
        elif lstm_wins > gru_wins:
            print("🏆 LSTM")
        else:
            print("🤝 TIE")
        print()

    # Models with only one type
    if lstm_only:
        print("\n" + "=" * 100)
        print(f"SYMBOLS WITH ONLY LSTM MODELS ({len(lstm_only)} symbols)")
        print("=" * 100)
        print(", ".join(lstm_only))
        print()

    if gru_only:
        print("\n" + "=" * 100)
        print(f"SYMBOLS WITH ONLY GRU MODELS ({len(gru_only)} symbols)")
        print("=" * 100)
        print(", ".join(gru_only))
        print()

    # Recommendations
    print("\n" + "=" * 100)
    print("RECOMMENDATIONS")
    print("=" * 100)
    print()

    if gru_wins > lstm_wins:
        print("✅ GRU models show better performance overall")
        print("   Recommendation: Prioritize GRU for production deployment")
        print(f"   Action: Train GRU models for the {len(lstm_only)} LSTM-only symbols")
    elif lstm_wins > gru_wins:
        print("✅ LSTM models show better performance overall")
        print("   Recommendation: Prioritize LSTM for production deployment")
        print(f"   Action: Train LSTM models for the {len(gru_only)} GRU-only symbols")
    else:
        print("⚖️  LSTM and GRU models show equal performance")
        print("   Recommendation: Use GRU for faster inference (fewer parameters)")
        print("   Alternative: Use ensemble of both for better predictions")

    print()
    print("Next Steps:")
    print(f"1. Complete training for all {len(lstm_symbols | gru_symbols)} symbols with both model types")
    print("2. Retrain with 24-month CSV data (100 epochs) for production quality")
    print("3. Deploy best-performing models to production")
    print("4. Monitor real-world performance metrics")
    print()

    return comparison_data

if __name__ == '__main__':
    try:
        comparison_data = compare_models()

        # Save comparison data to JSON
        output_file = Path(__file__).parent / 'lstm_gru_comparison.json'
        with open(output_file, 'w') as f:
            json.dump({
                'generated_at': datetime.now().isoformat(),
                'comparisons': comparison_data
            }, f, indent=2)

        print(f"✅ Comparison data saved to: {output_file}")
        print()

        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
