# Phase 4 Measurement (H3/H4 Kill Tests) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the permanent `backtesting/killtests/` harness that answers audit hypotheses H3 (ATR-stop replay of the 13 real entries) and H4 (ensemble signal-vs-forward-return information test with DSR gating), per the approved spec `docs/superpowers/specs/2026-08-05-phase4-measurement-h3-h4-design.md`.

**Architecture:** Three layers. (1) Data: 12-month mainnet kline backfill through bybit-connector into 11-col CSVs. (2) H3: a fixed-entry bracket walker (stop-first pessimistic, `validate_mr_rr_fix.py` pattern) over the 13 closed positions with ATR-derived stops. (3) H4: the deployed signal chain run **unmodified** offline — real TA FastAPI app behind `httpx.ASGITransport`, real `SignalAggregator`/MTF/`CoreAggregator`/`MultiStrategyEnsemble` loaded via the proven dual-namespace shims — producing a signal series scored against 24h forward log-returns with CPCV→DSR from the risk-metrics kernels.

**Tech Stack:** Python 3.12, pandas/numpy, httpx (ASGITransport + MockTransport), pytest (host-run, `--no-cov`), existing repo modules (no new dependencies).

## Global Constraints

- **Account:** $100. Capital constants ONLY via `from shared.account import PAPER_INITIAL_BALANCE, TAKER_FEE_PER_SIDE` (host-run code). Never write an account-size literal.
- **All code is host-run** from the repo root (`/mnt/d/Bimo_max/crypto-trading-bot`). Nothing here runs in containers.
- **Tests:** always `pytest --no-cov`. New tests live under `tests/killtests/`.
- **No new DSR/CPCV implementations.** Import from `services/risk-metrics-service/app/sharpe_metrics.py` and `cpcv.py` (a third hand-rolled DSR already exists in `run_walk_forward.py:200`; do not add a fourth).
- **No direct-Bybit HTTP.** All fetches route through bybit-connector at `http://localhost:8001` (BC-02/D-04 policy; `bybit_data_fetcher.py` already complies).
- **Testnet data is forbidden.** Every candle consumed must carry `is_mainnet=True`.
- **Deployed-path bugs are preserved, not fixed** (spec §3.3). If you find yourself "fixing" the ensemble while building the replay, stop — that is out of scope.
- **Profit factor** is always pooled `sum(wins)/abs(sum(losses))` — never mean-of-folds.
- **Verdict criteria are verbatim from AUDIT.md §7** — H3: stop-out rate < 40% AND gross expectancy > 0 pre-fee. H4: directional accuracy > 50% AND DSR > 0.95 with `num_trials >= 8`.
- **Commits:** conventional messages, one concern per commit, on branch `fix/audit-phase1`.
- Python interpreter: `python3`. Working dir for every command: repo root.

## Verified interface facts (read before any task; source of truth for signatures)

- `BybitDataFetcher` (`backtesting/bybit_data_fetcher.py`): `__init__(base_url=None)` → env `BYBIT_CONNECTOR_URL` → `http://localhost:8001`. `download_historical_data(symbol, interval='60', days=90, output_file=None) -> pd.DataFrame` paginates backwards from `now` with `max_candles_per_request = 200` (line 246); other `limit: int = 200` defaults at lines 119 and 183. Connector wrapper response: `{"success": bool, "data": {"list": [[startTime, open, high, low, close, volume, turnover], ...]}}`, newest-first. CSV written today: 6 cols `timestamp,open,high,low,close,volume`, filename `{symbol}_{interval}m_{days}d_bybit.csv`. D-04 probes: `assert_connector_reachable_sync()` (CLI) + lazy async probe on first `fetch_klines`.
- Target 11-col CSV schema (matches existing `backtesting/data/BTCUSDT_60m_60d.csv`): `timestamp,symbol,interval,open,high,low,close,volume,turnover,is_mainnet,created_at` with `timestamp` as `YYYY-MM-DD HH:MM:SS` (naive UTC) and `is_mainnet` boolean.
- Postgres (container `crypto-bot-postgres`, db **`cryptobot`**, user `cryptobot`): `positions` has `id, position_id (uuid), symbol, side (LONG|SHORT), quantity, entry_price, exit_price, status (OPEN|CLOSED), opened_at, closed_at (timestamp without time zone), realized_pnl, entry_fee, exit_fee, entry_signal_confidence (NULL on all 13 closed rows)`. `trades` has `trade_id, symbol, side (BUY|SELL), quantity, price, fee, strategy, signal_confidence, executed_at, metadata (jsonb, keys: order_type, position_id)`. **There is no `signal_indicators` column** — entry confidence comes from the entry trade row's `signal_confidence`. The 13 closed positions are ids 46–56, 59–60.
- `ATRStopCalculator` (`services/trading-engine/app/atr_stops.py`): `__init__(risk_level=RiskLevel.MODERATE, atr_period=14, custom_multipliers=None)`; `calculate_atr(self, highs: list, lows: list, closes: list) -> float` — **SMA of true ranges** (not Wilder), returns `0.0` if `len(highs) < atr_period + 1`.
- `BacktestEngine` opens positions at bar close with engine-computed size — it **cannot** pin entries to recorded fill prices/times. H3 uses a custom walker; it copies the engine's pessimistic intrabar rule: **stop checked before take-profit, for both sides** (`backtest_engine.py:322-362`).
- Kernels: `sharpe_metrics.py` is numpy-only, no intra-package imports. `cpcv.py` does `from app.sharpe_metrics import deflated_sharpe_ratio` (line 40) — and the name `app` collides with the trading-engine/TA namespaces. Killtests load both via `importlib.util.spec_from_file_location` under unique module names, satisfying cpcv's import with a temporary `sys.modules["app.sharpe_metrics"]` alias that is restored afterwards (never purging `sys.modules["app"]`) — idempotent and callable before OR after the TE namespace exists (Task 8 `_load_kernels`).
  - `deflated_sharpe_ratio(returns: np.ndarray, num_trials: int, trial_sharpes_variance: float) -> float` (pass: > 0.95).
  - `CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.01).split(n_samples: int, label_horizon: int) -> Iterator[CPCVSplit]` where `CPCVSplit` has `train_idx, test_idx, test_groups, path_id`.
  - `cpcv_to_dsr(returns_per_path: Sequence[np.ndarray], concatenated_returns: np.ndarray) -> float` (NaN if < 2 valid paths).
- TA service (`services/technical-analysis/`): FastAPI object `app` in `app/main.py:162`; **no route depends on lifespan state** (lifespan only pings market-data and closes the fetcher) — safe to use with `httpx.ASGITransport` without lifespan. Zero required env vars (all Settings fields have defaults; `market_data_url` default `http://localhost:8002`). Module import side effects: creates `logs/` in cwd; registers Prometheus collectors in the global registry (**import `app.main` exactly once per process** — a second exec raises `Duplicated timeseries`).
- TA candle seam: module-level singleton `app/fetcher.py:275` `_fetcher: Optional[MarketDataFetcher]`. All consumers call `get_fetcher()` at request time, so the correct patch is either setting `_fetcher` or (preferred here, keeps real validation) **swapping the real fetcher's `self.client`** with a mocked httpx client. `MarketDataFetcher.get_klines` calls `GET {market_data_url}/api/v1/klines/{symbol}?interval=..&limit=..&mainnet_only=true` and expects `{"success": true, "data": [{timestamp, open, high, low, close, volume}, ...]}` (timestamp epoch-ms int). `get_klines_as_dataframe` then validates: drops bad OHLC, drops |log return| > 0.35, drops the still-forming last candle using **wall clock** (historical candles are never dropped — an as-of feed passes through untouched), raises `ValueError` if < 30 rows remain.
- Trading-engine side (loaded via dual-namespace shims, template `backtesting/run_walk_forward_ensemble.py:58-191`): PHASE 1 imports under TA's `app`, capture references; PHASE 2 purge `sys.modules` of `app`/`app.*` and remove the TA path; PHASE 3 register a synthetic `app` package and `_load_te_module(dotted_name, rel_path)` each needed TE file via `importlib.util.spec_from_file_location`, with hand stubs for `app.models`, `app.config.get_settings`, `app.monitoring.metrics`, and an `app.aggregation` package whose real `__init__.py` never runs.
- `SignalAggregator.__init__` builds `self.client = httpx.AsyncClient(timeout=30.0)` inline and `self.base_url = settings.technical_analysis_url` — inject by **replacing `agg.client` post-construction**. `get_trading_signal_multi_timeframe(symbol, primary_interval='60', timeframes=None, regime_analysis=None) -> TradingSignal`; live call uses `timeframes=['15', '60', '240']`; it lazily does `from app.aggregation import get_multi_timeframe_analyzer` (line 974) — the aggregation stub package must expose that accessor. Its top-of-file imports also include `from app.aggregation import CoreAggregator` (line 22) and `from app.services.indicator_registry import get_indicator_registry` (line 24) — the stub set must cover both. Timestamps come from **function-local** `import time` (lines 924, 975, 1116) — a module-attribute patch is a no-op; pin by patching `time.time` process-wide (`unittest.mock.patch`) around each replay call.
- `MarketRegimeDetector`: cache `self._cache: Dict[str, Tuple[float, RegimeAnalysis]]` keyed `f"{symbol}_{interval}"`, TTL vs wall clock — **clear per replayed bar**. The detector lives at `aggregator.core_aggregator.regime_detector` (`aggregator_core.py:119`), NOT on the aggregator directly. It fetches ADX by constructing `httpx.AsyncClient` **inline per call** (`market_regime.py:242`) — no attribute exists to swap; redirect by patching the loaded `app.aggregation.market_regime` module's `httpx` name with a factory shim. Left unpatched, the fetch fails silently and every bar degrades to the UNKNOWN default regime — divergence the golden gate would NOT catch (both legs would share the dead URL).
- `MultiStrategyEnsemble.__init__(mean_reversion=None)`; `generate_signal(aggregator_signal: TradingSignal, current_price: float, capital: float = 100.0) -> Optional[EnsembleSignal]` (sync; returns None for HOLD / no legs fired). `EnsembleSignal` dataclass fields: `action, confidence, entry_price, stop_loss, take_profit, position_size_pct, reasoning, leg_contributions, leg_actions, weights_snapshot`. Weights singleton `get_ensemble_weights()` reads `/app/data/ensemble_weights.json` — absent on host → default win rates 0.50 each → **normalized weights ⅓/⅓/⅓ automatically**. `MAX_POSITION_PCT` property reads `get_settings().max_risk_per_trade` at call time — the config stub must provide it (0.10) plus `ensemble_min_position_pct=0.05`, `ensemble_confidence_size_multiplier=3.7`.
- `TradingSignal` fields: `symbol, timestamp (ms int), action, confidence (0-1), indicators (Dict[str, IndicatorSignal]), aggregated_score (-1..1), consensus_count, strategy, metadata`. `IndicatorSignal`: `name, signal, confidence, value, metadata` + `numeric_value()`.
- Timeframe weights: `{"15": 0.20, "60": 0.50, "240": 0.30}` built in `MultiTimeframeAnalyzer.__init__` from the `TimeframeWeight` enum.

---

### Task 1: Backfill capacity + 11-col schema in `bybit_data_fetcher.py`

