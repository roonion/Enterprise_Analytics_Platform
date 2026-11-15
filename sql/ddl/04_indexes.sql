-- ============================================================================
-- Additional Indexes and Performance Optimizations
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Composite indexes for common query patterns
-- ============================================================================

-- Transaction analysis by date and customer
CREATE INDEX IF NOT EXISTS idx_fact_txn_date_customer 
    ON analytics.fact_transactions(date_key, customer_sk);

-- Transaction analysis by date and product
CREATE INDEX IF NOT EXISTS idx_fact_txn_date_product 
    ON analytics.fact_transactions(date_key, product_sk);

-- Transaction analysis by customer and status
CREATE INDEX IF NOT EXISTS idx_fact_txn_customer_status 
    ON analytics.fact_transactions(customer_sk, status);

-- Session analysis by date and traffic source
CREATE INDEX IF NOT EXISTS idx_fact_sessions_date_traffic 
    ON analytics.fact_customer_sessions(date_key, traffic_source);

-- Session analysis by customer and conversion
CREATE INDEX IF NOT EXISTS idx_fact_sessions_customer_conv 
    ON analytics.fact_customer_sessions(customer_sk, conversion);

-- ============================================================================
-- Partial indexes for frequently filtered queries
-- ============================================================================

-- Only completed transactions (most common filter)
CREATE INDEX IF NOT EXISTS idx_fact_txn_completed 
    ON analytics.fact_transactions(date_key, customer_sk, total_amount_usd) 
    WHERE status = 'Completed';

-- High value transactions
CREATE INDEX IF NOT EXISTS idx_fact_txn_high_value 
    ON analytics.fact_transactions(date_key, customer_sk, total_amount_usd) 
    WHERE is_high_value = TRUE;

-- Current customers only
CREATE INDEX IF NOT EXISTS idx_dim_customers_current_segment 
    ON analytics.dim_customers(customer_segment, lifetime_value) 
    WHERE is_current = TRUE;

-- Active products only
CREATE INDEX IF NOT EXISTS idx_dim_products_active 
    ON analytics.dim_products(category, brand) 
    WHERE is_current = TRUE AND is_active = TRUE;

-- Converted sessions
CREATE INDEX IF NOT EXISTS idx_fact_sessions_converted 
    ON analytics.fact_customer_sessions(date_key, customer_sk) 
    WHERE conversion = TRUE;

-- Open support tickets
CREATE INDEX IF NOT EXISTS idx_fact_support_open 
    ON analytics.fact_support_interactions(created_date_key, priority) 
    WHERE status NOT IN ('closed', 'resolved');

-- ============================================================================
-- Expression indexes for common calculations
-- ============================================================================

-- Month from date_key for grouping
CREATE INDEX IF NOT EXISTS idx_fact_txn_month 
    ON analytics.fact_transactions((date_key / 100));

-- Year from date_key
CREATE INDEX IF NOT EXISTS idx_fact_txn_year 
    ON analytics.fact_transactions((date_key / 10000));

-- ============================================================================
-- Covering indexes for dashboard queries
-- ============================================================================

-- Daily revenue dashboard
CREATE INDEX IF NOT EXISTS idx_fact_txn_daily_revenue 
    ON analytics.fact_transactions(date_key, status) 
    INCLUDE (total_amount_usd, quantity, customer_sk);

-- Customer analysis dashboard
CREATE INDEX IF NOT EXISTS idx_fact_txn_customer_analysis 
    ON analytics.fact_transactions(customer_sk, date_key) 
    INCLUDE (total_amount_usd, quantity, status);

-- ============================================================================
-- BRIN indexes for time-series data (efficient for large tables)
-- ============================================================================

-- Transaction timestamp (for range queries on large tables)
CREATE INDEX IF NOT EXISTS idx_fact_txn_timestamp_brin 
    ON analytics.fact_transactions 
    USING BRIN (transaction_timestamp) 
    WITH (pages_per_range = 128);

-- Session start time
CREATE INDEX IF NOT EXISTS idx_fact_sessions_start_brin 
    ON analytics.fact_customer_sessions 
    USING BRIN (session_start) 
    WITH (pages_per_range = 128);

-- ============================================================================
-- GIN indexes for JSONB columns (if using)
-- ============================================================================

-- Data quality log details
CREATE INDEX IF NOT EXISTS idx_dq_log_details 
    ON analytics._data_quality_log 
    USING GIN (details);

