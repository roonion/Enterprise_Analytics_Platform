# Enterprise Analytics Platform

A comprehensive end-to-end analytics system for processing customer behavior data, transactions, and support interactions for e-commerce/SaaS companies.

## 🏗️ Architecture

```
Raw Data Sources → ETL Pipeline (Airflow) → PostgreSQL Warehouse → BI Layer (Metabase/Streamlit)
```

## ✨ Features

- **Multi-source Data Ingestion**: CSV, JSON, Database, Streaming
- **Robust ETL Pipeline**: Apache Airflow orchestration with data quality validation
- **Dimensional Data Warehouse**: Star schema with SCD Type 2 dimensions
- **Data Quality Framework**: Comprehensive validation and monitoring
- **Multiple Dashboards**: Metabase BI + Streamlit operational dashboards
- **Messy Data Handling**: Fuzzy matching, timezone normalization, currency conversion

## 📁 Project Structure

```
enterprise-analytics-platform/
├── airflow/
│   ├── dags/
│   │   ├── daily_etl.py          # Main ETL pipeline
│   │   ├── customer_pipeline.py   # SCD Type 2 customer dimension
│   │   └── backfill_pipeline.py   # Historical data backfill
│   └── tests/
├── sql/
│   ├── ddl/                       # Table definitions
│   ├── transforms/                # Transformation queries
│   └── analysis/                  # Analytical queries
├── src/
│   ├── extractors/                # Data extraction modules
│   ├── transformers/              # Data transformation logic
│   ├── validators/                # Data quality validation
│   ├── monitoring/                # Pipeline health monitoring
│   └── utils/                     # Shared utilities
├── dashboards/
│   ├── metabase_configs/          # Metabase dashboard definitions
│   └── streamlit/                 # Streamlit dashboard apps
├── data/
│   └── sample/                    # Sample data with intentional issues
├── tests/                         # Unit and integration tests
├── docs/                          # Documentation
├── docker-compose.yml             # Full stack deployment
├── requirements.txt               # Python dependencies
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose (version 2.0+)
- Python 3.11+ (for local development)
- 8GB+ RAM recommended
- 20GB+ free disk space

### 1. Clone and Setup

```bash
git clone https://github.com/roonion/Enterprise_Analytics_Platform.git
cd Enterprise_Platform

# Copy environment file
cp env.example .env

# Edit .env with your settings
# Key variables to configure:
# - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
# - AIRFLOW_UID (for Linux/Mac)
# - Data source connection strings
```

### 2. Start Services

```bash
# Start all services
docker-compose up -d

# Wait for services to be healthy (may take 2-3 minutes)
docker-compose ps

# Check logs if needed
docker-compose logs -f airflow-webserver
```

**First-time Setup:**
- Airflow requires database initialization on first run
- Wait for "Booting worker" messages in logs before accessing UI
- Metabase setup wizard will appear on first access

### 3. Access Applications

| Service | URL | Credentials | Notes |
|---------|-----|-------------|-------|
| Airflow | http://localhost:8080 | airflow / airflow | Admin UI for pipeline management |
| Metabase | http://localhost:3000 | Setup on first access | BI dashboard tool |
| Streamlit | http://localhost:8501 | No auth | Operational dashboards |
| PostgreSQL | localhost:5433 | analytics_user / analytics_password | Analytics warehouse |

### 4. Initialize Database Schema

```bash
# Run DDL scripts to create tables
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/01_dim_tables.sql
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/02_fact_tables.sql
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/03_aggregated_marts.sql
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/04_indexes.sql
```

### 5. Generate Sample Data

```bash
# Generate sample data with realistic issues
docker-compose exec airflow-webserver python -m src.utils.data_generator

# Or generate specific datasets
docker-compose exec airflow-webserver python -c "
from src.utils.data_generator import DataGenerator
gen = DataGenerator()
gen.generate_customers(1000).to_csv('/opt/airflow/data/sample/customers_messy.csv', index=False)
gen.generate_transactions(5000).to_csv('/opt/airflow/data/sample/transactions_messy.csv', index=False)
"
```

### 6. Run ETL Pipeline

```bash
# Trigger the daily ETL DAG
docker-compose exec airflow-webserver airflow dags trigger daily_etl

# Or use the Airflow UI:
# 1. Navigate to http://localhost:8080
# 2. Find 'daily_etl' DAG
# 3. Click "Play" button to trigger
```

### 7. Verify Data

```bash
# Check data in warehouse
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -c "
SELECT COUNT(*) as customer_count FROM analytics.dim_customers;
SELECT COUNT(*) as transaction_count FROM analytics.fact_transactions;
"
```

## 📊 Data Model

### Dimension Tables

- `dim_customers` - Customer attributes (SCD Type 2)
- `dim_products` - Product catalog (SCD Type 2)
- `dim_time` - Date dimension
- `dim_channels` - Sales channels
- `dim_payment_methods` - Payment methods
- `dim_geography` - Geographic regions

### Fact Tables

- `fact_transactions` - Sales transactions
- `fact_customer_sessions` - Website sessions
- `fact_support_interactions` - Support tickets

### Aggregated Marts

- `mart_daily_revenue` - Daily revenue metrics
- `mart_customer_lifetime_value` - CLV and RFM analysis
- `mart_product_performance` - Product metrics
- `mart_customer_cohorts` - Cohort retention

## 🔧 Components

### Extractors

```python
from src.extractors import CSVExtractor, JSONExtractor

# Extract CSV with messy data handling
extractor = CSVExtractor(
    file_path='data/customers.csv',
    encoding='auto',  # Auto-detect encoding
)
df = extractor.run()
```

### Transformers

```python
from src.transformers import CustomerTransformer

