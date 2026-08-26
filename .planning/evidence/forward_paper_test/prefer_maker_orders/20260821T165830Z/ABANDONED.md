# Isolation run ABANDONED — 2026-08-21

- **Run:** `prefer_maker_orders`, run id `20260821T165830Z`, launched 2026-08-21 16:58:30 UTC on `2d45be2`, harvest was due 2026-08-28 16:58 UTC.
- **Decision:** Operator authorized a mid-window trading-engine redeploy (2026-08-21, in response to the measurement below) to land the signal-funnel instrumentation and the advisory strategy router.
- **Why the window was already worthless — measured, not assumed.** Over the first 3.4 h (16:58 → 20:25 UTC) the engine produced **zero orders, zero fills, zero positions**:

  | Ensemble outcome | Count |
  |---|---|
  | `HOLD — no legs fired` | 1013 |
  | `ADAUSDT: SELL conf=27.61% size=10.00% legs={simple_rsi: SELL, mean_reversion: SELL}` | 84 |
  | `HOLD — weighted score below threshold 0.1` | 3 |
  | orders placed / filled / positions opened | **0** |

  Every one of the 84 emitted signals died at the same gate:
  `[ENSEMBLE][GATE] ADAUSDT: confidence 0.2761 < min_signal_confidence 0.30 — rejecting`.
  A 7-day harvest of a `prefer_maker_orders` window with zero fills measures **no maker execution whatsoever** — the same reason run `20260820T151351Z` was abandoned the day before, one gate further down the cascade.

- **Root shape of the failure (same class as the previous run).** Under frozen ⅓ ensemble weights, ensemble confidence is `|Σ sign × leg_conf × ⅓|`. Clearing `min_signal_confidence = 0.30` therefore requires `Σ leg_conf ≥ 0.90` across agreeing legs — one leg alone needs conviction ≥ 0.90; two legs need mean ≥ 0.45. The observed two-leg SELL sat at 0.2761 (mean leg conviction ≈ 0.414) and could not clear it. This is a reachability question about the gate, not a market-opportunity question, and it is now measurable directly: see `docs/FUNNEL_REPORT.md`.

- **Consequences:**
  - `complete-run` must NOT be run against this window. If run it will refuse on container-Created mismatch after the redeploy — that refusal is correct, do not `--force-unverified`.
  - The `PREFER_MAKER_ORDERS` env override reverts to compose defaults on redeploy.
  - A fresh isolation run must be relaunched from the launcher **after** the Phase-3 recalibration settles, not before — relaunching against an unchanged `min_signal_confidence` would reproduce this window exactly.
- **Not affected:** Phase C orderbook/OI collection clock (market-data untouched); daily evidence cron.
