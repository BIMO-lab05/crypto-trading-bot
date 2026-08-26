# Edge Research Battery — Design

**Date:** 2026-08-16
**Status:** Approved (brainstorming session, operator-confirmed section by section)
**Scope:** Host-run research pipeline. Touches `backtesting/` and `tests/` only. No `services/` runtime code.

## 1. Why this exists

The "why are we losing trades" question is answered and closed:

- The deployed ensemble is chance-level: 49.07% directional accuracy over 12,387
  signals, DSR 0.0 (`.planning/evidence/killtests/H4-verdict-20260806.md`).
- Costs exceed gross edge 2.3–4.1×: 4.88 bps gross edge per trade vs 21–31 bps
  round-trip cost (`H3-secondary-verdict-20260806.md`).
- 16 mechanical money-path defects were fixed 2026-08-12 (`63595b0`..`2a48846`);
  the RES minors batch landed 2026-08-16. There is no remaining "bug that makes
  it unprofitable."

Therefore profitability requires **new edge that clears costs**, not more bug
fixing. This design builds the pipeline that finds it — or, more likely per
repo doctrine, kills candidates cheaply and honestly. A clean REJECT is a
successful outcome.

The paper trader keeps running on the clean-data epoch as a **control**: its
forward P&L is the baseline any promoted candidate must beat. Nothing in this
scope modifies it.

## 2. Goal and non-goals

**Goal:** A unified kill-funnel that takes four strategy candidates (interface
open to more later) through
identical data, identical costs, and identical statistical gates, and emits one
killtest-style verdict per candidate.

**Non-goals (explicit, to prevent scope drift):**

- No trading-engine integration. A PASS verdict yields a recommendation to
  forward-paper-test; wiring a winner into `services/trading-engine` is a
  separate future design.
- No cost-reduction re-engineering of the running trader.
- No ML re-enable. No LIVE anything.
- No expansion of the validated trading set (BTC/ETH/SOL/BNB/ADA). Research
  universe is wide; the tradable set is unchanged without operator approval.

## 3. Architecture

New code in `backtesting/edge_lab/` (host-run):

```
backtesting/edge_lab/
├── universe.py      # top-30 USDT linear perp selection, pinned snapshot
├── fetch.py         # klines + funding-rate history → CSV cache
├── candidates/
│   ├── xs_momentum.py
│   ├── funding_carry.py
│   ├── lf_trend.py
│   └── vol_breakout.py
├── gates.py         # gate runner: sanity → hurdle → CPCV/DSR
└── run_battery.py   # entry point
```

Money rules (host-run side of `.claude/rules/money.md`):

- `from shared.account import ACCOUNT_EQUITY_USD` — never a capital literal.
- `Decimal` for money; `float` for indicator math only.
- Tick-size price rounding; `round(price, 2)` is forbidden.

### 3.1 Universe

- Top ~30 USDT linear perps by 24h turnover via Bybit `/v5/market/tickers`
  (public endpoint, no keys), filtered to symbols with ≥ 2 years of listing
  history.
- Written once to `backtesting/edge_lab/universe_<date>.json`; every run reads
  the pin. Reproducible by construction.
- **Documented bias:** selecting today's top-30 and backtesting 2 years is
  survivorship-biased. The ≥2y listing filter mitigates but does not remove it.
  Every verdict doc carries this caveat verbatim.

### 3.2 Data

- Fresh Bybit **mainnet** fetch. Local TimescaleDB is not used: it is polluted
  with testnet prices before 2026-04-25 and holds only 14 symbols.
- Per symbol: 1440m klines × 730d, 240m klines × 365d. Same CSV conventions and
  `backtesting/data/` location as the existing `bybit_data_fetcher.py` output.
- Funding-rate history via `/v5/market/funding/history` →
  `backtesting/data/funding/<SYMBOL>_funding.csv`. This is a new repo
  capability: nothing has ever stored funding rates
  (`screen.py` docstring documents the resulting EXCLUDES marker). It serves
  both the cost model and the funding-carry candidate.

