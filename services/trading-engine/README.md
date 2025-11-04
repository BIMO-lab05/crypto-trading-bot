# Trading Engine Service

## Overview

The Trading Engine is the core decision-making service of the crypto trading bot. It aggregates signals from the Technical Analysis Service, applies risk management rules, and executes trades in paper or live mode.

## Features

### 🎯 Core Capabilities
- **Multi-Indicator Aggregation**: Combines RSI, MACD, Bollinger Bands, SMA, and EMA signals
- **Intelligent Signal Weighting**: Confidence-based scoring system
- **Risk Management**: Position sizing, stop-loss, take-profit, exposure limits
- **Paper Trading**: Safe testing environment with virtual $10,000 balance
- **Real-time Position Tracking**: Live P&L calculation and monitoring
- **Performance Metrics**: Win rate, ROI, Sharpe ratio, drawdown tracking

### 🛡️ Safety Features
- **Default Paper Mode**: Starts in paper trading mode by default
- **Risk Limits**:
  - Max 2% of capital per position
  - Max 5% daily loss (automatic trading halt)
  - Max 20% total exposure across all positions
- **Signal Validation**: Minimum confidence (0.6) and consensus (3 indicators) requirements
- **Emergency Stop**: Manual and automatic trading halt mechanisms

## Architecture

```
┌─────────────────────────────────────────────┐
│         Trading Engine (Port 8005)          │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐  ┌──────────────┐       │
│  │   Signal     │  │     Risk     │       │
│  │  Aggregator  │  │   Manager    │       │
│  └──────┬───────┘  └──────┬───────┘       │
│         │                  │               │
│         ▼                  ▼               │
│  ┌──────────────────────────────┐         │
│  │    Decision Engine           │         │
│  └──────┬───────────────────────┘         │
│         │                                  │
│         ▼                                  │
│  ┌──────────────┐  ┌──────────────┐       │
│  │   Position   │  │    Paper     │       │
│  │   Manager    │  │   Trading    │       │
│  └──────────────┘  └──────────────┘       │
│                                             │
└─────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
  ┌─────────────┐    ┌─────────────┐
  │  Technical  │    │   Bybit     │
  │  Analysis   │    │  Connector  │
  │  (8004)     │    │   (8002)    │
  └─────────────┘    └─────────────┘
```

## API Endpoints

### Health & Status

#### GET /health
Health check with dependency status
```bash
curl http://localhost:8005/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "trading-engine",
  "technical_analysis_connection": true,
  "bybit_connector_connection": false,
  "database_connection": false,
  "timestamp": 1730332800000
}
```

#### GET /status
Current trading engine status
```bash
curl http://localhost:8005/status
```

**Response**:
```json
{
  "status": "running",
  "trading_mode": "PAPER",
  "auto_trading_enabled": false,
  "active_strategy": "consensus",
  "open_positions_count": 0,
  "current_balance": 10000.0,
  "timestamp": 1730332800000
}
```

### Signal Analysis

#### GET /api/v1/signals/{symbol}
Get aggregated trading signal
```bash
curl "http://localhost:8005/api/v1/signals/BTCUSDT?interval=60"
```

**Response**:
```json
{
  "success": true,
  "signal": {
    "symbol": "BTCUSDT",
    "timestamp": 1730332800000,
    "action": "HOLD",
    "confidence": 0.47,
    "indicators": {
      "RSI": {"signal": "HOLD", "confidence": 0.3, "value": 43.74},
      "MACD": {"signal": "SELL", "confidence": 1.0, "value": -42743.55},
      "BOLLINGER_BANDS": {"signal": "BUY", "confidence": 0.4},
      "SMA": {"signal": "SELL", "confidence": 1.0},
      "EMA": {"signal": "SELL", "confidence": 0.73}
    },
    "aggregated_score": -0.466,
    "consensus_count": 3,
    "metadata": {
      "buy_count": 1,
      "sell_count": 3,
      "hold_count": 1,
      "meets_requirements": false
    }
  }
}
```

