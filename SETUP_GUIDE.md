# Enterprise Analytics Platform - Complete Setup & Implementation Guide

## 📋 Overview

This is an **Enterprise Analytics Platform** - a complete end-to-end data analytics system for processing customer behavior data, transactions, and support interactions. It includes:

- **ETL Pipeline**: Apache Airflow-based data extraction, transformation, and loading
- **Data Warehouse**: PostgreSQL with dimensional modeling (star schema)
- **Dashboards**: Metabase (BI) and Streamlit (operational dashboards)
- **Data Quality Framework**: Comprehensive validation and monitoring

---

## 🛠️ Required Tools & Software

### 1. **Docker Desktop** (REQUIRED)
   - **Download**: https://www.docker.com/products/docker-desktop/
   - **Version**: 2.0 or higher
   - **Why**: All services run in Docker containers
   - **System Requirements**: 
     - Windows 10/11 Pro, Enterprise, or Education (64-bit)
     - WSL 2 enabled (Docker Desktop will prompt you)
     - 8GB+ RAM (recommended: 16GB)
     - 20GB+ free disk space

### 2. **Python 3.11+** (For Local Development - OPTIONAL)
   - **Download**: https://www.python.org/downloads/
   - **Why**: For running tests, development, and local execution
   - **Note**: If using Docker only, Python is not strictly required

### 3. **Git** (Already installed on Windows)
   - **Verify**: Run `git --version` in PowerShell
   - **Download**: https://git-scm.com/download/win (if needed)

### 4. **Code Editor** (Recommended)
   - **VS Code**: https://code.visualstudio.com/
   - **PyCharm**: https://www.jetbrains.com/pycharm/ (optional)

---

## 📦 Step-by-Step Setup Instructions

### Step 1: Install Docker Desktop

1. Download Docker Desktop from the official website
2. Run the installer and follow the setup wizard
3. **IMPORTANT**: Enable WSL 2 backend when prompted (required for Windows)
4. Restart your computer if required
5. Start Docker Desktop and wait for it to fully start (whale icon in system tray)
6. Verify installation:
   ```powershell
   docker --version
   docker-compose --version
   ```

### Step 2: Clone/Setup the Repository

Since you already have the repository, you can skip this step. If you need to set it up fresh:

```powershell
# Navigate to your desired directory
cd C:\Users\KIRAN

# If cloning from GitHub (optional):
# git clone https://github.com/roonion/Enterprise_Analytics_Platform.git
# cd Enterprise_Analytics_Platform
```

### Step 3: Create Environment File

1. Copy the example environment file:
   ```powershell
   Copy-Item env.example .env
   ```

2. **Note**: For Docker Compose, the environment variables are already configured in `docker-compose.yml`. The `.env` file is mainly for local development.

### Step 4: Verify Directory Structure

Ensure you have these directories (create if missing):

```powershell
# Create data directory if it doesn't exist
New-Item -ItemType Directory -Force -Path "data\sample"
```

**Important directories:**
- `airflow/dags/` - Airflow DAG definitions
- `src/` - Python source code (extractors, transformers, validators)
- `sql/ddl/` - Database schema definitions
- `sql/transforms/` - SQL transformation queries
- `sql/analysis/` - Analytical queries
- `dashboards/streamlit/` - Streamlit dashboard apps
- `data/sample/` - Sample data files (will be generated)

### Step 5: Start All Services with Docker

This is the **main command** to run everything:

```powershell
# Navigate to the project directory
cd C:\Users\KIRAN\Enterprise_Analytics_Platform

# Start all services in detached mode

```

**First run will:**
- Download Docker images (PostgreSQL, Airflow, Metabase)
- Build custom images (Airflow and Streamlit)
- Initialize databases
- Set up Airflow metadata
- **This can take 5-10 minutes on first run**

### Step 6: Monitor Startup

Check if services are starting properly:

```powershell
# Check service status
docker-compose ps

# View logs (all services)
docker-compose logs -f

# View specific service logs
docker-compose logs -f airflow-webserver
docker-compose logs -f airflow-scheduler
docker-compose logs -f analytics-db
```

**Wait for:**
- `analytics-db`: "database system is ready to accept connections"
- `airflow-webserver`: "Booting worker" message
- `airflow-scheduler`: Health check passing
- All services show "healthy" status

### Step 7: Access the Applications

Once all services are running, access them via web browser:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Airflow UI** | http://localhost:8080 | Username: `airflow`<br>Password: `airflow` |
| **Metabase** | http://localhost:3000 | Setup wizard on first access |
| **Streamlit Dashboard** | http://localhost:8501 | No authentication |

**Note**: It may take 2-3 minutes after `docker-compose up` for services to be fully ready.

---

## 🗄️ Database Initialization

The database schema should be automatically initialized via the SQL scripts in `sql/ddl/`. However, if you need to manually run them:

```powershell
# Connect to the analytics database
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse

# Or run scripts directly:
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/01_dim_tables.sql
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/02_fact_tables.sql
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/03_aggregated_marts.sql
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -f /docker-entrypoint-initdb.d/04_indexes.sql
```

---

## 🧪 Generate Sample Data

Before running ETL pipelines, you need sample data:

```powershell
# Generate sample data using the data generator
docker-compose exec airflow-webserver python -c "
from src.utils.data_generator import DataGenerator
import os
os.makedirs('/opt/airflow/data/sample', exist_ok=True)
gen = DataGenerator()
gen.generate_customers(1000).to_csv('/opt/airflow/data/sample/customers_messy.csv', index=False)
gen.generate_transactions(5000).to_csv('/opt/airflow/data/sample/transactions_messy.csv', index=False)
gen.generate_sessions(3000).to_csv('/opt/airflow/data/sample/sessions_messy.csv', index=False)
print('Sample data generated successfully!')
"
```