**Files:**
- Modify: `backtesting/bybit_data_fetcher.py` (lines 119, 183, 246; CSV write block ~307-345; CLI ~394-431)
- Test: `tests/killtests/test_backfill_fetcher.py` (new directory; deliberately NO `__init__.py` — test files must stay importable in pytest's rootdir mode so `from conftest import ...` works in later tasks)

**Interfaces:**
- Consumes: existing `BybitDataFetcher` (see facts above).
- Produces: `download_historical_data(..., schema='legacy'|'klines')` — `'klines'` writes the 11-col CSV; `assert_connector_live(fetcher) -> None` (async) which raises `RuntimeError` if the newest fetched candle is stale (tape-mode guard); CLI flags `--schema klines` and `--out-dir`. Batch size 1000.

- [ ] **Step 1: Write the failing tests**

Create `tests/killtests/test_backfill_fetcher.py`:

```python
"""Backfill fetcher upgrade: batch size 1000, 11-col klines schema, liveness guard."""
import asyncio
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

import bybit_data_fetcher as bdf  # noqa: E402

KLINES_COLUMNS = [
    "timestamp", "symbol", "interval", "open", "high", "low", "close",
    "volume", "turnover", "is_mainnet", "created_at",
]


def _mk_rows(n, start_ms, interval_min=60):
    """Bybit v5 rows, newest-first, [startTime, open, high, low, close, volume, turnover]."""
    step = interval_min * 60 * 1000
    rows = []
    for i in range(n):
        ts = start_ms + i * step
        rows.append([str(ts), "100", "101", "99", "100.5", "10", "1000"])
    rows.reverse()
    return rows


class FakeFetcher(bdf.BybitDataFetcher):
    """Bypass HTTP: serve canned batches; record requested limits."""

    def __init__(self, batches):
        # deliberately do NOT call super().__init__ — no httpx client needed
        self.rate_limit_delay = 0
        self._reachability_checked = True
        self._batches = list(batches)
        self.requested_limits = []

    async def fetch_klines(self, symbol, interval, start_time=None, end_time=None, limit=200):
        self.requested_limits.append(limit)
        return self._batches.pop(0) if self._batches else []


def test_pagination_requests_limit_1000():
    now_ms = int(time.time() * 1000)
    f = FakeFetcher([_mk_rows(1000, now_ms - 1000 * 3600 * 1000), []])
    asyncio.run(f.download_historical_data("BTCUSDT", interval="60", days=50))
    assert f.requested_limits and all(l == 1000 for l in f.requested_limits)


def test_default_limits_are_1000():
    import inspect
    assert inspect.signature(bdf.BybitDataFetcher.fetch_klines).parameters["limit"].default == 1000
    assert inspect.signature(bdf.BybitDataFetcher.get_klines).parameters["limit"].default == 1000


def test_klines_schema_csv(tmp_path):
    now_ms = int(time.time() * 1000)
    f = FakeFetcher([_mk_rows(48, now_ms - 48 * 3600 * 1000), []])
    out = tmp_path / "BTCUSDT_60m_2d_bybit.csv"
    asyncio.run(
        f.download_historical_data(
            "BTCUSDT", interval="60", days=2, output_file=str(out), schema="klines"
        )
    )
    df = pd.read_csv(out)
    assert list(df.columns) == KLINES_COLUMNS
    assert df["is_mainnet"].all()
    assert (df["symbol"] == "BTCUSDT").all()
    assert (df["interval"].astype(str) == "60").all()


def test_legacy_schema_unchanged(tmp_path):
    now_ms = int(time.time() * 1000)
    f = FakeFetcher([_mk_rows(48, now_ms - 48 * 3600 * 1000), []])
    out = tmp_path / "legacy.csv"
    asyncio.run(
        f.download_historical_data("BTCUSDT", interval="60", days=2, output_file=str(out))
    )
    df = pd.read_csv(out)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_assert_connector_live_rejects_stale():
    """Newest candle older than 3 intervals => tape mode / frozen data => RuntimeError."""
    stale_ms = int(time.time() * 1000) - 10 * 3600 * 1000
    f = FakeFetcher([_mk_rows(5, stale_ms)])
    with pytest.raises(RuntimeError, match="stale"):
        asyncio.run(bdf.assert_connector_live(f, symbol="BTCUSDT", interval="60"))


def test_assert_connector_live_accepts_fresh():
    fresh_ms = int(time.time() * 1000) - 2 * 3600 * 1000
    f = FakeFetcher([_mk_rows(5, fresh_ms)])
    asyncio.run(bdf.assert_connector_live(f, symbol="BTCUSDT", interval="60"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/killtests/test_backfill_fetcher.py -v --no-cov`
Expected: FAIL — `test_default_limits_are_1000` asserts 1000 vs current 200; `download_historical_data` has no `schema` kwarg (TypeError); `assert_connector_live` not defined.

- [ ] **Step 3: Implement the fetcher changes**

In `backtesting/bybit_data_fetcher.py`:

(a) Change the three limit sites — line 119 and line 183: `limit: int = 200` → `limit: int = 1000`; line 246: `max_candles_per_request = 200  # Bybit limit` → `max_candles_per_request = 1000  # Bybit v5 hard cap (connector clamps via min(limit, 1000))`.

(b) Add `schema` parameter to `download_historical_data(self, symbol, interval="60", days=90, output_file=None, schema="legacy")`. In the CSV-write block (after the existing `df = df[["timestamp", "open", "high", "low", "close", "volume"]]` — keep a pre-trim copy of `turnover` for this), write:

```python
        if output_file:
            if schema == "klines":
                out = df.copy()
                out["symbol"] = symbol
                out["interval"] = interval
                out["turnover"] = turnover_series.values  # kept from pre-trim df
                out["is_mainnet"] = True
                out["created_at"] = int(time.time() * 1000)
                out = out[[
                    "timestamp", "symbol", "interval", "open", "high", "low",
                    "close", "volume", "turnover", "is_mainnet", "created_at",
                ]]
                out.to_csv(output_file, index=False)
            else:
                df.to_csv(output_file, index=False)
            logger.info(f"Data saved to: {output_file} (schema={schema})")
```

Concretely: just before the column-trim line, insert `turnover_series = df["turnover"].copy()`. Add `import time` at module top if absent.

(c) Add the liveness guard as a module-level async function (near the D-04 probes):

```python
async def assert_connector_live(
    fetcher: "BybitDataFetcher", symbol: str = "BTCUSDT", interval: str = "60"
) -> None:
    """Refuse to backfill from a connector serving frozen tape fixtures.

    A connector in MARKET_DATA_SOURCE=tape mode answers /health and serves
    klines, but the newest candle is weeks old. Fresh mainnet data must have
    a candle newer than 3 intervals ago.
    """
    rows = await fetcher.fetch_klines(symbol=symbol, interval=interval, limit=5)
    if not rows:
        raise RuntimeError("connector returned no candles; cannot verify liveness")
    newest_ms = max(int(r[0]) for r in rows)
    interval_ms = fetcher.convert_interval_to_minutes(interval) * 60 * 1000  # instance method (bybit_data_fetcher.py:193)
    age = int(time.time() * 1000) - newest_ms
    if age > 3 * interval_ms:
        raise RuntimeError(
            f"connector data is stale: newest {symbol}/{interval} candle is "
            f"{age / 3600000:.1f}h old — is bybit-connector in tape mode? "
            f"(MARKET_DATA_SOURCE must be 'live', see docker-compose.unified.yml:453)"
        )
```

(d) CLI: add `parser.add_argument("--schema", choices=["legacy", "klines"], default="legacy")` and `parser.add_argument("--out-dir", type=str, default="backtesting/data")`; thread `schema=args.schema` through the single and `--multiple` paths (`download_multiple_symbols` gains and forwards `schema` and `output_dir=args.out_dir`); in `main()`, call `await assert_connector_live(fetcher)` before any download.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/killtests/test_backfill_fetcher.py -v --no-cov`
Expected: 6 PASS.

- [ ] **Step 5: Run the fetcher's existing consumers' smoke check**

Run: `python3 -c "import sys; sys.path.insert(0,'backtesting'); import bybit_data_fetcher; print('import OK')"`
Expected: `import OK` (no syntax errors; legacy default keeps old callers working).

- [ ] **Step 6: Commit**

```bash
git add backtesting/bybit_data_fetcher.py tests/killtests/
git commit -m "feat(backtesting): 1000-bar batches, 11-col klines CSV schema, tape-liveness guard"
```

---

### Task 2: Execute the 12-month backfill and validate it

**Files:**
- Create: `backtesting/killtests/__init__.py` (empty), `backtesting/killtests/backfill_manifest.py`
- Output (not committed): `backtesting/data/{SYM}_{15,60,240,1440}m_365d_bybit.csv` × 5 symbols
- Committed: `.planning/evidence/killtests/backfill-manifest-2026-08.md`

**Interfaces:**
- Consumes: Task 1 CLI.
- Produces: validated CSVs; `backfill_manifest.py` CLI writing a coverage manifest. Later tasks read these CSVs by the exact filenames above (interval `D` is requested as `D` but **filed as `1440m`** so filenames stay uniform).

- [ ] **Step 1: Preconditions**

Run: `docker ps --format '{{.Names}} {{.Status}}' | grep bybit-connector`
Expected: `crypto-bot-bybit-connector Up ...`. If down: `docker compose -f docker-compose.unified.yml up -d bybit-connector` and re-check.

- [ ] **Step 2: Probe 15m depth (spec §4 open probe — one request)**

Run:
```bash
python3 - <<'EOF'
import asyncio, sys, time
sys.path.insert(0, "backtesting")
from bybit_data_fetcher import BybitDataFetcher

async def main():
    f = BybitDataFetcher()
    year_ago = int(time.time() * 1000) - 365 * 24 * 3600 * 1000
    rows = await f.fetch_klines("BTCUSDT", "15", start_time=year_ago,
                                end_time=year_ago + 1000 * 15 * 60 * 1000, limit=1000)
    print("15m rows at t-365d:", len(rows))
asyncio.run(main())
EOF
```
Expected: `15m rows at t-365d: 1000` (Bybit serves it) — proceed with 365d for all intervals. If `0`: Bybit does not serve year-old 15m; use `--days 365` for 60/240/D and the maximum available for 15m (bisect with the same probe at t-270d/t-180d; record the chosen depth in the manifest). H3 only needs 15m around 2026-07-26..08-05, which is well inside any plausible depth.

- [ ] **Step 3: Run the backfill (4 intervals × 5 symbols)**

```bash
for iv in 15 60 240 D; do
  python3 backtesting/bybit_data_fetcher.py \
    --multiple BTCUSDT ETHUSDT SOLUSDT BNBUSDT ADAUSDT \
    --interval "$iv" --days 365 --schema klines --out-dir backtesting/data
done
```
Note: with `--interval D` the fetcher writes `{sym}_Dm_365d_bybit.csv`; rename to the uniform names:
```bash
cd backtesting/data && for s in BTCUSDT ETHUSDT SOLUSDT BNBUSDT ADAUSDT; do
  [ -f "${s}_Dm_365d_bybit.csv" ] && mv "${s}_Dm_365d_bybit.csv" "${s}_1440m_365d_bybit.csv"; done; cd ../..
```
Expected: 20 CSVs, no `stale` RuntimeError (liveness guard passed), each 15m file ≈ 35,000 rows, 60m ≈ 8,760, 240m ≈ 2,190, 1440m ≈ 365.

- [ ] **Step 4: Write the manifest generator**

`backtesting/killtests/backfill_manifest.py`:

```python
"""Emit a coverage manifest for backfilled kline CSVs.

Usage: python3 backtesting/killtests/backfill_manifest.py > .planning/evidence/killtests/backfill-manifest-2026-08.md
"""
import glob
import hashlib
import os

import pandas as pd

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
INTERVALS = {"15": 15, "60": 60, "240": 240, "1440": 1440}
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def main() -> None:
    print("# Backfill manifest\n")
    print("| file | rows | first | last | expected step (min) | gaps | sha256[:12] |")
    print("|---|---|---|---|---|---|---|")
    for sym in SYMBOLS:
        for iv, minutes in INTERVALS.items():
            path = os.path.abspath(os.path.join(DATA_DIR, f"{sym}_{iv}m_365d_bybit.csv"))
            if not os.path.exists(path):
                print(f"| {os.path.basename(path)} | MISSING | | | {minutes} | | |")
                continue
            df = pd.read_csv(path)
            ts = pd.to_datetime(df["timestamp"])
            steps = ts.diff().dropna().dt.total_seconds() / 60
            gaps = int((steps != minutes).sum())
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]
            print(
                f"| {os.path.basename(path)} | {len(df)} | {ts.iloc[0]} | {ts.iloc[-1]} "
                f"| {minutes} | {gaps} | {digest} |"
            )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Generate and inspect the manifest**

```bash
mkdir -p .planning/evidence/killtests
python3 backtesting/killtests/backfill_manifest.py > .planning/evidence/killtests/backfill-manifest-2026-08.md
cat .planning/evidence/killtests/backfill-manifest-2026-08.md
```
Expected: 20 rows, `gaps` = 0 or single-digit (Bybit occasionally skips a maintenance bar; any gaps count > 20 per file means the pagination is broken — stop and investigate before proceeding).

- [ ] **Step 6: Commit (manifest + generator only — CSVs stay untracked)**

```bash
git add backtesting/killtests/__init__.py backtesting/killtests/backfill_manifest.py .planning/evidence/killtests/backfill-manifest-2026-08.md
git commit -m "feat(killtests): 12-month mainnet backfill executed with coverage manifest"
```

---

### Task 3: `candles.py` — validated CSV store with as-of slicing

**Files:**
- Create: `backtesting/killtests/candles.py`
- Test: `tests/killtests/test_candles.py`

**Interfaces:**
- Consumes: Task 2 CSVs (11-col schema).
- Produces: `class CandleStore` used by every later task:
  - `CandleStore(data_dir: str, symbols: list[str], intervals: list[str])` — loads and validates on construction; raises `CandleValidationError` on any violation.
  - `.frame(symbol: str, interval: str) -> pd.DataFrame` — full validated frame, columns `timestamp` (pandas Timestamp, naive UTC), `ts_ms` (int), `open, high, low, close, volume` (float), sorted ascending.
  - `.as_of(symbol: str, interval: str, now_ms: int, limit: int) -> list[dict]` — last `limit` **closed** bars: rows where `ts_ms + interval_ms <= now_ms`, formatted as market-data API dicts `{"timestamp": int, "open": float, "high": float, "low": float, "close": float, "volume": float}` ascending.
  - `.daily_window_before(symbol: str, date_ms: int, n: int) -> pd.DataFrame` — last `n` 1440m bars strictly before `date_ms` (for point-in-time ATR).
  - `INTERVAL_MS = {"15": 900_000, "60": 3_600_000, "240": 14_400_000, "1440": 86_400_000}` module constant.
  - `class CandleValidationError(Exception)`.

- [ ] **Step 1: Write the failing tests**

`tests/killtests/test_candles.py`:

```python
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.candles import CandleStore, CandleValidationError, INTERVAL_MS  # noqa: E402

COLS = ["timestamp", "symbol", "interval", "open", "high", "low", "close",
        "volume", "turnover", "is_mainnet", "created_at"]


def _write_csv(path, n=50, start="2026-05-01 00:00:00", interval="60",
               symbol="BTCUSDT", mainnet=True, drop_row=None):
    ts = pd.date_range(start, periods=n, freq="60min")
    df = pd.DataFrame({
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "symbol": symbol,
        "interval": interval, "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.5, "volume": 10.0, "turnover": 1000.0,
        "is_mainnet": mainnet, "created_at": 1777161607163,
    })
    if drop_row is not None:
        df = df.drop(index=drop_row)
    df.to_csv(path, index=False)


@pytest.fixture
def store_dir(tmp_path):
    _write_csv(tmp_path / "BTCUSDT_60m_365d_bybit.csv")
    return tmp_path


def test_loads_and_frames(store_dir):
    s = CandleStore(str(store_dir), ["BTCUSDT"], ["60"])
    f = s.frame("BTCUSDT", "60")
    assert len(f) == 50
    assert list(f.columns) == ["timestamp", "ts_ms", "open", "high", "low", "close", "volume"]
    assert f["ts_ms"].is_monotonic_increasing


def test_rejects_non_mainnet(tmp_path):
    _write_csv(tmp_path / "BTCUSDT_60m_365d_bybit.csv", mainnet=False)
    with pytest.raises(CandleValidationError, match="is_mainnet"):
        CandleStore(str(tmp_path), ["BTCUSDT"], ["60"])


def test_rejects_gap(tmp_path):
    _write_csv(tmp_path / "BTCUSDT_60m_365d_bybit.csv", drop_row=10)
    with pytest.raises(CandleValidationError, match="gap"):
        CandleStore(str(tmp_path), ["BTCUSDT"], ["60"])


def test_rejects_missing_file(tmp_path):
    with pytest.raises(CandleValidationError, match="missing"):
        CandleStore(str(tmp_path), ["BTCUSDT"], ["60"])


def test_as_of_excludes_forming_and_future(store_dir):
    s = CandleStore(str(store_dir), ["BTCUSDT"], ["60"])
    f = s.frame("BTCUSDT", "60")
    # "now" = exactly the open of bar index 10 => bars 0..9 are closed
    now_ms = int(f["ts_ms"].iloc[10])
    rows = s.as_of("BTCUSDT", "60", now_ms, limit=200)
    assert len(rows) == 10
    assert rows[-1]["timestamp"] == int(f["ts_ms"].iloc[9])
    # one ms before bar 10 closes => bar 10 still forming, still 10 closed bars
    rows = s.as_of("BTCUSDT", "60", now_ms + INTERVAL_MS["60"] - 1, limit=200)
    assert rows[-1]["timestamp"] == int(f["ts_ms"].iloc[9])
    # exactly at close of bar 10 => it is included
    rows = s.as_of("BTCUSDT", "60", now_ms + INTERVAL_MS["60"], limit=200)
    assert rows[-1]["timestamp"] == int(f["ts_ms"].iloc[10])


def test_as_of_limit(store_dir):
    s = CandleStore(str(store_dir), ["BTCUSDT"], ["60"])
    f = s.frame("BTCUSDT", "60")
    end_ms = int(f["ts_ms"].iloc[-1]) + INTERVAL_MS["60"]
    rows = s.as_of("BTCUSDT", "60", end_ms, limit=7)
    assert len(rows) == 7


def test_daily_window_before(tmp_path):
    ts = pd.date_range("2026-05-01", periods=30, freq="D")
    df = pd.DataFrame({
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "symbol": "BTCUSDT",
        "interval": "1440", "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.5, "volume": 10.0, "turnover": 1000.0,
        "is_mainnet": True, "created_at": 1,
    })
    df.to_csv(tmp_path / "BTCUSDT_1440m_365d_bybit.csv", index=False)
    s = CandleStore(str(tmp_path), ["BTCUSDT"], ["1440"])
    cut = int(pd.Timestamp("2026-05-20 13:00:00").timestamp() * 1000)
    win = s.daily_window_before("BTCUSDT", cut, n=15)
    assert len(win) == 15
    # strictly before the cut DATE's bar: last bar must be 2026-05-19 (its close 05-20 00:00 <= cut)
    assert str(win["timestamp"].iloc[-1].date()) == "2026-05-19"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/killtests/test_candles.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: killtests.candles`.

- [ ] **Step 3: Implement `candles.py`**

`backtesting/killtests/candles.py`:

