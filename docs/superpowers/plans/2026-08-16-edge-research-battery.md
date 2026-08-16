# Edge Research Battery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `backtesting/edge_lab/` — a unified kill-funnel that runs 4 strategy candidates (8 variants) over a top-30 Bybit perp universe through identical gates (data sanity → 2× cost hurdle → CPCV/DSR → hostile review) and emits one killtest-style verdict per candidate.

**Architecture:** Host-run Python package under `backtesting/edge_lab/` + tests under `tests/edge_lab/`. Reuses `screen.py`'s `screen_trades()` for Gate 1 and `killtests/offline_ensemble._load_kernels()` for Gate 2 CPCV/DSR kernels. Fetches klines/funding/tickers/instruments directly from `https://api.bybit.com` (public v5 endpoints, no keys). Candidates emit trades CSVs in screen.py's exact column contract; no dependency on `BacktestEngine` (it executes same-bar-close and hardcodes $10,000 — both disqualifying).

**Tech Stack:** Python 3.12, pandas, numpy, httpx (sync client), Decimal for money, pytest (`--no-cov`, host-run).

**Spec:** `docs/superpowers/specs/2026-08-16-edge-research-battery-design.md`

## Global Constraints

- Account is **$100**: `from shared.account import ACCOUNT_EQUITY_USD` — never write a capital literal (`.claude/rules/money.md`). `100.0` is the only exempt literal.
- `Decimal` for money (P&L, notionals, rates); `float` only for indicator math. Convert via `Decimal(str(x))`, never `Decimal(float)`.
- Never `round(price, 2)` — tick-size or full precision only.
- **No `services/` runtime code changes.** All new code in `backtesting/edge_lab/` + `tests/edge_lab/`. Never edit `costs.py`, `screen.py`, `cpcv.py`, `sharpe_metrics.py` (the last two are drift-guarded by `test_cpcv_sync.py`).
- Host-side import of trading-engine code goes through `costs_loader.load_costs()` (`te_costs` spec-load). Never `import app.*` from trading-engine — the `app` package name is claimed by technical-analysis (`costs_loader.py:1-14` docstring).
- Signal at bar `t` uses only data through bar `t−1` close; execution at bar `t` open. Enforced by shift-invariance test per candidate.
- Test command (from repo root): `python3 -m pytest tests/edge_lab/ --no-cov -q`. Must be `python3 -m pytest` (puts repo root on sys.path so `shared.account` resolves). Root `pytest.ini` has `filterwarnings = error` — silence expected pandas warnings explicitly, don't let them fail tests.
- Test files: unique basenames repo-wide (no `__init__.py` in tests/), bootstrap `backtesting/` onto sys.path (pattern below).
- Commits: `git commit -- <paths>` (pathspec; shared index), conventional messages `feat(edge-lab): ...` / `test(edge-lab): ...`.
- Pinned battery constants (single source: `edge_lab/config.py`, Task 1):

| Constant | Value |
|---|---|
| `UNIVERSE_TOP_N` | 30 |
| `MIN_LISTING_AGE_DAYS` | 730 |
| `DAILY_LOOKBACK_DAYS` | 730 |
| `H4_LOOKBACK_DAYS` | 365 (interval `"240"`) |
| `HURDLE_MULTIPLE` | `Decimal("2")` |
| `SLIPPAGE_BPS` | `{"BTCUSDT": 5, "ETHUSDT": 5, "SOLUSDT": 5, "BNBUSDT": 10, "ADAUSDT": 10}` (Decimals) |
| `SLIPPAGE_FALLBACK_BPS` | `Decimal("10")` (⇒ 31 bps round-trip taker for every non-major — conservative tier) |
| `DSR_THRESHOLD` | 0.95 |
| `NUM_TRIALS_FLOOR` | 16 — 8 battery variants + 8 historical strategy families (CLAUDE.md §2 table) |
| `MIN_POSITIVE_PATH_FRAC` | 0.70 |
| CPCV | `n_groups=10, k_test_groups=2, embargo_pct=0.01` |
| `NOTIONAL_PER_TRADE` | `Decimal(str(ACCOUNT_EQUITY_USD))` |

---

### Task 1: Package scaffold, config, trade record + CSV contract

**Files:**
- Create: `backtesting/edge_lab/__init__.py` (empty)
- Create: `backtesting/edge_lab/config.py`
- Create: `backtesting/edge_lab/trades.py`
- Create: `backtesting/edge_lab/candidates/__init__.py` (empty)
- Test: `tests/edge_lab/test_edge_lab_trades.py`

**Interfaces:**
- Produces: `config.py` module constants (table above, exact names). `trades.py`: `@dataclass(frozen=True) Trade(symbol: str, side: str, entry_ts_ms: int, exit_ts_ms: int, entry_px: float, exit_px: float)` with `side in ("LONG", "SHORT")`; `gross_pnl(trade) -> Decimal`; `notionals(trade) -> tuple[Decimal, Decimal]`; `write_trades_csv(trades: list[Trade], path: Path) -> Path` emitting exactly the screen.py columns `symbol,side,gross_pnl,notional_in,notional_out,entry_ts_ms,exit_ts_ms`; `Variant(candidate: str, name: str, params: dict)` frozen dataclass.
- Consumes: `shared.account.ACCOUNT_EQUITY_USD`.

- [ ] **Step 1: Write the failing test**

```python
# tests/edge_lab/test_edge_lab_trades.py
"""Trade record + CSV contract against screen.py's parser."""
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.trades import Trade, gross_pnl, notionals, write_trades_csv  # noqa: E402
from edge_lab.config import NOTIONAL_PER_TRADE  # noqa: E402
from screen import _rows_from_csv, screen_trades  # noqa: E402
from costs_loader import load_costs  # noqa: E402


def _mk(side, entry_px, exit_px):
    return Trade(symbol="BTCUSDT", side=side, entry_ts_ms=1_700_000_000_000,
                 exit_ts_ms=1_700_086_400_000, entry_px=entry_px, exit_px=exit_px)


def test_long_pnl_sign():
    # LONG, +1%: pnl = notional * 0.01
    t = _mk("LONG", 100.0, 101.0)
    assert gross_pnl(t) == (NOTIONAL_PER_TRADE * Decimal("0.01")).quantize(Decimal("0.00000001"))


def test_short_pnl_sign():
    # SHORT, price +1%: loss
    t = _mk("SHORT", 100.0, 101.0)
    assert gross_pnl(t) < 0


def test_notional_out_scales_with_price():
    t = _mk("LONG", 100.0, 110.0)
    n_in, n_out = notionals(t)
    assert n_in == NOTIONAL_PER_TRADE
    assert n_out == (NOTIONAL_PER_TRADE * Decimal("1.1")).quantize(Decimal("0.00000001"))


def test_csv_round_trips_through_screen(tmp_path):
    trades = [_mk("LONG", 100.0, 101.0), _mk("SHORT", 200.0, 199.0)]
    path = write_trades_csv(trades, tmp_path / "t.csv")
    rows, provenance = _rows_from_csv(str(path), modelled_fee_rate=Decimal("0.001"))
    assert len(rows) == 2
    assert provenance == "notional_in / notional_out, as supplied"
    costs = load_costs()
    result = screen_trades(
        rows,
        schedule=costs.FeeSchedule.bybit_linear_perp(),
        slippage_table={"BTCUSDT": Decimal("5")},
        slippage_fallback=Decimal("10"),
    )
    assert result.n_trades == 2
    assert result.verdict in ("PASS", "KILL")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_trades.py --no-cov -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'edge_lab'`

- [ ] **Step 3: Write the implementation**

`backtesting/edge_lab/config.py`:

```python
"""Battery-wide pinned constants. Declared before any run; changing a value
after verdicts exist invalidates them (spec §4 anti-overfitting rule)."""
from decimal import Decimal

from shared.account import ACCOUNT_EQUITY_USD

UNIVERSE_TOP_N = 30
MIN_LISTING_AGE_DAYS = 730
DAILY_LOOKBACK_DAYS = 730
H4_LOOKBACK_DAYS = 365
H4_INTERVAL = "240"
DAILY_INTERVAL = "D"          # Bybit API interval; filenames use 1440m (killtest convention)

HURDLE_MULTIPLE = Decimal("2")
SLIPPAGE_BPS = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}
SLIPPAGE_FALLBACK_BPS = Decimal("10")   # every non-major: 11 fee + 20 slip = 31 bps RT taker

DSR_THRESHOLD = 0.95
NUM_TRIALS_FLOOR = 16   # 8 battery variants + 8 historical families (CLAUDE.md §2)
MIN_POSITIVE_PATH_FRAC = 0.70
CPCV_N_GROUPS = 10
CPCV_K_TEST_GROUPS = 2
CPCV_EMBARGO_PCT = 0.01

NOTIONAL_PER_TRADE = Decimal(str(ACCOUNT_EQUITY_USD))
```

Note: `shared.account` resolves because every entry point (pytest from repo root, `run_battery.py` bootstrap) puts repo root on sys.path. `config.py` itself must not manipulate sys.path.

`backtesting/edge_lab/trades.py`:

```python
"""Trade record + the trades-CSV contract screen.py consumes.

Columns (screen.py adapt_row): symbol, side, gross_pnl, notional_in,
notional_out, entry_ts_ms, exit_ts_ms. side must be LONG/SHORT — te_costs
funding_cost switches on it.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from edge_lab.config import NOTIONAL_PER_TRADE

_Q = Decimal("0.00000001")


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str            # "LONG" | "SHORT"
    entry_ts_ms: int
    exit_ts_ms: int
    entry_px: float
    exit_px: float

    def __post_init__(self) -> None:
        if self.side not in ("LONG", "SHORT"):
            raise ValueError(f"side must be LONG/SHORT, got {self.side!r}")
        if self.entry_px <= 0 or self.exit_px <= 0:
            raise ValueError(f"non-positive price on {self.symbol}")
        if self.exit_ts_ms <= self.entry_ts_ms:
            raise ValueError(f"exit_ts_ms <= entry_ts_ms on {self.symbol}")


@dataclass(frozen=True)
class Variant:
    candidate: str       # e.g. "xs_momentum"
    name: str            # e.g. "lookback_30d"
    params: tuple        # hashable param pairs, e.g. (("lookback_days", 30),)


def _ratio(t: Trade) -> Decimal:
    return Decimal(str(t.exit_px)) / Decimal(str(t.entry_px))


def gross_pnl(t: Trade) -> Decimal:
    move = _ratio(t) - 1
    signed = move if t.side == "LONG" else -move
    return (NOTIONAL_PER_TRADE * signed).quantize(_Q)


def notionals(t: Trade) -> tuple[Decimal, Decimal]:
    n_in = NOTIONAL_PER_TRADE
    n_out = (NOTIONAL_PER_TRADE * _ratio(t)).quantize(_Q)
    return n_in, n_out


def write_trades_csv(trades: list[Trade], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "side", "gross_pnl", "notional_in",
                    "notional_out", "entry_ts_ms", "exit_ts_ms"])
        for t in sorted(trades, key=lambda x: x.entry_ts_ms):
            n_in, n_out = notionals(t)
            w.writerow([t.symbol, t.side, str(gross_pnl(t)), str(n_in),
                        str(n_out), t.entry_ts_ms, t.exit_ts_ms])
    return path
```

