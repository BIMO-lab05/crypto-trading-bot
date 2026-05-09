---
type: concept
status: active
tags: [concept, trading, safety]
created: 2026-05-05
updated: 2026-05-05
---

# Trading Mode Flags

Four deliberate steps to LIVE. No confuse.

| Flag | Selects | Current |
|---|---|---|
| `BYBIT_TESTNET` | Price source (testnet=fake, mainnet=real) | `false` (mainnet) |
| `PAPER_TRADING_MODE` | Whether orders simulated | `true` |
| `TRADING_MODE` | Engine mode (paper/live) | paper |
| `LIVE_TRADING_ACK` | Required to boot LIVE | unset |

**Current state:** mainnet prices + simulated orders.

**To go LIVE (real money):**
1. `PAPER_TRADING_MODE=false`
2. `TRADING_MODE=LIVE`
3. Mainnet Bybit keys with trade permissions
4. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (added 2026-05; trading-engine refuses to boot in LIVE without it)

Catches env drift on cloud hosts.

## Related

- [[../modules/trading-engine|trading-engine]]
- [[../modules/bybit-connector|bybit-connector]]
- [[Auto-Trader]]
