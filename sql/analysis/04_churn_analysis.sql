-- ============================================================================
-- Churn Analysis Queries
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Churn Definition and Identification
-- ============================================================================

-- Define churned as no purchase in last 90 days
WITH customer_activity AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.full_name,
        dc.customer_segment,
        dc.email,
        MIN(ft.transaction_timestamp) as first_purchase,
        MAX(ft.transaction_timestamp) as last_purchase,
        COUNT(ft.transaction_sk) as total_orders,
        SUM(ft.total_amount_usd) as total_revenue,
        EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) as days_since_last_purchase
    FROM analytics.dim_customers dc
    LEFT JOIN analytics.fact_transactions ft 
        ON dc.customer_sk = ft.customer_sk 
        AND ft.status = 'Completed'
    WHERE dc.is_current = TRUE
    GROUP BY dc.customer_sk, dc.customer_id, dc.full_name, dc.customer_segment, dc.email
)
SELECT 
    customer_sk,
    customer_id,
    full_name,
    customer_segment,
    first_purchase,
    last_purchase,
    total_orders,
    ROUND(total_revenue, 2) as total_revenue,
    days_since_last_purchase,
    -- Churn status
    CASE 
        WHEN total_orders = 0 THEN 'Never Purchased'
        WHEN days_since_last_purchase <= 30 THEN 'Active'
        WHEN days_since_last_purchase <= 60 THEN 'At Risk'
        WHEN days_since_last_purchase <= 90 THEN 'High Risk'
        ELSE 'Churned'
    END as churn_status,
    -- Churn risk score (0-100)
    CASE 
        WHEN total_orders = 0 THEN 0
        ELSE LEAST(100, GREATEST(0, 
            days_since_last_purchase * 0.5 +  -- Recency factor
            (1 / GREATEST(total_orders, 1)) * 30 +  -- Frequency factor (inverted)
            CASE WHEN total_revenue < 100 THEN 20 ELSE 0 END  -- Value factor
        ))::INTEGER
    END as churn_risk_score
FROM customer_activity
ORDER BY churn_risk_score DESC;


-- ============================================================================
-- Monthly Churn Rate Calculation
-- ============================================================================

WITH monthly_status AS (
    SELECT 
        DATE_TRUNC('month', dt.full_date)::DATE as month,
        dc.customer_sk,
        MAX(ft.transaction_timestamp) as last_purchase_in_month,
        -- Was customer active this month?
        CASE WHEN COUNT(ft.transaction_sk) > 0 THEN 1 ELSE 0 END as was_active
    FROM analytics.dim_time dt
    CROSS JOIN analytics.dim_customers dc
    LEFT JOIN analytics.fact_transactions ft 
        ON dc.customer_sk = ft.customer_sk
        AND DATE_TRUNC('month', ft.transaction_timestamp) = DATE_TRUNC('month', dt.full_date)
        AND ft.status = 'Completed'
    WHERE dc.is_current = TRUE
    AND dt.full_date >= '2023-01-01'
    AND dt.full_date <= CURRENT_DATE
    GROUP BY DATE_TRUNC('month', dt.full_date), dc.customer_sk
),
churn_tracking AS (
    SELECT 
        month,
        customer_sk,
        was_active,
        LAG(was_active) OVER (PARTITION BY customer_sk ORDER BY month) as was_active_prev_month,
        -- Identify churns: was active last month, not active this month
        CASE 
            WHEN LAG(was_active) OVER (PARTITION BY customer_sk ORDER BY month) = 1 
             AND was_active = 0 
            THEN 1 
            ELSE 0 
        END as churned_this_month,
        -- Identify reactivations: was not active, now active
        CASE 
            WHEN LAG(was_active) OVER (PARTITION BY customer_sk ORDER BY month) = 0 
             AND was_active = 1 
            THEN 1 
            ELSE 0 
        END as reactivated_this_month
    FROM monthly_status
)
SELECT 
    month,
    SUM(was_active) as active_customers,
    SUM(was_active_prev_month) as prev_month_active,
    SUM(churned_this_month) as churned_customers,
    SUM(reactivated_this_month) as reactivated_customers,
    -- Churn rate
    ROUND(
        100.0 * SUM(churned_this_month) / NULLIF(SUM(was_active_prev_month), 0),
        2
    ) as churn_rate_pct,
    -- Reactivation rate
    ROUND(
        100.0 * SUM(reactivated_this_month) / NULLIF(SUM(CASE WHEN was_active_prev_month = 0 THEN 1 ELSE 0 END), 0),
        2
    ) as reactivation_rate_pct,
    -- Net customer change
    SUM(CASE WHEN was_active = 1 AND (was_active_prev_month = 0 OR was_active_prev_month IS NULL) THEN 1 ELSE 0 END) 
    - SUM(churned_this_month) as net_customer_change
FROM churn_tracking
WHERE month >= '2023-02-01'  -- Skip first month due to LAG
GROUP BY month
ORDER BY month;


-- ============================================================================
-- Churn by Customer Segment
-- ============================================================================

WITH segment_churn AS (
    SELECT 
        dc.customer_segment,
        dc.customer_sk,
        EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) as days_inactive,
        CASE 
            WHEN EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) > 90 THEN 1 
            ELSE 0 
        END as is_churned
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_segment, dc.customer_sk
)
SELECT 
    customer_segment,
    COUNT(*) as total_customers,
    SUM(is_churned) as churned_customers,
    COUNT(*) - SUM(is_churned) as active_customers,
    ROUND(100.0 * SUM(is_churned) / COUNT(*), 2) as churn_rate_pct,
    ROUND(AVG(days_inactive), 1) as avg_days_inactive,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_inactive), 1) as median_days_inactive
