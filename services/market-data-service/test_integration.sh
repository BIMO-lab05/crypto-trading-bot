#!/bin/bash

echo "=========================================="
echo "INTEGRATION TESTS FOR MARKET DATA SERVICE"
echo "=========================================="
echo ""

echo "TEST 1: Authentication - Request WITHOUT API key (should fail with 401)"
echo "---"
curl -s -X POST http://localhost:8003/api/v1/collect/ticker/BTCUSDT | python3 -m json.tool
echo ""

echo "TEST 2: Authentication - Request WITH valid API key (should succeed with 200)"
echo "---"
curl -s -X POST -H "X-API-Key: test-key-123" http://localhost:8003/api/v1/collect/ticker/BTCUSDT | python3 -m json.tool
echo ""

echo "TEST 3: Redis Caching - First request (should be cache miss)"
echo "---"
curl -s http://localhost:8003/api/v1/ticker/BTCUSDT | python3 -m json.tool | grep -E '"source"|"success"'
echo ""

echo "TEST 4: Redis Caching - Second request within 5s (should be cache hit)"
echo "---"
curl -s http://localhost:8003/api/v1/ticker/BTCUSDT | python3 -m json.tool | grep -E '"source"|"success"'
echo ""

echo "TEST 5: Health check (should return healthy)"
echo "---"
curl -s http://localhost:8003/health | python3 -m json.tool
echo ""

echo "=========================================="
echo "ALL TESTS COMPLETED"
echo "=========================================="
