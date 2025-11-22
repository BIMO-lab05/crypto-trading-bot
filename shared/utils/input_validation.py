"""
Input Validation Middleware
Protects against injection attacks, XSS, and malformed requests

Features:
- SQL injection pattern detection
- XSS attempt blocking
- Path traversal prevention
- Payload size limits
- JSON validation
- Header sanitization
"""

import re
import json
import logging
from typing import List, Optional, Pattern, Set
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class SecurityPatterns:
    """Security patterns for detecting malicious input"""

    # SQL Injection Patterns
    SQL_INJECTION: List[str] = [
        r"(\%27)|(\')|(\-\-)|(\%23)|(#)",  # SQL comments and quotes
        r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",  # SQL operators
        r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",  # OR injection
        r"((\%27)|(\'))union",  # UNION attacks
        r"exec(\s|\+)+(s|x)p\w+",  # Stored procedures
        r"execute\s+immediate",  # Oracle injection
        r"UNION.*SELECT",  # UNION SELECT
        r"INSERT\s+INTO",  # INSERT injection
        r"DELETE\s+FROM",  # DELETE injection
        r"DROP\s+(TABLE|DATABASE)",  # DROP attacks
        r"UPDATE\s+.*SET",  # UPDATE injection
    ]

    # XSS (Cross-Site Scripting) Patterns
    XSS_PATTERNS: List[str] = [
        r"<script[^>]*>.*?</script>",  # Script tags
        r"javascript:",  # JavaScript protocol
        r"onerror\s*=",  # Event handlers
        r"onload\s*=",
        r"onclick\s*=",
        r"onmouseover\s*=",
        r"<iframe[^>]*>",  # Iframe injection
        r"<embed[^>]*>",  # Embed tags
        r"<object[^>]*>",  # Object tags
        r"eval\s*\(",  # Eval function
        r"document\.cookie",  # Cookie stealing
        r"window\.location",  # Redirect attacks
    ]

    # Path Traversal Patterns
    PATH_TRAVERSAL: List[str] = [
        r"\.\.\/",  # Directory traversal
        r"\.\.[\\\/]",  # Windows/Linux traversal
        r"[\\\/]etc[\\\/]passwd",  # Unix password file
        r"[\\\/]windows[\\\/]win\.ini",  # Windows config
        r"file:\/\/",  # File protocol
        r"[\\\/]proc[\\\/]",  # Linux /proc
        r"[\\\/]sys[\\\/]",  # Linux /sys
    ]

    # Command Injection Patterns
    COMMAND_INJECTION: List[str] = [
        r";\s*\w+",  # Command chaining
        r"\|\s*\w+",  # Pipe commands
        r"`.*`",  # Backtick execution
        r"\$\(.*\)",  # Command substitution
        r"&&",  # AND operator
        r"\|\|",  # OR operator
        r">\s*\/",  # Output redirection
        r"<\s*\/",  # Input redirection
    ]

    # LDAP Injection Patterns
    LDAP_INJECTION: List[str] = [
        r"\*\)",  # Wildcard injection
        r"\(\|",  # OR operator
        r"\(&",  # AND operator
        r"\(!(.*)\)",  # NOT operator
    ]

    # XML/XXE Patterns
    XML_INJECTION: List[str] = [
        r"<!DOCTYPE",  # DOCTYPE declaration
        r"<!ENTITY",  # Entity definition
        r"SYSTEM\s+['\"]",  # External entity
        r"<\?xml",  # XML declaration
    ]