-- ============================================================================
-- Statistics targets for frequently queried columns
-- ============================================================================

-- Increase statistics for better query plans
ALTER TABLE analytics.fact_transactions ALTER COLUMN date_key SET STATISTICS 1000;
ALTER TABLE analytics.fact_transactions ALTER COLUMN customer_sk SET STATISTICS 1000;
ALTER TABLE analytics.fact_transactions ALTER COLUMN status SET STATISTICS 500;
ALTER TABLE analytics.fact_transactions ALTER COLUMN total_amount_usd SET STATISTICS 500;

ALTER TABLE analytics.dim_customers ALTER COLUMN customer_segment SET STATISTICS 500;
ALTER TABLE analytics.dim_customers ALTER COLUMN country SET STATISTICS 500;

ALTER TABLE analytics.dim_products ALTER COLUMN category SET STATISTICS 500;
ALTER TABLE analytics.dim_products ALTER COLUMN brand SET STATISTICS 500;

-- ============================================================================
-- Materialized view for expensive aggregations
-- ============================================================================

-- Daily revenue summary (refreshed periodically)
DROP MATERIALIZED VIEW IF EXISTS analytics.mv_daily_revenue_summary;

CREATE MATERIALIZED VIEW analytics.mv_daily_revenue_summary AS
SELECT 
    t.date_key,
    dt.full_date,
    dt.year,
    dt.month,
    dt.quarter,
    COUNT(DISTINCT t.transaction_sk) as total_transactions,
    COUNT(DISTINCT t.customer_sk) as unique_customers,
    SUM(t.total_amount_usd) as total_revenue,
    AVG(t.total_amount_usd) as avg_transaction_value,
    SUM(t.quantity) as total_quantity,
    SUM(CASE WHEN t.status = 'Completed' THEN t.total_amount_usd ELSE 0 END) as completed_revenue,
    SUM(CASE WHEN t.status = 'Refunded' THEN t.total_amount_usd ELSE 0 END) as refunded_revenue,
    c.channel_name,
    SUM(CASE WHEN c.channel_code = 'WEB' THEN t.total_amount_usd ELSE 0 END) as web_revenue,
    SUM(CASE WHEN c.channel_code = 'MOBILE' THEN t.total_amount_usd ELSE 0 END) as mobile_revenue,
    SUM(CASE WHEN c.channel_code = 'STORE' THEN t.total_amount_usd ELSE 0 END) as store_revenue
FROM analytics.fact_transactions t
JOIN analytics.dim_time dt ON t.date_key = dt.date_key
LEFT JOIN analytics.dim_channels c ON t.channel_sk = c.channel_sk
GROUP BY t.date_key, dt.full_date, dt.year, dt.month, dt.quarter, c.channel_name
WITH DATA;

CREATE UNIQUE INDEX idx_mv_daily_revenue_date 
    ON analytics.mv_daily_revenue_summary(date_key, channel_name);

-- Refresh command (to be scheduled)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_daily_revenue_summary;

-- ============================================================================
-- Customer segment summary
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS analytics.mv_customer_segment_summary;

CREATE MATERIALIZED VIEW analytics.mv_customer_segment_summary AS
SELECT 
    dc.customer_segment,
    COUNT(DISTINCT dc.customer_sk) as customer_count,
    AVG(dc.lifetime_value) as avg_lifetime_value,
    COUNT(DISTINCT ft.transaction_sk) as total_transactions,
    SUM(ft.total_amount_usd) as total_revenue,
    AVG(ft.total_amount_usd) as avg_transaction_value
FROM analytics.dim_customers dc
LEFT JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
WHERE dc.is_current = TRUE
GROUP BY dc.customer_segment
WITH DATA;

CREATE UNIQUE INDEX idx_mv_segment_summary 
    ON analytics.mv_customer_segment_summary(customer_segment);

-- ============================================================================
-- Analyze tables for query optimizer
-- ============================================================================

ANALYZE analytics.dim_time;
ANALYZE analytics.dim_customers;
ANALYZE analytics.dim_products;
ANALYZE analytics.dim_channels;
ANALYZE analytics.dim_payment_methods;
ANALYZE analytics.dim_geography;
ANALYZE analytics.fact_transactions;
ANALYZE analytics.fact_customer_sessions;
ANALYZE analytics.fact_support_interactions;

