# Data Enhancement Architecture

**Visual guide to data flow and system components**

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA ENHANCEMENT SYSTEM                           │
└─────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │   USER      │
                              │  Executes   │
                              └──────┬──────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
            ┌───────▼───────┐ ┌─────▼─────┐ ┌───────▼────────┐
            │  Quick Start  │ │  Summary  │ │  Technical     │
            │  Guide        │ │  Document │ │  Documentation │
            └───────────────┘ └───────────┘ └────────────────┘
                    │
                    │ Reads and executes
                    │
            ┌───────▼────────────────────────────────────────────────┐
            │                                                         │
            │            EXECUTION LAYER                              │
            │                                                         │
            │  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
            │  │ Connection  │  │  Enhancement │  │  Validation  │  │
            │  │    Test     │─▶│    Script    │─▶│   Script     │  │
            │  └─────────────┘  └──────┬───────┘  └──────────────┘  │
            │                           │                             │
            └───────────────────────────┼─────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────▼────────┐  ┌───────▼────────┐  ┌──────▼─────┐
            │  TimescaleDB   │  │  Bybit API     │  │  Reports   │
            │  (localhost:   │  │  (Historical   │  │  (Markdown │
            │   5433)        │  │   Data)        │  │   Files)   │
            └────────────────┘  └────────────────┘  └────────────┘
                    │
                    │ Enhanced data
                    │
            ┌───────▼────────┐
            │  ML Prediction │
            │    Service     │
            │  (Retraining)  │
            └────────────────┘
```

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW PIPELINE                             │
└─────────────────────────────────────────────────────────────────────────┘

PHASE 1: ANALYSIS
─────────────────
    TimescaleDB
         │
         │ SQL Query: SELECT * FROM candles
         │ WHERE symbol = ? AND interval = '60'
         ▼
    pandas DataFrame
         │
         │ Statistical Analysis:
         │ • Z-score calculation
         │ • IQR calculation
         │ • Price jump detection
         │ • OHLCV validation
         ▼
    Quality Report
         │
         │ Metrics:
         │ • Total candles: 720
         │ • Date coverage: 30 days
         │ • Outliers: 89 (12.4%)
         │ • Quality score: 45/100
         │ • ML-ready: NO
         ▼
    Decision Matrix
         ├── Needs Cleaning? ──▶ YES ──▶ Go to Phase 2
         └── Needs Extension? ─▶ YES ──▶ Go to Phase 3


PHASE 2: CLEANING
─────────────────
    Quality Report
         │
         │ Extract: outlier_indices = [23, 45, 67, ...]
         ▼
    pandas DataFrame
         │
         │ Mark outliers as NaN:
         │ df.loc[outlier_indices, ['open','high','low','close']] = NaN
         ▼
    Interpolation
         │
         │ Linear interpolation:
         │ df.interpolate(method='linear', limit_direction='both')
         ▼
    Cleaned DataFrame
         │
         │ UPDATE candles SET
         │ open=?, high=?, low=?, close=?, volume=?
         │ WHERE symbol=? AND timestamp=?
         ▼
    TimescaleDB
         │
         │ Verify: Re-analyze data
         ▼
    Quality Check
         │
         │ Outliers: 0 (0%)
         │ Quality score: 85/100
         ▼
    Go to Phase 3


PHASE 3: EXTENSION
──────────────────
    Date Range Calculator
         │
         │ Current: 2025-10-20 to 2025-11-19 (30 days)
         │ Target:  2025-07-20 to 2025-11-19 (120 days)
         │ Fetch:   2025-07-20 to 2025-10-19 (90 days gap)
         ▼
    Bybit API Request Loop
         │
         │ For each batch (200 candles):
         │ GET /v5/market/kline
         │ params: {
         │   category: 'spot',
         │   symbol: 'BTCUSDT',
         │   interval: '60',
         │   start: timestamp_ms,
         │   end: timestamp_ms,
         │   limit: 200
         │ }
         ▼
    API Response Parser
         │
         │ Parse JSON:
         │ [timestamp, open, high, low, close, volume, turnover]
         │
         │ Convert to dict:
         │ {
         │   'timestamp': datetime,
         │   'open': float,
         │   'high': float,
         │   'low': float,
         │   'close': float,
         │   'volume': float
         │ }
         ▼
    Database Insertion
         │
         │ INSERT INTO candles
         │ (symbol, interval, timestamp, open, high, low, close, volume)
         │ VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         │ ON CONFLICT (symbol, interval, timestamp) DO NOTHING
         ▼
    TimescaleDB
         │
         │ New total: 2,880 candles (120 days)
         ▼
    Go to Phase 4


PHASE 4: VALIDATION
───────────────────
    TimescaleDB
         │
         │ Fetch enhanced data
         ▼
    Validation Checks
         │
         ├─▶ Coverage Check
         │   │ Days = (max_timestamp - min_timestamp).days
         │   │ Pass if days >= 90
         │   └─▶ Result: 120 days ✓
         │
         ├─▶ Outlier Check
         │   │ Z-score, IQR, Price jumps
         │   │ Pass if total_outliers = 0
         │   └─▶ Result: 0 outliers ✓
         │
         ├─▶ Gap Check
         │   │ time_diffs = df['timestamp'].diff()
         │   │ gaps = time_diffs > 1.5 hours
         │   │ Pass if len(gaps) = 0
         │   └─▶ Result: 0 gaps ✓
         │
         ├─▶ Consistency Check
         │   │ Validate: High >= Low, Close <= High, etc.
         │   │ Pass if inconsistent_count = 0
         │   └─▶ Result: 0 inconsistencies ✓
         │
         ├─▶ ML Features Check
         │   │ Calculate: returns, RSI, MA, etc.
         │   │ Pass if no NaN/Inf values
         │   └─▶ Result: All features valid ✓
         │
         └─▶ Recent Data Check
             │ hours_ago = (now - max_timestamp).hours
             │ Pass if hours_ago <= 24
             └─▶ Result: 2 hours ago ✓
         │
         │ All checks passed
         ▼
    Quality Score Calculation
         │
         │ Score = 100
         │   - (outlier_pct × 100)
         │   - (gap_pct × 100)
         │
         │ Result: 95/100
         ▼
    ML Readiness Assessment
         │
         │ Critical checks:
         │ ✓ Coverage >= 90 days
         │ ✓ Outliers = 0
         │ ✓ ML features calculable
         │
         │ Result: ML-READY ✓
         ▼
    Validation Report
         │
         │ Symbol: BTCUSDT
         │ Status: EXCELLENT
         │ Quality: 95/100
         │ ML-Ready: YES
         ▼
    Go to Phase 5


PHASE 5: REPORTING
──────────────────
    Aggregated Results
         │
         │ All symbols validated
         ▼
    Report Generator
         │
         │ Generate markdown tables:
         │ • Executive summary
         │ • Symbol-by-symbol details
         │ • Pass/fail matrix
         │ • Recommendations
         ▼
    Markdown Files
         │
         ├─▶ data_quality_report.md
         │   └─▶ Enhancement results
         │
         └─▶ data_validation_report.md
             └─▶ Validation results
         │
         ▼
    User Review
         │
         │ Read reports
         │ Confirm ML-readiness
         ▼
    ML Model Retraining
         │
         │ Use enhanced data
         │ Compare R² scores
         ▼
    COMPLETE ✓
```

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        COMPONENT BREAKDOWN                               │
└─────────────────────────────────────────────────────────────────────────┘

