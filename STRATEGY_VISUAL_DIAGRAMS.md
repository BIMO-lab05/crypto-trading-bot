# Trading Strategy - Visual Diagrams

## Signal Aggregation Architecture

```
                          Market Data
                          (BTCUSDT)
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
            Technical Analysis Service  Real-time Prices
                    │
    ┌───────────────┼───────────────┬──────────┬──────────┐
    │               │               │          │          │
    ▼               ▼               ▼          ▼          ▼
 ┌─────┐        ┌──────┐      ┌──────────┐  ┌─────┐  ┌─────┐
 │ RSI │        │ MACD │      │Bollinger │  │ SMA │  │ EMA │
 │ (14)│        │      │      │  Bands   │  │(20)│  │(20)│
 └─────┘        └──────┘      └──────────┘  └─────┘  └─────┘
    │               │               │          │          │
    │ Signal        │ Signal        │ Signal   │ Signal   │ Signal
    │ + Conf        │ + Conf        │ + Conf   │ + Conf   │ + Conf
    │               │               │          │          │
    └───────────────┼───────────────┴──────────┴──────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │  Signal Aggregator        │
        │  - Normalize scores       │
        │  - Weight by confidence   │
        │  - Average signals        │
        └───────────────────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │ Aggregated Score          │
        │ & Confidence              │
        └───────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
    ┌─────────┐         ┌──────────────┐
    │ Validate │        │ Check Rules   │
    │ Thresholds│       │- Min conf 0.6 │
    │- Score   │        │- Consensus ≥3 │
    │  ≥ 0.3   │        │- Not halted    │
    └─────────┘        └──────────────┘
        │                       │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │  Final Decision           │
        │  BUY / SELL / HOLD        │
        └───────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
    ┌─────────┐         ┌──────────────┐
    │ Trading │         │ Position      │
    │ Engine  │         │ Management    │
    │ (Execute)│        │ (Track/Close) │
    └─────────┘         └──────────────┘
```

---

## Position Lifecycle

```
                   BUY SIGNAL
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Check Risk Manager           │
        │  - Sufficient balance?        │
        │  - Exposure < 20%?            │
        │  - Daily loss ok?             │
        └──────────────────────────────┘
                       │
                       ▼ (Approved)
        ┌──────────────────────────────┐
        │  Calculate Position Size      │
        │  Max = 2% of capital          │
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Calculate Risk Levels        │
        │  Stop Loss = Entry × 0.97     │
        │  Take Profit = Entry × 1.06   │
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  OPEN POSITION                │
        │  ✓ Long at entry price        │
        │  ✓ Set SL and TP              │
        │  ✓ Update balance             │
        └──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
    ┌─────┐      ┌──────┐      ┌──────────┐
    │SL HIT│      │TP HIT│      │SELL SIGNAL│
    │-3%  │      │+6%   │      │Score ≤-0.3│
    └─────┘      └──────┘      └──────────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  CLOSE POSITION               │
        │  - Exit at market price       │
        │  - Calculate P&L              │
        │  - Realize gains/losses       │
        │  - Update balance             │
        │  - Log closure reason         │
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Update Daily P&L             │
        │  Check if daily loss > -5%?   │
        │  If yes: HALT TRADING         │
        └──────────────────────────────┘
                       │
                       ▼
                 Position CLOSED
```

---

## Indicator Signal Generation Examples

### RSI Decision Tree
```
                    RSI Value
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
    < 30            30-70          > 70
     │               │               │
     ▼               ▼               ▼
    BUY          Weak Signal       SELL
 Conf: High      Conf: Low      Conf: High
 (0.7-1.0)       (0.1-0.5)      (0.7-1.0)
```

### MACD Decision Tree
```
                 Histogram Value
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
      > 0                             < 0
    BULLISH                        BEARISH
      │                               │
      ▼                               ▼
     BUY                             SELL
     │                               │
     │ Confidence based on         │ Confidence based on
     │ histogram magnitude         │ histogram magnitude
     │ + 20% boost if             │ + 20% boost if
     │   crossover detected       │   crossover detected
     │                             │
     ▼                             ▼
  0.1 - 1.0                    0.1 - 1.0
```

