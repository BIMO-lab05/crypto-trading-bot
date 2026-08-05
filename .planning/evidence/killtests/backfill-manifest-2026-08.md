# Backfill manifest

| file | rows | first | last | expected step (min) | gaps | sha256[:12] |
|---|---|---|---|---|---|---|
| BTCUSDT_15m_365d_bybit.csv | 35039 | 2025-08-05 20:15:00 | 2026-08-05 19:45:00 | 15 | 0 | b149670e3ee3 |
| BTCUSDT_60m_365d_bybit.csv | 8759 | 2025-08-05 21:00:00 | 2026-08-05 19:00:00 | 60 | 0 | ddf3dfcb47a1 |
| BTCUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 00:00:00 | 2026-08-05 16:00:00 | 240 | 0 | ce48765376a9 |
| BTCUSDT_1440m_365d_bybit.csv | 364 | 2025-08-06 00:00:00 | 2026-08-04 00:00:00 | 1440 | 0 | ea3da0d848f1 |
| ETHUSDT_15m_365d_bybit.csv | 35039 | 2025-08-05 20:15:00 | 2026-08-05 19:45:00 | 15 | 0 | 49a9d6b05db5 |
| ETHUSDT_60m_365d_bybit.csv | 8759 | 2025-08-05 21:00:00 | 2026-08-05 19:00:00 | 60 | 0 | a78a1d5f06f3 |
| ETHUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 00:00:00 | 2026-08-05 16:00:00 | 240 | 0 | c153c579f22b |
| ETHUSDT_1440m_365d_bybit.csv | 364 | 2025-08-06 00:00:00 | 2026-08-04 00:00:00 | 1440 | 0 | 1904f90be1e2 |
| SOLUSDT_15m_365d_bybit.csv | 35039 | 2025-08-05 20:15:00 | 2026-08-05 19:45:00 | 15 | 0 | 4710d9b450be |
| SOLUSDT_60m_365d_bybit.csv | 8759 | 2025-08-05 21:00:00 | 2026-08-05 19:00:00 | 60 | 0 | 4cf2c00a590b |
| SOLUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 00:00:00 | 2026-08-05 16:00:00 | 240 | 0 | c2fe0eedd4ea |
| SOLUSDT_1440m_365d_bybit.csv | 364 | 2025-08-06 00:00:00 | 2026-08-04 00:00:00 | 1440 | 0 | 0ce6c21d83eb |
| BNBUSDT_15m_365d_bybit.csv | 35039 | 2025-08-05 20:15:00 | 2026-08-05 19:45:00 | 15 | 0 | 9bc6ee34fde8 |
| BNBUSDT_60m_365d_bybit.csv | 8759 | 2025-08-05 21:00:00 | 2026-08-05 19:00:00 | 60 | 0 | ac64a813eee5 |
| BNBUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 00:00:00 | 2026-08-05 16:00:00 | 240 | 0 | 25d452bd7700 |
| BNBUSDT_1440m_365d_bybit.csv | 364 | 2025-08-06 00:00:00 | 2026-08-04 00:00:00 | 1440 | 0 | aa0956777fa6 |
| ADAUSDT_15m_365d_bybit.csv | 35039 | 2025-08-05 20:15:00 | 2026-08-05 19:45:00 | 15 | 0 | 1db215c289aa |
| ADAUSDT_60m_365d_bybit.csv | 8759 | 2025-08-05 21:00:00 | 2026-08-05 19:00:00 | 60 | 0 | 30b705f915f0 |
| ADAUSDT_240m_365d_bybit.csv | 2189 | 2025-08-06 00:00:00 | 2026-08-05 16:00:00 | 240 | 0 | 14bd42320bba |
| ADAUSDT_1440m_365d_bybit.csv | 364 | 2025-08-06 00:00:00 | 2026-08-04 00:00:00 | 1440 | 0 | 2a3999fa7c35 |

## Mainnet provenance check (pre-backfill, 2026-08-05)

Confirmed the connector was on mainnet before any download ran (`is_mainnet=True` is stamped unconditionally by the CSV writer, so this check is the only real provenance guard):

- `docker exec crypto-bot-bybit printenv BYBIT_TESTNET` -> `false`
- Log line from the running container: `"Initialized Bybit REST client (testnet=False, base_url=https://api.bybit.com)"` (most recent occurrence timestamped `2026-08-05T13:41:23`, container `crypto-bot-bybit` — note: this is the actual container name; the brief's `crypto-bot-bybit-connector` does not exist in this deployment)

## 15m depth probe (Step 2)

Bybit serves full 1000-row depth at t-365d for 15m (`15m rows at t-365d: 1000`) — proceeded with `--days 365` for all four intervals, no bisection needed.

Note: the probe initially returned `0` with an internal parsing error, not a clean "no data" signal. Root-caused to a pre-existing double-unwrap bug in `backtesting/bybit_data_fetcher.py::fetch_klines` (predates this task, introduced in commit `57b0d72`) that discarded every real kline response. Fixed in commit `e6b08e8` before re-running this probe; see that commit message and the Task 2 report for detail.
