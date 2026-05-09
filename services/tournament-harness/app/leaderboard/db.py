"""SQLite leaderboard data access (D-17, D-18).

Single writer (orchestrator process). Readers are advisory: CLI list, snapshot
exporter, future Phase 7 dashboard. PRAGMA journal_mode=WAL gives readers
non-blocking reads while the orchestrator inserts.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# Order matches the leaderboard table column order so positional binding works.
LEADERBOARD_COLUMNS = (
    "run_id",
    "tournament_id",
    "architecture",
    "symbol",
    "horizon",
    "target_mode",
    "hp_hash",
    "r2_returns",
    "dir_acc_corrected",
    "oos_sharpe",
    "psr",
    "dsr",
    "cpcv_dsr",
    "train_seconds",
    "git_sha",
    "tournament_start_ts",
    "train_window_includes_contaminated",
    "status",
    "failure_reason",
    "failure_stderr_tail",
)

# Raw literal INSERT — column list and ? placeholders are compile-time constants.
# All values are bound via positional ? placeholders (T-03-08: no value interpolation).
_INSERT_LEADERBOARD_SQL = (
    "INSERT INTO leaderboard ("
    "run_id, tournament_id, architecture, symbol, horizon, target_mode, hp_hash, "
    "r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr, train_seconds, "
    "git_sha, tournament_start_ts, train_window_includes_contaminated, "
    "status, failure_reason, failure_stderr_tail"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def run_migrations(
    db_path: str | os.PathLike, migrations_dir: str | os.PathLike
) -> None:
    """Apply numbered SQL files in order. Idempotent via schema_version + IF NOT EXISTS (D-17)."""
    db_path = Path(db_path)
    migrations_dir = Path(migrations_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_fresh = not db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        # Set restrictive perms on first creation (T-03-09)
        if is_fresh:
            try:
                os.chmod(db_path, 0o600)
            except OSError as e:  # filesystem may not support chmod (Windows shares)
                logger.warning("could not chmod %s to 0600: %s", db_path, e)
        # WAL mode for non-blocking reads while orchestrator writes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        # Bootstrap schema_version (no-op after first run)
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, "
            " applied_at TEXT NOT NULL DEFAULT (datetime('now')), "
            " description TEXT NOT NULL);"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
        for sql_file in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            try:
                version = int(sql_file.stem.split("_", 1)[0])
            except ValueError:
                logger.warning("skipping non-numbered migration: %s", sql_file)
                continue
            if version in applied:
                continue
            logger.info("applying migration %s", sql_file.name)
            conn.executescript(sql_file.read_text())
            conn.commit()
        # Verify (idempotency invariant): schema_version max should equal max-on-disk version
        on_disk = {
            int(p.stem.split("_", 1)[0])
            for p in migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")
        }
        if on_disk:
            applied_after = {
                row[0] for row in conn.execute("SELECT version FROM schema_version")
            }
            missing = on_disk - applied_after
            if missing:
                raise RuntimeError(f"migrations failed to apply: {sorted(missing)}")
    finally:
        conn.close()


class LeaderboardDB:
    """Thin sqlite3 wrapper. Single-writer, raw parameterised SQL only (no ORM)."""

    def __init__(self, db_path: str | os.PathLike):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON;")

    def close(self) -> None:
        self.conn.close()

    def schema_version(self) -> int:
        cur = self.conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
        return int(cur.fetchone()[0])

    def upsert_tournament(
        self, tournament_id: str, config_yaml: str, git_sha: str, seed: int
    ) -> None:
        # ON CONFLICT UPDATE for idempotent re-runs (same tournament_id = same config)
        self.conn.execute(
            """
            INSERT INTO tournaments (tournament_id, config_yaml, git_sha, seed)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tournament_id) DO UPDATE SET
                config_yaml = excluded.config_yaml,
                git_sha     = excluded.git_sha,
                seed        = excluded.seed
            """,
            (tournament_id, config_yaml, git_sha, int(seed)),
        )
        self.conn.commit()

    def update_tournament_counts(
        self,
        tournament_id: str,
        n_total: int,
        n_success: int,
        n_failed: int,
        completed: bool = False,
    ) -> None:
        if completed:
            self.conn.execute(
                """UPDATE tournaments
                   SET n_experiments_total=?, n_experiments_success=?, n_experiments_failed=?,
                       completed_at=datetime('now')
                   WHERE tournament_id=?""",
                (n_total, n_success, n_failed, tournament_id),
            )
        else:
            self.conn.execute(
                """UPDATE tournaments
                   SET n_experiments_total=?, n_experiments_success=?, n_experiments_failed=?
                   WHERE tournament_id=?""",
                (n_total, n_success, n_failed, tournament_id),
            )
        self.conn.commit()

    def insert_run(self, normalised_result: Dict[str, Any]) -> None:
        """Insert one leaderboard row. Caller MUST pass result_schema.validate output."""
        metrics = normalised_result.get("metrics", {}) or {}
        row = (
            normalised_result["run_id"],
            normalised_result["tournament_id"],
            normalised_result["architecture"],
            normalised_result["symbol"],
            int(normalised_result["horizon"]),
            normalised_result["target_mode"],
            normalised_result["hp_hash"],
            metrics.get("r2_returns"),
            metrics.get("dir_acc_corrected"),
            metrics.get("oos_sharpe"),
            metrics.get("psr"),
            metrics.get("dsr"),
            metrics.get("cpcv_dsr"),
            metrics.get("train_seconds"),
            normalised_result["git_sha"],
            normalised_result["tournament_start_ts"],
            int(bool(normalised_result.get("train_window_includes_contaminated", 0))),
            normalised_result["status"],
            normalised_result.get("failure_reason"),
            normalised_result.get("failure_stderr_tail"),
        )
        self.conn.execute(_INSERT_LEADERBOARD_SQL, row)
        self.conn.commit()

    def list_runs(
        self,
        tournament_id: Optional[str] = None,
        architecture: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        # Fixed SQL with nullable equality pattern: (? IS NULL OR col = ?)
        # All filter values are bound as ? params — no string interpolation of values (T-03-08).
        _LIST_SQL = (
            "SELECT * FROM leaderboard"
            " WHERE (? IS NULL OR tournament_id = ?)"
            "   AND (? IS NULL OR architecture = ?)"
            "   AND (? IS NULL OR symbol = ?)"
            "   AND (? IS NULL OR status = ?)"
            " ORDER BY created_at DESC LIMIT ?"
        )
        params = (
            tournament_id,
            tournament_id,
            architecture,
            architecture,
            symbol,
            symbol,
            status,
            status,
            int(limit),
        )
        cur = self.conn.execute(_LIST_SQL, params)
        return [dict(row) for row in cur.fetchall()]

    def get_tournament_config(self, tournament_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM tournaments WHERE tournament_id = ?", (tournament_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
