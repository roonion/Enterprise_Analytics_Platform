-- ============================================================================
-- Fact Tables DDL
-- Enterprise Analytics Platform
-- ============================================================================

-- ============================================================================
-- Fact: Transactions
-- Grain: One row per transaction
-- ============================================================================
DROP TABLE IF EXISTS analytics.fact_transactions CASCADE;

CREATE TABLE analytics.fact_transactions (
    transaction_sk BIGSERIAL PRIMARY KEY,
    
    -- Foreign keys (surrogate)
    customer_sk INTEGER REFERENCES analytics.dim_customers(customer_sk),
    product_sk INTEGER REFERENCES analytics.dim_products(product_sk),
    date_key INTEGER REFERENCES analytics.dim_time(date_key),
    channel_sk INTEGER REFERENCES analytics.dim_channels(channel_sk),
    payment_method_sk INTEGER REFERENCES analytics.dim_payment_methods(payment_method_sk),
    geography_sk INTEGER REFERENCES analytics.dim_geography(geography_sk),
    
    -- Degenerate dimensions (transaction-specific attributes)
    transaction_id VARCHAR(50) NOT NULL UNIQUE,
    transaction_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Measures
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price_usd DECIMAL(12, 2) NOT NULL,
    total_amount_usd DECIMAL(15, 2) NOT NULL,
    original_amount DECIMAL(15, 2),
    original_currency VARCHAR(10),
    exchange_rate DECIMAL(10, 6) DEFAULT 1.0,
    discount_amount DECIMAL(10, 2) DEFAULT 0,
    tax_amount DECIMAL(10, 2) DEFAULT 0,
    shipping_amount DECIMAL(10, 2) DEFAULT 0,
    
    -- Transaction attributes
    status VARCHAR(50) NOT NULL,
    is_high_value BOOLEAN DEFAULT FALSE,
    is_late_arrival BOOLEAN DEFAULT FALSE,
    
    -- Processing metadata
    processing_date DATE,
    processing_delay_days INTEGER,
    
    -- Audit columns
    _extracted_at TIMESTAMP,
    _loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    _source VARCHAR(100),
    
    -- Constraints
    CONSTRAINT chk_quantity_positive CHECK (quantity > 0),
    CONSTRAINT chk_amount_non_negative CHECK (total_amount_usd >= 0)
);

-- Indexes for fact_transactions
CREATE INDEX idx_fact_txn_date ON analytics.fact_transactions(date_key);
CREATE INDEX idx_fact_txn_customer ON analytics.fact_transactions(customer_sk);
CREATE INDEX idx_fact_txn_product ON analytics.fact_transactions(product_sk);
CREATE INDEX idx_fact_txn_timestamp ON analytics.fact_transactions(transaction_timestamp);
CREATE INDEX idx_fact_txn_status ON analytics.fact_transactions(status);
CREATE INDEX idx_fact_txn_channel ON analytics.fact_transactions(channel_sk);

-- Partitioning-ready index (if implementing partitioning later)
CREATE INDEX idx_fact_txn_date_timestamp ON analytics.fact_transactions(date_key, transaction_timestamp);

-- ============================================================================
-- Fact: Customer Sessions
-- Grain: One row per customer session
-- ============================================================================
DROP TABLE IF EXISTS analytics.fact_customer_sessions CASCADE;

