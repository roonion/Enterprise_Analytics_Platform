-- ============================================================================
-- Customer Lifetime Value (CLV) Analysis
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- RFM Segmentation
-- ============================================================================

WITH customer_rfm AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.full_name,
        dc.customer_segment,
        -- Recency: Days since last purchase
        EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) as recency_days,
        -- Frequency: Total number of orders
        COUNT(ft.transaction_sk) as frequency,
        -- Monetary: Total revenue
        SUM(ft.total_amount_usd) as monetary
    FROM analytics.dim_customers dc
    LEFT JOIN analytics.fact_transactions ft 
        ON dc.customer_sk = ft.customer_sk 
        AND ft.status = 'Completed'
    WHERE dc.is_current = TRUE
    GROUP BY dc.customer_sk, dc.customer_id, dc.full_name, dc.customer_segment
),
rfm_scores AS (
    SELECT 
        *,
        -- Recency score (1-5, higher is better/more recent)
        NTILE(5) OVER (ORDER BY recency_days DESC) as r_score,
        -- Frequency score (1-5, higher is more frequent)
        NTILE(5) OVER (ORDER BY frequency) as f_score,
        -- Monetary score (1-5, higher is more valuable)
        NTILE(5) OVER (ORDER BY monetary) as m_score
    FROM customer_rfm
    WHERE frequency > 0
)
SELECT 
    customer_sk,
    customer_id,
    full_name,
    customer_segment,
    recency_days,
    frequency,
    ROUND(monetary, 2) as monetary,
    r_score,
    f_score,
    m_score,
    r_score + f_score + m_score as rfm_total,
    CONCAT(r_score, f_score, m_score) as rfm_cell,
    -- Segment assignment
    CASE 
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'
        WHEN r_score >= 3 AND f_score >= 1 AND m_score >= 3 THEN 'Potential Loyalists'
        WHEN r_score >= 4 AND f_score <= 2 AND m_score <= 2 THEN 'New Customers'
        WHEN r_score >= 3 AND f_score >= 3 AND m_score <= 2 THEN 'Promising'
        WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'At Risk'
        WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'Cant Lose Them'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score >= 3 THEN 'Hibernating'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score <= 2 THEN 'Lost'
        ELSE 'Others'
    END as rfm_segment
FROM rfm_scores
ORDER BY rfm_total DESC, monetary DESC;


-- ============================================================================
-- Historical CLV Calculation
-- ============================================================================

WITH customer_history AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.customer_segment,
        -- First and last purchase
        MIN(ft.transaction_timestamp) as first_purchase,
        MAX(ft.transaction_timestamp) as last_purchase,
        -- Customer tenure in days
        EXTRACT(DAY FROM MAX(ft.transaction_timestamp) - MIN(ft.transaction_timestamp)) as tenure_days,
        -- Order metrics
        COUNT(ft.transaction_sk) as total_orders,
        SUM(ft.total_amount_usd) as total_revenue,
        AVG(ft.total_amount_usd) as avg_order_value,
        -- Time between orders
        CASE 
            WHEN COUNT(ft.transaction_sk) > 1 
            THEN EXTRACT(DAY FROM MAX(ft.transaction_timestamp) - MIN(ft.transaction_timestamp)) / (COUNT(ft.transaction_sk) - 1)
            ELSE NULL
        END as avg_days_between_orders
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_sk, dc.customer_id, dc.customer_segment
)
SELECT 
    customer_sk,
    customer_id,
    customer_segment,
    first_purchase,
    last_purchase,
    tenure_days,
    total_orders,
    ROUND(total_revenue, 2) as total_revenue,
    ROUND(avg_order_value, 2) as avg_order_value,
    ROUND(avg_days_between_orders, 1) as avg_days_between_orders,
    -- Historical CLV = Total Revenue (what they've spent)
    ROUND(total_revenue, 2) as historical_clv,
    -- Annualized CLV (extrapolated to yearly)
    CASE 
        WHEN tenure_days > 0 
        THEN ROUND(total_revenue / tenure_days * 365, 2)
        ELSE ROUND(total_revenue, 2)
    END as annualized_clv,
    -- Purchase frequency (orders per year)
    CASE 
        WHEN tenure_days > 0 
        THEN ROUND(total_orders::DECIMAL / tenure_days * 365, 2)
        ELSE total_orders::DECIMAL
    END as annual_purchase_frequency
FROM customer_history
ORDER BY total_revenue DESC;


-- ============================================================================
-- Predictive CLV Model Inputs
-- ============================================================================

WITH customer_metrics AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.customer_segment,
        COUNT(ft.transaction_sk) as total_orders,
        SUM(ft.total_amount_usd) as total_revenue,
        AVG(ft.total_amount_usd) as avg_order_value,
        STDDEV(ft.total_amount_usd) as stddev_order_value,
        MIN(ft.transaction_timestamp) as first_purchase,
        MAX(ft.transaction_timestamp) as last_purchase,
        EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) as recency_days
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_sk, dc.customer_id, dc.customer_segment
),
aggregates AS (
    SELECT 
        AVG(total_revenue) as avg_clv,
        STDDEV(total_revenue) as stddev_clv,
        AVG(total_orders) as avg_orders,
        AVG(avg_order_value) as overall_aov
    FROM customer_metrics
)
SELECT 
    cm.customer_sk,
    cm.customer_id,
    cm.customer_segment,
    cm.total_orders,
    ROUND(cm.total_revenue, 2) as total_revenue,
    ROUND(cm.avg_order_value, 2) as avg_order_value,
    cm.recency_days,
    -- Customer tenure in months
    ROUND(EXTRACT(DAY FROM cm.last_purchase - cm.first_purchase) / 30.0, 1) as tenure_months,
    -- Orders per month
    CASE 
        WHEN cm.last_purchase > cm.first_purchase
        THEN ROUND(cm.total_orders / (EXTRACT(DAY FROM cm.last_purchase - cm.first_purchase) / 30.0), 2)
        ELSE cm.total_orders::DECIMAL
    END as orders_per_month,
    -- Coefficient of variation (consistency)
    CASE 
        WHEN cm.avg_order_value > 0 
        THEN ROUND(cm.stddev_order_value / cm.avg_order_value, 2)
        ELSE 0
    END as cv_order_value,
    -- CLV Index (compared to average)
    ROUND(cm.total_revenue / NULLIF(a.avg_clv, 0), 2) as clv_index,
    -- Predicted 12-month CLV (simple model)
    ROUND(
        cm.avg_order_value * 
        (cm.total_orders / GREATEST(EXTRACT(DAY FROM cm.last_purchase - cm.first_purchase) / 365.0, 0.1)) *
        CASE 
            WHEN cm.recency_days < 30 THEN 1.0
            WHEN cm.recency_days < 90 THEN 0.8
            WHEN cm.recency_days < 180 THEN 0.5
            ELSE 0.2
        END,
        2
    ) as predicted_12m_clv
