"""
Daily ETL Pipeline DAG
Enterprise Analytics Platform

This DAG orchestrates the daily ETL process:
1. Extract data from various sources
2. Validate data quality
3. Transform and normalize data
4. Load into the data warehouse
5. Generate metrics and aggregations
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.utils.trigger_rule import TriggerRule

# Import custom modules
import sys
sys.path.insert(0, '/opt/airflow')

from src.extractors import CSVExtractor, JSONExtractor, DatabaseExtractor
from src.transformers import (
    CustomerTransformer,
    TransactionTransformer,
    SessionTransformer,
    TimezoneHandler
)
from src.validators import DataQualityValidator, SchemaValidator
from src.utils.db_utils import DatabaseUtils
from src.utils.logging_config import setup_logging

# Setup logging
logger = setup_logging(level="INFO")

# Default arguments
default_args = {
    'owner': 'data_engineering',
    'depends_on_past': False,
    'email': ['data-alerts@company.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# DAG configuration
DAG_CONFIG = {
    'data_path': '/opt/airflow/data/sample',
    'postgres_conn_id': 'analytics_warehouse',
}


def extract_customer_data(**context):
    """Extract customer data from CSV files."""
    data_path = Path(DAG_CONFIG['data_path'])
    
    extractor = CSVExtractor(
        file_path=data_path / 'customers_messy.csv',
        encoding='utf-8'
    )
    
    df = extractor.run()
    
    # Store in XCom for downstream tasks
    context['ti'].xcom_push(key='customer_data', value=df.to_json())
    context['ti'].xcom_push(key='customer_rows', value=len(df))
    
    logger.info("Customer extraction complete", rows=len(df))
    return len(df)


def extract_transaction_data(**context):
    """Extract transaction data from CSV files."""
    data_path = Path(DAG_CONFIG['data_path'])
    
    extractor = CSVExtractor(
        file_path=data_path / 'transactions_messy.csv',
        encoding='utf-8'
    )
    
    df = extractor.run()
    
    context['ti'].xcom_push(key='transaction_data', value=df.to_json())
    context['ti'].xcom_push(key='transaction_rows', value=len(df))
    
    logger.info("Transaction extraction complete", rows=len(df))
    return len(df)


def extract_session_data(**context):
    """Extract session data from CSV files."""
    data_path = Path(DAG_CONFIG['data_path'])
    
    extractor = CSVExtractor(
        file_path=data_path / 'sessions_messy.csv',
        encoding='utf-8'
    )
    
    df = extractor.run()
    
    context['ti'].xcom_push(key='session_data', value=df.to_json())
    context['ti'].xcom_push(key='session_rows', value=len(df))
    
    logger.info("Session extraction complete", rows=len(df))
    return len(df)


def extract_support_data(**context):
    """Extract support interaction data from CSV files."""
    data_path = Path(DAG_CONFIG['data_path'])
    
    extractor = CSVExtractor(
        file_path=data_path / 'support_interactions.csv',
        encoding='utf-8'
    )
    
    df = extractor.run()
    
    context['ti'].xcom_push(key='support_data', value=df.to_json())
    context['ti'].xcom_push(key='support_rows', value=len(df))
    
    logger.info("Support extraction complete", rows=len(df))
    return len(df)


def validate_data_quality(**context):
    """Validate data quality for all extracted datasets."""
    import pandas as pd
    
    ti = context['ti']
    validation_results = {}
    all_passed = True
    
    # Validate customer data
    customer_json = ti.xcom_pull(key='customer_data', task_ids='extract_customer_data')
    if customer_json:
        customer_df = pd.read_json(customer_json)
        
        validator = DataQualityValidator(
            dataset_name='customers',
            fail_on_error=False,
            null_threshold=0.1,
            duplicate_threshold=0.1
        )
        validator.check_column_exists(['customer_id', 'email'])
        validator.check_not_null(['customer_id'])
        
        report = validator.validate(customer_df)
        validation_results['customers'] = report.to_dict()
        
        if not report.is_valid:
            all_passed = False
    
    # Validate transaction data
    txn_json = ti.xcom_pull(key='transaction_data', task_ids='extract_transaction_data')
    if txn_json:
        txn_df = pd.read_json(txn_json)
        
        validator = DataQualityValidator(
            dataset_name='transactions',
            fail_on_error=False
        )
        validator.check_column_exists(['transaction_id', 'customer_id', 'total_amount'])
        validator.check_not_null(['transaction_id'])
        validator.check_range('total_amount', min_value=0)
        
        report = validator.validate(txn_df)
        validation_results['transactions'] = report.to_dict()
        
        if not report.is_valid:
            all_passed = False
    
    ti.xcom_push(key='validation_results', value=validation_results)
    ti.xcom_push(key='validation_passed', value=all_passed)
    
    logger.info("Data validation complete", passed=all_passed)
    return all_passed


def branch_on_validation(**context):
    """Branch based on validation results."""
    ti = context['ti']
    validation_passed = ti.xcom_pull(key='validation_passed', task_ids='validate_data_quality')
    
    if validation_passed:
        return 'transform_normalize'
    else:
        return 'handle_validation_failure'


def transform_normalize(**context):
    """Transform and normalize all datasets."""
    import pandas as pd
    
    ti = context['ti']
    transformed_data = {}
    
    # Transform customer data
    customer_json = ti.xcom_pull(key='customer_data', task_ids='extract_customer_data')
    if customer_json:
        customer_df = pd.read_json(customer_json)
        
        transformer = CustomerTransformer(
            fuzzy_threshold=85,
            deduplicate=True
        )
        transformed_customers = transformer.run(customer_df)
        transformed_data['customers'] = transformed_customers.to_json()
        
        logger.info(
            "Customer transformation complete",
            input_rows=len(customer_df),
            output_rows=len(transformed_customers)
        )
    
    # Transform transaction data
    txn_json = ti.xcom_pull(key='transaction_data', task_ids='extract_transaction_data')
    if txn_json:
        txn_df = pd.read_json(txn_json)
        
        # First normalize timezones
        tz_handler = TimezoneHandler(target_timezone='UTC')
        txn_df = tz_handler.run(txn_df)
        
        # Then transform transactions
        transformer = TransactionTransformer(
            base_currency='USD',
            validate_amounts=True
        )
        transformed_txn = transformer.run(txn_df)
        transformed_data['transactions'] = transformed_txn.to_json()
        
        logger.info(
            "Transaction transformation complete",
            input_rows=len(txn_df),
            output_rows=len(transformed_txn)
        )
    
    # Transform session data
    session_json = ti.xcom_pull(key='session_data', task_ids='extract_session_data')
    if session_json:
        session_df = pd.read_json(session_json)
        
        transformer = SessionTransformer(
            calculate_engagement_score=True
        )
        transformed_sessions = transformer.run(session_df)
        transformed_data['sessions'] = transformed_sessions.to_json()
        
        logger.info(
            "Session transformation complete",
            input_rows=len(session_df),
            output_rows=len(transformed_sessions)
        )
    
    ti.xcom_push(key='transformed_data', value=transformed_data)
    return True


def load_to_warehouse(**context):
    """Load transformed data into the data warehouse."""
    import pandas as pd
    import os
    
    ti = context['ti']
    transformed_data = ti.xcom_pull(key='transformed_data', task_ids='transform_normalize')
    
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    load_stats = {}
    
    try:
        # Load customers (with SCD Type 2 handling)
        if 'customers' in transformed_data:
            customer_df = pd.read_json(transformed_data['customers'])
            # For now, simple append (SCD logic would be more complex)
            rows = db.load_dataframe(
                customer_df,
                'dim_customers_staging',
                schema='analytics',
                if_exists='replace'
            )
            load_stats['customers'] = rows
        
        # Load transactions
        if 'transactions' in transformed_data:
            txn_df = pd.read_json(transformed_data['transactions'])
            rows = db.load_dataframe(
                txn_df,
                'fact_transactions_staging',
                schema='analytics',
                if_exists='replace'
            )
            load_stats['transactions'] = rows
        
        # Load sessions
        if 'sessions' in transformed_data:
            session_df = pd.read_json(transformed_data['sessions'])
            rows = db.load_dataframe(
                session_df,
                'fact_sessions_staging',
                schema='analytics',
                if_exists='replace'
            )
            load_stats['sessions'] = rows
        
        ti.xcom_push(key='load_stats', value=load_stats)
        logger.info("Data warehouse load complete", stats=load_stats)
        
    finally:
        db.close()
    
    return load_stats


def generate_metrics(**context):
    """Generate aggregated metrics and KPIs."""
    import os
    
    ti = context['ti']
    load_stats = ti.xcom_pull(key='load_stats', task_ids='load_to_warehouse')
    
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        # Refresh daily revenue mart
        db.execute_query("""
            INSERT INTO analytics.mart_daily_revenue (date_key, full_date, total_revenue, total_transactions)
            SELECT 
                dt.date_key,
                dt.full_date,
                COALESCE(SUM(ft.total_amount_usd), 0),
                COUNT(ft.transaction_sk)
            FROM analytics.dim_time dt
            LEFT JOIN analytics.fact_transactions ft ON dt.date_key = ft.date_key
            WHERE dt.full_date = CURRENT_DATE - INTERVAL '1 day'
            GROUP BY dt.date_key, dt.full_date
            ON CONFLICT (date_key) 
            DO UPDATE SET 
                total_revenue = EXCLUDED.total_revenue,
                total_transactions = EXCLUDED.total_transactions,
                calculated_at = CURRENT_TIMESTAMP;
        """)
        
        logger.info("Metrics generation complete")
        
    except Exception as e:
        logger.warning("Metrics generation failed", error=str(e))
    finally:
        db.close()
    
    return True


def handle_validation_failure(**context):
    """Handle validation failures - send alerts, log issues."""
    ti = context['ti']
    validation_results = ti.xcom_pull(key='validation_results', task_ids='validate_data_quality')
    
    logger.error("Data validation failed", results=validation_results)
    
    # In production, this would send alerts, create tickets, etc.
    # For now, just log the failure
    return False


# Create the DAG
with DAG(
    dag_id='daily_etl',
    default_args=default_args,
    description='Daily ETL pipeline for analytics warehouse',
    schedule_interval='0 6 * * *',  # Run at 6 AM UTC daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['etl', 'daily', 'analytics'],
    max_active_runs=1,
) as dag:
    
    # Start
    start = EmptyOperator(task_id='start')
    
    # Extraction tasks (parallel)
    extract_customers = PythonOperator(
        task_id='extract_customer_data',
        python_callable=extract_customer_data,
    )
    
    extract_transactions = PythonOperator(
        task_id='extract_transaction_data',
        python_callable=extract_transaction_data,
    )
    
    extract_sessions = PythonOperator(
        task_id='extract_session_data',
        python_callable=extract_session_data,
    )
    
    extract_support = PythonOperator(
        task_id='extract_support_data',
        python_callable=extract_support_data,
    )
    
    # Validation
    validate_quality = PythonOperator(
        task_id='validate_data_quality',
        python_callable=validate_data_quality,
    )
    
    # Branch based on validation
    validation_branch = BranchPythonOperator(
        task_id='validation_branch',
        python_callable=branch_on_validation,
    )
    
    # Handle validation failure
    handle_failure = PythonOperator(
        task_id='handle_validation_failure',
        python_callable=handle_validation_failure,
    )
    
    # Transform
    transform = PythonOperator(
        task_id='transform_normalize',
        python_callable=transform_normalize,
    )
    
    # Load
    load = PythonOperator(
        task_id='load_to_warehouse',
        python_callable=load_to_warehouse,
    )
    
    # Generate metrics
    metrics = PythonOperator(
        task_id='generate_metrics',
        python_callable=generate_metrics,
    )
    
    # End
    end = EmptyOperator(
        task_id='end',
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )
    
    # Define task dependencies
    start >> [extract_customers, extract_transactions, extract_sessions, extract_support]
    [extract_customers, extract_transactions, extract_sessions, extract_support] >> validate_quality
    validate_quality >> validation_branch
    validation_branch >> [transform, handle_failure]
    transform >> load >> metrics >> end
    handle_failure >> end

