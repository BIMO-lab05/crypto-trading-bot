# Why the funnel emits zero signals — measured root cause, 2026-08-22

Investigation of the live signal funnel showing `Ensemble signal emitted 0/146`.
Every number below is measured from the running engine, not inferred.
Sample: **2,820 evaluations** (564 cycles x 5 symbols), 2026-08-21 22:03 → 2026-08-22 14:4x UTC (~16 h).

**Headline: this is not a threshold problem. Do not lower thresholds.**
The ensemble averages a structurally-bullish indicator group against a structurally-bearish
one and gets ~zero. The system already contains the component designed to fix this — the
hybrid router — and it is running in advisory mode, observing instead of deciding.

---

## 1. What the funnel's own numbers localise

Upstream stages pass at 81–100%. The collapse is entirely at one step:

| Stage | Pass |
|---|---|
| Aggregator confidence floor | 432/533 · 81.1% |
| Routing decision made | 146/146 · 100% |
| **Ensemble signal emitted** | **0/146 · 0%** |

Decomposing the ensemble's three early-returns over live traffic: **100% are
`no legs fired`**. Never `only N legs agree`, never `weighted score below threshold`.
So the ⅓-weight confidence ceiling — the usual suspect, and the thing that killed
isolation run `20260821T165830Z` at 0.2761 — is **not currently binding**. It sits behind
the real blocker.

## 2. Why no legs fire

`MultiStrategyEnsemble.generate_signal` has three legs. `LEG_MULTI`
(`multi_strategy_ensemble.py:313`) is guarded by:

```python
if (aggregator_signal.action != SignalAction.HOLD
        and aggregator_signal.confidence > 0):
```

`aggregator_signal` arrives from `get_trading_signal_multi_timeframe`
(`signal_aggregator.py:956`), which returns **`primary_signal` — the 60m signal — with only
its confidence rescaled**. Measured 60m action distribution:

| Timeframe | Actions (2,820 evals) |
|---|---|
| 15m | HOLD dominant, **SELL 13** |
| **60m (primary)** | **HOLD 100%, SELL 0** |
| 240m | **BUY 2,408 · HOLD 412 · SELL 0** |

60m is HOLD in every measured cycle → `LEG_MULTI` can never fire → legs 1 and 3 rarely fire
alone → `no legs fired` → `return None` → zero signals. That is the entire 0/146.

### 2a. `consensus_action` is dead code

`multi_timeframe.py:139` computes `consensus_action` via `_calculate_weighted_consensus`.
Its **only** consumer in the engine is `signal_aggregator.py:1043`, which writes it into a
metadata dict. It is never read to make a decision. The dataclass carries both
`primary_action` and `consensus_action`; only the former influences anything.

**But wiring it up does not fix the funnel.** Recomputed over 90 complete cycles using the
shipped weights (15m=0.20, 60m=0.50, 240m=0.30) and shipped ±0.2 threshold:

```
consensus_action if applied:  BUY 0 · SELL 0 · HOLD 90
consensus score: min -0.048  p50 +0.062  p90 +0.106  max +0.106
|score| >= 0.2 : 0/90
```

Max consensus is **+0.106 against a ±0.2 threshold**. Applying `consensus_action` removes
dead code and changes no observable behaviour. It is a correctness fix, not the repair.

## 3. The actual root cause: the voting set cancels itself out

Per-timeframe scores show the shape of the problem:

```
 15m score  min -0.230  p50 -0.070  max +0.040
 60m score  min -0.120  p50 -0.000  max +0.040     <- pinned at zero
240m score  min +0.100  p50 +0.300  max +0.410     <- never negative
```

The 60m median is **-0.000**. That is not a market observation; it is cancellation.
Indicator votes across the full log (9 voters; `TREND_FILTER`=GATEKEEPER,
`VOLUME_CONFIRMATION`=VALIDATOR and ATR=advisory do not vote):

| Indicator | Role | BUY | SELL | HOLD | Bias |
|---|---|---|---|---|---|
| ICHIMOKU | MULTI_ASPECT_TREND (**1.3x weight**) | 8,098 | 30 | 194 | **97.3% BUY** |
| EMA | VOTER | 7,430 | 892 | — | 89% BUY |
| SMA | VOTER | 7,155 | 1,166 | — | 86% BUY |
| ADX | TREND_GATE | 6,482 | 815 | 1,024 | 78% BUY |
| MACD | VOTER | 5,693 | 2,629 | — | 68% BUY |
| SQZMOM_ENHANCED | BREAKOUT_DETECTOR (1.4x) | 4,637 | 758 | 2,927 | 56% BUY |
| STOCHASTIC | MOMENTUM | 2,073 | 2,782 | 3,465 | balanced |
| **RSI** | VOTER | **189** | **5,846** | 2,287 | **70% SELL** |
| **BOLLINGER_BANDS** | VOTER | **404** | **6,125** | 1,792 | **74% SELL** |

The trend-following voters (Ichimoku, EMA, SMA, ADX, MACD) are pinned **bullish**. The
mean-reversion voters (RSI, Bollinger) are pinned **bearish**. Weighted together they sum
to approximately zero, every cycle, on every symbol.

**This is not a bug in any single indicator — probed directly, not assumed.** The 97%/74%
one-sidedness of RSI and Bollinger looks like a stuck computation, so it was tested against
the live TA service before drawing any conclusion:

