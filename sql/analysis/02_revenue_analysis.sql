-- ============================================================================
-- Revenue Analysis Queries
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Revenue Trends with Multiple Time Comparisons
-- ============================================================================

WITH daily_revenue AS (
    SELECT 
        dt.full_date,
        dt.year,
        dt.quarter,
        dt.month,
        dt.week_of_year,
        dt.day_of_week,
        dt.is_weekend,
        SUM(ft.total_amount_usd) as revenue,
        COUNT(ft.transaction_sk) as transactions,
        COUNT(DISTINCT ft.customer_sk) as customers
    FROM analytics.dim_time dt
    LEFT JOIN analytics.fact_transactions ft 
        ON dt.date_key = ft.date_key 
        AND ft.status = 'Completed'
    WHERE dt.full_date BETWEEN '2023-01-01' AND CURRENT_DATE
    GROUP BY dt.full_date, dt.year, dt.quarter, dt.month, dt.week_of_year, dt.day_of_week, dt.is_weekend
)
SELECT 
    full_date,
    revenue,
    transactions,
    customers,
    -- Daily comparisons
    LAG(revenue, 1) OVER (ORDER BY full_date) as prev_day_revenue,
    LAG(revenue, 7) OVER (ORDER BY full_date) as same_day_last_week,
    LAG(revenue, 365) OVER (ORDER BY full_date) as same_day_last_year,
    -- Growth rates
    ROUND(
        (revenue - LAG(revenue, 1) OVER (ORDER BY full_date))
        / NULLIF(LAG(revenue, 1) OVER (ORDER BY full_date), 0) * 100,
        2
    ) as dod_growth,
    ROUND(
        (revenue - LAG(revenue, 7) OVER (ORDER BY full_date))
        / NULLIF(LAG(revenue, 7) OVER (ORDER BY full_date), 0) * 100,
        2
    ) as wow_growth,
    ROUND(
        (revenue - LAG(revenue, 365) OVER (ORDER BY full_date))
        / NULLIF(LAG(revenue, 365) OVER (ORDER BY full_date), 0) * 100,
        2
    ) as yoy_growth,
    -- Rolling averages
    AVG(revenue) OVER (ORDER BY full_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as ma_7d,
    AVG(revenue) OVER (ORDER BY full_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as ma_30d,
    -- Weekend vs weekday analysis
    AVG(revenue) OVER (PARTITION BY is_weekend ORDER BY full_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as ma_7d_by_daytype
FROM daily_revenue
ORDER BY full_date DESC;


-- ============================================================================
-- Revenue by Segment Analysis
-- ============================================================================

SELECT 
    dc.customer_segment,
    dt.year,
    dt.month,
    COUNT(DISTINCT ft.customer_sk) as unique_customers,
    COUNT(ft.transaction_sk) as transactions,
    SUM(ft.total_amount_usd) as revenue,
    ROUND(AVG(ft.total_amount_usd), 2) as avg_order_value,
    ROUND(SUM(ft.total_amount_usd) / COUNT(DISTINCT ft.customer_sk), 2) as revenue_per_customer,
    -- Segment share of total revenue
    ROUND(
        SUM(ft.total_amount_usd) / SUM(SUM(ft.total_amount_usd)) OVER (PARTITION BY dt.year, dt.month) * 100,
        2
    ) as revenue_share_pct
FROM analytics.fact_transactions ft
JOIN analytics.dim_customers dc ON ft.customer_sk = dc.customer_sk
JOIN analytics.dim_time dt ON ft.date_key = dt.date_key
WHERE ft.status = 'Completed'
AND dc.is_current = TRUE
AND dt.year >= 2023
GROUP BY dc.customer_segment, dt.year, dt.month
ORDER BY dt.year, dt.month, revenue DESC;


-- ============================================================================
-- Channel Revenue Analysis
-- ============================================================================

WITH channel_revenue AS (
    SELECT 
        ch.channel_name,
        dt.year,
        dt.quarter,
        SUM(ft.total_amount_usd) as revenue,
        COUNT(ft.transaction_sk) as transactions,
        COUNT(DISTINCT ft.customer_sk) as customers
    FROM analytics.fact_transactions ft
    JOIN analytics.dim_channels ch ON ft.channel_sk = ch.channel_sk
    JOIN analytics.dim_time dt ON ft.date_key = dt.date_key
    WHERE ft.status = 'Completed'
    GROUP BY ch.channel_name, dt.year, dt.quarter
)
SELECT 
    channel_name,
    year,
    quarter,
    revenue,
    transactions,
    customers,
    -- Channel mix (share of quarterly revenue)
    ROUND(
        revenue / SUM(revenue) OVER (PARTITION BY year, quarter) * 100,
        2
    ) as channel_share_pct,
    -- Quarter-over-quarter growth
    ROUND(
        (revenue - LAG(revenue) OVER (PARTITION BY channel_name ORDER BY year, quarter))
        / NULLIF(LAG(revenue) OVER (PARTITION BY channel_name ORDER BY year, quarter), 0) * 100,
        2
    ) as qoq_growth,
    -- Average order value by channel
    ROUND(revenue / NULLIF(transactions, 0), 2) as aov,
    -- Revenue per customer
    ROUND(revenue / NULLIF(customers, 0), 2) as rev_per_customer
FROM channel_revenue
ORDER BY year, quarter, revenue DESC;


-- ============================================================================
-- Product Category Revenue with Trend
-- ============================================================================

WITH category_monthly AS (
    SELECT 
        dp.category,
        DATE_TRUNC('month', ft.transaction_timestamp)::DATE as month,
        SUM(ft.total_amount_usd) as revenue,
        SUM(ft.quantity) as units_sold,
        COUNT(DISTINCT ft.customer_sk) as unique_customers
    FROM analytics.fact_transactions ft
    JOIN analytics.dim_products dp ON ft.product_sk = dp.product_sk
    WHERE ft.status = 'Completed'
    AND dp.is_current = TRUE
    GROUP BY dp.category, DATE_TRUNC('month', ft.transaction_timestamp)
)
SELECT 
    category,
    month,
    revenue,
    units_sold,
    unique_customers,
    -- Category share
    ROUND(
        revenue / SUM(revenue) OVER (PARTITION BY month) * 100,
        2
    ) as category_share_pct,
    -- Growth
    LAG(revenue) OVER (PARTITION BY category ORDER BY month) as prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (PARTITION BY category ORDER BY month))
        / NULLIF(LAG(revenue) OVER (PARTITION BY category ORDER BY month), 0) * 100,
        2
    ) as mom_growth,
    -- 3-month trend
    ROUND(
        (revenue - LAG(revenue, 3) OVER (PARTITION BY category ORDER BY month))
        / NULLIF(LAG(revenue, 3) OVER (PARTITION BY category ORDER BY month), 0) * 100,
        2
    ) as growth_3m,
    -- Rank by revenue each month
    RANK() OVER (PARTITION BY month ORDER BY revenue DESC) as category_rank
FROM category_monthly
ORDER BY month DESC, revenue DESC;


-- ============================================================================
-- Revenue Forecasting Base Query
-- ============================================================================

WITH monthly_metrics AS (
    SELECT 
        DATE_TRUNC('month', transaction_timestamp)::DATE as month,
        SUM(total_amount_usd) as revenue,
        COUNT(*) as transactions,
        COUNT(DISTINCT customer_sk) as customers
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY DATE_TRUNC('month', transaction_timestamp)
),
with_trends AS (
    SELECT 
        month,
        revenue,
        transactions,
        customers,
        -- Calculate moving averages and trends
        AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as ma_3m,
        AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) as ma_6m,
        -- Calculate growth rate
        (revenue - LAG(revenue, 12) OVER (ORDER BY month)) 
        / NULLIF(LAG(revenue, 12) OVER (ORDER BY month), 0) as yoy_growth_rate,
        -- Seasonal index (month vs yearly average)
        revenue / AVG(revenue) OVER (PARTITION BY EXTRACT(YEAR FROM month)) as seasonal_index,
        -- Linear trend component
        ROW_NUMBER() OVER (ORDER BY month) as trend_period
    FROM monthly_metrics
)
SELECT 
    month,
    revenue,
    ma_3m,
    ma_6m,
    ROUND(yoy_growth_rate * 100, 2) as yoy_growth_pct,
    ROUND(seasonal_index, 3) as seasonal_index,
    -- Simple forecast: last year same month * (1 + growth rate)
    ROUND(
        LAG(revenue, 12) OVER (ORDER BY month) * (1 + COALESCE(yoy_growth_rate, 0)),
        2
    ) as simple_forecast,
    -- Trend-adjusted forecast
    ROUND(
        ma_6m * seasonal_index,
        2
    ) as seasonal_adjusted_forecast
