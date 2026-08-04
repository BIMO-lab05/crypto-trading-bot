---
type: decision
status: accepted
date: 2026-07-28
context: "kill switch false-tripped on every position open and its consecutive-loss breaker was structurally unreachable; daily-loss cap never reset"
deciders: [operator]
tags: [decision, adr, risk, circuit-breaker, kill-switch]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-019: kill switch fed equity (not cash), streak counts only on closes, daily-loss breaker auto-rolls per UTC day

## Context

Three defects in the trading-engine safety layer were found in the 2026-07-28 audit:

1. **Kill switch fed raw cash.** `KillSwitch.update_metrics(current_balance=…)` was called with cash. Opening a position deducts posted margin, so cash instantly dropped — the switch read that drop as a "daily loss" and false-tripped the moment any position opened.
2. **Consecutive-loss streak reset on every open.** `update_metrics` was called on position *open* with `was_loss=False`, which reset the streak. Since opens outnumber closes, the 5-consecutive-losses breaker was structurally unreachable while the bot kept re-entering.
3. **"Daily" loss cap never reset.** `RiskManager.reset_daily_pnl()` had no caller, so `daily_pnl` accumulated for the whole process lifetime — the "daily" loss limit was really a since-boot limit.

## Decision

- **Feed EQUITY, not cash.** Both the open-path and close-path call sites now pass `get_total_equity()` (cash + unrealized P&L). `auto_trader.py:2088-2103` (open), `auto_trader.py:2938-2949` (close).
- **Streak accounting only on trade CLOSES.** `update_metrics` gained an `is_trade_close` flag; the consecutive-loss counter only increments/resets when `is_trade_close=True`. Opens pass the default `False` and no longer touch the streak. `kill_switch.py:151-204`, close site `auto_trader.py:2943-2948`.
- **Daily-loss breaker auto-rolls per UTC day.** `RiskManager` tracks `_daily_pnl_date`; `_roll_daily_window_if_needed()` resets `daily_pnl` to 0 when the UTC calendar day changes, and is called from `update_daily_pnl` and `should_halt_trading`. A daily-loss halt therefore clears with the new UTC day. `risk_manager.py:32-85`.

## Consequences

- Opening a position no longer looks like a loss; the kill switch stops false-tripping on normal operation.
- The 5-consecutive-losses breaker is now reachable (only real closing losses count).
- The daily-loss cap is genuinely daily; a UTC-day boundary lifts a daily-loss halt without a manual reset (a *manual* halt still persists).
- Correct equity depends on the accounting fixes in [[ADR-018-paper-engine-accounting-overhaul]].

## Related

- `services/trading-engine/app/trading_enhancements/kill_switch.py:151-248`
- `services/trading-engine/app/risk_manager.py:27-95`
- `services/trading-engine/app/auto_trader.py:2088-2103, 2938-2949`
- [[ADR-017-risk-metrics-paper-mode-alignment]]
- [[ADR-005-emergency-stop-file-flag]]
- [[../flows/Emergency-Stop]]
