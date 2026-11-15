# Data Dictionary

## Overview

This document provides detailed descriptions of all tables, columns, and relationships in the Enterprise Analytics Platform data warehouse.

---

## Dimension Tables

### dim_customers

Customer dimension with SCD Type 2 history tracking.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| customer_sk | SERIAL | No | Surrogate key (primary key) |
| customer_id | VARCHAR(50) | No | Natural/business key from source system |
| first_name | VARCHAR(100) | Yes | Customer first name |
| last_name | VARCHAR(100) | Yes | Customer last name |
| full_name | VARCHAR(200) | Yes | Concatenated full name |
| email | VARCHAR(255) | Yes | Email address (lowercase) |
| email_domain | VARCHAR(100) | Yes | Extracted email domain |
| phone | VARCHAR(50) | Yes | Raw phone number |
| phone_formatted | VARCHAR(50) | Yes | Formatted phone number |
| address | VARCHAR(500) | Yes | Street address |
| city | VARCHAR(100) | Yes | City |
| state | VARCHAR(50) | Yes | State/Province |
| postal_code | VARCHAR(20) | Yes | Postal/ZIP code |
| country | VARCHAR(10) | Yes | ISO country code |
| customer_segment | VARCHAR(50) | Yes | Customer segment (Enterprise, SMB, Consumer) |
| lifetime_value | DECIMAL(15,2) | Yes | Calculated LTV |
| is_active | BOOLEAN | Yes | Active customer flag |
| source_system | VARCHAR(50) | Yes | Originating system |
| effective_start_date | TIMESTAMP | No | Start of this version's validity |
| effective_end_date | TIMESTAMP | Yes | End of validity (9999-12-31 for current) |
| is_current | BOOLEAN | No | Current record flag |
| version | INTEGER | No | Version number |
| created_at | TIMESTAMP | Yes | Record creation timestamp |
| updated_at | TIMESTAMP | Yes | Record update timestamp |

**Indexes:**
- `idx_dim_customers_customer_id` - Natural key lookup
- `idx_dim_customers_current` - Current record lookup
- `idx_dim_customers_email` - Email lookup
- `idx_dim_customers_segment` - Segment filtering

---

### dim_products

Product catalog dimension with SCD Type 2 history.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| product_sk | SERIAL | No | Surrogate key |
| product_id | VARCHAR(50) | No | Natural product key |
| product_name | VARCHAR(255) | No | Product display name |
| category | VARCHAR(100) | Yes | Product category |
| subcategory | VARCHAR(100) | Yes | Product subcategory |
| brand | VARCHAR(100) | Yes | Brand name |
| sku | VARCHAR(50) | Yes | Stock keeping unit |
| unit_price | DECIMAL(10,2) | Yes | List price |
| cost_price | DECIMAL(10,2) | Yes | Cost/wholesale price |
| profit_margin | DECIMAL(5,4) | Yes | Calculated margin (generated) |
| weight_kg | DECIMAL(10,2) | Yes | Product weight |
| is_active | BOOLEAN | Yes | Active product flag |
| effective_start_date | TIMESTAMP | No | Version start |
| effective_end_date | TIMESTAMP | Yes | Version end |
| is_current | BOOLEAN | No | Current version flag |
| version | INTEGER | No | Version number |

---

### dim_time

Date/time dimension for temporal analysis.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| date_key | INTEGER | No | Primary key (YYYYMMDD format) |
| full_date | DATE | No | Full date value |
| year | INTEGER | No | Calendar year |
| quarter | INTEGER | No | Calendar quarter (1-4) |
| month | INTEGER | No | Calendar month (1-12) |
| month_name | VARCHAR(20) | No | Month name |
| week_of_year | INTEGER | No | Week number |
| day_of_month | INTEGER | No | Day of month |
| day_of_week | INTEGER | No | Day of week (0=Sunday) |
| day_name | VARCHAR(20) | No | Day name |
| is_weekend | BOOLEAN | No | Weekend flag |
| is_holiday | BOOLEAN | Yes | Holiday flag |
| holiday_name | VARCHAR(100) | Yes | Holiday name |
| fiscal_year | INTEGER | Yes | Fiscal year |
| fiscal_quarter | INTEGER | Yes | Fiscal quarter |
| fiscal_month | INTEGER | Yes | Fiscal month |

---

### dim_channels

Sales channel dimension.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| channel_sk | SERIAL | No | Surrogate key |
| channel_code | VARCHAR(50) | No | Channel code (WEB, MOBILE, etc.) |
| channel_name | VARCHAR(100) | No | Display name |
| channel_category | VARCHAR(50) | Yes | Category (Digital, Physical) |
| is_digital | BOOLEAN | Yes | Digital channel flag |
| is_active | BOOLEAN | Yes | Active flag |

**Values:**
- WEB - Website
- MOBILE - Mobile App
- STORE - Retail Store
- PHONE - Phone Sales
- PARTNER - Partner Channel
- API - API Integration

---

### dim_payment_methods

