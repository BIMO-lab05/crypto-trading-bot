---
type: meta
title: "Wiki Index"
created: 2026-05-05
updated: 2026-05-05
tags: [meta, index]
---

# Crypto Trading Bot — Wiki Index

Master catalog. Updated on every ingest.

## Folders

- [[modules/_index|Modules]] — per-service pages (11 microservices + frontend)
- [[components/_index|Components]] — reusable UI / utility units
- [[decisions/_index|Decisions]] — ADRs, design choices, trade-offs
- [[dependencies/_index|Dependencies]] — external packages, models, infra
- [[flows/_index|Flows]] — request paths, signal pipeline, order lifecycle
- [[concepts/_index|Concepts]] — strategy patterns, ML lifecycle, risk model
- [[sources/_index|Sources]] — summaries of ingested raw documents
- [[questions/_index|Questions]] — filed Q&A from sessions
- meta/ — dashboards, lint reports, conventions

## Top-level pages

- [[overview|Overview]] — executive summary
- [[hot|Hot Cache]] — most recent context (~500 words)
- [[log|Log]] — append-only operation log

## Quick links

### Architecture
- [[modules/Architecture-Overview|Architecture Overview]]
- [[flows/Signal-Pipeline|Signal Pipeline]]
- [[flows/Order-Lifecycle|Order Lifecycle]]
- [[flows/Emergency-Stop|Emergency Stop]]

### Concepts
- [[concepts/Trading-Mode-Flags|Trading Mode Flags]]
- [[concepts/Risk-Model|Risk Model]]
- [[concepts/ML-Status|ML Status]]
- [[concepts/Auto-Trader|Auto-Trader]]
- [[concepts/Feature-Flags|Feature Flags]]
- [[concepts/Message-Queue-Topics|Message Queue Topics]]
- [[concepts/Test-Setup-Gotchas|Test Setup Gotchas]]

### Decisions (ADRs)
- [[decisions/ADR-001-LSTM-removed|ADR-001 LSTM removed]]
- [[decisions/ADR-002-trading-engine-lifespan-refactor|ADR-002 trading-engine lifespan refactor]]
- [[decisions/ADR-003-bcrypt-sha256-prehash|ADR-003 bcrypt_sha256 prehash]]
- [[decisions/ADR-004-paper-trading-default|ADR-004 paper-trading default]]
- [[decisions/ADR-005-emergency-stop-file-flag|ADR-005 EMERGENCY_STOP file flag]]
- [[decisions/ADR-006-mainnet-prices-paper-orders|ADR-006 mainnet prices + paper orders]]
- [[decisions/ADR-007-no-v1-api-prefix|ADR-007 no /v1/ prefix]]
- [[decisions/ADR-008-conventional-commits|ADR-008 conventional commits]]
- [[decisions/ADR-009-docker-compose-unified-canonical|ADR-009 unified compose canonical]]
