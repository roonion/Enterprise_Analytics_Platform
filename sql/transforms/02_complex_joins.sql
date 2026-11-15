-- ============================================================================
-- Complex JOIN Examples
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- 4+ Table JOIN: Complete Transaction Analysis
-- ============================================================================

-- Comprehensive transaction detail with all dimension data
SELECT 
    -- Transaction facts
    ft.transaction_id,
    ft.transaction_timestamp,
    ft.quantity,
    ft.unit_price_usd,
    ft.total_amount_usd,
    ft.status,
    
    -- Customer dimension
    dc.customer_id,
    dc.full_name as customer_name,
    dc.email as customer_email,
    dc.customer_segment,
    dc.country as customer_country,
    
    -- Product dimension
    dp.product_id,
    dp.product_name,
    dp.category as product_category,
    dp.subcategory as product_subcategory,
    dp.brand as product_brand,
    dp.unit_price as list_price,
    
    -- Time dimension
    dt.full_date as transaction_date,
    dt.year,
    dt.quarter,
    dt.month,
    dt.month_name,
    dt.day_name,
    dt.is_weekend,
    
    -- Channel dimension
    ch.channel_name,
    ch.channel_category,
    ch.is_digital as is_digital_channel,
    
    -- Payment dimension
    pm.payment_method_name,
    pm.payment_category,
    
    -- Geography dimension
    geo.country_name,
    geo.region,
    geo.continent,
    
    -- Calculated fields
    CASE 
        WHEN dp.unit_price > 0 
        THEN (dp.unit_price - COALESCE(dp.cost_price, 0)) / dp.unit_price 
        ELSE 0 
    END as margin_percentage,
    ft.total_amount_usd - (dp.cost_price * ft.quantity) as estimated_profit

FROM analytics.fact_transactions ft
-- Customer (point-in-time join for SCD Type 2)
INNER JOIN analytics.dim_customers dc 
    ON ft.customer_sk = dc.customer_sk
-- Product
INNER JOIN analytics.dim_products dp 
    ON ft.product_sk = dp.product_sk
-- Time
INNER JOIN analytics.dim_time dt 
    ON ft.date_key = dt.date_key
-- Channel
LEFT JOIN analytics.dim_channels ch 
    ON ft.channel_sk = ch.channel_sk
-- Payment Method
LEFT JOIN analytics.dim_payment_methods pm 
    ON ft.payment_method_sk = pm.payment_method_sk
-- Geography
LEFT JOIN analytics.dim_geography geo 
    ON ft.geography_sk = geo.geography_sk

WHERE dt.year = 2024
    AND ft.status = 'Completed'
ORDER BY ft.transaction_timestamp DESC;


-- ============================================================================
-- Self JOIN: Customer Purchase Intervals
-- ============================================================================

-- Calculate days between consecutive purchases for each customer
WITH customer_transactions AS (
    SELECT 
        dc.customer_id,
        dc.full_name,
        ft.transaction_id,
        ft.transaction_timestamp,
        ft.total_amount_usd,
        ROW_NUMBER() OVER (
            PARTITION BY dc.customer_id 
            ORDER BY ft.transaction_timestamp
        ) as purchase_number
    FROM analytics.fact_transactions ft
    JOIN analytics.dim_customers dc ON ft.customer_sk = dc.customer_sk
    WHERE dc.is_current = TRUE
    AND ft.status = 'Completed'
)
SELECT 
    t1.customer_id,
    t1.full_name,
    t1.transaction_id as current_transaction,
    t1.transaction_timestamp as current_purchase_date,
    t2.transaction_id as previous_transaction,
    t2.transaction_timestamp as previous_purchase_date,
    EXTRACT(DAY FROM t1.transaction_timestamp - t2.transaction_timestamp) as days_between_purchases,
    t1.total_amount_usd - t2.total_amount_usd as amount_change
FROM customer_transactions t1
-- Self join to get previous transaction
LEFT JOIN customer_transactions t2 
    ON t1.customer_id = t2.customer_id 
    AND t1.purchase_number = t2.purchase_number + 1
WHERE t2.transaction_id IS NOT NULL
ORDER BY t1.customer_id, t1.purchase_number;


-- ============================================================================
-- CROSS JOIN: Generate All Date-Product Combinations for Gap Analysis
-- ============================================================================

-- Find days where products had no sales
WITH date_product_grid AS (
    SELECT 
        dt.date_key,
        dt.full_date,
        dp.product_sk,
        dp.product_id,
        dp.product_name,
        dp.category
    FROM analytics.dim_time dt
    CROSS JOIN analytics.dim_products dp
    WHERE dt.full_date BETWEEN '2024-01-01' AND '2024-12-31'
    AND dp.is_current = TRUE
    AND dp.is_active = TRUE
),
actual_sales AS (
    SELECT 
        date_key,
        product_sk,
        SUM(quantity) as units_sold,
        SUM(total_amount_usd) as revenue
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY date_key, product_sk
)
SELECT 
    g.full_date,
    g.product_name,
    g.category,
    COALESCE(s.units_sold, 0) as units_sold,
    COALESCE(s.revenue, 0) as revenue,
    CASE WHEN s.product_sk IS NULL THEN TRUE ELSE FALSE END as no_sales_day
FROM date_product_grid g
LEFT JOIN actual_sales s 
    ON g.date_key = s.date_key 
    AND g.product_sk = s.product_sk
WHERE s.product_sk IS NULL  -- Only show zero-sale days
ORDER BY g.full_date, g.category, g.product_name;


-- ============================================================================
-- LATERAL JOIN: Top N Products per Category
-- ============================================================================

-- Get top 3 products by revenue for each category
SELECT 
    c.category,
    tp.product_name,
    tp.total_revenue,
    tp.rank_in_category
FROM (
    SELECT DISTINCT category 
    FROM analytics.dim_products 
    WHERE is_current = TRUE
) c
CROSS JOIN LATERAL (
    SELECT 
        dp.product_name,
        SUM(ft.total_amount_usd) as total_revenue,
        ROW_NUMBER() OVER (ORDER BY SUM(ft.total_amount_usd) DESC) as rank_in_category
    FROM analytics.dim_products dp
    JOIN analytics.fact_transactions ft ON dp.product_sk = ft.product_sk
    WHERE dp.category = c.category
    AND dp.is_current = TRUE
    AND ft.status = 'Completed'
    GROUP BY dp.product_sk, dp.product_name
    ORDER BY total_revenue DESC
    LIMIT 3
) tp
ORDER BY c.category, tp.rank_in_category;


-- ============================================================================
-- Anti-Join: Customers Without Recent Purchases
-- ============================================================================

-- Find customers who haven't purchased in the last 90 days
SELECT 
    dc.customer_id,
    dc.full_name,
    dc.email,
    dc.customer_segment,
    last_purchase.last_purchase_date,
    CURRENT_DATE - last_purchase.last_purchase_date::DATE as days_since_purchase
FROM analytics.dim_customers dc
LEFT JOIN (
    SELECT 
        customer_sk,
        MAX(transaction_timestamp) as last_purchase_date
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY customer_sk
) last_purchase ON dc.customer_sk = last_purchase.customer_sk
WHERE dc.is_current = TRUE
AND (
    last_purchase.last_purchase_date IS NULL
    OR last_purchase.last_purchase_date < CURRENT_DATE - INTERVAL '90 days'
)
ORDER BY days_since_purchase DESC NULLS FIRST;