Payment method dimension.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| payment_method_sk | SERIAL | No | Surrogate key |
| payment_method_code | VARCHAR(50) | No | Payment code |
| payment_method_name | VARCHAR(100) | No | Display name |
| payment_category | VARCHAR(50) | Yes | Category (Card, Digital Wallet, etc.) |
| is_digital | BOOLEAN | Yes | Digital payment flag |
| is_active | BOOLEAN | Yes | Active flag |

---

### dim_geography

Geographic/location dimension.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| geography_sk | SERIAL | No | Surrogate key |
| country_code | VARCHAR(10) | No | ISO country code |
| country_name | VARCHAR(100) | No | Country name |
| region | VARCHAR(100) | Yes | Geographic region |
| continent | VARCHAR(50) | Yes | Continent |
| currency_code | VARCHAR(10) | Yes | Local currency |
| timezone | VARCHAR(50) | Yes | Primary timezone |

---

## Fact Tables

### fact_transactions

Transaction-level sales data.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| transaction_sk | BIGSERIAL | No | Surrogate key |
| customer_sk | INTEGER | Yes | FK to dim_customers |
| product_sk | INTEGER | Yes | FK to dim_products |
| date_key | INTEGER | Yes | FK to dim_time |
| channel_sk | INTEGER | Yes | FK to dim_channels |
| payment_method_sk | INTEGER | Yes | FK to dim_payment_methods |
| geography_sk | INTEGER | Yes | FK to dim_geography |
| transaction_id | VARCHAR(50) | No | Business transaction ID |
| transaction_timestamp | TIMESTAMP | No | Transaction date/time |
| quantity | INTEGER | No | Units purchased |
| unit_price_usd | DECIMAL(12,2) | No | Unit price in USD |
| total_amount_usd | DECIMAL(15,2) | No | Total in USD |
| original_amount | DECIMAL(15,2) | Yes | Original currency amount |
| original_currency | VARCHAR(10) | Yes | Original currency code |
| exchange_rate | DECIMAL(10,6) | Yes | FX rate used |
| discount_amount | DECIMAL(10,2) | Yes | Discount applied |
| tax_amount | DECIMAL(10,2) | Yes | Tax amount |
| shipping_amount | DECIMAL(10,2) | Yes | Shipping cost |
| status | VARCHAR(50) | No | Transaction status |
| is_high_value | BOOLEAN | Yes | High value flag |
| is_late_arrival | BOOLEAN | Yes | Late arrival flag |
| processing_date | DATE | Yes | Processing date |
| processing_delay_days | INTEGER | Yes | Days to process |
| _extracted_at | TIMESTAMP | Yes | Extraction timestamp |
| _loaded_at | TIMESTAMP | Yes | Load timestamp |
| _source | VARCHAR(100) | Yes | Source system |

**Status Values:**
- Completed
- Pending
- Refunded
- Failed
- Cancelled

---

### fact_customer_sessions

Website/app session data.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| session_sk | BIGSERIAL | No | Surrogate key |
| customer_sk | INTEGER | Yes | FK to dim_customers (null for anonymous) |
| date_key | INTEGER | Yes | FK to dim_time |
| channel_sk | INTEGER | Yes | FK to dim_channels |
| geography_sk | INTEGER | Yes | FK to dim_geography |
| session_id | VARCHAR(50) | No | Session identifier |
| session_start | TIMESTAMP | No | Session start time |
| session_end | TIMESTAMP | Yes | Session end time |
| device_type | VARCHAR(50) | Yes | Device category |
| browser | VARCHAR(50) | Yes | Browser name |
| browser_family | VARCHAR(50) | Yes | Browser family (Chromium, etc.) |
| os | VARCHAR(50) | Yes | Operating system |
| is_mobile_os | BOOLEAN | Yes | Mobile OS flag |
| referrer | VARCHAR(500) | Yes | Referring URL |
| traffic_source | VARCHAR(50) | Yes | Traffic source category |
| landing_page | VARCHAR(500) | Yes | Landing page URL |
| exit_page | VARCHAR(500) | Yes | Exit page URL |
| duration_seconds | INTEGER | Yes | Session duration |
| duration_minutes | DECIMAL(10,2) | Yes | Duration in minutes |
| page_views | INTEGER | Yes | Page view count |
| events_count | INTEGER | Yes | Event count |
| pages_per_minute | DECIMAL(10,4) | Yes | Pages per minute |
| engagement_score | DECIMAL(5,2) | Yes | Engagement score (0-100) |
| session_category | VARCHAR(50) | Yes | Session category |
| is_bounce | BOOLEAN | Yes | Single page session |
| conversion | BOOLEAN | Yes | Conversion flag |
| session_hour | INTEGER | Yes | Hour of session start |
| session_day_of_week | INTEGER | Yes | Day of week |
| time_of_day | VARCHAR(20) | Yes | Time category |

**Traffic Sources:**
- Direct
- Organic Search
- Social
- Email
- Paid
- Referral

**Session Categories:**
- Converter
- Highly Engaged
- Engaged
- Browser
- Low Engagement
- Bouncer

---

### fact_support_interactions

