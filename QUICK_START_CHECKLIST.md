# Quick Start Checklist

Use this checklist to quickly set up and run the Enterprise Analytics Platform.

## ✅ Prerequisites Checklist

- [ ] **Docker Desktop installed** (https://www.docker.com/products/docker-desktop/)
  - Version 2.0 or higher
  - WSL 2 enabled (Windows)
  - Docker Desktop is running
  
- [ ] **System Resources**
  - [ ] 8GB+ RAM available
  - [ ] 20GB+ free disk space
  - [ ] Ports 8080, 3000, 5433, 8501 available

- [ ] **Verify Docker Installation**
  ```powershell
  docker --version
  docker-compose --version
  ```

## ✅ Setup Steps

1. [ ] **Navigate to project directory**
   ```powershell
   cd C:\Users\KIRAN\Enterprise_Analytics_Platform
   ```

2. [ ] **Create environment file** (optional, mainly for local dev)
   ```powershell
   Copy-Item env.example .env
   ```

3. [ ] **Create data directory** (if missing)
   ```powershell
   New-Item -ItemType Directory -Force -Path "data\sample"
   ```

4. [ ] **Start all services**
   ```powershell
   docker-compose up -d
   ```
   ⏱️ Wait 5-10 minutes on first run (images download & build)

5. [ ] **Check service status**
   ```powershell
   docker-compose ps
   ```
   All services should show "healthy" or "running"

6. [ ] **Access Airflow UI**
   - URL: http://localhost:8080
   - Username: `airflow`
   - Password: `airflow`
   - ✅ Verify you can see the DAGs list

7. [ ] **Generate sample data**
   ```powershell
   docker-compose exec airflow-webserver python -c "from src.utils.data_generator import DataGenerator; import os; os.makedirs('/opt/airflow/data/sample', exist_ok=True); gen = DataGenerator(); gen.generate_customers(1000).to_csv('/opt/airflow/data/sample/customers_messy.csv', index=False); gen.generate_transactions(5000).to_csv('/opt/airflow/data/sample/transactions_messy.csv', index=False); print('Done!')"
   ```

8. [ ] **Trigger ETL Pipeline**
   - Go to Airflow UI: http://localhost:8080
   - Find `daily_etl` DAG
   - Toggle it ON (if paused)
   - Click "Play" button to trigger
   - Monitor execution

9. [ ] **Verify data loaded**
   ```powershell
   docker-compose exec analytics-db psql -U analytics_user -d analytics_warehouse -c "SELECT COUNT(*) FROM analytics.dim_customers;"
   ```

10. [ ] **Access Dashboards**
    - Streamlit: http://localhost:8501
    - Metabase: http://localhost:3000 (setup wizard on first access)

## 🎯 You're Done When...

- ✅ Docker Desktop is running
- ✅ All services show as healthy: `docker-compose ps`
- ✅ Airflow UI loads at http://localhost:8080
- ✅ DAGs are visible in Airflow
- ✅ Sample data files exist in `data/sample/`
- ✅ ETL pipeline runs successfully
- ✅ Streamlit dashboard loads at http://localhost:8501

## 🛑 Common First-Time Issues

**Problem**: Services won't start
- **Check**: Docker Desktop is running
- **Check**: WSL 2 is enabled
- **Check**: Ports are not in use

**Problem**: Airflow shows "No DAGs"
- **Wait**: DAGs take 1-2 minutes to parse
- **Check logs**: `docker-compose logs airflow-scheduler`

**Problem**: Out of memory
- **Solution**: Increase Docker Desktop memory to 8GB+

## 📞 Quick Commands

```powershell
# View all logs
docker-compose logs -f

# Stop all services
docker-compose stop

# Restart all services
docker-compose restart

# Stop and remove everything (⚠️ deletes data)
docker-compose down -v

# Check resource usage
docker stats
```