```
RSI BTCUSDT   15m  rsi=45.68  signal=HOLD      <- mid-range, correctly neutral
              60m  rsi=47.92  signal=HOLD
              240m rsi=76.71  signal=SELL      <- genuinely overbought

RSI 60m across all 5 symbols: 43.72 - 52.43, every one HOLD

TREND_FILTER BTCUSDT 240m: fast_ema=69,304.79  slow_ema=65,526.98
                           spread=+5.77%  trend=BULLISH  signal=BUY
             ADAUSDT 240m: spread=+5.84%  trend=BULLISH  signal=BUY
```

RSI is not inverted or miscalibrated: it reads mid-range at 15m/60m and returns HOLD there,
and only says SELL at 240m where the market is actually overbought at 76.7. `TREND_FILTER`
is not stuck: a +5.8% fast/slow EMA separation is a real, strong uptrend. The engine relays
the TA verdict verbatim (`signal=SignalAction(data["signal"])`, `signal_aggregator.py:91`) —
no inversion in transit.

So each indicator is correct. In a sustained uptrend, trend-followers say *buy the trend*
and oscillators say *overbought, fade it* — **both readings are right at the same time**.
Averaging the two families with fixed weights guarantees cancellation precisely when the
market trends hardest. The aggregate score of ~0 is an artifact of the ensemble's
composition, not a reading of the market, and **not something an indicator-level bug fix
can repair.**

`ICHIMOKU` is worth separate note: it carries the largest weight (1.3x), is pinned at
`conf=1.00` in **5,445 of 8,322** votes (65%), and is 97.3% one-sided. A voter at maximum
confidence two-thirds of the time is not expressing conviction, it is saturated.

## 4. The system already contains the fix, switched off

The market is unambiguously trending. From the funnel's own routing telemetry:

```
Routing branches:  trend 146 · mean-rev 0
ADX min / median / max:  28.68 / 33.52 / 50.41      (all 146 decisions > 25)
```

And from live logs:

```
[HYBRID][ADVISORY] ADAUSDT regime=TRENDING adx=35.55 source=adx
                   (ensemble executes; router observing)
```

The hybrid router classifies the regime correctly on **146/146** decisions and would route
to a trend strategy. It does not execute — the ensemble does, and the ensemble is the thing
that cancels. The component designed for exactly this failure is built, running, correct,
and advisory-only.

Per `[[project_routing_repair_2026-08-21]]` the router was deliberately left advisory
pending Phase-3 recalibration. That decision is still standing and is **not** overridden by
this document.

## 5. What must NOT be done

- **Do not lower `min_signal_confidence`, the ±0.2 consensus threshold, or the 0.15 vote
  threshold.** Phase-3 tested threshold changes and returned NO CHANGE — IS/OOS rankings
  invert. Lowering thresholds here would manufacture trades out of a signal that is
  provably ~zero, which is worse than no trades.
- **Do not reweight toward the 240m timeframe.** It is the only timeframe with apparent
  conviction, but it produced **2,408 BUY and 0 SELL in 16 hours across 5 symbols**. That is
  a stuck-bullish read, not an informative one. Promoting it would hard-wire a permanent
  long bias.
- **Do not "fix" RSI or Bollinger to agree with the trend voters.** They are behaving
  correctly for what they measure.

## 6. Candidate repairs, in dependency order

**The discriminator has been run.** Because RSI/Bollinger/TREND_FILTER are all confirmed
correct, the repair is *not* a bounded indicator fix. It is the strategy-semantics change in
item 2 — which is gated on Phase-3 and reverses a standing research decision.

1. **Wire `consensus_action`** (`signal_aggregator.py:~1038`) — removes dead code. Honest
   but behaviourally inert on current data (90/90 still HOLD). Do it for correctness, do
   not expect signals from it.
2. **Resolve the trend/mean-reversion conflict** — the real repair. The regime router
   already makes the call correctly 146/146. Options: promote the router from advisory to
   executing, or make the ensemble regime-aware so mean-reversion voters are down-weighted
   in a trending regime. This is a strategy-semantics decision with edge implications and
   is gated on Phase-3.
3. **Ensemble abstention dilution** (`normalized_weights`, `multi_strategy_ensemble.py:162`)
   — non-firing legs keep their weight in the denominator while contributing 0, so two
   agreeing legs at confidence *c* score only `0.667c`. Double-counts participation, which
   `MIN_AGREEING_LEGS` already enforces. Latent now; binds the moment (1) or (2) lands.
4. **Investigate Ichimoku saturation** — `conf=1.00` on 65% of votes at 1.3x weight.

## 7. Caveat that outranks all of the above

None of this creates edge. Per `CLAUDE.md` §2 every measured strategy has negative Sharpe,
and round-trip taker fees (~0.11%) exceed any observed edge at a $100 account. These repairs
make the plumbing report the truth; they do not make the truth profitable. Any claim
otherwise needs DSR/CPCV per `returns_metrics.py` / `cpcv.py`.

> **Note (2026-08-25, ADR-029):** the account flipped to $10,000, but the fee argument above is
> **bps-of-notional and holds at any account size** — only the "$100 account" framing was size-specific.
> The flip does not create edge.

Counters are process-local and reset on engine restart; the engine was restarted
2026-08-22 14:09 UTC during the bind-mount outage repair
(`docs/operations/INCIDENT-2026-08-22-bind-mount-outage.md`), so the funnel's 146-evaluation
window starts there while the log-derived figures above span the full 16 h.
