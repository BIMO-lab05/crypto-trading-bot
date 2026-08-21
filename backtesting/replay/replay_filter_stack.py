#!/usr/bin/env python3
"""
Stage 2 of the filter-stack replay: push historical indicator frames through
the LIVE aggregation + ensemble + entry-gate stack and report where signals die.

Runs in the trading-engine context (`services/trading-engine` on sys.path), so
`app.*` resolves to the engine. Stage 1 (`build_indicator_frames.py`) runs in
the TA context and hands over plain JSON — the two `app.*` namespaces cannot
coexist in one process.

What is replayed, in production order:

    CoreAggregator.aggregate_signals   per timeframe (15 / 60 / 240)
      voter -> gatekeeper -> validator -> regime -> category -> AND gate
    MultiTimeframeAnalyzer.analyze_timeframes   -> confidence modifier
    MultiStrategyEnsemble.generate_signal       -> leg vote, SL/TP
    entry gates                                 -> min_signal_confidence,
                                                   allowed sides, short floor

Every one of those is the deployed object, imported not reimplemented. The
per-stage accounting uses the same `SignalFunnel` the live engine writes to.

Costs: `app.costs.round_trip_cost_bps` with the Bybit linear-perp schedule and
the paper-engine slippage table. A configuration that looks profitable at zero
cost is not a result.

Data floor: 2026-04-25 (mainnet flip). Stage 1 refuses earlier bars.

Usage:
    python3 backtesting/replay/replay_filter_stack.py \\
        --frames <dir> --out <file.json> [--split-date 2026-07-01] \\
        [--min-signal-confidence 0.30] [--adx-threshold 25.0]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_ENGINE = os.path.join(_REPO_ROOT, "services", "trading-engine")
for p in (_ENGINE, _REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# `app.config` sets env_file=".env" RELATIVE TO CWD. Run from the repo root it
# picks up the operator's untracked .env and dies parsing cors_origins; run
# from the service dir it silently inherits a years-stale file. Pin it to None
# at import time — the singleton is built on first get_settings() — exactly as
# services/trading-engine/tests/conftest.py does. The defaults ARE production:
# the Dockerfile copies app/ only and no .env enters the image.
from app.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

from app.aggregation.aggregator_core import CoreAggregator  # noqa: E402
from app.aggregation.multi_timeframe import (  # noqa: E402
    MultiTimeframeAnalyzer,
)
from app.costs import FeeSchedule, Liquidity, round_trip_cost_bps  # noqa: E402
from app.models import IndicatorSignal, SignalAction  # noqa: E402
from app.monitoring.signal_funnel import get_signal_funnel  # noqa: E402
from app.paper_slippage import (  # noqa: E402
    DEFAULT_SLIPPAGE_BPS,
    FALLBACK_SLIPPAGE_BPS,
)
from app.strategies.hybrid_strategy_router import HybridStrategyRouter  # noqa: E402
from app.strategies.multi_strategy_ensemble import MultiStrategyEnsemble  # noqa: E402
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

MAINNET_FLIP_MS = 1777075200000  # 2026-04-25T00:00:00Z
TIMEFRAMES = ["15", "60", "240"]
PRIMARY = "60"
MAX_HOLD_BARS = 48  # 48h at 60m bars — mirrors the engine's max-hold rule


def _to_indicator(leg: Dict) -> IndicatorSignal:
    return IndicatorSignal(
        name=leg["name"],
        signal=SignalAction(leg["signal"]),
        confidence=float(leg["confidence"]),
        value=float(leg["value"]),
        metadata=dict(leg["metadata"]),
    )


def _load_frames(frames_dir: str, symbol: str, interval: str) -> List[Dict]:
    path = os.path.join(frames_dir, f"{symbol}_{interval}.jsonl")
    out = []
    with open(path) as fh:
        for line in fh:
            row = json.loads(line)
            if row["timestamp"] < MAINNET_FLIP_MS:
                raise SystemExit(
                    f"{path}: pre-2026-04-25 bar — testnet prices would poison the distributions"
                )
            out.append(row)
    return out


def _index_by_ts(rows: List[Dict]) -> List[int]:
    return [r["timestamp"] for r in rows]


class ReplayConfig:
    """Every tunable the replay varies. Defaults MUST mirror the deployed
    values so an unmodified run reproduces production."""

    def __init__(self, **kw):
        self.min_signal_confidence = kw.get("min_signal_confidence", 0.30)
        self.short_min_confidence = kw.get("short_min_confidence", 0.35)
        self.aggregator_min_confidence = kw.get("aggregator_min_confidence", 0.30)
        self.aggregator_min_consensus = kw.get("aggregator_min_consensus", 3)
        self.aggregator_min_category = kw.get("aggregator_min_category", 2)
        self.vote_threshold = kw.get("vote_threshold", 0.15)
        self.ensemble_threshold = kw.get("ensemble_threshold", 0.10)
        self.adx_threshold = kw.get("adx_threshold", 25.0)
        self.short_trading_enabled = kw.get("short_trading_enabled", True)

    def as_dict(self) -> Dict:
        return dict(self.__dict__)


class Replay:
    def __init__(self, cfg: ReplayConfig):
        self.cfg = cfg
        # MUST be the module singleton, not a fresh SignalFunnel(). The live
        # aggregator (`aggregator_core`) and the router (`_record_route`) both
        # write through `get_signal_funnel()`; a private instance here would
        # silently drop eight of the stages — the gatekeeper, the validator,
        # the vote threshold and the routing decision among them — and the
        # rejection table would read 0/0 for the very filters this exists to
        # measure. Reset so consecutive configs in one process do not pool.
        self.funnel = get_signal_funnel()
        self.funnel.reset()
        self.agg = CoreAggregator(enable_market_regime=True)
        self.agg.min_confidence = cfg.aggregator_min_confidence
        self.agg.min_consensus = cfg.aggregator_min_consensus
        self.agg.min_category_consensus = cfg.aggregator_min_category
        self.agg.voter.aggregation_threshold = cfg.vote_threshold
        self.mtf = MultiTimeframeAnalyzer()
        self.ensemble = MultiStrategyEnsemble()
        self.ensemble.AGGREGATION_THRESHOLD = cfg.ensemble_threshold
        self.router = HybridStrategyRouter()
        self.router.ADX_TRENDING_THRESHOLD = cfg.adx_threshold
        self.signals: List[Dict] = []
        self.missing_timeframes: Dict[str, List[str]] = {}

    async def _aggregate_one(self, legs: Dict, timestamp: int):
        indicators = {name: _to_indicator(leg) for name, leg in legs.items()}
        adx_meta = legs.get("ADX", {}).get("metadata", {})
        regime_analysis = self.agg.regime_detector._analyze_regime(
            {
                "adx": adx_meta.get("adx", legs.get("ADX", {}).get("value", 0.0)),
                "plus_di": adx_meta.get("plus_di", 0.0),
                "minus_di": adx_meta.get("minus_di", 0.0),
                "regime": adx_meta.get("regime", "UNKNOWN"),
                "direction": adx_meta.get("direction", "NEUTRAL"),
                "confidence": legs.get("ADX", {}).get("confidence", 0.5),
            }
        )
        atr_meta = legs.get("ATR", {}).get("metadata", {})
        signal = self.agg.aggregate_signals(
            indicators=indicators,
            timestamp=timestamp,
            atr_data=atr_meta or None,
            regime_analysis=regime_analysis,
        )
        return signal, indicators, atr_meta

    async def run_symbol(self, frames_dir: str, symbol: str) -> None:
        # A missing secondary timeframe degrades the multi-timeframe modifier
        # rather than aborting, but it is RECORDED — a replay that quietly
        # dropped the 240m leg would report a different confidence cascade
        # from production and never say so.
        per_tf = {}
        for tf in TIMEFRAMES:
            path = os.path.join(frames_dir, f"{symbol}_{tf}.jsonl")
            if os.path.exists(path):
                per_tf[tf] = _load_frames(frames_dir, symbol, tf)
            else:
                self.missing_timeframes.setdefault(symbol, []).append(tf)
        if PRIMARY not in per_tf:
            raise SystemExit(f"{symbol}: primary {PRIMARY}m frames missing")
        ts_index = {tf: _index_by_ts(rows) for tf, rows in per_tf.items()}
        import bisect

        for row in per_tf[PRIMARY]:
            ts = row["timestamp"]
            price = float(row["close"])
            self.funnel.gate("evaluations", True, symbol=symbol)
            self.funnel.gate("passed_risk_halt", True, symbol=symbol)

            signals = {}
            primary_indicators = None
            primary_atr = None
            for tf in per_tf:
                if tf == PRIMARY:
                    legs = row["legs"]
                else:
                    j = bisect.bisect_right(ts_index[tf], ts) - 1
                    if j < 0:
                        continue
                    legs = per_tf[tf][j]["legs"]
                sig, inds, atr = await self._aggregate_one(legs, ts)
                signals[tf] = sig
                if tf == PRIMARY:
                    primary_indicators = inds
                    primary_atr = atr

            if PRIMARY not in signals:
                self.funnel.reject(
                    "raw_signals_generated",
                    "primary_timeframe_missing",
                    symbol=symbol,
                )
                continue
            self.funnel.gate("raw_signals_generated", True, symbol=symbol)
            self.funnel.gate("passed_price_lookup", True, symbol=symbol)

            # Advisory routing — same call the live engine makes.
            self.router.observe_regime(primary_indicators, symbol=symbol)

            atr_pct = (primary_atr or {}).get("atr_pct")
            self.funnel.observe("atr_pct", atr_pct)
            self.funnel.gate("passed_atr_filter", True, symbol=symbol)

            primary = signals[PRIMARY]
            if len(signals) >= 2:
                mtf = await self.mtf.analyze_timeframes(signals, primary)
                primary.confidence = primary.confidence * mtf.confidence_modifier

            ens = self.ensemble.generate_signal(primary, price, capital=float(ACCOUNT_EQUITY_USD))
            # No `observed` here: the ensemble's own weighted score is not
            # exposed on a HOLD return, and the aggregator's vote score is a
            # DIFFERENT quantity. Reporting it against the ensemble threshold
            # would print two unrelated numbers side by side, which is exactly
            # the kind of false precision this funnel is supposed to remove.
            if not self.funnel.gate(
                "ensemble_signal_emitted",
                ens is not None,
                reason="ensemble_returned_hold",
                symbol=symbol,
                threshold=float(self.cfg.ensemble_threshold),
                detail="weighted leg score below threshold or no leg fired",
            ):
                continue

            conf = float(ens.confidence)
            self.funnel.observe("ensemble_confidence", conf)
            side = "LONG" if ens.action == SignalAction.BUY else "SHORT"

            self.funnel.gate("passed_position_dedupe", True, symbol=symbol)
            self.funnel.gate("passed_cooldown", True, symbol=symbol)

            if side == "SHORT" and not self.cfg.short_trading_enabled:
                self.funnel.gate(
                    "passed_side_gate",
                    False,
                    reason="short_trading_disabled",
                    symbol=symbol,
                )
                continue
            self.funnel.gate("passed_side_gate", True, symbol=symbol)

            floor = (
                self.cfg.short_min_confidence if side == "SHORT" else self.cfg.min_signal_confidence
            )
            reason = (
                "short_confidence_below_short_min_confidence"
                if side == "SHORT"
                else "confidence_below_min_signal_confidence"
            )
            if not self.funnel.gate(
                "passed_signal_confidence_gate",
                conf >= floor,
                reason=reason,
                symbol=symbol,
                observed=conf,
                threshold=float(floor),
            ):
                continue

            self.funnel.gate("passed_daily_limit", True, symbol=symbol)
            self.funnel.gate("passed_stop_consistency", True, symbol=symbol)
            self.funnel.gate("passed_portfolio_heat", True, symbol=symbol)
            self.funnel.gate("order_intent_emitted", True, symbol=symbol)

            self.signals.append(
                {
                    "symbol": symbol,
                    "timestamp": ts,
                    "action": ens.action.value,
                    "confidence": conf,
                    "entry": price,
                    "stop_loss": float(ens.stop_loss),
                    "take_profit": float(ens.take_profit),
                    "position_size_pct": float(ens.position_size_pct),
                    "leg_actions": dict(getattr(ens, "leg_actions", {}) or {}),
                }
            )


# --------------------------------------------------------------------------
# Trade simulation, net of costs
# --------------------------------------------------------------------------


# Real Bybit linear-perp specs, captured from the running bybit-connector on
# 2026-08-21 (`/api/v1/market/instruments-info?category=linear&symbol=...`).
# Pinned rather than fetched so a replay is reproducible offline; if Bybit
# changes a lot size, re-capture and record the date.
INSTRUMENTS: Dict[str, Dict[str, float]] = {
    "BTCUSDT": {"min_order_qty": 0.001, "qty_step": 0.001, "min_notional": 5.0},
    "ETHUSDT": {"min_order_qty": 0.01, "qty_step": 0.01, "min_notional": 5.0},
    "SOLUSDT": {"min_order_qty": 0.1, "qty_step": 0.1, "min_notional": 5.0},
    "BNBUSDT": {"min_order_qty": 0.01, "qty_step": 0.01, "min_notional": 5.0},
    "ADAUSDT": {"min_order_qty": 1.0, "qty_step": 1.0, "min_notional": 5.0},
}

# Notional cap as a PERCENT of equity — mirrors settings.max_position_size_pct.
MAX_POSITION_SIZE_PCT = 10.0

# Re-entry cooldown after an exit, seconds. Mirrors settings.sl_cooldown_seconds.
COOLDOWN_SECONDS = 14400


def sizing_verdict(symbol: str, price: float, size_pct: float, equity: float):
    """Mirror `_passes_min_notional` + `_snap_quantity_to_step`.

    Returns (ok, quantity, notional, reason). A trade below the venue floor is
    REJECTED with a reason — never clamped up. Clamping up is how a 10 % cap
    silently becomes a 40 % cap (.claude/rules/money.md).
    """
    spec = INSTRUMENTS.get(symbol)
    if spec is None:
        return False, 0.0, 0.0, "no_instrument_spec"
    cap_notional = equity * MAX_POSITION_SIZE_PCT / 100.0
    notional = min(equity * size_pct, cap_notional)
    step = spec["qty_step"]
    qty = math.floor((notional / price) / step) * step
    if qty < spec["min_order_qty"]:
        return False, qty, qty * price, "below_min_order_qty"
    actual = qty * price
    if actual < spec["min_notional"]:
        return False, qty, actual, "below_min_notional"
    return True, qty, actual, ""


def simulate(signals: List[Dict], klines_dir: str, equity: float):
    """Walk each signal forward to SL, TP, or the 48-bar max hold.

    Deliberately conservative:
      - entry at the signal bar's close (the price the engine would see)
      - a bar that touches BOTH stop and target counts as a STOP. Assuming the
        favourable fill is the single most common way a replay invents edge
        that does not exist.
      - **one open position per symbol at a time**, plus the post-exit
        cooldown. Without this every bar in a persistent signal state becomes
        an independent trade, and the trade count, expectancy and drawdown all
        describe something the engine cannot do — it blocks re-entry while a
        position is open (`_check_symbol_cooldown`, the open-slot claim).
      - min-notional / min-qty rejection per symbol. On a $100 account most of
        the validated universe cannot clear the venue floor at a 10 % cap;
        tuning on trades that cannot exist would be worse than not tuning.
      - costs are a full taker round trip plus one-way slippage per leg.

    Returns (trades, skipped_counter).
    """
    import csv

    bars: Dict[str, List[Dict]] = {}
    for sig in signals:
        sym = sig["symbol"]
        if sym in bars:
            continue
        with open(os.path.join(klines_dir, f"{sym}_60.csv")) as fh:
            bars[sym] = [
                {k: float(v) for k, v in row.items()} for row in csv.DictReader(fh)
            ]

    schedule = FeeSchedule.bybit_linear_perp()
    trades = []
    skipped: Counter = Counter()
    busy_until: Dict[str, int] = {}

    for sig in sorted(signals, key=lambda x: (x["symbol"], x["timestamp"])):
        sym = sig["symbol"]

        # one position per symbol + post-exit cooldown
        if sig["timestamp"] < busy_until.get(sym, 0):
            skipped["blocked_position_open_or_cooldown"] += 1
            continue

        # venue floor — reject, never clamp up
        ok, qty, notional, why = sizing_verdict(
            sym, sig["entry"], sig["position_size_pct"], equity
        )
        if not ok:
            skipped[f"{sym}:{why}"] += 1
            continue

        series = bars[sig["symbol"]]
        idx = next(
            (i for i, b in enumerate(series) if b["timestamp"] > sig["timestamp"]),
            None,
        )
        if idx is None:
            continue
        entry = sig["entry"]
        sl, tp = sig["stop_loss"], sig["take_profit"]
        is_long = sig["action"] == "BUY"
        exit_price, exit_reason, held = None, None, 0
        for j in range(idx, min(idx + MAX_HOLD_BARS, len(series))):
            bar = series[j]
            held = j - idx + 1
            hit_sl = bar["low"] <= sl if is_long else bar["high"] >= sl
            hit_tp = bar["high"] >= tp if is_long else bar["low"] <= tp
            if hit_sl:  # stop wins ties — see docstring
                exit_price, exit_reason = sl, "stop"
                break
            if hit_tp:
                exit_price, exit_reason = tp, "target"
                break
        if exit_price is None:
            j = min(idx + MAX_HOLD_BARS, len(series)) - 1
            exit_price, exit_reason = series[j]["close"], "max_hold"
            held = j - idx + 1

        gross_ret = (exit_price - entry) / entry
        if not is_long:
            gross_ret = -gross_ret
        cost_bps = round_trip_cost_bps(
            sig["symbol"],
            entry_liquidity=Liquidity.TAKER,
            exit_liquidity=Liquidity.TAKER,
            schedule=schedule,
            slippage_table=DEFAULT_SLIPPAGE_BPS,
            slippage_fallback=FALLBACK_SLIPPAGE_BPS,
        )
        net_ret = gross_ret - float(cost_bps) / 10000.0
        risk = abs(entry - sl) / entry
        exit_ts = series[min(idx + held - 1, len(series) - 1)]["timestamp"]
        busy_until[sym] = int(exit_ts) + COOLDOWN_SECONDS * 1000
        trades.append(
            {
                **sig,
                "quantity": qty,
                "notional_usd": notional,
                "exit": exit_price,
                "exit_ts": int(exit_ts),
                "exit_reason": exit_reason,
                "bars_held": held,
                "gross_return": gross_ret,
                "cost_bps": float(cost_bps),
                "net_return": net_ret,
                "net_pnl_usd": net_ret * notional,
                "r_multiple": (net_ret / risk) if risk > 0 else 0.0,
            }
        )
    return trades, skipped


def summarise(trades: List[Dict]) -> Dict:
    if not trades:
        return {
            "trades": 0,
            "win_rate_pct": None,
            "avg_net_return_pct": None,
            "avg_r": None,
            "expectancy_pct": None,
            "total_net_return_pct": None,
            "max_drawdown_pct": None,
            "profit_factor": None,
        }
    # Chronological, not append order: `simulate` groups by symbol, and a
    # drawdown computed over symbol-blocked returns is meaningless.
    ordered = sorted(trades, key=lambda t: t["timestamp"])
    nets = [t["net_return"] for t in ordered]
    wins = [n for n in nets if n > 0]
    losses = [-n for n in nets if n < 0]
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for n in nets:
        equity *= 1 + n
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    return {
        "trades": len(trades),
        "win_rate_pct": 100.0 * len(wins) / len(trades),
        "avg_net_return_pct": 100.0 * sum(nets) / len(nets),
        "avg_r": sum(t["r_multiple"] for t in trades) / len(trades),
        # Expectancy per trade == mean net return; kept explicit because the
        # mission asks for expectancy, not trade count.
        "expectancy_pct": 100.0 * sum(nets) / len(nets),
        "total_net_return_pct": 100.0 * (equity - 1.0),
        "max_drawdown_pct": 100.0 * max_dd,
        # Pooled, NOT the mean of per-fold PFs (see the PF pooling note in
        # the project memory) — mean-of-folds drags toward 1.0 on small folds.
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
    }


async def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,ADAUSDT")
    ap.add_argument(
        "--split-date",
        default="",
        help="ISO date; trades before it are IN-SAMPLE, on/after are OUT-OF-SAMPLE",
    )
    ap.add_argument("--label", default="baseline")
    for name, default in (
        ("min-signal-confidence", 0.30),
        ("short-min-confidence", 0.35),
        ("aggregator-min-confidence", 0.30),
        ("vote-threshold", 0.15),
        ("ensemble-threshold", 0.10),
        ("adx-threshold", 25.0),
    ):
        ap.add_argument(f"--{name}", type=float, default=default)
    ap.add_argument("--aggregator-min-consensus", type=int, default=3)
    ap.add_argument("--aggregator-min-category", type=int, default=2)
    args = ap.parse_args()

    cfg = ReplayConfig(
        min_signal_confidence=args.min_signal_confidence,
        short_min_confidence=args.short_min_confidence,
        aggregator_min_confidence=args.aggregator_min_confidence,
        aggregator_min_consensus=args.aggregator_min_consensus,
        aggregator_min_category=args.aggregator_min_category,
        vote_threshold=args.vote_threshold,
        ensemble_threshold=args.ensemble_threshold,
        adx_threshold=args.adx_threshold,
    )
    replay = Replay(cfg)
    requested = args.symbols.split(",")
    included, excluded = [], {}
    for symbol in requested:
        path = os.path.join(args.frames, f"{symbol}_{PRIMARY}.jsonl")
        if not os.path.exists(path):
            # No silent caps: an absent symbol is recorded in the report, not
            # just printed.
            excluded[symbol] = "no indicator frames on disk"
            print(f"  SKIP {symbol}: no frames at {path}", flush=True)
            continue
        await replay.run_symbol(args.frames, symbol)
        included.append(symbol)
        print(f"  {symbol}: {len(replay.signals)} cumulative signals", flush=True)

    trades, skipped = simulate(
        replay.signals, args.klines, float(ACCOUNT_EQUITY_USD)
    )

    split_ms = None
    if args.split_date:
        split_ms = int(
            datetime.fromisoformat(args.split_date).replace(tzinfo=timezone.utc).timestamp() * 1000
        )

    report = {
        "label": args.label,
        "config": cfg.as_dict(),
        "account_equity_usd": float(ACCOUNT_EQUITY_USD),
        "cost_model": {
            "schedule": "bybit_linear_perp taker 0.055% / maker 0.020%",
            "legs": "TAKER entry + TAKER exit",
            "slippage_table_bps": {k: float(v) for k, v in DEFAULT_SLIPPAGE_BPS.items()},
            "slippage_fallback_bps": float(FALLBACK_SLIPPAGE_BPS),
        },
        "symbols_requested": requested,
        "symbols_included": included,
        "symbols_excluded": excluded,
        "sizing": {
            "max_position_size_pct": MAX_POSITION_SIZE_PCT,
            "cooldown_seconds": COOLDOWN_SECONDS,
            "one_open_position_per_symbol": True,
            "instruments": INSTRUMENTS,
        },
        "timeframes": TIMEFRAMES,
        "missing_timeframes": replay.missing_timeframes,
        "signals_emitted": len(replay.signals),
        "signals_not_traded": dict(skipped),
        "funnel": replay.funnel.snapshot(),
        "routing": replay.router.get_stats(),
        "all": summarise(trades),
        "leg_action_counts": dict(
            Counter(f"{k}:{v}" for t in trades for k, v in (t.get("leg_actions") or {}).items())
        ),
    }
    if split_ms:
        report["in_sample"] = summarise([t for t in trades if t["timestamp"] < split_ms])
        report["out_of_sample"] = summarise([t for t in trades if t["timestamp"] >= split_ms])
        report["split_date"] = args.split_date

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    with open(args.out.replace(".json", "_trades.json"), "w") as fh:
        json.dump(trades, fh, indent=2, default=str)
    print(json.dumps(report["all"], indent=2))
    if skipped:
        print("signals emitted but NOT traded:")
        for k, v in sorted(skipped.items(), key=lambda kv: -kv[1]):
            print(f"  {k}: {v}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
