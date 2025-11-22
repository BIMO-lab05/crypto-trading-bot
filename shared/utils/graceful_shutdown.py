"""
Graceful Shutdown Handler
Ensures clean shutdown of services with proper resource cleanup
"""

import signal
import asyncio
import logging
from typing import List, Callable, Optional, Awaitable
from functools import wraps

logger = logging.getLogger(__name__)


class GracefulShutdownHandler:
    """
    Handles graceful shutdown of services

    Features:
    - Signal handling (SIGTERM, SIGINT)
    - Ordered cleanup execution
    - Timeout protection
    - Resource cleanup tracking
    - Background task cancellation
    """

    def __init__(
        self,
        shutdown_timeout: float = 30.0,
        service_name: str = "unknown"
    ):
        self.shutdown_timeout = shutdown_timeout
        self.service_name = service_name
        self.cleanup_handlers: List[Callable] = []
        self.background_tasks: List[asyncio.Task] = []
        self.is_shutting_down = False
        self._shutdown_event = asyncio.Event()

    def register_cleanup(self, handler: Callable):
        """
        Register a cleanup handler to be called on shutdown

        Handlers are called in reverse registration order (LIFO)

        Args:
            handler: Sync or async cleanup function

        Usage:
            shutdown_handler.register_cleanup(database.close)
            shutdown_handler.register_cleanup(lambda: logger.info("Goodbye!"))
        """
        self.cleanup_handlers.append(handler)
        logger.debug(f"Registered cleanup handler: {handler.__name__}")

    def register_background_task(self, task: asyncio.Task):
        """
        Register a background task for cancellation on shutdown

        Args:
            task: AsyncIO task to cancel

        Usage:
            task = asyncio.create_task(worker())
            shutdown_handler.register_background_task(task)
        """
        self.background_tasks.append(task)
        logger.debug(f"Registered background task: {task.get_name()}")

    async def _execute_cleanup(self):
        """Execute all cleanup handlers in reverse order"""
        logger.info(f"Executing {len(self.cleanup_handlers)} cleanup handlers...")

        # Execute in reverse order (LIFO)
        for handler in reversed(self.cleanup_handlers):
            try:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.debug(f"Executing cleanup: {handler_name}")

                if asyncio.iscoroutinefunction(handler):
                    await asyncio.wait_for(
                        handler(),
                        timeout=self.shutdown_timeout / len(self.cleanup_handlers)
                    )
                else:
                    handler()

                logger.debug(f"Cleanup completed: {handler_name}")

            except asyncio.TimeoutError:
                logger.error(f"Cleanup timeout: {handler_name}")
            except Exception as e:
                logger.error(f"Cleanup error in {handler_name}: {e}")

    async def _cancel_background_tasks(self):
        """Cancel all registered background tasks"""
        if not self.background_tasks:
            return

        logger.info(f"Cancelling {len(self.background_tasks)} background tasks...")

        # Cancel all tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.background_tasks, return_exceptions=True),
                timeout=self.shutdown_timeout
            )
            logger.info("All background tasks cancelled")
        except asyncio.TimeoutError:
            logger.warning("Background task cancellation timeout")

    async def shutdown(self):
        """
        Perform graceful shutdown

        Execution order:
        1. Set shutdown flag
        2. Cancel background tasks
        3. Execute cleanup handlers (LIFO)
        4. Set shutdown event
        """
        if self.is_shutting_down:
            logger.warning("Shutdown already in progress")
            return

        self.is_shutting_down = True
        logger.info(f"Starting graceful shutdown of {self.service_name}...")

        try:
            # Cancel background tasks
            await self._cancel_background_tasks()

            # Execute cleanup handlers
            await self._execute_cleanup()

            logger.info(f"Graceful shutdown of {self.service_name} completed")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        finally:
            self._shutdown_event.set()

    async def wait_for_shutdown(self):
        """Wait for shutdown to complete"""
        await self._shutdown_event.wait()

    def setup_signal_handlers(self):
        """
        Setup signal handlers for SIGTERM and SIGINT

        Usage:
            shutdown_handler = GracefulShutdownHandler()
            shutdown_handler.setup_signal_handlers()
        """
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating shutdown...")
            asyncio.create_task(self.shutdown())

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        logger.info("Signal handlers registered (SIGTERM, SIGINT)")


