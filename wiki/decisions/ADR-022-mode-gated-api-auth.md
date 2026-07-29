---
type: decision
status: accepted
date: 2026-07-29
context: "control endpoints were effectively unauthenticated and the rate limiter was a no-op tag; needed to fail closed for real money without breaking the tokenless local dashboard"
deciders: [operator]
tags: [decision, adr, api-gateway, security, auth, rate-limit]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-022: mode-gated API auth + real (method-aware) rate-limit enforcement

## Context

Two api-gateway security gaps:

1. **Auth.** The trading-control endpoints (start/stop/buy/sell/emergency-stop/circuit-breaker reset/train) needed protection for real money, but the single-user local dashboard has no login flow — enforcing auth unconditionally would break local paper operation, while leaving it open is unacceptable in LIVE/prod.
2. **Rate limiting.** `RateLimitMiddleware` only *tagged* each request with an `X-RateLimit-Category` header and never rejected anything — every route documented as "rate limited via middleware" (including `/auth/login` brute-force protection) was effectively unlimited.

## Decision

**Mode-gated auth** (`api-gateway/app/auth_middleware.py`):

- `api_auth_required()` decides enforcement per request (read fresh so runtime/test env flips are honored). Precedence: explicit `REQUIRE_API_AUTH` (true/false) wins; otherwise enforce when `ENVIRONMENT ∈ {production, staging}`, `TRADING_MODE=LIVE`, or `PAPER_TRADING_MODE=false`. `auth_middleware.py:40-64`.
- `get_current_user_gated` returns the real user for a valid token in *both* modes; when auth is **not** enforced a *missing* token falls back to a synthetic `local-paper` admin principal so the tokenless dashboard works; an **invalid** token is rejected 401 in every mode. `auth_middleware.py:131-173`.
- Identity endpoints (`/auth/me`, `/auth/logout`) use `get_current_active_user_strict`, which always requires a real token. `auth_middleware.py:231-247`.

**Real rate-limit enforcement** (`api-gateway/app/security/rate_limiter.py`):

- `RateLimitMiddleware` now counts requests per `(client, category)` in a 60 s fixed window and **fails closed with HTTP 429** past the limit. Per-process (correct for the single-instance deployment; multi-replica needs shared Redis). `rate_limiter.py:353-506`.
- **Method-aware categorization.** Only *mutating* methods (POST/PUT/PATCH/DELETE) on trade paths get the strict `trading_write` bucket; GET read-polls fall through to the generous `general` bucket, so dashboard polling isn't throttled as trades. `rate_limiter.py:414-446`.
- Limits recalibrated for the real dashboard (~250–300 read req/min): `trading_write=60`, `auth=10`, `health=1200`, `general=1200`. `rate_limiter.py:54-66`.

## Consequences

- Control endpoints fail closed under LIVE/prod/staging or `REQUIRE_API_AUTH=true`; local paper stays usable without a token.
- Brute-force and abuse are actually rejected now (429), not just labeled.
- Read polling is no longer collateral-damaged by the strict trade bucket.
- `REQUIRE_API_AUTH` is the single override to force-enforce (or force-open, never for real money) anywhere.

## Related

- `services/api-gateway/app/auth_middleware.py:40-247`
- `services/api-gateway/app/security/rate_limiter.py:54-66, 322-506`
- [[ADR-003-bcrypt-sha256-prehash]]
- [[ADR-004-paper-trading-default]]
- [[../concepts/Trading-Mode-Flags]]
