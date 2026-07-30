---
type: concept
status: active
tags: [concept, symbols]
created: 2026-05-05
updated: 2026-07-30
---

# Validated Symbols

5 active as of 2026-05-03: **BTC, ETH, SOL, BNB, ADA**.

- XRP / DOGE excluded by paper-trading data — no silent re-add
- BTC + ETH re-added 2026-05-03 per operator request
- trading-engine `trading_symbols` already had them; market-data `default_symbols` did not until 2026-05-03
- **Re-audited 2026-05-23** (Phase 16 AUDIT-01): 74 requirements satisfied / 7 drift / 0 missing — the 5-symbol set stands on this re-audit, not on the (measurement-corrupted) 2025 win-rate numbers
- **Two universes**: market-data-service ingests 14 symbols for research + cross-asset lookback; trading-engine takes positions only in the 5 above

## Allocation caveat (2026-07-30)

`trading-engine/app/config.py` weights positions per symbol ("BACKTEST-OPTIMIZED ALLOCATION 2026-01-19": SOL 30%, BTC 25%, rest ADA/BNB/ETH). Those weights were fit on **pre-ADR-018/021 data** (broken accounting + testnet pollution) — re-derive on clean paper data before trusting them. See [[../sources/Archive-Distillation-2026-07-30|Archive Distillation]].

## Related

- [[../modules/market-data-service|market-data-service]]
- [[../modules/trading-engine|trading-engine]]
