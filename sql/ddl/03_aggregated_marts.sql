-- ============================================================================
-- Aggregated Data Marts DDL
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Daily Revenue Summary
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_daily_revenue CASCADE;

CREATE TABLE analytics.mart_daily_revenue (
    date_key INTEGER PRIMARY KEY REFERENCES analytics.dim_time(date_key),
    full_date DATE NOT NULL,
    
    -- Revenue metrics
    total_revenue DECIMAL(15, 2) NOT NULL DEFAULT 0,
    total_transactions INTEGER NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    
    -- Averages
    avg_transaction_value DECIMAL(12, 2),
    avg_basket_size DECIMAL(8, 2),
    
    -- By status
    completed_revenue DECIMAL(15, 2) DEFAULT 0,
    refunded_revenue DECIMAL(15, 2) DEFAULT 0,
    pending_revenue DECIMAL(15, 2) DEFAULT 0,
    
    -- Customer metrics
    unique_customers INTEGER DEFAULT 0,
    new_customers INTEGER DEFAULT 0,
    returning_customers INTEGER DEFAULT 0,
    
    -- Channel breakdown
    web_revenue DECIMAL(15, 2) DEFAULT 0,
    mobile_revenue DECIMAL(15, 2) DEFAULT 0,
    store_revenue DECIMAL(15, 2) DEFAULT 0,
    other_channel_revenue DECIMAL(15, 2) DEFAULT 0,
    
    -- Growth metrics (calculated)
    revenue_dod_change DECIMAL(10, 4),
    revenue_wow_change DECIMAL(10, 4),
    revenue_mom_change DECIMAL(10, 4),
    revenue_yoy_change DECIMAL(10, 4),
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mart_daily_revenue_date ON analytics.mart_daily_revenue(full_date);

-- ============================================================================
-- Customer Lifetime Value
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_customer_lifetime_value CASCADE;

CREATE TABLE analytics.mart_customer_lifetime_value (
    customer_sk INTEGER PRIMARY KEY REFERENCES analytics.dim_customers(customer_sk),
    customer_id VARCHAR(50) NOT NULL,
    
    -- Lifetime metrics
    total_lifetime_revenue DECIMAL(15, 2) DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    total_quantity INTEGER DEFAULT 0,
    avg_order_value DECIMAL(12, 2),
    
    -- Time-based metrics
    first_order_date DATE,
    last_order_date DATE,
    customer_age_days INTEGER,
    days_since_last_order INTEGER,
    avg_days_between_orders DECIMAL(10, 2),
    
    -- Frequency
    orders_last_30_days INTEGER DEFAULT 0,
    orders_last_90_days INTEGER DEFAULT 0,
    orders_last_365_days INTEGER DEFAULT 0,
    
    -- Revenue by period
    revenue_last_30_days DECIMAL(12, 2) DEFAULT 0,
    revenue_last_90_days DECIMAL(12, 2) DEFAULT 0,
    revenue_last_365_days DECIMAL(12, 2) DEFAULT 0,
    
    -- CLV prediction inputs
    recency_score INTEGER,    -- 1-5
    frequency_score INTEGER,  -- 1-5
    monetary_score INTEGER,   -- 1-5
    rfm_segment VARCHAR(50),
    
    -- Predicted CLV
    predicted_clv_12m DECIMAL(12, 2),
    clv_tier VARCHAR(20),
    
    -- Churn indicators
    is_churned BOOLEAN DEFAULT FALSE,
    churn_probability DECIMAL(5, 4),
    
    -- Engagement
    total_sessions INTEGER DEFAULT 0,
    avg_session_engagement_score DECIMAL(5, 2),
    conversion_rate DECIMAL(5, 4),
    
    -- Support
    total_support_tickets INTEGER DEFAULT 0,
    avg_satisfaction_score DECIMAL(3, 2),
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mart_clv_customer_id ON analytics.mart_customer_lifetime_value(customer_id);
CREATE INDEX idx_mart_clv_segment ON analytics.mart_customer_lifetime_value(rfm_segment);
CREATE INDEX idx_mart_clv_tier ON analytics.mart_customer_lifetime_value(clv_tier);
CREATE INDEX idx_mart_clv_churned ON analytics.mart_customer_lifetime_value(is_churned);

-- ============================================================================
-- Product Performance Metrics
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_product_performance CASCADE;

CREATE TABLE analytics.mart_product_performance (
    product_sk INTEGER PRIMARY KEY REFERENCES analytics.dim_products(product_sk),
    product_id VARCHAR(50) NOT NULL,
    product_name VARCHAR(255),
    category VARCHAR(100),
    brand VARCHAR(100),
    
    -- Lifetime metrics
    total_revenue DECIMAL(15, 2) DEFAULT 0,
    total_quantity_sold INTEGER DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    total_customers INTEGER DEFAULT 0,
    
    -- Averages
    avg_unit_price DECIMAL(12, 2),
    avg_quantity_per_order DECIMAL(8, 2),
    
    -- Recent performance (last 30 days)
    revenue_last_30_days DECIMAL(12, 2) DEFAULT 0,
    quantity_last_30_days INTEGER DEFAULT 0,
    orders_last_30_days INTEGER DEFAULT 0,
    
    -- Growth
    revenue_mom_change DECIMAL(10, 4),
    quantity_mom_change DECIMAL(10, 4),
    
    -- Profitability (if cost data available)
    total_cost DECIMAL(15, 2),
    total_profit DECIMAL(15, 2),
    profit_margin DECIMAL(5, 4),
    
    -- Rankings
    revenue_rank INTEGER,
    quantity_rank INTEGER,
    
    -- Performance tier
    performance_tier VARCHAR(20), -- A, B, C, D
    
    -- Reorder rate
    repeat_purchase_rate DECIMAL(5, 4),
    
    -- Returns (if tracked)
    return_rate DECIMAL(5, 4),
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mart_product_category ON analytics.mart_product_performance(category);
CREATE INDEX idx_mart_product_brand ON analytics.mart_product_performance(brand);
CREATE INDEX idx_mart_product_tier ON analytics.mart_product_performance(performance_tier);

-- ============================================================================
-- Customer Cohort Analysis Table
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_customer_cohorts CASCADE;

CREATE TABLE analytics.mart_customer_cohorts (
    cohort_month DATE NOT NULL,
    months_since_acquisition INTEGER NOT NULL,
    
    -- Cohort size
    cohort_size INTEGER NOT NULL,
    
    -- Retention
    retained_customers INTEGER DEFAULT 0,
    retention_rate DECIMAL(5, 4),
    
    -- Revenue
    total_revenue DECIMAL(15, 2) DEFAULT 0,
    avg_revenue_per_customer DECIMAL(12, 2),
    
    -- Activity
    active_customers INTEGER DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    avg_orders_per_customer DECIMAL(8, 2),
    
    -- Cumulative metrics
    cumulative_revenue DECIMAL(15, 2),
    cumulative_avg_revenue_per_customer DECIMAL(12, 2),
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (cohort_month, months_since_acquisition)
);

CREATE INDEX idx_mart_cohorts_month ON analytics.mart_customer_cohorts(cohort_month);

-- ============================================================================
-- Traffic Source Performance
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_traffic_source_performance CASCADE;

CREATE TABLE analytics.mart_traffic_source_performance (
    date_key INTEGER NOT NULL REFERENCES analytics.dim_time(date_key),
    traffic_source VARCHAR(50) NOT NULL,
    device_type VARCHAR(50),
    
    -- Session metrics
    total_sessions INTEGER DEFAULT 0,
    total_page_views INTEGER DEFAULT 0,
    total_duration_minutes DECIMAL(15, 2) DEFAULT 0,
    
    -- Averages
    avg_session_duration DECIMAL(10, 2),
    avg_pages_per_session DECIMAL(8, 2),
    avg_engagement_score DECIMAL(5, 2),
    
    -- Rates
    bounce_rate DECIMAL(5, 4),
    conversion_rate DECIMAL(5, 4),
    
    -- Conversions
    total_conversions INTEGER DEFAULT 0,
    conversion_revenue DECIMAL(15, 2) DEFAULT 0,
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (date_key, traffic_source, device_type)
);

CREATE INDEX idx_mart_traffic_date ON analytics.mart_traffic_source_performance(date_key);
CREATE INDEX idx_mart_traffic_source ON analytics.mart_traffic_source_performance(traffic_source);

-- ============================================================================
-- Support Metrics Summary
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_support_metrics CASCADE;

CREATE TABLE analytics.mart_support_metrics (
    date_key INTEGER PRIMARY KEY REFERENCES analytics.dim_time(date_key),
    full_date DATE NOT NULL,
    
    -- Volume
    total_tickets INTEGER DEFAULT 0,
    tickets_opened INTEGER DEFAULT 0,
    tickets_resolved INTEGER DEFAULT 0,
    tickets_escalated INTEGER DEFAULT 0,
    
    -- By priority
    tickets_high_priority INTEGER DEFAULT 0,
    tickets_urgent INTEGER DEFAULT 0,
    
    -- By category
    tickets_billing INTEGER DEFAULT 0,
    tickets_technical INTEGER DEFAULT 0,
    tickets_shipping INTEGER DEFAULT 0,
    tickets_returns INTEGER DEFAULT 0,
    tickets_other INTEGER DEFAULT 0,
    
    -- Response times
    avg_first_response_minutes DECIMAL(10, 2),
    avg_resolution_hours DECIMAL(10, 2),
    median_resolution_hours DECIMAL(10, 2),
    
    -- Satisfaction
    avg_satisfaction_score DECIMAL(3, 2),
    satisfaction_response_rate DECIMAL(5, 4),
    nps_score DECIMAL(5, 2),
    
    -- SLA compliance
    sla_compliance_rate DECIMAL(5, 4),
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Executive KPI Dashboard Table
-- ============================================================================
DROP TABLE IF EXISTS analytics.mart_executive_kpis CASCADE;

CREATE TABLE analytics.mart_executive_kpis (
    metric_date DATE PRIMARY KEY,
    
    -- Revenue KPIs
    daily_revenue DECIMAL(15, 2),
    mtd_revenue DECIMAL(15, 2),
    ytd_revenue DECIMAL(15, 2),
    revenue_target DECIMAL(15, 2),
    revenue_vs_target_pct DECIMAL(6, 2),
    
    -- Growth KPIs
    revenue_growth_yoy DECIMAL(6, 2),
    revenue_growth_mom DECIMAL(6, 2),
    
    -- Customer KPIs
    daily_active_customers INTEGER,
    monthly_active_customers INTEGER,
    new_customers_today INTEGER,
    new_customers_mtd INTEGER,
    customer_acquisition_cost DECIMAL(10, 2),
    customer_lifetime_value_avg DECIMAL(12, 2),
    ltv_to_cac_ratio DECIMAL(6, 2),
    
    -- Churn KPIs
    monthly_churn_rate DECIMAL(5, 4),
    churned_customers_mtd INTEGER,
    
    -- Transaction KPIs
    daily_transactions INTEGER,
    avg_order_value DECIMAL(10, 2),
    conversion_rate DECIMAL(5, 4),
    
    -- Support KPIs
    support_tickets_open INTEGER,
    avg_resolution_time_hours DECIMAL(8, 2),
    customer_satisfaction_score DECIMAL(3, 2),
    
    -- Data Quality KPIs
    data_quality_score DECIMAL(5, 2),
    pipeline_health_score DECIMAL(5, 2),
    
    -- Audit
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE analytics.mart_daily_revenue IS 'Daily aggregated revenue metrics';
COMMENT ON TABLE analytics.mart_customer_lifetime_value IS 'Customer lifetime value and RFM analysis';
COMMENT ON TABLE analytics.mart_product_performance IS 'Product sales and performance metrics';
COMMENT ON TABLE analytics.mart_customer_cohorts IS 'Customer cohort retention analysis';
COMMENT ON TABLE analytics.mart_traffic_source_performance IS 'Website traffic and conversion by source';
COMMENT ON TABLE analytics.mart_support_metrics IS 'Daily support ticket metrics';
COMMENT ON TABLE analytics.mart_executive_kpis IS 'Executive dashboard KPIs';

