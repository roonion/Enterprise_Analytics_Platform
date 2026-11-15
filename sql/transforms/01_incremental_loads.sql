-- ============================================================================
-- Incremental Load Patterns
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- MERGE Pattern for SCD Type 2 Customer Dimension
-- ============================================================================

-- Step 1: Identify changed records
WITH source_data AS (
    SELECT * FROM analytics.dim_customers_staging
),
current_records AS (
    SELECT * FROM analytics.dim_customers WHERE is_current = TRUE
),
changed_records AS (
    SELECT 
        s.customer_id,
        s.first_name,
        s.last_name,
        s.email,
        s.phone,
        s.address,
        s.city,
        s.state,
        s.postal_code,
        s.country,
        s.customer_segment,
        c.customer_sk as existing_sk,
        CASE 
            WHEN c.customer_id IS NULL THEN 'INSERT'
            WHEN 
                COALESCE(s.email, '') <> COALESCE(c.email, '') OR
                COALESCE(s.phone, '') <> COALESCE(c.phone, '') OR
                COALESCE(s.address, '') <> COALESCE(c.address, '') OR
                COALESCE(s.customer_segment, '') <> COALESCE(c.customer_segment, '')
            THEN 'UPDATE'
            ELSE 'UNCHANGED'
        END as change_type
    FROM source_data s
    LEFT JOIN current_records c ON s.customer_id = c.customer_id
)
SELECT * FROM changed_records WHERE change_type <> 'UNCHANGED';

-- Step 2: Close old records for updates
UPDATE analytics.dim_customers dc
SET 
    effective_end_date = CURRENT_TIMESTAMP,
    is_current = FALSE,
    updated_at = CURRENT_TIMESTAMP
FROM (
    SELECT customer_id FROM changed_records WHERE change_type = 'UPDATE'
) changes
WHERE dc.customer_id = changes.customer_id
AND dc.is_current = TRUE;

-- Step 3: Insert new records (both new customers and new versions)
INSERT INTO analytics.dim_customers (
    customer_id, first_name, last_name, full_name, email, email_domain,
    phone, address, city, state, postal_code, country, customer_segment,
    effective_start_date, effective_end_date, is_current, version
)
SELECT 
    c.customer_id,
    c.first_name,
    c.last_name,
    c.first_name || ' ' || c.last_name,
    c.email,
    SPLIT_PART(c.email, '@', 2),
    c.phone,
    c.address,
    c.city,
    c.state,
    c.postal_code,
    c.country,
    c.customer_segment,
    CURRENT_TIMESTAMP,
    '9999-12-31 23:59:59'::TIMESTAMP,
    TRUE,
    COALESCE(
        (SELECT MAX(version) + 1 FROM analytics.dim_customers WHERE customer_id = c.customer_id),
        1
    )
FROM changed_records c
WHERE c.change_type IN ('INSERT', 'UPDATE');


-- ============================================================================
-- Incremental Transaction Load with Watermark
-- ============================================================================

-- Load transactions newer than watermark
INSERT INTO analytics.fact_transactions (
    customer_sk,
    product_sk,
    date_key,
    channel_sk,
    payment_method_sk,
    transaction_id,
    transaction_timestamp,
    quantity,
    unit_price_usd,
    total_amount_usd,
    original_amount,
    original_currency,
    exchange_rate,
    status,
    _loaded_at
)
SELECT 
    dc.customer_sk,
    dp.product_sk,
    TO_CHAR(s.transaction_timestamp, 'YYYYMMDD')::INTEGER,
    ch.channel_sk,
    pm.payment_method_sk,
    s.transaction_id,
    s.transaction_timestamp,
    s.quantity,
    s.unit_price_usd,
    s.total_amount_usd,
    s.original_amount,
    s.original_currency,
    s.exchange_rate,
    s.status,
    CURRENT_TIMESTAMP
FROM analytics.fact_transactions_staging s
-- Join to get surrogate keys
LEFT JOIN analytics.dim_customers dc 
    ON s.customer_id = dc.customer_id 
    AND dc.is_current = TRUE
