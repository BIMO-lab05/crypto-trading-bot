---
type: concept
status: active
tags: [concept, risk]
created: 2026-05-05
updated: 2026-07-29
---

# Risk Model

Caps wired into [[../modules/trading-engine|trading-engine]]. No relax without explicit approval.

- **Per-trade cap:** `max_risk_per_trade` fraction of balance — default **0.10 (10%)** in PAPER (per ADR-010; compose `MAX_RISK_PER_TRADE=0.10`), with a **hard 2% floor in LIVE** (`min(cap, 0.02)` when `TRADING_MODE=LIVE`). The cap **CLAMPS** the notional to `cap_value` — it no longer rejects the trade. Enforced on BOTH the default/standard path and the research/hybrid path (`auto_trader.py:1989-2022`, `:3782-3796`). Compose also sets `DEFAULT_LEVERAGE=10.0`.
- **Daily-loss circuit-breaker:** **12%** (`max_daily_loss_pct`) since 2026-08-03 — see [[../decisions/ADR-028-daily-loss-breaker-reconciliation|ADR-028]]. Was 5%, but against the ADR-010 per-trade cap of 10% ($10 on a $100 balance) a 5% limit ($5) tripped on the **first** full loss, so the breaker measured one trade rather than a day. **This allows more daily loss, not less** — a coherence fix. Auto-rolls-over per UTC day (`risk_manager.py:44-88`); previously `reset_daily_pnl` had no caller, so it was effectively a lifetime cap that only reset on restart.
- **Units are a live trap:** `max_risk_per_trade` is a **fraction** (`0.10`); `max_daily_loss_pct` and `max_position_size_pct` are **percents** (`12.0`, `10.0`). Comparing across them without normalizing yields a check that silently never fires — this shipped once.
- **Kill switch** is fed **EQUITY** (cash + unrealized), not cash — opening a position no longer false-triggers a "daily loss". Consecutive-loss streak only updates on trade **CLOSES** (`is_trade_close=True`); previously every open reset it, making the 5-loss breaker unreachable (`kill_switch.py:151-226`, fed from `auto_trader.py:2094-2103`, `:2941-2949`).
- **Side gates** (`allowed_trade_sides`, `short_trading_enabled`, `short_min_confidence`) are now enforced on the default/standard path too (`auto_trader.py:3753-3780`), not only research/hybrid.
- **Max hold:** 48h (Jan 2026 fix, commit `380a674`)
- **SHORT enforcement, stop-loss limit-orders** (same commit)

## Related

- [[../modules/risk-metrics-service|risk-metrics-service]]
- [[../modules/trading-engine|trading-engine]]
- [[Trading-Mode-Flags]]

## Corrections 2026-07-29

- "Per-trade cap: 2%" was stale: default is now 10% in PAPER, 2% hard floor only in LIVE, and the gate **clamps** rather than rejecting (verified `config.py:321-332`, `auto_trader.py:1989-2022` / `:3782-3796`).
- Daily-loss cap now genuinely daily (UTC rollover) rather than a lifetime cap; kill switch fed equity + streak-on-close; side gates added to the default path. All verified against the cited files.
