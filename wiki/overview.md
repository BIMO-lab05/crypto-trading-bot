---
type: meta
title: "Project Overview"
created: 2026-05-05
updated: 2026-07-29
tags: [overview]
---

# Crypto Trading Bot — Overview

Autonomous Bybit crypto trading bot. **Paper-trading mode** (no real orders). Market data feed from Bybit mainnet for real prices; orders simulated internally.

## Stack

- Python 3.12 + FastAPI + asyncio per service
- React 18 + Vite frontend
- TimescaleDB (candles), PostgreSQL (app state), Redis (cache), RabbitMQ (deployed but idle — services talk via synchronous REST only; no AMQP pub/sub wired, see [[modules/Architecture-Overview]])
- Docker Compose for local; Kubernetes manifests + Helm in `infrastructure/` for prod
- ML: 16 GRU price-prediction models (currently gated OFF; LSTM deleted 2026-05)

## Services

| Service | Port | Purpose |
|---|---|---|
| [[modules/api-gateway\|api-gateway]] | 8000 | Frontend → backend routing, auth |
| [[modules/bybit-connector\|bybit-connector]] | 8001 | Bybit REST + WebSocket wrapper |
| [[modules/market-data-service\|market-data-service]] | 8002 | Candle ingest → TimescaleDB |
| [[modules/portfolio-manager\|portfolio-manager]] | 8003 | Positions, balances, P&L |
| [[modules/technical-analysis\|technical-analysis]] | 8004 | TA indicators + GRU + signal aggregator |
| [[modules/trading-engine\|trading-engine]] | 8005 | Strategy + risk + order execution |
| [[modules/notification-service\|notification-service]] | 8006 | Telegram + email alerts |
| [[modules/ml-prediction-service\|ml-prediction-service]] | 8007 | Standalone ML inference |
| [[modules/sentiment-analysis-service\|sentiment-analysis-service]] | 8008 | News / social sentiment (idle) |
| [[modules/risk-metrics-service\|risk-metrics-service]] | 8009 | Risk dashboards |
| [[modules/ml-retraining-service\|ml-retraining-service]] | — | Cron-driven GRU retrain |
| [[modules/frontend\|frontend]] | 3000 | React dashboard |

Prometheus :9090, Grafana :3001.

## Critical concepts

- [[concepts/Trading-Mode-Flags|Trading Mode Flags]] — 4-step gate to LIVE
- [[concepts/Risk-Model|Risk Model]] — 2% per trade, 5% daily loss circuit breaker
- [[concepts/ML-Status|ML Status]] — GRU off pending DSR > 0.95 acceptance
- [[concepts/Validated-Symbols|Validated Symbols]] — BTC/ETH/SOL/BNB/ADA
- [[concepts/Auto-Trader|Auto-Trader]] — armed by .env override; EMERGENCY_STOP file gates loop

## Critical flows

- [[flows/Signal-Pipeline|Signal Pipeline]] — market-data → TA + ML → aggregator → trading-engine
- [[flows/Order-Lifecycle|Order Lifecycle]] — strategy decision → risk check → simulated fill → portfolio update
- [[flows/Emergency-Stop|Emergency Stop]] — file flag + admin endpoint