```python
"""Validated candle store over backfilled 11-col kline CSVs.

Hard-fail on any data-quality violation (spec §8): missing file, non-mainnet
rows, spacing gaps. As-of slicing serves only CLOSED bars (close <= now),
mirroring the live forming-candle drop in technical-analysis fetcher.py.
"""
import os

import pandas as pd

INTERVAL_MS = {"15": 900_000, "60": 3_600_000, "240": 14_400_000, "1440": 86_400_000}

_REQUIRED_COLS = {"timestamp", "symbol", "interval", "open", "high", "low",
                  "close", "volume", "turnover", "is_mainnet", "created_at"}


class CandleValidationError(Exception):
    pass


class CandleStore:
    def __init__(self, data_dir: str, symbols: list, intervals: list):
        self._frames = {}
        for sym in symbols:
            for iv in intervals:
                path = os.path.join(data_dir, f"{sym}_{iv}m_365d_bybit.csv")
                if not os.path.exists(path):
                    raise CandleValidationError(f"missing candle file: {path}")
                self._frames[(sym, iv)] = self._load(path, sym, iv)

    @staticmethod
    def _load(path: str, sym: str, iv: str) -> pd.DataFrame:
        raw = pd.read_csv(path)
        missing = _REQUIRED_COLS - set(raw.columns)
        if missing:
            raise CandleValidationError(f"{path}: missing columns {sorted(missing)}")
        if not raw["is_mainnet"].astype(bool).all():
            raise CandleValidationError(f"{path}: contains is_mainnet=False rows")
        ts = pd.to_datetime(raw["timestamp"])
        if not ts.is_monotonic_increasing:
            raise CandleValidationError(f"{path}: timestamps not ascending")
        step_ms = INTERVAL_MS[iv]
        diffs = ts.diff().dropna().dt.total_seconds() * 1000
        bad = diffs[diffs != step_ms]
        if len(bad):
            first_bad = ts.iloc[bad.index[0]]
            raise CandleValidationError(
                f"{path}: {len(bad)} spacing gap(s)/duplicate(s); first at {first_bad}"
            )
        out = pd.DataFrame({
            "timestamp": ts,
            "ts_ms": (ts.astype("int64") // 1_000_000).astype("int64"),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["volume"].astype(float),
        })
        return out.reset_index(drop=True)

    def frame(self, symbol: str, interval: str) -> pd.DataFrame:
        return self._frames[(symbol, interval)]

    def as_of(self, symbol: str, interval: str, now_ms: int, limit: int) -> list:
        f = self._frames[(symbol, interval)]
        step = INTERVAL_MS[interval]
        closed = f[f["ts_ms"] + step <= now_ms].tail(limit)
        return [
            {"timestamp": int(r.ts_ms), "open": r.open, "high": r.high,
             "low": r.low, "close": r.close, "volume": r.volume}
            for r in closed.itertuples()
        ]

    def daily_window_before(self, symbol: str, date_ms: int, n: int) -> pd.DataFrame:
        f = self._frames[(symbol, "1440")]
        step = INTERVAL_MS["1440"]
        closed = f[f["ts_ms"] + step <= date_ms]
        if len(closed) < n:
            raise CandleValidationError(
                f"{symbol}: only {len(closed)} daily bars before "
                f"{pd.Timestamp(date_ms, unit='ms')}, need {n}"
            )
        return closed.tail(n).reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/killtests/test_candles.py -v --no-cov`
Expected: 8 PASS.

- [ ] **Step 5: Validate against the real backfill**

Run:
```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "backtesting")
from killtests.candles import CandleStore
s = CandleStore("backtesting/data",
                ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"],
                ["15", "60", "240", "1440"])
print("all 20 frames validated")
EOF
```
Expected: `all 20 frames validated`. If a real file has a legitimate Bybit maintenance gap, this raises — in that case relax is NOT the answer; add an explicit `KNOWN_GAPS` allowlist constant in `candles.py` listing each `(symbol, interval, timestamp)` triple, validated to match exactly, and note them in the manifest.

- [ ] **Step 6: Commit**

```bash
git add backtesting/killtests/candles.py tests/killtests/test_candles.py
git commit -m "feat(killtests): validated candle store with as-of slicing"
```

---

### Task 4: `entries.py` — extract the 13 closed entries into a committed fixture

**Files:**
- Create: `backtesting/killtests/entries.py`, `backtesting/killtests/fixtures/closed_entries_2026-08.json`
- Test: `tests/killtests/test_entries.py`

**Interfaces:**
- Consumes: Postgres (one-time extraction); afterwards nothing needs the DB.
- Produces: `load_entries(path=DEFAULT_FIXTURE) -> list[Entry]` where `Entry` is a dataclass: `position_id: str, symbol: str, side: str ("LONG"|"SHORT"), quantity: float, entry_price: float, entry_ts_ms: int, exit_ts_ms: int, actual_exit_price: float, actual_realized_pnl: float, signal_confidence: float | None`. `DEFAULT_FIXTURE` = the JSON above.

- [ ] **Step 1: Verify DB timezone (fixture provenance requires it)**

Run: `docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SHOW timezone;" && docker exec crypto-bot-postgres date -u`
Expected: `Etc/UTC` (or `UTC`) — then `opened_at`/`closed_at` naive timestamps are UTC and convert to epoch-ms directly. If NOT UTC, record the actual zone and convert accordingly in Step 3's SQL (`AT TIME ZONE`). Paste the output into the fixture's `provenance.timezone_check` field.

- [ ] **Step 2: Write the failing test**

`tests/killtests/test_entries.py`:

```python
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.entries import DEFAULT_FIXTURE, load_entries  # noqa: E402


def test_fixture_loads_13_entries():
    entries = load_entries(DEFAULT_FIXTURE)
    assert len(entries) == 13
    ids = sorted(e.position_id for e in entries)
    assert len(set(ids)) == 13


def test_entry_fields_sane():
    for e in load_entries(DEFAULT_FIXTURE):
        assert e.side in ("LONG", "SHORT")
        assert e.symbol in {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"}
        assert e.entry_price > 0 and e.quantity > 0
        assert e.exit_ts_ms > e.entry_ts_ms
        # audit window: opened 2026-07-29 .. 2026-08-04; 1785974400000 = 2026-08-06 00:00 UTC (generous upper bound)
        assert 1785283200000 <= e.entry_ts_ms <= 1785974400000


def test_known_row_values():
    """Spot-check against the verified DB dump (position id 59)."""
    by_symbol_ts = {(e.symbol, e.side, round(e.entry_price, 2)) for e in load_entries(DEFAULT_FIXTURE)}
    assert ("SOLUSDT", "LONG", 71.04) in by_symbol_ts
    assert ("BTCUSDT", "SHORT", 63556.10) in by_symbol_ts
```

- [ ] **Step 3: Run test to verify it fails, then implement**

Run: `python3 -m pytest tests/killtests/test_entries.py -v --no-cov` → FAIL (module missing).

`backtesting/killtests/entries.py`:

```python
"""Closed-entry fixture: the 13 CLOSED paper positions, extracted once from Postgres.

Regenerate with:  python3 backtesting/killtests/entries.py --extract
(requires crypto-bot-postgres up; read-only). The committed fixture is the
source of record for H3 — replays never touch the DB.
"""
import argparse
import json
import os
import subprocess
from dataclasses import dataclass

DEFAULT_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "closed_entries_2026-08.json")

_SQL = """
COPY (
  SELECT json_agg(row_to_json(t)) FROM (
    SELECT p.id, p.position_id::text, p.symbol, p.side, p.quantity::float8,
           p.entry_price::float8, p.exit_price::float8 AS actual_exit_price,
           p.realized_pnl::float8 AS actual_realized_pnl,
           (EXTRACT(EPOCH FROM p.opened_at) * 1000)::bigint AS entry_ts_ms,
           (EXTRACT(EPOCH FROM p.closed_at) * 1000)::bigint AS exit_ts_ms,
           tr.signal_confidence::float8
    FROM positions p
    LEFT JOIN trades tr
      ON tr.metadata->>'position_id' = p.position_id::text
     AND tr.side = CASE WHEN p.side = 'LONG' THEN 'BUY' ELSE 'SELL' END
     AND tr.strategy = 'ensemble'
    WHERE p.status = 'CLOSED'
    ORDER BY p.closed_at
  ) t
) TO STDOUT;
"""


@dataclass(frozen=True)
class Entry:
    position_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_ts_ms: int
    exit_ts_ms: int
    actual_exit_price: float
    actual_realized_pnl: float
    signal_confidence: float | None


def load_entries(path: str = DEFAULT_FIXTURE) -> list:
    with open(path) as f:
        doc = json.load(f)
    return [
        Entry(
            position_id=str(r["position_id"]), symbol=r["symbol"], side=r["side"],
            quantity=r["quantity"], entry_price=r["entry_price"],
            entry_ts_ms=r["entry_ts_ms"], exit_ts_ms=r["exit_ts_ms"],
            actual_exit_price=r["actual_exit_price"],
            actual_realized_pnl=r["actual_realized_pnl"],
            signal_confidence=r.get("signal_confidence"),
        )
        for r in doc["entries"]
    ]


def extract() -> None:
    out = subprocess.run(
        ["docker", "exec", "crypto-bot-postgres", "psql", "-U", "cryptobot",
         "-d", "cryptobot", "-At", "-c", _SQL],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(out.stdout.strip())
    assert len(rows) == 13, f"expected 13 closed positions, got {len(rows)} (join multiplicity broke?)"
    shorts = [r for r in rows if r["side"] == "SHORT"]
    assert shorts, "no SHORT rows — side-matched join is wrong"
    tz = subprocess.run(
        ["docker", "exec", "crypto-bot-postgres", "psql", "-U", "cryptobot",
         "-d", "cryptobot", "-At", "-c", "SHOW timezone;"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    doc = {
        "provenance": {
            "extracted_from": "crypto-bot-postgres db=cryptobot",
            "sql": _SQL.strip(),
            "timezone_check": tz,
            "note": "naive timestamps interpreted as UTC; epoch conversion done in SQL",
            "row_count": len(rows),
        },
        "entries": rows,
    }
    os.makedirs(os.path.dirname(DEFAULT_FIXTURE), exist_ok=True)
    with open(DEFAULT_FIXTURE, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    print(f"wrote {len(rows)} entries to {DEFAULT_FIXTURE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    args = ap.parse_args()
    if args.extract:
        extract()
```

Note: `EXTRACT(EPOCH FROM ...)` on a `timestamp without time zone` uses the value as-is; with the server in UTC (Step 1) that IS epoch-UTC. If Step 1 showed a non-UTC zone, change to `EXTRACT(EPOCH FROM p.opened_at AT TIME ZONE '<zone>')`.

- [ ] **Step 4: Run the extraction and the tests**

```bash
python3 backtesting/killtests/entries.py --extract
python3 -m pytest tests/killtests/test_entries.py -v --no-cov
```
Expected: `wrote 13 entries ...`; 3 PASS. Eyeball the fixture: 13 rows, sides/symbols match the verified dump (ids 46–56, 59–60; e.g. id 47 BTCUSDT SHORT entry 63556.10, realized +0.39211922).

- [ ] **Step 5: Commit**

```bash
git add backtesting/killtests/entries.py backtesting/killtests/fixtures/closed_entries_2026-08.json tests/killtests/test_entries.py
git commit -m "feat(killtests): closed-entry fixture extracted from Postgres with provenance"
```

---

### Task 5: `report.py` — verdict file emitter

**Files:**
- Create: `backtesting/killtests/report.py`
- Test: `tests/killtests/test_report.py`

**Interfaces:**
- Consumes: nothing internal.
- Produces:
  - `write_verdict(test_id: str, verdict: str, criterion: str, metrics: dict, caveats: list[str], config: dict, input_hashes: dict, out_dir: str = EVIDENCE_DIR) -> str` — writes `{out_dir}/{test_id}-verdict-{YYYYMMDD}.md` + sibling `.json`, returns the md path. `verdict` must be `"ACCEPT"` or `"REJECT"`.
  - `latest_verdict(test_id: str, out_dir: str = EVIDENCE_DIR) -> dict | None` — parses the newest `{test_id}-verdict-*.json`, returns its dict (used by the H4 order gate).
  - `EVIDENCE_DIR = ".planning/evidence/killtests"` (repo-relative).

- [ ] **Step 1: Write the failing tests**

`tests/killtests/test_report.py`:

```python
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.report import latest_verdict, write_verdict  # noqa: E402


def test_write_and_read_roundtrip(tmp_path):
    p = write_verdict(
        "H3", "REJECT", "stop-out < 40% AND gross expectancy > 0",
        metrics={"stop_out_rate": 0.62, "gross_expectancy": -0.31},
        caveats=["n=13"], config={"stop_mult": 1.5},
        input_hashes={"entries": "abc123"}, out_dir=str(tmp_path),
    )
    assert Path(p).exists() and p.endswith(".md")
    v = latest_verdict("H3", out_dir=str(tmp_path))
    assert v["verdict"] == "REJECT"
    assert v["metrics"]["stop_out_rate"] == 0.62
    assert "n=13" in v["caveats"]


def test_invalid_verdict_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_verdict("H3", "MAYBE", "c", {}, [], {}, {}, out_dir=str(tmp_path))


def test_latest_verdict_none_when_absent(tmp_path):
    assert latest_verdict("H4", out_dir=str(tmp_path)) is None
```

- [ ] **Step 2: Run to verify FAIL, implement, run to verify PASS**

`backtesting/killtests/report.py`:

```python
"""Dated verdict files for kill-test runs (spec §9).

Verdict language is the audit criterion verbatim — never an edge claim.
"""
import glob
import json
import os
from datetime import date

EVIDENCE_DIR = ".planning/evidence/killtests"


def write_verdict(test_id, verdict, criterion, metrics, caveats, config,
                  input_hashes, out_dir=EVIDENCE_DIR, tables=None):
    """tables: optional {name: list-of-row-dicts} — written to the .json only
    (per-trade / per-symbol detail per spec §5/§9)."""
    if verdict not in ("ACCEPT", "REJECT"):
        raise ValueError(f"verdict must be ACCEPT or REJECT, got {verdict!r}")
    os.makedirs(out_dir, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    base = os.path.join(out_dir, f"{test_id}-verdict-{stamp}")
    doc = {
        "test_id": test_id, "verdict": verdict, "criterion": criterion,
        "metrics": metrics, "caveats": caveats, "config": config,
        "input_hashes": input_hashes, "date": stamp, "tables": tables or {},
    }
    with open(base + ".json", "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    lines = [
        f"# {test_id} verdict: {verdict}", "",
        f"**Criterion (AUDIT.md §7, verbatim):** {criterion}", "",
        "## Metrics", "",
    ]
    lines += [f"- {k}: {v}" for k, v in sorted(metrics.items())]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in caveats]
    lines += ["", "## Config", "", "```json", json.dumps(config, indent=2, sort_keys=True), "```"]
    lines += ["", "## Input hashes", ""] + [f"- {k}: {v}" for k, v in sorted(input_hashes.items())]
    with open(base + ".md", "w") as f:
        f.write("\n".join(lines) + "\n")
    return base + ".md"


def latest_verdict(test_id, out_dir=EVIDENCE_DIR):
    paths = sorted(glob.glob(os.path.join(out_dir, f"{test_id}-verdict-*.json")))
    if not paths:
        return None
    with open(paths[-1]) as f:
        return json.load(f)
```