class InputValidator:
    """
    Comprehensive input validation for HTTP requests

    Validates:
    - Query parameters
    - Request body
    - Headers
    - Path parameters
    - Content length
    """

    def __init__(
        self,
        max_content_length: int = 10 * 1024 * 1024,  # 10MB default
        max_header_size: int = 8192,  # 8KB headers
        allowed_content_types: Optional[Set[str]] = None,
        enable_sql_check: bool = True,
        enable_xss_check: bool = True,
        enable_path_traversal_check: bool = True,
        enable_command_injection_check: bool = True,
        strict_mode: bool = False
    ):
        self.max_content_length = max_content_length
        self.max_header_size = max_header_size
        self.allowed_content_types = allowed_content_types or {
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain"
        }
        self.enable_sql_check = enable_sql_check
        self.enable_xss_check = enable_xss_check
        self.enable_path_traversal_check = enable_path_traversal_check
        self.enable_command_injection_check = enable_command_injection_check
        self.strict_mode = strict_mode

        # Compile regex patterns for performance
        self.sql_patterns: List[Pattern] = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in SecurityPatterns.SQL_INJECTION
        ]

        self.xss_patterns: List[Pattern] = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in SecurityPatterns.XSS_PATTERNS
        ]

        self.path_patterns: List[Pattern] = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in SecurityPatterns.PATH_TRAVERSAL
        ]

        self.cmd_patterns: List[Pattern] = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in SecurityPatterns.COMMAND_INJECTION
        ]

    def _check_patterns(
        self,
        value: str,
        patterns: List[Pattern],
        attack_type: str
    ) -> Optional[str]:
        """Check if value matches any malicious patterns"""
        for pattern in patterns:
            if pattern.search(value):
                match = pattern.search(value).group()
                logger.warning(
                    f"{attack_type} attempt detected",
                    pattern=pattern.pattern,
                    match=match,
                    value_preview=value[:100]
                )
                return f"{attack_type} pattern detected: {match}"
        return None

    def validate_string(self, value: str, field_name: str = "input") -> None:
        """
        Validate string input against all enabled security patterns

        Args:
            value: String to validate
            field_name: Name of the field (for error messages)

        Raises:
            HTTPException: If malicious pattern detected
        """
        if not isinstance(value, str):
            return  # Skip non-string values

        # Check SQL injection
        if self.enable_sql_check:
            error = self._check_patterns(value, self.sql_patterns, "SQL Injection")
            if error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid input in '{field_name}': {error}"
                )

        # Check XSS
        if self.enable_xss_check:
            error = self._check_patterns(value, self.xss_patterns, "XSS")
            if error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid input in '{field_name}': {error}"
                )

        # Check path traversal
        if self.enable_path_traversal_check:
            error = self._check_patterns(value, self.path_patterns, "Path Traversal")
            if error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid input in '{field_name}': {error}"
                )

        # Check command injection
        if self.enable_command_injection_check:
            error = self._check_patterns(value, self.cmd_patterns, "Command Injection")
            if error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid input in '{field_name}': {error}"
                )

    def validate_dict(self, data: dict, prefix: str = "") -> None:
        """Recursively validate dictionary values"""
        for key, value in data.items():
            field_name = f"{prefix}.{key}" if prefix else key

            if isinstance(value, str):
                self.validate_string(value, field_name)
            elif isinstance(value, dict):
                self.validate_dict(value, field_name)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, str):
                        self.validate_string(item, f"{field_name}[{i}]")
                    elif isinstance(item, dict):
                        self.validate_dict(item, f"{field_name}[{i}]")

    async def validate_request(self, request: Request) -> None:
        """
        Validate entire HTTP request

        Checks:
        1. Content length
        2. Content type
        3. Headers
        4. Query parameters
        5. Request body

        Raises:
            HTTPException: If validation fails
        """

        # 1. Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_content_length:
            logger.warning(
                "Oversized request rejected",
                content_length=content_length,
                max_allowed=self.max_content_length,
                client_ip=request.client.host if request.client else "unknown"
            )
            raise HTTPException(
                status_code=413,
                detail=f"Request too large. Max size: {self.max_content_length} bytes"
            )

        # 2. Check content type
        content_type = request.headers.get("content-type", "").split(";")[0].strip()
        if content_type and content_type not in self.allowed_content_types:
            if self.strict_mode:
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported content type: {content_type}"
                )

        # 3. Validate headers
        total_header_size = sum(len(k) + len(v) for k, v in request.headers.items())
        if total_header_size > self.max_header_size:
            raise HTTPException(
                status_code=431,
                detail="Request headers too large"
            )

        # Validate specific headers
        for key, value in request.headers.items():
            # Skip certain headers
            if key.lower() in ["content-length", "content-type", "host"]:
                continue
            self.validate_string(value, f"header.{key}")

        # 4. Validate query parameters
        for key, value in request.query_params.items():
            self.validate_string(key, f"query_param_key.{key}")
            self.validate_string(value, f"query_param.{key}")

        # 5. Validate path parameters
        if hasattr(request, "path_params"):
            for key, value in request.path_params.items():
                if isinstance(value, str):
                    self.validate_string(value, f"path.{key}")

        # 6. Validate request body (if JSON)
        if request.method in ["POST", "PUT", "PATCH"]:
            if content_type == "application/json":
                try:
                    body = await request.body()
                    if body:
                        data = json.loads(body)
                        if isinstance(data, dict):
                            self.validate_dict(data, "body")
                        elif isinstance(data, list):
                            for i, item in enumerate(data):
                                if isinstance(item, dict):
                                    self.validate_dict(item, f"body[{i}]")
                                elif isinstance(item, str):
                                    self.validate_string(item, f"body[{i}]")
                except json.JSONDecodeError as e:
                    if self.strict_mode:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid JSON: {str(e)}"
                        )


