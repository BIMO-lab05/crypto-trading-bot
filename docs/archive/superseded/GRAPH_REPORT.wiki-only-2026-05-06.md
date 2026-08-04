# Graph Report - wiki/  (2026-05-06)

## Corpus Check
- Corpus is ~17,365 words - fits in a single context window. You may not need a graph.

## Summary
- 248 nodes · 325 edges · 20 communities detected
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 18 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]

## God Nodes (most connected - your core abstractions)
1. `api-gateway module` - 24 edges
2. `Wiki Index` - 22 edges
3. `trading-engine` - 21 edges
4. `Project Overview` - 19 edges
5. `bybit-connector` - 17 edges
6. `market-data-service` - 16 edges
7. `portfolio-manager` - 15 edges
8. `Architecture Overview` - 14 edges
9. `Modules Index` - 14 edges
10. `notification-service` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Order Lifecycle flow` --semantically_similar_to--> `Signal Pipeline flow`  [INFERRED] [semantically similar]
  wiki/flows/Order-Lifecycle.md → wiki/flows/Signal-Pipeline.md
- `Aspirational vs Real` --semantically_similar_to--> `Message Queue Topics (not wired)`  [INFERRED] [semantically similar]
  wiki/concepts/Aspirational-vs-Real.md → wiki/concepts/Message-Queue-Topics.md
- `Test Setup Gotchas` --semantically_similar_to--> `State Persistence`  [INFERRED] [semantically similar]
  wiki/concepts/Test-Setup-Gotchas.md → wiki/concepts/State-Persistence.md
- `ADR-001: LSTM removed; GRU is sole price predictor` --semantically_similar_to--> `ADR-002: trading-engine lifespan refactor`  [INFERRED] [semantically similar]
  wiki/decisions/ADR-001-LSTM-removed.md → wiki/decisions/ADR-002-trading-engine-lifespan-refactor.md
- `technical-analysis` --semantically_similar_to--> `ml-prediction-service`  [INFERRED] [semantically similar]
  wiki/modules/technical-analysis.md → wiki/modules/ml-prediction-service.md

## Hyperedges (group relationships)
- **Documented-but-not-built integration fictions** — aspirational_vs_real, message_queue_topics, http_service_mesh [INFERRED 0.90]
- **Safety gates: auto-trader + flags + risk caps** — auto_trader, feature_flags, risk_model [INFERRED 0.80]
- **ML lifecycle: status + retrain + flag** — ml_status, feature_flags, ml_status_ml_retraining_ref [INFERRED 0.75]
- **LIVE trading 4-flag alignment** — trading_mode_flags_paper_trading_mode, trading_mode_flags_trading_mode, trading_mode_flags_live_trading_ack, trading_mode_flags_bybit_testnet [EXTRACTED 0.90]
- **Emergency-Stop paths (file flag + admin endpoint + full stop)** — emergency_stop_flow_step_file_flag, emergency_stop_flow_step_admin_endpoint, emergency_stop_flow_step_full_stop [EXTRACTED 0.90]
- **Order lifecycle pipeline steps** — order_lifecycle_step_strategy_intent, order_lifecycle_step_risk_gate, order_lifecycle_step_simulated_fill, order_lifecycle_step_portfolio_update, order_lifecycle_step_notification [EXTRACTED 0.90]
- **Signal Pipeline participants** — module_market_data_service, module_technical_analysis, module_trading_engine [EXTRACTED 0.95]
- **Order Lifecycle participants** — module_trading_engine, module_bybit_connector, module_portfolio_manager, module_notification_service [EXTRACTED 0.90]
- **ML Lifecycle participants** — module_ml_retraining_service, module_ml_prediction_service, module_market_data_service [EXTRACTED 0.90]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.12
Nodes (47): Auto-Trader, Feature-Flags, Message-Queue-Topics, ML-Status, Risk-Model, Test-Setup-Gotchas, Trading-Mode-Flags, Validated-Symbols (+39 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (44): Auto-Trader, Emergency Stop (ref), trading-engine (ref), Feature Flags, Auto-Trader (ref), ML-Status (ref), sentiment-analysis-service (ref), Trading-Mode-Flags (ref) (+36 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (25): Auto-Trader (referenced), Message-Queue-Topics (referenced), Risk-Model (referenced), Test-Setup-Gotchas (referenced), Trading-Mode-Flags (referenced), Validated-Symbols (referenced), ADR-001-LSTM-removed (referenced), ADR-003-bcrypt-sha256-prehash (referenced) (+17 more)

### Community 3 - "Community 3"
Cohesion: 0.12
Nodes (17): ADR-001 LSTM removed, ADR-012 HTTP not events, HTTP-Service-Mesh (ref), Message-Queue-Topics (ref), Aspirational vs Real, ADR-007 no /v1/ prefix, ADR-012 HTTP not events (ref), Aspirational-vs-Real (ref) (+9 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (15): Trading-Mode-Flags (referenced), ADR-004: paper-trading default; LIVE requires 4-flag alignment, ADR-006-mainnet-prices-paper-orders (referenced), Trading-Mode-Flags (referenced), ADR-006: mainnet prices + paper-simulated orders, ADR-004-paper-trading-default (referenced), market-data-service (referenced), BYBIT_TESTNET flag (+7 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (15): Emergency-Stop (referenced), Order-Lifecycle (referenced), Signal-Pipeline (referenced), Architecture Overview, api-gateway (referenced), bybit-connector (referenced), market-data-service (referenced), ml-prediction-service (referenced) (+7 more)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (14): Auto-Trader (referenced), Risk-Model (referenced), Trading-Mode-Flags (referenced), Order Lifecycle flow, bybit-connector (referenced), notification-service (referenced), portfolio-manager (referenced), trading-engine (referenced) (+6 more)

### Community 7 - "Community 7"
Cohesion: 0.15
Nodes (14): Feature-Flags (referenced), ML-Status (referenced), Risk-Model (referenced), Signal Pipeline flow, bybit-connector (referenced), market-data-service (referenced), technical-analysis (referenced), trading-engine (referenced) (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.2
Nodes (12): Auto-Trader (referenced), Test-Setup-Gotchas (referenced), ADR-005: EMERGENCY_STOP file flag + admin endpoint, Emergency-Stop flow (referenced), Emergency Stop flow, Auto-Trader (referenced), api-gateway (referenced), trading-engine (referenced) (+4 more)

### Community 9 - "Community 9"
Cohesion: 0.22
Nodes (9): ADR-010 paper deterministic execution, bybit-connector (ref), Paper Trading Internals, flows/Order-Lifecycle (ref), Trading-Mode-Flags (ref), Risk Model, risk-metrics-service (ref), trading-engine (ref) (+1 more)

### Community 10 - "Community 10"
Cohesion: 0.25
Nodes (8): ADA, BNB, BTC, Validated Symbols, ETH, market-data-service (referenced), trading-engine (referenced), SOL

### Community 11 - "Community 11"
Cohesion: 0.29
Nodes (7): ML-Status (referenced), ADR-001: LSTM removed; GRU is sole price predictor, ml-prediction-service (referenced), ml-retraining-service (referenced), Test-Setup-Gotchas (referenced), ADR-002: trading-engine lifespan refactor, trading-engine (referenced)

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (6): Hot Cache, progress.md, SERVICE_CONTRACTS.md (stale), sources/SYSTEM_OVERVIEW, Stage 1 parallel agent dispatch, SYSTEM_OVERVIEW.md (stale)

### Community 13 - "Community 13"
Cohesion: 0.33
Nodes (6): State Persistence, ADR-006 mainnet prices + paper orders, flows/Order-Lifecycle (ref), ADR-002 trading-engine lifespan refactor, flows/Emergency-Stop (ref), Test Setup Gotchas

### Community 14 - "Community 14"
Cohesion: 0.67
Nodes (3): ADR-007: drop /v1/ prefix from gateway routes, api-gateway (referenced), SERVICE_CONTRACTS (referenced)

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (2): ADR-003: bcrypt_sha256 prehash for password hashing, api-gateway (referenced)

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Operation Log

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): ADR-008: Conventional Commits

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): ADR-009: docker-compose.unified.yml is canonical

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): RabbitMQ

## Knowledge Gaps
- **169 isolated node(s):** `Stage 1 parallel agent dispatch`, `SYSTEM_OVERVIEW.md (stale)`, `SERVICE_CONTRACTS.md (stale)`, `progress.md`, `sources/SYSTEM_OVERVIEW` (+164 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 15`** (2 nodes): `ADR-003: bcrypt_sha256 prehash for password hashing`, `api-gateway (referenced)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `Operation Log`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `ADR-008: Conventional Commits`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `ADR-009: docker-compose.unified.yml is canonical`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (1 nodes): `RabbitMQ`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Wiki Index` connect `Community 1` to `Community 9`, `Community 3`, `Community 13`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `Message Queue Topics (not wired)` connect `Community 3` to `Community 1`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `Project Overview` connect `Community 1` to `Community 9`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **What connects `Stage 1 parallel agent dispatch`, `SYSTEM_OVERVIEW.md (stale)`, `SERVICE_CONTRACTS.md (stale)` to the rest of the system?**
  _169 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._