Run: `python3 -m pytest tests/killtests/test_report.py -v --no-cov` → 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add backtesting/killtests/report.py tests/killtests/test_report.py
git commit -m "feat(killtests): verdict report emitter with order-gate reader"
```

---

### Task 6: `h3_atr_replay.py` — ATR bracket walker + verdict

**Files:**
- Create: `backtesting/killtests/h3_atr_replay.py`
- Test: `tests/killtests/test_h3_atr_replay.py`

**Interfaces:**
- Consumes: `CandleStore` (Task 3), `load_entries` (Task 4), `write_verdict` (Task 5), `ATRStopCalculator` (trading-engine, loaded via `importlib` spec-load — NOT `sys.path` `app` insertion), `shared.account.PAPER_INITIAL_BALANCE / TAKER_FEE_PER_SIDE`.
- Produces:
  - `daily_atr(store: CandleStore, symbol: str, entry_ts_ms: int, period: int = 14) -> float` — point-in-time ATR over the `period+1` daily bars strictly before the entry's date.
  - `replay_entry(entry: Entry, bars: pd.DataFrame, stop: float, tp: float, max_hold_bars: int) -> TradeOutcome` — dataclass `TradeOutcome(exit_price, exit_reason ("stop_loss"|"take_profit"|"max_hold"|"end_of_data"), bars_held, gross_pnl, ambiguous_bars)`.
  - `run_h3(data_dir: str, stop_mult: float, resolution: str = "15") -> dict` — full run for one variant; CLI `python3 backtesting/killtests/h3_atr_replay.py --data-dir backtesting/data` runs both variants (1.5, 2.5) and writes the verdict.
- Semantics (locked by spec §5): stop = entry ∓ `stop_mult × ATR_daily`; TP = 2R (entry ± `2 × stop_mult × ATR_daily`); walk starts at the **first bar whose open time ≥ entry_ts_ms** (entries land mid-bar; the partial entry bar is unknowable — starting next bar is the conservative choice and is reported); per bar **stop before TP** (both touched → stop, `ambiguous_bars += 1`); max-hold 48h = 192 15m bars; max-hold/end exits fill at that bar's close. Gross P&L on actual DB quantity: LONG `(exit-entry)*qty`, SHORT `(entry-exit)*qty`.

- [ ] **Step 1: Write the failing tests**

`tests/killtests/test_h3_atr_replay.py`:

```python
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.entries import Entry  # noqa: E402
from killtests.h3_atr_replay import TradeOutcome, replay_entry  # noqa: E402


def _bars(prices, start_ms=1_700_000_000_000, step_ms=900_000, spread=0.5):
    """Bars where high=price+spread, low=price-spread, close=price."""
    return pd.DataFrame({
        "ts_ms": [start_ms + i * step_ms for i in range(len(prices))],
        "open": prices, "high": [p + spread for p in prices],
        "low": [p - spread for p in prices], "close": prices,
    })


def _entry(side="LONG", price=100.0, qty=1.0, ts=1_700_000_000_000):
    return Entry(position_id="t", symbol="TESTUSDT", side=side, quantity=qty,
                 entry_price=price, entry_ts_ms=ts, exit_ts_ms=ts + 1,
                 actual_exit_price=0.0, actual_realized_pnl=0.0,
                 signal_confidence=None)


def test_long_stop_hit():
    bars = _bars([100, 100, 97, 100])
    out = replay_entry(_entry(), bars, stop=98.0, tp=104.0, max_hold_bars=192)
    assert out.exit_reason == "stop_loss"
    assert out.exit_price == 98.0
    assert out.gross_pnl == pytest.approx(-2.0)


def test_long_tp_hit():
    bars = _bars([100, 100, 105, 100])
    out = replay_entry(_entry(), bars, stop=98.0, tp=104.0, max_hold_bars=192)
    assert out.exit_reason == "take_profit"
    assert out.gross_pnl == pytest.approx(4.0)


def test_ambiguous_bar_stop_wins():
    # bar 2 spans both stop (98) and tp (104): low=95.5, high=104.5
    bars = _bars([100, 100, 100, 100])
    bars.loc[2, "low"], bars.loc[2, "high"] = 95.5, 104.5
    out = replay_entry(_entry(), bars, stop=98.0, tp=104.0, max_hold_bars=192)
    assert out.exit_reason == "stop_loss"
    assert out.ambiguous_bars == 1


def test_short_stop_hit():
    bars = _bars([100, 100, 103, 100])
    out = replay_entry(_entry(side="SHORT"), bars, stop=102.0, tp=96.0, max_hold_bars=192)
    assert out.exit_reason == "stop_loss"
    assert out.gross_pnl == pytest.approx(-2.0)


def test_max_hold_exit_at_close():
    bars = _bars([100.0] * 10)
    out = replay_entry(_entry(), bars, stop=90.0, tp=110.0, max_hold_bars=4)
    assert out.exit_reason == "max_hold"
    assert out.bars_held == 4
    assert out.exit_price == 100.0


def test_walk_starts_after_entry_ts():
    # entry mid-bar-0: bar 0's crash to 90 must NOT trigger the stop
    bars = _bars([100, 100, 100, 100])
    bars.loc[0, "low"] = 90.0
    e = _entry(ts=bars["ts_ms"][0] + 1)  # 1ms after bar 0 opens
    out = replay_entry(e, bars, stop=95.0, tp=110.0, max_hold_bars=192)
    assert out.exit_reason == "max_hold"  # never stopped


def test_end_of_data():
    bars = _bars([100.0] * 3)
    out = replay_entry(_entry(), bars, stop=90.0, tp=110.0, max_hold_bars=192)
    assert out.exit_reason == "end_of_data"