DataQualityEnhancer
├── __init__()
│   ├─ db_params: {host, port, dbname, user, password}
│   ├─ symbols: ['BTCUSDT', 'ETHUSDT', ...]
│   ├─ thresholds: {z_score: 3.0, iqr: 1.5, max_jump: 0.20}
│   └─ target_days: 120
│
├── connect_db()
│   └─ Returns: psycopg2.connection
│
├── fetch_symbol_data(symbol)
│   ├─ SQL: SELECT * FROM candles WHERE symbol=? AND interval='60'
│   └─ Returns: pandas.DataFrame
│
├── detect_outliers_zscore(series)
│   ├─ Calculate: z = (x - μ) / σ
│   └─ Returns: Boolean mask (True = outlier)
│
├── detect_outliers_iqr(series)
│   ├─ Calculate: IQR = Q3 - Q1
│   ├─ Bounds: [Q1 - 1.5×IQR, Q3 + 1.5×IQR]
│   └─ Returns: Boolean mask
│
├── detect_price_jumps(df)
│   ├─ Calculate: pct_change = |close[t] - close[t-1]| / close[t-1]
│   └─ Returns: Boolean mask (True if >20%)
│
├── detect_ohlcv_inconsistencies(df)
│   ├─ Check: High >= Low, Close <= High, etc.
│   └─ Returns: Boolean mask
│
├── analyze_data_quality(symbol)
│   ├─ Calls: fetch_symbol_data()
│   ├─ Calls: detect_outliers_*()
│   ├─ Calls: detect_price_jumps()
│   ├─ Calls: detect_ohlcv_inconsistencies()
│   ├─ Calculate: quality_score
│   └─ Returns: Dict with metrics
│
├── clean_data(symbol, report)
│   ├─ Get: outlier_indices from report
│   ├─ Mark: df.loc[indices, cols] = NaN
│   ├─ Interpolate: df.interpolate(method='linear')
│   ├─ Update: Database UPDATE statements
│   └─ Returns: cleaned_count
│
├── fetch_historical_data_bybit(symbol, start, end)
│   ├─ Loop: Batch requests (200 candles each)
│   ├─ API: GET /v5/market/kline
│   ├─ Parse: JSON response to dict list
│   └─ Returns: List[Dict]
│
├── insert_historical_data(symbol, candles)
│   ├─ SQL: INSERT INTO candles ... ON CONFLICT DO NOTHING
│   └─ Returns: inserted_count
│
├── extend_historical_data(symbol, current_days)
│   ├─ Calculate: gap_start, gap_end
│   ├─ Calls: fetch_historical_data_bybit()
│   ├─ Calls: insert_historical_data()
│   └─ Returns: Dict with extension results
│
├── generate_final_report()
│   ├─ Aggregate: self.quality_reports
│   ├─ Format: Markdown tables
│   └─ Returns: String (markdown)
│
└── run_full_enhancement()
    ├─ For each symbol:
    │   ├─ analyze_data_quality()
    │   ├─ clean_data()
    │   ├─ extend_historical_data()
    │   └─ re-analyze_data_quality()
    ├─ generate_final_report()
    └─ Save: reports/data_quality_report.md


