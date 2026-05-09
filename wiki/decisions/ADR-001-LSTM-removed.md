---
type: decision
status: accepted
date: 2026-05
context: "ML pipeline simplification"
deciders: []
tags: [decision, adr, ml]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-001: LSTM removed; GRU is sole price predictor

## Context

`LSTMPricePredictor` was the #1 god-node in the codebase (734 edges in dependency graph). GRU models replaced LSTM late 2025 but LSTM class remained, splitting maintenance load.

## Decision

Migrated 9 live importers to GRU. Deleted:
- `LSTMPricePredictor` class file
- 3 LSTM-only training scripts
- LSTM-only tests

Archived `.keras` artifacts under `_archive_lstm/` for rollback safety.

## Commits

`25ca9ab`, `1d616fc`, `69e48b2`, `4f18548`, `ace3582`, `9a0f584`, `f24fd72`, `324e162`

## Consequences

- ML pipeline = GRU only
- ml-prediction-service factory simplified — 5 tests pass
- Rollback path = unarchive `_archive_lstm/`
- See [[../concepts/ML-Status]] for current GRU lifecycle (gated off pending DSR > 0.95)

## Related

- [[../modules/ml-prediction-service]]
- [[../modules/ml-retraining-service]]
- [[../concepts/ML-Status]]