# FastAPI Middleware
class InputValidationMiddleware:
    """
    FastAPI middleware for automatic input validation

    Usage:
        app = FastAPI()
        app.add_middleware(
            InputValidationMiddleware,
            max_content_length=10 * 1024 * 1024,
            strict_mode=False
        )
    """

    def __init__(
        self,
        app,
        max_content_length: int = 10 * 1024 * 1024,
        strict_mode: bool = False,
        **kwargs
    ):
        self.app = app
        self.validator = InputValidator(
            max_content_length=max_content_length,
            strict_mode=strict_mode,
            **kwargs
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Create request
        request = Request(scope, receive)

        # Skip validation for certain paths
        exempt_paths = ["/health", "/metrics", "/docs", "/openapi.json"]
        if any(request.url.path.startswith(path) for path in exempt_paths):
            return await self.app(scope, receive, send)

        try:
            # Validate request
            await self.validator.validate_request(request)

        except HTTPException as e:
            # Return error response
            response = JSONResponse(
                status_code=e.status_code,
                content={"error": e.detail}
            )
            await response(scope, receive, send)
            return

        # Continue with request
        await self.app(scope, receive, send)


# Utility functions
def sanitize_input(value: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize user input by removing potentially dangerous characters

    Args:
        value: Input string to sanitize
        max_length: Optional maximum length

    Returns:
        Sanitized string
    """
    # Remove null bytes
    value = value.replace("\x00", "")

    # Remove control characters (except newline, tab, carriage return)
    value = "".join(char for char in value if char >= " " or char in "\n\t\r")

    # Trim to max length
    if max_length and len(value) > max_length:
        value = value[:max_length]

    return value.strip()


def is_safe_filename(filename: str) -> bool:
    """
    Check if filename is safe (no path traversal, special chars)

    Args:
        filename: Filename to check

    Returns:
        True if safe, False otherwise
    """
    # Reject empty or suspicious names
    if not filename or filename in [".", "..", "/"]:
        return False

    # Reject path separators
    if any(char in filename for char in ["/", "\\", "\x00"]):
        return False

    # Reject control characters
    if any(ord(char) < 32 for char in filename):
        return False

    return True


def validate_email(email: str) -> bool:
    """Simple email validation"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_url(url: str, allowed_schemes: Optional[List[str]] = None) -> bool:
    """Validate URL with optional scheme whitelist"""
    if allowed_schemes is None:
        allowed_schemes = ["http", "https"]

    pattern = r"^(https?|ftp):\/\/[^\s/$.?#].[^\s]*$"
    if not re.match(pattern, url):
        return False

    # Check scheme
    scheme = url.split("://")[0].lower()
    return scheme in allowed_schemes