### Bollinger Bands Decision Tree
```
             Price Position Within Bands
                        │
        ┌───────────────┼───────────────┬─────────────────┐
        │               │               │                 │
        ▼               ▼               ▼                 ▼
    At Lower       Middle Area      At Upper        Volatility Check
    (0-30%)        (30-70%)         (70-100%)           │
        │               │               │                 │
        ▼               ▼               ▼                 │
      BUY             HOLD            SELL         Bandwidth < 2%?
    High Conf     Medium Conf       High Conf           │
   (0.7-1.0)      (0.3)            (0.7-1.0)       ┌───┴────┐
                                                     │        │
                                                    Yes      No
                                                     │        │
                                                     ▼        ▼
                                              -20% Conf   -10% Conf
```

---

## Risk Management Flowchart

```
                    New Trade Request
                            │
                            ▼
              ┌─────────────────────────┐
              │ Check Daily Loss Limit   │
              │ Current Loss < 5%?       │
              └─────────────────────────┘
                      │         │
                     Yes        No
                      │         │
                      ▼         ▼
                  [Continue]  [HALT]
                      │         │
                      ▼         │
              ┌─────────────────────────┐
              │ Check Available Balance  │
              │ Balance > Position Cost? │
              └─────────────────────────┘
                      │         │
                     Yes        No
                      │         │
                      ▼         ▼
                  [Continue]  [REJECT]
                      │         │
                      ▼         │
              ┌─────────────────────────┐
              │ Check Total Exposure     │
              │ Total Exp < 20%?         │
              └─────────────────────────┘
                      │         │
                     Yes        No
                      │         │
                      ▼         ▼
                  [Continue]  [REJECT]
                      │         │
                      ▼         │
              ┌─────────────────────────┐
              │ Calculate Position Size  │
              │ Size = min(2%, risk-adj) │
              └─────────────────────────┘
                      │
                      ▼
              ┌─────────────────────────┐
              │ Calculate Stop Loss      │
              │ SL = Entry × (1 - 3%)    │
              └─────────────────────────┘
                      │
                      ▼
              ┌─────────────────────────┐
              │ Calculate Take Profit    │
              │ TP = Entry × (1 + 6%)    │
              └─────────────────────────┘
                      │
                      ▼
              ┌─────────────────────────┐
              │ EXECUTE TRADE            │
              │ ✓ Create Position        │
              │ ✓ Update Balance         │
              │ ✓ Log Trade              │
              └─────────────────────────┘
```

---

## Price Action vs Indicators

### Example: Bitcoin Rally

```
Price Action                    Indicators Signals
─────────────────────────────────────────────────────
   $47,000 ────  Resistance ──→  RSI = 72 (OVERBOUGHT)
           │                      MACD (Positive)
   $46,000 ║                      BB (Near upper)
           ║                      Result: SELL signal
   $45,000 ║────  Support   ──→  RSI = 28 (OVERSOLD)
           │                      MACD (Negative)
   $44,000 ▼                      BB (Near lower)
                                  Result: BUY signal

Example Signal Aggregation:
- RSI (28): BUY (conf 0.8)
- MACD: BUY (conf 0.65)
- BB: BUY (conf 0.75)
- SMA: BUY (conf 0.6)
- EMA: BUY (conf 0.55)
─────────────────────────
Score: (1+1+1+1+1) × avg(conf) / 5 = 0.67
Consensus: 5/5 (100%) → STRONG BUY
```

---

## Daily Trading Cycle

