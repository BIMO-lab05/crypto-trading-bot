# Isolation-run harvest — prefer_maker_orders (harvested 2026-08-26, one day early on operator instruction)

Window: 2026-08-20 (run start, post-`80c7947`) → 2026-08-26 01:45 UTC (harvest).
Harvested before the ADR-029 $10,000 DB reseed; full pre-reseed state preserved in
`backups/cryptobot_pre10k_20260826_014506.sql` and in-DB archive tables
(`trades_archive_100usd`, `positions_archive_100usd`).

## Verdict: NO maker-execution evidence produced

- **3 trades in the whole window** (portfolio lifetime total 50, first 2026-07-29):

| executed_at (UTC) | symbol | side | qty | price | fee | order_type | prefer_maker meta |
|---|---|---|---|---|---|---|---|
| 2026-08-23 01:42:58 | SOLUSDT | BUY | 0.1 | 96.41 | 0.00530255 | MARKET | (empty) |
| 2026-08-23 05:00:53 | SOLUSDT | SELL | 0.1 | 93.11 | 0.00512105 | MARKET | (empty) |
| 2026-08-23 06:00:53 | ADAUSDT | BUY | 46 | 0.2151 | 0.00544203 | MARKET | (empty) |

- Fee check: 0.00530255 / (0.1 × 96.41) = **0.055%/side = taker rate** on every fill.
  All three executed as market orders; `metadata` carries no prefer_maker / order_type
  override. **prefer_maker_orders either never engaged on the fill path or always
  fell through to taker** — the run cannot distinguish which; that is itself the finding.
- No further trades after 2026-08-23 06:00 (last signal before the same-day DB outage
  took market-data down at ~19:47; the engine stayed up but starved of data through
  2026-08-26 00:00 — the run's final 2.2 days are data-outage, not market-quiet).
- One position left OPEN at harvest: ADAUSDT LONG 46 @ 0.2151 (entered 2026-08-23
  06:00, unrealized 0.00) — archived and cleared by the reseed, not closed via engine.

## Portfolio state at harvest ($100 era, final)

`id=1 paper_trading`: initial 100.00, cash 100.25118663, total_value 100.25118663,
realized_pnl +0.25118662 (lifetime, gross of slippage). Per-symbol lifetime P&L:
BTC +2.36, ETH +0.37, BNB +0.50, SOL −0.11, ADA −2.87 (fees included in ledger).

## Consequences

- Maker-vs-taker cost question (edge-search v2, "maker halves costs") remains OPEN —
  needs an instrumented run where the order path logs the maker attempt/fallback,
  not just the final fill type.
- Data-outage class (host suspend → staged bind mounts) has now truncated TWO
  evaluation windows. Any future isolation window needs the DB-outage watchdog first.