CREATE TABLE analytics.fact_customer_sessions (
    session_sk BIGSERIAL PRIMARY KEY,
    
    -- Foreign keys
    customer_sk INTEGER REFERENCES analytics.dim_customers(customer_sk),
    date_key INTEGER REFERENCES analytics.dim_time(date_key),
    channel_sk INTEGER REFERENCES analytics.dim_channels(channel_sk),
    geography_sk INTEGER REFERENCES analytics.dim_geography(geography_sk),
    
    -- Degenerate dimension
    session_id VARCHAR(50) NOT NULL UNIQUE,
    
    -- Timestamps
    session_start TIMESTAMP WITH TIME ZONE NOT NULL,
    session_end TIMESTAMP WITH TIME ZONE,
    
    -- Session attributes
    device_type VARCHAR(50),
    browser VARCHAR(50),
    browser_family VARCHAR(50),
    os VARCHAR(50),
    is_mobile_os BOOLEAN,
    
    -- Traffic source
    referrer VARCHAR(500),
    traffic_source VARCHAR(50),
    landing_page VARCHAR(500),
    exit_page VARCHAR(500),
    
    -- Measures
    duration_seconds INTEGER,
    duration_minutes DECIMAL(10, 2),
    page_views INTEGER DEFAULT 0,
    events_count INTEGER DEFAULT 0,
    pages_per_minute DECIMAL(10, 4),
    
    -- Engagement
    engagement_score DECIMAL(5, 2),
    session_category VARCHAR(50),
    is_bounce BOOLEAN DEFAULT FALSE,
    conversion BOOLEAN DEFAULT FALSE,
    
    -- Time attributes
    session_hour INTEGER,
    session_day_of_week INTEGER,
    time_of_day VARCHAR(20),
    
    -- Audit columns
    _extracted_at TIMESTAMP,
    _loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    _source VARCHAR(100)
);

-- Indexes for fact_customer_sessions
CREATE INDEX idx_fact_sessions_date ON analytics.fact_customer_sessions(date_key);
CREATE INDEX idx_fact_sessions_customer ON analytics.fact_customer_sessions(customer_sk);
CREATE INDEX idx_fact_sessions_start ON analytics.fact_customer_sessions(session_start);
CREATE INDEX idx_fact_sessions_traffic ON analytics.fact_customer_sessions(traffic_source);
CREATE INDEX idx_fact_sessions_device ON analytics.fact_customer_sessions(device_type);
CREATE INDEX idx_fact_sessions_conversion ON analytics.fact_customer_sessions(conversion) WHERE conversion = TRUE;

-- ============================================================================
-- Fact: Support Interactions
-- Grain: One row per support ticket
-- ============================================================================
DROP TABLE IF EXISTS analytics.fact_support_interactions CASCADE;

CREATE TABLE analytics.fact_support_interactions (
    interaction_sk BIGSERIAL PRIMARY KEY,
    
    -- Foreign keys
    customer_sk INTEGER REFERENCES analytics.dim_customers(customer_sk),
    agent_sk INTEGER REFERENCES analytics.dim_support_agents(agent_sk),
    created_date_key INTEGER REFERENCES analytics.dim_time(date_key),
    resolved_date_key INTEGER REFERENCES analytics.dim_time(date_key),
    
    -- Degenerate dimension
    ticket_id VARCHAR(50) NOT NULL UNIQUE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    
    -- Ticket attributes
    channel VARCHAR(50),
    category VARCHAR(100),
    priority VARCHAR(20),
    status VARCHAR(50),
    subject TEXT,
    
    -- Measures
    first_response_minutes INTEGER,
    resolution_hours DECIMAL(10, 2),
    satisfaction_score INTEGER,
    
    -- Flags
    is_resolved BOOLEAN DEFAULT FALSE,
    is_escalated BOOLEAN DEFAULT FALSE,
    
    -- Audit columns
    _extracted_at TIMESTAMP,
    _loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    _source VARCHAR(100),
    
    -- Constraints
    CONSTRAINT chk_satisfaction_range CHECK (satisfaction_score IS NULL OR (satisfaction_score >= 1 AND satisfaction_score <= 5))
);

-- Indexes for fact_support_interactions
CREATE INDEX idx_fact_support_created_date ON analytics.fact_support_interactions(created_date_key);
CREATE INDEX idx_fact_support_customer ON analytics.fact_support_interactions(customer_sk);
CREATE INDEX idx_fact_support_agent ON analytics.fact_support_interactions(agent_sk);
CREATE INDEX idx_fact_support_status ON analytics.fact_support_interactions(status);
CREATE INDEX idx_fact_support_category ON analytics.fact_support_interactions(category);
CREATE INDEX idx_fact_support_priority ON analytics.fact_support_interactions(priority);

-- ============================================================================
-- Bridge Table: Transaction-Product (for multi-product transactions)
-- ============================================================================
DROP TABLE IF EXISTS analytics.bridge_transaction_products CASCADE;

