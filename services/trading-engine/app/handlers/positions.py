"""
Position Endpoint Handlers
Extracted from main.py - Responsibility: Position management endpoints

Handles position querying and retrieval.
"""

import logging
import time
from uuid import UUID
from fastapi import HTTPException

from app.position_manager import get_position_manager
from app.models import PositionListResponse, PositionResponse

logger = logging.getLogger(__name__)


async def get_positions(status: str = "all") -> PositionListResponse:
    """
    Get positions with optional status filter

    Args:
        status: Filter by status (all, open, closed)

    Returns:
        PositionListResponse with list of positions

    Raises:
        HTTPException: If position retrieval fails
    """
    try:
        position_manager = get_position_manager()

        if status == "open":
            positions = position_manager.get_open_positions()
        elif status == "closed":
            positions = position_manager.get_closed_positions()
        else:
            positions = position_manager.get_all_positions()

        return PositionListResponse(
            success=True,
            positions=positions,
            count=len(positions),
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_position(position_id: str) -> PositionResponse:
    """
    Get specific position by ID

    Args:
        position_id: UUID of the position

    Returns:
        PositionResponse with position details

    Raises:
        HTTPException: If position not found or ID invalid
    """
    try:
        position_manager = get_position_manager()
        position = position_manager.get_position(UUID(position_id))

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        return PositionResponse(
            success=True,
            position=position,
            timestamp=int(time.time() * 1000)
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid position ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
