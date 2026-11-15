-- ============================================================================
-- Window Functions for Analytics
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Running Totals and Moving Averages
-- ============================================================================

-- Daily revenue with running total and 7-day moving average
SELECT 
    dt.full_date,
    dt.day_name,
    daily.revenue,
    daily.transactions,
    -- Running total (cumulative)
    SUM(daily.revenue) OVER (
        ORDER BY dt.full_date
        ROWS UNBOUNDED PRECEDING
    ) as ytd_revenue,
    -- 7-day moving average
    AVG(daily.revenue) OVER (
        ORDER BY dt.full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) as moving_avg_7d,
    -- 30-day moving average
    AVG(daily.revenue) OVER (
        ORDER BY dt.full_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) as moving_avg_30d,
    -- Day-over-day change
    daily.revenue - LAG(daily.revenue) OVER (ORDER BY dt.full_date) as dod_change,
    -- Week-over-week change (same day last week)
    daily.revenue - LAG(daily.revenue, 7) OVER (ORDER BY dt.full_date) as wow_change,
    -- Percentage change
    ROUND(
        (daily.revenue - LAG(daily.revenue) OVER (ORDER BY dt.full_date)) 
        / NULLIF(LAG(daily.revenue) OVER (ORDER BY dt.full_date), 0) * 100, 
        2
    ) as dod_change_pct
FROM analytics.dim_time dt
LEFT JOIN (
    SELECT 
        date_key,
        SUM(total_amount_usd) as revenue,
        COUNT(*) as transactions
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY date_key
) daily ON dt.date_key = daily.date_key
WHERE dt.year = 2024
ORDER BY dt.full_date;


-- ============================================================================
-- Ranking and Percentiles
-- ============================================================================

-- Customer ranking by multiple metrics
WITH customer_metrics AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.full_name,
        dc.customer_segment,
        COUNT(ft.transaction_sk) as order_count,
        SUM(ft.total_amount_usd) as total_revenue,
        AVG(ft.total_amount_usd) as avg_order_value,
        MAX(ft.transaction_timestamp) as last_purchase
    FROM analytics.dim_customers dc
    LEFT JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    GROUP BY dc.customer_sk, dc.customer_id, dc.full_name, dc.customer_segment
)
SELECT 
    customer_id,
    full_name,
    customer_segment,
    total_revenue,
    order_count,
    avg_order_value,
    -- Rank within segment
    RANK() OVER (
        PARTITION BY customer_segment 
        ORDER BY total_revenue DESC
    ) as revenue_rank_in_segment,
    -- Dense rank (no gaps)
    DENSE_RANK() OVER (
        ORDER BY total_revenue DESC
    ) as overall_revenue_rank,
    -- Percentile
    PERCENT_RANK() OVER (
        ORDER BY total_revenue
    ) as revenue_percentile,
    -- Ntile (quartiles)
    NTILE(4) OVER (
        ORDER BY total_revenue DESC
    ) as revenue_quartile,
    -- Percentile value
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_revenue) OVER () as median_revenue
FROM customer_metrics
WHERE total_revenue > 0
ORDER BY total_revenue DESC;


-- ============================================================================
-- Lead and Lag for Trend Analysis
-- ============================================================================

-- Product sales trend with comparison to previous period
WITH monthly_product_sales AS (
    SELECT 
        dp.product_id,
        dp.product_name,
        dp.category,
        DATE_TRUNC('month', ft.transaction_timestamp)::DATE as month,
        SUM(ft.quantity) as units_sold,
        SUM(ft.total_amount_usd) as revenue
    FROM analytics.fact_transactions ft
    JOIN analytics.dim_products dp ON ft.product_sk = dp.product_sk
    WHERE ft.status = 'Completed'
    AND dp.is_current = TRUE
    GROUP BY dp.product_id, dp.product_name, dp.category, DATE_TRUNC('month', ft.transaction_timestamp)
)
SELECT 
    product_id,
    product_name,
    category,
    month,
    revenue,
    units_sold,
    -- Previous month values
    LAG(revenue) OVER (PARTITION BY product_id ORDER BY month) as prev_month_revenue,
    LAG(units_sold) OVER (PARTITION BY product_id ORDER BY month) as prev_month_units,
    -- Next month values (forecast comparison)
    LEAD(revenue) OVER (PARTITION BY product_id ORDER BY month) as next_month_revenue,
    -- Month-over-month growth
    ROUND(
        (revenue - LAG(revenue) OVER (PARTITION BY product_id ORDER BY month))
        / NULLIF(LAG(revenue) OVER (PARTITION BY product_id ORDER BY month), 0) * 100,
        2
    ) as mom_growth_pct,
    -- 3-month trend (first vs last of 3 months)
    FIRST_VALUE(revenue) OVER (
        PARTITION BY product_id 
        ORDER BY month 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) as revenue_3m_ago,
    -- Trend direction
    CASE 
        WHEN revenue > LAG(revenue) OVER (PARTITION BY product_id ORDER BY month) THEN 'Growing'
        WHEN revenue < LAG(revenue) OVER (PARTITION BY product_id ORDER BY month) THEN 'Declining'
        ELSE 'Stable'
    END as trend
