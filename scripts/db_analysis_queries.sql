-- Database Analysis and Verification Queries
-- Purpose: Manual SQL queries for data quality inspection
-- Date: 2025-11-20

-- ============================================================================
-- 1. BASIC DATA SUMMARY
-- ============================================================================

-- Overview of all symbols
SELECT
    symbol,
    interval,
    COUNT(*) as total_candles,
    MIN(timestamp) as earliest_date,
    MAX(timestamp) as latest_date,
    MAX(timestamp) - MIN(timestamp) as date_range,
    ROUND(AVG(close)::numeric, 2) as avg_price,
    ROUND(MIN(close)::numeric, 2) as min_price,
    ROUND(MAX(close)::numeric, 2) as max_price,
    ROUND(STDDEV(close)::numeric, 2) as price_stddev
FROM candles
WHERE interval = '60'
GROUP BY symbol, interval
ORDER BY symbol;


-- ============================================================================
-- 2. OUTLIER DETECTION - PRICE EXTREMES
-- ============================================================================

-- Find extreme prices (potential outliers)
WITH stats AS (
    SELECT
        symbol,
        AVG(close) as mean_price,
        STDDEV(close) as stddev_price
    FROM candles
    WHERE interval = '60'
    GROUP BY symbol
)
SELECT
    c.symbol,
    c.timestamp,
    c.close,
    s.mean_price,
    s.stddev_price,
    ABS(c.close - s.mean_price) / NULLIF(s.stddev_price, 0) as z_score
FROM candles c
JOIN stats s ON c.symbol = s.symbol
WHERE c.interval = '60'
    AND ABS(c.close - s.mean_price) / NULLIF(s.stddev_price, 0) > 3
ORDER BY c.symbol, ABS(c.close - s.mean_price) / NULLIF(s.stddev_price, 0) DESC;


-- ============================================================================
-- 3. DETECT SUDDEN PRICE JUMPS
-- ============================================================================

-- Find candles with >20% price change
WITH price_changes AS (
    SELECT
        symbol,
        timestamp,
        close,
        LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_close,
        ABS((close - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp))
            / NULLIF(LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp), 0)) as pct_change
    FROM candles
    WHERE interval = '60'
)
SELECT
    symbol,
    timestamp,
    ROUND(prev_close::numeric, 2) as previous_close,
    ROUND(close::numeric, 2) as current_close,
    ROUND((pct_change * 100)::numeric, 2) as pct_change
FROM price_changes
WHERE pct_change > 0.20  -- 20% threshold
ORDER BY pct_change DESC;


-- ============================================================================
-- 4. OHLCV CONSISTENCY CHECKS
-- ============================================================================

-- Find inconsistent OHLCV data
SELECT
    symbol,
    timestamp,
    open,
    high,
    low,
    close,
    volume,
    CASE
        WHEN high < low THEN 'High < Low'
        WHEN close > high THEN 'Close > High'
        WHEN close < low THEN 'Close < Low'
        WHEN open > high THEN 'Open > High'
        WHEN open < low THEN 'Open < Low'
        WHEN volume < 0 THEN 'Negative Volume'
        WHEN close <= 0 OR open <= 0 OR high <= 0 OR low <= 0 THEN 'Zero/Negative Price'
        ELSE 'Other'
    END as issue_type
FROM candles
WHERE interval = '60'
    AND (
        high < low OR
        close > high OR
        close < low OR
        open > high OR
        open < low OR
        volume < 0 OR
        close <= 0 OR
        open <= 0 OR
        high <= 0 OR
        low <= 0
    )
ORDER BY symbol, timestamp;


-- ============================================================================
-- 5. DETECT DATA GAPS (Missing Timestamps)
-- ============================================================================

-- Find gaps in hourly data (>2 hours between candles)
WITH time_diffs AS (
    SELECT
        symbol,
        timestamp,
        LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_timestamp,
        timestamp - LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as time_diff
    FROM candles
    WHERE interval = '60'
)
SELECT
    symbol,
    prev_timestamp,
    timestamp as current_timestamp,
    time_diff,
    EXTRACT(EPOCH FROM time_diff) / 3600 as hours_gap
FROM time_diffs
WHERE time_diff > INTERVAL '2 hours'
ORDER BY symbol, time_diff DESC;


-- ============================================================================
-- 6. DUPLICATE DETECTION
-- ============================================================================

