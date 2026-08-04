---
slug: leverage-ensemble-path-bypass
status: resolved
trigger: |
  Operator set LEVERAGE_ENABLED=true + DEFAULT_LEVERAGE=10.0 in container env.
  Bot still opens paper positions at non-leveraged size (~$5-7 notional at
  $73 balance). User complaint: "i want to use 10% lavrage and i activate
  it in the env fille but the bot is not using lavrage". Plus user asked
  to audit tournament + phase3 frontend pages via Playwright MCP.
created: 2026-05-19
updated: 2026-05-19
tdd_mode: false
---

# Debug Session: leverage-ensemble-path-bypass

## Symptoms (2026-05-19 audit)

1. **Leverage env correctly set:** `docker exec crypto-bot-trading printenv` returns
   `LEVERAGE_ENABLED=true`, `DEFAULT_LEVERAGE=10.0`, `MAX_LEVERAGE=20.0`,
   `MIN_LEVERAGE=1.0`. Pydantic `Settings()` parses these correctly.
2. **Recent paper positions show no leverage applied:** all 5 open positions
   (BTC/ETH/SOL/BNB/ADA, opened 2026-05-19T15:59:44Z, all SHORT) have notional
   ≈ $5 (allocation_pct ~6-9%). With $73 balance × 10% margin × 10x leverage
   the expected notional is ~$73. Observed is 10× smaller.
3. **Trading-engine logs contain ZERO `[LEVERAGE]` lines** — the only place
   leverage is logged (`auto_trader.py:1912-1914`) lives in the
   research_optimized path. Active strategy is `ensemble`.
4. **Frontend pages render but have cosmetic gaps:**
   - `/tournament`: dropdown stuck at "Loading tournaments…" even after API
     returns `{count: 0, tournaments: []}` cleanly. No console errors, all
     network 200s.
   - `/phase3`: ML card titled "ML Price Predictions (LSTM)" but project
     deleted LSTM May 2026 (archived under `_archive_lstm/`). Models in use
     are GRU. Stale label appears 4 places: title, fallback model_type,
     untrained empty-state copy, hover description.

## Reproduction

1. `docker compose -f docker-compose.unified.yml ps` — confirm trading-engine
   running + healthy.
2. `curl -s localhost:8000/api/trading/auto/status | jq .status.strategy_mode`
   → `ensemble`.
3. `curl -s localhost:8000/api/trading/positions | jq '.positions[] | {symbol, side, entry_price, quantity}'`
   → each notional = entry × quantity ≈ $5 (not the expected $73).
4. `docker exec crypto-bot-trading python -c "from app.config import Settings; s = Settings(); print(s.leverage_enabled, s.default_leverage, s.max_risk_per_trade)"`
   → `True 10.0 0.1` — leverage is on, max-risk-per-trade is 10%.

## Hypothesis (verified)

`auto_trader.py:3993` (`_execute_ensemble_strategy` path) computed
`position_value = float(balance) * ens_signal.position_size_pct` with NO
leverage multiplication. The leverage code added 2025-12-15 (config.py L569,
auto_trader.py L1882-1907) lives ONLY in the research_optimized path
(`_handle_research_optimized`). The newer ensemble path (ADR-015, 2026-05-07)
was added without leverage awareness, so toggling `LEVERAGE_ENABLED=true`
has no effect when `strategy_mode=ensemble`.

paper_trading.py (L199-201, L269-271) DOES read `settings.default_leverage`
to compute `margin_required = order_value / leverage`. So with ensemble
passing un-leveraged `order_value`, the margin deduction becomes
`order_value / 10` — effectively under-deducting 10× on every ensemble
trade. (Cash impact is consistent for the OPEN side, but P&L on close uses
full notional moves, leading to over-stated profit/loss vs. true paper
account.)

## Evidence

- 2026-05-19T17:18Z: `docker logs crypto-bot-trading 2>&1 | grep -c LEVERAGE`
  → 0 hits.
- 2026-05-19T17:18Z: open positions `strategy=ensemble` (ADAUSDT
  position id `39b73638`); notional ≈ $4.74 (qty 18.84 × price $0.2518).
  Expected with leverage: $47.40.
- 2026-05-19T17:18Z: ensemble.position_size_pct at conf 0.27 = 0.0999
  (floor 0.05, cap 0.10, scaled 0.27 × 0.10 × 3.7). $73 × 0.0999 = $7.30
  un-leveraged. Should be $73 leveraged.
- 2026-05-19T17:18Z: `total_trades_executed=0, total_trades_rejected=65`
  in current run; counter increments on every HOLD signal cycle (no
  [ENSEMBLE] action lines for trade execution since 15:59:44 entries).

## Eliminated

- env-variable parsing bug — `Settings()` reads `leverage_enabled=True,
  default_leverage=10.0` correctly inside container.
