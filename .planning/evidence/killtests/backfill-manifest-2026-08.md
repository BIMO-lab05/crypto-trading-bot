# Backfill manifest

| file | rows | first | last | expected step (min) | gaps | sha256[:12] |
|---|---|---|---|---|---|---|
| BTCUSDT_15m_365d_bybit.csv | 35039 | 2025-08-06 03:15:00 | 2026-08-06 02:45:00 | 15 | 0 | 95c6c8e2791c |
| BTCUSDT_60m_365d_bybit.csv | 8759 | 2025-08-06 04:00:00 | 2026-08-06 02:00:00 | 60 | 0 | 8c9137e68266 |
| BTCUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 04:00:00 | 2026-08-05 20:00:00 | 240 | 0 | d7ab3cac146b |
| BTCUSDT_1440m_365d_bybit.csv | 364 | 2025-08-07 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | dd45dddb860d |
| ETHUSDT_15m_365d_bybit.csv | 35039 | 2025-08-06 03:15:00 | 2026-08-06 02:45:00 | 15 | 0 | 5ae6308ff28a |
| ETHUSDT_60m_365d_bybit.csv | 8759 | 2025-08-06 04:00:00 | 2026-08-06 02:00:00 | 60 | 0 | 437aa7661a1f |
| ETHUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 04:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 9abca3eaf3ff |
| ETHUSDT_1440m_365d_bybit.csv | 364 | 2025-08-07 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | 53c6d827aafd |
| SOLUSDT_15m_365d_bybit.csv | 35039 | 2025-08-06 03:15:00 | 2026-08-06 02:45:00 | 15 | 0 | f52dbdc0d8f5 |
| SOLUSDT_60m_365d_bybit.csv | 8759 | 2025-08-06 04:00:00 | 2026-08-06 02:00:00 | 60 | 0 | 71a8b981fdf5 |
| SOLUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 04:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 2fd0bd0751cc |
| SOLUSDT_1440m_365d_bybit.csv | 364 | 2025-08-07 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | 0f181a3b9fa2 |
| BNBUSDT_15m_365d_bybit.csv | 35039 | 2025-08-06 03:15:00 | 2026-08-06 02:45:00 | 15 | 0 | 0360ebb2bd8c |
| BNBUSDT_60m_365d_bybit.csv | 8759 | 2025-08-06 04:00:00 | 2026-08-06 02:00:00 | 60 | 0 | 2c0541877f36 |
| BNBUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 04:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 883ee96df7e4 |
| BNBUSDT_1440m_365d_bybit.csv | 364 | 2025-08-07 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | ba579e72a29d |
| ADAUSDT_15m_365d_bybit.csv | 35039 | 2025-08-06 03:15:00 | 2026-08-06 02:45:00 | 15 | 0 | 72e1836f3cec |
| ADAUSDT_60m_365d_bybit.csv | 8759 | 2025-08-06 04:00:00 | 2026-08-06 02:00:00 | 60 | 0 | 9e061c1b3eaf |
| ADAUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 04:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 58063816a0e0 |
| ADAUSDT_1440m_365d_bybit.csv | 364 | 2025-08-07 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | d6a6c01fabc1 |

## Mainnet provenance check (pre-backfill, 2026-08-05)

Confirmed the connector was on mainnet before any download ran (`is_mainnet=True` is stamped unconditionally by the CSV writer, so this check is the only real provenance guard):

- `docker exec crypto-bot-bybit printenv BYBIT_TESTNET` -> `false`
- Log line from the running container: `"Initialized Bybit REST client (testnet=False, base_url=https://api.bybit.com)"` (most recent occurrence timestamped `2026-08-05T13:41:23`, container `crypto-bot-bybit` — note: this is the actual container name; the brief's `crypto-bot-bybit-connector` does not exist in this deployment)

## 15m depth probe (Step 2)

Bybit serves full 1000-row depth at t-365d for 15m (`15m rows at t-365d: 1000`) — proceeded with `--days 365` for all four intervals, no bisection needed.

Note: the probe initially returned `0` with an internal parsing error, not a clean "no data" signal. Root-caused to a pre-existing double-unwrap bug in `backtesting/bybit_data_fetcher.py::fetch_klines` (predates this task, introduced in commit `57b0d72`) that discarded every real kline response. Fixed in commit `e6b08e8` before re-running this probe; see that commit message and the Task 2 report for detail.

## Manifest refresh log

2026-08-06: 9 files (BTC/SOL/ADA × 15m/60m/240m) refreshed by Task 11 golden-parity backfill; table regenerated to match disk.

2026-08-06 (Task 13): all 20 files (5 symbols × 4 intervals) refreshed ahead of the H4 full-series run — the golden-parity CSVs had lagged live data again by the time this task started (same staleness pattern Task 11 hit), so the whole dataset was re-pulled for coherence rather than patching individual symbols. `--interval 1440` was tried first and silently returned 0 candles for all 5 symbols (confirmed harmless — the fetcher only writes a file when the downloaded frame is non-empty, so the stale pre-existing `*_1440m_365d_bybit.csv` files were untouched by the failed attempt); Bybit's v5 kline endpoint does not recognize `1440` as an interval value, only `D` — re-ran with `--interval D --days 365` per the Task 2 precedent, then renamed `{sym}_Dm_365d_bybit.csv` -> `{sym}_1440m_365d_bybit.csv` for all 5 symbols. All 20 files: 0 gaps, coherent `is_mainnet=True` fresh mainnet pull, forming trailing candle already dropped by the fetcher (row counts 35039/8759/2189/364 match the trimmed expectation from commit `4f92643`).
