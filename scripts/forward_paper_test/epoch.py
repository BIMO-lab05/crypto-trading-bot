"""Clean-data epoch: positions opened at/after this instant ran entirely on the
repaired engine (progress.md 2026-08-12). The two legacy sweep closes seconds
after the epoch (13:47:27Z / 13:47:35Z) belong to PRE-epoch positions and are
excluded by filtering on the POSITION's opened_at, never on trade timestamps.

Single source of truth for host-side analysis. The DB-side twin is the
public.clean_epoch_positions / clean_epoch_trades views
(scripts/sql/create_clean_epoch_views.sql) — keep them in agreement.
"""

CLEAN_DATA_EPOCH_ISO = "2026-08-12T13:47:20Z"
CLEAN_DATA_EPOCH_MS = 1786542440000