# Deduplicate with fuzzy matching
transformer = CustomerTransformer(
    fuzzy_threshold=85,
    deduplicate=True
)
clean_df = transformer.run(df)
```

### Validators

```python
from src.validators import DataQualityValidator

validator = DataQualityValidator(dataset_name='customers')
validator.check_not_null(['customer_id', 'email'])
validator.check_unique(['customer_id'])
validator.check_regex('email', r'^[^@]+@[^@]+\.[^@]+$')

report = validator.validate(df)
print(f"Quality Score: {report.overall_score}%")
```

## 🧪 Testing

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_transformers.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run tests in parallel (faster)
pytest tests/ -n auto

# Run only fast tests (skip slow integration tests)
pytest tests/ -m "not slow"
```

### Test Structure

- `test_etl_pipeline.py` - ETL pipeline integration tests
- `test_data_quality.py` - Data quality validator tests
- `test_transformers.py` - Transformer logic tests
- `test_extractors.py` - Data extractor tests
- `test_sql_queries.py` - SQL query logic tests

### Writing Tests

```python
# Example test structure
def test_feature_name():
    """Test description."""
    # Arrange
    input_data = create_test_data()
    
    # Act
    result = process_data(input_data)
    
    # Assert
    assert result is not None
    assert len(result) > 0
```

## 📈 Sample Analyses

### Cohort Retention

```sql
-- See sql/analysis/01_cohort_analysis.sql
SELECT cohort_month, months_since_acquisition, retention_rate
FROM cohort_analysis;
```

### Customer Lifetime Value

```sql
-- See sql/analysis/03_clv_analysis.sql
SELECT customer_id, rfm_segment, predicted_clv_12m
FROM mart_customer_lifetime_value
WHERE clv_tier = 'Platinum';
```

### Churn Analysis

```sql
-- See sql/analysis/04_churn_analysis.sql
SELECT customer_segment, churn_rate_pct
FROM segment_churn_summary;
```

## 🔍 Data Quality

### Built-in Checks

- Null rate validation
- Duplicate detection
- Referential integrity
- Schema compliance
- Business rule validation
- Freshness monitoring
- Volume anomaly detection

### Monitoring Dashboard

Access the operational dashboard at http://localhost:8501 for:
- Pipeline health scores
- Data quality metrics
- Freshness status
- Recent issues

## 📚 Documentation

### Core Documentation

- **[Architecture](docs/architecture.md)** - System design, data flow, and component details
- **[Data Dictionary](docs/data_dictionary.md)** - Complete table and column descriptions with data types
- **[Pipeline SLA](docs/pipeline_sla.md)** - Service level agreements, monitoring, and alerting

### Additional Resources

- **SQL Queries**: See `sql/analysis/` for analytical query examples
- **DAG Documentation**: See `airflow/dags/` for pipeline orchestration details
- **API Documentation**: See docstrings in `src/` modules

### Quick Reference

**Common Tasks:**
- [Setup Instructions](#-quick-start)
- [Running Tests](#-testing)
- [Troubleshooting](#-troubleshooting)
- [Development Guide](#-development)

## 🛠️ Development

### Local Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt  # If exists

# Run tests
pytest tests/ -v

# Run linting
flake8 src/ tests/
black --check src/ tests/

# Format code
black src/ tests/
```

### Development Workflow

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Test Your Changes**
   ```bash
   pytest tests/ -v
   pytest tests/test_your_module.py -v
   ```

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Write docstrings for all public functions/classes
- Keep functions focused and small
- Add logging for important operations

### Adding New Extractors

1. Create class inheriting from `BaseExtractor`
2. Implement `extract()` and `validate_source()` methods
3. Add to `src/extractors/__init__.py`

### Adding New Transformers

1. Create class inheriting from `BaseTransformer`
2. Implement `transform()` method
3. Add to `src/transformers/__init__.py`

## 🐛 Troubleshooting

### Common Issues

**Airflow not starting:**
```bash
# Check logs
docker-compose logs airflow-webserver

# Ensure sufficient memory
docker info | grep Memory

# Reset Airflow database (WARNING: deletes all DAG runs)
docker-compose down -v
docker-compose up -d
```

**Database connection issues:**
```bash
# Verify database is running
docker-compose ps analytics-db

# Check connectivity
docker-compose exec analytics-db pg_isready -U analytics_user

# Test connection manually
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -c "SELECT 1;"
```

**Pipeline failures:**
```bash
# Check Airflow UI for task logs
# Navigate to: http://localhost:8080 -> DAGs -> daily_etl -> Graph View -> Click failed task

# Review pipeline logs in database
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -c "
SELECT * FROM analytics._pipeline_log 
WHERE status = 'Failed' 
ORDER BY execution_date DESC 
LIMIT 10;
"

# Check data quality issues
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -c "
SELECT * FROM analytics._data_quality_log 
WHERE passed = false 
ORDER BY run_timestamp DESC 
LIMIT 10;
"
```

**Port conflicts:**
```bash
# Check what's using the ports
netstat -an | grep 8080  # Airflow
netstat -an | grep 3000  # Metabase
netstat -an | grep 5433  # PostgreSQL

# Change ports in docker-compose.yml if needed
```

**Out of memory:**
```bash
# Check Docker memory limits
docker stats

# Increase Docker Desktop memory allocation
# Settings -> Resources -> Memory
```

**Permission issues (Linux/Mac):**
```bash
# Fix Airflow directory permissions
sudo chown -R 50000:50000 ./airflow/dags
sudo chown -R 50000:50000 ./airflow/logs
```

## 📄 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request





