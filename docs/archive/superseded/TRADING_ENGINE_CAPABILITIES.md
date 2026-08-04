# Trading Engine - Complete Capabilities Documentation
**Service:** trading-engine (Port 8005)
**Version:** 2.0.0
**Last Updated:** 2025-11-14

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Signal Aggregation System](#signal-aggregation-system)
5. [Trading Strategies](#trading-strategies)
6. [Risk Management](#risk-management)
7. [Position Management](#position-management)
8. [Paper Trading](#paper-trading)
9. [Monitoring & Alerts](#monitoring--alerts)
10. [API Endpoints](#api-endpoints)
11. [Configuration](#configuration)
12. [Testing](#testing)

---

## Overview

The Trading Engine is the core decision-making component of the crypto trading bot. It:
- Aggregates signals from multiple sources (TA, ML, Sentiment)
- Makes trading decisions based on weighted scoring
- Manages positions and risk
- Executes trades (paper or live)
- Monitors performance and sends alerts

**Key Features:**
- ✅ Multi-signal aggregation with gatekeepers and validators
- ✅ Weighted scoring system (replaces strict AND logic)
- ✅ Risk management (2% per trade limit, daily loss limits)
- ✅ Position tracking (entry, exit, P&L calculation)
- ✅ Paper trading mode
- ✅ Real-time monitoring and alerting
- ✅ Comprehensive testing (unit + integration)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING ENGINE (Port 8005)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          SIGNAL AGGREGATION LAYER                    │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │Gatekeeper│  │Validator │  │  Voter/Scorer   │  │  │
│  │  │(Filters) │→ │(Confirms)│→ │(Weighted Score) │  │  │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          TRADING DECISION ENGINE                     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │  Risk    │  │ Position │  │  Order Executor │  │  │
│  │  │ Manager  │→ │ Manager  │→ │ (Paper/Live)    │  │  │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         MONITORING & PERFORMANCE TRACKING            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │  Metrics │  │  Alerts  │  │    Database      │  │  │
│  │  │Collector │  │  System  │  │    Repository    │  │  │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
           ↑                    ↓                    ↑
    Signals from          Orders to            Updates to
    - Technical          Bybit Connector       Portfolio
    - ML Prediction                            Manager
    - Sentiment
```

---

## Core Components

### 1. Auto Trader (`app/auto_trader.py`)

**Purpose:** Main orchestrator that coordinates all trading activities

**Capabilities:**
- Polls for new signals from TA, ML, and sentiment services
- Triggers signal aggregation
- Executes trading decisions
- Updates portfolio state
- Sends notifications

**Key Methods:**
```python
async def start_trading(symbol: str, interval: str)
    # Start automated trading loop

async def stop_trading()
    # Gracefully stop trading

async def process_signal_cycle()
    # Main trading cycle: fetch signals → aggregate → decide → execute
```

**Configuration:**
```python
POLLING_INTERVAL = 60  # Check for new signals every 60 seconds
MAX_CONCURRENT_SYMBOLS = 10  # Trade up to 10 pairs simultaneously
```

### 2. Risk Manager (`app/risk_manager.py`)

**Purpose:** Enforces risk limits to prevent catastrophic losses

**Implemented Safeguards:**

**Position Size Limits:**
```python
MAX_RISK_PER_TRADE = 0.02  # 2% of portfolio per trade
MAX_POSITION_SIZE = 1000.0  # $1000 max per position (configurable)
MIN_POSITION_SIZE = 10.0    # $10 minimum
```

**Daily Loss Limits:**
```python
DAILY_LOSS_LIMIT = 0.05  # Stop trading if lose 5% in one day
MAX_DAILY_TRADES = 50     # Prevent runaway trading
```

**Drawdown Protection:**
```python
MAX_DRAWDOWN = 0.10  # Circuit breaker at 10% drawdown from peak
```

**Key Methods:**
```python
def validate_trade(order: Order, portfolio_balance: float) -> bool
    # Check if trade passes all risk checks

def calculate_position_size(signal_strength: float,
                           portfolio_balance: float,
                           stop_loss_pct: float) -> float
    # Calculate safe position size based on risk

def check_daily_limits() -> bool
    # Verify daily trading limits not exceeded

def activate_circuit_breaker() -> None
    # Emergency stop all trading
```

**Risk Calculation Example:**
```python
# If portfolio = $10,000 and risk per trade = 2%
# Maximum loss allowed = $200

# If stop loss = 5% below entry
# Position size = $200 / 0.05 = $4,000

# But capped at MAX_POSITION_SIZE ($1,000)
# Actual position size = min($4,000, $1,000) = $1,000
```

### 3. Position Manager (`app/position_manager.py`)

**Purpose:** Track all open positions and calculate P&L

**Position States:**
```python
class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    MANUALLY_CLOSED = "manually_closed"
```

**Tracked Metrics:**
```python
class Position:
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    exit_time: Optional[datetime]
    exit_price: Optional[float]
    pnl: float  # Profit/Loss in dollars
    pnl_pct: float  # Profit/Loss percentage
    duration: timedelta  # How long position was held
    fees: float  # Trading fees paid
    status: PositionStatus
```

**Key Methods:**
```python
def open_position(symbol, side, entry_price, quantity, sl, tp)
    # Create new position

def close_position(position_id, exit_price)
    # Close position and calculate P&L

def update_stop_loss(position_id, new_sl)
    # Adjust stop loss (trailing stop)

def get_open_positions(symbol=None)
    # List all open positions

def calculate_unrealized_pnl(current_price)
    # Calculate current P&L without closing
```

**P&L Calculation:**
```python
# Long Position (BUY)
pnl = (exit_price - entry_price) * quantity - fees
pnl_pct = ((exit_price - entry_price) / entry_price) * 100

# Short Position (SELL)
pnl = (entry_price - exit_price) * quantity - fees
pnl_pct = ((entry_price - exit_price) / entry_price) * 100
```

### 4. Paper Trading (`app/paper_trading.py`)

**Purpose:** Simulate trading without real money

**Simulated Features:**
- ✅ Virtual balance ($10,000 default)
- ✅ Realistic order execution (slippage simulation)
- ✅ Trading fees (0.1% default, matching Bybit)
- ✅ Stop-loss and take-profit triggers
- ✅ Position tracking identical to live trading
- ✅ Performance metrics

**Configuration:**
```python
PAPER_TRADING_INITIAL_BALANCE = 10000.0  # $10k start
PAPER_TRADING_SLIPPAGE = 0.001  # 0.1% slippage
PAPER_TRADING_COMMISSION = 0.001  # 0.1% fee
```

**Key Methods:**
```python
async def execute_paper_order(order: Order) -> OrderResult
    # Simulate order execution with realistic delays

def simulate_slippage(price: float, side: str) -> float
    # Apply realistic price slippage

def check_stop_loss_take_profit(position: Position, current_price: float)
    # Monitor and trigger SL/TP
```

**Advantages:**
- Zero financial risk
- Validate strategies before live trading
- Test edge cases (flash crashes, API failures)
- Build confidence in system

---

## Signal Aggregation System

### Overview

The signal aggregation system replaces strict AND logic (all conditions must be true) with a **weighted scoring system** (accumulate points from multiple sources).

### Architecture

```
Technical Analysis → ┐
ML Prediction      → ├→ [Gatekeeper] → [Validator] → [Voter] → Final Score → Decision
Sentiment Analysis → ┘
```

### 1. Gatekeeper (`app/aggregation/gatekeeper.py`)

**Purpose:** Fast filters that block obviously bad signals

**Filters:**
```python
class GatekeeperFilter(Enum):
    TREND_FILTER = "trend"        # Must align with major trend
    VOLUME_FILTER = "volume"      # Sufficient volume required
    VOLATILITY_FILTER = "volatility"  # Not too volatile
    LIQUIDITY_FILTER = "liquidity"    # Enough market depth
```

**Example:**
```python
# BUY signal gatekeeper
if trend == "BEARISH":
    return BLOCK  # Don't buy in downtrend

if volume < average_volume * 0.5:
    return BLOCK  # Insufficient volume

return PASS
```

### 2. Validator (`app/aggregation/validator.py`)

**Purpose:** Confirmation checks for signals that passed gatekeeper

**Validations:**
```python
class ValidatorCheck(Enum):
    MULTI_TIMEFRAME = "mtf"       # Confirm on multiple timeframes
    CORRELATION = "correlation"    # Check asset correlation
    NEWS_SENTIMENT = "news"        # No negative news
    VOLATILITY_REGIME = "regime"   # Market regime appropriate
```

**Example:**
```python
# Multi-timeframe confirmation
if signal_15m == "BUY" and signal_1h == "BUY" and signal_4h == "BUY":
    validator_score += 20  # Strong confirmation

elif signal_15m == "BUY" and signal_1h == "BUY":
    validator_score += 10  # Moderate confirmation
```

### 3. Voter/Scorer (`app/aggregation/voter.py`)

**Purpose:** Assign weighted scores to each signal source

**Weight Distribution (Phase 3 Strategy):**
```python
SIGNAL_WEIGHTS = {
    # Phase 1 Technical Indicators (60 points total)
    "rsi": 15,                    # RSI oversold/overbought
    "price_vs_ema": 15,           # Price relative to EMA
    "macd_histogram": 15,         # MACD momentum
    "bollinger_position": 10,     # BB squeeze/expansion
    "trend_filter": 10,           # Gatekeeper trend
    "volume_confirmation": 5,     # Validator volume

    # Phase 3 AI Enhancements (40 points total)
    "ml_prediction": 20,          # LSTM price prediction (KEY DIFFERENTIATOR)
    "sentiment_score": 15,        # News/social sentiment
    "volatility_forecast": 5,     # ML volatility prediction
}

THRESHOLD_BUY = 55   # Need 55/100 points for BUY signal
THRESHOLD_SELL = 55  # Need 55/100 points for SELL signal
```

**Scoring Example (BUY Signal):**
```python
score = 0

# Technical Analysis
if rsi < 40:  # Oversold
    score += 15 * (40 - rsi) / 40  # Stronger oversold = more points

if price > ema_20:  # Price above EMA (bullish)
    score += 15

if macd_histogram > 0:  # Positive momentum
    score += 15

if price < bb_lower * 1.05:  # Near lower Bollinger Band
    score += 10

# AI Enhancements
if ml_prediction == "BULLISH" and ml_confidence > 0.7:
    score += 20 * ml_confidence  # 20 * 0.7 = 14 points

if sentiment_score > 0.3:  # Positive sentiment
    score += 15

# Gatekeeper & Validator
if trend == "BULLISH" and trend_confidence > 0.8:
    score += 10 * 0.8  # 8 points

if volume > avg_volume * 1.5:  # High volume
    score += 5

# Total: 15 + 15 + 15 + 10 + 14 + 15 + 8 + 5 = 97/100
# Result: STRONG BUY (exceeds 55 threshold)
```

### 4. Signal Cache (`app/aggregation/signal_cache.py`)

**Purpose:** Prevent duplicate processing of same signals

**Features:**
- 5-minute TTL (time to live)
- Redis-backed caching
- Deduplication by (symbol, interval, timestamp)

---

## Trading Strategies

### Phase 1: Technical Analysis Only

**Strategy File:** `app/strategies/phase1_strategy.py`

**Indicators Used:**
1. **RSI (Relative Strength Index)**
   - Buy: RSI < 40 (oversold)
   - Sell: RSI > 60 (overbought)
   - Weight: 20 points

2. **MACD (Moving Average Convergence Divergence)**
   - Buy: Histogram > 0 (bullish momentum)
   - Sell: Histogram < 0 (bearish momentum)
   - Weight: 20 points

3. **Bollinger Bands**
   - Buy: Price < Lower Band * 1.05
   - Sell: Price > Upper Band * 0.95
   - Weight: 15 points

4. **EMA (Exponential Moving Average)**
   - Buy: Price > EMA20 (uptrend)
   - Sell: Price < EMA20 (downtrend)
   - Weight: 20 points

5. **Volume Confirmation**
   - Requires volume > average * 1.2
   - Weight: 10 points

6. **Trend Filter (Gatekeeper)**
   - Uses EMA50/EMA200 crossover
   - Weight: 15 points

**Threshold:** 60/100 points required

### Phase 3: AI-Enhanced Strategy

**Strategy File:** `app/strategies/phase3_strategy.py`

**Additional Features:**
1. **LSTM Price Prediction**
   - Direction: BULLISH / BEARISH / NEUTRAL
   - Confidence: 0.0 to 1.0
   - Weight: 20 points (HIGHEST - key differentiator)

2. **Sentiment Analysis**
   - Sources: Twitter, Reddit, News
   - Score: -1.0 (very negative) to +1.0 (very positive)
   - Weight: 15 points

3. **Volatility Forecasting**
   - ML-predicted volatility for next N hours
   - Used to adjust stop-loss distance
   - Weight: 5 points

**Threshold:** 55/100 points (more aggressive than Phase 1)

**Enhanced Stop-Loss:**
```python
# Base stop-loss from ATR
base_sl = current_price - (atr * 2.0)

# Adjust for predicted volatility
volatility_multiplier = 1.0 + (ml_volatility * 10)
enhanced_sl = current_price - (atr * 2.0 * volatility_multiplier)

# If high volatility predicted, widen stop-loss to avoid whipsaws
```

---

## Risk Management

### Position Sizing Algorithm

**Kelly Criterion (Modified):**
```python
def calculate_position_size(
    win_rate: float,  # Historical win rate (e.g., 0.55)
    avg_win: float,   # Average winning trade %
    avg_loss: float,  # Average losing trade %
    balance: float,   # Current portfolio balance
    risk_pct: float = 0.02  # Risk per trade (2%)
) -> float:

    # Kelly formula
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

    # Use fractional Kelly (25% of full Kelly for safety)
    fractional_kelly = kelly * 0.25

    # Calculate position size
    risk_amount = balance * risk_pct
    position_size = risk_amount / abs(avg_loss)

    # Cap at max position size
    return min(position_size, MAX_POSITION_SIZE)
```

### Stop-Loss Calculation

**ATR-Based Dynamic Stop-Loss:**
```python
def calculate_stop_loss(
    entry_price: float,
    atr: float,  # Average True Range
    side: str,   # "BUY" or "SELL"
    multiplier: float = 2.0
) -> float:

    if side == "BUY":
        stop_loss = entry_price - (atr * multiplier)
    else:  # SELL
        stop_loss = entry_price + (atr * multiplier)

    return stop_loss
```

**Trailing Stop-Loss:**
```python
def update_trailing_stop(
    position: Position,
    current_price: float,
    trailing_pct: float = 0.02  # 2% trailing
) -> float:

    if position.side == "BUY":
        # Only raise stop-loss, never lower
        new_sl = current_price * (1 - trailing_pct)
        position.stop_loss = max(position.stop_loss, new_sl)

    else:  # SELL
        # Only lower stop-loss, never raise
        new_sl = current_price * (1 + trailing_pct)
        position.stop_loss = min(position.stop_loss, new_sl)

    return position.stop_loss
```

### Circuit Breaker Conditions

**Automatic Trading Halt:**
```python
# 1. Daily loss limit exceeded
if daily_pnl < -balance * 0.05:  # -5%
    activate_circuit_breaker("DAILY_LOSS_LIMIT")

# 2. Max drawdown from peak
if (peak_balance - current_balance) / peak_balance > 0.10:  # 10%
    activate_circuit_breaker("MAX_DRAWDOWN")

# 3. Too many consecutive losses
if consecutive_losses >= 5:
    activate_circuit_breaker("LOSS_STREAK")

# 4. API connection issues
if api_failures >= 3:
    activate_circuit_breaker("API_FAILURE")
```

---

## Position Management

### Position Lifecycle

```
1. SIGNAL RECEIVED
   ↓
2. RISK VALIDATION
   ↓
3. POSITION OPENED (status: OPEN)
   ↓
4. MONITORING (update unrealized P&L)
   ↓
5. EXIT TRIGGER (SL/TP/Manual)
   ↓
6. POSITION CLOSED (status: CLOSED/STOP_LOSS_HIT/TAKE_PROFIT_HIT)
   ↓
7. P&L CALCULATION
   ↓
8. PORTFOLIO UPDATE
   ↓
9. NOTIFICATION SENT
```

### Position Monitoring

**Real-time Checks (Every 10 seconds):**
```python
async def monitor_positions():
    for position in get_open_positions():
        current_price = await get_current_price(position.symbol)

        # Check stop-loss
        if position.side == "BUY" and current_price <= position.stop_loss:
            await close_position(position, current_price, "STOP_LOSS_HIT")

        # Check take-profit
        if position.side == "BUY" and current_price >= position.take_profit:
            await close_position(position, current_price, "TAKE_PROFIT_HIT")

        # Update trailing stop
        if TRAILING_STOP_ENABLED:
            update_trailing_stop(position, current_price)

        # Calculate unrealized P&L
        position.unrealized_pnl = calculate_unrealized_pnl(
            position, current_price
        )
```

### Performance Metrics

**Per-Position Metrics:**
```python
class PositionMetrics:
    pnl: float  # Profit/Loss ($)
    pnl_pct: float  # Profit/Loss (%)
    duration: timedelta  # Holding time
    mae: float  # Maximum Adverse Excursion (worst drawdown during trade)
    mfe: float  # Maximum Favorable Excursion (highest profit during trade)
    efficiency: float  # mfe / mae ratio
    profit_per_hour: float  # pnl / duration.hours
```

**Portfolio-Wide Metrics:**
```python
class PortfolioMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # winning_trades / total_trades
    avg_win: float  # Average winning trade %
    avg_loss: float  # Average losing trade %
    profit_factor: float  # Total wins / Total losses
    sharpe_ratio: float  # Risk-adjusted returns
    sortino_ratio: float  # Downside risk-adjusted returns
    max_drawdown: float  # Worst peak-to-trough loss
    total_pnl: float
    total_fees: float
    net_pnl: float  # total_pnl - total_fees
```

---

## Monitoring & Alerts

### Metrics Collection (`app/monitoring/metrics.py`)

**Tracked Metrics:**
```python
# Trading metrics
trades_executed_total
trades_won_total
trades_lost_total
trade_pnl_dollars
trade_duration_seconds

# Risk metrics
position_size_dollars
daily_pnl_dollars
drawdown_from_peak_pct
consecutive_losses

# System metrics
signal_processing_time_seconds
api_request_latency_seconds
order_execution_time_seconds
```

**Prometheus Export:**
```python
from prometheus_client import Counter, Histogram, Gauge

trades_counter = Counter('trades_total', 'Total trades executed', ['symbol', 'side', 'result'])
pnl_gauge = Gauge('pnl_dollars', 'Current profit/loss', ['symbol'])
latency_histogram = Histogram('api_latency_seconds', 'API request latency')
```

### Alert System (`app/monitoring/alerts.py`)

**Alert Levels:**
```python
class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

**Alert Types:**
```python
# Trading alerts
TRADE_EXECUTED = "Trade {side} {symbol} @ ${price}"
POSITION_CLOSED = "Position closed: ${pnl} ({pnl_pct}%)"
STOP_LOSS_HIT = "Stop loss hit on {symbol}: -${loss}"
TAKE_PROFIT_HIT = "Take profit hit on {symbol}: +${profit}"

# Risk alerts
DAILY_LIMIT_REACHED = "Daily loss limit reached: -${loss}"
MAX_DRAWDOWN_REACHED = "Max drawdown reached: {dd}%"
LOSS_STREAK = "{count} consecutive losses"

# System alerts
API_FAILURE = "API connection failed: {error}"
CIRCUIT_BREAKER_ACTIVATED = "Circuit breaker activated: {reason}"
LOW_BALANCE = "Portfolio balance low: ${balance}"
```

**Notification Channels:**
```python
async def send_alert(alert: Alert):
    # Send to multiple channels
    await send_telegram_alert(alert)
    await send_email_alert(alert)
    await log_alert_to_database(alert)
    await update_prometheus_metrics(alert)
```

---

## API Endpoints

### Health & Status

```bash
GET /health
# Response: {"status": "healthy", "service": "trading-engine"}

GET /api/v1/status
# Response: {
#   "trading_active": true,
#   "symbols_trading": ["BTCUSDT", "ETHUSDT"],
#   "open_positions": 3,
#   "daily_pnl": 125.50,
#   "total_trades_today": 12
# }
```

### Trading Control

```bash
POST /api/v1/start
# Body: {"symbol": "BTCUSDT", "interval": "60"}
# Start automated trading for symbol

POST /api/v1/stop
# Body: {"symbol": "BTCUSDT"}  # Optional, stops all if omitted
# Stop automated trading

POST /api/v1/emergency/stop
# Immediately halt all trading and close positions

POST /api/v1/emergency/close-all
# Close all open positions
```

### Paper Trading

```bash
POST /api/v1/execute/paper
# Body: {
#   "symbol": "BTCUSDT",
#   "action": "BUY",
#   "quantity": 0.001,
#   "order_type": "MARKET"
# }
# Execute simulated paper trade

GET /api/v1/paper/balance
# Get paper trading balance

POST /api/v1/paper/reset
# Reset paper trading balance to initial amount
```

### Position Management

```bash
GET /api/v1/positions
# Query params: ?symbol=BTCUSDT&status=open
# List positions

GET /api/v1/positions/{position_id}
# Get specific position details

POST /api/v1/positions/{position_id}/close
# Manually close a position

PATCH /api/v1/positions/{position_id}/stop-loss
# Body: {"stop_loss": 37000.00}
# Update stop-loss level
```

### Performance Metrics

```bash
GET /api/v1/performance/daily
# Get today's performance metrics

GET /api/v1/performance/weekly
# Get this week's performance

GET /api/v1/performance/summary
# Get all-time performance summary
```

### Configuration

```bash
GET /api/v1/config
# Get current configuration

POST /api/v1/config/update
# Body: {"risk_per_trade": 0.01, "signal_threshold": 60}
# Update configuration (requires restart)
```

---

## Configuration

### Environment Variables

**File:** `services/trading-engine/.env`

```bash
# Trading Mode
PAPER_TRADING=true  # false for live trading
PAPER_TRADING_INITIAL_BALANCE=10000.0

# Risk Management
MAX_RISK_PER_TRADE=0.02  # 2%
DAILY_LOSS_LIMIT=0.05     # 5%
MAX_DRAWDOWN=0.10         # 10%
MAX_POSITION_SIZE=1000.0  # $1000
MIN_POSITION_SIZE=10.0    # $10

# Signal Processing
SIGNAL_THRESHOLD_BUY=55   # Phase 3: 55/100
SIGNAL_THRESHOLD_SELL=55
SIGNAL_CACHE_TTL=300      # 5 minutes

# Auto Trading
AUTO_TRADING_ENABLED=false  # Manual enable
POLLING_INTERVAL=60         # Check signals every 60s
MAX_CONCURRENT_SYMBOLS=10

# Service URLs
BYBIT_CONNECTOR_URL=http://bybit-connector:8001
PORTFOLIO_MANAGER_URL=http://portfolio-manager:8003
TECHNICAL_ANALYSIS_URL=http://technical-analysis:8004
ML_PREDICTION_URL=http://ml-prediction:8007
SENTIMENT_ANALYSIS_URL=http://sentiment-analysis:8008
NOTIFICATION_SERVICE_URL=http://notification-service:8006

# Database
DATABASE_URL=postgresql://crypto_user:crypto_pass@timescaledb:5432/crypto_trading
REDIS_URL=redis://redis:6379/0

# Monitoring
ENABLE_METRICS=true
PROMETHEUS_PORT=9090
LOG_LEVEL=INFO
```

---

## Testing

### Unit Tests (19 test files)

**Located in:** `services/trading-engine/tests/unit/`

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_risk_manager.py -v

# Run with coverage
pytest tests/unit/ --cov=app --cov-report=html
```

**Test Coverage:**
- `test_aggregator_core.py` - Signal aggregation logic
- `test_auto_trader.py` - Automated trading loop
- `test_gatekeeper_validator.py` - Filter and validation logic
- `test_multi_timeframe.py` - Multi-timeframe confirmation
- `test_order_models.py` - Order data models
- `test_paper_trading.py` - Paper trading simulation
- `test_position_manager.py` - Position lifecycle
- `test_risk_manager.py` - Risk calculations
- `test_signal_aggregator.py` - Weighted scoring
- `test_voter.py` - Voting mechanism

**Coverage Target:** >80%

### Integration Tests

**Located in:** `services/trading-engine/tests/`

```bash
# Test full trading flow
pytest tests/test_auto_trader.py -v

# Test position management
pytest tests/test_position_manager.py -v

# Test risk management
pytest tests/test_risk_manager.py -v
```

---

## Usage Examples

### Start Automated Trading

```python
import httpx

async def start_trading():
    async with httpx.AsyncClient() as client:
        # Start trading BTCUSDT on 1-hour timeframe
        response = await client.post(
            "http://localhost:8005/api/v1/start",
            json={"symbol": "BTCUSDT", "interval": "60"}
        )
        print(response.json())
        # {"success": true, "message": "Trading started for BTCUSDT"}
```

### Monitor Positions

```python
async def monitor_positions():
    async with httpx.AsyncClient() as client:
        # Get all open positions
        response = await client.get(
            "http://localhost:8005/api/v1/positions",
            params={"status": "open"}
        )

        positions = response.json()["data"]
        for pos in positions:
            print(f"{pos['symbol']}: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:.2f}%)")
```

### Paper Trading Test

```bash
# Execute test buy order
curl -X POST http://localhost:8005/api/v1/execute/paper \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "action": "BUY",
    "quantity": 0.001,
    "order_type": "MARKET"
  }'

# Check paper balance
curl http://localhost:8005/api/v1/paper/balance
# {"balance": 9996.25, "pnl": -3.75}
```

---

## Future Enhancements

### Planned Features

1. **Advanced Order Types**
   - Limit orders
   - Stop-limit orders
   - OCO (One-Cancels-Other)
   - Iceberg orders

2. **Strategy Improvements**
   - Ensemble ML predictions (LSTM + GRU + Transformer)
   - Regime detection (bull/bear/sideways)
   - Correlation-based pair trading
   - Options hedging strategies

3. **Risk Management**
   - Portfolio-level risk budgeting
   - Correlation-adjusted position sizing
   - VaR-based limits
   - Stress testing

4. **Performance**
   - Strategy auto-optimization
   - Walk-forward analysis
   - Monte Carlo simulation
   - Parameter sensitivity analysis

5. **Monitoring**
   - Real-time dashboard (React/Vue)
   - Advanced charting (TradingView integration)
   - Alert customization
   - Performance attribution

---

## Support & Documentation

**Service README:** `/services/trading-engine/README.md`
**API Documentation:** OpenAPI spec at `http://localhost:8005/docs`
**Test Coverage Report:** `/services/trading-engine/htmlcov/index.html`
**Architecture Docs:** `/docs/architecture/SYSTEM_OVERVIEW.md`

**Key Files:**
- `app/main.py` - FastAPI application entry point
- `app/auto_trader.py` - Automated trading orchestrator
- `app/risk_manager.py` - Risk management engine
- `app/position_manager.py` - Position tracking
- `app/paper_trading.py` - Paper trading simulator
- `app/aggregation/` - Signal aggregation system
- `app/strategies/` - Trading strategies

---

**Last Updated:** 2025-11-14
**Maintained By:** Trading Bot Development Team
**Service Port:** 8005
**Status:** Production Ready (Paper Trading Mode)
