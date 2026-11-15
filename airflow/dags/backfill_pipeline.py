"""
Backfill Pipeline DAG
Enterprise Analytics Platform

This DAG handles historical data backfilling for:
- Initial data loads
- Schema changes requiring data migration
- Recovering from data issues
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.models.param import Param

import sys
sys.path.insert(0, '/opt/airflow')

from src.utils.logging_config import setup_logging

logger = setup_logging(level="INFO")

default_args = {
    'owner': 'data_engineering',
    'depends_on_past': False,
    'email': ['data-alerts@company.com'],
    'email_on_failure': True,
    'retries': 1,
    'retry_delay': timedelta(minutes=10),
    'execution_timeout': timedelta(hours=6),
}


def validate_backfill_params(**context):
    """Validate backfill parameters before processing."""
    params = context['params']
    
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    table_name = params.get('table_name', 'all')
    batch_size = params.get('batch_size', 10000)
    
    # Validate dates
    if start_date:
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Invalid start_date format: {start_date}. Use YYYY-MM-DD")
    
    if end_date:
        try:
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Invalid end_date format: {end_date}. Use YYYY-MM-DD")
    
    # Validate table name
    valid_tables = ['all', 'customers', 'transactions', 'sessions', 'support']
    if table_name not in valid_tables:
        raise ValueError(f"Invalid table_name: {table_name}. Must be one of {valid_tables}")
    
    logger.info(
        "Backfill parameters validated",
        start_date=start_date,
        end_date=end_date,
        table=table_name,
        batch_size=batch_size
    )
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'table_name': table_name,
        'batch_size': batch_size
    }


def backfill_transactions(**context):
    """Backfill transaction data."""
    import pandas as pd
    import os
    
    from src.utils.db_utils import DatabaseUtils
    from src.extractors import CSVExtractor
    from src.transformers import TransactionTransformer, TimezoneHandler
    
    params = context['params']
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    batch_size = params.get('batch_size', 10000)
    
    table_name = params.get('table_name', 'all')
    if table_name not in ['all', 'transactions']:
        logger.info("Skipping transactions backfill - not selected")
        return 0
    
    # Extract historical data
    extractor = CSVExtractor(
        file_path='/opt/airflow/data/sample/transactions_messy.csv',
        chunk_size=batch_size
    )
    
    df = extractor.run()
    
    # Filter by date range if specified
    if start_date or end_date:
        df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
        
        if start_date:
            df = df[df['transaction_date'] >= start_date]
        if end_date:
            df = df[df['transaction_date'] <= end_date]
    
    if df.empty:
        logger.info("No transactions to backfill")
        return 0
    
    # Transform
    tz_handler = TimezoneHandler(target_timezone='UTC')
    df = tz_handler.run(df)
    
    transformer = TransactionTransformer(base_currency='USD')
    df = transformer.run(df)
    
    # Load in batches
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        total_loaded = 0
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            rows = db.load_dataframe(
                batch,
                'fact_transactions_staging',
                schema='analytics',
                if_exists='append' if i > 0 else 'replace'
            )
            total_loaded += rows
            logger.info(f"Loaded batch {i//batch_size + 1}", rows=rows)
        
        logger.info("Transaction backfill complete", total_rows=total_loaded)
        return total_loaded
        
    finally:
        db.close()


def backfill_customers(**context):
    """Backfill customer dimension data."""
    import pandas as pd
    import os
    
    from src.utils.db_utils import DatabaseUtils
    from src.extractors import CSVExtractor
    from src.transformers import CustomerTransformer
    
    params = context['params']
    table_name = params.get('table_name', 'all')
    
    if table_name not in ['all', 'customers']:
        logger.info("Skipping customers backfill - not selected")
        return 0
    
    # Extract
    extractor = CSVExtractor(
        file_path='/opt/airflow/data/sample/customers_messy.csv'
    )
    df = extractor.run()
    
    # Transform
    transformer = CustomerTransformer(
        fuzzy_threshold=85,
        deduplicate=True
    )
    df = transformer.run(df)
    
    # Load
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        # Add SCD columns
        df['is_current'] = True
        df['version'] = 1
        df['effective_start_date'] = datetime.now()
        df['effective_end_date'] = pd.Timestamp('9999-12-31 23:59:59')
        
        rows = db.load_dataframe(
            df,
            'dim_customers',
            schema='analytics',
            if_exists='replace'
        )
        
        logger.info("Customer backfill complete", rows=rows)
        return rows
        
    finally:
        db.close()


def backfill_sessions(**context):
    """Backfill session data."""
    import pandas as pd
    import os
    
    from src.utils.db_utils import DatabaseUtils
    from src.extractors import CSVExtractor
    from src.transformers import SessionTransformer
    
    params = context['params']
    table_name = params.get('table_name', 'all')
    
    if table_name not in ['all', 'sessions']:
        logger.info("Skipping sessions backfill - not selected")
        return 0
    
    # Extract
    extractor = CSVExtractor(
        file_path='/opt/airflow/data/sample/sessions_messy.csv'
    )
    df = extractor.run()
    
    # Transform
    transformer = SessionTransformer(calculate_engagement_score=True)
    df = transformer.run(df)
    
    # Load
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        rows = db.load_dataframe(
            df,
            'fact_customer_sessions',
            schema='analytics',
            if_exists='replace'
        )
        
        logger.info("Session backfill complete", rows=rows)
        return rows
        
    finally:
        db.close()


def rebuild_aggregations(**context):
    """Rebuild all aggregated marts after backfill."""
    import os
    
    from src.utils.db_utils import DatabaseUtils
    
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        # Rebuild daily revenue
        db.execute_query("""
            TRUNCATE analytics.mart_daily_revenue;
            
            INSERT INTO analytics.mart_daily_revenue (
                date_key, full_date, total_revenue, total_transactions, 
                total_quantity, unique_customers
            )
            SELECT 
                dt.date_key,
                dt.full_date,
                COALESCE(SUM(ft.total_amount_usd), 0),
                COUNT(ft.transaction_sk),
                COALESCE(SUM(ft.quantity), 0),
                COUNT(DISTINCT ft.customer_sk)
            FROM analytics.dim_time dt
            LEFT JOIN analytics.fact_transactions ft ON dt.date_key = ft.date_key
            WHERE dt.full_date <= CURRENT_DATE
            GROUP BY dt.date_key, dt.full_date;
        """)
        
        logger.info("Aggregations rebuilt")
        
    except Exception as e:
        logger.error("Failed to rebuild aggregations", error=str(e))
        raise
    finally:
        db.close()


def log_backfill_completion(**context):
    """Log backfill completion and statistics."""
    import os
    
    from src.utils.db_utils import DatabaseUtils
    
    params = context['params']
    ti = context['ti']
    
    stats = {
        'customers': ti.xcom_pull(task_ids='backfill_customers') or 0,
        'transactions': ti.xcom_pull(task_ids='backfill_transactions') or 0,
        'sessions': ti.xcom_pull(task_ids='backfill_sessions') or 0,
    }
    
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        db.execute_query("""
            INSERT INTO analytics._pipeline_log (
                dag_id, dag_run_id, task_id, execution_date,
                start_time, end_time, status, rows_processed
            ) VALUES (
                'backfill_pipeline', :run_id, 'backfill_complete', :exec_date,
                :start_time, CURRENT_TIMESTAMP, 'success', :rows
            )
        """, {
            'run_id': context['run_id'],
            'exec_date': context['execution_date'],
            'start_time': context['execution_date'],
            'rows': sum(stats.values())
        })
        
    except Exception:
        pass
    finally:
        db.close()
    
    logger.info("Backfill complete", stats=stats)


# Create the DAG
with DAG(
    dag_id='backfill_pipeline',
    default_args=default_args,
    description='Historical data backfill pipeline',
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['backfill', 'manual', 'migration'],
    params={
        'start_date': Param(
            default=None,
            type=['null', 'string'],
            description='Start date for backfill (YYYY-MM-DD)'
        ),
        'end_date': Param(
            default=None,
            type=['null', 'string'],
            description='End date for backfill (YYYY-MM-DD)'
        ),
        'table_name': Param(
            default='all',
            enum=['all', 'customers', 'transactions', 'sessions', 'support'],
            description='Table to backfill'
        ),
        'batch_size': Param(
            default=10000,
            type='integer',
            minimum=1000,
            maximum=100000,
            description='Batch size for loading'
        ),
    },
) as dag:
    
    start = EmptyOperator(task_id='start')
    
    validate = PythonOperator(
        task_id='validate_params',
        python_callable=validate_backfill_params,
    )
    
    customers = PythonOperator(
        task_id='backfill_customers',
        python_callable=backfill_customers,
    )
    
    transactions = PythonOperator(
        task_id='backfill_transactions',
        python_callable=backfill_transactions,
    )
    
    sessions = PythonOperator(
        task_id='backfill_sessions',
        python_callable=backfill_sessions,
    )
    
    aggregations = PythonOperator(
        task_id='rebuild_aggregations',
        python_callable=rebuild_aggregations,
    )
    
    complete = PythonOperator(
        task_id='log_completion',
        python_callable=log_backfill_completion,
    )
    
    end = EmptyOperator(task_id='end')
    
    start >> validate >> [customers, transactions, sessions] >> aggregations >> complete >> end