- research_optimized leverage code path bug — that path correctly applies
  leverage (auto_trader.py L1882-1907). Not exercised because
  `strategy_mode=ensemble`.
- per-trade cap rejection — only fires from research path (auto_trader.py
  L1974). Ensemble path has no cap check. Zero `PER_TRADE_CAP BREACH` hits
  in log confirms cap not involved.
- `has_position` skip — would skip but is irrelevant; even if no positions
  were open, ensemble sizing would still be un-leveraged.
- WSL bind-mount or stale .env — env is propagating to container correctly
  per `printenv` inside container.

## Resolution

root_cause: |
  `auto_trader.py:3993` in `_execute_ensemble_strategy` computed
  `position_value = balance × position_size_pct` with no leverage
  multiplication. Ensemble path (ADR-015, 2026-05-07) ships independent
  from the leverage feature added to research_optimized path 2025-12-15;
  the two paths share `paper_engine` and `Settings` but not sizing logic,
  so toggling `LEVERAGE_ENABLED` had zero effect when `strategy_mode=
  ensemble` (the bot's default).

fix: |
  Mirror the research-path leverage calculation inside ensemble. Compute
  `leverage = max(min_leverage, min(default_leverage, max_leverage))` when
  `leverage_enabled`, otherwise `1.0`. Set
  `margin_value = balance × position_size_pct`, then
  `position_value = margin_value × leverage`. Log a `[ENSEMBLE][LEVERAGE]`
  line so future audits see the multiplier in stdout. Margin deduction
  inside paper_engine is unchanged: paper_trading divides notional by
  `default_leverage`, so cash impact = margin_value regardless of leverage
  (leverage only scales notional P&L exposure).

  Frontend cosmetic fixes alongside:
  - TournamentSelector.jsx L83: "Loading tournaments…" → "No tournaments
    available". The `empty` flag is true both during fetch and after
    fetch-with-empty-result; the prior copy lied to the user when the
    backend has zero tournaments (current state — no walk-forward runs
    on disk since 2025-12-06).
  - Phase3Dashboard.jsx 4 sites: "LSTM" → "GRU". CLAUDE.md notes LSTM
    deleted May 2026; models in use are GRU. Stale strings caught:
    L558 (title), L794 (fallback model_type), L816 (untrained copy),
    L1178 (hover description).

verification: |
  1. Source diff: auto_trader.py L3993 expanded from 1 line into a 14-line
     leverage-aware block + log. TournamentSelector.jsx L83 string swap.
     Phase3Dashboard.jsx 4 string swaps.
  2. trading-engine restart needed to load the auto_trader.py change
     (Python import cached). Operator action.
  3. Frontend rebuild needed to push new bundle to nginx. Operator action.
  4. Live verification deferred until operator clears 5 open positions
     (stop-loss, take-profit, or manual close) AND removes EMERGENCY_STOP.
     Expected post-resume:
     - First [ENSEMBLE] BUY/SELL log line on a fresh signal will be
       followed by [ENSEMBLE][LEVERAGE] line showing
       `margin=$X × 10x = notional $Y`.
     - New position notional ≈ 10× margin (e.g. $7 margin → $70 position).
     - paper_engine continues to deduct $7 cash (not $70) because
       paper_trading divides by default_leverage.

files_changed:
  - services/trading-engine/app/auto_trader.py (L3993 — ensemble leverage)
  - frontend/src/components/TournamentSelector.jsx (L83 — empty-state copy)
  - frontend/src/pages/Phase3Dashboard.jsx (LSTM → GRU, 4 sites)

## Out of scope (deferred / not bugs)

- "Strategy bugs" portion of user's request: all signals HOLD with
  `[ENSEMBLE] HOLD — no legs fired`. Per ADR-013 + commit `5b54ef1`
  (walk-forward 2026-05-19 — bot paused, gate fails), legs are gated off
  pending fresh edge evidence. Intentional safety, not a bug. Bot will
  resume firing when walk-forward shows DSR > 0.95 acceptance.
- 5 stale OPEN positions from 2026-05-19T15:59:44Z. Each position has
  running unrealized P&L (mostly +$0.01-0.07). NOT auto-closed because
  closing is operator action. Operator must close (or let stops fire)
  before leverage takes observable effect on new positions.
- Per-trade cap latent rejection in research_optimized path (auto_trader.py
  L1974 compares notional vs balance × cap). Not exercised because
  strategy_mode=ensemble. If user later switches to research_optimized
  with leverage on, REJECT fires immediately — would need separate
  ADR-class change to compare margin vs notional in that gate.
- portfolio-manager UPSERT bug was already fixed at commit `e03291a`
  earlier this session.
- api-gateway sentiment/ml DNS errors fixed at commit `7897201` earlier
  today (10:30 UTC).
