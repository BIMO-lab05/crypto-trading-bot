"""Top-N liquid USDT linear perp selection, pinned to a dated JSON snapshot.

First consumer of Bybit's per-instrument `launchTime` in this repo (the
connector passes instrument dicts through raw). Survivorship caveat: pinning
today's top-N and backtesting 2y is survivorship-biased; the >=2y listing
filter mitigates but does not remove it. Verdict docs must carry this.
"""

from __future__ import annotations

import json
from pathlib import Path

from edge_lab.config import MIN_LISTING_AGE_DAYS, UNIVERSE_TOP_N

_DAY_MS = 86_400_000


def select_universe(
    tickers,
    instruments,
    now_ms,
    top_n=UNIVERSE_TOP_N,
    min_age_days=MIN_LISTING_AGE_DAYS,
):
    inst_by_symbol = {i.get("symbol"): i for i in instruments}
    selected, excluded = [], []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue  # not in scope at all, not "excluded"
        inst = inst_by_symbol.get(sym)
        if inst is None or inst.get("status") != "Trading":
            excluded.append(sym)
            continue
        ctype = inst.get("contractType")
        if ctype is not None and ctype != "LinearPerpetual":
            excluded.append(sym)
            continue
        launch = inst.get("launchTime")
        if not launch or now_ms - int(launch) < min_age_days * _DAY_MS:
            excluded.append(sym)
            continue
        selected.append(
            {
                "symbol": sym,
                "turnover24h": float(t.get("turnover24h") or 0.0),
                "launch_ms": int(launch),
            }
        )
    selected.sort(key=lambda d: d["turnover24h"], reverse=True)
    return selected[:top_n], sorted(excluded)


def write_pin(selected, excluded, date_str, dir_path) -> Path:
    dir_path = Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"universe_{date_str}.json"
    path.write_text(
        json.dumps(
            {
                "date": date_str,
                "top_n": UNIVERSE_TOP_N,
                "min_age_days": MIN_LISTING_AGE_DAYS,
                "symbols": selected,
                "excluded": excluded,
            },
            indent=2,
        )
    )
    return path


def load_pin(path) -> dict:
    return json.loads(Path(path).read_text())