LEFT JOIN analytics.dim_products dp 
    ON s.product_id = dp.product_id 
    AND dp.is_current = TRUE
LEFT JOIN analytics.dim_channels ch 
    ON UPPER(s.channel) = ch.channel_code
LEFT JOIN analytics.dim_payment_methods pm 
    ON UPPER(REPLACE(s.payment_method, ' ', '_')) = pm.payment_method_code
-- Filter by watermark
WHERE s.transaction_timestamp > (
    SELECT COALESCE(watermark_value, '1900-01-01'::TIMESTAMP)
    FROM analytics._watermarks
    WHERE table_name = 'transactions'
)
ON CONFLICT (transaction_id) DO UPDATE SET
    status = EXCLUDED.status,
    _loaded_at = CURRENT_TIMESTAMP;

-- Update watermark
INSERT INTO analytics._watermarks (table_name, watermark_column, watermark_value, updated_at)
SELECT 
    'transactions',
    'transaction_timestamp',
    MAX(transaction_timestamp),
    CURRENT_TIMESTAMP
FROM analytics.fact_transactions_staging
ON CONFLICT (table_name) 
DO UPDATE SET 
    watermark_value = EXCLUDED.watermark_value,
    updated_at = EXCLUDED.updated_at;


-- ============================================================================
-- Late-Arriving Fact Handling
-- ============================================================================

-- Identify late-arriving transactions and update dimension keys
-- (when transaction references a customer version that was updated after the fact arrived)

WITH late_facts AS (
    SELECT 
        ft.transaction_sk,
        ft.transaction_timestamp,
        dc.customer_sk as correct_customer_sk
    FROM analytics.fact_transactions ft
    JOIN analytics.dim_customers dc 
        ON ft.customer_sk = dc.customer_sk
    -- Find transactions where the customer dimension has been updated
    WHERE ft.transaction_timestamp BETWEEN dc.effective_start_date AND dc.effective_end_date
    AND ft.customer_sk <> dc.customer_sk
)
UPDATE analytics.fact_transactions ft
SET customer_sk = lf.correct_customer_sk
FROM late_facts lf
WHERE ft.transaction_sk = lf.transaction_sk;


-- ============================================================================
-- Session Load with Deduplication
-- ============================================================================

-- Insert new sessions, update existing ones
INSERT INTO analytics.fact_customer_sessions (
    customer_sk,
    date_key,
    channel_sk,
    session_id,
    session_start,
    session_end,
    device_type,
    browser,
    os,
    referrer,
    traffic_source,
    duration_seconds,
    page_views,
    events_count,
    engagement_score,
    session_category,
    is_bounce,
    conversion,
    _loaded_at
)
SELECT 
    dc.customer_sk,
    TO_CHAR(s.session_start, 'YYYYMMDD')::INTEGER,
    CASE 
        WHEN LOWER(s.device_type) = 'mobile' THEN 
            (SELECT channel_sk FROM analytics.dim_channels WHERE channel_code = 'MOBILE')
        ELSE 
            (SELECT channel_sk FROM analytics.dim_channels WHERE channel_code = 'WEB')
    END,
    s.session_id,
    s.session_start,
    s.session_end,
    s.device_type,
    s.browser,
    s.os,
    s.referrer,
    s.traffic_source,
    s.duration_seconds,
    s.page_views,
    s.events_count,
    s.engagement_score,
    s.session_category,
    s.is_bounce,
    s.conversion,
    CURRENT_TIMESTAMP
FROM analytics.fact_sessions_staging s
LEFT JOIN analytics.dim_customers dc 
    ON s.customer_id = dc.customer_id 
    AND dc.is_current = TRUE
ON CONFLICT (session_id) DO UPDATE SET
    session_end = EXCLUDED.session_end,
    duration_seconds = EXCLUDED.duration_seconds,
    page_views = EXCLUDED.page_views,
    events_count = EXCLUDED.events_count,
    engagement_score = EXCLUDED.engagement_score,
    conversion = EXCLUDED.conversion,
    _loaded_at = CURRENT_TIMESTAMP;