Create empty `backtesting/edge_lab/__init__.py` and `backtesting/edge_lab/candidates/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_trades.py --no-cov -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/__init__.py backtesting/edge_lab/config.py backtesting/edge_lab/trades.py backtesting/edge_lab/candidates/__init__.py tests/edge_lab/test_edge_lab_trades.py
git commit -m "feat(edge-lab): package scaffold, pinned battery config, trades CSV contract" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 2: Causal indicators (BB, Keltner, ATR, Donchian, squeeze)

**Files:**
- Create: `backtesting/edge_lab/indicators.py`
- Test: `tests/edge_lab/test_edge_lab_indicators.py`

**Interfaces:**
- Produces (all take/return pandas objects, float math, causal — value at row i depends only on rows ≤ i):
  - `sma(s: pd.Series, n: int) -> pd.Series`
  - `true_range(df: pd.DataFrame) -> pd.Series` (needs high/low/close)
  - `atr(df: pd.DataFrame, n: int = 14) -> pd.Series` (Wilder: `ewm(alpha=1/n, adjust=False, min_periods=n)` — same formula as `backtesting/strategies/sqzmom_v2.py:79-88`)
  - `bollinger(close: pd.Series, n: int = 20, mult: float = 2.0) -> pd.DataFrame` cols `bb_upper, bb_mid, bb_lower`
  - `keltner(df: pd.DataFrame, n: int = 20, mult: float = 1.5) -> pd.DataFrame` cols `kc_upper, kc_mid, kc_lower` (KC = SMA(close) ± mult·SMA(TR) — same formula as `squeeze_momentum.py:151-192`)
  - `donchian(df: pd.DataFrame, entry_n: int, exit_n: int) -> pd.DataFrame` cols `dc_entry_high, dc_entry_low, dc_exit_high, dc_exit_low` — rolling max(high)/min(low) over trailing n bars **excluding the current bar** (`.shift(1)` applied inside, so a breakout compares close[t] to the channel of bars t−n..t−1)
  - `squeeze_on(df: pd.DataFrame, bb_n=20, bb_mult=2.0, kc_n=20, kc_mult=1.5) -> pd.Series[bool]` — `(bb_lower > kc_lower) & (bb_upper < kc_upper)` (formula verbatim from `squeeze_momentum.py:351-361`)
- Consumes: nothing from earlier tasks.

Note: we implement locally instead of importing `prod_indicators.SqueezeMomentumIndicator` — the service class is same-formula but O(n·period) slow (rolling `scipy.linregress` apply), requires OHLCV columns, logs via service logger, and claims the `app` package for technical-analysis. Formulas are borrowed verbatim; the source lines are cited above so a reviewer can diff.

- [ ] **Step 1: Write the failing test**

```python
# tests/edge_lab/test_edge_lab_indicators.py
"""Known-value + causality tests for edge_lab indicators."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab import indicators as ind  # noqa: E402


def _df(n=300, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close})


def test_sma_known_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    out = ind.sma(s, 2)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 1.5 and out.iloc[3] == 3.5


def test_bollinger_symmetry():
    df = _df()
    bb = ind.bollinger(df["close"], 20, 2.0)
    mid_dev_up = (bb["bb_upper"] - bb["bb_mid"]).dropna()
    mid_dev_dn = (bb["bb_mid"] - bb["bb_lower"]).dropna()
    assert np.allclose(mid_dev_up, mid_dev_dn)


def test_donchian_excludes_current_bar():
    # Current bar makes a new high; channel must NOT include it.
    df = pd.DataFrame({
        "high": [10.0, 11.0, 12.0, 99.0],
        "low": [9.0, 10.0, 11.0, 98.0],
        "close": [9.5, 10.5, 11.5, 98.5],
    })
    dc = ind.donchian(df, entry_n=3, exit_n=2)
    assert dc["dc_entry_high"].iloc[3] == 12.0   # max of bars 0..2, not 99


def test_squeeze_on_boolean_and_causal():
    df = _df()
    sq = ind.squeeze_on(df)
    assert sq.dtype == bool


def test_all_indicators_causal():
    """Value at row i must not change when future rows are removed."""
    df = _df(n=300)
    t = 250
    full = {
        "atr": ind.atr(df, 14),
        "bb": ind.bollinger(df["close"], 20, 2.0)["bb_upper"],
        "kc": ind.keltner(df, 20, 1.5)["kc_upper"],
        "dc": ind.donchian(df, 20, 10)["dc_entry_high"],
        "sq": ind.squeeze_on(df).astype(float),
    }
    trunc_df = df.iloc[: t + 1]
    trunc = {
        "atr": ind.atr(trunc_df, 14),
        "bb": ind.bollinger(trunc_df["close"], 20, 2.0)["bb_upper"],
        "kc": ind.keltner(trunc_df, 20, 1.5)["kc_upper"],
        "dc": ind.donchian(trunc_df, 20, 10)["dc_entry_high"],
        "sq": ind.squeeze_on(trunc_df).astype(float),
    }
    for k in full:
        a, b = full[k].iloc[t], trunc[k].iloc[t]
        assert (np.isnan(a) and np.isnan(b)) or a == b, f"{k} is not causal at row {t}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_indicators.py --no-cov -q`
Expected: FAIL — `ImportError` (module missing)

- [ ] **Step 3: Write the implementation**

```python
# backtesting/edge_lab/indicators.py
"""Causal indicator math for edge_lab candidates.

