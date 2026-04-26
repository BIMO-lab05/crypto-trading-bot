"""Backtest the MultiStrategyEnsemble vs SimpleRSI / MeanReversion / a baseline buy-and-hold.

Pulls hourly klines from TimescaleDB (running in the docker network — uses DB_HOST env or
falls back to the host-mapped 5433 port), computes indicators inline so it doesn't depend
on the technical-analysis service, builds the same `IndicatorSignal` / `TradingSignal`
shapes the aggregator returns, then replays each candle through every strategy and the
ensemble. Tracks P&L, win rate, max drawdown, and Sharpe.

Run from the host:
    docker exec -e PYTHONPATH=/app crypto-bot-trading python -m scripts.backtest_ensemble

Or locally with DB tunneled:
    DB_HOST=localhost DB_PORT=5433 python services/trading-engine/scripts/backtest_ensemble.py
"""

from __future__ import annotations

import os
import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # /app

from app.models.signal import IndicatorSignal, TradingSignal
from app.models.enums import SignalAction
from app.strategies.simple_rsi_strategy import SimpleRSIStrategy
from app.strategies.mean_reversion_strategy import MeanReversionStrategy
from app.strategies.multi_strategy_ensemble import (
    MultiStrategyEnsemble, get_ensemble_weights, LEG_RSI, LEG_MULTI, LEG_MEAN_REV,
)


# ----------------------------- DB ---------------------------------------------

def fetch_klines(symbol: str, limit: int = 1500) -> List[Dict]:
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5433"))
    user = os.getenv("DB_USER", "cryptobot")
    password = os.getenv("DB_PASSWORD", "cryptobot_secure_2024")
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="market_data")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT timestamp, open, high, low, close, volume FROM klines "
                "WHERE symbol=%s AND interval=%s ORDER BY timestamp ASC LIMIT %s",
                (symbol, "60", limit),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ----------------------------- Indicators -------------------------------------

