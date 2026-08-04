# Circuit Breaker Quick Reference

## State Machine Overview

```
┌─────────┐  Threshold    ┌─────────┐  Cooldown   ┌────────────┐
│ CLOSED  │─────────────>│  OPEN   │──────────>│ HALF_OPEN  │
│         │   Exceeded    │         │  Expires   │            │
└─────────┘               └─────────┘            └────────────┘
     ↑                                                  │
     │                                                  │
     └──────────────────────────────────────────────────┘
              Success (Recovery Complete)
```

## Quick Start

### 1. Check Circuit Breaker Status
```python
status = risk_engine.check_circuit_breaker(
    daily_pnl=-0.03,      # -3% daily loss
    drawdown=0.07,        # 7% drawdown
    exposure_ratio=0.18   # 18% exposure
)
```

### 2. Handle Response
```python
if status.can_trade:
    execute_trade()
else:
    logger.warning(f"Trading halted: {status.reason}")
    logger.info(f"Cooldown ends: {status.cooldown_until}")
```

### 3. Record Trade Results (in HALF_OPEN state)
```python
if status.state == CircuitBreakerState.HALF_OPEN:
    result = execute_trade()
    risk_engine.record_trade_result(success=result)
```

## Configuration

### Environment Variables
```bash
# Enable/Disable
CIRCUIT_BREAKER_ENABLED=true

# Cooldown Settings
CIRCUIT_BREAKER_COOLDOWN=300              # Base: 5 minutes
CIRCUIT_BREAKER_MAX_COOLDOWN=3600         # Max: 1 hour
CIRCUIT_BREAKER_COOLDOWN_MULTIPLIER=2.0   # Exponential backoff

# Recovery Settings
CIRCUIT_BREAKER_HALF_OPEN_MAX_REQUESTS=1  # Trades needed to recover

# Thresholds
CIRCUIT_BREAKER_DAILY_LOSS_THRESHOLD=0.05  # 5%
CIRCUIT_BREAKER_DRAWDOWN_THRESHOLD=0.10    # 10%
CIRCUIT_BREAKER_EXPOSURE_MULTIPLIER=1.2    # 1.2x max exposure
```

## State Descriptions

| State | Trading | Description |
|-------|---------|-------------|
| `CLOSED` | ✅ Full | Normal operation |
| `OPEN` | ❌ None | Cooldown active |
| `HALF_OPEN` | ⚠️ Limited | Testing recovery |

## Trip Conditions

Circuit trips when **ANY** condition met:
- Daily loss > 5%
- Drawdown > 10%
- Exposure > 24% (20% × 1.2)

## Cooldown Progression

| Failure # | Cooldown Duration |
|-----------|-------------------|
| 1st | 300s (5 min) |
| 2nd | 600s (10 min) |
| 3rd | 1200s (20 min) |
| 4th | 2400s (40 min) |
| 5th+ | 3600s (1 hour max) |

## API Endpoints

### GET /api/v1/circuit-breaker/status
Returns current state and metrics

### POST /api/v1/circuit-breaker/reset
Manually reset (requires admin auth)

## Common Scenarios

### Scenario 1: Normal Trip and Recovery
```python
# 1. Trip
status = engine.check_circuit_breaker(-0.06, 0.05, 0.15)
# State: OPEN, can_trade: False

# 2. Wait 5 minutes...
status = engine.check_circuit_breaker(-0.02, 0.05, 0.15)
# State: HALF_OPEN, can_trade: True

# 3. Trade succeeds
engine.record_trade_result(success=True)
status = engine.check_circuit_breaker(-0.02, 0.05, 0.15)
# State: CLOSED, can_trade: True
```

### Scenario 2: Failed Recovery
```python
# In HALF_OPEN state
engine.record_trade_result(success=False)
# State: OPEN, cooldown_duration: 600s (doubled)
```

### Scenario 3: Manual Reset
```python
# Admin intervention
engine.reset_circuit_breaker()
# State: CLOSED immediately
```

## Monitoring

### Key Metrics
- Trip frequency (alerts per day)
- Average cooldown duration
- Recovery success rate
- Time to recovery

### Log Messages
```
CRITICAL: Circuit breaker TRIPPED
INFO: Transitioning to HALF_OPEN
INFO: Trade success in HALF_OPEN
WARNING: Trade failed in HALF_OPEN
INFO: Transitioning to CLOSED
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Won't reset | Check if conditions still violated |
| Frequent trips | Review/adjust thresholds |
| Slow recovery | Increase half_open_max_requests |
| Extended cooldown | Check failure_count, consider manual reset |

## Files

- **Implementation**: `app/risk_engine.py`
- **Models**: `app/models.py`
- **Config**: `app/config.py`
- **Tests**: `tests/test_circuit_breaker_state_machine.py`
- **Docs**: `docs/CIRCUIT_BREAKER.md`