def test_daily_atr_known_values(tmp_path):
    """ATR = SMA of last 14 true ranges; constant bars => TR = high-low = 2."""
    from killtests.candles import CandleStore
    ts = pd.date_range("2026-05-01", periods=20, freq="D")
    df = pd.DataFrame({
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "symbol": "TESTUSDT",
        "interval": "1440", "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.0, "volume": 1.0, "turnover": 1.0,
        "is_mainnet": True, "created_at": 1,
    })
    df.to_csv(tmp_path / "TESTUSDT_1440m_365d_bybit.csv", index=False)
    from killtests.h3_atr_replay import daily_atr
    store = CandleStore(str(tmp_path), ["TESTUSDT"], ["1440"])
    cut = int(pd.Timestamp("2026-05-19 12:00:00").timestamp() * 1000)
    assert daily_atr(store, "TESTUSDT", cut) == pytest.approx(2.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/killtests/test_h3_atr_replay.py -v --no-cov`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`backtesting/killtests/h3_atr_replay.py`:

```python
"""H3 kill test: replay the recorded entries with ATR-derived brackets.

AUDIT.md:261 — stops at 1.5x/2.5x ATR-derived daily vol, TP 2R, all else
identical. Accept: stop-out rate < 40% AND gross expectancy > 0 pre-fee.

Intrabar rule copied from BacktestEngine._check_exit_conditions: stop is
checked BEFORE take-profit on every bar, for both sides (pessimistic).
Entries start at the first bar opening at/after the recorded entry time.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "backtesting"))

from shared.account import PAPER_INITIAL_BALANCE, TAKER_FEE_PER_SIDE  # noqa: E402

from killtests.candles import INTERVAL_MS, CandleStore  # noqa: E402
from killtests.entries import DEFAULT_FIXTURE, Entry, load_entries  # noqa: E402
from killtests.report import write_verdict  # noqa: E402

MODELLED_FEE_PER_SIDE = 0.001  # engine convention ("modelled"), AUDIT.md header
MAX_HOLD_HOURS = 48


def _load_atr_calculator():
    """Spec-load trading-engine atr_stops.py under a unique name (no `app` collision)."""
    path = os.path.join(_REPO, "services", "trading-engine", "app", "atr_stops.py")
    spec = importlib.util.spec_from_file_location("_killtests_atr_stops", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_killtests_atr_stops"] = mod
    spec.loader.exec_module(mod)
    return mod.ATRStopCalculator


def daily_atr(store: CandleStore, symbol: str, entry_ts_ms: int, period: int = 14) -> float:
    win = store.daily_window_before(symbol, entry_ts_ms, n=period + 1)
    calc = _load_atr_calculator()(atr_period=period)
    atr = calc.calculate_atr(win["high"].tolist(), win["low"].tolist(), win["close"].tolist())
    if atr <= 0:
        raise ValueError(f"non-positive ATR for {symbol} at {entry_ts_ms}")
    return atr


@dataclass
class TradeOutcome:
    exit_price: float
    exit_reason: str
    bars_held: int
    gross_pnl: float
    ambiguous_bars: int


def replay_entry(entry: Entry, bars: pd.DataFrame, stop: float, tp: float,
                 max_hold_bars: int) -> TradeOutcome:
    walk = bars[bars["ts_ms"] >= entry.entry_ts_ms].reset_index(drop=True)
    if walk.empty:
        raise ValueError(f"{entry.position_id}: no bars at/after entry ts {entry.entry_ts_ms}")
    long = entry.side == "LONG"
    ambiguous = 0
    exit_price, reason, held = None, None, 0
    for i, row in enumerate(walk.itertuples(), start=1):
        if i > max_hold_bars:
            exit_price, reason, held = walk.iloc[i - 2]["close"], "max_hold", i - 1
            break
        stop_hit = row.low <= stop if long else row.high >= stop
        tp_hit = row.high >= tp if long else row.low <= tp
        if stop_hit and tp_hit:
            ambiguous += 1
        if stop_hit:  # stop checked first — pessimistic, mirrors BacktestEngine
            exit_price, reason, held = stop, "stop_loss", i
            break
        if tp_hit:
            exit_price, reason, held = tp, "take_profit", i
            break
    if exit_price is None:
        last = walk.iloc[min(len(walk), max_hold_bars) - 1]
        held = min(len(walk), max_hold_bars)
        reason = "max_hold" if len(walk) >= max_hold_bars else "end_of_data"
        exit_price = float(last["close"])
    direction = 1.0 if long else -1.0
    gross = (exit_price - entry.entry_price) * direction * entry.quantity
    return TradeOutcome(float(exit_price), reason, held, float(gross), ambiguous)


def _pick_resolution(store: CandleStore, entry, preferred: str) -> str:
    """Per-entry resolution: preferred (15m) if its frame covers the entry start,
    else fall back to 60m (spec §5: 'fallback noted per-entry')."""
    for res in (preferred, "60"):
        f = store.frame(entry.symbol, res)
        if int(f["ts_ms"].iloc[0]) <= entry.entry_ts_ms <= int(f["ts_ms"].iloc[-1]):
            return res
    raise ValueError(
        f"{entry.position_id} ({entry.symbol}): no frame ({preferred}m or 60m) "
        f"covers entry ts {entry.entry_ts_ms} — genuine backfill hole, refresh it"
    )


def run_h3(data_dir: str, stop_mult: float, resolution: str = "15",
           fixture: str = DEFAULT_FIXTURE) -> dict:
    entries = load_entries(fixture)
    symbols = sorted({e.symbol for e in entries})
    store = CandleStore(data_dir, symbols, [resolution, "60", "1440"])
    rows = []
    truncated = 0
    fallbacks = 0
    for e in entries:
        res = _pick_resolution(store, e, resolution)
        fallbacks += res != resolution
        bar_hours = INTERVAL_MS[res] / 3_600_000
        max_hold_bars = int(MAX_HOLD_HOURS * 3_600_000 / INTERVAL_MS[res])
        # Truncation at the DATA END is allowed (exits via end_of_data, counted
        # as a caveat). A frame that starts AFTER the entry is a hard abort
        # (interior hole — spec §8), handled inside _pick_resolution.
        atr = daily_atr(store, e.symbol, e.entry_ts_ms)
        risk = stop_mult * atr
        if e.side == "LONG":
            stop, tp = e.entry_price - risk, e.entry_price + 2 * risk
        else:
            stop, tp = e.entry_price + risk, e.entry_price - 2 * risk
        out = replay_entry(e, store.frame(e.symbol, res), stop, tp, max_hold_bars)
        truncated += out.exit_reason == "end_of_data"
        notional_in = e.entry_price * e.quantity
        notional_out = out.exit_price * e.quantity
        # funding overlay (spec §5): ~0.01% of notional per 8h held (not modelled live)
        funding_est = notional_in * 0.0001 * (out.bars_held * bar_hours / 8.0)
        rows.append({
            "position_id": e.position_id, "symbol": e.symbol, "side": e.side,
            "resolution": res, "atr_daily": atr, "stop": stop, "tp": tp,
            **asdict(out),
            "fees_modelled": (notional_in + notional_out) * MODELLED_FEE_PER_SIDE,
            "fees_bybit_est": (notional_in + notional_out) * TAKER_FEE_PER_SIDE,
            "funding_est": funding_est,
        })
    df = pd.DataFrame(rows)
    n = len(df)
    stop_out_rate = float((df["exit_reason"] == "stop_loss").mean())
    gross_expectancy = float(df["gross_pnl"].mean())
    return {
        "stop_mult": stop_mult, "resolution": resolution, "n": n,
        "stop_out_rate": stop_out_rate,
        "gross_expectancy_per_trade": gross_expectancy,
        "gross_total": float(df["gross_pnl"].sum()),
        "net_total_modelled": float((df["gross_pnl"] - df["fees_modelled"]).sum()),
        "net_total_bybit_est": float((df["gross_pnl"] - df["fees_bybit_est"]).sum()),
        "funding_est_total": float(df["funding_est"].sum()),
        "ambiguous_bars_total": int(df["ambiguous_bars"].sum()),
        "truncated_windows": int(truncated),
        "resolution_fallbacks": int(fallbacks),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
        "per_trade": rows,
        "accept": stop_out_rate < 0.40 and gross_expectancy > 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="backtesting/data")
    ap.add_argument("--resolution", default="15")
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE)
    args = ap.parse_args()
    results = {m: run_h3(args.data_dir, m, args.resolution, args.fixture) for m in (1.5, 2.5)}
    accept = any(r["accept"] for r in results.values())
    metrics = {}
    for m, r in results.items():
        metrics[f"stop_out_rate_{m}x"] = r["stop_out_rate"]
        metrics[f"gross_expectancy_{m}x"] = r["gross_expectancy_per_trade"]
        metrics[f"net_total_modelled_{m}x"] = r["net_total_modelled"]
        metrics[f"net_total_bybit_est_{m}x"] = r["net_total_bybit_est"]
        metrics[f"funding_est_total_{m}x"] = r["funding_est_total"]
        metrics[f"ambiguous_bars_{m}x"] = r["ambiguous_bars_total"]
        metrics[f"exit_reasons_{m}x"] = json.dumps(r["exit_reasons"], sort_keys=True)
    def _sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
    input_hashes = {"entries_fixture": _sha(args.fixture)}
    manifest = ".planning/evidence/killtests/backfill-manifest-2026-08.md"
    if os.path.exists(manifest):  # carries per-CSV digests (spec §9 input-data hash)
        input_hashes["backfill_manifest"] = _sha(manifest)
    path = write_verdict(
        "H3", "ACCEPT" if accept else "REJECT",
        "stop-out rate < 40% AND gross expectancy > 0 pre-fee (either ATR variant)",
        metrics=metrics,
        caveats=[
            f"n={results[1.5]['n']} — percentages describe these trades, not true rates",
            "gross P&L is pre-fee (the criterion); net shown under both fee conventions",
            "funding not modelled live; overlay estimate reported (0.01%/8h of entry notional)",
            "walk starts at first full bar after entry; partial entry bar excluded (conservative)",
            f"resolution {args.resolution}m with per-entry 60m fallback; stop-before-TP on ambiguous bars (pessimistic)",
            f"truncated windows (exit=end_of_data at data end): "
            f"{ {m: r['truncated_windows'] for m, r in results.items()} }",
            f"resolution fallbacks to 60m: { {m: r['resolution_fallbacks'] for m, r in results.items()} }",
        ],
        config={"stop_mults": [1.5, 2.5], "tp_r_multiple": 2.0,
                "max_hold_hours": MAX_HOLD_HOURS, "atr_period": 14,
                "initial_capital_source": f"shared.account ({PAPER_INITIAL_BALANCE})"},
        input_hashes=input_hashes,
        tables={f"per_trade_{m}x": r["per_trade"] for m, r in results.items()},
    )
    print(f"H3 verdict written: {path}")
    for m, r in results.items():
        print(f"  {m}x: stop-out {r['stop_out_rate']:.1%}, "
              f"gross expectancy {r['gross_expectancy_per_trade']:+.4f}, accept={r['accept']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/killtests/test_h3_atr_replay.py -v --no-cov`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add backtesting/killtests/h3_atr_replay.py tests/killtests/test_h3_atr_replay.py
git commit -m "feat(killtests): H3 ATR bracket walker with pessimistic intrabar rule"
```

---

### Task 7: Run H3 → primary verdict

**Files:**
- Output: `.planning/evidence/killtests/H3-verdict-<date>.md` + `.json` (committed)
- Modify: `AUDIT.md` (H3 row in §7 table gets a status pointer)

- [ ] **Step 1: Run the replay**

Run: `python3 backtesting/killtests/h3_atr_replay.py --data-dir backtesting/data`
Expected: verdict path printed plus per-variant lines. Sanity-check against the audit's forensics: 5 of the original exits were stops with the 0.5% penalty; the replay's exit distribution should differ (ATR stops are wider than 2% for most of these symbols).

- [ ] **Step 2: Update AUDIT.md H3 row**

In `AUDIT.md` §7, the H3 row's status cell currently reads `**CONFIRMED for the geometry** (0.37–0.97 daily ATR); causal claim needs the test`. Append to that cell: `— tested <date>: see .planning/evidence/killtests/H3-verdict-<date>.md (<ACCEPT|REJECT>)`. Do not alter the criterion text.

- [ ] **Step 3: Commit**

```bash
git add .planning/evidence/killtests/H3-verdict-* AUDIT.md
git commit -m "docs(killtests): H3 verdict recorded, AUDIT.md H3 row updated"
```

---

### Task 8: `offline_ensemble.py` part 1 — namespace loader + transports

**Files:**
- Create: `backtesting/killtests/offline_ensemble.py`
- Test: `tests/killtests/test_offline_ensemble_seam.py`

**Interfaces:**
- Consumes: `CandleStore` (Task 3); TA app; TE modules; shim pattern from `run_walk_forward_ensemble.py:58-191`.
- Produces (all in `offline_ensemble.py`):
  - `class ReplayClock: now_ms: int` — mutable holder the driver advances.
  - `load_stack(store: CandleStore, clock: ReplayClock) -> Stack` — one-per-process loader returning `Stack` (dataclass) with fields: `aggregator` (real `SignalAggregator`, transports swapped), `ensemble` (real `MultiStrategyEnsemble`), `signal_aggregator_mod`, `SignalAction`. Import order inside: (1) stats kernels first (hold refs), (2) TA `app.main` fully (hold `ta_app`, `ta_fetcher_mod` refs), (3) purge `app*`, (4) TE namespace via `_load_te_module` shims, (5) construct + wire transports.
  - Market-data mock: `httpx.MockTransport` handler answering `GET /api/v1/klines/{symbol}` with `{"success": True, "data": store.as_of(symbol, interval, clock.now_ms, limit)}` (interval/limit from query params; interval aliases `D`→`1440`).
  - The TA fetcher singleton stays REAL (its validation pipeline runs); only its `client` is replaced with `httpx.AsyncClient(transport=<MockTransport>)`.
  - `aggregator.client` and every other `httpx.AsyncClient` inside loaded TE modules (regime detector) replaced with `httpx.AsyncClient(transport=httpx.ASGITransport(app=ta_app), base_url="http://ta.offline")`.
  - Time pin: the loaded TE `signal_aggregator` module's `time` attribute replaced with a shim whose `time()` returns `clock.now_ms / 1000`.

- [ ] **Step 1: Write the shared candle-writer conftest + the failing seam test**

`tests/killtests/conftest.py` (shared synthetic-candle writer — fixtures avoid cross-test-module imports, which break depending on whether `tests/` is a package):

```python
import numpy as np
import pandas as pd
import pytest


def _write_candles(tmp_path, symbol, interval, n, start):
    freq = {"15": "15min", "60": "60min", "240": "240min", "1440": "D"}[interval]
    ts = pd.date_range(start, periods=n, freq=freq)
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    df = pd.DataFrame({
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "symbol": symbol,
        "interval": interval, "open": closes, "high": closes + 0.6,
        "low": closes - 0.6, "close": closes, "volume": 10.0,
        "turnover": 1000.0, "is_mainnet": True, "created_at": 1,
    })
    df.to_csv(tmp_path / f"{symbol}_{interval}m_365d_bybit.csv", index=False)


@pytest.fixture
def write_candles():
    return _write_candles
```

`tests/killtests/test_offline_ensemble_seam.py`:

```python
"""Smoke: the deployed chain runs offline end-to-end on synthetic candles."""
import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.candles import INTERVAL_MS, CandleStore  # noqa: E402

from conftest import _write_candles  # same-dir conftest; pytest puts it on the path


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("candles")
    for iv, n in [("15", 2000), ("60", 600), ("240", 400), ("1440", 60)]:
        _write_candles(tmp, "BTCUSDT", iv, n, "2026-04-01 00:00:00")
    store = CandleStore(str(tmp), ["BTCUSDT"], ["15", "60", "240", "1440"])
    from killtests.offline_ensemble import ReplayClock, frozen_time, load_stack
    clock = ReplayClock(now_ms=int(store.frame("BTCUSDT", "60")["ts_ms"].iloc[-1]) + INTERVAL_MS["60"])
    return load_stack(store, clock), clock, store


def _signal(st, clock, symbol="BTCUSDT"):
    from killtests.offline_ensemble import frozen_time
    with frozen_time(clock):
        return asyncio.run(st.aggregator.get_trading_signal_multi_timeframe(symbol, "60"))


def test_signal_computes_offline(stack):
    st, clock, store = stack
    sig = _signal(st, clock)
    assert sig.symbol == "BTCUSDT"
    assert sig.action is not None
    assert sig.indicators  # primary-timeframe indicator dict survives
    assert sig.timestamp == clock.now_ms  # frozen_time pin holds


def test_regime_fetch_is_real_not_default(stack):
    """The regime seam works: ADX reaches the offline TA app. An UNKNOWN-default
    regime on every call means the inline-httpx patch is broken (silent
    divergence from deployed behavior)."""
    st, clock, store = stack
    from killtests.offline_ensemble import frozen_time
    det = st.aggregator.core_aggregator.regime_detector
    det._cache.clear()
    with frozen_time(clock):
        analysis = asyncio.run(det.detect_regime("BTCUSDT", "60"))
    assert analysis.regime.name != "UNKNOWN", (
        "regime degraded to default — market_regime httpx shim not reaching the ASGI app"
    )


def test_deployed_bugs_preserved(stack):
    """Spec §3.3: ATR entry absent/None; atr_stop_loss has no producer."""
    st, clock, store = stack
    sig = _signal(st, clock)
    assert sig.indicators.get("ATR") is None
    assert "atr_stop_loss" not in sig.metadata


def test_ensemble_runs_on_signal(stack):
    st, clock, store = stack
    sig = _signal(st, clock)
    price = float(store.frame("BTCUSDT", "60")["close"].iloc[-1])
    ens = st.ensemble.generate_signal(sig, current_price=price)
    # None (HOLD) or an EnsembleSignal — both prove the leg wiring executes
    if ens is not None:
        assert ens.action.value in ("BUY", "SELL")
        assert set(ens.weights_snapshot) == {"simple_rsi", "multi_indicator", "mean_reversion"}


def test_as_of_no_lookahead(stack):
    """Signals at an earlier clock must not see later candles."""
    st, clock, store = stack
    f = store.frame("BTCUSDT", "60")
    clock.now_ms = int(f["ts_ms"].iloc[400]) + INTERVAL_MS["60"]
    sig = _signal(st, clock)
    assert sig.timestamp == clock.now_ms
    clock.now_ms = int(f["ts_ms"].iloc[-1]) + INTERVAL_MS["60"]  # restore
```

- [ ] **Step 2: Run to verify FAIL**

Run: `python3 -m pytest tests/killtests/test_offline_ensemble_seam.py -v --no-cov`
Expected: FAIL — `killtests.offline_ensemble` missing.

- [ ] **Step 3: Implement the loader**

`backtesting/killtests/offline_ensemble.py` — follow this structure exactly; where a detail is discovered at implementation time (attribute names of regime-detector clients), grep the loaded module source and swap every `httpx.AsyncClient` instance found:

```python
"""Offline replay of the DEPLOYED ensemble signal chain (spec §3.1).

Seam: real TA FastAPI app served in-process via httpx.ASGITransport; real
SignalAggregator / MTF / CoreAggregator / MultiStrategyEnsemble loaded via
the dual-namespace shim pattern proven by run_walk_forward_ensemble.py:58-191.
Only the market-data HTTP boundary is faked (MockTransport -> CandleStore).

MUST be loaded once per process (TA app registers Prometheus collectors in
the global registry; a second import raises Duplicated timeseries).
"""
import importlib.util
import os
import re
import sys
import types
from contextlib import contextmanager
from dataclasses import dataclass
from unittest import mock

import httpx

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_TA_PATH = os.path.join(_REPO, "services", "technical-analysis")
_TE_PATH = os.path.join(_REPO, "services", "trading-engine")
_RM_PATH = os.path.join(_REPO, "services", "risk-metrics-service")

sys.path.insert(0, _REPO)

from killtests.candles import CandleStore  # noqa: E402


@dataclass
class ReplayClock:
    now_ms: int


@contextmanager
def frozen_time(clock: ReplayClock):
    """Pin wall clock to the replay clock for one call.

    signal_aggregator.py (and market_regime cache writes) use FUNCTION-LOCAL
    `import time` — a module-attribute patch is a no-op. Patch time.time
    process-wide for the duration of the call instead. asyncio/httpx use
    time.monotonic internally, which stays real.
    """
    with mock.patch("time.time", lambda: clock.now_ms / 1000.0):
        yield


@dataclass
class Stack:
    aggregator: object
    ensemble: object
    signal_aggregator_mod: object
    regime_mod: object  # loaded app.aggregation.market_regime (its `httpx` name is the patch point)
    SignalAction: object
    kernels: dict  # {'deflated_sharpe_ratio', 'CombinatorialPurgedCV', 'cpcv_to_dsr', ...}
    ta_app: object
    clock: ReplayClock


_LOADED: Stack = None


def _purge_app_modules() -> None:
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]


_KERNELS: dict = None


def _load_kernels() -> dict:
    """Spec-load risk-metrics kernels under unique names — collision-proof and
    idempotent (callable before OR after the TE `app` namespace exists, and
    repeatedly within one pytest process). Never purges `sys.modules['app']`.
    """
    global _KERNELS
    if _KERNELS is not None:
        return _KERNELS

    def _spec_load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    sm = _spec_load("_killtests_sharpe_metrics",
                    os.path.join(_RM_PATH, "app", "sharpe_metrics.py"))
    # cpcv.py does `from app.sharpe_metrics import deflated_sharpe_ratio`:
    # temporarily alias our loaded copy; restore whatever was there before.
    created_app = "app" not in sys.modules
    if created_app:
        sys.modules["app"] = types.ModuleType("app")
    prior = sys.modules.get("app.sharpe_metrics")
    sys.modules["app.sharpe_metrics"] = sm
    try:
        cp = _spec_load("_killtests_cpcv", os.path.join(_RM_PATH, "app", "cpcv.py"))
    finally:
        if prior is not None:
            sys.modules["app.sharpe_metrics"] = prior
        else:
            del sys.modules["app.sharpe_metrics"]
        if created_app:
            del sys.modules["app"]
    _KERNELS = {
        "deflated_sharpe_ratio": sm.deflated_sharpe_ratio,
        "probabilistic_sharpe_ratio": sm.probabilistic_sharpe_ratio,
        "CombinatorialPurgedCV": cp.CombinatorialPurgedCV,
        "cpcv_to_dsr": cp.cpcv_to_dsr,
        "cpcv_sharpe_distribution": cp.cpcv_sharpe_distribution,
    }
    return _KERNELS


def _load_ta_app():
    """Import the full TA FastAPI app under TA's own `app` namespace, keep refs, purge."""
    sys.path.insert(0, _TA_PATH)
    import app.fetcher as ta_fetcher_mod  # noqa: PLC0415
    import app.main as ta_main  # noqa: PLC0415
    ta_app = ta_main.app
    _purge_app_modules()
    sys.path.remove(_TA_PATH)
    return ta_app, ta_fetcher_mod


def _mk_market_data_transport(store: CandleStore, clock: ReplayClock) -> httpx.MockTransport:
    kline_re = re.compile(r"/api/v1/klines/([A-Z]+)$")

    def handler(request: httpx.Request) -> httpx.Response:
        m = kline_re.search(request.url.path)
        if not m:
            return httpx.Response(404, json={"success": False, "error": "not mocked"})
        symbol = m.group(1)
        params = dict(request.url.params)
        interval = params.get("interval", "60")
        interval = {"D": "1440", "1440": "1440"}.get(interval, interval)
        limit = int(params.get("limit", 200))
        rows = store.as_of(symbol, interval, clock.now_ms, limit)
        return httpx.Response(200, json={"success": True, "data": rows})

    return httpx.MockTransport(handler)


def _load_te_module(dotted_name: str, rel_path: str):
    abs_path = os.path.join(_TE_PATH, rel_path)
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)
    return module


def _build_te_namespace():
    """PHASE 3 of the shim pattern, extended for the full deployed chain."""
    from shared.account import DEFAULTS  # noqa: PLC0415

    sys.path.insert(0, _TE_PATH)
    app_pkg = types.ModuleType("app")
    app_pkg.__path__ = [os.path.join(_TE_PATH, "app")]
    sys.modules["app"] = app_pkg

    te_enums = _load_te_module("app.models.enums", "app/models/enums.py")
    te_signal = _load_te_module("app.models.signal", "app/models/signal.py")
    models_stub = types.ModuleType("app.models")
    models_stub.SignalAction = te_enums.SignalAction
    models_stub.IndicatorSignal = te_signal.IndicatorSignal
    models_stub.TradingSignal = te_signal.TradingSignal
    sys.modules["app.models"] = models_stub

    config_stub = types.ModuleType("app.config")

    def _stub_get_settings():
        return types.SimpleNamespace(
            technical_analysis_url="http://ta.offline",
            market_data_url="http://md.offline",
            service_name="killtests-offline-ensemble",
            max_risk_per_trade=DEFAULTS["MAX_RISK_PER_TRADE"],
            ensemble_min_position_pct=0.05,
            ensemble_confidence_size_multiplier=3.7,
        )

    config_stub.get_settings = _stub_get_settings
    sys.modules["app.config"] = config_stub

    monitoring_pkg = types.ModuleType("app.monitoring")
    monitoring_pkg.__path__ = []
    sys.modules["app.monitoring"] = monitoring_pkg
    metrics_stub = types.ModuleType("app.monitoring.metrics")
    metrics_stub.record_cache_hit = lambda *a, **kw: None
    metrics_stub.record_cache_miss = lambda *a, **kw: None
    sys.modules["app.monitoring.metrics"] = metrics_stub

    aggregation_pkg = types.ModuleType("app.aggregation")
    aggregation_pkg.__path__ = [os.path.join(_TE_PATH, "app", "aggregation")]
    sys.modules["app.aggregation"] = aggregation_pkg

    _load_te_module("app.phase1_metrics", "app/phase1_metrics.py")
    _load_te_module("app.aggregation.confidence_guard", "app/aggregation/confidence_guard.py")
    _load_te_module("app.aggregation.gatekeeper", "app/aggregation/gatekeeper.py")
    _load_te_module("app.aggregation.validator", "app/aggregation/validator.py")
    _load_te_module("app.aggregation.voter", "app/aggregation/voter.py")
    _load_te_module("app.aggregation.signal_cache", "app/aggregation/signal_cache.py")
    regime_mod = _load_te_module("app.aggregation.market_regime", "app/aggregation/market_regime.py")
    core_mod = _load_te_module("app.aggregation.aggregator_core", "app/aggregation/aggregator_core.py")
    mtf_mod = _load_te_module("app.aggregation.multi_timeframe", "app/aggregation/multi_timeframe.py")
    # signal_aggregator's imports from app.aggregation (top-of-file line 22 and
    # lazy line 974) must both resolve against the stub package:
    aggregation_pkg.CoreAggregator = core_mod.CoreAggregator
    aggregation_pkg.get_multi_timeframe_analyzer = mtf_mod.get_multi_timeframe_analyzer

    # signal_aggregator.py:24 `from app.services.indicator_registry import get_indicator_registry`
    # — stub the package so the REAL app/services/__init__.py (which drags in
    # trading_service and the full models package) never runs.
    services_pkg = types.ModuleType("app.services")
    services_pkg.__path__ = []
    sys.modules["app.services"] = services_pkg
    reg_mod = _load_te_module("app.services.indicator_registry", "app/services/indicator_registry.py")
    services_pkg.indicator_registry = reg_mod

    sa_mod = _load_te_module("app.signal_aggregator", "app/signal_aggregator.py")

    _load_te_module("app.strategies.simple_rsi_strategy", "app/strategies/simple_rsi_strategy.py")
    _load_te_module("app.strategies.mean_reversion_strategy", "app/strategies/mean_reversion_strategy.py")
    mse_mod = _load_te_module("app.strategies.multi_strategy_ensemble", "app/strategies/multi_strategy_ensemble.py")

    return sa_mod, mse_mod, te_enums, regime_mod


