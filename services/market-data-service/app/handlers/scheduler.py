"""
Scheduler Control Endpoint Handlers
Extracted from main.py - Responsibility: Automated data collection scheduler management

Handles:
- Scheduler status endpoint
- Scheduler start endpoint
- Scheduler stop endpoint
- Manual collection trigger endpoint
"""

import logging
from fastapi import HTTPException, Depends

from app.scheduler import (
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    run_manual_collection
)
from app.auth import verify_api_key

logger = logging.getLogger(__name__)


async def get_scheduler_status_handler() -> dict:
    """
    Get scheduler status and job information

    Returns detailed information about the automated data collection scheduler
    including running status, configured jobs, and next run times.

    Returns:
        dict: Scheduler status with job details

    Raises:
        HTTPException: 500 if status retrieval fails
    """
    try:
        status = get_scheduler_status()
        return {
            "success": True,
            "scheduler": status
        }
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get scheduler status")


async def start_scheduler_handler(api_key: str = Depends(verify_api_key)) -> dict:
    """
    Manually start the scheduler

    Starts the automated data collection scheduler. The scheduler will run
    periodic jobs to collect market data for configured symbols.

    Requires API key authentication for security.

    Args:
        api_key: API key for authentication (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException: 500 if scheduler start fails
    """
    try:
        start_scheduler()
        logger.info("Scheduler started via API")
        return {
            "success": True,
            "message": "Scheduler started successfully"
        }
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def stop_scheduler_handler(api_key: str = Depends(verify_api_key)) -> dict:
    """
    Manually stop the scheduler

    Stops the automated data collection scheduler. No new scheduled jobs
    will be executed until the scheduler is started again.

    Requires API key authentication for security.

    Args:
        api_key: API key for authentication (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException: 500 if scheduler stop fails
    """
    try:
        stop_scheduler()
        logger.info("Scheduler stopped via API")
        return {
            "success": True,
            "message": "Scheduler stopped successfully"
        }
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def trigger_manual_collection_handler(api_key: str = Depends(verify_api_key)) -> dict:
    """
    Manually trigger a full data collection cycle

    Executes an immediate data collection cycle for all configured symbols.
    Collects both ticker and kline data.

    Useful for testing or forcing an immediate update outside of the
    scheduled collection times.

    Requires API key authentication for security.

    Args:
        api_key: API key for authentication (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException: 500 if collection fails
    """
    try:
        logger.info("Manual data collection triggered via API")
        await run_manual_collection()
        return {
            "success": True,
            "message": "Manual data collection completed"
        }
    except Exception as e:
        logger.error(f"Error during manual collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))
