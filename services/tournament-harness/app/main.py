"""Tournament Harness — Main Application.

Read-only status / leaderboard inspection API per CD-07. Mutation paths
(start tournament, export-snapshot) live in app/cli.py — landed in 03-08.
This skeleton ships the FastAPI surface so the container boots and exposes
/health for the compose healthcheck. Listing endpoints are stubs at this
plan boundary; LeaderboardDB wiring lands in 03-08.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings

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
# TOURNAMENT INSPECTION (read-only stubs; LeaderboardDB wiring lands in 03-08)
# ============================================================================


@app.get("/api/v1/tournaments", tags=["Tournament"])
async def list_tournaments():
    """List tournaments.

    Stub — returns an empty list at this plan boundary so the surface is
    honest. Full implementation arrives in 03-08 once the LeaderboardDB
    layer exists.
    """
    try:
        return {"success": True, "count": 0, "tournaments": []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tournaments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tournaments/{tournament_id}", tags=["Tournament"])
async def get_tournament(tournament_id: str):
    """Get a tournament's runs.

    Stub — returns an empty runs list at this plan boundary. Full
    implementation arrives in 03-08.
    """
    try:
        return {
            "success": True,
            "tournament_id": tournament_id,
            "runs": [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching tournament {tournament_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