CREATE TABLE analytics.bridge_transaction_products (
    bridge_sk BIGSERIAL PRIMARY KEY,
    transaction_sk BIGINT REFERENCES analytics.fact_transactions(transaction_sk),
    product_sk INTEGER REFERENCES analytics.dim_products(product_sk),
    quantity INTEGER NOT NULL DEFAULT 1,
    line_amount DECIMAL(12, 2),
    allocation_factor DECIMAL(5, 4) DEFAULT 1.0,
    
    CONSTRAINT uq_txn_product UNIQUE (transaction_sk, product_sk)
);

CREATE INDEX idx_bridge_txn_products_txn ON analytics.bridge_transaction_products(transaction_sk);
CREATE INDEX idx_bridge_txn_products_product ON analytics.bridge_transaction_products(product_sk);

-- ============================================================================
-- Watermark Table for Incremental Loads
-- ============================================================================
DROP TABLE IF EXISTS analytics._watermarks CASCADE;

CREATE TABLE analytics._watermarks (
    table_name VARCHAR(100) PRIMARY KEY,
    watermark_column VARCHAR(100) NOT NULL,
    watermark_value TIMESTAMP WITH TIME ZONE,
    row_count BIGINT,
    last_run_status VARCHAR(20),
    last_run_duration_seconds INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100) DEFAULT 'etl_process'
);

-- ============================================================================
-- Data Quality Log Table
-- ============================================================================
DROP TABLE IF EXISTS analytics._data_quality_log CASCADE;

CREATE TABLE analytics._data_quality_log (
    log_id BIGSERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    dataset_name VARCHAR(100) NOT NULL,
    check_name VARCHAR(200) NOT NULL,
    passed BOOLEAN NOT NULL,
    severity VARCHAR(20),
    message TEXT,
    affected_rows INTEGER,
    affected_percentage DECIMAL(5, 2),
    details JSONB,
    dag_run_id VARCHAR(100),
    task_id VARCHAR(100)
);

CREATE INDEX idx_dq_log_timestamp ON analytics._data_quality_log(run_timestamp);
CREATE INDEX idx_dq_log_dataset ON analytics._data_quality_log(dataset_name);
CREATE INDEX idx_dq_log_passed ON analytics._data_quality_log(passed);

-- ============================================================================
-- Pipeline Execution Log Table
-- ============================================================================
DROP TABLE IF EXISTS analytics._pipeline_log CASCADE;

CREATE TABLE analytics._pipeline_log (
    log_id BIGSERIAL PRIMARY KEY,
    dag_id VARCHAR(100) NOT NULL,
    dag_run_id VARCHAR(100) NOT NULL,
    task_id VARCHAR(100),
    execution_date TIMESTAMP WITH TIME ZONE,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    status VARCHAR(20),
    rows_processed BIGINT,
    error_message TEXT,
    
    CONSTRAINT uq_pipeline_run UNIQUE (dag_run_id, task_id)
);

CREATE INDEX idx_pipeline_log_dag ON analytics._pipeline_log(dag_id);
CREATE INDEX idx_pipeline_log_execution ON analytics._pipeline_log(execution_date);
CREATE INDEX idx_pipeline_log_status ON analytics._pipeline_log(status);

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE analytics.fact_transactions IS 'Transaction fact table - grain: one row per transaction';
COMMENT ON TABLE analytics.fact_customer_sessions IS 'Customer session fact table - grain: one row per session';
COMMENT ON TABLE analytics.fact_support_interactions IS 'Support interaction fact table - grain: one row per ticket';
COMMENT ON TABLE analytics._watermarks IS 'Incremental load watermark tracking';
COMMENT ON TABLE analytics._data_quality_log IS 'Data quality check results log';
COMMENT ON TABLE analytics._pipeline_log IS 'ETL pipeline execution log';

COMMENT ON COLUMN analytics.fact_transactions.customer_sk IS 'Surrogate key to dim_customers (point-in-time)';
COMMENT ON COLUMN analytics.fact_transactions.unit_price_usd IS 'Unit price converted to USD';
COMMENT ON COLUMN analytics.fact_transactions.original_amount IS 'Original transaction amount in source currency';

