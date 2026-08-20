---
type: meta
status: current
title: "Project Overview"
created: 2026-05-05
updated: 2026-08-19
tags: [overview]
---

# Crypto Trading Bot — Overview

Autonomous Bybit crypto trading bot. **Paper-trading mode** (no real orders). Market data feed from Bybit mainnet for real prices; orders simulated internally.

## Stack

- Python 3.12 + FastAPI + asyncio per service
- React 18 + Vite frontend
- TimescaleDB (candles), PostgreSQL (app state), Redis (cache), RabbitMQ (deployed but idle — services talk via synchronous REST only; no AMQP pub/sub wired, see [[modules/Architecture-Overview]])
- Docker Compose for local; Kubernetes manifests + Helm in `infrastructure/` for prod
- ML: 16 GRU price-prediction models (gated OFF; stale since 2025-12-10). LSTM removal began 2026-05 and is **incomplete** — see [[concepts/ML-Status]]

## Services

| Service | Port | Purpose |
|---|---|---|
| [[modules/api-gateway\|api-gateway]] | 8000 | Frontend → backend routing, auth |
| [[modules/bybit-connector\|bybit-connector]] | 8001 | Bybit REST + WebSocket wrapper |
| [[modules/market-data-service\|market-data-service]] | 8002 | Candle ingest → TimescaleDB |
| [[modules/portfolio-manager\|portfolio-manager]] | 8003 | Positions, balances, P&L |
| [[modules/technical-analysis\|technical-analysis]] | 8004 | TA indicators + GRU + signal aggregator |
| [[modules/trading-engine\|trading-engine]] | 8005 | Strategy + risk + order execution |
| [[modules/notification-service\|notification-service]] | 8006 | Alerts — telegram / email / slack / sms / dashboard |
| [[modules/ml-prediction-service\|ml-prediction-service]] | 8007 | Standalone ML inference |
| [[modules/sentiment-analysis-service\|sentiment-analysis-service]] | 8008 | News / social sentiment (idle) |
| [[modules/risk-metrics-service\|risk-metrics-service]] | 8009 | Risk dashboards |
| [[modules/ml-retraining-service\|ml-retraining-service]] | — | Cron-driven GRU retrain |
| [[modules/frontend\|frontend]] | 3000 | React dashboard |

Prometheus :9090, Grafana :3001.

## Critical concepts

- [[concepts/Trading-Mode-Flags|Trading Mode Flags]] — 4-step gate to LIVE
- [[concepts/Risk-Model|Risk Model]] — 10% per trade in paper / 2% LIVE, 12% daily loss circuit breaker (ADR-028)
- [[concepts/ML-Status|ML Status]] — GRU off pending DSR > 0.95 acceptance
- [[concepts/Validated-Symbols|Validated Symbols]] — 5 traded (BTC/ETH/SOL/BNB/ADA); 14 ingested for research; 30 pinned for edge batteries
- [[concepts/Auto-Trader|Auto-Trader]] — armed by .env override; EMERGENCY_STOP file gates loop

## Edge status

**Twelve strategy families tested, twelve rejected — no strategy here has a demonstrated edge.** Seven legacy
indicator/grid/trend strategies returned negative Sharpe; two pre-registered kill-test batteries
(2026-08-17, 2026-08-18) rejected all five structurally different candidates — `lf_trend`, `funding_carry`,
`xs_momentum`, `vol_breakout`, `pairs_statarb`.

Candidates must clear a cost hurdle (gross edge ≥ 2× taker cost) *and* a statistical gate (DSR ≥ 0.95 with
≥ 0.7 of CPCV paths positive). Clearing the first alone means nothing. The append-only
`backtesting/edge_lab/trial_ledger.json` ratchets the DSR trials floor upward with every variant ever
scored — the anti-p-hacking rail. Details in [[hot|Hot Cache]] and CLAUDE.md §2.

## Critical flows

- [[flows/Signal-Pipeline|Signal Pipeline]] — market-data → TA + ML → aggregator → trading-engine
- [[flows/Order-Lifecycle|Order Lifecycle]] — strategy decision → risk check → simulated fill → portfolio update
- [[flows/Emergency-Stop|Emergency Stop]] — file flag + admin endpoint
