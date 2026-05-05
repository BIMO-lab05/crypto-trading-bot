---
type: concept
status: active
tags: [concept, risk]
created: 2026-05-05
updated: 2026-05-05
---

# Risk Model

Hard caps wired into [[../modules/trading-engine|trading-engine]]. No relax without explicit approval.

- **Per-trade cap:** 2% of capital
- **Daily-loss circuit-breaker:** 5%
- **Max hold:** 48h (Jan 2026 fix, commit `380a674`)
- **SHORT enforcement, stop-loss limit-orders** (same commit)

## Related

- [[../modules/risk-metrics-service|risk-metrics-service]]
- [[../modules/trading-engine|trading-engine]]
- [[Trading-Mode-Flags]]