### 3.3 Costs

- Cost math stays in `services/trading-engine/app/costs.py`, loaded host-side
  through `backtesting/costs_loader.py` (`te_costs`).
- Per-symbol round-trip tiers extended from the current 5 symbols to the full
  universe. A symbol without an explicit tier gets the **conservative 31 bps
  tier**, never the cheap one by default.

### 3.4 Candidate interface

Each candidate module exposes one function:

```python
def generate_trades(data: UniverseData, variant: Variant) -> Path:
    """Emit a trades CSV in the exact column format screen.py consumes."""
```

Execution model, uniform across candidates: the signal at bar `t` uses only
data through bar `t−1` close; the trade executes at bar `t` open. Next-bar
execution — no look-ahead by construction, and enforced by test (§7).

## 4. Candidate battery

Anti-overfitting rule for the whole battery: **small fixed parameter grids,
declared here, before any run. Every variant is reported. The total trial count
feeds DSR deflation.** No optimizer sweeps. No cherry-picking.

| # | Candidate | Signal | Bars | Rebalance / hold | Variants |
|---|---|---|---|---|---|
| 1 | Cross-sectional momentum | Rank universe by trailing return; long top quintile, short bottom quintile | 1440m | Weekly | lookback ∈ {7d, 30d, 90d} = 3 |
| 2 | Funding carry | Position against the crowded side when funding is persistent and above threshold; collect funding | 1440m + 8h funding | Daily eval; hold while funding pays | entry threshold ∈ {1.5×, 2×} hurdle = 2 |
| 3 | Low-frequency trend | Donchian channel breakout, per symbol, long + short | 1440m | Hold days–weeks; exit on opposite channel | (entry, exit) ∈ {(20,10), (55,20)} = 2 |
| 4 | Vol breakout | Squeeze (BB inside Keltner) → trade direction of expansion break; ATR stop | 240m | Hold ≤ 5 days | 1 fixed config |

Pinned definitions (declared before any run, per the anti-overfitting rule):

- **Candidate 1:** rebalance at Monday 00:00 UTC open; quintile = top/bottom 6
  of the 30-symbol universe; equal weight within each leg.
- **Candidate 2:** "persistent" = same funding sign across the last 3
  settlements (24h) **and** trailing 3-settlement mean, annualized, above the
  entry threshold. Exit when either condition fails.
- **Candidate 2 amendment (Task 9 implementation, pinned in fix round 1):**
  "the last 3 settlements (24h)" is enforced, not assumed — persistence
  additionally requires (a) the newest of the 3 to be under 24h old relative
  to the evaluation bar, since a series that has gone quiet can otherwise
  read as permanently persistent and (b) the oldest-to-newest span of the 3
  to be ≤ 24h, since a collector gap can otherwise let 2 stale settlements
  plus 1 fresh one pass check (a) while spanning several days. Both are
  fixed thresholds declared here, not selected from a grid — they add no
  swept parameter, so `NUM_TRIALS_FLOOR = 16` and the 8-variant DSR
  deflation are unchanged.
- **Candidate 4:** BB(20, 2.0) inside Keltner(20, 1.5) defines the squeeze;
  entry on close beyond the Keltner band in the expansion direction; stop at
  2× ATR(14); time-exit at 5 days.

- **8 variants battery-wide.** DSR is deflated for all 8 trials (plus the
  historical trials already on record for this repo).
- Shorts are included in research (the engine has supported SHORT since the
  Jan-2026 fixes). If a surviving candidate needs a long-only variant for the
  declared account size (`shared/account.py`), that is recorded in its verdict — never silently
  swapped.
- Candidate 2 depends on the funding fetcher (§3.2): funding is both a cost
  input and that candidate's alpha source.