def rsi_series(closes: List[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_g = sum(gains) / period; avg_l = sum(losses) / period
    rs = avg_g / avg_l if avg_l > 0 else float("inf")
    out[period] = 100 - 100 / (1 + rs) if avg_l > 0 else 100.0
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g, l = max(d, 0), max(-d, 0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        rs = avg_g / avg_l if avg_l > 0 else float("inf")
        out[i] = 100 - 100 / (1 + rs) if avg_l > 0 else 100.0
    return out


def sma(closes: List[float], period: int, i: int) -> Optional[float]:
    if i + 1 < period:
        return None
    return sum(closes[i - period + 1 : i + 1]) / period


def stddev(closes: List[float], period: int, i: int, mean: float) -> Optional[float]:
    if i + 1 < period:
        return None
    window = closes[i - period + 1 : i + 1]
    return math.sqrt(sum((c - mean) ** 2 for c in window) / period)


def atr_pct(highs: List[float], lows: List[float], closes: List[float], i: int, period: int = 14) -> Optional[float]:
    if i < period:
        return None
    trs = []
    for j in range(i - period + 1, i + 1):
        if j == 0:
            trs.append(highs[j] - lows[j])
        else:
            trs.append(max(highs[j] - lows[j], abs(highs[j] - closes[j - 1]), abs(lows[j] - closes[j - 1])))
    return (sum(trs) / period) / closes[i] if closes[i] else None


# ----------------------------- Signal builder ---------------------------------

def build_indicator_dict(
    closes: List[float], highs: List[float], lows: List[float], rsis: List[Optional[float]], i: int
) -> Optional[Dict[str, IndicatorSignal]]:
    rsi = rsis[i]
    if rsi is None:
        return None
    bb_period = 20
    bb_mid = sma(closes, bb_period, i)
    if bb_mid is None:
        return None
    sd = stddev(closes, bb_period, i, bb_mid)
    if sd is None:
        return None
    bb_lower, bb_upper = bb_mid - 2.5 * sd, bb_mid + 2.5 * sd
    price = closes[i]
    bb_position = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper > bb_lower else 0.5
    sma20 = bb_mid
    a_pct = atr_pct(highs, lows, closes, i)
    if a_pct is None:
        return None

    def sig(name: str, action: SignalAction, conf: float, **meta) -> IndicatorSignal:
        return IndicatorSignal(name=name, signal=action, confidence=conf, value=meta.get("value"), metadata=meta)

    rsi_action = SignalAction.BUY if rsi <= 30 else SignalAction.SELL if rsi >= 70 else SignalAction.HOLD
    bb_action = SignalAction.BUY if bb_position <= 0.1 else SignalAction.SELL if bb_position >= 0.9 else SignalAction.HOLD
    sma_action = SignalAction.BUY if price > sma20 else SignalAction.SELL

    return {
        "RSI": sig("RSI", rsi_action, 0.5, value=rsi),
        "BOLLINGER_BANDS": sig("BOLLINGER_BANDS", bb_action, 0.4, position=bb_position, lower=bb_lower, upper=bb_upper, middle=bb_mid),
        "SMA": sig("SMA", sma_action, 0.3, value=sma20),
        "ATR": sig("ATR", SignalAction.HOLD, 0.0, value=a_pct, atr_pct=a_pct),
    }


def build_trading_signal(indicators: Dict[str, IndicatorSignal], price: float, ts: int) -> TradingSignal:
    """Mimic the aggregator's `multi-indicator` consensus output.

    Use a simple voting rule: average the BUY/SELL signs of RSI/BB/SMA, weighted by their
    confidences, to derive an action + score in [-1, 1].
    """
    score = 0.0; tot = 0.0
    for name in ("RSI", "BOLLINGER_BANDS", "SMA"):
        ind = indicators.get(name)
        if not ind:
            continue
        sign = 1.0 if ind.signal == SignalAction.BUY else -1.0 if ind.signal == SignalAction.SELL else 0.0
        score += sign * ind.confidence
        tot += ind.confidence
    score = score / tot if tot > 0 else 0.0
    if score > 0.20:
        action = SignalAction.BUY
    elif score < -0.20:
        action = SignalAction.SELL
    else:
        action = SignalAction.HOLD
    consensus = sum(
        1 for n in ("RSI", "BOLLINGER_BANDS", "SMA")
        if indicators.get(n) and indicators[n].signal == action
    )
    return TradingSignal(
        symbol="X",
        timestamp=ts,
        action=action,
        confidence=min(abs(score), 1.0),
        indicators=indicators,
        aggregated_score=score,
        consensus_count=consensus,
        metadata={"atr_stop_loss": price * (1 - 0.02), "atr_take_profit": price * (1 + 0.04)},
    )


# ----------------------------- Backtest engine --------------------------------

@dataclass
class TradeRecord:
    symbol: str
    side: str          # "LONG" or "SHORT"
    entry_ts: int
    entry: float
    exit_ts: int
    exit: float
    qty: float
    pnl: float
    pnl_pct: float
    legs: Dict[str, float] = field(default_factory=dict)
    label: str = ""


@dataclass
class StrategyResult:
    name: str
    trades: List[TradeRecord] = field(default_factory=list)
    equity: List[Tuple[int, float]] = field(default_factory=list)

    def summary(self, starting_balance: float) -> Dict:
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        win_rate = len(wins) / len(self.trades) if self.trades else 0.0
        total_pnl = sum(t.pnl for t in self.trades)
        equity_vals = [v for _, v in self.equity] or [starting_balance]
        peak = equity_vals[0]; max_dd = 0.0
        for v in equity_vals:
            peak = max(peak, v)
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        rets = [t.pnl_pct for t in self.trades]
        sharpe = (statistics.mean(rets) / statistics.stdev(rets) * math.sqrt(252)) if len(rets) > 1 and statistics.stdev(rets) > 0 else 0.0
        avg_win = statistics.mean([t.pnl for t in wins]) if wins else 0.0
        avg_loss = statistics.mean([t.pnl for t in losses]) if losses else 0.0
        return {
            "name": self.name,
            "trades": len(self.trades),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 4),
            "ending_balance": round(starting_balance + total_pnl, 4),
            "return_pct": round((total_pnl / starting_balance) * 100, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "sharpe": round(sharpe, 2),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": round(abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)), 2) if losses and sum(t.pnl for t in losses) != 0 else 0.0,
        }


def replay(
    klines: List[Dict],
    symbol: str,
    starting_balance: float = 100.0,
    risk_per_trade: float = 0.02,
    max_hold_bars: int = 48,
) -> Dict[str, StrategyResult]:
    closes = [float(k["close"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    rsis = rsi_series(closes, 14)
    timestamps = [int(k["timestamp"]) for k in klines]

    rsi_strat = SimpleRSIStrategy()
    mr_strat = MeanReversionStrategy()
    ensemble = MultiStrategyEnsemble(mean_reversion=mr_strat)

    results: Dict[str, StrategyResult] = {
        "simple_rsi": StrategyResult("SimpleRSI"),
        "mean_reversion": StrategyResult("MeanReversion"),
        "multi_indicator": StrategyResult("MultiIndicator"),
        "ensemble": StrategyResult("Ensemble"),
    }
    balances: Dict[str, float] = {k: starting_balance for k in results}
    open_pos: Dict[str, Optional[Dict]] = {k: None for k in results}

    for i in range(20, len(klines)):
        price = closes[i]; ts = timestamps[i]
        ind = build_indicator_dict(closes, highs, lows, rsis, i)
        if ind is None:
            continue
        agg = build_trading_signal(ind, price, ts)

        # Close on stop / target / max-hold
        for strat_name, pos in list(open_pos.items()):
            if pos is None:
                continue
            sl, tp = pos["sl"], pos["tp"]
            hit_sl = (pos["side"] == "LONG" and lows[i] <= sl) or (pos["side"] == "SHORT" and highs[i] >= sl)
            hit_tp = (pos["side"] == "LONG" and highs[i] >= tp) or (pos["side"] == "SHORT" and lows[i] <= tp)
            timed_out = (i - pos["entry_idx"]) >= max_hold_bars
            if hit_sl or hit_tp or timed_out:
                exit_price = sl if hit_sl else tp if hit_tp else price
                pnl_per_unit = (exit_price - pos["entry"]) if pos["side"] == "LONG" else (pos["entry"] - exit_price)
                pnl = pnl_per_unit * pos["qty"]
                pnl_pct = pnl_per_unit / pos["entry"] if pos["entry"] > 0 else 0.0
                trade = TradeRecord(
                    symbol=symbol, side=pos["side"], entry_ts=pos["entry_ts"], entry=pos["entry"],
                    exit_ts=ts, exit=exit_price, qty=pos["qty"], pnl=pnl, pnl_pct=pnl_pct,
                    legs=pos.get("legs", {}), label="SL" if hit_sl else "TP" if hit_tp else "TIMEOUT",
                )
                results[strat_name].trades.append(trade)
                balances[strat_name] += pnl
                results[strat_name].equity.append((ts, balances[strat_name]))
                if strat_name == "ensemble" and pos.get("legs"):
                    ensemble.record_trade_outcome(pos["legs"], pnl)
                open_pos[strat_name] = None

        # Open new positions
        if open_pos["simple_rsi"] is None:
            s = rsi_strat.generate_signal(ind, price, balances["simple_rsi"])
            if s and s.action != SignalAction.HOLD:
                qty = (balances["simple_rsi"] * risk_per_trade) / abs(price - s.stop_loss) if price != s.stop_loss else 0.0
                if qty > 0:
                    open_pos["simple_rsi"] = {"side": "LONG" if s.action == SignalAction.BUY else "SHORT",
                                              "entry": price, "entry_ts": ts, "entry_idx": i,
                                              "sl": s.stop_loss, "tp": s.take_profit, "qty": qty}

        if open_pos["mean_reversion"] is None:
            s = mr_strat.generate_signal(ind, price, balances["mean_reversion"])
            if s and s.action != SignalAction.HOLD:
                qty = (balances["mean_reversion"] * risk_per_trade) / abs(price - s.stop_loss) if price != s.stop_loss else 0.0
                if qty > 0:
                    open_pos["mean_reversion"] = {"side": "LONG" if s.action == SignalAction.BUY else "SHORT",
                                                  "entry": price, "entry_ts": ts, "entry_idx": i,
                                                  "sl": s.stop_loss, "tp": s.target, "qty": qty}

        if open_pos["multi_indicator"] is None and agg.action != SignalAction.HOLD and agg.confidence > 0.20:
            sl = float(agg.metadata.get("atr_stop_loss", price * 0.98))
            tp = float(agg.metadata.get("atr_take_profit", price * 1.04))
            qty = (balances["multi_indicator"] * risk_per_trade) / abs(price - sl) if price != sl else 0.0
            if qty > 0:
                open_pos["multi_indicator"] = {"side": "LONG" if agg.action == SignalAction.BUY else "SHORT",
                                               "entry": price, "entry_ts": ts, "entry_idx": i,
                                               "sl": sl, "tp": tp, "qty": qty}

        if open_pos["ensemble"] is None:
            es = ensemble.generate_signal(agg, price, balances["ensemble"])
            if es:
                qty = balances["ensemble"] * es.position_size_pct / price
                open_pos["ensemble"] = {"side": "LONG" if es.action == SignalAction.BUY else "SHORT",
                                        "entry": price, "entry_ts": ts, "entry_idx": i,
                                        "sl": es.stop_loss, "tp": es.take_profit, "qty": qty,
                                        "legs": es.leg_contributions}

    return results, balances


def main():
    symbols = os.getenv("BACKTEST_SYMBOLS", "SOLUSDT,BNBUSDT,ADAUSDT").split(",")
    starting_balance = float(os.getenv("BACKTEST_BALANCE", "100"))
    overall = {}
    for symbol in symbols:
        print(f"\n=== {symbol} ===")
        klines = fetch_klines(symbol)
        print(f"Loaded {len(klines)} klines")
        if len(klines) < 50:
            print("  (skip — not enough data)")
            continue
        results, balances = replay(klines, symbol, starting_balance=starting_balance)
        rows = []
        for k in ("simple_rsi", "mean_reversion", "multi_indicator", "ensemble"):
            s = results[k].summary(starting_balance)
            rows.append(s)
            print(
                f"  {s['name']:<16} trades={s['trades']:<3} win_rate={s['win_rate']*100:>5.1f}% "
                f"P&L=${s['total_pnl']:>+8.2f} ({s['return_pct']:>+6.2f}%) "
                f"DD={s['max_drawdown_pct']:>5.2f}% Sharpe={s['sharpe']:>5.2f} "
                f"PF={s['profit_factor']:.2f}"
            )
        overall[symbol] = rows

    # Aggregate across symbols
    print("\n=== AGGREGATE (all symbols summed) ===")
    for k in ("simple_rsi", "mean_reversion", "multi_indicator", "ensemble"):
        total_trades = sum(r[i]["trades"] for r in [v for v in overall.values()] for i in range(len(r)) if r[i]["name"].lower().replace(" ", "_") == k.replace("_", ""))
        # Cleaner: iterate by index
    # Simpler: re-iterate
    by_strat: Dict[str, Dict] = {k: {"trades": 0, "pnl": 0.0, "wins": 0} for k in ("simple_rsi", "mean_reversion", "multi_indicator", "ensemble")}
    name_map = {"SimpleRSI": "simple_rsi", "MeanReversion": "mean_reversion", "MultiIndicator": "multi_indicator", "Ensemble": "ensemble"}
    for sym, rows in overall.items():
        for r in rows:
            k = name_map[r["name"]]
            by_strat[k]["trades"] += r["trades"]
            by_strat[k]["pnl"] += r["total_pnl"]
    for k, v in by_strat.items():
        print(f"  {k:<16} trades={v['trades']:<4} total_P&L=${v['pnl']:>+9.2f}")

    # Print final ensemble weights
    w = get_ensemble_weights().snapshot()
    print(f"\nEnsemble weights after backtest: {w['weights']}")
    print(f"Win-rate EMA per leg:           {w['win_rates']}")
    print(f"Trade counts per leg:           {w['trade_counts']}")


if __name__ == "__main__":
    main()