#### POST /api/v1/signals/{symbol}/analyze
Analyze signal and optionally execute trade
```bash
curl -X POST "http://localhost:8005/api/v1/signals/BTCUSDT/analyze?execute=true"
```

### Position Management

#### GET /api/v1/positions
List all positions
```bash
curl "http://localhost:8005/api/v1/positions?status=open"
```

#### GET /api/v1/positions/{position_id}
Get specific position details
```bash
curl "http://localhost:8005/api/v1/positions/{uuid}"
```

### Performance Metrics

#### GET /api/v1/performance
Get performance metrics
```bash
curl http://localhost:8005/api/v1/performance
```

**Response**:
```json
{
  "success": true,
  "metrics": {
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_pnl": "0.0",
    "win_rate": 0.0,
    "current_balance": "10000.0",
    "initial_balance": "10000.0",
    "roi": 0.0
  }
}
```

### Trading Control

#### POST /api/v1/trading/start
Start automated trading
```bash
curl -X POST http://localhost:8005/api/v1/trading/start
```

#### POST /api/v1/trading/stop
Stop automated trading
```bash
curl -X POST http://localhost:8005/api/v1/trading/stop
```

## Configuration

### Environment Variables

Create `.env` file:
```env
# Service Configuration
SERVICE_NAME=trading-engine
SERVICE_PORT=8005
TRADING_MODE=PAPER

# Service URLs
TECHNICAL_ANALYSIS_URL=http://localhost:8004
BYBIT_CONNECTOR_URL=http://localhost:8002

# Risk Management
MAX_POSITION_SIZE_PCT=2.0
MAX_DAILY_LOSS_PCT=5.0
MAX_TOTAL_EXPOSURE_PCT=20.0
DEFAULT_STOP_LOSS_PCT=3.0
DEFAULT_TAKE_PROFIT_PCT=6.0

# Signal Thresholds
MIN_SIGNAL_CONFIDENCE=0.6
MIN_CONSENSUS_INDICATORS=3

# Paper Trading
PAPER_INITIAL_BALANCE=10000.0
PAPER_COMMISSION_PCT=0.1
```

## Installation

### Prerequisites
- Python 3.12+
- Technical Analysis Service running on port 8004
- Bybit Connector Service running on port 8002 (optional for paper trading)

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Start Service
```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/trading-engine

# Run with uvicorn
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005
```

Or use the convenience script:
```bash
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

## How It Works

### Signal Aggregation Algorithm

1. **Fetch Indicators**: Parallel requests to Technical Analysis Service for all 5 indicators
2. **Normalize Signals**: Convert BUY/SELL/HOLD to numerical scores (-1 to +1)
3. **Weight by Confidence**: Multiply each signal by its confidence score
4. **Calculate Aggregated Score**: Average of all weighted scores
5. **Determine Action**:
   - Score ≥ 0.3: BUY
   - Score ≤ -0.3: SELL
   - Otherwise: HOLD
6. **Validate Requirements**:
   - Minimum consensus: 3 indicators must agree
   - Minimum confidence: 0.6
   - If not met: Override to HOLD

### Risk Management

#### Position Sizing
```python
# Maximum position value
max_value = account_balance * (MAX_POSITION_SIZE_PCT / 100)

# Calculate quantity
quantity = max_value / entry_price

# If stop-loss provided, use risk-based sizing
risk_per_unit = abs(entry_price - stop_loss)
risk_based_quantity = (account_balance * MAX_POSITION_SIZE_PCT / 100) / risk_per_unit

# Use the more conservative
final_quantity = min(quantity, risk_based_quantity)
```

#### Stop-Loss Calculation
```python
# For LONG positions
stop_loss = entry_price * (1 - DEFAULT_STOP_LOSS_PCT / 100)

# For SHORT positions
stop_loss = entry_price * (1 + DEFAULT_STOP_LOSS_PCT / 100)
```

#### Daily Loss Limit
```python
max_daily_loss = initial_balance * (MAX_DAILY_LOSS_PCT / 100)

if daily_pnl < -max_daily_loss:
    halt_trading()  # Emergency stop
