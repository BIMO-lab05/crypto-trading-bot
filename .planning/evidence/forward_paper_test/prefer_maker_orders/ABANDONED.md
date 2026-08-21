# Isolation run ABANDONED — 2026-08-21

- **Run:** `prefer_maker_orders`, run id `20260820T151351Z`, launched 2026-08-20 15:13 UTC, harvest was due 2026-08-27 15:13 UTC.
- **Decision:** Operator ("fix the gates too, the window is empty anyway", 2026-08-20) authorized mid-window redeploy of trading-engine + technical-analysis.
- **Why the window was already worthless:** in the first 3.4h the engine rejected **686/686** ensemble signals — 379 at the mathematically unreachable `short_min_confidence=0.70` (structural ceiling 0.60 under frozen ⅓ weights), 307 at the 0.30 general floor (including every BUY). Zero fills → zero maker-execution evidence. A 7-day harvest would have measured nothing.
- **Consequences:**
  - `complete-run` must NOT be run against this window; if run, it will refuse on container-Created mismatch after the engine redeploy — that refusal is correct, do not `--force-unverified`.
  - The `prefer_maker_orders` env override reverts to compose defaults on redeploy. A fresh isolation run must be relaunched from the launcher after the gate fixes settle.
  - Gate fixes deployed instead: `short_min_confidence` 0.70→0.35 (`df35367`), phase1 metrics honesty (`66d8cb2`), weights persistence (`c517f6e`, `06e949b`).
- **Not affected:** Phase C orderbook/OI collection clock (market-data untouched); daily evidence cron (dormant-state tick unaffected).
