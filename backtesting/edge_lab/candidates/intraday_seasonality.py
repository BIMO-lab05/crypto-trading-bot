"""Battery #3 candidate: intraday seasonality on hourly perp bars.

Hypothesis: funding-settlement positioning creates repeatable pre-funding
drift; hour-of-day flow imbalances create repeatable strong/weak hours.
All statistics are rolling 30-day windows over data strictly BEFORE the
decision time — no full-history stats (leakage rule).
"""

from __future__ import annotations

import pandas as pd

from edge_lab.trades import Trade, Variant

CLEAN_EPOCH_MS = int(pd.Timestamp("2026-04-25").timestamp() * 1000)
ROLL_DAYS = 30
FUNDING_HOURS_UTC = (0, 8, 16)

VARIANTS: list[Variant] = [
    Variant("intraday_seasonality", "funding_window_drift", (("roll_days", 30),)),
    Variant("intraday_seasonality", "hour_of_day", (("roll_days", 30),)),
]


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    d = df.sort_values("ts_ms").reset_index(drop=True).copy()
    ts = pd.to_datetime(d["ts_ms"], unit="ms", utc=True)
    d["hour"] = ts.dt.hour
    d["ret"] = d["close"].pct_change()
    return d


def _funding_window_drift(d: pd.DataFrame, symbol: str) -> list[Trade]:
    trades: list[Trade] = []
    # Return of the hour ENDING at each funding settlement (entry = prior bar
    # close, exit = settlement bar close).
    for i in range(ROLL_DAYS * 24, len(d) - 1):
        nxt = d.iloc[i + 1]
        if nxt["hour"] not in FUNDING_HOURS_UTC or nxt["ts_ms"] < CLEAN_EPOCH_MS:
            continue
        # Rolling mean of PRIOR pre-funding-hour returns (strictly before bar i+1).
        hist = d.iloc[: i + 1]
        prior = hist[hist["hour"].isin(FUNDING_HOURS_UTC)]["ret"].tail(
            ROLL_DAYS * len(FUNDING_HOURS_UTC)
        )
        if len(prior) < 20 or prior.mean() == 0:
            continue
        side = "LONG" if prior.mean() > 0 else "SHORT"
        trades.append(
            Trade(
                symbol,
                side,
                int(d.iloc[i]["ts_ms"]),
                int(nxt["ts_ms"]),
                float(d.iloc[i]["close"]),
                float(nxt["close"]),
            )
        )
    return trades


def _hour_of_day(d: pd.DataFrame, symbol: str) -> list[Trade]:
    trades: list[Trade] = []
    ts = pd.to_datetime(d["ts_ms"], unit="ms", utc=True)
    d = d.assign(date=ts.dt.date)
    for day, day_rows in d.groupby("date"):
        first_idx = day_rows.index[0]
        if first_idx < ROLL_DAYS * 24 or day_rows.iloc[0]["ts_ms"] < CLEAN_EPOCH_MS:
            continue
        hist = d.loc[: first_idx - 1].tail(ROLL_DAYS * 24)
        by_hour = hist.groupby("hour")["ret"].mean()
        if by_hour.isna().any() or len(by_hour) < 24:
            continue
        strong, weak = int(by_hour.idxmax()), int(by_hour.idxmin())
        for hour, side in ((strong, "LONG"), (weak, "SHORT")):
            bar = day_rows[day_rows["hour"] == hour]
            if bar.empty:
                continue
            i = bar.index[0]
            if i == 0 or i + 1 >= len(d):
                continue
            trades.append(
                Trade(
                    symbol,
                    side,
                    int(d.loc[i - 1, "ts_ms"]),
                    int(d.loc[i, "ts_ms"]),
                    float(d.loc[i - 1, "close"]),
                    float(d.loc[i, "close"]),
                )
            )
    return trades


def generate_trades(h1: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]:
    fn = (
        _funding_window_drift
        if variant.name == "funding_window_drift"
        else _hour_of_day
    )
    out: list[Trade] = []
    for symbol, df in h1.items():
        out.extend(fn(_prep(df), symbol))
    return out
