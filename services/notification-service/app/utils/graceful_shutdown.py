# Notification Service - Graceful Shutdown Handler
# Minimal local implementation for Docker container

import signal
import asyncio
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class GracefulShutdownHandler:
    """Handles graceful shutdown of the service"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.shutdown_requested = False
        self._callbacks: List[Callable] = []

    def register(self, callback: Callable) -> None:
        """Register a cleanup callback"""
        self._callbacks.append(callback)

    async def shutdown(self) -> None:
        """Execute all shutdown callbacks"""
        self.shutdown_requested = True
        logger.info("Shutting down gracefully...")

        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error during shutdown callback: {e}")

        logger.info("Shutdown complete")

    def setup_signals(self) -> None:
        """Setup signal handlers for graceful shutdown"""
        loop = asyncio.get_event_loop()

        def handle_signal(sig: signal.Signals) -> None:
            logger.info(f"Received signal {sig.name}")
            loop.create_task(self.shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, handle_signal, sig)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: asyncio.ensure_future(self.shutdown()))

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been requested"""
        return self.shutdown_requested
