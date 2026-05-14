"""
Unit tests for the catch-all reverse-proxy to the frontend nginx container.

Plan 07.1-01 Task 3 / BUG-3: api-gateway acts as the host-edge ingress on
port 8000. Non-/api GET paths (including `/`) are reverse-proxied to the
frontend container at FRONTEND_UPSTREAM. The Phase 7 audit-driven smoke
relies on this so GATEWAY_ORIGIN can be a single origin.

These tests mock httpx.AsyncClient so they do NOT hit the live frontend
container — they exercise the gateway-side proxy logic in isolation.

Per CLAUDE.md, api-gateway tests are intended to run inside the container
(`docker exec crypto-bot-api-gateway pytest`). The fastapi version pinned
in the container differs from host pip, which can produce spurious
status-code drift on auth routes — these tests target unauthenticated
proxy paths so they should pass either context, but the canonical run
is in-container.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


class TestReverseProxyHandler:
    """The `/{full_path:path}` catch-all proxies non-/api GETs to frontend."""

    def _make_upstream_response(
        self,
        *,
        status_code=200,
        content=b"<!doctype html><html></html>",
        content_type="text/html; charset=utf-8",
        extra_headers=None,
    ):
        """Build a MagicMock that quacks like an httpx.Response."""
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.content = content
        headers = {"content-type": content_type, "content-length": str(len(content))}
        if extra_headers:
            headers.update(extra_headers)
        resp.headers = headers
        return resp

    def _patch_async_client(self, upstream_response):
        """Patch httpx.AsyncClient to return our canned upstream response."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=upstream_response)
        # Async context manager protocol.
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return patch("app.main.httpx.AsyncClient", return_value=mock_client)

    def test_reverse_proxy_returns_html_for_root(self, test_client):
        """GET / proxies to frontend upstream and returns its HTML body."""
        upstream = self._make_upstream_response(
            content=b"<!doctype html><html><body>App</body></html>",
            content_type="text/html; charset=utf-8",
        )
        with self._patch_async_client(upstream):
            response = test_client.get("/")

        assert response.status_code == 200
        # Content-Type comes from upstream (passed through hop-by-hop strip).
        assert response.headers["content-type"].startswith("text/html")
        assert b"<!doctype html>" in response.content

    def test_reverse_proxy_returns_html_for_spa_route(self, test_client):
        """GET /tournament also proxies (vite hash router catches it client-side)."""
        upstream = self._make_upstream_response(
            content=b"<!doctype html><html></html>",
            content_type="text/html; charset=utf-8",
        )
        with self._patch_async_client(upstream):
            response = test_client.get("/tournament")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_reverse_proxy_strips_hop_by_hop_response_headers(self, test_client):
        """RFC 7230 §6.1 hop-by-hop headers MUST NOT pass through."""
        upstream = self._make_upstream_response(
            extra_headers={
                "transfer-encoding": "chunked",
                "connection": "keep-alive",
                "keep-alive": "timeout=5",
                "x-frontend-version": "1.0.0",  # not hop-by-hop, should pass
            },
        )
        with self._patch_async_client(upstream):
            response = test_client.get("/")

        # Hop-by-hop headers stripped.
        assert "transfer-encoding" not in {k.lower() for k in response.headers}
        assert "keep-alive" not in {k.lower() for k in response.headers}
        # Non-hop-by-hop header passed through.
        assert response.headers.get("x-frontend-version") == "1.0.0"

    def test_reverse_proxy_bypasses_api_paths(self, test_client):
        """Defense-in-depth: even if a /api/* path leaked into the catch-all,
        it should 404 (not proxy) because that's gateway-owned territory.

        In practice this never triggers because FastAPI route ordering
        resolves /api/* exact matches first — but the bypass list is here
        as a fail-closed guard.
        """
        # We can't easily test the bypass via TestClient because the catch-all
        # is registered AFTER /api/* routes — any real /api/* GET will be
        # resolved by its specific handler before reaching the catch-all.
        # Verify the bypass logic by inspecting the constant directly.
        from app.main import _GATEWAY_OWNED_PREFIXES, _GATEWAY_OWNED_EXACT

        assert "api/" in _GATEWAY_OWNED_PREFIXES
        assert "health" in _GATEWAY_OWNED_EXACT
        assert "metrics" in _GATEWAY_OWNED_EXACT
        assert "gateway-info" in _GATEWAY_OWNED_EXACT

    def test_reverse_proxy_returns_502_when_upstream_unreachable(self, test_client):
        """ConnectError from httpx.AsyncClient surfaces as 502 Bad Gateway."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("upstream down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            response = test_client.get("/")

        assert response.status_code == 502
        assert "unreachable" in response.text.lower()

    def test_gateway_info_still_returns_json(self, test_client):
        """`/gateway-info` (relocated from `/`) keeps returning the JSON
        service-info shape — the catch-all does NOT shadow it because the
        exact route is registered first in app.routes."""
        response = test_client.get("/gateway-info")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()
        assert data["service"] == "api-gateway"


class TestReverseProxyHopByHopConstants:
    """Sanity-check the module-level constants used by the catch-all."""

    def test_hop_by_hop_set_matches_rfc7230(self):
        from app.main import _HOP_BY_HOP_HEADERS

        # RFC 7230 §6.1 verbatim.
        expected = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
        assert _HOP_BY_HOP_HEADERS == expected

    def test_gateway_owned_exact_includes_critical_paths(self):
        from app.main import _GATEWAY_OWNED_EXACT

        critical = {"health", "metrics", "docs", "openapi.json", "gateway-info"}
        assert critical.issubset(_GATEWAY_OWNED_EXACT)
