# Enterprise Analytics Platform - Architecture

## Overview

The Enterprise Analytics Platform is a comprehensive end-to-end analytics system designed for processing customer behavior data, transactions, and support interactions for e-commerce/SaaS companies.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA SOURCES                                      │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤
│  CSV Files   │  JSON APIs   │  Databases   │  Streaming   │  Third Party   │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┴────────┬───────┘
       │              │              │              │                │
       └──────────────┴──────────────┴──────────────┴────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ETL LAYER (Apache Airflow)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  Extractors │───▶│ Validators  │───▶│ Transformers│───▶│   Loaders   │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│         │                  │                  │                  │          │
│  - CSV Extractor    - Data Quality    - Customer         - Incremental     │
│  - JSON Extractor   - Schema          - Transaction      - SCD Type 2      │
│  - DB Extractor     - Referential     - Session          - Batch Load      │
│  - Stream Extractor   Integrity       - Timezone                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     DATA WAREHOUSE (PostgreSQL)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Dimension Tables                              │   │
│  │  dim_customers (SCD2) │ dim_products │ dim_time │ dim_channels │... │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          Fact Tables                                 │   │
│  │  fact_transactions │ fact_customer_sessions │ fact_support_interactions│  │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Aggregated Marts                              │   │
│  │  mart_daily_revenue │ mart_customer_lifetime_value │ mart_cohorts   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BI & VISUALIZATION                                   │
├───────────────────────────────┬─────────────────────────────────────────────┤
│         Metabase              │               Streamlit                      │
│  - Executive Dashboard        │  - Executive Dashboard                       │
│  - Operational Dashboard      │  - Operational Dashboard                     │
│  - Self-Service SQL           │  - Self-Service Analytics                    │
└───────────────────────────────┴─────────────────────────────────────────────┘
```

## Components

### 1. Data Sources

The platform supports multiple data source types:

- **CSV Files**: Batch exports with handling for messy data (encoding, delimiters, missing values)
- **JSON APIs**: REST API consumption with pagination and nested structure flattening
- **Databases**: Direct database extraction with incremental loading support
- **Streaming**: Micro-batch processing with watermark-based late arrival handling

### 2. ETL Layer

Built on Apache Airflow for orchestration:

#### DAGs

| DAG | Schedule | Description |
|-----|----------|-------------|
| `daily_etl` | 6:00 AM UTC | Main ETL pipeline for all data sources |
| `customer_pipeline` | 7:00 AM UTC | Customer dimension with SCD Type 2 |
| `backfill_pipeline` | Manual | Historical data backfilling |

#### Extractors

- **CSVExtractor**: Handles encoding detection, delimiter inference, chunked reading
- **JSONExtractor**: Supports nested structures, JSON Lines, API pagination
- **DatabaseExtractor**: Incremental loads, watermark tracking
- **StreamingExtractor**: Micro-batching, late arrival handling

#### Transformers

- **CustomerTransformer**: Fuzzy matching deduplication, PII masking
- **TransactionTransformer**: Currency conversion, amount validation
- **SessionTransformer**: Engagement scoring, traffic categorization
- **TimezoneHandler**: UTC normalization, timezone detection
- **SchemaEvolutionHandler**: Schema versioning, migrations

#### Validators

- **DataQualityValidator**: Null checks, duplicates, range validation
- **SchemaValidator**: Type validation, pattern matching
- **ReferentialIntegrityValidator**: Foreign key checking, orphan detection

### 3. Data Warehouse

PostgreSQL-based dimensional model:

#### Dimension Tables

| Table | Type | Description |
|-------|------|-------------|
| `dim_customers` | SCD Type 2 | Customer attributes with history |
| `dim_products` | SCD Type 2 | Product catalog |
| `dim_time` | Type 1 | Date dimension (2018-2030) |
| `dim_channels` | Type 1 | Sales channels |
| `dim_payment_methods` | Type 1 | Payment methods |
| `dim_geography` | Type 1 | Geographic regions |

#### Fact Tables

| Table | Grain | Description |
|-------|-------|-------------|
| `fact_transactions` | Transaction | Sales transactions |
| `fact_customer_sessions` | Session | Website sessions |
| `fact_support_interactions` | Ticket | Support tickets |

#### Aggregated Marts

- `mart_daily_revenue`: Daily revenue summary
- `mart_customer_lifetime_value`: CLV and RFM analysis
- `mart_product_performance`: Product metrics
- `mart_customer_cohorts`: Cohort retention
- `mart_traffic_source_performance`: Traffic analysis
- `mart_support_metrics`: Support KPIs

### 4. Data Quality Framework

Multi-layer validation:

1. **Extract Validation**: Source connectivity, file existence
2. **Transform Validation**: Schema compliance, business rules
3. **Load Validation**: Referential integrity, volume checks
4. **Continuous Monitoring**: Freshness, anomaly detection

### 5. Visualization Layer

#### Metabase
- Pre-built dashboards for executives and operations
- SQL-based self-service analytics
- Scheduled reports and alerts

#### Streamlit
- Interactive Python dashboards
- Real-time operational monitoring
- Custom query interface with visualization

## Data Flow

### Batch Processing

1. Airflow scheduler triggers DAGs at scheduled times
2. Extractors pull data from sources
3. Validators check data quality
4. Transformers normalize and enrich data
5. Loaders insert/update warehouse tables
6. Marts are refreshed
7. Dashboards reflect updated data

### Incremental Loading

```sql
-- Watermark-based incremental load
SELECT * FROM source_table
WHERE updated_at > (
    SELECT watermark_value 
    FROM _watermarks 
    WHERE table_name = 'target_table'
)
```

### SCD Type 2 Process

1. Compare source records with current dimension records
2. For changed records:
   - Close existing record (set `effective_end_date`, `is_current = FALSE`)
   - Insert new record with new version number
3. For new records:
   - Insert with `version = 1`, `is_current = TRUE`

## Deployment

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5432 | Airflow metadata DB |
| `analytics-db` | 5433 | Analytics warehouse |
| `airflow-webserver` | 8080 | Airflow UI |
| `airflow-scheduler` | - | DAG scheduler |
| `metabase` | 3000 | BI tool |
| `streamlit` | 8501 | Dashboards |

### Environment Variables

See `env.example` for required configuration:

- Database connections
- Airflow settings
- API keys
- Data quality thresholds

## Monitoring & Alerting

### Pipeline Monitoring

- Execution logs in `_pipeline_log` table
- Health scores calculated from success rates
- Duration tracking and anomaly detection

### Data Quality Monitoring

- Check results in `_data_quality_log` table
- Freshness tracking for all tables
- Volume anomaly detection

### SLA Monitoring

- Target completion times per DAG
- Grace periods for acceptable delays
- Compliance reporting

## Security Considerations

1. **Data Masking**: PII fields can be masked for dev environments
2. **Access Control**: Database-level permissions
3. **Encryption**: TLS for data in transit
4. **Audit Logging**: All pipeline executions logged

## Scalability

### Horizontal Scaling

- Airflow can scale workers for parallel task execution
- PostgreSQL supports connection pooling
- Streamlit apps can be load-balanced

### Performance Optimization

- Partitioned fact tables (by date)
- Materialized views for common aggregations
- Covering indexes for dashboard queries
- Query result caching

