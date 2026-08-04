---
type: agent-report
service: sentiment-analysis-service
created: 2026-05-05
---

# sentiment-analysis-service — raw report

Path: `services/sentiment-analysis-service/`
Port: `8008`
Stated purpose (CLAUDE.md): "News / social sentiment (currently idle)"
Compose container: `crypto-bot-sentiment`
Image build: `services/sentiment-analysis-service/Dockerfile`

## Endpoints

FastAPI app in `app/main.py`. All under prefix `/api/v1/sentiment/...` plus health/info.

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Service info / route map |
| GET | `/health` | Returns `{status: healthy, service: sentiment-analysis-service}` |
| GET | `/ready` | Reports which API keys are configured (news / twitter / reddit) |
| GET | `/metrics` | Prometheus (multiproc dir set on lifespan startup) |
| GET | `/api/v1/stats` | Cache + API-call counters |
| GET | `/api/v1/sentiment/news/{symbol}` | News sentiment, `lookback_hours` 1–168 (default 24) |
| GET | `/api/v1/sentiment/social/{symbol}` | Twitter-only social sentiment |
| GET | `/api/v1/sentiment/combined/{symbol}` | Weighted (news 0.6 / social 0.4) — 503 if both upstream sources fail |
| GET | `/api/v1/sentiment/{symbol}` | Backwards-compat shim → calls `combined` |
| GET | `/api/v1/sentiment/trend/{symbol}` | **501 Not Implemented** — no historical persistence |
| GET | `/api/v1/sentiment/aggregate` | **501 Not Implemented** — no scheduled fan-out |

Notes:
- `combined` no longer fabricates a third "market sentiment" 0.5 anchor (removed 2026-04-29; comment in code).
- `trend` and `aggregate` previously returned synthetic numbers (`0.3 + i*0.02`, hardcoded `bullish_count: 12`); both replaced with honest 501 in 2026-04-29 cleanup. Comments preserve the rationale.
- `combined` returns 503 when both news + social fail (was previously a fake `0.5` neutral fallback).

## Sources scraped

- **NewsAPI.org** (`https://newsapi.org/`) via `app/analyzers/news_fetcher.py`. Free tier 100 req/day. Falls back to mock articles (`https://example.com/news/{symbol}-{i}`) if key absent.
- **Twitter API v2** via `app/analyzers/twitter_fetcher.py` using bearer token. Falls back to mock tweets if token absent.
- **Reddit** — config slots exist (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`) and `/ready` reports them, but no `reddit_fetcher.py` exists. Documented but not implemented.

Sentiment scoring is via `app/analyzers/sentiment_analyzer.py` (local; no external NLP API).

## Removal evidence

CLAUDE.md says: sentiment leg removed from signal pipeline (commits c346483, acae081, fe941cf, c171bb0). Verified at consumer side:

- `services/technical-analysis/` — `grep -rn sentiment` returns **zero hits**. No HTTP calls, no signal aggregation, no env vars referencing sentiment.
- `services/trading-engine/` — `grep -rn ENABLE_SENTIMENT|sentiment_analysis_url|fetch_sentiment|SentimentSignal|sentiment_data` returns **zero hits**. Trading engine does not consume sentiment at all.
- `api-gateway` still proxies six routes to it (`/api/sentiment/news|social|combined|trend|aggregate|{symbol}`) — gateway-level surface intact for frontend visibility, but no backend consumer.

Inside the service itself there is **no dead/removal code** — the service was never modified to publish anywhere; consumer-side removal is what gutted its role. Two endpoints (`/trend`, `/aggregate`) were honesty-fixed (501) rather than removed.

A `app/main.py.bak` backup file exists alongside `main.py` — pre-cleanup snapshot.

## Internal deps

External APIs:
- NewsAPI.org (HTTP, key env `NEWS_API_KEY`)
- Twitter API v2 (HTTP, env `TWITTER_BEARER_TOKEN`)
- Reddit (declared, unused: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`)

Env vars (from `app/config.py` + compose):
- `NEWS_API_KEY` (default empty → mock data path)
- `TWITTER_BEARER_TOKEN` (default empty → mock data path)
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- `LOG_LEVEL`, `ENVIRONMENT`
- `SERVICE_NAME=sentiment-analysis-service`
- `cache_ttl=900`, `sentiment_cache_ttl_minutes=15`, `sentiment_lookback_hours=24`
- Scoring weights `news_weight=0.4`, `social_weight=0.3`, `technical_weight=0.3` — these compose-config weights are **stale** (combined endpoint hardcodes 0.6/0.4 news/social since 2026-04-29).

