#!/bin/bash
# Start all services
echo "Starting Crypto Trading Bot Services..."
echo "This is a placeholder - services should be started manually for now"
echo ""
echo "To start services:"
echo "1. Start Docker: cd infrastructure && docker-compose up -d"
echo "2. Start Bybit Connector: cd services/bybit-connector && uvicorn app.main:app --port 8002"
echo "3. Start Market Data: cd services/market-data-service && uvicorn app.main:app --port 8003"