- Honest expectation, stated up front: most or all variants die at Gate 1.

## 5. Gates

Kill funnel, cheapest gate first. Failing any gate produces a REJECT verdict
doc and stops that candidate.

**Gate 0 — data sanity (automatic, per symbol).** Candle continuity (no gap
greater than 2 intervals), no zero or negative prices, funding coverage stated.
Failing symbols are dropped **and named** in the output. No silent universe
shrinkage.

**Gate 1 — cost hurdle (`backtesting/screen.py`, already built).** Gross edge
must be ≥ **2× the taker round-trip cost**, per variant. The headline verdict
is the TAKER verdict; a maker-only pass is reported but does not advance
(screen.py's own rule — no fill model, no maker credit). With the funding
fetcher in place, `net` lines include funding for the first time instead of
carrying the EXCLUDES marker.

**Gate 2 — CPCV + DSR (survivors only).** Combinatorially purged
cross-validation with purge and embargo, reusing the existing `cpcv.py`, run on
**net-of-cost returns**. Pass requires all of:

- **DSR ≥ 0.95**, deflated by all 8 battery trials;
- **Pooled profit factor** computed as `sum(wins) / sum(losses)` across all
  folds' trades — never mean-of-fold-PFs (zero-loss folds drag that mean toward
  1.0);
- Positive net expectancy in ≥ 70% of CPCV paths — one lucky regime cannot
  carry a pass.

**Gate 3 — hostile review.** The `quant-skeptic` agent reviews any PASS before
it is called a pass (its default verdict is *no edge*). Review targets:
look-ahead, survivorship handling, trial accounting, regime concentration.

**What promotion means — bounded.** A candidate passing all gates gets a PASS
verdict doc and a recommendation to forward-paper-test against the control
trader. It does **not** get wired into the engine in this scope.

**Verdict format.** One doc per candidate in `.planning/evidence/killtests/`
(`<candidate>-verdict-<date>.md`), same structure as the H3/H4 verdicts:
n trades, gross edge bps, cost bps, net, DSR, PASS/REJECT, caveats — including
the survivorship caveat (§3.1) verbatim.

## 6. Error handling

- Fetcher: retry with backoff on Bybit 5xx/timeouts; partial downloads resume
  from cache; public-endpoint rate limits respected.
- Missing funding series → screen.py's existing EXCLUDES marker. Funding is
  reported as unavailable, never assumed zero.
- A candidate crashing mid-battery does not kill the battery: its verdict is
  ERROR with the traceback; the others complete.
- No silent caps anywhere: dropped symbols, skipped variants, and truncated
  histories are all named in output.

## 7. Testing

Host-run, `--no-cov`, under `tests/edge_lab/`:

- **Look-ahead (shift-invariance) test per candidate:** the signal at bar `t`
  must be byte-identical when all bars after `t` are deleted. Automated, not
  eyeballed.
- Cost application: known trade → expected fee/slippage/funding, exact to the
  `Decimal`.
- Cross-sectional ranking correctness on a synthetic fixture with a known
  ordering.
- Pooled-PF regression test including a zero-loss fold (the known trap).
- Interface contract test: candidate CSV columns match what `screen.py`
  consumes.

## 8. Deliverables

1. `backtesting/edge_lab/` code + `tests/edge_lab/` tests.
2. Universe pin + fetched kline and funding data cache (funding history is a
   new repo capability).
3. Four verdict docs in `.planning/evidence/killtests/` + one battery summary.
4. STATE.md / progress.md updates; quant-skeptic review record on any PASS.

## 9. Execution notes (for the implementation plan)

- Data layer (universe, fetch, cost tiers) lands first, sequentially — it is
  the shared dependency.
- Candidates 1–4 are independent after that: fan out to parallel subagents at
  execution time (3–5 ceiling per CLAUDE.md §8).
- Verdicts are written as each candidate finishes; the battery summary last.
