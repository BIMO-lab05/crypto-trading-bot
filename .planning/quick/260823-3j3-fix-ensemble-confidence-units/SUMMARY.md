---
quick_id: 260823-3j3
slug: fix-ensemble-confidence-units
status: complete
created: 2026-08-23
completed: 2026-08-23
commits: [b4cb894, 94727f3, 744d3e7, 58332fb, 42e2250]
---

# Summary — ensemble confidence unit mismatch

**Outcome: the system is trading again.** First entry since 2026-08-18.

## The defect

`MultiStrategyEnsemble` scaled each leg's contribution by its share of ALL THREE
legs' weight, then handed that to `auto_trader._ensemble_passes_signal_gates`,
which compares it against `min_signal_confidence = 0.30` — a **conviction**
floor, the same constant `RiskManager.validate_signal` applies to an aggregator
confidence on the REST path. A **vote-share** measured against a conviction bar.

With two of three legs silent, a lone leg's ceiling was 1/3, so clearing 0.30
required post-MTF conviction ≥ 0.90 against a scale observed to top out near
0.62. Two knobs contradicted each other: `MIN_AGREEING_LEGS = 1` said one leg
suffices; the denominator made that arithmetically impossible.

Live proof, SOLUSDT 2026-08-23 01:00–01:23 — conviction 0.36 reported as
`conf=11.90%` (0.36 / 3), rejected against the 0.30 floor 36 consecutive times.

## Commits

| Commit | Change | Threshold changed? |
|---|---|---|
| `b4cb894` | Normalise ensemble score over **firing** legs | no |
| `94727f3` | Bucket MACD as TREND, not MOMENTUM | no |
| `744d3e7` | MTF confidence derived from the action it describes | no |
| `58332fb` | Wire the dead `signal_type` threshold (volume) | no |
| `42e2250` | Funnel: terminal attribution, symbol, cycles | no |

**No threshold value was changed anywhere.** Every change is a unit or
correctness repair.

## Measured effects (8h of live logs, before deploying)

- **Ensemble renormalisation:** 36 of 231 leg-fire events clear
  `min_signal_confidence` — all SOLUSDT, one recurring state. ~1 position, not a
  floodgate. Verified: exactly 1 trade after deploy.
- **MACD re-bucket:** flips 712 of 1,924 diversity passes (37.0%) to fail —
  makes the gate **stricter**. On the pre-fix pipeline the cost was zero: all
  247 signals that passed every aggregator gate also had SQZMOM (VOLATILITY)
  agreeing, so they still spanned 2+ categories. **That figure describes the
  old pipeline** — it was measured before items 2 and 4 changed which
  confidence is forwarded and demoted 152 laundered consensuses to HOLD, so it
  is not a post-deploy number. See the post-deploy section below for what was
  actually observed.
- **MTF consolidation:** of 231 directional consensuses, 152 (65.8%) had zero
  timeframe whose *gated* action matched; 43 had one; 36 had two — and those 36
  are exactly the ones that emitted. Drops 152 laundered artifacts at zero cost.
- **Volume `signal_type`:** behaviour-identical for both callers; removes a dead
  variable and one of two expressions that had to agree.

## Post-deploy measurement (all five live, 11 cycles, 187 aggregations)

Read from the repaired funnel, so these are the real numbers for the current
pipeline rather than a counterfactual on the old one:

| stage | evaluated | passed | rejected |
|---|---|---|---|
| `passed_indicator_agreement` | 187 | 121 | 66 |
| `passed_category_diversity` | 187 | 132 | **55 (29.4%)** |
| `passed_confidence_floor` | 187 | 77 | **110 (58.8%)** |
| `ensemble_signal_emitted` | 55 | **11** | 44 |
| `passed_position_dedupe` | 11 | 0 | 11 |

**The ensemble now emits on 11 of 55 evaluations (20%). Before the fix it was
0 of 1,195.** The stricter MACD map is live for all of these, and diversity is
not what blocks emission — the confidence floor still rejects roughly twice as
often. All 11 emissions were SOLUSDT and were correctly refused by position
dedupe because the position opened at 01:42:58 is still open, which is the
guard working, not a failure.

`terminal_stage` totals 55 against 104+ all-stage rejections — a strict subset,
which is the point of item 6.

## Verification (CLAUDE.md §7)

| Check | Result |
|---|---|
| Service rebuilt + restarted | `directional_weight` present in container |
| Order log line | `Executing paper market order: BUY 0.1 SOLUSDT @ 96.36` |
| DB row persisted | `f41fbdba-cb57-4724-a82a-9782339afeca` |
| Risk cap honoured | `PER_TRADE_CAP CLAMP ... clamped=$10.06 (10.0% of $100.59)` |
| Not a runaway | exactly 1 execution; subsequent cycles returned HOLD |

```
symbol SOLUSDT | side BUY | quantity 0.10000000 | price 96.41000000
total_value 9.64100000 | fee 0.00530255 | strategy ensemble
signal_confidence 0.3060 | executed_at 2026-08-23 01:42:58.286475
```

`$9.64` notional clears the ~$5 Bybit minimum. Fee `$0.0053` = 0.055%, one side
of the ~0.11% round trip.

## Test baseline

Full trading-engine suite, compared against `931eb81` in an isolated worktree:

| | failed | passed | skipped |
|---|---|---|---|
| baseline `931eb81` | 2 | 1,988 | 795 |
| after all five fixes | 2 | 2,014 | 795 |

Identical failure set both runs — `test_pairs_trading::test_complete_trading_cycle`
and `test_signal_cache::test_cache_entries_isolated`. Neither is caused by this
work; both are pre-existing, and `test_signal_cache` passes 33/33 in isolation
and 40/40 alongside the new funnel tests, so it is cross-test pollution rather
than a singleton interaction. The +26 is exactly the new tests added here
(7 ensemble + 5 categories + 7 MTF + 7 funnel).

## What this does NOT establish

**No edge claim.** One paper trade is not evidence of profitability, and no
strategy in this repo has a positive Sharpe (CLAUDE.md §2: −0.22 … −0.50). The
value of trading again is that it produces the data to kill or confirm the
strategy cheaply — not that it makes money. Expect losses.

## Deliberately not done

- The engine still requests `signal_type="breakout"` only, so the volume WEAK
  band (1.0–1.2×) stays unconfirmable live. Making it reachable is a behaviour
  change, not a correctness fix.
- The volume `< 1.0×` trailing-mean label still puts the median bar below the
  line by construction (~65% of all bars). Changing it is a threshold decision.

## Evidence

`.planning/evidence/hold-funnel-2026-08-22.md` — full funnel diagnosis, measured
counterfactuals, and the adversarial-verification record.
