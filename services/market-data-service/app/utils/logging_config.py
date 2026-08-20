"""
Logging Configuration Utilities
Extracted from main.py - Responsibility: Structured logging with secret masking

Provides:
- SecretMaskingFormatter: JSON formatter that masks sensitive data
- setup_logging(): Configure structured JSON logging
"""

import logging
import re
# python-json-logger>=3 moved JsonFormatter into pythonjsonlogger.json;
# importing the legacy `jsonlogger` module emits a DeprecationWarning on
# 4.x. Try the new path first, fall back for python-json-logger<3.
try:
    from pythonjsonlogger import json as jsonlogger  # type: ignore[import]
except ImportError:  # pragma: no cover - only on python-json-logger<3
    from pythonjsonlogger import jsonlogger  # type: ignore[no-redef]


class SecretMaskingFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that masks sensitive data in logs"""

    SECRET_PATTERNS = [
        (re.compile(r'(api_key["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(api_secret["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(password["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(token["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(bearer\s+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(authorization["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'([?&]key=)([^&\s]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'([?&]secret=)([^&\s]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(postgres://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1***MASKED***\3'),
        (re.compile(r'(redis://[^:]*:)([^@]+)(@)', re.IGNORECASE), r'\1***MASKED***\3'),
    ]

    def format(self, record):
        """Format log record and apply secret masking"""
        # Get the formatted message
        message = super().format(record)

        # Apply all masking patterns
        for pattern, replacement in self.SECRET_PATTERNS:
            message = pattern.sub(replacement, message)

        return message


def setup_logging():
    """
    Configure structured JSON logging with secret masking

    Sets up:
    - JSON formatted log messages
    - Secret masking for sensitive data
    - INFO level logging
    - Suppression of noisy HTTP loggers
    """
    log_handler = logging.StreamHandler()
    formatter = SecretMaskingFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    log_handler.setFormatter(formatter)

    logging.root.addHandler(log_handler)
    logging.root.setLevel(logging.INFO)

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
