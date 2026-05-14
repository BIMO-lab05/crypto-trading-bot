"""Tournament Harness — Main Application.

Read-only status / leaderboard inspection API per CD-07. Mutation paths
(start tournament, export-snapshot) live in app/cli.py — landed in 03-08.
"""

import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.leaderboard.db import LeaderboardDB

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle.

    No scheduler (D-12 — start is operator-driven via CLI), no DB-init side
    effects on boot. Migrations run lazily on the first orchestrator CLI
    invocation, not at API startup.
    """
    logger.info("=" * 60)
    logger.info(f"Starting {settings.service_name}")
    logger.info("=" * 60)
    logger.info(f"Service ready on {settings.service_host}:{settings.service_port}")
    yield
    logger.info("Service stopped")


app = FastAPI(
    title="Tournament Harness",
    description=(
        "Read-only status / leaderboard inspection. Mutation via CLI only (CD-07)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH CHECK
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check — returns basic service status."""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# TOURNAMENT INSPECTION (read-only; LeaderboardDB wired in 03-08)
# ============================================================================


@app.get("/api/v1/tournaments", tags=["Tournament"])
async def list_tournaments(limit: int = Query(default=100, le=1000)):
    """List tournaments ordered by start time descending."""
    try:
        db = LeaderboardDB(settings.leaderboard_db_path)
        try:
            cur = db.conn.execute(
                "SELECT tournament_id, started_at, completed_at, "
                "n_experiments_total, n_experiments_success, n_experiments_failed "
                "FROM tournaments ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        finally:
            db.close()
        return {"success": True, "count": len(rows), "tournaments": rows}
    except HTTPException:
        raise
    except sqlite3.OperationalError:
        # DB doesn't yet exist (no tournaments run) — return empty list
        return {"success": True, "count": 0, "tournaments": []}
    except Exception as e:
        logger.error(f"list_tournaments failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tournaments/{tournament_id}/runs", tags=["Tournament"])
async def list_runs(
    tournament_id: str,
    architecture: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, description="success | failed"),
    limit: int = Query(default=100, le=1000),
):
    """List leaderboard rows for a tournament."""
    try:
        db = LeaderboardDB(settings.leaderboard_db_path)
        try:
            rows = db.list_runs(
                tournament_id=tournament_id,
                architecture=architecture,
                symbol=symbol,
                status=status,
                limit=limit,
            )
        finally:
            db.close()
        return {"success": True, "count": len(rows), "runs": rows}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"list_runs failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