class ShutdownContext:
    """
    Context manager for automatic cleanup on shutdown

    Usage:
        async with ShutdownContext(shutdown_handler, "database"):
            db = await connect_database()
            shutdown_handler.register_cleanup(db.close)
            # Use database
        # Automatically cleaned up
    """

    def __init__(self, handler: GracefulShutdownHandler, resource_name: str):
        self.handler = handler
        self.resource_name = resource_name
        self.cleanup_func: Optional[Callable] = None

    async def __aenter__(self):
        logger.debug(f"Acquiring resource: {self.resource_name}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.debug(f"Releasing resource: {self.resource_name}")
        if self.cleanup_func:
            self.handler.register_cleanup(self.cleanup_func)

    def on_cleanup(self, func: Callable):
        """Register cleanup function"""
        self.cleanup_func = func


def with_graceful_shutdown(shutdown_handler: GracefulShutdownHandler):
    """
    Decorator to wrap service main function with graceful shutdown

    Usage:
        @with_graceful_shutdown(shutdown_handler)
        async def main():
            # Service code
            await asyncio.sleep(1000)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Run the main function
                await func(*args, **kwargs)
            except asyncio.CancelledError:
                logger.info("Service cancelled, shutting down...")
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt, shutting down...")
            except Exception as e:
                logger.error(f"Service error: {e}", exc_info=True)
            finally:
                # Always perform graceful shutdown
                await shutdown_handler.shutdown()

        return wrapper
    return decorator


class HealthCheckServer:
    """
    Simple health check server that responds during shutdown

    Allows load balancers to know when service is shutting down
    """

    def __init__(
        self,
        shutdown_handler: GracefulShutdownHandler,
        port: int = 8000
    ):
        self.shutdown_handler = shutdown_handler
        self.port = port
        self.server: Optional[asyncio.Server] = None

    async def health_handler(self, reader, writer):
        """Handle health check requests"""
        try:
            # Read request
            data = await reader.read(1024)

            if self.shutdown_handler.is_shutting_down:
                # Return 503 Service Unavailable during shutdown
                response = (
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: application/json\r\n"
                    b"\r\n"
                    b'{"status": "shutting_down"}\r\n'
                )
            else:
                # Return 200 OK during normal operation
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"\r\n"
                    b'{"status": "healthy"}\r\n'
                )

            writer.write(response)
            await writer.drain()

        except Exception as e:
            logger.error(f"Health check error: {e}")

        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        """Start health check server"""
        self.server = await asyncio.start_server(
            self.health_handler,
            '0.0.0.0',
            self.port
        )
        logger.info(f"Health check server started on port {self.port}")

    async def stop(self):
        """Stop health check server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Health check server stopped")


# Example usage function
async def example_service():
    """
    Example showing how to use GracefulShutdownHandler

    This demonstrates proper service structure with:
    - Signal handling
    - Database connections
    - Background tasks
    - Cleanup handlers
    """
    # Create shutdown handler
    shutdown_handler = GracefulShutdownHandler(
        shutdown_timeout=30.0,
        service_name="example-service"
    )

    # Setup signal handlers
    shutdown_handler.setup_signal_handlers()

    # Initialize database (example)
    # db = await connect_database()
    # shutdown_handler.register_cleanup(db.close)

    # Start background task (example)
    async def background_worker():
        try:
            while True:
                logger.info("Working...")
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Worker cancelled")

    task = asyncio.create_task(background_worker())
    shutdown_handler.register_background_task(task)

    # Register cleanup handlers
    shutdown_handler.register_cleanup(
        lambda: logger.info("Final cleanup executed")
    )

    # Wait for shutdown signal
    logger.info("Service running... Press Ctrl+C to shutdown")
    await shutdown_handler.wait_for_shutdown()

    logger.info("Service stopped")


if __name__ == "__main__":
    # Run example
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_service())