FROM with_trends
ORDER BY month DESC;


-- ============================================================================
-- Geographic Revenue Analysis
-- ============================================================================

SELECT 
    geo.country_name,
    geo.region,
    geo.continent,
    dt.year,
    SUM(ft.total_amount_usd) as revenue,
    COUNT(ft.transaction_sk) as transactions,
    COUNT(DISTINCT ft.customer_sk) as customers,
    ROUND(AVG(ft.total_amount_usd), 2) as avg_order_value,
    -- Regional share
    ROUND(
        SUM(ft.total_amount_usd) / SUM(SUM(ft.total_amount_usd)) OVER (PARTITION BY geo.continent, dt.year) * 100,
        2
    ) as regional_share,
    -- Year-over-year growth
    ROUND(
        (SUM(ft.total_amount_usd) - LAG(SUM(ft.total_amount_usd)) OVER (PARTITION BY geo.country_name ORDER BY dt.year))
        / NULLIF(LAG(SUM(ft.total_amount_usd)) OVER (PARTITION BY geo.country_name ORDER BY dt.year), 0) * 100,
        2
    ) as yoy_growth
FROM analytics.fact_transactions ft
JOIN analytics.dim_geography geo ON ft.geography_sk = geo.geography_sk
JOIN analytics.dim_time dt ON ft.date_key = dt.date_key
WHERE ft.status = 'Completed'
GROUP BY geo.country_name, geo.region, geo.continent, dt.year
ORDER BY dt.year DESC, revenue DESC;