Formulas match the TA service (cited per function); implemented locally
because the service classes are latest-value-shaped, slow, and claim the
`app` package. Float math only — no money here.
"""
from __future__ import annotations

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    # Wilder smoothing — same as backtesting/strategies/sqzmom_v2.py:79-88
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def bollinger(close: pd.Series, n: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std()
    return pd.DataFrame({"bb_upper": mid + mult * sd, "bb_mid": mid,
                         "bb_lower": mid - mult * sd})


def keltner(df: pd.DataFrame, n: int = 20, mult: float = 1.5) -> pd.DataFrame:
    # KC = SMA(close) ± mult * SMA(TR) — squeeze_momentum.py:151-192
    mid = sma(df["close"], n)
    rng = sma(true_range(df), n)
    return pd.DataFrame({"kc_upper": mid + mult * rng, "kc_mid": mid,
                         "kc_lower": mid - mult * rng})


def donchian(df: pd.DataFrame, entry_n: int, exit_n: int) -> pd.DataFrame:
    # shift(1): channel of bars t-n..t-1 — the current bar never sees itself.
    return pd.DataFrame({
        "dc_entry_high": df["high"].rolling(entry_n, min_periods=entry_n).max().shift(1),
        "dc_entry_low": df["low"].rolling(entry_n, min_periods=entry_n).min().shift(1),
        "dc_exit_high": df["high"].rolling(exit_n, min_periods=exit_n).max().shift(1),
        "dc_exit_low": df["low"].rolling(exit_n, min_periods=exit_n).min().shift(1),
    })


def squeeze_on(df: pd.DataFrame, bb_n: int = 20, bb_mult: float = 2.0,
               kc_n: int = 20, kc_mult: float = 1.5) -> pd.Series:
    # (bb_lower > kc_lower) & (bb_upper < kc_upper) — squeeze_momentum.py:351-361
    bb = bollinger(df["close"], bb_n, bb_mult)
    kc = keltner(df, kc_n, kc_mult)
    return ((bb["bb_lower"] > kc["kc_lower"]) &
            (bb["bb_upper"] < kc["kc_upper"])).fillna(False).astype(bool)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_indicators.py --no-cov -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/indicators.py tests/edge_lab/test_edge_lab_indicators.py
git commit -m "feat(edge-lab): causal BB/Keltner/ATR/Donchian/squeeze indicators" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 3: Universe selection + pin

**Files:**
- Create: `backtesting/edge_lab/universe.py`
- Test: `tests/edge_lab/test_edge_lab_universe.py`

**Interfaces:**
- Produces:
  - `select_universe(tickers: list[dict], instruments: list[dict], now_ms: int, top_n: int = UNIVERSE_TOP_N, min_age_days: int = MIN_LISTING_AGE_DAYS) -> list[dict]` — pure function; returns list of `{"symbol": str, "turnover24h": float, "launch_ms": int}` sorted by turnover desc, length ≤ top_n. Filters: symbol endswith `USDT`; instrument `status == "Trading"`; `contractType == "LinearPerpetual"` when the key is present; `launchTime` present and `now_ms - int(launchTime) >= min_age_days * 86_400_000`. Symbols excluded for age/status are returned via second channel: actual signature returns `tuple[list[dict], list[str]]` — `(selected, excluded_names)` (no silent shrinkage).
  - `write_pin(selected: list[dict], excluded: list[str], date_str: str, dir_path: Path) -> Path` — writes `universe_<date>.json` with keys `date, top_n, min_age_days, symbols (list of dicts), excluded`.
  - `load_pin(path: Path) -> dict`.
- Consumes: `edge_lab.config` constants. Network fetch of tickers/instruments lives in Task 4's client; `run_battery.py` (Task 12) wires them together. `select_universe` itself is pure — testable offline.
- Ticker field: `turnover24h` (stringified USDT turnover — `fetcher.py:253-263` precedent). Instrument field: `launchTime` (ms-epoch string, passes through connector raw; no repo precedent reads it — this is the first consumer, note it in the docstring).

- [ ] **Step 1: Write the failing test**

```python
# tests/edge_lab/test_edge_lab_universe.py
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.universe import select_universe, write_pin, load_pin  # noqa: E402

NOW = 1_800_000_000_000
OLD = NOW - 800 * 86_400_000     # ~800 days old
YOUNG = NOW - 100 * 86_400_000   # 100 days old


def _ticker(sym, turnover):
    return {"symbol": sym, "turnover24h": str(turnover)}


def _inst(sym, launch, status="Trading", ctype="LinearPerpetual"):
    return {"symbol": sym, "launchTime": str(launch), "status": status,
            "contractType": ctype}


def test_sorts_by_turnover_and_caps():
    tickers = [_ticker(f"C{i}USDT", 1000 - i) for i in range(40)]
    instruments = [_inst(f"C{i}USDT", OLD) for i in range(40)]
    selected, excluded = select_universe(tickers, instruments, NOW, top_n=30)
    assert len(selected) == 30
    assert selected[0]["symbol"] == "C0USDT"          # highest turnover first
    assert selected[0]["turnover24h"] >= selected[-1]["turnover24h"]


def test_age_filter_excludes_young_and_names_them():
    tickers = [_ticker("OLDUSDT", 100), _ticker("YOUNGUSDT", 99999)]
    instruments = [_inst("OLDUSDT", OLD), _inst("YOUNGUSDT", YOUNG)]
    selected, excluded = select_universe(tickers, instruments, NOW)
    assert [s["symbol"] for s in selected] == ["OLDUSDT"]
    assert "YOUNGUSDT" in excluded


def test_non_usdt_and_non_trading_excluded():
    tickers = [_ticker("AAAUSDT", 5), _ticker("BBBUSD", 9), _ticker("CCCUSDT", 7)]
    instruments = [_inst("AAAUSDT", OLD), _inst("BBBUSD", OLD),
                   _inst("CCCUSDT", OLD, status="Closed")]
    selected, excluded = select_universe(tickers, instruments, NOW)
    assert [s["symbol"] for s in selected] == ["AAAUSDT"]
    assert "CCCUSDT" in excluded          # named, not silent


def test_missing_launchtime_excluded_not_crash():
    tickers = [_ticker("XUSDT", 5)]
    instruments = [{"symbol": "XUSDT", "status": "Trading"}]   # no launchTime
    selected, excluded = select_universe(tickers, instruments, NOW)
    assert selected == [] and "XUSDT" in excluded


def test_pin_round_trip(tmp_path):
    tickers = [_ticker("AUSDT", 5)]
    instruments = [_inst("AUSDT", OLD)]
    selected, excluded = select_universe(tickers, instruments, NOW)
    p = write_pin(selected, excluded, "2026-08-16", tmp_path)
    pin = load_pin(p)
    assert pin["symbols"][0]["symbol"] == "AUSDT"
    assert pin["date"] == "2026-08-16"
    data = json.loads(p.read_text())
    assert data == pin
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_universe.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Write the implementation**

```python
# backtesting/edge_lab/universe.py
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


def select_universe(tickers, instruments, now_ms, top_n=UNIVERSE_TOP_N,
                    min_age_days=MIN_LISTING_AGE_DAYS):
    inst_by_symbol = {i.get("symbol"): i for i in instruments}
    selected, excluded = [], []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue                     # not in scope at all, not "excluded"
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
        selected.append({
            "symbol": sym,
            "turnover24h": float(t.get("turnover24h") or 0.0),
            "launch_ms": int(launch),
        })
    selected.sort(key=lambda d: d["turnover24h"], reverse=True)
    return selected[:top_n], sorted(excluded)


def write_pin(selected, excluded, date_str, dir_path) -> Path:
    dir_path = Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"universe_{date_str}.json"
    path.write_text(json.dumps({
        "date": date_str,
        "top_n": UNIVERSE_TOP_N,
        "min_age_days": MIN_LISTING_AGE_DAYS,
        "symbols": selected,
        "excluded": excluded,
    }, indent=2))
    return path


def load_pin(path) -> dict:
    return json.loads(Path(path).read_text())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_universe.py --no-cov -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/universe.py tests/edge_lab/test_edge_lab_universe.py
git commit -m "feat(edge-lab): top-30 universe selection with age filter and dated pin" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 4: Public Bybit client + kline/funding fetchers with cache

**Files:**
- Create: `backtesting/edge_lab/fetch.py`
- Test: `tests/edge_lab/test_edge_lab_fetch.py`

**Interfaces:**
- Produces:
  - `class BybitPublic:` `__init__(self, base_url: str = "https://api.bybit.com", client: httpx.Client | None = None, sleep_s: float = 0.2)` — sync httpx; `get(self, path: str, params: dict) -> dict` returns the v5 `result` dict; raises `FetchError` after 3 attempts (backoff 1s/2s/4s via plain loop — no tenacity dep) or on `retCode != 0`.
  - `tickers(self) -> list[dict]` — `/v5/market/tickers?category=linear`, returns `result["list"]`.
  - `instruments(self) -> list[dict]` — `/v5/market/instruments-info?category=linear&limit=1000` with `nextPageCursor` loop, 10-page cap (pattern verbatim from `bybit_rest_client.py:712-750`).
  - `fetch_klines(self, symbol: str, interval: str, days: int, now_ms: int) -> pd.DataFrame` — backward pagination from `now_ms`; params `category/symbol/interval/start/end/limit=1000`; **l18-correct loop**: break only on empty batch or `oldest_ts <= target_start`, `current_end = oldest_ts - 1`, `max_batches` guard, a short batch is NOT end-of-history; dedupe by ts, sort ascending, drop still-forming bar (`ts_ms + interval_ms > now_ms`).
  - `fetch_funding(self, symbol: str, days: int, now_ms: int) -> pd.DataFrame` — `/v5/market/funding/history`, params `category/symbol/startTime/endTime/limit=200` (camelCase — differs from kline's `start`/`end`), newest-first, **no cursor**: walk `endTime = oldest_ts - 1` backward until empty batch or window covered; cols `ts_ms:int, funding_rate:str`.
  - `kline_csv_path(data_dir: Path, symbol: str, interval: str, days: int) -> Path` — killtest naming: interval `"D"` maps to `1440`, giving `{SYM}_{1440|240}m_{days}d_bybit.csv`.
  - `funding_csv_path(data_dir: Path, symbol: str) -> Path` — `funding/{SYM}_funding.csv` (what `costs_loader.load_funding` reads).
  - `ensure_klines(client, data_dir, symbol, interval, days, now_ms) -> Path` and `ensure_funding(client, data_dir, symbol, days, now_ms) -> Path` — skip fetch when the file already exists (resume-from-cache = file granularity), else fetch and write. Kline CSV written in the 11-col klines schema (`timestamp,symbol,interval,open,high,low,close,volume,turnover,is_mainnet,created_at`) with `is_mainnet=True` — justified: `api.bybit.com` IS mainnet by construction. Funding CSV: header `ts_ms,funding_rate`.
- `interval_ms(interval: str) -> int` — `"D"` → 86_400_000, else `int(interval) * 60_000`.
- Consumes: `edge_lab.config`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_fetch.py
"""Fetcher pagination + cache tests against httpx.MockTransport. No network."""
import sys
from pathlib import Path

import httpx
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.fetch import (  # noqa: E402
    BybitPublic, ensure_funding, ensure_klines, funding_csv_path,
    interval_ms, kline_csv_path,
)

DAY = 86_400_000
NOW = 1_800_000_000_000


def _kline_rows(start_ms, n, step_ms):
    # Bybit shape: newest-first [ts, o, h, l, c, vol, turnover] strings
    rows = [[str(start_ms + i * step_ms), "100", "101", "99", "100.5", "10", "1000"]
            for i in range(n)]
    return list(reversed(rows))


def _mock(handler):
    return BybitPublic(client=httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.bybit.com"),
        sleep_s=0.0)


def test_kline_pagination_stitches_multiple_pages():
    """3000 daily bars must come back complete across 3 pages."""
    total = 3000
    step = DAY
    t0 = NOW - total * step
    calls = []

    def handler(request):
        params = dict(request.url.params)
        calls.append(params)
        start, end = int(params["start"]), int(params["end"])
        rows = [[str(ts), "1", "1", "1", "1", "1", "1"]
                for ts in range(t0, NOW, step) if start <= ts <= end]
        rows = sorted(rows, key=lambda r: -int(r[0]))[:1000]
        return httpx.Response(200, json={"retCode": 0, "result": {"list": rows}})

    df = _mock(handler).fetch_klines("BTCUSDT", "D", days=total, now_ms=NOW)
    assert len(df) >= total - 1                    # forming-bar drop allowed
    assert df["ts_ms"].is_monotonic_increasing
    assert df["ts_ms"].duplicated().sum() == 0
    assert len(calls) >= 3


def test_short_batch_is_not_end_of_history():
    """999-row page (forming bar dropped upstream) must NOT stop the loop.
    Regression on the 260816-l18 gotcha."""
    step = DAY
    t0 = NOW - 1500 * step
    pages = []

    def handler(request):
        params = dict(request.url.params)
        start, end = int(params["start"]), int(params["end"])
        rows = [[str(ts), "1", "1", "1", "1", "1", "1"]
                for ts in range(t0, NOW, step) if start <= ts <= end]
        rows = sorted(rows, key=lambda r: -int(r[0]))[:999]   # always short
        pages.append(len(rows))
        return httpx.Response(200, json={"retCode": 0, "result": {"list": rows}})

    df = _mock(handler).fetch_klines("BTCUSDT", "D", days=1500, now_ms=NOW)
    assert len(df) >= 1499
    assert len(pages) >= 2                          # kept paginating past a short page


def test_funding_walks_end_time_backward():
    """700 settlements, 200/page, no cursor — endTime walk must fetch all."""
    step = 8 * 3_600_000
    n = 700
    t0 = NOW - n * step

    def handler(request):
        assert request.url.path == "/v5/market/funding/history"
        params = dict(request.url.params)
        start, end = int(params["startTime"]), int(params["endTime"])
        rows = [{"symbol": "BTCUSDT", "fundingRate": "0.0001",
                 "fundingRateTimestamp": str(ts)}
                for ts in range(t0, NOW, step) if start <= ts <= end]
        rows = sorted(rows, key=lambda r: -int(r["fundingRateTimestamp"]))[:200]
        return httpx.Response(200, json={"retCode": 0, "result": {"list": rows}})

    df = _mock(handler).fetch_funding("BTCUSDT", days=n * step // DAY + 1, now_ms=NOW)
    assert len(df) == n
    assert df["ts_ms"].is_monotonic_increasing


def test_retcode_error_raises():
    def handler(request):
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "bad param"})
    try:
        _mock(handler).tickers()
        assert False, "should have raised"
    except Exception as e:
        assert "10001" in str(e)


def test_ensure_klines_skips_when_cached(tmp_path):
    hits = []

    def handler(request):
        hits.append(1)
        return httpx.Response(200, json={"retCode": 0, "result": {"list": [
            [str(NOW - 2 * DAY), "1", "1", "1", "1", "1", "1"]]}})

    c = _mock(handler)
    p1 = ensure_klines(c, tmp_path, "BTCUSDT", "D", 5, NOW)
    n_calls = len(hits)
    p2 = ensure_klines(c, tmp_path, "BTCUSDT", "D", 5, NOW)
    assert p1 == p2 and len(hits) == n_calls        # second call: zero fetches
    assert p1.name == "BTCUSDT_1440m_5d_bybit.csv"  # killtest naming, D->1440
    header = p1.read_text().splitlines()[0]
    assert header == ("timestamp,symbol,interval,open,high,low,close,"
                      "volume,turnover,is_mainnet,created_at")


def test_funding_csv_matches_costs_loader_contract(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "fundingRate": "0.0001",
             "fundingRateTimestamp": str(NOW - DAY)}]}})

    p = ensure_funding(_mock(handler), tmp_path, "BTCUSDT", 5, NOW)
    assert p == funding_csv_path(tmp_path, "BTCUSDT")
    from costs_loader import load_funding  # noqa: E402
    series = load_funding("BTCUSDT", str(tmp_path / "funding"))
    assert len(series) == 1 and series[0].ts_ms == NOW - DAY


def test_interval_ms():
    assert interval_ms("D") == DAY and interval_ms("240") == 4 * 3_600_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_fetch.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Write the implementation**

Key requirements beyond the interface block (implement exactly):

```python
# backtesting/edge_lab/fetch.py — core loop shapes (full file follows this design)
class FetchError(RuntimeError):
    pass


class BybitPublic:
    def __init__(self, base_url="https://api.bybit.com", client=None, sleep_s=0.2):
        self._client = client or httpx.Client(base_url=base_url, timeout=30.0)
        self._sleep_s = sleep_s

    def get(self, path, params):
        last = None
        for attempt in range(3):
            try:
                resp = self._client.get(path, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data.get("retCode") != 0:
                    raise FetchError(f"{path} retCode={data.get('retCode')} "
                                     f"retMsg={data.get('retMsg')}")
                return data.get("result", {})
            except (httpx.TimeoutException, httpx.TransportError, FetchError) as e:
                if isinstance(e, FetchError) and "retCode" in str(e):
                    raise                      # API rejected the request: don't retry
                last = e
                time.sleep(2 ** attempt)       # 1, 2, 4
        raise FetchError(f"{path} failed after 3 attempts: {last}")
```

- `fetch_klines`: `target_start = now_ms - days * DAY`; `current_end = now_ms`; `max_batches = days * DAY // (1000 * interval_ms(interval)) + 10`; loop per the l18 pattern (`fetcher.py:329-384`): request `{"category": "linear", "symbol", "interval", "start": target_start, "end": current_end, "limit": 1000}`; empty list → break; extend; `oldest = min(int(r[0]) for r in rows)`; `oldest <= target_start` → break; `current_end = oldest - 1`; `time.sleep(self._sleep_s)`. After loop: dedupe on ts, sort ascending, build DataFrame with `ts_ms:int64, open/high/low/close/volume/turnover: float`, then drop rows where `ts_ms + interval_ms(interval) > now_ms` (forming bar).
- `fetch_funding`: same backward walk on `fundingRateTimestamp` with params `{"category": "linear", "symbol", "startTime": target_start, "endTime": current_end, "limit": 200}`; returns DataFrame `ts_ms:int64, funding_rate:str` ascending. Empty result for the whole window → empty DataFrame (caller records the symbol as funding-missing; never fabricate).
- `ensure_klines` writes the 11-col schema: `timestamp` = `pd.to_datetime(ts_ms, unit="ms")`, `symbol`, `interval` (the API string, `"D"` or `"240"`), OHLCV+turnover floats, `is_mainnet=True`, `created_at=now_ms`. `ensure_funding` writes `ts_ms,funding_rate` under `data_dir/funding/`.
- `kline_csv_path`: `iv = "1440" if interval == "D" else interval`; `data_dir / f"{symbol}_{iv}m_{days}d_bybit.csv"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_fetch.py --no-cov -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/fetch.py tests/edge_lab/test_edge_lab_fetch.py
git commit -m "feat(edge-lab): direct Bybit v5 public client — kline/funding fetch with l18-correct pagination and file cache" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 5: Gate 0 — data sanity

**Files:**
- Create: `backtesting/edge_lab/sanity.py`
- Test: `tests/edge_lab/test_edge_lab_sanity.py`

**Interfaces:**
- Produces:
  - `@dataclass SanityReport(symbol: str, interval: str, ok: bool, n_bars: int, first_ts_ms: int, last_ts_ms: int, gaps: list[tuple[int, int]], defects: list[str], funding_ok: bool, funding_n: int)`
  - `check_klines(df: pd.DataFrame, symbol: str, interval: str) -> SanityReport` — defects appended for: non-monotonic `ts_ms`; duplicate `ts_ms`; any `open/high/low/close <= 0`; any NaN in OHLC; any gap where `ts_next - ts > 2 * interval_ms(interval)` (each recorded in `gaps`); `high < low` on any bar. `ok = not defects`. Gaps of exactly 2 intervals (one missing bar) are recorded in `gaps` but do NOT set a defect — spec tolerance is "no gap > 2 intervals".
  - `check_funding(df: pd.DataFrame, days_expected: int) -> tuple[bool, int]` — `funding_ok` False when the series is empty or covers < 50% of expected settlements at 8h cadence; returns `(ok, n_rows)`. Missing funding is NOT a battery-stopper — it flows into screen.py's EXCLUDES marker — but it must be visible in the report.
  - `render_sanity_table(reports: list[SanityReport]) -> str` — one line per symbol/interval incl. every dropped symbol and every defect string. No silent shrinkage.
- Consumes: `edge_lab.fetch.interval_ms`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_sanity.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.sanity import check_funding, check_klines, render_sanity_table  # noqa: E402

DAY = 86_400_000


def _clean(n=10, start=1_700_000_000_000):
    ts = [start + i * DAY for i in range(n)]
    return pd.DataFrame({"ts_ms": ts, "open": [100.0] * n, "high": [101.0] * n,
                         "low": [99.0] * n, "close": [100.5] * n,
                         "volume": [1.0] * n})


def test_clean_data_passes():
    r = check_klines(_clean(), "BTCUSDT", "D")
    assert r.ok and r.defects == [] and r.n_bars == 10


def test_one_missing_bar_recorded_but_ok():
    df = _clean(10)
    df = df[df["ts_ms"] != df["ts_ms"].iloc[5]]        # one-bar hole = 2-interval gap
    r = check_klines(df, "BTCUSDT", "D")
    assert r.ok and len(r.gaps) == 1


def test_three_bar_hole_is_a_defect():
    df = _clean(10)
    df = df[~df["ts_ms"].isin(df["ts_ms"].iloc[4:7])]   # 3 missing bars
    r = check_klines(df, "BTCUSDT", "D")
    assert not r.ok and any("gap" in d for d in r.defects)


def test_negative_price_is_a_defect():
    df = _clean()
    df.loc[3, "low"] = -1.0
    r = check_klines(df, "BTCUSDT", "D")
    assert not r.ok


def test_funding_coverage():
    n_days = 30
    settlements = pd.DataFrame({
        "ts_ms": [1_700_000_000_000 + i * 8 * 3_600_000 for i in range(90)],
        "funding_rate": ["0.0001"] * 90})
    ok, n = check_funding(settlements, n_days)
    assert ok and n == 90
    ok_empty, n_empty = check_funding(settlements.iloc[0:0], n_days)
    assert not ok_empty and n_empty == 0


def test_render_names_every_defect():
    bad = check_klines(_clean().assign(low=-5.0), "XUSDT", "D")
    out = render_sanity_table([bad])
    assert "XUSDT" in out and "FAIL" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_sanity.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `sanity.py` per the interface block. Gap scan: `diffs = df["ts_ms"].diff().iloc[1:]`; record `(ts_prev, ts_next)` for every diff > `interval_ms`; defect when diff > `2 * interval_ms`. Funding expected count: `days_expected * 3` (8h cadence); `ok = n >= 0.5 * expected`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_sanity.py --no-cov -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/sanity.py tests/edge_lab/test_edge_lab_sanity.py
git commit -m "feat(edge-lab): Gate 0 data sanity — gap/price/funding coverage checks, named drops" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 6: Gate 1 — cost hurdle wrapper

**Files:**
- Create: `backtesting/edge_lab/gate1.py`
- Test: `tests/edge_lab/test_edge_lab_gate1.py`

**Interfaces:**
- Produces:
  - `slippage_table() -> dict[str, Decimal]` — returns `SLIPPAGE_BPS` copy (fallback handled by `screen_trades`'s `slippage_fallback` arg — every non-major symbol lands on the conservative tier automatically).
  - `run_gate1(trades_csv: Path, funding_dir: Path) -> ScreenResult` — exactly the `screen.py main()` composition: `_rows_from_csv` → `load_funding` per symbol → `screen_trades(rows, schedule=te_costs.FeeSchedule.bybit_linear_perp(), slippage_table=slippage_table(), slippage_fallback=SLIPPAGE_FALLBACK_BPS, hurdle_multiple=HURDLE_MULTIPLE, funding_by_symbol=..., funding_source=str(funding_dir resolved), notional_provenance=...)`.
- Consumes: Task 1 CSV contract; `screen.screen_trades`, `screen._rows_from_csv`, `costs_loader.load_costs/load_funding`; `edge_lab.config`.
- Note: `screen_trades` verdict values are `"PASS"`/`"KILL"` (`screen.py:212`) — downstream code must use `"KILL"`, not `"REJECT"`, when branching on Gate 1.

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_gate1.py
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.gate1 import run_gate1, slippage_table  # noqa: E402
from edge_lab.trades import Trade, write_trades_csv  # noqa: E402

T0, T1 = 1_700_000_000_000, 1_700_086_400_000


def test_slippage_table_has_majors_only():
    t = slippage_table()
    assert t["BTCUSDT"] == Decimal("5") and t["ADAUSDT"] == Decimal("10")
    assert "PEPEUSDT" not in t          # unknowns hit the fallback, by design


def test_big_edge_passes_small_edge_killed(tmp_path):
    # +5% per trade on an unknown symbol (31bps RT cost): ratio 500/31 = 16x -> PASS
    win = [Trade("PEPEUSDT", "LONG", T0 + i * 200_000_000, T1 + i * 200_000_000,
                 100.0, 105.0) for i in range(5)]
    r = run_gate1(write_trades_csv(win, tmp_path / "w.csv"), tmp_path / "funding")
    assert r.verdict == "PASS" and r.ratio_taker > Decimal("2")

    # +0.02% per trade: 2 bps gross vs 31 bps cost -> KILL
    lose = [Trade("PEPEUSDT", "LONG", T0 + i * 200_000_000, T1 + i * 200_000_000,
                  100.0, 100.02) for i in range(5)]
    r2 = run_gate1(write_trades_csv(lose, tmp_path / "l.csv"), tmp_path / "funding")
    assert r2.verdict == "KILL"


def test_missing_funding_is_marked_not_zeroed(tmp_path):
    trades = [Trade("BTCUSDT", "LONG", T0, T1, 100.0, 105.0)]
    r = run_gate1(write_trades_csv(trades, tmp_path / "t.csv"), tmp_path / "funding")
    assert not r.funding_complete
    assert "BTCUSDT" in r.funding_symbols_missing
    assert "EXCLUDES funding" in r.render()


def test_funding_series_feeds_through(tmp_path):
    fdir = tmp_path / "funding"
    fdir.mkdir(parents=True)
    # settlement inside the holding window, LONG pays positive rate
    (fdir / "BTCUSDT_funding.csv").write_text(
        f"ts_ms,funding_rate\n{T0 + 3_600_000},0.0001\n")
    trades = [Trade("BTCUSDT", "LONG", T0, T1, 100.0, 105.0)]
    r = run_gate1(write_trades_csv(trades, tmp_path / "t.csv"), fdir)
    assert r.funding_complete
    assert r.funding_total > 0          # positive = paid, per te_costs sign convention
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_gate1.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `gate1.py` (~40 lines) exactly as the interface block describes, mirroring `screen.py:312-335` with config constants substituted.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_gate1.py --no-cov -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/gate1.py tests/edge_lab/test_edge_lab_gate1.py
git commit -m "feat(edge-lab): Gate 1 cost-hurdle wrapper over screen.screen_trades" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 7: Gate 2 — daily returns builder + CPCV/DSR

**Files:**
- Create: `backtesting/edge_lab/gate2.py`
- Test: `tests/edge_lab/test_edge_lab_gate2.py`

**Interfaces:**
- Produces:
  - `daily_returns_from_trades(trades: list[Trade], daily_closes: dict[str, pd.DataFrame], start_ms: int, end_ms: int, cost_bps_rt: dict[str, Decimal], funding: dict[str, list]) -> pd.Series` — calendar-daily net return series (float) over `[start_ms, end_ms]`, **including flat days at 0.0** (honest capital utilization). Per trade per day: fractional close-to-close return of its symbol, signed by side; entry day uses entry_px→close, exit day uses prev close→exit_px; half the round-trip cost (`cost_bps_rt/2 / 10000`) deducted on entry day and half on exit day; funding settlements inside the window applied on their day with te_costs sign convention (LONG pays positive rate). Concurrent trades are equal-weighted (divide each day's sum by `max(1, n_open_that_day)`).
  - `@dataclass Gate2Result(dsr: float, pooled_pf: float, positive_path_frac: float, n_paths_valid: int, n_samples: int, sharpe_mean: float, sharpe_std: float, passed: bool, reasons: list[str])`
  - `run_gate2(returns: pd.Series, label_horizon_days: int, num_trials_floor: int = NUM_TRIALS_FLOOR) -> Gate2Result` — composition per the h4 precedent (`h4_information.py:134-155`), NOT `cpcv_to_dsr` (it hard-codes `num_trials=len(paths)` and cannot honor a floor):

```python
k = _load_kernels()          # from killtests.offline_ensemble
rets = returns.to_numpy(dtype=float)
cv = k["CombinatorialPurgedCV"](n_groups=CPCV_N_GROUPS,
                                k_test_groups=CPCV_K_TEST_GROUPS,
                                embargo_pct=CPCV_EMBARGO_PCT)
paths = {}
for split in cv.split(n_samples=len(rets), label_horizon=label_horizon_days):
    paths.setdefault(split.path_id, []).append(rets[split.test_idx])
returns_per_path = [np.concatenate(chunks) for chunks in paths.values()]
dist = k["cpcv_sharpe_distribution"](returns_per_path)
dsr = k["deflated_sharpe_ratio"](
    rets,
    num_trials=max(num_trials_floor, int(dist["n_paths"])),
    trial_sharpes_variance=float(dist["std"]) ** 2,
)
```

  - Pooled PF over the concatenated OOS path returns: `wins = sum(r for r in all_path_rets if r > 0)`, `losses = abs(sum(r for r in all_path_rets if r < 0))`, `pooled_pf = wins / losses` (`inf` when no losses) — **never mean-of-fold-PFs** (zero-loss folds drag that mean to ~1.0; `feedback_pf_metric_pooling`).
  - `positive_path_frac` = fraction of per-path mean returns > 0.
  - `passed = dsr >= DSR_THRESHOLD and pooled_pf > 1.0 and positive_path_frac >= MIN_POSITIVE_PATH_FRAC`; every failed criterion appended to `reasons`.
  - Insufficient data (`cv.split` raises ValueError on `n_samples < n_groups * (h + embargo + 1)`) → return `Gate2Result(passed=False, reasons=["insufficient samples: <detail>"], ...)` with NaN metrics — never crash the battery.
- Consumes: `killtests.offline_ensemble._load_kernels` (existing), Task 1 `Trade`.
- Import bootstrap inside `gate2.py` (needed because `killtests` imports assume `backtesting/` on sys.path — already true for every entry point; `gate2.py` itself just does `from killtests.offline_ensemble import _load_kernels`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_gate2.py
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.gate2 import daily_returns_from_trades, run_gate2  # noqa: E402
from edge_lab.trades import Trade  # noqa: E402

DAY = 86_400_000
T0 = 1_700_000_000_000


def _daily_closes(symbol="BTCUSDT", n=400, drift=0.001):
    ts = [T0 + i * DAY for i in range(n)]
    px = 100.0 * np.cumprod([1 + drift] * n)
    return {symbol: pd.DataFrame({"ts_ms": ts, "open": px, "close": px})}


def test_flat_days_are_zero():
    closes = _daily_closes()
    trades = [Trade("BTCUSDT", "LONG", T0 + 10 * DAY, T0 + 12 * DAY, 101.0, 102.0)]
    rets = daily_returns_from_trades(trades, closes, T0, T0 + 20 * DAY,
                                     {"BTCUSDT": Decimal("21")}, {})
    assert len(rets) == 21
    assert rets.iloc[0] == 0.0 and rets.iloc[-1] == 0.0
    assert (rets.iloc[10:13] != 0).any()


def test_costs_deducted_at_entry_and_exit():
    closes = _daily_closes(drift=0.0)          # flat prices: only costs remain
    trades = [Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 7 * DAY, 100.0, 100.0)]
    rets = daily_returns_from_trades(trades, closes, T0, T0 + 10 * DAY,
                                     {"BTCUSDT": Decimal("20")}, {})
    # 10 bps at entry day, 10 bps at exit day
    assert abs(rets.iloc[5] + 0.001) < 1e-9
    assert abs(rets.iloc[7] + 0.001) < 1e-9


def test_short_side_sign():
    closes = _daily_closes(drift=0.01)         # rising market
    trades = [Trade("BTCUSDT", "SHORT", T0 + 5 * DAY, T0 + 10 * DAY, 105.0, 110.0)]
    rets = daily_returns_from_trades(trades, closes, T0, T0 + 15 * DAY,
                                     {"BTCUSDT": Decimal("0")}, {})
    assert rets.iloc[6] < 0                    # short loses in a rising market


def test_gate2_strong_signal_passes():
    rng = np.random.default_rng(3)
    rets = pd.Series(rng.normal(0.004, 0.005, 500))     # absurdly strong daily edge
    r = run_gate2(rets, label_horizon_days=5)
    assert r.passed and r.dsr >= 0.95 and r.pooled_pf > 1.0


def test_gate2_noise_fails():
    rng = np.random.default_rng(4)
    rets = pd.Series(rng.normal(0.0, 0.01, 500))
    r = run_gate2(rets, label_horizon_days=5)
    assert not r.passed and len(r.reasons) >= 1


def test_gate2_insufficient_samples_is_reported_not_raised():
    r = run_gate2(pd.Series([0.001] * 50), label_horizon_days=20)
    assert not r.passed
    assert any("insufficient" in reason for reason in r.reasons)


def test_pooled_pf_not_dragged_by_zero_loss_folds():
    """All-positive returns: pooled PF must be inf, not a fold-mean near 1."""
    rets = pd.Series([0.001] * 400)
    r = run_gate2(rets, label_horizon_days=2)
    assert r.pooled_pf == float("inf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_gate2.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `gate2.py` per the interface block. `daily_returns_from_trades` implementation notes: build a `pd.date_range`-equivalent integer day index from `start_ms` to `end_ms` step DAY; per symbol pre-index closes by `ts_ms // DAY`; walk each trade's day span accumulating signed fractional returns into a numpy accumulator plus an `n_open` counter per day; divide, minus costs/funding on their days. Funding application: for each settlement `s` with `entry_ts_ms <= s.ts_ms <= exit_ts_ms`, day `s.ts_ms // DAY` gets `-float(notional-fraction)`: rate signed by side exactly as `te_costs.funding_cost` (LONG pays positive rate → negative return contribution).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_gate2.py --no-cov -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/gate2.py tests/edge_lab/test_edge_lab_gate2.py
git commit -m "feat(edge-lab): Gate 2 — daily returns builder + CPCV/DSR with trials floor, pooled PF" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 8: Candidate 1 — cross-sectional momentum

**Files:**
- Create: `backtesting/edge_lab/candidates/xs_momentum.py`
- Create: `tests/edge_lab/conftest.py` (shared shift-invariance helper + synthetic universe fixture)
- Test: `tests/edge_lab/test_edge_lab_xs_momentum.py`

**Interfaces:**
- Produces: `generate_trades(daily: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]` where `daily` maps symbol → DataFrame with `ts_ms, open, high, low, close, volume` ascending. Variant params: `(("lookback_days", L),)` for L ∈ {7, 30, 90}. `VARIANTS: list[Variant]` module constant (3 entries, names `lookback_7d/30d/90d`).
- Also produces (in conftest): `assert_shift_invariant(gen_fn, data, variant, cut_ts_ms)` — trades with `entry_ts_ms <= cut_ts_ms` must be identical when all bars with `ts_ms > cut_ts_ms` are removed from every symbol frame (exit-open trades still open at the cut are excluded from comparison on both sides).
- Pinned rules (spec §4): rebalance at each **Monday 00:00 UTC bar's open**; signal from closes through Sunday (the Monday bar itself never contributes); rank symbols by trailing L-day close-over-close return; long top 6, short bottom 6, equal weight; **full close/reopen weekly** (conservative on costs — membership continuity is NOT netted); positions exit at the next rebalance's open. Symbols lacking L+1 closes by a rebalance are skipped for that week (and the skip is visible: `generate_trades` logs skipped symbols per rebalance via the module logger at WARNING).
- Monday detection: `pd.Timestamp(ts_ms, unit="ms", tz="UTC").dayofweek == 0`.

- [ ] **Step 1: Write conftest helper + failing tests**

```python
# tests/edge_lab/conftest.py
"""Shared fixtures: synthetic multi-symbol daily data + shift-invariance check."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