---

## 🚀 Running the ETL Pipeline

### Option 1: Using Airflow UI (Recommended)

1. Go to http://localhost:8080
2. Login with `airflow` / `airflow`
3. Find the `daily_etl` DAG in the list
4. Toggle it ON (if paused)
5. Click the "Play" button (▶️) to trigger it
6. Click on the DAG name to view the graph
7. Monitor task execution in real-time

### Option 2: Using Command Line

```powershell
# Trigger the daily ETL DAG
docker-compose exec airflow-webserver airflow dags trigger daily_etl

# List all DAGs
docker-compose exec airflow-webserver airflow dags list

# Check DAG status
docker-compose exec airflow-webserver airflow dags state daily_etl
```

---

## 🔍 Verify Data Load

Check if data was loaded into the warehouse:

```powershell
# Connect to database and check counts
docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -c "
SELECT 
    'dim_customers' as table_name, 
    COUNT(*) as row_count 
FROM analytics.dim_customers
UNION ALL
SELECT 
    'fact_transactions', 
    COUNT(*) 
FROM analytics.fact_transactions;
"
```

---

## 🧪 Running Tests (Optional - Local Development)

If you want to run tests locally (not in Docker):

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# If you get execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_transformers.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

---

## 📊 Using the Dashboards

### Metabase Setup (First Time)

1. Go to http://localhost:3000
2. Complete the setup wizard:
   - Enter your email and create admin account
   - Choose "I'll add my data later" (skip adding database for now)
   - You can connect to the analytics database later if needed

### Streamlit Dashboards

1. Go to http://localhost:8501
2. You'll see the Executive Dashboard
3. Navigate between dashboards using the sidebar (if multiple apps)

---

## 🛑 Stopping Services

```powershell
# Stop all services (keeps data)
docker-compose stop

# Stop and remove containers (keeps volumes/data)
docker-compose down

# Stop and remove everything including volumes (⚠️ DELETES DATA)
docker-compose down -v
```

---

## 🐛 Troubleshooting

### Issue: Docker Desktop not starting
- **Solution**: Ensure WSL 2 is enabled and updated
- Run: `wsl --update` in PowerShell
- Restart Docker Desktop

### Issue: Port already in use
```powershell
# Check what's using the ports
netstat -ano | findstr :8080  # Airflow
netstat -ano | findstr :3000  # Metabase
netstat -ano | findstr :5433  # PostgreSQL
```
- **Solution**: Stop the conflicting service or change ports in `docker-compose.yml`

### Issue: Out of memory
- **Solution**: Increase Docker Desktop memory limit
- Docker Desktop → Settings → Resources → Memory → Increase to 8GB+

### Issue: Airflow not loading DAGs
```powershell
# Check DAG parsing errors
docker-compose logs airflow-scheduler | Select-String -Pattern "ERROR"

# Check if DAGs folder is mounted correctly
docker-compose exec airflow-webserver ls -la /opt/airflow/dags
```

### Issue: Database connection errors
```powershell
# Verify database is healthy
docker-compose ps analytics-db

# Check database logs
docker-compose logs analytics-db

# Test connection
docker-compose exec analytics-db pg_isready -U analytics_user
```

### Issue: Services won't start
```powershell
# View detailed logs
docker-compose logs

# Rebuild images
docker-compose build --no-cache

# Start fresh (⚠️ deletes data)
docker-compose down -v
docker-compose up -d
```

---

## 📁 Important File Locations

- **Docker Configuration**: `docker-compose.yml`
- **Airflow DAGs**: `airflow/dags/`
- **SQL Schemas**: `sql/ddl/`
- **Python Code**: `src/`
- **Dashboards**: `dashboards/streamlit/`
- **Environment Variables**: `.env` (create from `env.example`)

---

## 🎯 Quick Command Reference

```powershell
# Start everything
docker-compose up -d

# View logs
docker-compose logs -f [service-name]

# Stop everything
docker-compose stop

# Restart a specific service
docker-compose restart airflow-webserver

# Execute command in container
docker-compose exec airflow-webserver airflow dags list

# View container status
docker-compose ps

# Rebuild after code changes
docker-compose build airflow-webserver
docker-compose up -d airflow-webserver
```

---

## 🔐 Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| Airflow | `airflow` | `airflow` |
| PostgreSQL (Airflow DB) | `airflow` | `airflow` |
| PostgreSQL (Analytics) | `analytics_user` | `analytics_password` |
| Metabase | Setup on first access | - |

**⚠️ IMPORTANT**: Change these passwords in production!

---

## 📚 Next Steps

1. ✅ Ensure Docker Desktop is installed and running
2. ✅ Run `docker-compose up -d`
3. ✅ Wait for services to be healthy
4. ✅ Access Airflow UI at http://localhost:8080
5. ✅ Generate sample data
6. ✅ Trigger the `daily_etl` DAG
7. ✅ Explore dashboards at http://localhost:8501

---

## 💡 Tips

- **Development**: Mount volumes allow code changes without rebuilding images
- **Logs**: Use `docker-compose logs -f` to follow logs in real-time
- **Resource Usage**: Monitor with `docker stats`
- **Backup**: Database data is in Docker volumes - use `docker volume ls` to find them

---

## 🆘 Getting Help

If you encounter issues:
1. Check the logs: `docker-compose logs [service-name]`
2. Verify all prerequisites are installed
3. Ensure Docker Desktop is running
4. Check the troubleshooting section above
5. Review the README.md for additional details