def _swap_httpx_clients(obj, transport: httpx.AsyncTransport, base_url: str) -> None:
    """Replace every httpx.AsyncClient attribute on obj (one level deep)."""
    for name in dir(obj):
        try:
            attr = getattr(obj, name)
        except Exception:
            continue
        if isinstance(attr, httpx.AsyncClient):
            setattr(obj, name, httpx.AsyncClient(transport=transport, base_url=base_url, timeout=30.0))


def load_stack(store: CandleStore, clock: ReplayClock) -> Stack:
    global _LOADED
    if _LOADED is not None:
        raise RuntimeError("load_stack may only run once per process (Prometheus registry)")

    kernels = _load_kernels()
    ta_app, ta_fetcher_mod = _load_ta_app()

    # Patch market-data boundary: real TA fetcher keeps its validation pipeline,
    # only its HTTP client is mocked to serve CandleStore rows as-of the clock.
    md_transport = _mk_market_data_transport(store, clock)
    fetcher = ta_fetcher_mod.get_fetcher()
    fetcher.client = httpx.AsyncClient(transport=md_transport, base_url="http://md.offline", timeout=30.0)

    sa_mod, mse_mod, te_enums, regime_mod = _build_te_namespace()

    aggregator = sa_mod.SignalAggregator()
    ta_transport = httpx.ASGITransport(app=ta_app)
    _swap_httpx_clients(aggregator, ta_transport, "http://ta.offline")

    # MarketRegimeDetector builds `httpx.AsyncClient` INLINE per ADX fetch
    # (market_regime.py:242) — no attribute exists to swap. Patch the loaded
    # module's `httpx` name with a factory shim so those inline constructions
    # get the ASGI transport. Unpatched, every regime fetch fails silently and
    # degrades to the UNKNOWN default — a divergence the golden gate can't see.
    class _HttpxShim:
        ASGITransport = httpx.ASGITransport
        MockTransport = httpx.MockTransport
        Response = httpx.Response
        Request = httpx.Request

        @staticmethod
        def AsyncClient(**kw):
            kw.pop("transport", None)
            kw.setdefault("timeout", 30.0)
            return httpx.AsyncClient(transport=ta_transport, base_url="http://ta.offline", **kw)

    regime_mod.httpx = _HttpxShim

    ensemble = mse_mod.MultiStrategyEnsemble()
    # Determinism pin: weights file absent on host -> default 0.50 win rates -> 1/3 each.
    snapshot = ensemble.weights.normalized_weights() if hasattr(ensemble.weights, "normalized_weights") else None
    if snapshot is not None:
        vals = sorted(round(v, 6) for v in snapshot.values())
        assert vals == [round(1 / 3, 6)] * 3, f"weights not pinned to 1/3: {snapshot}"

    _LOADED = Stack(
        aggregator=aggregator, ensemble=ensemble, signal_aggregator_mod=sa_mod,
        regime_mod=regime_mod, SignalAction=te_enums.SignalAction,
        kernels=kernels, ta_app=ta_app, clock=clock,
    )
    return _LOADED
```

Implementation notes (discovered-at-build-time items, resolve by reading the loaded sources — do not guess):
- If `signal_aggregator.py` imports modules beyond the stub set (check its import block), extend `_build_te_namespace` with additional `_load_te_module`/stub lines following the same pattern.
- The regime seam is handled by the `_HttpxShim` module patch above (the detector constructs clients inline — verified at `market_regime.py:242`); the detector object itself sits at `aggregator.core_aggregator.regime_detector` (`aggregator_core.py:119`). The seam test asserts regime data is real, not the UNKNOWN default.
- If `mean_reversion_strategy.py`/`simple_rsi_strategy.py` import other `app.*` names, stub or load them the same way.
- The regime cache is cleared per bar by the driver (Task 9), not here.
- If `ensemble.weights.normalized_weights()` is named differently, read `multi_strategy_ensemble.py` and adjust the assertion (the pin requirement stands: ⅓/⅓/⅓ or fail loudly).

- [ ] **Step 4: Run seam tests until they pass**

Run: `python3 -m pytest tests/killtests/test_offline_ensemble_seam.py -v --no-cov`
Expected: 5 PASS. This is the riskiest step of the plan — iterate on the loader until green, extending stubs per the notes above. If `ASGITransport` fails on a TA route (lifespan-dependent state — not expected per the verified facts), fall back per spec §3.1: MockTransport routing to `indicator_service` functions; record the deviation.

- [ ] **Step 5: Commit**

```bash
git add backtesting/killtests/offline_ensemble.py tests/killtests/test_offline_ensemble_seam.py
git commit -m "feat(killtests): offline ensemble seam - real TA app via ASGI, real TE chain via shims"
```

---

### Task 9: `offline_ensemble.py` part 2 — replay driver + signal series

**Files:**
- Modify: `backtesting/killtests/offline_ensemble.py` (append driver)
- Test: `tests/killtests/test_offline_driver.py`

**Interfaces:**
- Consumes: Task 8 `load_stack`/`ReplayClock`/`Stack`.
- Produces: `async run_replay(store: CandleStore, stack: Stack, clock: ReplayClock, symbols: list[str], warmup_bars: int = 300) -> pd.DataFrame` — one row per (symbol, 60m bar close) after warmup, columns: `symbol, ts_ms (decision time = bar close), action (str), confidence (float), aggregated_score (float), consensus_count (int), ens_action (str|None), ens_confidence (float|None), ens_position_size_pct (float|None), close (float, primary 60m close)`. Plus CLI: `python3 backtesting/killtests/offline_ensemble.py --data-dir backtesting/data --out <parquet-or-csv>` writing the series. Driver clears the regime cache every bar: locate the detector on the aggregator (`aggregator.regime_detector._cache.clear()` — verify the attribute name while implementing; if the detector lives inside `get_trading_signal`'s scope, clear via the module-level accessor found in the source).

- [ ] **Step 1: Write the failing driver test**

`tests/killtests/test_offline_driver.py`:

```python
import asyncio
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.candles import INTERVAL_MS, CandleStore  # noqa: E402

from conftest import _write_candles  # noqa: E402  # shared writer, same-dir conftest


def test_driver_emits_rows_and_advances_clock(tmp_path):
    for iv, n in [("15", 2000), ("60", 500), ("240", 400), ("1440", 60)]:
        _write_candles(tmp_path, "BTCUSDT", iv, n, "2026-04-01 00:00:00")
    store = CandleStore(str(tmp_path), ["BTCUSDT"], ["15", "60", "240", "1440"])
    from killtests.offline_ensemble import ReplayClock, load_stack, run_replay
    clock = ReplayClock(now_ms=0)
    stack = load_stack(store, clock)
    df = asyncio.run(run_replay(store, stack, clock, ["BTCUSDT"], warmup_bars=450))
    f60 = store.frame("BTCUSDT", "60")
    expected_rows = len(f60) - 450
    assert len(df) == expected_rows
    assert df["ts_ms"].is_monotonic_increasing
    # decision time is always a 60m bar CLOSE
    assert ((df["ts_ms"] - f60["ts_ms"].iloc[0]) % INTERVAL_MS["60"] == 0).all()
    assert set(df["action"].unique()) <= {"BUY", "SELL", "HOLD"}
    assert df["close"].notna().all()
```

Note: this test imports the seam test's `_write`; the same process re-uses `load_stack` — pytest runs both files in one process and `load_stack` raises on the second call. Guard: give `run_replay`'s test its own pytest module-scoped process via `pytest tests/killtests/test_offline_driver.py` run separately, OR (implementation choice) make `load_stack` return the cached `_LOADED` when called with the same store/clock types instead of raising, re-wiring `_mk_market_data_transport`'s store/clock references. **Choose the cache-and-rewire option**: change `load_stack` so a second call replaces the fetcher transport and clock references on the cached stack rather than raising. Update the Task 8 docstring accordingly.

- [ ] **Step 2: Run to verify FAIL, implement the driver**

Append to `offline_ensemble.py`:

```python
async def run_replay(store, stack, clock, symbols, warmup_bars=300):
    import pandas as pd  # local: keeps module import light

    from killtests.candles import INTERVAL_MS

    rows = []
    step = INTERVAL_MS["60"]
    for symbol in symbols:
        f60 = store.frame(symbol, "60")
        for i in range(warmup_bars, len(f60)):
            bar_close_ms = int(f60["ts_ms"].iloc[i]) + step
            clock.now_ms = bar_close_ms
            _clear_regime_cache(stack.aggregator)
            with frozen_time(clock):  # pins time.time -> bar close (function-local imports)
                sig = await stack.aggregator.get_trading_signal_multi_timeframe(symbol, "60")
            close = float(f60["close"].iloc[i])
            ens = stack.ensemble.generate_signal(sig, current_price=close)
            rows.append({
                "symbol": symbol, "ts_ms": bar_close_ms,
                "action": sig.action.value, "confidence": float(sig.confidence),
                "aggregated_score": float(sig.aggregated_score),
                "consensus_count": int(sig.consensus_count),
                "ens_action": ens.action.value if ens else None,
                "ens_confidence": float(ens.confidence) if ens else None,
                "ens_position_size_pct": float(ens.position_size_pct) if ens else None,
                "close": close,
            })
    return pd.DataFrame(rows)


def _clear_regime_cache(aggregator) -> None:
    # Verified location: aggregator_core.py:119 — NOT on the aggregator itself.
    det = aggregator.core_aggregator.regime_detector
    assert det is not None, "regime detector missing — determinism pin broken"
    det._cache.clear()
