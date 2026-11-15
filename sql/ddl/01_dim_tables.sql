-- ============================================================================
-- Dimension Tables DDL
-- Enterprise Analytics Platform
-- ============================================================================

-- Create schema for analytics warehouse
CREATE SCHEMA IF NOT EXISTS analytics;

-- ============================================================================
-- Time Dimension (Date Dimension)
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_time CASCADE;

CREATE TABLE analytics.dim_time (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    week_of_year INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_holiday BOOLEAN DEFAULT FALSE,
    holiday_name VARCHAR(100),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    fiscal_month INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for common lookups
CREATE INDEX idx_dim_time_full_date ON analytics.dim_time(full_date);
CREATE INDEX idx_dim_time_year_month ON analytics.dim_time(year, month);

-- ============================================================================
-- Customer Dimension (SCD Type 2)
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_customers CASCADE;

CREATE TABLE analytics.dim_customers (
    customer_sk SERIAL PRIMARY KEY,                    -- Surrogate key
    customer_id VARCHAR(50) NOT NULL,                  -- Natural/business key
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    full_name VARCHAR(200),
    email VARCHAR(255),
    email_domain VARCHAR(100),
    phone VARCHAR(50),
    phone_formatted VARCHAR(50),
    address VARCHAR(500),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    country VARCHAR(10),
    customer_segment VARCHAR(50),
    lifetime_value DECIMAL(15, 2),
    is_active BOOLEAN,
    source_system VARCHAR(50),
    
    -- SCD Type 2 columns
    effective_start_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effective_end_date TIMESTAMP DEFAULT '9999-12-31 23:59:59',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Audit columns
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT 'etl_process',
    
    -- Constraints
    CONSTRAINT uq_customer_version UNIQUE (customer_id, version)
);

-- Indexes for dim_customers
CREATE INDEX idx_dim_customers_customer_id ON analytics.dim_customers(customer_id);
CREATE INDEX idx_dim_customers_current ON analytics.dim_customers(customer_id) WHERE is_current = TRUE;
CREATE INDEX idx_dim_customers_email ON analytics.dim_customers(email) WHERE email IS NOT NULL;
CREATE INDEX idx_dim_customers_segment ON analytics.dim_customers(customer_segment);
CREATE INDEX idx_dim_customers_effective_dates ON analytics.dim_customers(effective_start_date, effective_end_date);

-- ============================================================================
-- Product Dimension
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_products CASCADE;

CREATE TABLE analytics.dim_products (
    product_sk SERIAL PRIMARY KEY,                     -- Surrogate key
    product_id VARCHAR(50) NOT NULL,                   -- Natural key
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    sku VARCHAR(50),
    unit_price DECIMAL(10, 2),
    cost_price DECIMAL(10, 2),
    profit_margin DECIMAL(5, 4) GENERATED ALWAYS AS (
        CASE WHEN unit_price > 0 
             THEN (unit_price - COALESCE(cost_price, 0)) / unit_price 
             ELSE 0 
        END
    ) STORED,
    weight_kg DECIMAL(10, 2),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- SCD Type 2 columns
    effective_start_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effective_end_date TIMESTAMP DEFAULT '9999-12-31 23:59:59',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Audit columns
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_product_version UNIQUE (product_id, version)
);

-- Indexes for dim_products
CREATE INDEX idx_dim_products_product_id ON analytics.dim_products(product_id);
CREATE INDEX idx_dim_products_current ON analytics.dim_products(product_id) WHERE is_current = TRUE;
CREATE INDEX idx_dim_products_category ON analytics.dim_products(category);
CREATE INDEX idx_dim_products_brand ON analytics.dim_products(brand);
CREATE INDEX idx_dim_products_sku ON analytics.dim_products(sku);

-- ============================================================================
-- Channel Dimension
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_channels CASCADE;

CREATE TABLE analytics.dim_channels (
    channel_sk SERIAL PRIMARY KEY,
    channel_code VARCHAR(50) NOT NULL UNIQUE,
    channel_name VARCHAR(100) NOT NULL,
    channel_category VARCHAR(50),
    is_digital BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed channel dimension
INSERT INTO analytics.dim_channels (channel_code, channel_name, channel_category, is_digital) VALUES
    ('WEB', 'Website', 'Digital', TRUE),
    ('MOBILE', 'Mobile App', 'Digital', TRUE),
    ('STORE', 'Retail Store', 'Physical', FALSE),
    ('PHONE', 'Phone Sales', 'Direct', FALSE),
    ('PARTNER', 'Partner Channel', 'Indirect', TRUE),
    ('API', 'API Integration', 'Digital', TRUE)
ON CONFLICT (channel_code) DO NOTHING;

-- ============================================================================
-- Payment Method Dimension
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_payment_methods CASCADE;

CREATE TABLE analytics.dim_payment_methods (
    payment_method_sk SERIAL PRIMARY KEY,
    payment_method_code VARCHAR(50) NOT NULL UNIQUE,
    payment_method_name VARCHAR(100) NOT NULL,
    payment_category VARCHAR(50),
    is_digital BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed payment method dimension
INSERT INTO analytics.dim_payment_methods (payment_method_code, payment_method_name, payment_category, is_digital) VALUES
    ('CREDIT_CARD', 'Credit Card', 'Card', TRUE),
    ('DEBIT_CARD', 'Debit Card', 'Card', TRUE),
    ('PAYPAL', 'PayPal', 'Digital Wallet', TRUE),
    ('APPLE_PAY', 'Apple Pay', 'Digital Wallet', TRUE),
    ('GOOGLE_PAY', 'Google Pay', 'Digital Wallet', TRUE),
    ('BANK_TRANSFER', 'Bank Transfer', 'Bank', TRUE),
    ('CASH', 'Cash', 'Cash', FALSE)
ON CONFLICT (payment_method_code) DO NOTHING;

-- ============================================================================
-- Geography Dimension
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_geography CASCADE;

CREATE TABLE analytics.dim_geography (
    geography_sk SERIAL PRIMARY KEY,
    country_code VARCHAR(10) NOT NULL,
    country_name VARCHAR(100) NOT NULL,
    region VARCHAR(100),
    continent VARCHAR(50),
    currency_code VARCHAR(10),
    timezone VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_country_code UNIQUE (country_code)
);

-- Seed geography dimension
INSERT INTO analytics.dim_geography (country_code, country_name, region, continent, currency_code, timezone) VALUES
    ('US', 'United States', 'North America', 'Americas', 'USD', 'America/New_York'),
    ('CA', 'Canada', 'North America', 'Americas', 'CAD', 'America/Toronto'),
    ('GB', 'United Kingdom', 'Western Europe', 'Europe', 'GBP', 'Europe/London'),
    ('DE', 'Germany', 'Western Europe', 'Europe', 'EUR', 'Europe/Berlin'),
    ('FR', 'France', 'Western Europe', 'Europe', 'EUR', 'Europe/Paris'),
    ('AU', 'Australia', 'Oceania', 'Oceania', 'AUD', 'Australia/Sydney'),
    ('JP', 'Japan', 'East Asia', 'Asia', 'JPY', 'Asia/Tokyo')
ON CONFLICT (country_code) DO NOTHING;

-- ============================================================================
-- Support Agent Dimension
-- ============================================================================
DROP TABLE IF EXISTS analytics.dim_support_agents CASCADE;

CREATE TABLE analytics.dim_support_agents (
    agent_sk SERIAL PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL UNIQUE,
    agent_name VARCHAR(100),
    department VARCHAR(100),
    team VARCHAR(100),
    hire_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Populate Time Dimension
-- ============================================================================
INSERT INTO analytics.dim_time (
    date_key,
    full_date,
    year,
    quarter,
    month,
    month_name,
    week_of_year,
    day_of_month,
    day_of_week,
    day_name,
    is_weekend,
    fiscal_year,
    fiscal_quarter,
    fiscal_month
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER as date_key,
    d as full_date,
    EXTRACT(YEAR FROM d) as year,
    EXTRACT(QUARTER FROM d) as quarter,
    EXTRACT(MONTH FROM d) as month,
    TO_CHAR(d, 'Month') as month_name,
    EXTRACT(WEEK FROM d) as week_of_year,
    EXTRACT(DAY FROM d) as day_of_month,
    EXTRACT(DOW FROM d) as day_of_week,
    TO_CHAR(d, 'Day') as day_name,
    CASE WHEN EXTRACT(DOW FROM d) IN (0, 6) THEN TRUE ELSE FALSE END as is_weekend,
    -- Fiscal year (assuming fiscal year starts in February)
    CASE WHEN EXTRACT(MONTH FROM d) >= 2 
         THEN EXTRACT(YEAR FROM d) 
         ELSE EXTRACT(YEAR FROM d) - 1 
    END as fiscal_year,
    CASE 
        WHEN EXTRACT(MONTH FROM d) IN (2,3,4) THEN 1
        WHEN EXTRACT(MONTH FROM d) IN (5,6,7) THEN 2
        WHEN EXTRACT(MONTH FROM d) IN (8,9,10) THEN 3
        ELSE 4
    END as fiscal_quarter,
    CASE 
        WHEN EXTRACT(MONTH FROM d) >= 2 THEN EXTRACT(MONTH FROM d) - 1
        ELSE EXTRACT(MONTH FROM d) + 11
    END as fiscal_month
FROM GENERATE_SERIES('2018-01-01'::DATE, '2030-12-31'::DATE, '1 day') d
ON CONFLICT (date_key) DO NOTHING;

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE analytics.dim_time IS 'Date/time dimension for temporal analysis';
COMMENT ON TABLE analytics.dim_customers IS 'Customer dimension with SCD Type 2 history tracking';
COMMENT ON TABLE analytics.dim_products IS 'Product dimension with SCD Type 2 history tracking';
COMMENT ON TABLE analytics.dim_channels IS 'Sales channel dimension';
COMMENT ON TABLE analytics.dim_payment_methods IS 'Payment method dimension';
COMMENT ON TABLE analytics.dim_geography IS 'Geographic/location dimension';

COMMENT ON COLUMN analytics.dim_customers.customer_sk IS 'Surrogate key for dimension';
COMMENT ON COLUMN analytics.dim_customers.customer_id IS 'Natural business key from source system';
COMMENT ON COLUMN analytics.dim_customers.effective_start_date IS 'Start date of this version';
COMMENT ON COLUMN analytics.dim_customers.effective_end_date IS 'End date of this version (9999-12-31 for current)';
COMMENT ON COLUMN analytics.dim_customers.is_current IS 'Flag indicating current active record';