DataValidator
├── __init__()
│   ├─ db_params: {host, port, dbname, user, password}
│   ├─ symbols: ['BTCUSDT', 'ETHUSDT', ...]
│   └─ min_days_required: 90
│
├── validate_coverage(symbol, df)
│   ├─ Calculate: days = (max_timestamp - min_timestamp).days
│   ├─ Check: days >= min_days_required
│   └─ Returns: Dict {passed, days, message}
│
├── validate_no_outliers(df)
│   ├─ Check: Z-score, IQR, price jumps
│   ├─ Count: total_outliers
│   └─ Returns: Dict {passed, total, message}
│
├── validate_no_gaps(df)
│   ├─ Calculate: time_diffs = df['timestamp'].diff()
│   ├─ Find: gaps > 1.5 hours
│   └─ Returns: Dict {passed, gap_count, message}
│
├── validate_ohlcv_consistency(df)
│   ├─ Check: All OHLCV rules
│   └─ Returns: Dict {passed, inconsistent_count, message}
│
├── validate_ml_features(df)
│   ├─ Calculate: returns, RSI, MA, etc.
│   ├─ Check: No NaN/Inf values
│   └─ Returns: Dict {passed, nan_count, message}
│
├── validate_recent_data(df)
│   ├─ Calculate: hours_ago = now - max_timestamp
│   └─ Returns: Dict {passed, hours_ago, message}
│
├── calculate_data_quality_score(validations)
│   ├─ Weights: coverage=25, outliers=25, gaps=20, etc.
│   ├─ Score: Sum of passed checks × weights
│   └─ Returns: Float (0-100)
│
├── validate_symbol(symbol)
│   ├─ Calls: All validate_*() methods
│   ├─ Calls: calculate_data_quality_score()
│   ├─ Determine: ml_ready, status
│   └─ Returns: Dict with validation results
│
├── generate_validation_report()
│   ├─ Aggregate: self.validation_results
│   ├─ Format: Markdown tables
│   └─ Returns: String (markdown)
│
└── run_validation()
    ├─ For each symbol:
    │   └─ validate_symbol()
    ├─ generate_validation_report()
    └─ Save: reports/data_validation_report.md
```

---

## Database Schema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATABASE STRUCTURE                              │
└─────────────────────────────────────────────────────────────────────────┘

TimescaleDB (PostgreSQL 15+)
│
└─ Database: market_data
   │
   └─ Table: candles (Hypertable)
      │
      ├─ Columns:
      │  ├─ symbol      VARCHAR(20)      NOT NULL
      │  ├─ interval    VARCHAR(10)      NOT NULL
      │  ├─ timestamp   TIMESTAMPTZ      NOT NULL  ◀── Hypertable partition key
      │  ├─ open        DOUBLE PRECISION NOT NULL
      │  ├─ high        DOUBLE PRECISION NOT NULL
      │  ├─ low         DOUBLE PRECISION NOT NULL
      │  ├─ close       DOUBLE PRECISION NOT NULL
      │  └─ volume      DOUBLE PRECISION NOT NULL
      │
      ├─ Primary Key:
      │  └─ (symbol, interval, timestamp)  ◀── Prevents duplicates
      │
      ├─ Indexes:
      │  └─ Automatic time-based indexes (from hypertable)
      │
      └─ Chunks:
         ├─ _hyper_1_1_chunk (2025-07-01 to 2025-07-08)
         ├─ _hyper_1_2_chunk (2025-07-08 to 2025-07-15)
         ├─ _hyper_1_3_chunk (2025-07-15 to 2025-07-22)
         └─ ... (7-day chunks)

Data Volume:
├─ Before: 5,040 rows (30 days × 7 symbols × 24 hours)
├─ After:  20,160 rows (120 days × 7 symbols × 24 hours)
└─ Growth: 4× increase, ~50-100 MB additional storage
```