```
Day Start (00:00 UTC)
    │
    ▼
┌─────────────────────┐
│ Reset Daily P&L     │
│ Resume Trading      │
│ (if previously halted)
└─────────────────────┘
    │
    ├─ Every 5 min: Check signals
    │  ├─ 00:05 - Check
    │  ├─ 00:10 - Check (maybe BUY)
    │  ├─ 00:15 - Check
    │  ├─ 00:20 - Check (maybe SELL)
    │  └─ ... continue
    │
    ├─ Monitor open positions
    │  ├─ Update prices
    │  ├─ Check SL/TP
    │  ├─ Execute exits if needed
    │
    ├─ Track daily P&L
    │  ├─ Sum all closed positions
    │  ├─ Check against limit (-5%)
    │  ├─ If breach: HALT
    │
    └─ ... until 23:59
         │
         ▼
    Day End (23:59 UTC)
         │
         ▼
    ┌─────────────────────┐
    │ Finalize Daily P&L  │
    │ Log Performance     │
    │ Prepare for Day+1   │
    └─────────────────────┘
```

---

## Risk vs Reward Profile

```
Win Scenario                 Loss Scenario
─────────────────────────────────────────
Entry: $100                  Entry: $100
Take Profit: $106            Stop Loss: $97
Profit: +$6 (+6%)            Loss: -$3 (-3%)

Position Size: 1 unit        Position Size: 1 unit
Max Account Risk: 2%         Max Account Risk: 2%

On $10k account:             On $10k account:
├─ Max Win: $600             ├─ Max Loss: $300
│  (from +6% at 100 units)   │  (from -3% at 100 units)
│                             │
├─ Risk:Reward = 1:2          ├─ Safety cushion: 2x
└─ Attractive ratio          └─ Tight risk control
```

---

## Confidence Scoring System

```
Individual Indicator Confidence (0.0 - 1.0)
                    │
        ┌───────────┼───────────┐
        │           │           │
     0.0-0.3     0.3-0.6      0.6-1.0
    (Weak)     (Medium)      (Strong)
        │           │           │
        ▼           ▼           ▼
    Skip      Consider      Trading
    Trade     with caution    Signal

Example:
┌─────────────────────────────────┐
│ RSI: 0.8 (Strong overbought)    │
│ MACD: 0.6 (Medium positive)     │
│ BB: 0.7 (Strong lower band)     │
│ SMA: 0.55 (Medium bullish)      │
│ EMA: 0.5 (Medium bullish)       │
├─────────────────────────────────┤
│ Aggregated: 0.67 (Strong)       │
│ Consensus: 5/5 (100%)           │
│ Action: EXECUTE BUY             │
└─────────────────────────────────┘
```

---

## Market Regime Detection (Conceptual)

```
Current Strategy Behavior by Market Condition

Trending Market              Sideways Market
──────────────────          ────────────────
    ↑↑↑                         ═══════
 Excellent                       Poor
    │                            │
 ├─ Fast signals          ├─ Whipsaws
 ├─ Clear direction       ├─ False breakouts
 ├─ High Win Rate         ├─ Low Win Rate
 └─ Good for Strategy     └─ Needs Improvement

SOLUTION: Add Trend Filter
Before trading:
✓ Is price above 200-day MA? (trend confirmation)
✗ Skip if price ranges between MA (sideways)
```

---

## Configuration Impact on Behavior

```
Parameter Adjustment     Effect
─────────────────────────────────────────
↑ min_confidence         More selective, fewer trades
↓ min_confidence         More aggressive, more trades

↑ min_consensus          Stricter, wait for agreement
↓ min_consensus          Looser, trade with less agreement

↑ Stop Loss %            Wider stops, allow more breathing room
↓ Stop Loss %            Tighter stops, faster exits

↑ Take Profit %          Greedy, wait for bigger gains
↓ Take Profit %          Conservative, lock in gains quickly

↑ Position Size %        More capital at risk per trade
↓ Position Size %        Smaller size, slower growth

↑ Daily Loss Limit %     Trade more before halt trigger
↓ Daily Loss Limit %     Halt trading sooner
```

---

**Last Updated:** 2025-11-04