DAY = 86_400_000
# 2023-01-02 00:00 UTC — a Monday, so rebalance days align deterministically
T0 = 1_672_617_600_000


def make_daily(symbols, n_days=400, seed=11, drifts=None):
    rng = np.random.default_rng(seed)
    out = {}
    for i, sym in enumerate(symbols):
        drift = (drifts or {}).get(sym, 0.0)
        rets = rng.normal(drift, 0.02, n_days)
        close = 100.0 * np.cumprod(1 + rets)
        open_ = np.concatenate([[100.0], close[:-1]])
        out[sym] = pd.DataFrame({
            "ts_ms": [T0 + k * DAY for k in range(n_days)],
            "open": open_, "high": np.maximum(open_, close) * 1.005,
            "low": np.minimum(open_, close) * 0.995, "close": close,
            "volume": np.full(n_days, 1000.0),
        })
    return out


@pytest.fixture
def universe12():
    syms = [f"S{i:02d}USDT" for i in range(12)]
    drifts = {s: 0.004 if i < 3 else (-0.004 if i >= 9 else 0.0)
              for i, s in enumerate(syms)}
    return make_daily(syms, drifts=drifts)


def assert_shift_invariant(gen_fn, data, variant, cut_ts_ms):
    full = gen_fn(data, variant)
    trunc_data = {s: df[df["ts_ms"] <= cut_ts_ms].reset_index(drop=True)
                  for s, df in data.items()}
    trunc = gen_fn(trunc_data, variant)
    key = lambda t: (t.symbol, t.side, t.entry_ts_ms, t.exit_ts_ms,
                     round(t.entry_px, 10), round(t.exit_px, 10))
    full_closed = {key(t) for t in full if t.exit_ts_ms <= cut_ts_ms}
    trunc_closed = {key(t) for t in trunc if t.exit_ts_ms <= cut_ts_ms}
    assert full_closed == trunc_closed, (
        f"future data changed past trades: only-full={full_closed - trunc_closed} "
        f"only-trunc={trunc_closed - full_closed}")