FROM customer_metrics cm
CROSS JOIN aggregates a
ORDER BY cm.total_revenue DESC;


-- ============================================================================
-- CLV by Acquisition Cohort
-- ============================================================================

WITH cohort_clv AS (
    SELECT 
        DATE_TRUNC('month', MIN(ft.transaction_timestamp))::DATE as cohort_month,
        dc.customer_sk,
        SUM(ft.total_amount_usd) as lifetime_value
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_sk
)
SELECT 
    cohort_month,
    COUNT(*) as cohort_size,
    ROUND(AVG(lifetime_value), 2) as avg_clv,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lifetime_value), 2) as median_clv,
    ROUND(MIN(lifetime_value), 2) as min_clv,
    ROUND(MAX(lifetime_value), 2) as max_clv,
    ROUND(SUM(lifetime_value), 2) as total_clv,
    -- CLV distribution
    SUM(CASE WHEN lifetime_value < 100 THEN 1 ELSE 0 END) as clv_under_100,
    SUM(CASE WHEN lifetime_value BETWEEN 100 AND 500 THEN 1 ELSE 0 END) as clv_100_500,
    SUM(CASE WHEN lifetime_value BETWEEN 500 AND 1000 THEN 1 ELSE 0 END) as clv_500_1000,
    SUM(CASE WHEN lifetime_value > 1000 THEN 1 ELSE 0 END) as clv_over_1000
FROM cohort_clv
GROUP BY cohort_month
ORDER BY cohort_month;


-- ============================================================================
-- Customer Value Tiers
-- ============================================================================

WITH customer_value AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.customer_segment,
        SUM(ft.total_amount_usd) as lifetime_value,
        COUNT(ft.transaction_sk) as order_count,
        MAX(ft.transaction_timestamp) as last_order
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_sk, dc.customer_id, dc.customer_segment
),
value_tiers AS (
    SELECT 
        *,
        CASE 
            WHEN lifetime_value >= PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY lifetime_value) OVER () THEN 'Platinum'
            WHEN lifetime_value >= PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY lifetime_value) OVER () THEN 'Gold'
            WHEN lifetime_value >= PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY lifetime_value) OVER () THEN 'Silver'
            ELSE 'Bronze'
        END as value_tier
    FROM customer_value
)
SELECT 
    value_tier,
    COUNT(*) as customer_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct_of_customers,
    ROUND(SUM(lifetime_value), 2) as total_revenue,
    ROUND(100.0 * SUM(lifetime_value) / SUM(SUM(lifetime_value)) OVER (), 2) as pct_of_revenue,
    ROUND(AVG(lifetime_value), 2) as avg_clv,
    ROUND(AVG(order_count), 1) as avg_orders,
    ROUND(AVG(lifetime_value / NULLIF(order_count, 0)), 2) as avg_order_value
FROM value_tiers
GROUP BY value_tier
ORDER BY 
    CASE value_tier 
        WHEN 'Platinum' THEN 1 
        WHEN 'Gold' THEN 2 
        WHEN 'Silver' THEN 3 
        ELSE 4 
    END;

