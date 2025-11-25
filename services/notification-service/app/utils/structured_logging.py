# Notification Service - Structured Logging Module
# Minimal local implementation for Docker container

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar

# Context variable for request context
request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': record.levelname,
            'name': record.name,
            'message': record.getMessage(),
        }
        # Add extra fields
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        # Add context
        ctx = request_context.get()
        if ctx:
            log_entry.update(ctx)
        return json.dumps(log_entry)


class RequestContextLogger:
    """Logger with request context support"""

    def __init__(self, name: str = __name__):
        self.logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, **kwargs) -> None:
        extra = {'extra': kwargs} if kwargs else {}
        self.logger.log(level, msg, extra=extra)

    def info(self, msg: str, **kwargs) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def debug(self, msg: str, **kwargs) -> None:
        self._log(logging.DEBUG, msg, **kwargs)


def setup_logging(
    service_name: str = 'notification-service',
    log_level: str = 'INFO',
    structured: bool = True
) -> None:
    """Configure logging for the service"""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Get root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    root.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler()
    handler.setLevel(level)

    if structured:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

    root.addHandler(handler)