```

```python
# tests/edge_lab/test_edge_lab_xs_momentum.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, assert_shift_invariant, make_daily  # noqa: E402
from edge_lab.candidates.xs_momentum import VARIANTS, generate_trades  # noqa: E402

V30 = next(v for v in VARIANTS if v.name == "lookback_30d")


def test_three_variants_declared():
    assert [v.name for v in VARIANTS] == ["lookback_7d", "lookback_30d", "lookback_90d"]
    assert all(v.candidate == "xs_momentum" for v in VARIANTS)


def test_ranks_longs_high_drift_shorts_low_drift(universe12):
    trades = generate_trades(universe12, V30)
    assert trades, "no trades generated"
    longs = {t.symbol for t in trades if t.side == "LONG"}
    shorts = {t.symbol for t in trades if t.side == "SHORT"}
    # drifted +0.4%/day symbols should dominate the long book
    assert {"S00USDT", "S01USDT", "S02USDT"} & longs
    assert {"S09USDT", "S10USDT", "S11USDT"} & shorts


def test_entries_only_on_mondays(universe12):
    trades = generate_trades(universe12, V30)
    for t in trades:
        dow = pd.Timestamp(t.entry_ts_ms, unit="ms", tz="UTC").dayofweek
        assert dow == 0, f"entry on non-Monday: {t}"


