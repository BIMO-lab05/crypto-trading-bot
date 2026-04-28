# Notification Service - Structured Logging Module
# Minimal local implementation for Docker container

import logging
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar

# Context variable for request context
request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


# Telegram bot token in URL form: /bot<numeric_id>:<35+ chars>
_TELEGRAM_URL_TOKEN = re.compile(r"/bot\d{6,}:[A-Za-z0-9_-]{30,}")
# Bare Telegram bot token (e.g. logged as a string): <numeric_id>:<35+ chars>
_TELEGRAM_BARE_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b")


def _redact_telegram_token(text: str) -> str:
    text = _TELEGRAM_URL_TOKEN.sub("/bot<REDACTED>", text)
    text = _TELEGRAM_BARE_TOKEN.sub("<REDACTED_TELEGRAM_TOKEN>", text)
    return text


class TelegramTokenRedactionFilter(logging.Filter):
    """Strip Telegram bot tokens from any log record before it is emitted.

    httpx logs request URLs at INFO, which would otherwise expose
    `https://api.telegram.org/bot<TOKEN>/sendMessage` in container logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            return True
        redacted = _redact_telegram_token(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = None
        return True


def install_token_redaction() -> None:
    """Attach the Telegram-token redaction filter to every root handler.

    Filters on a Logger only run for records emitted by that logger, not
    descendants — so the filter must live on Handlers to catch httpx logs
    that propagate up to the root handler. Idempotent per handler.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if any(isinstance(f, TelegramTokenRedactionFilter) for f in handler.filters):
            continue
        handler.addFilter(TelegramTokenRedactionFilter())


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

    handler.addFilter(TelegramTokenRedactionFilter())
    root.addHandler(handler)
