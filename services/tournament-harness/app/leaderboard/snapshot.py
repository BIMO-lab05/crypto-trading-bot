"""Tournament leaderboard snapshot exporter (D-18).

The committed artifact for downstream phases:
  - Phase 4 (TOURN-05/06 significance test + auto-PR) reads snapshot JSON
  - Phase 7 (DASH-04 dashboard tournament view) reads snapshot JSON
The SQLite DB at services/tournament-harness/data/leaderboard/leaderboard.db is
gitignored; snapshot JSON is the source of truth in git.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.leaderboard.db import LeaderboardDB


logger = logging.getLogger(__name__)


def export_snapshot(
    db_path: str | os.PathLike,
    tournament_id: str,
    output_path: str | os.PathLike,
) -> Dict[str, Any]:
    """Export one tournament's leaderboard rows + config to a committable JSON file.

    Returns the snapshot dict (also written to disk).
    Raises ValueError if tournament_id has no row in the tournaments table.
    """
    db = LeaderboardDB(db_path)
    try:
        config = db.get_tournament_config(tournament_id)
        if config is None:
            raise ValueError(
                f"tournament_id {tournament_id!r} not found in tournaments table"
            )
        rows = db.list_runs(tournament_id=tournament_id, limit=10_000_000)
        version = db.schema_version()
    finally:
        db.close()

    snapshot: Dict[str, Any] = {
        "tournament_id": tournament_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": version,
        "config": config,
        "rows": rows,
        "summary": {
            "n_rows": len(rows),
            "n_success": sum(1 for r in rows if r.get("status") == "success"),
            "n_failed": sum(1 for r in rows if r.get("status") == "failed"),
            "architectures": sorted(
                {r.get("architecture") for r in rows if r.get("architecture")}
            ),
            "symbols": sorted({r.get("symbol") for r in rows if r.get("symbol")}),
        },
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write (T-03-32)
    fd, tmp_path = tempfile.mkstemp(
        prefix="snapshot.", suffix=".json.tmp", dir=str(out_path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(out_path))
        try:
            os.chmod(out_path, 0o644)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.info("snapshot written: %s (%d rows)", out_path, len(rows))
    return snapshot


__all__ = ["export_snapshot"]