```

Plus a `main()`/CLI block mirroring Task 6's (`--data-dir`, `--symbols` defaulting to the 5 validated, `--warmup` default 300, `--out` default `.planning/evidence/killtests/signal-series.csv`): build store over `["15", "60", "240", "1440"]`, `ReplayClock(0)`, `load_stack`, `asyncio.run(run_replay(...))`, `df.to_csv(out, index=False)`, print row count.

Cache-and-rewire on a second `load_stack` call must rebuild **everything that closed over the first caller's objects**: construct a fresh `_mk_market_data_transport(new_store, new_clock)` and swap it onto the TA fetcher's client, rebind `stack.clock = new_clock`, and rebuild the `_HttpxShim` only if the TA app object changed (it can't — one per process). `frozen_time` takes the clock as an argument, so it needs no rewiring.

- [ ] **Step 3: Run the driver test**

Run: `python3 -m pytest tests/killtests/test_offline_driver.py -v --no-cov`
Expected: PASS. Also re-run the seam tests together to confirm the cache-and-rewire change: `python3 -m pytest tests/killtests/test_offline_ensemble_seam.py tests/killtests/test_offline_driver.py -v --no-cov` → all PASS in one process.

- [ ] **Step 4: Commit**

```bash
git add backtesting/killtests/offline_ensemble.py tests/killtests/test_offline_driver.py
git commit -m "feat(killtests): bar-by-bar replay driver emitting the deployed-signal series"
```

---

### Task 10: Preservation + weight-canary tests

**Files:**
- Test: `tests/killtests/test_preservation.py`

**Interfaces:**
- Consumes: the Task 8 stack (module refs). No production code changes.
- Produces: red-flag tests that fail loudly when a future engine fix changes the instrument (spec §7.3) + a weights/params canary snapshot.

- [ ] **Step 1: Write the tests (they should PASS immediately — they pin current behavior)**

`tests/killtests/test_preservation.py`:

```python
"""Known-bug preservation (spec §3.3/§7.3): these tests pin DEPLOYED behavior.

A failure here means the engine changed — update the offline replay
consciously, then re-baseline. Never 'fix' these to green silently.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

SA = REPO / "services" / "trading-engine" / "app" / "signal_aggregator.py"
MSE = REPO / "services" / "trading-engine" / "app" / "strategies" / "multi_strategy_ensemble.py"
SRS = REPO / "services" / "trading-engine" / "app" / "strategies" / "simple_rsi_strategy.py"


def test_atr_never_reinjected_into_indicators():
    src = SA.read_text()
    # fetch_all_indicators routes ATR out to atr_data; nothing assigns indicators["ATR"]
    assert 'indicators["ATR"]' not in src.replace(" ", "")


def test_simple_rsi_atr_pct_fallback_is_002():
    src = SRS.read_text()
    assert re.search(r"atr_pct\s*=\s*0\.02", src), "hardcoded 0.02 fallback changed"


def test_no_producer_for_atr_stop_loss_metadata():
    te_app = REPO / "services" / "trading-engine" / "app"
    producers = [
        p for p in te_app.rglob("*.py")
        if re.search(r"""metadata\[["']atr_stop_loss["']\]\s*=""", p.read_text())
    ]
    assert producers == [], f"atr_stop_loss now has producer(s): {producers}"


def test_mtf_consensus_action_not_applied():
    src = SA.read_text()
    # the merge mutates confidence only; consensus_action lands in metadata
    assert "primary_signal.confidence" in src
    assert not re.search(r"primary_signal\.action\s*=\s*consensus", src)


def test_ensemble_constants_pinned():
    src = MSE.read_text()
    assert re.search(r"AGGREGATION_THRESHOLD\s*=\s*\(?\s*0\.10", src)
    assert re.search(r"MIN_AGREEING_LEGS\s*=\s*\(?\s*1", src)


def test_voting_weights_canary():
    """Snapshot of client-side metadata weights in fetch_* (the live table).

    RESEARCH_WEIGHTS in voter.py is dead code; THIS is what votes. Measured
    2026-08-05: 9 weight literals summing 9.7 — the ACTIVE set (total 8.1:
    five 1.0s incl. ADX, SMA 0.8, Ichimoku 1.3, ...) plus two literals inside
    the DISABLED fetch_rsi_divergence (1.2) and fetch_enhanced_sqzmom (1.4)
    functions, which fetch_all_indicators does not call. If this fails, the
    live weight table moved — update the snapshot AND re-run any standing H4
    verdict.
    """
    src = SA.read_text()
    weights = re.findall(r'"weight":\s*([0-9.]+)', src)
    assert len(weights) == 9, f"weight-literal count changed: {len(weights)} (was 9)"
    total = sum(float(w) for w in weights)
    assert abs(total - 9.7) < 0.01, f"total weight literals changed: {total} (was 9.7)"


def test_confidence_can_exceed_one():
    """Spec §3.3 bullet 5: TradingSignal has no validate_assignment, so the MTF
    x1.2 modifier can push confidence past the le=1.0 field bound after
    construction. Pin it: if a future fix adds validate_assignment, this fails
    and the replay must be consciously re-baselined."""
    import importlib.util
    import sys
    import types

    te_app = REPO / "services" / "trading-engine" / "app"

    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    created_app = "app" not in sys.modules
    if created_app:
        sys.modules["app"] = types.ModuleType("app")
    prior_models = sys.modules.get("app.models")
    prior_enums = sys.modules.get("app.models.enums")
    try:
        enums = _load("app.models.enums", te_app / "models" / "enums.py")
        models_stub = types.ModuleType("app.models")
        models_stub.enums = enums
        sys.modules["app.models"] = models_stub
        signal_mod = _load("_preservation_signal", te_app / "models" / "signal.py")
        sig = signal_mod.TradingSignal(
            symbol="BTCUSDT", timestamp=1, action=enums.SignalAction.BUY,
            confidence=0.9, indicators={}, aggregated_score=0.5, consensus_count=3,
        )
        sig.confidence = 1.08  # must NOT raise, must stick (no validate_assignment)
        assert sig.confidence == 1.08
    finally:
        if prior_models is not None:
            sys.modules["app.models"] = prior_models
        else:
            sys.modules.pop("app.models", None)
        if prior_enums is not None:
            sys.modules["app.models.enums"] = prior_enums
        else:
            sys.modules.pop("app.models.enums", None)
        if created_app:
            sys.modules.pop("app", None)
```

- [ ] **Step 2: Run and adjust the canary to reality**

Run: `python3 -m pytest tests/killtests/test_preservation.py -v --no-cov`
Expected: PASS. If `test_voting_weights_canary` finds a different count/total, read `signal_aggregator.py`'s actual `metadata={"weight": ...}` entries and pin the true values (the probe measured total 8.1 across the voting set; verify and correct the assertion to the measured truth — the point is pinning, not the specific 8.1).

- [ ] **Step 3: Commit**

```bash
git add tests/killtests/test_preservation.py
git commit -m "test(killtests): known-bug preservation pins + voting-weight canary"
```

---

### Task 11: Golden-sample parity tests (offline vs running stack)

**Files:**
- Test: `tests/killtests/test_golden_parity.py`
- Modify: `pytest.ini` — the repo sets `--strict-markers`; register the marker or the module ERRORS at collection: add `golden: golden-sample parity tests requiring the running docker stack` under `markers`

**Interfaces:**
- Consumes: running docker stack (TA `:8004`, market-data `:8002`); the offline stack.
- Produces: the spec §7.1 gate. Marked `@pytest.mark.golden`; skipped with a LOUD message when the stack is down. **An H4 verdict is invalid unless this suite passed on the same day** — Task 12's CLI enforces it via a stamp file this suite writes on success: `.planning/evidence/killtests/golden-parity-stamp.json` (`{"date": "YYYYMMDD", "passed": true}`).

- [ ] **Step 1: Write the tests**

`tests/killtests/test_golden_parity.py`:

```python
"""Golden-sample parity: same candles -> identical signals, offline vs live TA.

Two layers:
  A) every TA indicator endpoint: live HTTP response == offline ASGI response
     for the identical candle window (window equality asserted first).
  B) full aggregator chain: SignalAggregator against live TA vs against the
     offline ASGI app — TradingSignal fields must match.
Requires the docker stack; skips (loudly) otherwise. On full pass, writes
the parity stamp consumed by the H4 CLI gate.
"""
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

TA_URL = "http://localhost:8004"
MD_URL = "http://localhost:8002"
STAMP = REPO / ".planning" / "evidence" / "killtests" / "golden-parity-stamp.json"

pytestmark = pytest.mark.golden


def _stack_up() -> bool:
    try:
        return httpx.get(f"{TA_URL}/health", timeout=3).status_code == 200 and \
               httpx.get(f"{MD_URL}/health", timeout=3).status_code == 200
    except Exception:
        return False


if not _stack_up():
    pytest.skip(
        "GOLDEN PARITY SKIPPED - docker stack down. H4 verdicts are INVALID "
        "until this suite passes. Start: docker compose -f docker-compose.unified.yml up -d",
        allow_module_level=True,
    )

SYMBOLS = ["BTCUSDT", "SOLUSDT", "ADAUSDT"]  # 3 windows (one per symbol) — see spec amendment: live TA has no as-of param, so window breadth comes from symbols + endpoints, not from time travel
ENDPOINTS = [  # (path template, params) — extend to all 11 while implementing
    ("/api/v1/indicators/rsi/{s}", {"interval": "60"}),
    ("/api/v1/indicators/macd/{s}", {"interval": "60"}),
    ("/api/v1/indicators/bollinger/{s}", {"interval": "60"}),
]


@pytest.fixture(scope="module")
def offline():
    from killtests.candles import CandleStore
    from killtests.offline_ensemble import ReplayClock, load_stack
    store = CandleStore("backtesting/data",
                        ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"],
                        ["15", "60", "240", "1440"])
    clock = ReplayClock(now_ms=int(time.time() * 1000))
    return load_stack(store, clock), store, clock


def test_candle_window_equality(offline):
    """Precondition: DB candles == CSV candles for the comparison window."""
    _, store, clock = offline
    for sym in SYMBOLS:
        live = httpx.get(f"{MD_URL}/api/v1/klines/{sym}",
                         params={"interval": "60", "limit": 50, "mainnet_only": "true"},
                         timeout=10).json()["data"]
        offline_rows = store.as_of(sym, "60", clock.now_ms, 50)
        live_by_ts = {int(r["timestamp"]): r for r in live}
        matched = 0
        for row in offline_rows:
            lv = live_by_ts.get(row["timestamp"])
            if lv is None:
                continue
            assert float(lv["close"]) == pytest.approx(row["close"]), \
                f"{sym} candle mismatch at {row['timestamp']}"
            matched += 1
        assert matched >= 40, f"{sym}: only {matched}/50 overlapping candles (backfill stale? refresh it)"


def test_indicator_endpoint_parity(offline):
    stack, store, clock = offline
    transport = httpx.ASGITransport(app=stack.ta_app)

    async def compare():
        async with httpx.AsyncClient(transport=transport, base_url="http://ta.offline") as oc, \
                   httpx.AsyncClient(base_url=TA_URL) as lc:
            for sym in SYMBOLS:
                for tmpl, params in ENDPOINTS:
                    path = tmpl.format(s=sym)
                    o = (await oc.get(path, params=params)).json()
                    l = (await lc.get(path, params=params)).json()
                    o.pop("timestamp", None); l.pop("timestamp", None)
                    assert o == l, f"parity break {sym} {path}:\noffline={o}\nlive={l}"
    asyncio.run(compare())


_CHAIN_ACTIONS: list = []  # collected by test_full_chain_parity; gates the stamp


def _run_chain_leg(stack, symbol, client, regime_httpx):
    """One full-chain evaluation with BOTH transports (aggregator client and the
    regime module's inline-httpx factory) pointed at the same target."""
    agg = stack.aggregator
    saved_client, saved_httpx = agg.client, stack.regime_mod.httpx
    agg.client, stack.regime_mod.httpx = client, regime_httpx
    agg.core_aggregator.regime_detector._cache.clear()
    try:
        return asyncio.run(agg.get_trading_signal_multi_timeframe(symbol, "60"))
    finally:
        agg.client, stack.regime_mod.httpx = saved_client, saved_httpx


def test_full_chain_parity(offline):
    """SignalAggregator vs live TA == SignalAggregator vs offline ASGI —
    field-for-field on TradingSignal, per-indicator, AND the ensemble output
    (spec §7.1). All 3 golden symbols."""
    stack, store, clock = offline
    asgi_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=stack.ta_app), base_url="http://ta.offline", timeout=30.0)
    live_client = httpx.AsyncClient(base_url=TA_URL, timeout=30.0)

    for sym in SYMBOLS:
        sig_off = _run_chain_leg(stack, sym, asgi_client, stack.regime_mod.httpx)
        sig_live = _run_chain_leg(stack, sym, live_client, httpx)  # live leg: REAL httpx
        assert sig_off.action == sig_live.action, sym
        assert sig_off.confidence == pytest.approx(sig_live.confidence, abs=1e-9), sym
        assert sig_off.aggregated_score == pytest.approx(sig_live.aggregated_score, abs=1e-9), sym
        assert sig_off.consensus_count == sig_live.consensus_count, sym
        assert set(sig_off.indicators) == set(sig_live.indicators), sym
        for name, ind_off in sig_off.indicators.items():
            ind_live = sig_live.indicators[name]
            if ind_off is None or ind_live is None:
                assert ind_off is ind_live, f"{sym}/{name}: one leg None"
                continue
            assert ind_off.signal == ind_live.signal, f"{sym}/{name}"
            assert ind_off.confidence == pytest.approx(ind_live.confidence, abs=1e-9), f"{sym}/{name}"
            assert ind_off.value == ind_live.value or \
                ind_off.value == pytest.approx(ind_live.value, abs=1e-9), f"{sym}/{name}"
        price = float(store.frame(sym, "60")["close"].iloc[-1])
        ens_off = stack.ensemble.generate_signal(sig_off, current_price=price)
        ens_live = stack.ensemble.generate_signal(sig_live, current_price=price)
        assert (ens_off is None) == (ens_live is None), sym
        if ens_off is not None:
            assert ens_off == ens_live, f"{sym}: EnsembleSignal diverged"
        _CHAIN_ACTIONS.append(sig_off.action.value)


def test_write_stamp(offline):
    """Stamp only after full-chain parity produced >= 1 non-HOLD signal
    (spec §7.1). All-HOLD parity never exercised the ensemble legs — no stamp."""
    non_hold = [a for a in _CHAIN_ACTIONS if a != "HOLD"]
    if not non_hold:
        pytest.skip(
            "GOLDEN PARITY all-HOLD across all symbols — stamp NOT written; "
            "re-run when the market produces a live non-HOLD signal (H4 stays gated)"
        )
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps({"date": date.today().strftime("%Y%m%d"), "passed": True}))
    assert STAMP.exists()
```

Implementation notes: extend `ENDPOINTS` to the full active fetch set — verified 2026-08-05 to be exactly 11: rsi, macd, bollinger, sma, ema, trend, volume, stochastic, ichimoku, adx, atr (rsi-divergence and sqzmom-enhanced are commented out of `fetch_all_indicators`); all 11 exist as GET routes in TA `app/main.py` — copy the exact paths and params from the `fetch_*` functions in `signal_aggregator.py`. Regime-detector calls in the live comparison hit live TA both times through the swapped client — if the detector holds its own client (Task 8 note), swap that too inside `one()`. Candle-window equality can legitimately fail if the backfill is days old — refresh the 60m/15m/240m backfill (Task 2 Step 3) rather than loosening the assertion. Timing skew: both chains run within the same minute against the same latest-closed candle; if a bar closes between the two runs, rerun the test.

- [ ] **Step 2: Run against the live stack**

```bash
docker compose -f docker-compose.unified.yml up -d  # if not already up
python3 -m pytest tests/killtests/test_golden_parity.py -v --no-cov -m golden
```
Expected: 4 PASS and the stamp file written. Any parity mismatch is a STOP: diagnose the seam (most likely: an unswapped httpx client, or backfill/DB candle drift) before touching H4.

- [ ] **Step 3: Commit**

```bash
git add tests/killtests/test_golden_parity.py pytest.ini
git commit -m "test(killtests): golden-sample parity gate with H4 stamp file"
```

---

### Task 12: `h4_information.py` — information test + order gate

**Files:**
- Create: `backtesting/killtests/h4_information.py`, `backtesting/killtests/fixtures/h4_num_trials.json`
- Test: `tests/killtests/test_h4_information.py`

**Interfaces:**
- Consumes: signal series CSV (Task 9), kernels (via `Stack.kernels` OR direct import — use the direct import pattern from Task 8's `_load_kernels`, it needs no TA/TE modules), `latest_verdict`/`write_verdict` (Task 5).
- Produces:
  - `score_signals(series: pd.DataFrame, store: CandleStore, horizon_bars: int = 24) -> pd.DataFrame` — non-HOLD ensemble rows (`ens_action` not null) joined with forward log-return: `fwd_ret = ln(close[t+24] / close[t])`, `signed_ret = fwd_ret * (+1 BUY / -1 SELL)`, `hit = signed_ret > 0`. Rows whose horizon extends past the data end are dropped (count reported).
  - `h4_stats(scored: pd.DataFrame, num_trials: int) -> dict` — `{n_signals, directional_accuracy, dsr, n_cpcv_paths, num_trials_used, pf_pooled, dropped_tail_signals}` (`non_hold_rate` is computed in `main()` from the FULL series — `series['ens_action'].notna().mean()` — and added to the verdict metrics there, since `h4_stats` only sees the filtered frame); DSR via CPCV: `CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.01).split(n_samples=len(scored), label_horizon=24)`, per-path returns = `signed_ret[test_idx]`, then `cpcv_to_dsr(returns_per_path, all_signed_ret)`; **final DSR = deflated_sharpe_ratio(all_signed_ret, num_trials=max(num_trials, n_valid_paths), trial_sharpes_variance=var_of_path_sharpes)** — i.e., the configuration-history `num_trials` floor is applied on top of `cpcv_to_dsr`'s internals (implement by calling the kernel functions directly rather than `cpcv_to_dsr` if its internal `num_trials` cannot be overridden — read `cpcv.py:232` while implementing and pick the variant that lets `num_trials >= 8` bind; document which was used in the verdict config). `pf_pooled = sum(positive signed_ret) / abs(sum(negative signed_ret))`.
  - CLI: `python3 backtesting/killtests/h4_information.py --series <csv> --data-dir backtesting/data [--force]` — refuses without (a) an H3 verdict (`latest_verdict("H3")`), (b) a same-day golden parity stamp; `--force` bypasses with a logged warning line in the verdict caveats.
- `fixtures/h4_num_trials.json` — the committed configuration-history enumeration:

```json
{
  "floor": 8,
  "note": "AUDIT.md H4 clause: count all >=8 strategy configurations tried",
  "configurations": [
    "min_signal_confidence=0.65 (original gate)",
    "min_signal_confidence=0.40 (walk step 2, config.py:402 history)",
    "min_signal_confidence=0.30 (walk step 3)",
    "AGGREGATION_THRESHOLD=0.10 relaxation (multi_strategy_ensemble.py:150)",
    "MIN_AGREEING_LEGS=1 relaxation (multi_strategy_ensemble.py:153)",
    "phase1_strategy_prod walk-forward config (run_walk_forward.py)",
    "CoreAggregator-only harness config (run_walk_forward_ensemble.py)",
    "deployed 3-leg ensemble (this test)"
  ]
}
```

- [ ] **Step 1: Write the failing tests**

`tests/killtests/test_h4_information.py`:

```python
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.h4_information import h4_stats, load_num_trials, score_signals  # noqa: E402