def test_entry_price_is_monday_open(universe12):
    trades = generate_trades(universe12, V30)
    t = trades[0]
    df = universe12[t.symbol]
    row = df[df["ts_ms"] == t.entry_ts_ms].iloc[0]
    assert t.entry_px == row["open"]


def test_holding_is_one_week(universe12):
    trades = generate_trades(universe12, V30)
    complete = [t for t in trades if t.exit_ts_ms - t.entry_ts_ms == 7 * DAY]
    assert len(complete) >= 0.9 * len(trades)   # tail week may truncate


def test_shift_invariance(universe12):
    cut = T0 + 200 * DAY
    assert_shift_invariant(generate_trades, universe12, V30, cut)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_xs_momentum.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `xs_momentum.py`. Sketch: collect sorted union of all `ts_ms`; identify Monday bars; for each rebalance Monday `m` (needs a following Monday `m_next` for the exit — else skip, the final open week is not emitted): for each symbol with a bar at `m` and at `m_next` and ≥ L+1 closes strictly before `m`, momentum = `close[last bar < m] / close[L days earlier] - 1`; rank; top 6 → LONG, bottom 6 → SHORT (when < 12 eligible symbols, quintile size = `max(1, n_eligible // 5)`); emit `Trade(sym, side, entry_ts_ms=m, exit_ts_ms=m_next, entry_px=open[m], exit_px=open[m_next])`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_xs_momentum.py --no-cov -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/candidates/xs_momentum.py tests/edge_lab/conftest.py tests/edge_lab/test_edge_lab_xs_momentum.py
git commit -m "feat(edge-lab): candidate 1 — weekly cross-sectional momentum, 3 lookback variants" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 9: Candidate 2 — funding carry

**Files:**
- Create: `backtesting/edge_lab/candidates/funding_carry.py`
- Test: `tests/edge_lab/test_edge_lab_funding_carry.py`

**Interfaces:**
- Produces: `generate_trades(daily: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]` — note the extra `funding` argument (DataFrames `ts_ms:int, funding_rate:str` ascending, from Task 4). Variant params: `(("threshold_mult", "1.5"),)` and `(("threshold_mult", "2"),)`; `VARIANTS` names `thresh_1.5x/thresh_2x`.
- Pinned rules (spec §4 + self-review pins): evaluated daily at each daily bar `t`. Entry signal at `t` uses the **last 3 settlements with `ts_ms < t_open`**: all same sign AND `|mean_rate| * settlements_per_hold ≥ threshold_mult × round_trip_cost_bps(symbol)/10000` where `settlements_per_hold = 9` (3 days × 3 settlements/day at 8h cadence — the expected funding collected over the minimum hold must clear the entry+exit cost). Direction: **against the crowd** — funding positive (longs pay) → SHORT (receives funding); negative → LONG. Entry at bar `t` open. Exit evaluated daily: when the persistence condition fails on the trailing 3 settlements (sign flip or mean below threshold), exit at the **next** day's open. One position per symbol at a time. Cost per symbol from `te_costs.round_trip_cost_bps` with the config slippage table (same numbers Gate 1 will charge — the threshold and the gate agree by construction).
- Funding P&L is NOT added to `gross_pnl` — `screen_trades` accounts funding separately via `funding_by_symbol`; the candidate's `gross_pnl` stays price-only. (Double-counting funding would inflate the screen.)

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_funding_carry.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, make_daily  # noqa: E402
from edge_lab.candidates.funding_carry import VARIANTS, generate_trades  # noqa: E402

V15 = next(v for v in VARIANTS if v.name == "thresh_1.5x")
EIGHT_H = 8 * 3_600_000


def _funding(symbol, rate, n=90, start=T0):
    return {symbol: pd.DataFrame({
        "ts_ms": [start + i * EIGHT_H for i in range(n)],
        "funding_rate": [rate] * n})}


def test_two_variants_declared():
    assert [v.name for v in VARIANTS] == ["thresh_1.5x", "thresh_2x"]


def test_high_positive_funding_opens_short():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    # 0.3%/settlement, wildly above any threshold; positive -> longs pay -> we SHORT
    trades = generate_trades(daily, _funding("AUSDT", "0.003"), V15)
    assert trades and all(t.side == "SHORT" for t in trades)


def test_negative_funding_opens_long():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    trades = generate_trades(daily, _funding("AUSDT", "-0.003"), V15)
    assert trades and all(t.side == "LONG" for t in trades)


def test_tiny_funding_never_enters():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    # 0.1 bp/settlement * 9 = 0.9 bp per hold vs threshold 1.5 * 31bp — no entry
    trades = generate_trades(daily, _funding("AUSDT", "0.00001"), V15)
    assert trades == []


def test_sign_flip_exits():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    n = 90
    rates = ["0.003"] * 45 + ["-0.003"] * 45          # flips mid-window
    f = {"AUSDT": pd.DataFrame({
        "ts_ms": [T0 + i * EIGHT_H for i in range(n)],
        "funding_rate": rates})}
    trades = generate_trades(daily, f, V15)
    assert trades
    first = trades[0]
    flip_ms = T0 + 45 * EIGHT_H
    assert first.exit_ts_ms <= flip_ms + 3 * DAY      # exits shortly after the flip


def test_no_funding_data_no_trades():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    assert generate_trades(daily, {}, V15) == []


