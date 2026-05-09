---
type: decision
status: accepted
date: 2026-05
context: "operational safety"
deciders: []
tags: [decision, adr, safety]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-004: paper-trading is repo default; LIVE requires 4-flag alignment

## Context

Single boolean would let env drift on cloud hosts silently flip the system to real-money trading.

## Decision

LIVE requires **all four** flags aligned:

1. `PAPER_TRADING_MODE=false`
2. `TRADING_MODE=LIVE`
3. Mainnet Bybit keys with trade permissions
4. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (added 2026-05; trading-engine refuses to boot in LIVE without it)

`BYBIT_TESTNET` is orthogonal — selects price source (testnet=fake, mainnet=real).

## Consequences

- Current state: mainnet prices + simulated orders ([[ADR-006-mainnet-prices-paper-orders]])
- Cloud env drift can no longer silently enable real trading
- Bootstrap order in trading-engine asserts `LIVE_TRADING_ACK` in LIVE mode

## Related

- [[../concepts/Trading-Mode-Flags]]
