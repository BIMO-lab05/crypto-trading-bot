---
name: verify-stack
description: Verify the trading stack is genuinely working end-to-end with real data, not shallow HTTP 200 checks. Use before declaring any deploy, fix, or refactor "working". Confirms live (non-testnet) prices, real notification delivery, DB persistence, and that services were restarted after config changes. Reports PASS/FAIL per check — never aggregates to "working" unless all 4 pass.
disable-model-invocation: true
---

# Verify Stack

Verify the trading stack is genuinely working end-to-end. Curl 200s and "tests pass" are not sufficient — every check below must produce concrete evidence.

## Checks (all must PASS)

1. **Live prices, not testnet**
   - Read recent logs from market-data-service / price ingestion.
   - Confirm the source URL points to live exchange endpoints, not testnet (`testnet.binance`, `api-testnet.bybit`, etc.).
   - Paste the source URL line from the logs as evidence.

2. **Notification actually delivered**
   - Trigger a test signal end-to-end (not a unit test, not a curl against the notification service).
   - Confirm the message arrived at the destination (Telegram chat, Discord channel, webhook receiver).
   - Paste the received message as evidence. HTTP 200 from the notification service is NOT proof of delivery.

3. **Signal/trade persisted to DB**
   - Query the relevant DB table (signals, trades, orders) after the test signal.
   - Confirm the row exists with expected fields (symbol, confidence, timestamp).
   - Paste the `SELECT` result as evidence.

4. **Services restarted after config changes**
   - If any service config (env, YAML, model file) changed in this session, the service must have been restarted before testing.
   - Stale in-memory state has caused false-pass integration tests before.
   - List which services were restarted and when.

## Output format

Report each check on its own line:

```
[1] Live prices:        PASS  (source: https://api.bybit.com/v5/market/...)
[2] Notification:       FAIL  (no message received in Telegram chat after 60s)
[3] DB persistence:     PASS  (signal_id=12345 in signals table)
[4] Services restarted: PASS  (signal-aggregator restarted at 14:32 after confidence_gate change)

Overall: FAIL — notification check failed
```

Never aggregate to "working" or "fixed" unless all 4 are PASS.
