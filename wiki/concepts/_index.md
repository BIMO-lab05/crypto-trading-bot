---
type: meta
title: "Concepts Index"
status: current
created: 2026-05-05
updated: 2026-07-30
tags: [index, concepts]
---

# Concepts

Cross-cutting domain ideas, lifecycles, and rules. All 14 pages.

## Trading & risk

- [[Trading-Mode-Flags]] — paper vs live; 4 flags must align (incl. `LIVE_TRADING_ACK`)
- [[Risk-Model]] — per-trade cap (10% paper / 2% LIVE), 12% daily-loss breaker (ADR-028), kill switch
- [[Auto-Trader]] — armed by .env override; EMERGENCY_STOP halt exits loop (manual restart); risk-halt auto-resumes
- [[Paper-Trading-Internals]] — simulated fill mechanics, accounting model (post ADR-018)
- [[Validated-Symbols]] — BTC/ETH/SOL/BNB/ADA trading whitelist vs 14-symbol research universe

## ML

- [[ML-Status]] — GRU lifecycle, look-ahead leakage history, DSR acceptance gate, LSTM purge status

## Architecture & state

- [[HTTP-Service-Mesh]] — real topology: synchronous REST end-to-end (see ADR-016)
- [[Message-Queue-Topics]] — documented RabbitMQ topics (aspirational — nothing wires AMQP)
- [[Aspirational-vs-Real]] — how to read docs that describe intended vs actual behavior
- [[State-Persistence]] — what survives restarts, where state actually lives
- [[Aggregator-Strangler-Fig]] — CoreAggregator strangler-fig refactor state
- [[Feature-Flags]] — ENABLE_ML_PREDICTIONS, ENABLE_SENTIMENT_ANALYSIS, compose profiles `ml`/`analytics`

## Tooling & testing

- [[Graphify-Shadow-Nodes]] — proposal: shadow nodes for graph hygiene
- [[Test-Setup-Gotchas]] — admin_client fixture, Path mocking, in-container test runs
