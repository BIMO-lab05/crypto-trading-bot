# Circuit Breaker Implementation Guide

## Overview

The Risk Metrics Service implements a complete circuit breaker pattern with a three-state state machine to protect the trading system from catastrophic losses. The circuit breaker automatically halts trading when risk thresholds are exceeded and implements gradual recovery mechanisms.

## State Machine

```
CLOSED → OPEN → HALF_OPEN → CLOSED
   ↑                 ↓
   └─────────────────┘
```

### States

#### CLOSED (Normal Operation)
- Trading Allowed: Yes (full)
- Monitoring: Continuously checks risk thresholds
- Transitions To: OPEN when thresholds exceeded

#### OPEN (Circuit Tripped)
- Trading Allowed: No
- Monitoring: Waiting for cooldown to expire
- Transitions To: HALF_OPEN when cooldown expires

#### HALF_OPEN (Testing Recovery)
- Trading Allowed: Yes (limited - 1 request by default)
- Monitoring: Tracking trade success/failure
- Transitions To: CLOSED on success, OPEN on failure

## Configuration

### Default Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `circuit_breaker_cooldown` | `300s` | Initial cooldown period |
| `circuit_breaker_half_open_max_requests` | `1` | Trades needed to recover |
| `circuit_breaker_cooldown_multiplier` | `2.0` | Exponential backoff multiplier |
| `circuit_breaker_max_cooldown` | `3600s` | Maximum cooldown cap |

## Trip Conditions

1. **Excessive Daily Loss**: Daily PnL < -5%
2. **Excessive Drawdown**: Drawdown > 10%
3. **Critical Exposure**: Exposure > 24% (20% * 1.2)

## Cooldown Logic - Exponential Backoff

- 1st failure: 300s (5 minutes)
- 2nd failure: 600s (10 minutes)
- 3rd failure: 1200s (20 minutes)
- 4th failure: 2400s (40 minutes)
- 5th+ failure: 3600s (1 hour - capped)

## API Usage

### Check Circuit Breaker Status

```python
status = risk_engine.check_circuit_breaker(
    daily_pnl=-0.03,
    drawdown=0.07,
    exposure_ratio=0.18
)

if status.can_trade:
    execute_trade()
else:
    print(f"Trading halted: {status.reason}")
```

### Record Trade Results (HALF_OPEN state)

```python
engine.record_trade_result(success=True)
```

### Manual Reset (Admin Only)

```python
engine.reset_circuit_breaker()
```

## Version History

- **v1.0.0** (2025-11-19): Complete state machine implementation