---

## API Integration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BYBIT API INTEGRATION                             │
└─────────────────────────────────────────────────────────────────────────┘

Endpoint: https://api.bybit.com/v5/market/kline

Request Flow:
│
├─ Calculate date range to fetch
│  ├─ current_earliest = 2025-10-20
│  ├─ target_start = 2025-07-20 (120 days ago)
│  └─ gap_to_fetch = 90 days
│
├─ Batch loop (90 days / 200 candles per request ≈ 11 requests)
│  │
│  └─ For each batch:
│     │
│     ├─ Calculate timestamps
│     │  ├─ start_ts = int(batch_start.timestamp() * 1000)
│     │  └─ end_ts = int(batch_end.timestamp() * 1000)
│     │
│     ├─ Build request
│     │  └─ GET /v5/market/kline?
│     │      category=spot&
│     │      symbol=BTCUSDT&
│     │      interval=60&
│     │      start=1721433600000&
│     │      end=1722211200000&
│     │      limit=200
│     │
│     ├─ Send request
│     │  └─ requests.get(endpoint, params=params, timeout=10)
│     │
│     ├─ Parse response
│     │  └─ {
│     │      "retCode": 0,
│     │      "retMsg": "OK",
│     │      "result": {
│     │        "symbol": "BTCUSDT",
│     │        "category": "spot",
│     │        "list": [
│     │          [
│     │            "1721433600000",  ← timestamp
│     │            "67234.5",        ← open
│     │            "67891.2",        ← high
│     │            "67100.0",        ← low
│     │            "67543.8",        ← close
│     │            "123.45",         ← volume
│     │            "8345678.90"      ← turnover
│     │          ],
│     │          ...
│     │        ]
│     │      }
│     │    }
│     │
│     └─ Convert to dict
│        └─ {
│            'timestamp': datetime(2025, 7, 20, 0, 0),
│            'open': 67234.5,
│            'high': 67891.2,
│            'low': 67100.0,
│            'close': 67543.8,
│            'volume': 123.45
│          }
│
└─ Insert to database
   └─ INSERT INTO candles ... ON CONFLICT DO NOTHING

Rate Limits:
├─ Bybit: 50 requests/second (public endpoint)
├─ Script: Sequential requests (no parallelization)
└─ Safety: Can add time.sleep(0.1) if needed

Error Handling:
├─ Timeout: 10 seconds per request
├─ HTTP errors: response.raise_for_status()
├─ API errors: Check retCode in response
└─ Retry: Manual re-run if batch fails
```

---

## File Interaction Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       FILE INTERACTION DIAGRAM                           │
└─────────────────────────────────────────────────────────────────────────┘

User
 │
 ├─ Reads ──▶ QUICK_START_DATA_ENHANCEMENT.md
 │            DATA_ENHANCEMENT_SUMMARY.md
 │            DATA_ENHANCEMENT_README.md
 │
 ├─ Executes ─▶ run_data_enhancement.sh
 │              │
 │              ├─ Installs ──▶ requirements_data_enhancement.txt
 │              │
 │              ├─ Runs ──▶ test_db_connection.py
 │              │           │
 │              │           └─ Connects ──▶ TimescaleDB
 │              │
 │              ├─ Runs ──▶ data_quality_enhancement.py
 │              │           │
 │              │           ├─ Connects ──▶ TimescaleDB
 │              │           │               │
 │              │           │               ├─ Reads: candles table
 │              │           │               └─ Writes: candles table
 │              │           │
 │              │           ├─ Calls ──▶ Bybit API
 │              │           │
 │              │           └─ Generates ──▶ data_quality_report.md
 │              │
 │              └─ Runs ──▶ validate_enhanced_data.py
 │                          │
 │                          ├─ Connects ──▶ TimescaleDB
 │                          │
 │                          └─ Generates ──▶ data_validation_report.md
 │
 ├─ Or Executes ─▶ data_quality_enhancement.py (directly)
 │
 ├─ Or Queries ─▶ psql ──▶ db_analysis_queries.sql ──▶ TimescaleDB
 │
 └─ Reviews ──▶ data_quality_report.md
                data_validation_report.md
                logs/data_enhancement_*.log

All files reside in:
/mnt/d/Bimo_max/crypto-trading-bot/
```

