---
id: 260801-nui
slug: kill-switch-daily-roll
date: 2026-08-01
status: in-progress
---

# The "daily" loss breaker never rolls, so it halts the bot permanently

## Live symptom — the bot is not trading

```
$ docker logs crypto-bot-trading --since 30m | grep CRITICAL
CRITICAL - KILL SWITCH ACTIVE - Trading halted | Reason: daily_loss_limit   (x4)

$ curl -s :8005/api/v1/trading/status
kill_switch: is_active=True, reason=daily_loss_limit
metrics: daily_loss_pct 8.42, drawdown_pct 8.42,
         peak_balance 83.48, current_balance 76.46
thresholds: max_daily_loss_pct 5.0
```

## Root cause

`KillSwitchState.initial_balance` is set once by `initialize_balance()` at boot
(`auto_trader.py:853`) and **never rolled**. `update_metrics`
(`kill_switch.py:190-192`) then computes:

```python
daily_pnl = current_balance - self.state.initial_balance
self.state.current_daily_loss_pct = -(daily_pnl / self.state.initial_balance * 100)
```

That is **cumulative loss since process start**, not daily loss. There is no
day boundary anywhere in the class.

`AutoTrader.reset_daily_metrics()` exists and does the right thing — but it has
**zero callers**:

```
$ grep -rn "reset_daily_metrics()" services/trading-engine/ | grep -v "def "
app/auto_trader.py:4398:        self.kill_switch.reset_daily_metrics()   # the call INSIDE the method
```

Nothing schedules it. So the 5% *daily* breaker is really an all-time 5%
breaker: once cumulative loss since boot crosses 5%, the bot halts and cannot
recover on its own.

Two audit findings compound it:

- **DL-2** — `peak_balance 83.48` is the *fabricated* balance from the
  2026-07-31 14:26 restart. The breaker is measuring against a number that was
  invented by the restart-rebase bug. (Fixed in `22285ae`, not yet deployed.)
- **T-15** — the baseline is seeded from cash while readings are equity.

Corroborating detail: `daily_loss_pct` and `drawdown_pct` are both exactly
8.42. They are computed from different formulas and should not coincide — they
match because `initial_balance` and `peak_balance` are both frozen at boot.

## Fix

Give the kill switch a real UTC day window, matching the pattern
`RiskManager._roll_daily_window_if_needed` (`risk_manager.py:44-57`) already
uses in this codebase:

1. Track `daily_window_date` on the state.
2. Roll at the top of `update_metrics()`: on a new UTC date, rebase
   `initial_balance` to current equity, zero `current_daily_loss_pct` and the
   consecutive-loss streak, and re-anchor `peak_balance`.
3. On roll, clear an **automatic** daily-loss activation so the bot resumes —
   but never clear a `manual_override` halt. An operator halt must survive
   midnight (this is audit T-27, which `RiskManager` gets wrong; do not repeat
   it here).
4. Use UTC, matching `risk_manager`. `auto_trader.py:1416` uses local-time
   `.date()` for the trade counter — noted as T-22, out of scope here.

## Out of scope

- T-22 local-vs-UTC counter mismatch in `auto_trader`.
- DL-2 deployment (already fixed in `22285ae`, awaiting a trading-engine
  rebuild).
- Clearing the currently-stuck halt on the running container — that needs the
  rebuild, which is the operator's call.

## Verification

- Baseline `pytest services/trading-engine/tests/` = 37 failed / 1503 passed /
  795 skipped. Must not regress.
- New tests: no roll within a day; roll on UTC date change rebases and clears
  an automatic daily-loss halt; a manual halt survives the roll; the reproduction
  case (cumulative multi-day loss must not read as a single day's loss).
