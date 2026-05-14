# Trading engine pipeline map

Walk this every time the user says "audit the trading engine" or "check the engine works". Each edge has a verification command. If an edge is broken, the whole pipeline is broken — report which one, do not patch silently.

## High-level flow

```
market-data-service (8002)
    │  RabbitMQ: candle.<symbol>.<timeframe>
    ▼
technical-analysis (8004)
    │  produces TA features + (optional) GRU prediction
    │  RabbitMQ: signal.<symbol>
    ▼
trading-engine (8005)
    ├─ signal_aggregator.py   ← multi-strategy fusion
    ├─ strategies/coordinator.py + aggregator.py
    ├─ risk_manager.py        ← 2% per-trade, 5% daily-loss
    ├─ position_sizing.py     ← capital fraction → qty
    ├─ atr_stops.py           ← stop-loss derivation
    ├─ execution/             ← paper or live router
    │     ├─ paper_trading.py
    │     └─ live_trading.py
    ├─ position_manager.py    ← SHORT enforcement, 48h hold cap (Jan 2026 fix)
    └─ database/              ← signals + orders + fills tables
            │
            ▼
notification-service (8006) ← Telegram + email
portfolio-manager (8003)    ← positions, balances, P&L
```

## Edge checklist

Each item: *file*, *what to check*, *evidence command*.

### A. Market data into TA

- File: `services/market-data-service/app/...` publisher; consumer in `services/technical-analysis/app/fetcher.py`.
- Check: candles arriving with monotonic timestamps and no NaN in `close`.
- Evidence:
  ```bash
  docker compose -f docker-compose.unified.yml logs --tail=200 technical-analysis | grep -E "candle|symbol|timeframe" | head -20
  ```
  Expect `received candle SOLUSDT 1m close=...` style lines.

### B. TA features into signals

- File: `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py` and indicators in `services/technical-analysis/app/indicators/`.
- Check: signal events emitted on RabbitMQ with `confidence`, `strategy`, `signal_type`.
- Evidence:
  ```bash
  curl -s http://localhost:8004/health
  curl -s http://localhost:8004/api/analysis/last-signals?symbol=SOLUSDT | jq
  ```

### C. Signal aggregator → strategy coordinator

- File: `services/trading-engine/app/signal_aggregator.py` (cross-strategy fuse), `services/trading-engine/app/strategies/coordinator.py` (per-strategy dispatch).
- Check: every strategy file in `app/strategies/` is imported and registered. Watch for orphans (e.g. `mean_reversion.py` AND `mean_reversion_strategy.py` both present — only one is wired).
- Evidence:
  ```bash
  grep -rn "register\|register_strategy\|StrategyCategory" services/trading-engine/app/strategies/coordinator.py services/trading-engine/app/strategies/aggregator.py
  ```

### D. Risk manager bind

- File: `services/trading-engine/app/risk_manager.py`.
- Check: 2% per-trade clamp present and active; 5% daily-loss kill-switch present and reachable.
- Evidence:
  ```bash
  grep -nE "0\.02|MAX_RISK_PER_TRADE|MAX_DAILY_LOSS|0\.05" services/trading-engine/app/risk_manager.py services/trading-engine/app/config.py
  ```
  Confirm the constants are *used*, not just defined.

### E. Position sizing bound

- File: `services/trading-engine/app/position_sizing.py`.
- Check: cannot return a quantity whose notional exceeds 2% capital. Add a unit test if missing.

### F. ATR stop-loss derivation

- File: `services/trading-engine/app/atr_stops.py`.
- Check: stops use ATR-based distance, not fixed pct of price (Jan 2026 fix).

### G. Execution router (paper vs live)

- File: `services/trading-engine/app/execution/paper_trading.py` and `live_trading.py`. Top-level switch in `auto_trader.py` / `multi_symbol_trader.py`.
- Check: when `PAPER_TRADING_MODE=true`, no path through `live_trading.place_order`. When `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` required at boot or service refuses to start (added 2026-05).
- Evidence:
  ```bash
  docker compose -f docker-compose.unified.yml logs trading-engine | grep -E "PAPER_TRADING_MODE|TRADING_MODE|LIVE_TRADING_ACK" | tail -10
  ```

### H. Position manager invariants

- File: `services/trading-engine/app/position_manager.py`.
- Check: SHORT enforcement (Jan 2026 commit `380a674`) intact. 48h max-hold present. Inverted R/R bug stays fixed.

### I. DB persistence

- Tables: `signals`, `orders`, `fills`, `positions` in app PostgreSQL.
- Evidence:
  ```bash
  docker exec crypto-bot-postgres psql -U postgres -d trading_bot \
    -c "SELECT id, symbol, strategy, signal_type, confidence, created_at FROM signals ORDER BY created_at DESC LIMIT 20;"
  docker exec crypto-bot-postgres psql -U postgres -d trading_bot \
    -c "SELECT id, symbol, side, qty, status, created_at FROM orders ORDER BY created_at DESC LIMIT 20;"
  ```

### J. Notification delivery

- File: `services/notification-service/app/...`.
- Check: end-to-end Telegram receipt, not HTTP 200 from the service.
- Evidence: paste the actual Telegram message into the report.

### K. Portfolio reconciliation

- File: `services/portfolio-manager/app/...`.
- Check: positions and balances consistent with order fills.
- Evidence:
  ```bash
  curl -s http://localhost:8003/api/portfolio/positions | jq
  curl -s http://localhost:8003/api/portfolio/balance | jq
  ```

### L. Auto-trader loop

- File: `services/trading-engine/app/auto_trader.py`.
- Check: only ticks when `EMERGENCY_STOP` file is absent at repo root and `AUTO_TRADING_ENABLED=true`. Loop-tick log present.
- Evidence:
  ```bash
  ls /mnt/d/Bimo_max/crypto-trading-bot/EMERGENCY_STOP 2>/dev/null && echo "STOP FILE PRESENT"
  docker compose -f docker-compose.unified.yml logs --since=5m trading-engine | grep -E "auto.?trader|tick|cycle" | tail -20
  ```

## Reporting

Output template:

```
edge | status | evidence
A market-data → TA | PASS | "received candle SOLUSDT 1m close=..." (logs)
B TA → signals | PASS | /api/analysis/last-signals returned 8 SOL signals last 1h
...
```

No edge marked PASS without a quote/snippet under "evidence". Aggregating to "engine OK" without per-edge evidence violates `verify-stack` rule.