---

## Execution Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION TIMELINE                               │
└─────────────────────────────────────────────────────────────────────────┘

T+0:00 ─ User executes: python3 scripts/data_quality_enhancement.py
│
T+0:01 ─ Script initializes
         ├─ Load configuration
         ├─ Test database connection
         └─ Print startup message
│
T+0:02 ─ Start symbol loop (BTCUSDT)
         │
T+0:03 ─ Analyze BTCUSDT
         ├─ Fetch 720 candles from database (30 days)
         ├─ Calculate Z-scores, IQR
         ├─ Detect price jumps
         ├─ Check OHLCV consistency
         └─ Generate quality report
│
T+0:04 ─ Clean BTCUSDT
         ├─ Mark 12 outliers as NaN
         ├─ Interpolate values
         └─ Update database (12 UPDATE statements)
│
T+0:05 ─ Extend BTCUSDT
         ├─ Calculate gap: 90 days needed
         ├─ Batch 1: Fetch 200 candles from Bybit
         ├─ Batch 2: Fetch 200 candles
         ├─ ...
         ├─ Batch 11: Fetch 160 candles
         └─ Insert 2,160 candles to database
│
T+0:45 ─ Re-analyze BTCUSDT
         └─ Verify: 120 days, 0 outliers, quality 95/100
│
T+0:46 ─ Next symbol (ETHUSDT)
         └─ Repeat steps...
│
T+1:00 ─ Symbol 2 complete
│
T+1:15 ─ Symbol 3 complete (BNBUSDT - many outliers cleaned)
│
... (continue for all 7 symbols)
│
T+5:00 ─ All symbols complete
│
T+5:01 ─ Generate final report
         ├─ Aggregate results
         ├─ Calculate statistics
         ├─ Format markdown
         └─ Write to reports/data_quality_report.md
│
T+5:02 ─ Script complete
         └─ Print summary and exit

Total Time: ~5 minutes (varies by network speed)
```

---

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ERROR HANDLING FLOW                               │
└─────────────────────────────────────────────────────────────────────────┘

Execution Start
     │
     ├─ Database Connection Test
     │  ├─ Success ──▶ Continue
     │  └─ Failure ──▶ Print error
     │                 ├─ Show troubleshooting steps
     │                 ├─ Check docker ps
     │                 ├─ Verify credentials
     │                 └─ Exit(1)
     │
     ├─ Data Fetching
     │  ├─ Success ──▶ Continue
     │  ├─ Empty result ──▶ Log warning
     │  │                  └─ Skip symbol
     │  └─ SQL error ──▶ Print error
     │                    ├─ Log details
     │                    └─ Skip symbol
     │
     ├─ API Request
     │  ├─ Success ──▶ Parse response
     │  ├─ Timeout ──▶ Retry once
     │  │              ├─ Success ──▶ Continue
     │  │              └─ Fail ──▶ Log error, skip batch
     │  ├─ HTTP 429 (Rate limit) ──▶ Wait 5 seconds
     │  │                            └─ Retry
     │  ├─ HTTP 4xx/5xx ──▶ Log error
     │  │                   └─ Skip batch
     │  └─ Network error ──▶ Log error
     │                       └─ Skip batch
     │
     ├─ Data Insertion
     │  ├─ Success ──▶ Continue
     │  ├─ Duplicate key ──▶ ON CONFLICT DO NOTHING
     │  │                    └─ Continue
     │  ├─ Constraint violation ──▶ Log error
     │  │                           └─ Skip record
     │  └─ SQL error ──▶ Rollback transaction
     │                   ├─ Log error
     │                   └─ Skip symbol
     │
     └─ Report Generation
        ├─ Success ──▶ Write file
        ├─ Permission error ──▶ Print error
        │                        └─ Show current directory
        └─ Disk full ──▶ Print error
                         └─ Check df -h

All errors are:
├─ Logged to console with context
├─ Include troubleshooting hints
└─ Allow script to continue (fail gracefully)

Exit codes:
├─ 0: Success
├─ 1: Fatal error (database connection failed)
└─ Warnings logged but exit 0 (partial success)
```

---

**End of Architecture Documentation**