-- Find duplicate candles (same symbol, interval, timestamp)
SELECT
    symbol,
    interval,
    timestamp,
    COUNT(*) as duplicate_count
FROM candles
WHERE interval = '60'
GROUP BY symbol, interval, timestamp
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;


-- ============================================================================
-- 7. DATA COMPLETENESS CHECK
-- ============================================================================

-- Check how many candles we should have vs actual
WITH expected_candles AS (
    SELECT
        symbol,
        MIN(timestamp) as start_time,
        MAX(timestamp) as end_time,
        EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) / 3600 as expected_hours
    FROM candles
    WHERE interval = '60'
    GROUP BY symbol
),
actual_candles AS (
    SELECT
        symbol,
        COUNT(*) as actual_count
    FROM candles
    WHERE interval = '60'
    GROUP BY symbol
)
SELECT
    e.symbol,
    e.start_time,
    e.end_time,
    ROUND(e.expected_hours::numeric) as expected_candles,
    a.actual_count,
    ROUND(e.expected_hours::numeric) - a.actual_count as missing_candles,
    ROUND((a.actual_count / NULLIF(e.expected_hours, 0) * 100)::numeric, 2) as completeness_pct
FROM expected_candles e
JOIN actual_candles a ON e.symbol = a.symbol
ORDER BY completeness_pct ASC;


-- ============================================================================
-- 8. VOLUME ANALYSIS
-- ============================================================================

-- Find unusual volume (>10x average)
WITH avg_volumes AS (
    SELECT
        symbol,
        AVG(volume) as avg_volume,
        STDDEV(volume) as stddev_volume
    FROM candles
    WHERE interval = '60'
    GROUP BY symbol
)
SELECT
    c.symbol,
    c.timestamp,
    ROUND(c.volume::numeric, 2) as volume,
    ROUND(a.avg_volume::numeric, 2) as avg_volume,
    ROUND((c.volume / NULLIF(a.avg_volume, 0))::numeric, 2) as volume_ratio
FROM candles c
JOIN avg_volumes a ON c.symbol = a.symbol
WHERE c.interval = '60'
    AND c.volume > a.avg_volume * 10
ORDER BY c.symbol, volume_ratio DESC;


-- ============================================================================
-- 9. RECENT DATA CHECK (Last 24 hours)
-- ============================================================================

-- Verify we have recent data
SELECT
    symbol,
    MAX(timestamp) as latest_candle,
    NOW() - MAX(timestamp) as time_since_last_update,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours') as candles_last_24h
FROM candles
WHERE interval = '60'
GROUP BY symbol
ORDER BY symbol;


-- ============================================================================
-- 10. PRICE STATISTICS BY SYMBOL
-- ============================================================================

-- Comprehensive price statistics
SELECT
    symbol,
    COUNT(*) as total_candles,
    ROUND(MIN(close)::numeric, 2) as min_price,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY close)::numeric, 2) as q1_price,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY close)::numeric, 2) as median_price,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY close)::numeric, 2) as q3_price,
    ROUND(MAX(close)::numeric, 2) as max_price,
    ROUND(AVG(close)::numeric, 2) as avg_price,
    ROUND(STDDEV(close)::numeric, 2) as stddev_price,
    ROUND((STDDEV(close) / NULLIF(AVG(close), 0) * 100)::numeric, 2) as coefficient_of_variation
FROM candles
WHERE interval = '60'
GROUP BY symbol
ORDER BY symbol;


-- ============================================================================
-- CLEANUP OPERATIONS (Use with caution!)
-- ============================================================================

-- Delete duplicate candles (keeps earliest entry)
-- UNCOMMENT TO RUN:
-- DELETE FROM candles a USING (
--     SELECT MIN(ctid) as ctid, symbol, interval, timestamp
--     FROM candles
--     GROUP BY symbol, interval, timestamp
--     HAVING COUNT(*) > 1
-- ) b
-- WHERE a.symbol = b.symbol
--     AND a.interval = b.interval
--     AND a.timestamp = b.timestamp
--     AND a.ctid <> b.ctid;

-- Delete candles with invalid prices
-- UNCOMMENT TO RUN:
-- DELETE FROM candles
-- WHERE close <= 0 OR open <= 0 OR high <= 0 OR low <= 0;

-- Delete candles with OHLCV inconsistencies
-- UNCOMMENT TO RUN:
-- DELETE FROM candles
-- WHERE high < low
--     OR close > high
--     OR close < low
--     OR open > high
--     OR open < low;
