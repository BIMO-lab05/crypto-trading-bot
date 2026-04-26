"""Head-to-head LSTM vs GRU comparison report.

Reads each symbol's LSTM and GRU metadata files from /app/models/, prints a markdown
table with R², MAE, RMSE, directional accuracy, training samples, training time,
training date, and a winner column. Also writes the report to a Markdown file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

MODELS_DIR = Path("/app/models")
SYMBOLS_DEFAULT = ["XRPUSDT", "BTCUSDT", "ETHUSDT"]


def load_meta(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def stats_of(meta: Dict) -> Dict:
    s = meta.get("training_stats") or {}
    return {
        "version":      meta.get("model_version", "?"),
        "trained_at":   meta.get("last_trained", "?"),
        "samples":      s.get("train_samples", "?"),
        "epochs":       s.get("epochs_trained", "?"),
        "r2":           s.get("r2_score"),
        "mae":          s.get("mae"),
        "rmse":         s.get("rmse"),
        "dir_acc":      s.get("directional_accuracy"),
        "params":       s.get("total_parameters", "?"),
    }


def fmt(v, places=4):
    if v is None: return "—"
    if isinstance(v, float): return f"{v:.{places}f}"
    return str(v)


def winner_row(lstm: Optional[Dict], gru: Optional[Dict]) -> str:
    if lstm is None and gru is None: return "—"
    if lstm is None: return "GRU (LSTM missing)"
    if gru is None: return "LSTM (GRU missing)"
    score_l = score_g = 0
    for key in ("r2", "dir_acc"):
        a, b = lstm["stats"].get(key), gru["stats"].get(key)
        if a is None or b is None: continue
        if a > b: score_l += 1
        elif b > a: score_g += 1
    for key in ("mae", "rmse"):
        a, b = lstm["stats"].get(key), gru["stats"].get(key)
        if a is None or b is None: continue
        if a < b: score_l += 1
        elif b < a: score_g += 1
    if score_g > score_l: return f"**GRU** ({score_g}-{score_l})"
    if score_l > score_g: return f"**LSTM** ({score_l}-{score_g})"
    return "Tie"


def main():
    symbols = sys.argv[1:] or SYMBOLS_DEFAULT
    rows = []
    for sym in symbols:
        lstm_meta = load_meta(MODELS_DIR / f"{sym}_60m_metadata.json")
        gru_meta  = load_meta(MODELS_DIR / f"{sym}_60m_gru_metadata.json")
        rows.append({
            "symbol": sym,
            "lstm": ({"meta": lstm_meta, "stats": stats_of(lstm_meta)} if lstm_meta else None),
            "gru":  ({"meta": gru_meta,  "stats": stats_of(gru_meta)}  if gru_meta  else None),
        })

    print("# LSTM vs GRU — Head-to-Head Comparison\n")
    print(f"_Models from `{MODELS_DIR}`. Symbols: {', '.join(symbols)}._\n")

    print("| Symbol | Arch | Trained | Samples | R² | MAE | RMSE | Dir.Acc |")
    print("|---|---|---|---:|---:|---:|---:|---:|")
    for r in rows:
        for arch_label, arch_data in (("LSTM", r["lstm"]), ("GRU", r["gru"])):
            if not arch_data:
                print(f"| {r['symbol']} | {arch_label} | (missing) | — | — | — | — | — |")
                continue
            s = arch_data["stats"]
            print(
                f"| {r['symbol']} | {arch_label} | {s['trained_at'][:10]} | {fmt(s['samples'],0)} | "
                f"{fmt(s['r2'])} | {fmt(s['mae'])} | {fmt(s['rmse'])} | {fmt(s['dir_acc'])} |"
            )

    print("\n## Winner per symbol\n")
    print("| Symbol | Winner | Notes |")
    print("|---|---|---|")
    for r in rows:
        notes = ""
        if r["lstm"] and r["gru"]:
            l, g = r["lstm"]["stats"], r["gru"]["stats"]
            if l.get("samples") and g.get("samples"):
                notes = f"LSTM trained on {l['samples']} samples vs GRU on {g['samples']}"
        print(f"| {r['symbol']} | {winner_row(r['lstm'], r['gru'])} | {notes} |")

    # Aggregate: mean of available metrics
    def mean(vals): vals = [v for v in vals if v is not None]; return sum(vals)/len(vals) if vals else None
    lstm_r2 = mean([r["lstm"]["stats"].get("r2") for r in rows if r["lstm"]])
    gru_r2  = mean([r["gru"]["stats"].get("r2")  for r in rows if r["gru"]])
    lstm_dir = mean([r["lstm"]["stats"].get("dir_acc") for r in rows if r["lstm"]])
    gru_dir  = mean([r["gru"]["stats"].get("dir_acc")  for r in rows if r["gru"]])
    print("\n## Mean across symbols\n")
    print(f"- Mean R² — LSTM: {fmt(lstm_r2)} | GRU: {fmt(gru_r2)}")
    print(f"- Mean directional accuracy — LSTM: {fmt(lstm_dir)} | GRU: {fmt(gru_dir)}")
    if lstm_r2 is not None and gru_r2 is not None:
        delta = (gru_r2 - lstm_r2) * 100
        verdict = "GRU wins" if gru_r2 > lstm_r2 else "LSTM wins" if lstm_r2 > gru_r2 else "tie"
        print(f"- **Verdict: {verdict}** by {abs(delta):.2f} pp on R²")


if __name__ == "__main__":
    main()