No DB connection (no Postgres, no TimescaleDB, no Redis). No RabbitMQ. In-memory caches on the fetcher classes (`news_cache`, `tweets_cache`).

## Used by

- **api-gateway** (`services/api-gateway/app/main.py` lines 1764–1887, `service_proxy.py:33`) — proxies six `/api/sentiment/*` routes to port 8008 over HTTP. Uses `SENTIMENT_ANALYSIS_URL=http://sentiment-analysis:8008`.
- **technical-analysis-service** — none. No code, no env var reference.
- **trading-engine** — none.
- **frontend** — implied via api-gateway routes; not directly verified here.

So: from a *signal-pipeline* perspective, no consumer. Only the gateway proxy keeps routes addressable.

## RabbitMQ

`grep -rn 'rabbitmq\|aio_pika\|pika\|RABBITMQ\|publish\|subscribe' app/` returns **zero hits**. Service does not import any AMQP library. It never published a topic — was always pull-only over HTTP. Anything CLAUDE.md describes as "sentiment topic removed from signal pipeline" was never an event topic on this side; the removal happened in consumer code (technical-analysis aggregator no longer GETs `/api/v1/sentiment/...`).

`requirements.txt` likewise contains no AMQP package.

## Key files

1. `app/main.py` — FastAPI app, all endpoints, lifespan init, Prometheus metrics middleware (~830 lines).
2. `app/main.py.bak` — pre-2026-04-29-cleanup backup.
3. `app/config.py` — pydantic Settings + env vars + scoring weights.
4. `app/models.py` — Pydantic schemas (NewsArticle, NewsSentiment, SocialPost, SocialSentiment, CombinedSentiment, SentimentTrend, HealthResponse, ReadyResponse).
5. `app/analyzers/sentiment_analyzer.py` — local NLP scoring (analyze_text, get_sentiment_distribution).
6. `app/analyzers/news_fetcher.py` — NewsAPI.org client + mock fallback.
7. `app/analyzers/twitter_fetcher.py` — Twitter API v2 client + mock fallback.
8. `Dockerfile` — image build (slow / flaky per CLAUDE.md).
9. `requirements.txt` — runtime deps.
10. `tests/` — service-level pytest suite.

## Gotchas

- **Dockerfile build flaky**: per CLAUDE.md "sentiment-analysis-service image has historically failed to build via pip (PyPI read timeouts). Other 10 service images cache fine." Workaround: retry build or `--no-deps` skip in `compose up`. `build_sentiment_analysis_service.log` artifact at the service root suggests prior build investigation.
- **Stale config weights**: `Settings.news_weight=0.4`, `social_weight=0.3`, `technical_weight=0.3` — combined endpoint ignores these and hardcodes 0.6/0.4 news/social since 2026-04-29. Keep the config value in sync or delete it.
- **Mock-data fallback is silent**: when `NEWS_API_KEY` / `TWITTER_BEARER_TOKEN` empty, fetchers return synthetic articles/tweets without flagging the response. Endpoint shape identical, so callers can't tell. Useful for local dev, dangerous if anything ever consumed this in production trading.
- **`/api/v1/sentiment/trend` and `/aggregate` return 501** — older clients that expected fake-data success will now error.
- **No persistence layer** — every call hits external APIs (or mocks). No Redis, no DB. Cache is in-memory on the fetcher instance, dies with the process.
- **Compose comment at line 747** of `docker-compose.unified.yml`: "No service depends_on sentiment-analysis; bringing it up is a [side concern]" — confirms idle status.
- **`ENABLE_SENTIMENT_ANALYSIS=false`** is the compose default; flag is read by the trading-engine (line 580 of compose) — not by this service. The flag gates *consumption*, not *availability*. The service runs regardless.

## Contradictions vs CLAUDE.md

- CLAUDE.md says service is "idle" — verified at consumer side, but service itself still: (a) runs in compose, (b) is reachable via 6 api-gateway routes, (c) actively serves news + social sentiment if its API keys configured. So "idle" = "no consumer", not "not running" or "not reachable".
- CLAUDE.md implies "sentiment topic" was removed. Service never had a RabbitMQ topic. Removal was at consumer-side HTTP-call sites (technical-analysis aggregator). No contradiction in outcome, but the topic framing in CLAUDE.md is loose.
- CLAUDE.md commits cited (`c346483`, `acae081`, `fe941cf`, `c171bb0`) appear to touch consumer code; this service's own visible removal work (the 2026-04-29 fake-data cleanup) does not match those SHAs and likely lives in a separate commit. Worth a `git log services/sentiment-analysis-service/` if precise lineage matters.
