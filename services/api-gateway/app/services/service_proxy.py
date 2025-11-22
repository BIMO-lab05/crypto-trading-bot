"""
Service Proxy
Handles proxying requests to backend services
"""

import httpx
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class ServiceProxy:
    """Proxy requests to backend microservices"""

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

        # Service URL mapping
        self.services = {
            "bybit": settings.bybit_connector_url,
            "market-data": settings.market_data_url,
            "technical-analysis": settings.technical_analysis_url,
            "trading-engine": settings.trading_engine_url,
            "portfolio-manager": settings.portfolio_manager_url,
            "risk-metrics": settings.risk_metrics_url,
            "ml-prediction": settings.ml_prediction_url,
            "sentiment-analysis": settings.sentiment_analysis_url,
        }

    async def initialize(self):
        """Initialize the HTTP client"""
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info("✓ Service Proxy initialized")

    async def cleanup(self):
        """Cleanup resources"""
        if self.client:
            await self.client.aclose()
        logger.info("✓ Service Proxy cleaned up")

    async def proxy_request(
        self,
        service_name: str,
        path: str,
        method: str = "GET",
        query_params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> JSONResponse:
        """
        Proxy a request to a backend service

        Args:
            service_name: Name of the backend service
            path: API path (e.g., "/api/v1/ticker/BTCUSDT")
            method: HTTP method (GET, POST, PUT, DELETE)
            query_params: Query parameters
            body: Request body for POST/PUT
            headers: Request headers

        Returns:
            JSONResponse with the backend service response
        """
        if not self.client:
            raise HTTPException(status_code=503, detail="Service proxy not initialized")

        # Get service URL
        service_url = self.services.get(service_name)
        if not service_url:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not found"
            )

        # Build full URL
        url = f"{service_url}{path}"

        try:
            # Make request to backend service
            if method == "GET":
                response = await self.client.get(
                    url,
                    params=query_params,
                    headers=headers
                )
            elif method == "POST":
                response = await self.client.post(
                    url,
                    params=query_params,
                    json=body,
                    headers=headers
                )
            elif method == "PUT":
                response = await self.client.put(
                    url,
                    params=query_params,
                    json=body,
                    headers=headers
                )
            elif method == "DELETE":
                response = await self.client.delete(
                    url,
                    params=query_params,
                    headers=headers
                )
            else:
                raise HTTPException(
                    status_code=405,
                    detail=f"Method '{method}' not supported"
                )

            # Return response
            return JSONResponse(
                content=response.json() if response.text else {},
                status_code=response.status_code,
                headers=dict(response.headers)
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout connecting to {service_name} at {url}")
            raise HTTPException(
                status_code=504,
                detail=f"Timeout connecting to {service_name}"
            )
        except httpx.RequestError as e:
            logger.error(f"Error connecting to {service_name}: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Service {service_name} unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error proxying to {service_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error"
            )

    async def check_service_health(self, service_name: str) -> bool:
        """Check if a backend service is healthy"""
        if not self.client:
            return False

        service_url = self.services.get(service_name)
        if not service_url:
            return False

        try:
            response = await self.client.get(
                f"{service_url}/health",
                timeout=5.0
            )
            return response.status_code == 200
        except Exception:
            return False

    async def aggregate_health_checks(self) -> Dict[str, bool]:
        """Check health of all backend services"""
        health_checks = {}

        for service_name in self.services.keys():
            health_checks[service_name] = await self.check_service_health(service_name)

        return health_checks
