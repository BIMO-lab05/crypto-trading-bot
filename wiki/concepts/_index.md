---
type: meta
title: "Concepts Index"
created: 2026-05-05
updated: 2026-05-05
tags: [index, concepts]
---

# Concepts

Cross-cutting domain ideas, lifecycles, and rules.

- [[Trading-Mode-Flags]] — paper vs live; 4 flags must align
- [[Risk-Model]] — 2% per-trade cap, 5% daily-loss circuit-breaker, max-hold 48h
- [[ML-Status]] — GRU lifecycle, look-ahead leakage history, acceptance gate
- [[Validated-Symbols]] — BTC/ETH/SOL/BNB/ADA whitelist
- [[Auto-Trader]] — armed by .env override; gated by EMERGENCY_STOP file
- [[Feature-Flags]] — ENABLE_ML_PREDICTIONS, ENABLE_SENTIMENT_ANALYSIS, etc.
- [[Message-Queue-Topics]] — RabbitMQ topic schemas + publishers/consumers
- [[Test-Setup-Gotchas]] — battle-scars in test infrastructure (admin_client, Path mocking, etc.)