FROM segment_churn
GROUP BY customer_segment
ORDER BY churn_rate_pct DESC;


-- ============================================================================
-- Churn Prediction Features
-- ============================================================================

WITH customer_features AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.customer_segment,
        
        -- Transaction history
        COUNT(ft.transaction_sk) as total_orders,
        SUM(ft.total_amount_usd) as total_revenue,
        AVG(ft.total_amount_usd) as avg_order_value,
        STDDEV(ft.total_amount_usd) as stddev_order_value,
        
        -- Recency
        EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) as days_since_last_order,
        
        -- Frequency patterns
        COUNT(DISTINCT DATE_TRUNC('month', ft.transaction_timestamp)) as active_months,
        EXTRACT(DAY FROM MAX(ft.transaction_timestamp) - MIN(ft.transaction_timestamp)) 
            / NULLIF(COUNT(ft.transaction_sk) - 1, 0) as avg_days_between_orders,
        
        -- Recent behavior (last 90 days vs historical)
        SUM(CASE WHEN ft.transaction_timestamp >= CURRENT_TIMESTAMP - INTERVAL '90 days' 
            THEN ft.total_amount_usd ELSE 0 END) as revenue_last_90d,
        COUNT(CASE WHEN ft.transaction_timestamp >= CURRENT_TIMESTAMP - INTERVAL '90 days' 
            THEN 1 END) as orders_last_90d,
        
        -- Trend (last 90 days vs previous 90 days)
        SUM(CASE WHEN ft.transaction_timestamp BETWEEN CURRENT_TIMESTAMP - INTERVAL '180 days' 
                                                  AND CURRENT_TIMESTAMP - INTERVAL '90 days' 
            THEN ft.total_amount_usd ELSE 0 END) as revenue_prev_90d,
            
        -- Customer tenure
        EXTRACT(DAY FROM CURRENT_TIMESTAMP - MIN(ft.transaction_timestamp)) as customer_age_days
        
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
    total_orders,
    ROUND(total_revenue, 2) as total_revenue,
    ROUND(avg_order_value, 2) as avg_order_value,
    days_since_last_order,
    active_months,
    ROUND(avg_days_between_orders, 1) as avg_days_between_orders,
    ROUND(revenue_last_90d, 2) as revenue_last_90d,
    orders_last_90d,
    
    -- Derived features for ML model
    ROUND(revenue_last_90d / NULLIF(total_revenue, 0) * 100, 2) as pct_revenue_recent,
    ROUND((revenue_last_90d - revenue_prev_90d) / NULLIF(revenue_prev_90d, 0) * 100, 2) as revenue_trend_pct,
    ROUND(orders_last_90d::DECIMAL / NULLIF(total_orders, 0) * 100, 2) as pct_orders_recent,
    
    -- Churn label (for model training)
    CASE WHEN days_since_last_order > 90 THEN 1 ELSE 0 END as is_churned,
    
    -- Risk score (rule-based)
    CASE 
        WHEN days_since_last_order > 90 THEN 100
        WHEN days_since_last_order > 60 AND revenue_last_90d < revenue_prev_90d * 0.5 THEN 80
        WHEN days_since_last_order > 60 THEN 60
        WHEN days_since_last_order > 30 AND orders_last_90d = 0 THEN 40
        WHEN revenue_last_90d < revenue_prev_90d * 0.5 THEN 30
        ELSE 10
    END as churn_risk_score
    
FROM customer_features
ORDER BY churn_risk_score DESC;


-- ============================================================================
-- Churned Customer Value Analysis
-- ============================================================================

WITH churned_customers AS (
    SELECT 
        dc.customer_sk,
        dc.customer_id,
        dc.customer_segment,
        MIN(ft.transaction_timestamp) as first_purchase,
        MAX(ft.transaction_timestamp) as last_purchase,
        COUNT(ft.transaction_sk) as total_orders,
        SUM(ft.total_amount_usd) as total_revenue
    FROM analytics.dim_customers dc
    JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dc.customer_sk, dc.customer_id, dc.customer_segment
    HAVING EXTRACT(DAY FROM CURRENT_TIMESTAMP - MAX(ft.transaction_timestamp)) > 90
)
SELECT 
    -- Total churned customers
    COUNT(*) as churned_customer_count,
    -- Revenue lost (what they spent while active)
    ROUND(SUM(total_revenue), 2) as total_revenue_from_churned,
    -- Average value of churned customer
    ROUND(AVG(total_revenue), 2) as avg_churned_customer_value,
    -- Average lifetime (days active)
    ROUND(AVG(EXTRACT(DAY FROM last_purchase - first_purchase)), 0) as avg_lifetime_days,
    -- Potential annual loss (if similar customers churn)
    ROUND(AVG(total_revenue) * 12 / NULLIF(AVG(EXTRACT(DAY FROM last_purchase - first_purchase)) / 30, 0), 2) 
        as est_annual_value_per_customer,
    -- By segment
    SUM(CASE WHEN customer_segment = 'Enterprise' THEN 1 ELSE 0 END) as enterprise_churned,
    SUM(CASE WHEN customer_segment = 'SMB' THEN 1 ELSE 0 END) as smb_churned,
    SUM(CASE WHEN customer_segment = 'Consumer' THEN 1 ELSE 0 END) as consumer_churned
FROM churned_customers;