FROM monthly_product_sales
ORDER BY category, product_id, month;


-- ============================================================================
-- Cohort Analysis with Window Functions
-- ============================================================================

-- Customer cohort retention analysis
WITH customer_cohorts AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        DATE_TRUNC('month', MIN(ft.transaction_timestamp))::DATE as cohort_month
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_sk, dc.customer_id
),
monthly_activity AS (
    SELECT 
        cc.customer_sk,
        cc.cohort_month,
        DATE_TRUNC('month', ft.transaction_timestamp)::DATE as activity_month,
        EXTRACT(YEAR FROM AGE(
            DATE_TRUNC('month', ft.transaction_timestamp),
            cc.cohort_month
        )) * 12 + EXTRACT(MONTH FROM AGE(
            DATE_TRUNC('month', ft.transaction_timestamp),
            cc.cohort_month
        )) as months_since_acquisition,
        SUM(ft.total_amount_usd) as revenue
    FROM customer_cohorts cc
    JOIN analytics.fact_transactions ft ON cc.customer_sk = ft.customer_sk
    WHERE ft.status = 'Completed'
    GROUP BY cc.customer_sk, cc.cohort_month, DATE_TRUNC('month', ft.transaction_timestamp)
),
cohort_sizes AS (
    SELECT 
        cohort_month,
        COUNT(DISTINCT customer_sk) as cohort_size
    FROM customer_cohorts
    GROUP BY cohort_month
)
SELECT 
    ma.cohort_month,
    cs.cohort_size,
    ma.months_since_acquisition,
    COUNT(DISTINCT ma.customer_sk) as active_customers,
    ROUND(
        COUNT(DISTINCT ma.customer_sk)::DECIMAL / cs.cohort_size * 100,
        2
    ) as retention_rate,
    SUM(ma.revenue) as cohort_revenue,
    -- Cumulative retention
    SUM(COUNT(DISTINCT ma.customer_sk)) OVER (
        PARTITION BY ma.cohort_month 
        ORDER BY ma.months_since_acquisition
    ) as cumulative_active,
    -- Average revenue per retained customer
    ROUND(SUM(ma.revenue) / COUNT(DISTINCT ma.customer_sk), 2) as arpu
FROM monthly_activity ma
JOIN cohort_sizes cs ON ma.cohort_month = cs.cohort_month
GROUP BY ma.cohort_month, cs.cohort_size, ma.months_since_acquisition
ORDER BY ma.cohort_month, ma.months_since_acquisition;


-- ============================================================================
-- Session Engagement Analysis
-- ============================================================================

-- Session engagement with rankings and comparisons
SELECT 
    session_id,
    customer_sk,
    session_start,
    device_type,
    traffic_source,
    page_views,
    duration_seconds,
    engagement_score,
    conversion,
    -- Rank sessions by engagement within traffic source
    RANK() OVER (
        PARTITION BY traffic_source 
        ORDER BY engagement_score DESC
    ) as engagement_rank_by_source,
    -- Compare to average for traffic source
    engagement_score - AVG(engagement_score) OVER (
        PARTITION BY traffic_source
    ) as vs_source_avg,
    -- Percentile within device type
    PERCENT_RANK() OVER (
        PARTITION BY device_type 
        ORDER BY engagement_score
    ) as engagement_percentile,
    -- Session sequence for customer
    ROW_NUMBER() OVER (
        PARTITION BY customer_sk 
        ORDER BY session_start
    ) as session_number,
    -- Gap from previous session
    session_start - LAG(session_start) OVER (
        PARTITION BY customer_sk 
        ORDER BY session_start
    ) as time_since_last_session
FROM analytics.fact_customer_sessions
WHERE session_start >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY engagement_score DESC;

