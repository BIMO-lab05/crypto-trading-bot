# Phase 22: round(price, N) Epidemic Kill - Context

**Gathered:** 2026-08-27
**Status:** Ready for planning
**Source:** 2026-08-26 signal-path audit (§3, adversarially verified) + fresh site verification 2026-08-27 post-phase-21. The roadmap's 2026-07-30 inventory is STALE — ~18-20 of its 22 sites were fixed by WS1-B (2026-08-17) and are guard-enforced by `tests/test_price_rounding_invariant.py`.

<domain>
## Phase Boundary

Kill the remaining price-domain fixed-precision rounding sites, grow the AST invariant guard over every cleaned file, and land a sub-$1 (ADA-scale) regression test for the one live-path site. Small phase — one plan expected.
</domain>

<decisions>
## Implementation Decisions

### Confirmed residue (verified on disk 2026-08-27 at commit 8168ae4 — these line numbers are current)
1. **`services/trading-engine/app/strategies/simple_rsi_strategy.py:214-215`** — `round(stop_loss, 4)` / `round(take_profit, 4)` on the LIVE ensemble path (leg 1 SL/TP flow into EnsembleSignal). Fix: `float()` passthrough (487d1bd pattern). `:212` `round(confidence, 4)` is dimensionless — keep, mark `# non-price-round` if the guard requires.
2. **`services/technical-analysis/app/handlers/sqzmom.py:109`** — 4dp price-unit momentum in the `/indicators/sqzmom` payload → `float()`. Lines `:364/:367/:370` are backtest display stats — fix to `float()` too while there (same price domain), `:358` pct and `:128` confidence stay.
3. **`services/technical-analysis/app/indicators/squeeze_momentum.py:541`** — 4dp momentum in `get_signal` dict → `float()`. `:496`/`:543` confidence/strength are dimensionless 0-1 — keep.
4. **`services/technical-analysis/backtesting/sqzmom_backtest.py:118,120`** — `round(entry_price, 2)` / `round(exit_price, 2)` — the exact ADA-killer class, in backtest serialization → `float()`. `:122-124` position_size/pnl/pnl_pct are not price-domain — keep.
5. **`services/trading-engine/app/trading_enhancements/adaptive_rsi.py:162`** — `round(self.atr_value, 4)` (price units, serialization-only) → `float()`.
6. **`services/trading-engine/app/analytics/post_trade_analysis.py:151`** — `round(self.price_improvement, 4)` (price units; flattens real sub-1e-4 improvements to 0.0 at ADA scale) → `float()`. The companion `_bps` field at `:152` is dimensionless — keep.

### Guard growth (PRICE-02 satisfied by the EXISTING AST guard, not a new grep gate)
- Add every file above to `SCANNED_FILES` in `tests/test_price_rounding_invariant.py` after cleaning it (append-only discipline: never add a file not just cleaned).
- Delete the stale "known debt" comment lines (currently `:52-53`) that list `handlers/sqzmom.py` and `simple_rsi_strategy.py` as uncovered.
- The roadmap's "CI grep gate" requirement is satisfied by this guard — it is stronger (AST, not grep) and already precedent. Do NOT build a parallel grep gate.

### Sub-$1 regression test (PRICE-01)
- ADA-scale test: SimpleRSIStrategy signal at price ≈ 0.60 with real ATR — assert SL/TP survive with full precision (not quantized to 4dp beyond what the values naturally carry; concretely: output equals the unrounded computation exactly).

### Constraints
- Min-notional rejection paths untouched: reject with reason, never clamp.
- No behavior change beyond precision: SL/TP values may differ at <1e-4 magnitude on the live path — document in SUMMARY, no ablation needed (below tick for majors, at-tick for ADA).
- Tick-aware quantization stays at order time (`costs.py quantize_price`, `paper_slippage.py`) — do NOT add tick logic at signal layer.
- Format-hook hazard: use Bash+pathlib for edits if the Edit tool reflows.
- Tests: engine from `services/trading-engine` `--no-cov`; TA from `services/technical-analysis`; guard from repo root. Pre-commit smoke hook is cwd-sensitive — commit from repo root.
- After fixes: rebuild + `--force-recreate` both touched services (trading-engine, technical-analysis) — Docker builds need `DOCKER_BUILDKIT=0` and a clean `DOCKER_CONFIG` (vsock credential bug).

### Claude's Discretion
- Whether backtest/serialization files get `# non-price-round` markers vs full float() conversion for their non-price rounds.
- Test placement (extend existing precision test files vs new file).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/audits/2026-08-26-ta-signal-path-audit.md` §3 — verified residue enumeration and classification discipline
- `tests/test_price_rounding_invariant.py` — the guard to grow (SCANNED_FILES tuple, `# non-price-round` opt-out, BANNED_NDIGITS {2,4})
- `services/trading-engine/app/utils/support_resistance_detector.py:631-641` — the float()+PRICE-01-comment fix pattern to replicate
- `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py` — precedent precision test
- `.planning/phases/21-ta-aggregator-widening-leakage-net/21-03-SUMMARY.md` — simple_rsi_strategy.py current shape (ATR threading moved the rounding sites to :214-215)
</canonical_refs>

<specifics>
## Specific Ideas

Verification: both suites green + repo-root guard green with grown SCANNED_FILES; rebuild + force-recreate; `docker exec` proof the float() change is in the running images; commit in logical chunks with pathspecs.
</specifics>

<deferred>
## Deferred Ideas

- 8dp/6dp non-destructive serialization rounds (10 sites) — hygiene only, not this phase.
- `main.py.bak` legacy sites — file deleted in 21-08; nothing left.
</deferred>

---

*Phase: 22-round-price--n--epidemic-kill*
*Context gathered: 2026-08-27 from audit §3 + on-disk verification at 8168ae4*