Customer support ticket data.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| interaction_sk | BIGSERIAL | No | Surrogate key |
| customer_sk | INTEGER | Yes | FK to dim_customers |
| agent_sk | INTEGER | Yes | FK to dim_support_agents |
| created_date_key | INTEGER | Yes | FK to dim_time (created) |
| resolved_date_key | INTEGER | Yes | FK to dim_time (resolved) |
| ticket_id | VARCHAR(50) | No | Ticket identifier |
| created_at | TIMESTAMP | No | Ticket creation time |
| resolved_at | TIMESTAMP | Yes | Resolution time |
| channel | VARCHAR(50) | Yes | Support channel |
| category | VARCHAR(100) | Yes | Issue category |
| priority | VARCHAR(20) | Yes | Priority level |
| status | VARCHAR(50) | Yes | Ticket status |
| subject | TEXT | Yes | Ticket subject |
| first_response_minutes | INTEGER | Yes | Time to first response |
| resolution_hours | DECIMAL(10,2) | Yes | Resolution time |
| satisfaction_score | INTEGER | Yes | CSAT score (1-5) |
| is_resolved | BOOLEAN | Yes | Resolved flag |
| is_escalated | BOOLEAN | Yes | Escalation flag |

---

## Aggregated Marts

### mart_daily_revenue

Pre-aggregated daily revenue metrics.

| Column | Type | Description |
|--------|------|-------------|
| date_key | INTEGER | Primary key, FK to dim_time |
| full_date | DATE | Full date |
| total_revenue | DECIMAL(15,2) | Total daily revenue |
| total_transactions | INTEGER | Transaction count |
| total_quantity | INTEGER | Units sold |
| avg_transaction_value | DECIMAL(12,2) | Average order value |
| unique_customers | INTEGER | Unique customer count |
| new_customers | INTEGER | First-time customers |
| web_revenue | DECIMAL(15,2) | Web channel revenue |
| mobile_revenue | DECIMAL(15,2) | Mobile channel revenue |
| store_revenue | DECIMAL(15,2) | Store channel revenue |
| revenue_dod_change | DECIMAL(10,4) | Day-over-day change |
| revenue_wow_change | DECIMAL(10,4) | Week-over-week change |

---

### mart_customer_lifetime_value

Customer lifetime value and RFM analysis.

| Column | Type | Description |
|--------|------|-------------|
| customer_sk | INTEGER | Primary key, FK to dim_customers |
| customer_id | VARCHAR(50) | Business key |
| total_lifetime_revenue | DECIMAL(15,2) | Total revenue |
| total_orders | INTEGER | Order count |
| avg_order_value | DECIMAL(12,2) | Average order value |
| first_order_date | DATE | First purchase |
| last_order_date | DATE | Last purchase |
| customer_age_days | INTEGER | Days since first purchase |
| days_since_last_order | INTEGER | Recency |
| recency_score | INTEGER | RFM Recency (1-5) |
| frequency_score | INTEGER | RFM Frequency (1-5) |
| monetary_score | INTEGER | RFM Monetary (1-5) |
| rfm_segment | VARCHAR(50) | RFM segment name |
| predicted_clv_12m | DECIMAL(12,2) | 12-month CLV prediction |
| clv_tier | VARCHAR(20) | Value tier |
| is_churned | BOOLEAN | Churn flag |
| churn_probability | DECIMAL(5,4) | Churn probability |

**RFM Segments:**
- Champions
- Loyal Customers
- Potential Loyalists
- New Customers
- Promising
- At Risk
- Can't Lose Them
- Hibernating
- Lost

---

## Metadata Tables

### _watermarks

Incremental load tracking.

| Column | Type | Description |
|--------|------|-------------|
| table_name | VARCHAR(100) | Table name (PK) |
| watermark_column | VARCHAR(100) | Column used for watermark |
| watermark_value | TIMESTAMP | Last processed value |
| row_count | BIGINT | Rows in last load |
| last_run_status | VARCHAR(20) | Success/Failed |
| updated_at | TIMESTAMP | Last update time |

---

### _data_quality_log

Data quality check results.

| Column | Type | Description |
|--------|------|-------------|
| log_id | BIGSERIAL | Primary key |
| run_timestamp | TIMESTAMP | Check execution time |
| dataset_name | VARCHAR(100) | Dataset checked |
| check_name | VARCHAR(200) | Check name |
| passed | BOOLEAN | Pass/Fail |
| severity | VARCHAR(20) | Error/Warning/Info |
| message | TEXT | Result message |
| affected_rows | INTEGER | Rows affected |
| details | JSONB | Additional details |

---

### _pipeline_log

Pipeline execution log.

| Column | Type | Description |
|--------|------|-------------|
| log_id | BIGSERIAL | Primary key |
| dag_id | VARCHAR(100) | Airflow DAG ID |
| dag_run_id | VARCHAR(100) | Run ID |
| task_id | VARCHAR(100) | Task ID |
| execution_date | TIMESTAMP | Scheduled date |
| start_time | TIMESTAMP | Actual start |
| end_time | TIMESTAMP | Actual end |
| duration_seconds | INTEGER | Duration |
| status | VARCHAR(20) | Success/Failed/Running |
| rows_processed | BIGINT | Rows processed |
| error_message | TEXT | Error details |

