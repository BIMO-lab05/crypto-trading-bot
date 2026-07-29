---
type: decision
status: accepted
date: 2026-07-28
context: "TA computed indicators on testnet-polluted, partial, and structurally-invalid candles; pre-flip rows were mis-tagged mainnet"
deciders: [operator]
tags: [decision, adr, technical-analysis, data-integrity]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-021: TA data-integrity gate (mainnet-only + candle validation) and testnet-pollution DB repair

## Context

Technical-analysis fetched klines from market-data and computed indicators on whatever came back. Two problems:

1. **Garbage in.** Testnet-polluted prints, structurally invalid candles (low > high, non-positive OHLC), still-forming last candles, and minute-vs-letter interval mismatches (a `1440` lookup silently returned 0 rows because daily candles are stored under `"D"`) all fed straight into indicators.
2. **Mis-tagged history.** The 2026-04-25 testnet→mainnet flip left pre-flip testnet candles in the shared tables; when `is_mainnet` was added (2026-04-29) all pre-existing rows defaulted to `TRUE`, so testnet rows read as mainnet.

## Decision

**Fetcher gate** (`technical-analysis/app/fetcher.py`):

- **Mainnet-only reads.** `get_klines` sends `mainnet_only=true` explicitly (defensive against a future default flip). `fetcher.py:104-112`.
- **Interval normalization.** `1440/10080/43200 → D/W/M` before querying so DB lookups don't silently return 0 rows. `fetcher.py:21-47`.
- **Candle validation** in `get_klines_as_dataframe`: drop structurally invalid rows (low > high, OHLC ≤ 0); drop corrupt jumps (`|ln(close/prev)| > 0.35`, ~35 %/bar); drop the still-forming last candle (`ts + interval > now`); and **refuse to compute** if fewer than `MIN_VALID_ROWS = 30` valid candles remain (raises `ValueError` rather than returning garbage). `fetcher.py:184-239`.

**DB repair** (`scripts/repair_testnet_pollution.sql`, run via `scripts/repair_testnet_pollution.sh`):

- Idempotent, transactional. Demotes to `is_mainnet=false`: (a) all rows before the conservative cutoff `2026-04-26T00:00Z` (epoch-ms `1777161600000`); (b) per-symbol price outliers > 5× above / below the mainnet-only median close. Rows are demoted, not deleted, so `mainnet_only=false` forensic reads still work. Tickers handled only if an `is_mainnet` column exists.

## Consequences

- Indicators compute on clean, complete, mainnet-only data or fail loudly — no more silent garbage output.
- The historical testnet pollution called out in [[ADR-006-mainnet-prices-paper-orders]] is repaired non-destructively; the old "wipe klines/tickers" guidance is superseded.
- A too-thin symbol (< 30 valid candles) raises instead of emitting a noise signal.

## Related

- `services/technical-analysis/app/fetcher.py:21-247`
- `scripts/repair_testnet_pollution.sql`
- `services/market-data-service/app/models.py` (schema: `klines.timestamp` BIGINT ms, `is_mainnet` BOOLEAN)
- [[ADR-006-mainnet-prices-paper-orders]]
- [[../concepts/Validated-Symbols]]
- [[../flows/Signal-Pipeline]]