def test_shift_invariance_manual():
    """Truncating both price and funding history must not change past trades."""
    from conftest import assert_shift_invariant
    daily = make_daily(["AUSDT"], n_days=120, seed=2)
    f = _funding("AUSDT", "0.003", n=360)
    cut = T0 + 60 * DAY
    gen = lambda d, v: generate_trades(
        d, {"AUSDT": f["AUSDT"][f["AUSDT"]["ts_ms"] <= cut]
            if d["AUSDT"]["ts_ms"].max() <= cut else f["AUSDT"]}, v)
    assert_shift_invariant(gen, daily, V15, cut)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_funding_carry.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `funding_carry.py`. Threshold comparison in Decimal: `abs(mean_rate) * 9 >= threshold_mult * rt_cost_bps / Decimal("10000")` with `mean_rate = sum(last3) / 3` over `Decimal(funding_rate)` values. `rt_cost_bps` computed once per symbol via `load_costs().round_trip_cost_bps(symbol, entry_liquidity=TAKER, exit_liquidity=TAKER, schedule=bybit_linear_perp(), slippage_table=SLIPPAGE_BPS, slippage_fallback=SLIPPAGE_FALLBACK_BPS)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_funding_carry.py --no-cov -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/candidates/funding_carry.py tests/edge_lab/test_edge_lab_funding_carry.py
git commit -m "feat(edge-lab): candidate 2 — funding carry with persistence rule, 2 threshold variants" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 10: Candidate 3 — low-frequency Donchian trend

**Files:**
- Create: `backtesting/edge_lab/candidates/lf_trend.py`
- Test: `tests/edge_lab/test_edge_lab_lf_trend.py`

**Interfaces:**
- Produces: `generate_trades(daily: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]`. Variant params `(("entry_n", E), ("exit_n", X))` ∈ {(20, 10), (55, 20)}; `VARIANTS` names `dc_20_10/dc_55_20`.
- Pinned rules: per symbol independently. Uses Task 2 `donchian` (channel excludes current bar). LONG entry signal at bar `t` when `close[t] > dc_entry_high[t]`; entry executes at bar `t+1` open. LONG exit signal when `close[t] < dc_exit_low[t]`; exit at `t+1` open. SHORT is the mirror (`close < dc_entry_low` enter / `close > dc_exit_high` exit). One position per symbol; an exit signal and opposite entry signal on the same bar close the old position and open the new one at the same `t+1` open (stop-and-reverse). Position still open at data end is discarded (not emitted) — only completed round trips are screened.

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_lf_trend.py
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, assert_shift_invariant, make_daily  # noqa: E402
from edge_lab.candidates.lf_trend import VARIANTS, generate_trades  # noqa: E402

V = next(v for v in VARIANTS if v.name == "dc_20_10")


def _trending_up(n=120):
    """Flat 30 bars then a strong uptrend — guarantees one clean breakout."""
    close = np.concatenate([np.full(30, 100.0), 100.0 * 1.01 ** np.arange(1, n - 29)])
    open_ = np.concatenate([[100.0], close[:-1]])
    return {"TUSDT": pd.DataFrame({
        "ts_ms": [T0 + i * DAY for i in range(n)],
        "open": open_, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": np.full(n, 1.0)})}


def test_two_variants_declared():
    assert [v.name for v in VARIANTS] == ["dc_20_10", "dc_55_20"]


def test_uptrend_produces_long():
    trades = generate_trades(_trending_up(), V)
    assert trades and trades[0].side == "LONG"


def test_entry_is_next_bar_open():
    data = _trending_up()
    trades = generate_trades(data, V)
    t = trades[0]
    df = data["TUSDT"]
    idx = df.index[df["ts_ms"] == t.entry_ts_ms][0]
    assert t.entry_px == df["open"].iloc[idx]
    # the breakout close happened strictly before the entry bar
    assert df["close"].iloc[idx - 1] > df["high"].iloc[max(0, idx - 21):idx - 1].max()


def test_open_position_at_end_not_emitted():
    data = _trending_up()          # trend never reverses: position never exits
    trades = generate_trades(data, V)
    for t in trades:
        assert t.exit_ts_ms <= data["TUSDT"]["ts_ms"].iloc[-1]


def test_few_trades_low_frequency(universe12):
    trades = generate_trades(universe12, V)
    # 12 symbols * 400 days of noise: Donchian should fire rarely
    assert len(trades) < 12 * 20


def test_shift_invariance(universe12):
    assert_shift_invariant(generate_trades, universe12, V, T0 + 250 * DAY)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_lf_trend.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `lf_trend.py` — iterate bars per symbol with a small state machine (`flat/long/short`), signals from `donchian` columns, fills at next bar open per the pinned rules.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_lf_trend.py --no-cov -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/candidates/lf_trend.py tests/edge_lab/test_edge_lab_lf_trend.py
git commit -m "feat(edge-lab): candidate 3 — Donchian breakout trend, 2 channel variants" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 11: Candidate 4 — vol breakout (squeeze expansion)

**Files:**
- Create: `backtesting/edge_lab/candidates/vol_breakout.py`
- Test: `tests/edge_lab/test_edge_lab_vol_breakout.py`

**Interfaces:**
- Produces: `generate_trades(h4: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]` — operates on **240m bars** (the only candidate that does). Single variant: `VARIANTS = [Variant("vol_breakout", "sqz_default", (("bb_n", 20), ("bb_mult", "2.0"), ("kc_n", 20), ("kc_mult", "1.5"), ("atr_n", 14), ("stop_atr_mult", "2.0"), ("max_hold_bars", 30), ("min_squeeze_bars", 6)))]`.
- Pinned rules (spec §4 pins): squeeze qualifies when `squeeze_on` was True for ≥ 6 consecutive bars ending at `t−1` and is False at `t` (release). Direction: `close[t] > kc_upper[t]` → LONG; `close[t] < kc_lower[t]` → SHORT; release without a band break → no trade. Entry at bar `t+1` open. Exit: adverse stop at `entry_px ∓ 2.0 × ATR14[t]` (ATR frozen at signal bar) — checked against bar closes, exit at the **next bar open** after the breach close (conservative simplification: no intrabar stop fills; documented in the verdict); or time exit at 30 bars (5 days) after entry, at that bar's open. One position per symbol.

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_vol_breakout.py
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.vol_breakout import VARIANTS, generate_trades  # noqa: E402

H4 = 4 * 3_600_000
V = VARIANTS[0]


def _squeeze_then_pop(n=200, pop_at=100, direction=1.0):
    """Tight flat range (BB inside KC) then an explosive move."""
    rng = np.random.default_rng(5)
    close = np.empty(n)
    close[:pop_at] = 100.0 + rng.normal(0, 0.05, pop_at)       # very tight
    steps = direction * np.abs(rng.normal(1.5, 0.3, n - pop_at))
    close[pop_at:] = close[pop_at - 1] + np.cumsum(steps)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return {"VUSDT": pd.DataFrame({
        "ts_ms": [T0 + i * H4 for i in range(n)],
        "open": open_, "high": np.maximum(open_, close) + 0.05,
        "low": np.minimum(open_, close) - 0.05, "close": close,
        "volume": np.full(n, 1.0)})}


def test_single_variant_declared():
    assert len(VARIANTS) == 1 and VARIANTS[0].name == "sqz_default"


def test_upward_pop_goes_long():
    trades = generate_trades(_squeeze_then_pop(direction=1.0), V)
    assert trades and trades[0].side == "LONG"


def test_downward_pop_goes_short():
    trades = generate_trades(_squeeze_then_pop(direction=-1.0), V)
    assert trades and trades[0].side == "SHORT"


def test_time_exit_bounds_holding():
    data = _squeeze_then_pop()
    trades = generate_trades(data, V)
    for t in trades:
        assert (t.exit_ts_ms - t.entry_ts_ms) <= 31 * H4


def test_no_squeeze_no_trades():
    """Steady high-vol trend without a squeeze phase: no entries."""
    rng = np.random.default_rng(6)
    n = 200
    close = 100.0 * np.cumprod(1 + rng.normal(0, 0.03, n))
    open_ = np.concatenate([[100.0], close[:-1]])
    data = {"VUSDT": pd.DataFrame({
        "ts_ms": [T0 + i * H4 for i in range(n)],
        "open": open_, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, 1.0)})}
    trades = generate_trades(data, V)
    assert len(trades) <= 2      # noise may fake one squeeze; a stream means a bug


def test_shift_invariance():
    data = _squeeze_then_pop(n=300)
    assert_shift_invariant(generate_trades, data, V, T0 + 200 * H4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_vol_breakout.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `vol_breakout.py` — precompute `squeeze_on`, `keltner`, `atr` columns once per symbol (Task 2 functions), then a per-bar state machine per the pinned rules.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_vol_breakout.py --no-cov -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/candidates/vol_breakout.py tests/edge_lab/test_edge_lab_vol_breakout.py
git commit -m "feat(edge-lab): candidate 4 — squeeze-release vol breakout on 240m bars" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 12: Verdict writer + battery orchestrator

**Files:**
- Create: `backtesting/edge_lab/verdicts.py`
- Create: `backtesting/edge_lab/run_battery.py`
- Test: `tests/edge_lab/test_edge_lab_battery.py`

**Interfaces:**
- Produces:
  - `verdicts.py`: `render_verdict(candidate: str, variants: list[dict], universe_pin: dict, sanity_summary: str, date_str: str) -> str` — killtest-style markdown (H3/H4 verdict format): header with candidate + date; per-variant table (`variant, n_trades, gross_edge_bps, cost_bps_taker, ratio_taker, gate1_verdict, dsr, pooled_pf, positive_path_frac, gate2_passed`); overall verdict = `PASS` only if ≥1 variant passed both gates, else `REJECT`, or `ERROR` when the candidate raised; a **Caveats** section that ALWAYS includes verbatim: *"Survivorship: the universe is today's top-30 by turnover with a ≥2y listing filter; assets that died before the pin date are absent. This biases results optimistic by an unmeasured amount."* plus the funding-exclusion note when any screened symbol lacked a funding series, and the trials accounting line (`num_trials floor = 16: 8 battery variants + 8 historical strategy families`). `write_verdict(text: str, candidate: str, date_str: str, out_dir: Path) -> Path` → `<out_dir>/<candidate>-verdict-<YYYYMMDD>.md`.
  - `run_battery.py`: `run_battery(data_dir: Path, pin_path: Path, out_dir: Path, now_ms: int, candidates: dict | None = None) -> dict` — pure orchestration, network-free (data must already be fetched): loads pin + kline/funding CSVs; Gate 0 per symbol (defect symbols dropped from `daily`/`h4` dicts and named in the sanity summary); for each candidate module (default registry: the 4 modules' `(VARIANTS, generate_trades)` — funding_carry's extra arg handled via a small adapter): for each variant, `generate_trades` → `write_trades_csv` to `<out_dir>/trades/<candidate>_<variant>.csv` → Gate 1 → if `verdict == "PASS"`, build daily returns (Task 7) with per-candidate `label_horizon_days` from `LABEL_HORIZONS = {"xs_momentum": 7, "funding_carry": 10, "lf_trend": 30, "vol_breakout": 5}` → Gate 2. **A candidate raising anywhere yields `{"error": traceback.format_exc()}` in its result and the loop continues** — the battery always completes. Zero-trade variants record `n_trades=0, gate1_verdict="NO_TRADES"` (screen refuses empty CSVs — don't call it). Returns `{candidate: {"variants": [...], "verdict": "PASS|REJECT|ERROR"}}`; writes one verdict doc per candidate + `battery-summary-<date>.md` listing all four one-line verdicts + the sanity table.
  - `main()` CLI: `--data-dir backtesting/data` `--pin <path>` `--out .planning/evidence/killtests` `--date YYYY-MM-DD`; boots sys.path (repo root + `backtesting/`) before edge_lab imports.
- Consumes: everything from Tasks 1–11.

- [ ] **Step 1: Write the failing tests**

```python
# tests/edge_lab/test_edge_lab_battery.py
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, make_daily  # noqa: E402
from edge_lab.run_battery import run_battery  # noqa: E402
from edge_lab.trades import Trade, Variant  # noqa: E402


