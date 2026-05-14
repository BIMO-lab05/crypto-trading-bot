# Crypto Sentiment Reviewer — agent scaffold

A managed-agent cookbook scaffold for the crypto bot's sentiment pipeline. Pattern is lifted directly from [`anthropics/financial-services/managed-agent-cookbooks/earnings-reviewer`](https://github.com/anthropics/financial-services/tree/main/managed-agent-cookbooks/earnings-reviewer) and adapted for crypto news + social analysis.

> **Status: scaffold.** Files are valid YAML in the Managed Agent API format. Nothing is wired into the trading-engine. Nothing is deployed to `POST /v1/agents`. The parent FastAPI service still has `ENABLE_SENTIMENT_ANALYSIS=false` in compose. Read [What's not done](#whats-not-done) before assuming this fires.

## Why three tiers

Same isolation logic as earnings-reviewer: the agent that touches **untrusted text** (news articles, tweets, reddit posts) has *no write capability* and *no MCP access*, so a prompt-injection in a tweet can't escape into a trade order or a written file. The aggregator orchestrates but never reads raw user-generated content. Only the digest-writer can write — and it never reads articles, only the validated aggregator output.

| Tier | File | Touches untrusted? | Tools | Output |
|---|---|---|---|---|
| 1. Reader | `subagents/crypto-reader.yaml` | **Yes** | `read`, `grep` only | Schema-validated JSON: `{symbol, window_hours, items[]}` |
| 2. Aggregator | `subagents/signal-aggregator.yaml` | No (reads tier-1 output) | `read`, `grep` | `{symbol, signal, weighted_sentiment, σ, confidence, …}` |
| 3. Digest-writer | `subagents/digest-writer.yaml` | No (reads tier-2 output) | `read`, `write`, `edit` | `./out/digest-<SYMBOL>-<ts>.md` |

The reader's `output_schema` enforces tight regex constraints on every string field. Anything malformed gets rejected at the boundary before the aggregator sees it.

## Mapping: earnings-reviewer → this scaffold

| earnings-reviewer | crypto-sentiment-reviewer | Notes |
|---|---|---|
| `transcript-reader` (10-K / earnings call) | `crypto-news-social-reader` | Different content type, identical isolation contract |
| `model-updater` (FactSet/Daloopa MCP) | `crypto-signal-aggregator` | No MCP yet. Could later add a Bybit funding-rate or open-interest MCP if/when one is built |
| `note-writer` (`.docx` + `.xlsx`) | `crypto-digest-writer` | Markdown only; no Office document deps |
| `steering-examples.json` per ticker | `steering-examples.json` per symbol + lookback | Same fan-out shape |
| Plugin-housed system prompt + skills | Inlined system prompts | Easier to read while iterating; split out if this graduates to a real plugin |

## Files

```
services/sentiment-analysis-service/agents/
├── agent.yaml                       # top-level orchestrator
├── subagents/
│   ├── crypto-reader.yaml           # tier 1 — untrusted boundary
│   ├── signal-aggregator.yaml       # tier 2 — orchestrator
│   └── digest-writer.yaml           # tier 3 — write-holder
├── steering-examples.json           # example invocation events
└── README.md                        # this file
```

## How invocation could work

Two paths. Pick one when you decide to actually run this:

### A. Managed Agent API (mirrors earnings-reviewer's deploy path)

1. Adapt `scripts/deploy-managed-agent.sh` from the financial-services repo to point at this directory.
2. Set whatever env vars the deploy script reads (none needed yet — no MCP servers).
3. Steer with events from the example file:
   ```bash
   curl https://api.anthropic.com/v1/agents/<id>/sessions \
     -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
     -d '{"event": "Analyze sentiment: BTCUSDT 24h"}'
   ```
4. Output digests land in `./out/` of the managed-agent's filesystem and you fetch them via the API.

### B. Local Claude Agent SDK from inside the FastAPI service

Add an endpoint to `app/main.py` (e.g. `POST /api/v1/sentiment/digest/{symbol}`) that:
1. Calls `news_fetcher.fetch_crypto_news()` and `twitter_fetcher.fetch_crypto_tweets()` to pull raw text.
2. Spawns a `claude_agent_sdk.ClaudeSDKClient` configured against `agent.yaml`.
3. Streams the raw text to the reader, captures the digest from `./out/`.
4. Returns the digest path or contents over HTTP.

This path lets you keep the existing FastAPI surface and add the agent layer behind one new endpoint. Prefer it for local iteration before any managed-agent deploy.

## What's not done

Honest list — these are NOT in this scaffold:

- [ ] Not deployed. No `POST /v1/agents` registration, no Managed Agent API setup.
- [ ] Not invokable locally. No SDK runner glue; `app/main.py` doesn't import these YAMLs.
- [ ] No upstream content plumbing. The reader expects raw articles + tweets to be handed to it; nothing here calls the existing `NewsFetcher` / `TwitterFetcher` analyzers.
- [ ] No trading-engine integration. The digest is markdown for human eyes. There is no contract for the trading-engine to subscribe to digests, and the `ENABLE_SENTIMENT_ANALYSIS=false` flag in compose still gates the whole service.
- [ ] No MCP servers wired. earnings-reviewer uses FactSet + Daloopa for market data inside the orchestrator tier; the equivalent for crypto would be a Bybit-funding-rate or open-interest MCP, which doesn't exist yet.
- [ ] No CI / tests. The existing service has 78% coverage on its analyzer code; the agents directory has no test footprint.
- [ ] System prompts are inlined into each YAML for readability. earnings-reviewer factors them into a plugin folder (`plugins/agent-plugins/earnings-reviewer/agents/*.md`). Refactor when this graduates from scaffold to deployed.

## Caveat I owe you because of the broader project state

The bot has been dormant since January 2026. The existing GRU strategy showed no edge in the V0 audit (`docs/strategy/research-2026-04-29/V0-RESULTS-no-edge.md`). The 60-day forward-test from the brainstorm earlier today hasn't started. **Adding a sentiment-driven signal layer before the existing strategy has demonstrated P&L is exactly the engineer-PM trap I called out in that brainstorm**: building new features when the open question is whether the system you already have makes money.

If the answer is "build the scaffold so the option exists, but don't enable it in the signal pipeline until the GRU baseline is replaced and forward-tested" — that's coherent and is what this scaffold does. If the answer is "wire this into the trading-engine and let it influence trades" — push back hard. There's no evidence yet that adding sentiment improves the equity curve, and `ENABLE_SENTIMENT_ANALYSIS=false` is currently load-bearing as a "we don't know if this helps" flag.

Either way: the scaffold sits here as a designed-and-documented option. Decide separately when (or whether) to plug it in.

## Related

- [`docs/strategy/research-2026-04-29/`](../../../docs/strategy/research-2026-04-29) — strategy research showing no edge in V0
- [`services/sentiment-analysis-service/app/main.py`](../app/main.py) — existing FastAPI service this would attach to
- [`docs/REVIVAL_PLAN_2026-05-02.md`](../../../docs/REVIVAL_PLAN_2026-05-02.md) — current revival plan
- Pattern source: [`anthropics/financial-services/managed-agent-cookbooks/earnings-reviewer`](https://github.com/anthropics/financial-services/tree/main/managed-agent-cookbooks/earnings-reviewer)
