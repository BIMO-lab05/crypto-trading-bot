---
type: module
path: "services/sentiment-analysis-service/"
status: idle
state: leg-removed
language: python
port: 8008
purpose: "News / social sentiment — leg removed from signal pipeline 2026-04-29; service still runs, no backend consumer"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on:
  - NewsAPI.org
  - Twitter API v2
used_by:
  - api-gateway
tags: [module, service, idle, leg-removed]
created: 2026-05-05
updated: 2026-05-05
---

# sentiment-analysis-service

> [!warning] Status: `idle / leg-removed`
> Sentiment leg removed from signal pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`). Default flag `ENABLE_SENTIMENT_ANALYSIS=false`. **Service still runs** in `docker-compose.unified.yml` and is reachable via api-gateway proxy routes, but neither `technical-analysis` nor `trading-engine` consume it. No RabbitMQ topic was ever published. See [[../concepts/Feature-Flags]] and [[../flows/Signal-Pipeline]].

**Port:** `8008`
**Path:** `services/sentiment-analysis-service/`
**Container:** `crypto-bot-sentiment`
**Image:** `services/sentiment-analysis-service/Dockerfile` (build often fails — PyPI read timeouts; see Gotchas)

## Overview

FastAPI service computing news + social sentiment scores per crypto symbol. Pulls news from NewsAPI.org and tweets from Twitter API v2, runs them through a local sentiment analyzer, and exposes weighted-combined / per-source endpoints. Falls back to mock data when API keys are absent.

As of 2026-04-29 cleanup, the previously fabricated `trend` and `aggregate` endpoints now return `501 Not Implemented` instead of synthetic numbers, and the `combined` endpoint no longer injects a hardcoded 0.5 "market sentiment" pseudo-source.

## Endpoints

| Method | Path | State |
|---|---|---|
| GET | `/` | info |
| GET | `/health` | active |
| GET | `/ready` | active |
| GET | `/metrics` | Prometheus |
| GET | `/api/v1/stats` | cache + API-call counters |
| GET | `/api/v1/sentiment/news/{symbol}` | active (NewsAPI or mock) |
| GET | `/api/v1/sentiment/social/{symbol}` | active (Twitter or mock) |
| GET | `/api/v1/sentiment/combined/{symbol}` | active; 503 if both sources fail |
| GET | `/api/v1/sentiment/{symbol}` | back-compat shim → combined |
| GET | `/api/v1/sentiment/trend/{symbol}` | **501** — no persistence layer |
| GET | `/api/v1/sentiment/aggregate` | **501** — no scheduled fan-out |

## Sources scraped

- NewsAPI.org — env `NEWS_API_KEY` (free tier 100/day)
- Twitter API v2 — env `TWITTER_BEARER_TOKEN`
- Reddit — env slots exist (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`) but no fetcher implemented
- Local NLP only — no external scoring API (e.g. no OpenAI / Claude)

## Used by

- [[api-gateway]] — proxies six `/api/sentiment/*` routes to port 8008 (`SENTIMENT_ANALYSIS_URL=http://sentiment-analysis:8008`).
- [[technical-analysis]] — **does not consume**. Aggregator no longer subscribes / fetches. Verified: zero `sentiment` references in `services/technical-analysis/`.
- `trading-engine` — does not consume.

## Messaging

No RabbitMQ. Service never imported `aio_pika` / `pika` and never published a sentiment topic. The "sentiment leg" was always an HTTP pull at consumer-side; removal was deletion of those calls in `technical-analysis`. See [[../concepts/Message-Queue-Topics]].

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `NEWS_API_KEY` | `""` | NewsAPI.org key (mock fallback if empty) |
| `TWITTER_BEARER_TOKEN` | `""` | Twitter v2 bearer (mock fallback) |
| `REDDIT_CLIENT_ID` / `_SECRET` | `""` | declared, unused |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` | **read by trading-engine, not by this service** — gates consumption, not availability |
| `cache_ttl` | `900` | seconds |
| `sentiment_lookback_hours` | `24` | default window |
| Scoring weights | news=0.4 / social=0.3 / technical=0.3 | **stale** — combined endpoint hardcodes 0.6/0.4 news/social |

See [[../concepts/Feature-Flags]] for the full feature-flag matrix.

## Key files

- `app/main.py` — FastAPI app, ~830 lines
- `app/main.py.bak` — pre-cleanup snapshot
- `app/config.py` — pydantic settings
- `app/models.py` — response schemas
- `app/analyzers/sentiment_analyzer.py` — local NLP
- `app/analyzers/news_fetcher.py` — NewsAPI client + mock
- `app/analyzers/twitter_fetcher.py` — Twitter v2 client + mock

## Gotchas

- **Dockerfile build flaky** — PyPI read timeouts. Workaround: retry build or `compose up --no-deps` skip. (Per repo `CLAUDE.md`.)
- **Silent mock fallback** — empty API keys produce structurally identical responses with synthetic data. Caller cannot tell.
- **Stale weight config** — `news_weight` / `social_weight` / `technical_weight` settings ignored by the combined endpoint since 2026-04-29.
- **No persistence** — every call hits external APIs (or mocks). In-memory cache only.
- **Idle ≠ off** — service runs in compose; routes return real data when keys present. Only the *consumer* leg is removed.

## Related

- [[../concepts/Feature-Flags]]
- [[../concepts/Message-Queue-Topics]]
- [[../flows/Signal-Pipeline]]
- [[technical-analysis]]
- [[api-gateway]]
- [[../flows/Order-Lifecycle]]
