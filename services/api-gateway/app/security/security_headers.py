"""
Security Headers Middleware
===========================
Implements security headers for API Gateway following OWASP guidelines.

Headers implemented:
- Content-Security-Policy (CSP)
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Strict-Transport-Security (HSTS)
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy

Version: 1.0.0
Created: 2025-12-12
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class SecurityHeadersConfig:
    """
    Configuration for security headers.

    All headers can be customized or disabled by setting to None.
    """

    # Content-Security-Policy
    # Restricts sources for scripts, styles, etc.
    csp_enabled: bool = True
    csp_default_src: str = "'self'"
    csp_script_src: str = "'self'"
    csp_style_src: str = "'self' 'unsafe-inline'"  # Needed for Swagger UI
    csp_img_src: str = "'self' data: https:"
    csp_font_src: str = "'self' data:"
    csp_connect_src: str = "'self' ws: wss:"  # Allow WebSocket connections
    csp_frame_ancestors: str = "'none'"
    csp_base_uri: str = "'self'"
    csp_form_action: str = "'self'"

    # X-Content-Type-Options
    # Prevents MIME type sniffing
    content_type_options: str = "nosniff"

    # X-Frame-Options
    # Prevents clickjacking by disabling iframe embedding
    frame_options: str = "DENY"

    # Strict-Transport-Security (HSTS)
    # Forces HTTPS connections
    hsts_enabled: bool = True
    hsts_max_age: int = 31536000  # 1 year
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False

    # X-XSS-Protection
    # Legacy XSS protection (deprecated but still used)
    xss_protection: str = "1; mode=block"

    # Referrer-Policy
    # Controls referrer information sent with requests
    referrer_policy: str = "strict-origin-when-cross-origin"

    # Permissions-Policy (formerly Feature-Policy)
    # Restricts browser features
    permissions_policy_enabled: bool = True
    permissions_camera: str = "()"
    permissions_microphone: str = "()"
    permissions_geolocation: str = "()"
    permissions_payment: str = "()"

    # Cache-Control for API responses
    cache_control: str = "no-store, no-cache, must-revalidate"

    # Custom headers
    custom_headers: Dict[str, str] = field(default_factory=dict)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Implements OWASP security header recommendations to protect
    against common web vulnerabilities.

    Usage:
        from app.security import SecurityHeadersMiddleware, SecurityHeadersConfig

        config = SecurityHeadersConfig(
            frame_options="SAMEORIGIN",  # Custom setting
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)
    """

    def __init__(self, app, config: Optional[SecurityHeadersConfig] = None):
        """
        Initialize security headers middleware.

        Args:
            app: FastAPI application
            config: Security headers configuration (uses defaults if None)
        """
        super().__init__(app)
        self.config = config or SecurityHeadersConfig()
        self._headers = self._build_headers()

        logger.info(
            f"Security headers middleware initialized with "
            f"{len(self._headers)} headers configured"
        )

    def _build_headers(self) -> Dict[str, str]:
        """
        Build the dictionary of security headers.

        Returns:
            Dictionary of header name -> value pairs
        """
        headers = {}

        # Content-Security-Policy
        if self.config.csp_enabled:
            csp_parts = [
                f"default-src {self.config.csp_default_src}",
                f"script-src {self.config.csp_script_src}",
                f"style-src {self.config.csp_style_src}",
                f"img-src {self.config.csp_img_src}",
                f"font-src {self.config.csp_font_src}",
                f"connect-src {self.config.csp_connect_src}",
                f"frame-ancestors {self.config.csp_frame_ancestors}",
                f"base-uri {self.config.csp_base_uri}",
                f"form-action {self.config.csp_form_action}",
            ]
            headers["Content-Security-Policy"] = "; ".join(csp_parts)

        # X-Content-Type-Options
        if self.config.content_type_options:
            headers["X-Content-Type-Options"] = self.config.content_type_options

        # X-Frame-Options
        if self.config.frame_options:
            headers["X-Frame-Options"] = self.config.frame_options

        # Strict-Transport-Security (HSTS)
        if self.config.hsts_enabled:
            hsts_value = f"max-age={self.config.hsts_max_age}"
            if self.config.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            if self.config.hsts_preload:
                hsts_value += "; preload"
            headers["Strict-Transport-Security"] = hsts_value

        # X-XSS-Protection
        if self.config.xss_protection:
            headers["X-XSS-Protection"] = self.config.xss_protection

        # Referrer-Policy
        if self.config.referrer_policy:
            headers["Referrer-Policy"] = self.config.referrer_policy

        # Permissions-Policy
        if self.config.permissions_policy_enabled:
            permissions_parts = [
                f"camera={self.config.permissions_camera}",
                f"microphone={self.config.permissions_microphone}",
                f"geolocation={self.config.permissions_geolocation}",
                f"payment={self.config.permissions_payment}",
            ]
            headers["Permissions-Policy"] = ", ".join(permissions_parts)

        # Cache-Control
        if self.config.cache_control:
            headers["Cache-Control"] = self.config.cache_control

        # Custom headers
        for name, value in self.config.custom_headers.items():
            headers[name] = value

        return headers

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and add security headers to response.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response with security headers added
        """
        # Process the request
        response = await call_next(request)

        # Add security headers to response
        for header_name, header_value in self._headers.items():
            # Don't override existing headers
            if header_name not in response.headers:
                response.headers[header_name] = header_value

        return response


def get_security_headers_middleware(
    config: Optional[SecurityHeadersConfig] = None
) -> type:
    """
    Factory function to create configured security headers middleware.

    Args:
        config: Security headers configuration

    Returns:
        Configured middleware class

    Usage:
        app.add_middleware(get_security_headers_middleware(config))
    """
    middleware_config = config or SecurityHeadersConfig()

    class ConfiguredSecurityHeadersMiddleware(SecurityHeadersMiddleware):
        def __init__(self, app):
            super().__init__(app, config=middleware_config)

    return ConfiguredSecurityHeadersMiddleware


# ============================================================================
# CORS CONFIGURATION
# ============================================================================

@dataclass
class CORSConfig:
    """
    Strict CORS configuration for production.

    Only allows specific origins instead of wildcard.
    """
    # Allowed origins (no wildcards in production)
    allow_origins: List[str] = field(default_factory=lambda: [
        "http://localhost:3000",     # Local React development
        "http://localhost:8000",     # Local API gateway
        "http://127.0.0.1:3000",     # Alternative localhost
        "http://127.0.0.1:8000",     # Alternative localhost
    ])

    # Allow credentials (cookies, auth headers)
    allow_credentials: bool = True

    # Allowed HTTP methods
    allow_methods: List[str] = field(default_factory=lambda: [
        "GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"
    ])

    # Allowed headers
    allow_headers: List[str] = field(default_factory=lambda: [
        "Accept",
        "Accept-Language",
        "Authorization",
        "Content-Language",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-Request-ID",
    ])

    # Exposed headers (headers that browser can access)
    expose_headers: List[str] = field(default_factory=lambda: [
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
    ])

    # Max age for preflight cache (in seconds)
    max_age: int = 600  # 10 minutes


def get_cors_config(
    additional_origins: Optional[List[str]] = None
) -> CORSConfig:
    """
    Get CORS configuration with optional additional origins.

    Args:
        additional_origins: Additional origins to allow

    Returns:
        CORSConfig with merged origins
    """
    config = CORSConfig()

    if additional_origins:
        # Validate and add additional origins
        for origin in additional_origins:
            # Basic validation - should be a valid URL
            if origin.startswith(("http://", "https://")):
                if origin not in config.allow_origins:
                    config.allow_origins.append(origin)
            else:
                logger.warning(f"Invalid CORS origin ignored: {origin}")

    return config
