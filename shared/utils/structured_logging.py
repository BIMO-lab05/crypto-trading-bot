"""
Structured Logging Module
Provides JSON-formatted logging for better observability and log aggregation
"""

import logging
import json
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from pythonjsonlogger import jsonlogger


class StructuredLogger:
    """
    Structured logger with JSON formatting for production use

    Features:
    - JSON formatted logs for easy parsing
    - Automatic context injection (service name, environment, etc.)
    - Request ID tracking for distributed tracing
    - Error tracking with stack traces
    - Performance metrics logging
    """

    def __init__(
        self,
        service_name: str,
        environment: str = "development",
        log_level: str = "INFO",
        enable_console: bool = True,
        enable_file: bool = True,
        log_file: Optional[str] = None
    ):
        self.service_name = service_name
        self.environment = environment
        self.log_level = getattr(logging, log_level.upper())
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(self.log_level)
        self.logger.handlers = []  # Clear existing handlers

        # Create formatters
        self.json_formatter = self._create_json_formatter()
        self.console_formatter = self._create_console_formatter()

        # Add handlers
        if enable_console:
            self._add_console_handler()

        if enable_file:
            log_file = log_file or f"/app/logs/{service_name}.log"
            self._add_file_handler(log_file)

    def _create_json_formatter(self) -> jsonlogger.JsonFormatter:
        """Create JSON formatter with custom fields"""
        format_str = '%(asctime)s %(name)s %(levelname)s %(message)s'

        class CustomJsonFormatter(jsonlogger.JsonFormatter):
            def add_fields(self, log_record, record, message_dict):
                super().add_fields(log_record, record, message_dict)
                # Add custom fields
                log_record['service'] = self.service_name
                log_record['environment'] = self.environment
                log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'

                # Add exception info if present
                if record.exc_info:
                    log_record['exception'] = {
                        'type': record.exc_info[0].__name__,
                        'message': str(record.exc_info[1]),
                        'traceback': traceback.format_exception(*record.exc_info)
                    }

        return CustomJsonFormatter(format_str)

    def _create_console_formatter(self) -> logging.Formatter:
        """Create human-readable formatter for console"""
        return logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def _add_console_handler(self):
        """Add console handler with appropriate formatter"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)

        # Use JSON in production, human-readable in development
        if self.environment == "production":
            console_handler.setFormatter(self.json_formatter)
        else:
            console_handler.setFormatter(self.console_formatter)

        self.logger.addHandler(console_handler)

    def _add_file_handler(self, log_file: str):
        """Add file handler with JSON formatting"""
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(self.json_formatter)
            self.logger.addHandler(file_handler)
        except (IOError, OSError) as e:
            self.logger.warning(f"Could not create file handler: {e}")

    def _build_log_data(self, message: str, **kwargs) -> Dict[str, Any]:
        """Build log data with message and additional fields"""
        log_data = {"msg": message}
        log_data.update(kwargs)
        return log_data

    def debug(self, message: str, **kwargs):
        """Log debug message with additional context"""
        self.logger.debug(json.dumps(self._build_log_data(message, **kwargs)))

    def info(self, message: str, **kwargs):
        """Log info message with additional context"""
        self.logger.info(json.dumps(self._build_log_data(message, **kwargs)))

    def warning(self, message: str, **kwargs):
        """Log warning message with additional context"""
        self.logger.warning(json.dumps(self._build_log_data(message, **kwargs)))

    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log error message with exception details"""
        log_data = self._build_log_data(message, **kwargs)

        if error:
            log_data['error'] = {
                'type': type(error).__name__,
                'message': str(error),
                'traceback': traceback.format_exc()
            }

        self.logger.error(json.dumps(log_data))

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log critical message with exception details"""
        log_data = self._build_log_data(message, **kwargs)

        if error:
            log_data['error'] = {
                'type': type(error).__name__,
                'message': str(error),
                'traceback': traceback.format_exc()
            }

        self.logger.critical(json.dumps(log_data))

    def log_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        **kwargs
    ):
        """Log API request with performance metrics"""
        self.info(
            "API request",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            **kwargs
        )

    def log_database_query(
        self,
        query_type: str,
        table: str,
        duration_ms: float,
        rows_affected: Optional[int] = None,
        **kwargs
    ):
        """Log database query with performance metrics"""
        self.info(
            "Database query",
            query_type=query_type,
            table=table,
            duration_ms=duration_ms,
            rows_affected=rows_affected,
            **kwargs
        )

    def log_external_api_call(
        self,
        api_name: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        **kwargs
    ):
        """Log external API call with performance metrics"""
        self.info(
            "External API call",
            api_name=api_name,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            **kwargs
        )

    def log_trade_execution(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: str,
        **kwargs
    ):
        """Log trade execution"""
        self.info(
            "Trade executed",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
            **kwargs
        )

    def log_circuit_breaker_event(
        self,
        breaker_name: str,
        event: str,
        state: str,
        **kwargs
    ):
        """Log circuit breaker state changes"""
        self.warning(
            "Circuit breaker event",
            breaker_name=breaker_name,
            event=event,
            state=state,
            **kwargs
        )

    def log_metric(
        self,
        metric_name: str,
        value: float,
        unit: str,
        tags: Optional[Dict[str, str]] = None
    ):
        """Log custom metric"""
        self.info(
            "Metric",
            metric_name=metric_name,
            value=value,
            unit=unit,
            tags=tags or {}
        )


class RequestContextLogger:
    """
    Context manager for request-scoped logging
    Automatically adds request ID and user context to all logs
    """

    def __init__(
        self,
        logger: StructuredLogger,
        request_id: str,
        user_id: Optional[str] = None,
        **context
    ):
        self.logger = logger
        self.request_id = request_id
        self.user_id = user_id
        self.context = context

    def _add_context(self, kwargs: Dict) -> Dict:
        """Add request context to log kwargs"""
        kwargs['request_id'] = self.request_id
        if self.user_id:
            kwargs['user_id'] = self.user_id
        kwargs.update(self.context)
        return kwargs

    def debug(self, message: str, **kwargs):
        self.logger.debug(message, **self._add_context(kwargs))

    def info(self, message: str, **kwargs):
        self.logger.info(message, **self._add_context(kwargs))

    def warning(self, message: str, **kwargs):
        self.logger.warning(message, **self._add_context(kwargs))

    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        self.logger.error(message, error=error, **self._add_context(kwargs))

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs):
        self.logger.critical(message, error=error, **self._add_context(kwargs))


def setup_logging(
    service_name: str,
    environment: str = "development",
    log_level: str = "INFO",
    log_file: Optional[str] = None
) -> StructuredLogger:
    """
    Setup structured logging for a service

    Args:
        service_name: Name of the service
        environment: Environment (development/production)
        log_level: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        log_file: Optional log file path

    Returns:
        Configured StructuredLogger instance

    Usage:
        logger = setup_logging("trading-engine", "production", "INFO")
        logger.info("Service started", version="1.0.0")
    """
    return StructuredLogger(
        service_name=service_name,
        environment=environment,
        log_level=log_level,
        log_file=log_file
    )


# Performance logging decorator
def log_performance(logger: StructuredLogger, operation: str):
    """
    Decorator to log function performance

    Usage:
        @log_performance(logger, "calculate_indicators")
        def calculate_rsi(data):
            # Function implementation
            pass
    """
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"{operation} completed",
                    operation=operation,
                    duration_ms=duration_ms,
                    status="success"
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"{operation} failed",
                    operation=operation,
                    duration_ms=duration_ms,
                    status="error",
                    error=e
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"{operation} completed",
                    operation=operation,
                    duration_ms=duration_ms,
                    status="success"
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"{operation} failed",
                    operation=operation,
                    duration_ms=duration_ms,
                    status="error",
                    error=e
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
