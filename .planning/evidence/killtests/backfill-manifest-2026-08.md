# Backfill manifest

| file | rows | first | last | expected step (min) | gaps | sha256[:12] |
|---|---|---|---|---|---|---|
| BTCUSDT_15m_365d_bybit.csv | 35040 | 2025-08-05 20:15:00 | 2026-08-05 20:00:00 | 15 | 0 | 0bfacf90a58f |
| BTCUSDT_60m_365d_bybit.csv | 8760 | 2025-08-05 21:00:00 | 2026-08-05 20:00:00 | 60 | 0 | e0e6e9fc04ec |
| BTCUSDT_240m_365d_bybit.csv | 2190 | 2025-08-06 00:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 22747dc1e85d |
| BTCUSDT_1440m_365d_bybit.csv | 365 | 2025-08-06 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | 92a5d46f8671 |
| ETHUSDT_15m_365d_bybit.csv | 35040 | 2025-08-05 20:15:00 | 2026-08-05 20:00:00 | 15 | 0 | d5c8c72a664f |
| ETHUSDT_60m_365d_bybit.csv | 8760 | 2025-08-05 21:00:00 | 2026-08-05 20:00:00 | 60 | 0 | 35618f911123 |
| ETHUSDT_240m_365d_bybit.csv | 2190 | 2025-08-06 00:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 8119e5ceef40 |
| ETHUSDT_1440m_365d_bybit.csv | 365 | 2025-08-06 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | 2e8139dc9c97 |
| SOLUSDT_15m_365d_bybit.csv | 35040 | 2025-08-05 20:15:00 | 2026-08-05 20:00:00 | 15 | 0 | f0eb4592cbb3 |
| SOLUSDT_60m_365d_bybit.csv | 8760 | 2025-08-05 21:00:00 | 2026-08-05 20:00:00 | 60 | 0 | a4895fb39f30 |
| SOLUSDT_240m_365d_bybit.csv | 2190 | 2025-08-06 00:00:00 | 2026-08-05 20:00:00 | 240 | 0 | 180c107d9ce1 |
| SOLUSDT_1440m_365d_bybit.csv | 365 | 2025-08-06 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | 6ba6b28357d2 |
| BNBUSDT_15m_365d_bybit.csv | 35040 | 2025-08-05 20:15:00 | 2026-08-05 20:00:00 | 15 | 0 | 36b7c1bf1e31 |
| BNBUSDT_60m_365d_bybit.csv | 8760 | 2025-08-05 21:00:00 | 2026-08-05 20:00:00 | 60 | 0 | 96f1e712bc58 |
| BNBUSDT_240m_365d_bybit.csv | 2190 | 2025-08-06 00:00:00 | 2026-08-05 20:00:00 | 240 | 0 | d89925339644 |
| BNBUSDT_1440m_365d_bybit.csv | 365 | 2025-08-06 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | bbcb03b46a90 |
| ADAUSDT_15m_365d_bybit.csv | 35040 | 2025-08-05 20:15:00 | 2026-08-05 20:00:00 | 15 | 0 | 6d4d0eedda14 |
| ADAUSDT_60m_365d_bybit.csv | 8760 | 2025-08-05 21:00:00 | 2026-08-05 20:00:00 | 60 | 0 | 1c76fcdcf759 |
| ADAUSDT_240m_365d_bybit.csv | 2190 | 2025-08-06 00:00:00 | 2026-08-05 20:00:00 | 240 | 0 | a4c50f2c0776 |
| ADAUSDT_1440m_365d_bybit.csv | 365 | 2025-08-06 00:00:00 | 2026-08-05 00:00:00 | 1440 | 0 | ce65c72e01a8 |

## Mainnet provenance check (pre-backfill, 2026-08-05)

Confirmed the connector was on mainnet before any download ran (`is_mainnet=True` is stamped unconditionally by the CSV writer, so this check is the only real provenance guard):

- `docker exec crypto-bot-bybit printenv BYBIT_TESTNET` -> `false`
- Log line from the running container: `"Initialized Bybit REST client (testnet=False, base_url=https://api.bybit.com)"` (most recent occurrence timestamped `2026-08-05T13:41:23`, container `crypto-bot-bybit` — note: this is the actual container name; the brief's `crypto-bot-bybit-connector` does not exist in this deployment)

## 15m depth probe (Step 2)

Bybit serves full 1000-row depth at t-365d for 15m (`15m rows at t-365d: 1000`) — proceeded with `--days 365` for all four intervals, no bisection needed.

Note: the probe initially returned `0` with an internal parsing error, not a clean "no data" signal. Root-caused to a pre-existing double-unwrap bug in `backtesting/bybit_data_fetcher.py::fetch_klines` (predates this task, introduced in commit `57b0d72`) that discarded every real kline response. Fixed in commit `e6b08e8` before re-running this probe; see that commit message and the Task 2 report for detail.