def _series_and_store(n=1200, informative=False, seed=7):
    # n=1200 -> ~390 scored signals; CPCV needs n_samples >= n_groups*(label_horizon+embargo+1)
    # = 10*(24+4+1) = 290 — n=600 (190 signals) would make split() raise ValueError.
    """Synthetic 60m series + matching CandleStore-like frame provider."""
    rng = np.random.default_rng(seed)
    start = 1_700_000_000_000
    step = 3_600_000
    rets = rng.normal(0, 0.01, n)
    closes = 100 * np.exp(np.cumsum(rets))
    f = pd.DataFrame({"ts_ms": [start + i * step for i in range(n)], "close": closes})

    class FakeStore:
        def frame(self, symbol, interval):
            return f

    sig_rows = []
    for i in range(0, n, 3):  # runs to the end so the last ~8 signals genuinely lack a 24-bar horizon
        if informative:
            fwd = np.log(closes[min(i + 24, n - 1)] / closes[i])
            act = "BUY" if fwd > 0 else "SELL"          # oracle: perfect foresight
        else:
            act = "BUY" if rng.random() < 0.5 else "SELL"
        sig_rows.append({"symbol": "TESTUSDT", "ts_ms": start + i * step + step,
                         "action": act, "confidence": 0.5, "aggregated_score": 0.2,
                         "consensus_count": 3, "ens_action": act, "ens_confidence": 0.5,
                         "ens_position_size_pct": 0.05, "close": closes[i]})
    return pd.DataFrame(sig_rows), FakeStore()


def test_score_signals_shapes_and_horizon_drop():
    series, store = _series_and_store()
    scored = score_signals(series, store, horizon_bars=24)
    assert {"signed_ret", "hit", "fwd_ret"} <= set(scored.columns)
    # tail signals without a full 24-bar horizon are dropped
    assert len(scored) < len(series)


def test_oracle_signals_score_high():
    series, store = _series_and_store(informative=True)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    assert stats["directional_accuracy"] > 0.95
    assert stats["dsr"] > 0.95


def test_random_signals_fail_dsr():
    series, store = _series_and_store(informative=False)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    assert stats["dsr"] < 0.95


def test_num_trials_floor():
    doc = load_num_trials()
    assert doc["floor"] == 8
    assert len(doc["configurations"]) >= 8


def test_pf_is_pooled():
    series, store = _series_and_store(informative=True)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    wins = scored.loc[scored["signed_ret"] > 0, "signed_ret"].sum()
    losses = abs(scored.loc[scored["signed_ret"] < 0, "signed_ret"].sum())
    assert stats["pf_pooled"] == pytest.approx(wins / losses if losses else float("inf"))
```

- [ ] **Step 2: Run to verify FAIL, implement**

`backtesting/killtests/h4_information.py` — core functions (kernels: importing `_load_kernels` from `killtests.offline_ensemble` is safe — that module's top level only imports httpx and candles; the TA/TE loads happen inside `load_stack`):

```python
"""H4 kill test: does the deployed ensemble signal carry information?

AUDIT.md:262 — every ensemble signal vs sign of 24h forward log-return.
Accept: directional accuracy > 50% AND DSR > 0.95, num_trials >= 8.
Fee-free by design: this measures information, not P&L.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "backtesting"))

from killtests.candles import CandleStore  # noqa: E402
from killtests.offline_ensemble import _load_kernels  # noqa: E402
from killtests.report import latest_verdict, write_verdict  # noqa: E402

NUM_TRIALS_FIXTURE = os.path.join(_HERE, "fixtures", "h4_num_trials.json")


def load_num_trials(path: str = NUM_TRIALS_FIXTURE) -> dict:
    with open(path) as f:
        return json.load(f)


def score_signals(series: pd.DataFrame, store, horizon_bars: int = 24) -> pd.DataFrame:
    out = []
    fired = series[series["ens_action"].notna()].copy()
    for symbol, grp in fired.groupby("symbol"):
        f = store.frame(symbol, "60").reset_index(drop=True)
        pos_by_ts = {int(ts): i for i, ts in enumerate(f["ts_ms"])}
        for row in grp.itertuples():
            # row.ts_ms is the decision time = close of bar i => bar open at ts_ms - 1h
            i = pos_by_ts.get(int(row.ts_ms) - 3_600_000)
            if i is None or i + horizon_bars >= len(f):
                continue  # tail signal without a full horizon — dropped, counted below
            fwd = float(np.log(f["close"].iloc[i + horizon_bars] / f["close"].iloc[i]))
            direction = 1.0 if row.ens_action == "BUY" else -1.0
            out.append({
                "symbol": symbol, "ts_ms": int(row.ts_ms), "ens_action": row.ens_action,
                "fwd_ret": fwd, "signed_ret": fwd * direction, "hit": fwd * direction > 0,
            })
    scored = pd.DataFrame(out)
    scored.attrs["dropped_tail"] = int(len(fired) - len(scored))
    return scored


class InsufficientSignalsError(Exception):
    pass


def h4_stats(scored: pd.DataFrame, num_trials: int) -> dict:
    k = _load_kernels()
    # CPCV purge/embargo assume chronological order; score_signals emits rows
    # grouped by symbol — sort by time or the leakage protection is fictional.
    # (With sparse multi-symbol signals a 24-sample purge in index space spans
    # >= 24h in time — conservative; noted in the verdict config.)
    scored = scored.sort_values("ts_ms").reset_index(drop=True)
    rets = scored["signed_ret"].to_numpy(dtype=float)
    cv = k["CombinatorialPurgedCV"](n_groups=10, k_test_groups=2, embargo_pct=0.01)
    min_n = 10 * (24 + max(1, int(np.ceil(0.01 * len(rets)))) + 1)
    if len(rets) < min_n:
        raise InsufficientSignalsError(
            f"{len(rets)} signals < CPCV minimum ~{min_n} "
            f"(n_groups*(label_horizon+embargo+1)) — cannot compute DSR honestly"
        )
    paths = {}
    for split in cv.split(n_samples=len(rets), label_horizon=24):
        paths.setdefault(split.path_id, []).append(rets[split.test_idx])
    returns_per_path = [np.concatenate(chunks) for chunks in paths.values()]
    # Path-Sharpe distribution from the KERNEL (no hand-rolled Sharpe convention):
    dist = k["cpcv_sharpe_distribution"](returns_per_path)
    n_valid = int(dist["n_paths"])
    if n_valid >= 2:
        # configuration-history floor bound on top of the kernel variance
        dsr = float(k["deflated_sharpe_ratio"](
            rets, num_trials=max(num_trials, n_valid),
            trial_sharpes_variance=float(dist["std"]) ** 2,
        ))
    else:
        dsr = float("nan")
    wins = float(scored.loc[scored["signed_ret"] > 0, "signed_ret"].sum())
    losses = abs(float(scored.loc[scored["signed_ret"] < 0, "signed_ret"].sum()))
    return {
        "n_signals": int(len(scored)),
        "directional_accuracy": float(scored["hit"].mean()),
        "dsr": dsr,
        "n_cpcv_paths": n_valid,
        "num_trials_used": max(num_trials, n_valid),
        "pf_pooled": wins / losses if losses else float("inf"),
        "dropped_tail_signals": scored.attrs.get("dropped_tail", 0),
        "path_sharpe_variance_source": "cpcv_sharpe_distribution (kernel)",
    }
```

Note on the CPCV→DSR bridge: `cpcv_to_dsr` sets `num_trials = len(valid path Sharpes)` internally with no override, which cannot honor the `>= 8` floor — hence the explicit composition above using the same kernel pieces (`deflated_sharpe_ratio` + path-Sharpe variance). Record `num_trials_used` in the verdict config. `main()` with the two gates:

```python
def _check_gates(force: bool, evidence_dir: str = None, stamp_path: str = None) -> list:
    """Both paths parameterized so the gate is unit-testable against tmp dirs."""
    from killtests.report import EVIDENCE_DIR, latest_verdict

    evidence_dir = evidence_dir or EVIDENCE_DIR
    stamp_path = stamp_path or os.path.join(EVIDENCE_DIR, "golden-parity-stamp.json")
    caveats = []
    if latest_verdict("H3", out_dir=evidence_dir) is None:
        if not force:
            raise SystemExit("H4 refused: no H3 verdict on file (AUDIT.md:267 order). Use --force to override.")
        caveats.append("FORCED past missing H3 verdict")
    today = date.today().strftime("%Y%m%d")
    try:
        stamp = json.load(open(stamp_path))
    except (FileNotFoundError, json.JSONDecodeError):
        stamp = {}
    if not (stamp.get("date") == today and stamp.get("passed") is True):
        if not force:
            raise SystemExit(
                "H4 refused: golden parity stamp missing/stale. Run: "
                "python3 -m pytest tests/killtests/test_golden_parity.py -m golden --no-cov"
            )
        caveats.append("FORCED past missing/stale golden-parity stamp")
    return caveats
```

Gate unit tests (add to `tests/killtests/test_h4_information.py` — spec §7.4 "verdict-file gating"):

```python
def test_gate_refuses_without_h3_verdict(tmp_path):
    from killtests.h4_information import _check_gates
    with pytest.raises(SystemExit, match="no H3 verdict"):
        _check_gates(force=False, evidence_dir=str(tmp_path),
                     stamp_path=str(tmp_path / "stamp.json"))


def test_gate_refuses_stale_stamp(tmp_path):
    from killtests.h4_information import _check_gates
    from killtests.report import write_verdict
    write_verdict("H3", "REJECT", "c", {}, [], {}, {}, out_dir=str(tmp_path))
    (tmp_path / "stamp.json").write_text(json.dumps({"date": "19700101", "passed": True}))
    with pytest.raises(SystemExit, match="parity stamp"):
        _check_gates(force=False, evidence_dir=str(tmp_path),
                     stamp_path=str(tmp_path / "stamp.json"))


def test_gate_force_returns_caveats(tmp_path):
    from killtests.h4_information import _check_gates
    caveats = _check_gates(force=True, evidence_dir=str(tmp_path),
                           stamp_path=str(tmp_path / "stamp.json"))
    assert any("H3" in c for c in caveats) and any("stamp" in c for c in caveats)
```

`main()` flow: gates → load series CSV → `CandleStore` → `score_signals` (whole series; it groups per symbol internally) → `metrics = h4_stats(scored, num_trials=load_num_trials()["floor"])` (catch `InsufficientSignalsError` → REJECT-with-reason verdict, not a crash) → `metrics["non_hold_rate"] = float(series["ens_action"].notna().mean())` (spec §6 fire rate — computed here because `h4_stats` only sees the filtered frame) → verdict `ACCEPT` iff `directional_accuracy > 0.50 and dsr > 0.95` → `write_verdict("H4", ..., criterion="directional accuracy > 50% AND DSR > 0.95, num_trials >= 8", metrics=metrics, caveats=[gate caveats + standard set: per-signal 24h horizon overlap handled by time-sorted CPCV purge/embargo; fee-free by design (information test, not P&L); series generated by the offline replay whose parity stamp is required], config={..., "cpcv": "n_groups=10 k=2 embargo=0.01 label_horizon=24, time-sorted"}, input_hashes={series csv sha256, num_trials fixture sha256, backfill manifest sha256 — same `_sha` helper pattern as H3})`.

Run: `python3 -m pytest tests/killtests/test_h4_information.py -v --no-cov` → 8 PASS (5 stats + 3 gate).

- [ ] **Step 3: Commit**

```bash
git add backtesting/killtests/h4_information.py backtesting/killtests/fixtures/h4_num_trials.json tests/killtests/test_h4_information.py
git commit -m "feat(killtests): H4 information test with CPCV-DSR and order/parity gates"
```

---

### Task 13: Full H4 run, H3 secondary run, docs, closeout

**Files:**
- Output (committed): `.planning/evidence/killtests/H4-verdict-<date>.md/.json`, `signal-series.csv` metadata (row count + hash only — the CSV itself stays untracked if > 5 MB)
- Create: `backtesting/killtests/README.md`
- Modify: `AUDIT.md` (H4 row), `docs/superpowers/specs/2026-08-05-phase4-measurement-h3-h4-design.md` (two reality amendments)

- [ ] **Step 1: Generate the full signal series (long-running)**

```bash
python3 -m pytest tests/killtests/test_golden_parity.py -m golden --no-cov   # fresh stamp
python3 backtesting/killtests/offline_ensemble.py --data-dir backtesting/data \
  --out .planning/evidence/killtests/signal-series.csv
```
Expected: ~ (8760 − 300) × 5 ≈ 42k rows. This runs the full chain ~42k times — expect 1–4 hours; run in background and checkpoint per symbol if needed (implementation detail: the CLI writes per-symbol partial CSVs and concatenates, so an interrupt resumes at symbol granularity).

- [ ] **Step 2: Run H4**

```bash
python3 backtesting/killtests/h4_information.py \
  --series .planning/evidence/killtests/signal-series.csv --data-dir backtesting/data
```
Expected: verdict written. Given the audit's priors, REJECT is the likely outcome — that is a valid, useful result; do not tune anything to change it.

- [ ] **Step 3: H3 secondary run on regenerated entries (spec §5 staged item)**

Add `--entries-from-series <csv>` to `h3_atr_replay.py`: build synthetic `Entry` objects from series rows where `ens_action` is non-null (entry price = row `close`, quantity = `ens_position_size_pct * PAPER_INITIAL_BALANCE / close`, ts = `ts_ms`), run both ATR variants, and write verdict id `H3-secondary` (same criterion, caveat "regenerated entries — secondary evidence, never merged into the primary n=13 verdict"). Run it; commit the code delta and the verdict.

- [ ] **Step 4: AUDIT.md + spec amendments**

- `AUDIT.md` §7 H4 row: append `— tested <date>: see .planning/evidence/killtests/H4-verdict-<date>.md (<ACCEPT|REJECT>)`.
- Spec amendments (append an `## Amendments` section to the spec, do not rewrite history): (1) H3 resolution uses a purpose-built bracket walker copying `BacktestEngine`'s stop-first rule — the engine itself cannot pin entries to recorded fills; (2) `Trade.signal_indicators` does not exist in the live schema — entry confidence sourced from entry-trade `signal_confidence`; ORM model diverges from DB; (3) golden-sample "minimum 3 windows" is realized as 3 symbols at the live latest bar plus the full indicator-endpoint sweep — live TA has no as-of parameter, so windows cannot vary in time against the running stack.

- [ ] **Step 5: Write `backtesting/killtests/README.md`**

Short operator doc: what each module does, the three run commands (H3, series, H4), the gate chain (H3 verdict → golden stamp → H4), where verdicts land, and the re-run policy (any engine change that trips `test_preservation.py` invalidates standing verdicts — re-run after re-baselining).

- [ ] **Step 6: Full killtests suite green + commit**

```bash
python3 -m pytest tests/killtests/ -v --no-cov
git add backtesting/killtests/README.md backtesting/killtests/h3_atr_replay.py \
  .planning/evidence/killtests/ AUDIT.md docs/superpowers/specs/2026-08-05-phase4-measurement-h3-h4-design.md
git commit -m "docs(killtests): H4 verdict, H3 secondary run, README, spec amendments"
```

---

## Execution order & gates

```
Task 1 ─► Task 2 ─► Task 3 ─► Task 4 ─► Task 5 ─► Task 6 ─► Task 7 (H3 verdict)
                        │                                        │
                        └────────► Task 8 ─► Task 9 ─► Task 10 ─► Task 11 (parity stamp)
                                                                  │
                                                    Task 12 ◄─────┘  (gates: H3 verdict + stamp)
                                                    Task 13 (H4 run + closeout)
```

H3 (Tasks 4–7) and the offline-ensemble build (Tasks 8–11) are independent after Task 3 and may proceed in parallel. Task 12/13 require both.
