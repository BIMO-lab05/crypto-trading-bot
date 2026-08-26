# Collection incident — 2026-08-20 (host suspend, 9.4h orderbook hole)

**Detected:** 2026-08-20 ~14:55 UTC, by Task 9's manual run of the new weekly gap check
(`scripts/check_collection_gaps.py --window-minutes 10080` → exit 1, 28 breaches).

**Window:** 2026-08-20 **02:59:17 → 12:21:23 UTC** (9h22m), all 14 orderbook symbols
(identical max_gap ≈ 33,726,600 ms). Tickers show the same hole (02:55:33 → 12:25:33).
A second, minor orderbook gap: 2026-08-19 18:31:47 → 18:33:32 (105s).

**Root cause: host machine suspended.** Evidence:
- Identical gap across every symbol and across two independent collectors (orderbook, tickers)
  — process-level failure of one job cannot do that.
- `journalctl`: systemd-resolved "Clock change detected" storm starting 02:00:20 UTC.
- WSL VM uptime unbroken (boot 2026-08-18) — WSL2 freezes rather than reboots on host sleep.
- `open_interest` shows NO gap because Bybit's OI endpoint serves history — the 5-min collector
  self-backfilled the sleep window on resume. Orderbook snapshots are live-only, unbackfillable.
- market-data container recreation at 12:58:31 UTC is a separate, later event (Task 6 deploy era);
  data had already resumed at 12:21.

**Current state:** healthy — last-60min cadence 5006 ms avg (nominal 5000, limit 7500), all symbols OK.

**Consequences:**
1. **Phase C gate clock RESET.** 21 consecutive gap-free days now count from 2026-08-20 12:21 UTC
   → earliest microstructure battery ~**2026-09-10**.
2. The 2026-08-21 17:30 UTC "48h acceptance" checkpoint (edge-search v2) is moot as originally
   framed — the window it would have measured contains the hole. The weekly cron check supersedes it;
   acceptance = 48h gap-free from 2026-08-20 12:21, checkable from 2026-08-22 ~12:30 UTC.
3. Paper trading engine was equally frozen during the window — absence of trades, not contamination.
   Clean-data epoch stands.
4. `check_collection_gaps.py`'s full-history max-gap check will now flag this hole FOREVER (until 90d
   retention ages it out) — the weekly cron will exit 1 on every run even with healthy collection.
   Loud-but-stale alarm. Follow-up filed (see below).

**Prevention (operator action — cannot be fixed from WSL):** disable Windows sleep while plugged in
(Settings → System → Power), or accept that every host suspend punches an unbackfillable hole in
orderbook history and resets the Phase C clock.

**Follow-up filed:** GAPCHK-01 — teach `check_collection_gaps.py` a windowed max-gap mode (same
`--window-minutes` scope as the cadence assertion) plus an explicit "consecutive gap-free days since
last gap" readout for the Phase C gate, so historical holes don't permanently redline the weekly cron.