def _write_daily_csvs(data_dir, daily):
    import pandas as pd
    from edge_lab.fetch import kline_csv_path
    for sym, df in daily.items():
        out = pd.DataFrame({
            "timestamp": pd.to_datetime(df["ts_ms"], unit="ms"),
            "symbol": sym, "interval": "D", "open": df["open"],
            "high": df["high"], "low": df["low"], "close": df["close"],
            "volume": df["volume"], "turnover": df["volume"],
            "is_mainnet": True, "created_at": df["ts_ms"].iloc[-1]})
        out.to_csv(kline_csv_path(data_dir, sym, "D", 730), index=False)


def _pin(tmp_path, symbols):
    from edge_lab.universe import write_pin
    sel = [{"symbol": s, "turnover24h": 1.0, "launch_ms": 0} for s in symbols]
    return write_pin(sel, [], "2026-08-16", tmp_path)


def _stub_registry(gen_map):
    """candidate name -> generate_trades(data_bundle, variant) stub registry."""
    return {name: {"variants": [Variant(name, "v0", ())], "generate": fn}
            for name, fn in gen_map.items()}


def test_crashing_candidate_isolated(tmp_path):
    daily = make_daily(["AUSDT", "BUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT", "BUSDT"])

    def boom(bundle, variant):
        raise RuntimeError("candidate exploded")

    def quiet(bundle, variant):
        return []

    res = run_battery(tmp_path, pin, tmp_path / "out", T0 + 400 * DAY,
                      candidates=_stub_registry({"boom": boom, "quiet": quiet}))
    assert res["boom"]["verdict"] == "ERROR"
    assert "candidate exploded" in res["boom"]["error"]
    assert res["quiet"]["verdict"] == "REJECT"          # completed despite boom


def test_zero_trades_recorded_not_screened(tmp_path):
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])
    res = run_battery(tmp_path, pin, tmp_path / "out", T0 + 400 * DAY,
                      candidates=_stub_registry({"quiet": lambda b, v: []}))
    v = res["quiet"]["variants"][0]
    assert v["n_trades"] == 0 and v["gate1_verdict"] == "NO_TRADES"


def test_verdict_docs_written_with_caveats(tmp_path):
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    def one_trade(bundle, variant):
        return [Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0)]

    out = tmp_path / "out"
    run_battery(tmp_path, pin, out, T0 + 400 * DAY,
                candidates=_stub_registry({"solo": one_trade}))
    docs = list(out.glob("solo-verdict-*.md"))
    assert len(docs) == 1
    text = docs[0].read_text()
    assert "Survivorship" in text and "num_trials floor = 16" in text
    summaries = list(out.glob("battery-summary-*.md"))
    assert len(summaries) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_battery.py --no-cov -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** `verdicts.py` + `run_battery.py` per the interface block. The default candidate registry adapts signatures: `xs_momentum/lf_trend` take `bundle["daily"]`; `vol_breakout` takes `bundle["h4"]`; `funding_carry` takes `(bundle["daily"], bundle["funding"])`. The stub registry in tests receives the whole bundle — the adapter passes `bundle` when the registry entry is a stub (`"generate"` key), keeping tests decoupled from real candidates.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/edge_lab/test_edge_lab_battery.py --no-cov -q`
Expected: 3 passed. Then run the whole suite: `python3 -m pytest tests/edge_lab/ --no-cov -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add backtesting/edge_lab/verdicts.py backtesting/edge_lab/run_battery.py tests/edge_lab/test_edge_lab_battery.py
git commit -m "feat(edge-lab): battery orchestrator with crash isolation + killtest-format verdict writer" -- backtesting/edge_lab tests/edge_lab
```

---

### Task 13: Execution run — fetch real data, run battery, file verdicts

This task is operator-facing execution, not TDD. Prereqs: Tasks 1–12 merged, full `tests/edge_lab/` suite green.

- [ ] **Step 1: Select and pin the universe**

Write a tiny driver or run inline Python (repo root):

```bash
python3 - <<'EOF'
import sys, time
from pathlib import Path
sys.path.insert(0, "backtesting")
from edge_lab.fetch import BybitPublic
from edge_lab.universe import select_universe, write_pin

c = BybitPublic()
now_ms = int(time.time() * 1000)
selected, excluded = select_universe(c.tickers(), c.instruments(), now_ms)
pin = write_pin(selected, excluded, "2026-08-16", Path("backtesting/edge_lab"))
print(pin, len(selected), "selected;", len(excluded), "excluded")
EOF
```

Expected: 30 symbols, pin file at `backtesting/edge_lab/universe_2026-08-16.json`. Sanity-check the list contains BTCUSDT/ETHUSDT near the top.

- [ ] **Step 2: Fetch klines + funding for the pinned universe**

```bash
python3 - <<'EOF'
import sys, time
from pathlib import Path
sys.path.insert(0, "backtesting")
from edge_lab.fetch import BybitPublic, ensure_klines, ensure_funding
from edge_lab.universe import load_pin
from edge_lab.config import DAILY_LOOKBACK_DAYS, H4_LOOKBACK_DAYS

c = BybitPublic()
now_ms = int(time.time() * 1000)
data_dir = Path("backtesting/data")
pin = load_pin("backtesting/edge_lab/universe_2026-08-16.json")
for s in pin["symbols"]:
    sym = s["symbol"]
    ensure_klines(c, data_dir, sym, "D", DAILY_LOOKBACK_DAYS, now_ms)
    ensure_klines(c, data_dir, sym, "240", H4_LOOKBACK_DAYS, now_ms)
    ensure_funding(c, data_dir, sym, DAILY_LOOKBACK_DAYS, now_ms)
    print("done", sym)
EOF
```

~90 files (30 × daily + 30 × 240m + 30 × funding). Resumable: rerun skips existing files. Funding CSVs land in `backtesting/data/funding/` — the first funding data this repo has ever had.

- [ ] **Step 3: Run the battery**

```bash
python3 backtesting/edge_lab/run_battery.py \
  --data-dir backtesting/data \
  --pin backtesting/edge_lab/universe_2026-08-16.json \
  --out .planning/evidence/killtests \
  --date 2026-08-16
```

Expected output: sanity table (any dropped symbols named), per-variant gate results, 4 verdict docs + 1 battery summary in `.planning/evidence/killtests/`.

- [ ] **Step 4: Hostile review of any PASS**

If (and only if) any candidate verdict is PASS: dispatch the `quant-skeptic` agent on that verdict doc + its trades CSV before calling it a pass. Its default verdict is *no edge*; targets: look-ahead, survivorship handling, trial accounting, regime concentration. Attach its findings to the verdict doc under a **Hostile review** section.

- [ ] **Step 5: Record and commit evidence**

- Update `.planning/STATE.md` Session Continuity + `progress.md` with the battery outcome (one paragraph each).
- Commit in two chunks:

```bash
git add backtesting/edge_lab/universe_2026-08-16.json
git commit -m "feat(edge-lab): pin 2026-08-16 top-30 universe" -- backtesting/edge_lab/universe_2026-08-16.json
git add .planning/evidence/killtests/*-verdict-2026*.md .planning/evidence/killtests/battery-summary-*.md .planning/STATE.md progress.md
git commit -m "docs(evidence): edge research battery verdicts 2026-08-16" -- .planning/evidence/killtests .planning/STATE.md progress.md
```

Data CSVs (~90 files) follow the existing `backtesting/data/` convention — commit them only if the operator wants the snapshot versioned (existing `*_bybit.csv` files ARE committed; default: commit the funding CSVs at minimum, they are small and unblock `screen.py` funding-inclusive verdicts repo-wide).

- [ ] **Step 6: Honest close-out**

Whatever the outcome, state it plainly: a clean 4× REJECT is a successful battery run (spec §1 — the infrastructure's value is killing bad strategies cheaply). No PASS gets called an edge until it also survives Step 4 hostile review — and even then it is a *forward-paper-test recommendation*, not an engine deployment (out of scope, spec §2).

---

## Self-review record

- **Spec coverage:** §3.1 universe → Task 3; §3.2 data/funding → Task 4; §3.3 costs → Tasks 1/6 (config + fallback, no costs.py edits); §3.4 interface → Tasks 1/8–11; §4 battery + pins → Tasks 8–11 (8 variants: 3+2+2+1); §5 gates → Tasks 5/6/7/12 + Task 13 Step 4 (Gate 3); §6 error handling → Task 4 (retry/resume), Task 5 (named drops), Task 12 (crash isolation, NO_TRADES); §7 testing → shift-invariance in conftest + per-candidate tests, cost-Decimal tests (Task 6), ranking fixture (Task 8), pooled-PF zero-loss regression (Task 7), CSV contract (Task 1); §8 deliverables → Tasks 12/13.
- **Known deviation from spec, justified:** spec §4 said vol-breakout "reuses SQZMOM machinery"; recon showed the service class is latest-value-shaped, O(n·period) slow, and claims the `app` package — Task 2 reimplements the exact formulas locally with source-line citations instead. Same math, testable, no service coupling.
- **Type consistency check:** `Trade`/`Variant` defined once (Task 1), consumed by 8–12; `generate_trades` signature uniform except funding_carry's documented extra arg, adapted in Task 12's registry; Gate 1 verdict strings are `"PASS"/"KILL"` (screen.py's literals) and Task 12 maps them to the candidate-level `PASS/REJECT/ERROR`.