```

### Paper Trading

Paper trading simulates real trading without using real money:

1. **Virtual Balance**: Starts with $10,000 (configurable)
2. **Commission Simulation**: 0.1% commission on each trade
3. **Order Execution**: Instant fills at current market price
4. **Position Tracking**: Full P&L calculation
5. **Performance Metrics**: Same as live trading

## Example Usage

### Complete Trading Flow

```bash
# 1. Check service health
curl http://localhost:8005/health

# 2. Check current status
curl http://localhost:8005/status

# 3. Get trading signal for BTCUSDT
curl "http://localhost:8005/api/v1/signals/BTCUSDT?interval=60"

# 4. Analyze and execute trade (if signal is strong enough)
curl -X POST "http://localhost:8005/api/v1/signals/BTCUSDT/analyze?execute=true"

# 5. Check open positions
curl "http://localhost:8005/api/v1/positions?status=open"

# 6. Check performance
curl http://localhost:8005/api/v1/performance
```

### Python Integration

```python
import httpx
import asyncio

async def trade_btcusdt():
    async with httpx.AsyncClient() as client:
        # Get signal
        response = await client.get(
            "http://localhost:8005/api/v1/signals/BTCUSDT",
            params={"interval": "60"}
        )
        signal = response.json()["signal"]

        print(f"Signal: {signal['action']} (confidence: {signal['confidence']})")
        print(f"Consensus: {signal['consensus_count']}/5 indicators")
        print(f"Aggregated score: {signal['aggregated_score']}")

        # Execute if strong signal
        if signal['action'] in ['BUY', 'SELL'] and signal['confidence'] >= 0.7:
            execute_response = await client.post(
                f"http://localhost:8005/api/v1/signals/BTCUSDT/analyze",
                params={"execute": True}
            )
            print(f"Execution: {execute_response.json()['message']}")

asyncio.run(trade_btcusdt())
```

## Testing

### Manual Testing
```bash
# Run all tests
cd services/trading-engine
bash test_all.sh
```

### Unit Tests
```bash
pytest tests/ -v --cov=app
```

## Monitoring

### Logs
Service logs are written to `logs/service.log`:
```bash
tail -f logs/service.log
```

### Key Log Messages
- `✓ Position created` - New position opened
- `✓ Position closed` - Position closed with P&L
- `🛑 TRADING HALTED` - Emergency stop triggered
- `Signal aggregated` - Signal analysis complete

## Safety Protocols

### Before Going Live

1. **Paper Trading Period**: Run for at least 2 weeks in paper mode
2. **Performance Review**: Analyze win rate, max drawdown, Sharpe ratio
3. **Risk Validation**: Verify all risk limits are working
4. **Monitor Signals**: Ensure signal quality is consistent
5. **Small Capital Test**: Start with small amounts in live mode

### Emergency Procedures

**If Daily Loss Limit Hit**:
- Trading automatically halts
- All positions remain open
- Manual review required before resuming

**Manual Emergency Stop**:
```bash
curl -X POST http://localhost:8005/api/v1/trading/stop
```

## Troubleshooting

### Service Won't Start
1. Check Python path: `export PYTHONPATH=.`
2. Verify dependencies: `pip install -r requirements.txt`
3. Check logs: `tail logs/service.log`

### Technical Analysis Connection Failed
1. Verify TA service is running: `curl http://localhost:8004/health`
2. Check TECHNICAL_ANALYSIS_URL in .env
3. Check network connectivity

### Signals Not Meeting Requirements
- Lower MIN_SIGNAL_CONFIDENCE in .env
- Lower MIN_CONSENSUS_INDICATORS in .env
- Check indicator values - market might be ranging

## Future Enhancements

- [ ] Automated trading loop
- [ ] Multiple strategy support
- [ ] Backtesting framework
- [ ] Machine learning integration
- [ ] Portfolio optimization
- [ ] Multi-symbol trading
- [ ] WebSocket real-time updates
- [ ] Advanced risk models

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions:
1. Check logs: `logs/service.log`
2. Verify all services are running
3. Review API documentation: http://localhost:8005/docs
4. Check IMPLEMENTATION_PLAN.md for architecture details
