---
type: concept
status: active
tags: [concept, trading, safety]
created: 2026-05-05
updated: 2026-07-30
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

**Security coupling (since 2026-07-29):** trading mode also gates API auth — control endpoints are open in local paper mode but **enforce auth in LIVE/prod** (`REQUIRE_API_AUTH` overrides; note the residual footgun: `REQUIRE_API_AUTH=false` on a LIVE host disables it). See [[../decisions/ADR-022-mode-gated-api-auth|ADR-022]]. Pre-LIVE checklist also requires restoring the ≤2% per-trade cap ([[../decisions/ADR-010-max-risk-per-trade-paper-bump|ADR-010]]) and a frontend login flow (none exists yet — tracked in [[../hot|hot.md]]).

## Related

- [[../modules/trading-engine|trading-engine]]
- [[../modules/bybit-connector|bybit-connector]]
- [[Auto-Trader]]
- [[../decisions/ADR-022-mode-gated-api-auth|ADR-022 mode-gated auth]]
