-- ============================================================================
-- Cohort Analysis Queries
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Monthly Cohort Retention Matrix
-- ============================================================================

WITH first_purchase AS (
    SELECT 
        customer_sk,
        DATE_TRUNC('month', MIN(transaction_timestamp))::DATE as cohort_month
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY customer_sk
),
monthly_purchases AS (
    SELECT 
        ft.customer_sk,
        fp.cohort_month,
        DATE_TRUNC('month', ft.transaction_timestamp)::DATE as purchase_month
    FROM analytics.fact_transactions ft
    JOIN first_purchase fp ON ft.customer_sk = fp.customer_sk
    WHERE ft.status = 'Completed'
),
cohort_data AS (
    SELECT 
        cohort_month,
        purchase_month,
        EXTRACT(YEAR FROM AGE(purchase_month, cohort_month)) * 12 +
        EXTRACT(MONTH FROM AGE(purchase_month, cohort_month)) as month_number,
        COUNT(DISTINCT customer_sk) as customers
    FROM monthly_purchases
    GROUP BY cohort_month, purchase_month
),
cohort_sizes AS (
    SELECT cohort_month, customers as cohort_size
    FROM cohort_data
    WHERE month_number = 0
)
SELECT 
    cd.cohort_month,
    cs.cohort_size,
    cd.month_number,
    cd.customers as retained_customers,
    ROUND(cd.customers::DECIMAL / cs.cohort_size * 100, 2) as retention_rate
FROM cohort_data cd
JOIN cohort_sizes cs ON cd.cohort_month = cs.cohort_month
WHERE cd.cohort_month >= '2023-01-01'
ORDER BY cd.cohort_month, cd.month_number;


-- ============================================================================
-- Cohort Revenue Analysis
-- ============================================================================

WITH customer_cohorts AS (
    SELECT 
        customer_sk,
        DATE_TRUNC('month', MIN(transaction_timestamp))::DATE as cohort_month
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY customer_sk
),
cohort_revenue AS (
    SELECT 
        cc.cohort_month,
        DATE_TRUNC('month', ft.transaction_timestamp)::DATE as revenue_month,
        EXTRACT(YEAR FROM AGE(
            DATE_TRUNC('month', ft.transaction_timestamp),
            cc.cohort_month
        )) * 12 + EXTRACT(MONTH FROM AGE(
            DATE_TRUNC('month', ft.transaction_timestamp),
            cc.cohort_month
        )) as month_number,
        COUNT(DISTINCT ft.customer_sk) as active_customers,
        COUNT(ft.transaction_sk) as transactions,
        SUM(ft.total_amount_usd) as revenue
    FROM analytics.fact_transactions ft
    JOIN customer_cohorts cc ON ft.customer_sk = cc.customer_sk
    WHERE ft.status = 'Completed'
    GROUP BY cc.cohort_month, DATE_TRUNC('month', ft.transaction_timestamp)
)
SELECT 
    cohort_month,
    month_number,
    active_customers,
    transactions,
    revenue,
    -- Cumulative revenue
    SUM(revenue) OVER (
        PARTITION BY cohort_month 
        ORDER BY month_number
    ) as cumulative_revenue,
    -- Average revenue per customer
    ROUND(revenue / NULLIF(active_customers, 0), 2) as arpu,
    -- Average transactions per customer
    ROUND(transactions::DECIMAL / NULLIF(active_customers, 0), 2) as transactions_per_customer
FROM cohort_revenue
WHERE cohort_month >= '2023-01-01'
ORDER BY cohort_month, month_number;


-- ============================================================================
-- Weekly Cohort Analysis (for faster iterations)
-- ============================================================================

WITH weekly_cohorts AS (
    SELECT 
        customer_sk,
        DATE_TRUNC('week', MIN(transaction_timestamp))::DATE as cohort_week
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    AND transaction_timestamp >= CURRENT_DATE - INTERVAL '12 weeks'
    GROUP BY customer_sk
),
weekly_activity AS (
    SELECT 
        wc.cohort_week,
        DATE_TRUNC('week', ft.transaction_timestamp)::DATE as activity_week,
        FLOOR(EXTRACT(DAY FROM 
            DATE_TRUNC('week', ft.transaction_timestamp) - wc.cohort_week
        ) / 7) as week_number,
        COUNT(DISTINCT ft.customer_sk) as customers,
        SUM(ft.total_amount_usd) as revenue
    FROM analytics.fact_transactions ft
    JOIN weekly_cohorts wc ON ft.customer_sk = wc.customer_sk
    WHERE ft.status = 'Completed'
    GROUP BY wc.cohort_week, DATE_TRUNC('week', ft.transaction_timestamp)
),
cohort_sizes AS (
    SELECT cohort_week, COUNT(DISTINCT customer_sk) as size
    FROM weekly_cohorts
    GROUP BY cohort_week
)
SELECT 
    wa.cohort_week,
    cs.size as cohort_size,
    wa.week_number,
    wa.customers as active_customers,
    ROUND(wa.customers::DECIMAL / cs.size * 100, 1) as retention_pct,
    wa.revenue,
    ROUND(wa.revenue / wa.customers, 2) as revenue_per_customer
