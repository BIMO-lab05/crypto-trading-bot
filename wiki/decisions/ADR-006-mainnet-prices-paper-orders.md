---
type: decision
status: accepted
date: 2026-04-25
context: "paper trading needs real market signal"
deciders: []
tags: [decision, adr, trading]
created: 2026-05-05
updated: 2026-07-29
---

# ADR-006: mainnet prices + paper-simulated orders (current dual-mode contract)

## Context

Pure-testnet mode produced unrealistic price action (low liquidity, occasional gaps). Needed real price signal while still avoiding real-money risk.

## Decision

- `BYBIT_TESTNET=false` — pull real prices from Bybit mainnet
- `PAPER_TRADING_MODE=true` — simulate orders internally; no exchange order calls
- TimescaleDB stores mainnet prices

## Consequences

- Realistic backtests / paper P&L
- ⚠️ TimescaleDB had mixed testnet/mainnet history before 2026-04-25 mid-day. **Repaired 2026-07-28** — `scripts/repair_testnet_pollution.sql` demotes pre-cutoff and >5×-outlier rows to `is_mainnet=false`, and TA now reads mainnet-only with candle validation. See [[ADR-021-ta-data-integrity-gate]]. (Historically the guidance here was to wipe `klines` / `tickers` before historical analysis; the repair script is now the preferred, non-destructive fix.)
- Live forward-going data clean.

## Related

- [[../concepts/Trading-Mode-Flags]]
- [[../modules/market-data-service]]
- [[ADR-004-paper-trading-default]]
- [[ADR-021-ta-data-integrity-gate]] (testnet-pollution repair + mainnet-only TA gate)