FROM weekly_activity wa
JOIN cohort_sizes cs ON wa.cohort_week = cs.cohort_week
ORDER BY wa.cohort_week, wa.week_number;


-- ============================================================================
-- Cohort LTV Projection
-- ============================================================================

WITH cohort_cumulative AS (
    SELECT 
        cohort_month,
        month_number,
        cohort_size,
        revenue,
        SUM(revenue) OVER (
            PARTITION BY cohort_month 
            ORDER BY month_number
        ) as cumulative_revenue
    FROM analytics.mart_customer_cohorts
    WHERE cohort_month >= '2023-01-01'
),
ltv_by_month AS (
    SELECT 
        month_number,
        AVG(cumulative_revenue / cohort_size) as avg_ltv_at_month,
        COUNT(DISTINCT cohort_month) as num_cohorts
    FROM cohort_cumulative
    GROUP BY month_number
)
SELECT 
    month_number,
    avg_ltv_at_month,
    num_cohorts,
    -- Projected 12-month LTV based on trend
    CASE 
        WHEN month_number <= 12 THEN avg_ltv_at_month
        ELSE NULL
    END as actual_ltv,
    -- Running average growth rate
    ROUND(
        (avg_ltv_at_month - LAG(avg_ltv_at_month) OVER (ORDER BY month_number))
        / NULLIF(LAG(avg_ltv_at_month) OVER (ORDER BY month_number), 0) * 100,
        2
    ) as month_growth_pct
FROM ltv_by_month
ORDER BY month_number;


-- ============================================================================
-- Cohort Behavioral Segmentation
-- ============================================================================

WITH customer_behavior AS (
    SELECT 
        cc.customer_sk,
        cc.cohort_month,
        COUNT(ft.transaction_sk) as total_orders,
        SUM(ft.total_amount_usd) as total_revenue,
        MAX(ft.transaction_timestamp) as last_purchase,
        COUNT(DISTINCT DATE_TRUNC('month', ft.transaction_timestamp)) as active_months
    FROM (
        SELECT 
            customer_sk,
            DATE_TRUNC('month', MIN(transaction_timestamp))::DATE as cohort_month
        FROM analytics.fact_transactions
        WHERE status = 'Completed'
        GROUP BY customer_sk
    ) cc
    JOIN analytics.fact_transactions ft ON cc.customer_sk = ft.customer_sk
    WHERE ft.status = 'Completed'
    GROUP BY cc.customer_sk, cc.cohort_month
),
segmented AS (
    SELECT 
        *,
        CASE 
            WHEN active_months >= 6 AND total_orders >= 10 THEN 'Champion'
            WHEN active_months >= 3 AND total_orders >= 5 THEN 'Loyal'
            WHEN total_orders >= 3 THEN 'Potential Loyalist'
            WHEN total_orders = 2 THEN 'New Customer'
            WHEN total_orders = 1 THEN 'First-Timer'
            ELSE 'Other'
        END as behavior_segment,
        CASE 
            WHEN last_purchase >= CURRENT_DATE - INTERVAL '30 days' THEN 'Active'
            WHEN last_purchase >= CURRENT_DATE - INTERVAL '90 days' THEN 'At Risk'
            ELSE 'Churned'
        END as status_segment
    FROM customer_behavior
)
SELECT 
    cohort_month,
    behavior_segment,
    status_segment,
    COUNT(*) as customer_count,
    SUM(total_revenue) as total_revenue,
    ROUND(AVG(total_orders), 1) as avg_orders,
    ROUND(AVG(total_revenue), 2) as avg_revenue
FROM segmented
GROUP BY cohort_month, behavior_segment, status_segment
ORDER BY cohort_month, behavior_segment, status_segment;

