"""
Customer Data Pipeline DAG
Enterprise Analytics Platform

Specialized pipeline for customer dimension management with SCD Type 2 handling.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator

import sys
sys.path.insert(0, '/opt/airflow')

from src.utils.logging_config import setup_logging

logger = setup_logging(level="INFO")

default_args = {
    'owner': 'data_engineering',
    'depends_on_past': False,
    'email': ['data-alerts@company.com'],
    'email_on_failure': True,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}


def extract_customer_updates(**context):
    """Extract new and updated customer records."""
    import pandas as pd
    import os
    
    from src.utils.db_utils import DatabaseUtils
    from src.extractors import CSVExtractor
    
    # Get last watermark
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        # Get watermark
        result = db.execute_query("""
            SELECT watermark_value 
            FROM analytics._watermarks 
            WHERE table_name = 'customers'
        """)
        
        last_watermark = result[0]['watermark_value'] if result else None
        
        # Extract from source (simulate with CSV for now)
        extractor = CSVExtractor(
            file_path='/opt/airflow/data/sample/customers_messy.csv'
        )
        df = extractor.run()
        
        # Filter by watermark if exists
        if last_watermark and 'updated_at' in df.columns:
            df['updated_at'] = pd.to_datetime(df['updated_at'])
            df = df[df['updated_at'] > last_watermark]
        
        context['ti'].xcom_push(key='customer_updates', value=df.to_json())
        context['ti'].xcom_push(key='update_count', value=len(df))
        
        logger.info("Customer updates extracted", count=len(df))
        return len(df)
        
    finally:
        db.close()


def transform_customers(**context):
    """Transform customer data with deduplication."""
    import pandas as pd
    
    from src.transformers import CustomerTransformer
    
    ti = context['ti']
    customer_json = ti.xcom_pull(key='customer_updates', task_ids='extract_customer_updates')
    
    if not customer_json:
        logger.info("No customer updates to transform")
        return 0
    
    df = pd.read_json(customer_json)
    
    transformer = CustomerTransformer(
        fuzzy_threshold=85,
        deduplicate=True,
        mask_pii=False  # Set True for dev environments
    )
    
    transformed_df = transformer.run(df)
    
    ti.xcom_push(key='transformed_customers', value=transformed_df.to_json())
    ti.xcom_push(key='transformed_count', value=len(transformed_df))
    
    logger.info(
        "Customer transformation complete",
        input=len(df),
        output=len(transformed_df),
        duplicates_removed=len(df) - len(transformed_df)
    )
    
    return len(transformed_df)


def apply_scd_type2(**context):
    """Apply SCD Type 2 logic to customer dimension."""
    import pandas as pd
    import os
    from datetime import datetime
    
    from src.utils.db_utils import DatabaseUtils
    
    ti = context['ti']
    customer_json = ti.xcom_pull(key='transformed_customers', task_ids='transform_customers')
    
    if not customer_json:
        logger.info("No customers to process for SCD")
        return 0
    
    source_df = pd.read_json(customer_json)
    
    db = DatabaseUtils(
        host=os.getenv('POSTGRES_HOST', 'analytics-db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'analytics_warehouse'),
        user=os.getenv('POSTGRES_USER', 'analytics_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'analytics_password')
    )
    
    try:
        # Get current customer records
        if 'customer_id' not in source_df.columns:
            logger.error("customer_id column not found")
            return 0
        
        customer_ids = source_df['customer_id'].tolist()
        
        if not customer_ids:
            return 0
        
        # Get existing current records
        existing_df = db.execute_query_df(f"""
            SELECT customer_sk, customer_id, email, phone, address, customer_segment
            FROM analytics.dim_customers
            WHERE is_current = TRUE
            AND customer_id IN ({','.join([f"'{c}'" for c in customer_ids])})
        """)
        
        # Compare and identify changes
        inserts = []
        updates = []
        
        for _, source_row in source_df.iterrows():
            customer_id = source_row['customer_id']
            existing_row = existing_df[existing_df['customer_id'] == customer_id]
            
            if existing_row.empty:
                # New customer - insert
                inserts.append(source_row)
            else:
                # Check for changes in tracked columns
                existing = existing_row.iloc[0]
                changed = False
                
                for col in ['email', 'phone', 'address', 'customer_segment']:
                    if col in source_row and col in existing:
                        if str(source_row.get(col, '')) != str(existing.get(col, '')):
                            changed = True
                            break
                
                if changed:
                    updates.append({
                        'old_sk': existing['customer_sk'],
                        'new_data': source_row
                    })
        
        # Process updates (close old record, insert new)
        now = datetime.now()
        
        for update in updates:
            # Close the old record
            db.execute_query(f"""
                UPDATE analytics.dim_customers
                SET effective_end_date = :end_date,
                    is_current = FALSE,
                    updated_at = :updated_at
                WHERE customer_sk = :sk
            """, {
                'end_date': now,
                'updated_at': now,
                'sk': update['old_sk']
            })
        
        # Insert new records (both new customers and new versions)
        new_records = []
        for row in inserts:
            new_records.append(row.to_dict())
        
        for update in updates:
            record = update['new_data'].to_dict()
            # Get new version number
            record['version'] = db.execute_query(f"""
                SELECT COALESCE(MAX(version), 0) + 1 as next_version
                FROM analytics.dim_customers
                WHERE customer_id = :customer_id
            """, {'customer_id': record['customer_id']})[0]['next_version']
            new_records.append(record)
        
        if new_records:
            new_df = pd.DataFrame(new_records)
            new_df['is_current'] = True
            new_df['effective_start_date'] = now
            new_df['effective_end_date'] = pd.Timestamp('9999-12-31 23:59:59')
            
            db.load_dataframe(
                new_df,
                'dim_customers',
                schema='analytics',
                if_exists='append'
            )
        
        # Update watermark
        db.execute_query("""
            INSERT INTO analytics._watermarks (table_name, watermark_column, watermark_value, updated_at)
            VALUES ('customers', 'updated_at', :watermark, :updated_at)
            ON CONFLICT (table_name)
            DO UPDATE SET watermark_value = :watermark, updated_at = :updated_at
        """, {'watermark': now, 'updated_at': now})
        
        logger.info(
            "SCD Type 2 applied",
            new_customers=len(inserts),
            updated_customers=len(updates)
        )
        
        return len(inserts) + len(updates)
        
    finally:
        db.close()


def update_customer_metrics(**context):
    """Update customer-related metrics after dimension update."""
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
        # Recalculate CLV for updated customers
        db.execute_query("""
            -- Update customer lifetime value calculations
            INSERT INTO analytics.mart_customer_lifetime_value (
                customer_sk,
                customer_id,
                total_lifetime_revenue,
                total_orders,
                first_order_date,
                last_order_date,
                calculated_at
            )
            SELECT 
                dc.customer_sk,
                dc.customer_id,
                COALESCE(SUM(ft.total_amount_usd), 0),
                COUNT(ft.transaction_sk),
                MIN(ft.transaction_timestamp)::DATE,
                MAX(ft.transaction_timestamp)::DATE,
                CURRENT_TIMESTAMP
            FROM analytics.dim_customers dc
            LEFT JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
            WHERE dc.is_current = TRUE
            GROUP BY dc.customer_sk, dc.customer_id
            ON CONFLICT (customer_sk)
            DO UPDATE SET
                total_lifetime_revenue = EXCLUDED.total_lifetime_revenue,
                total_orders = EXCLUDED.total_orders,
                last_order_date = EXCLUDED.last_order_date,
                calculated_at = EXCLUDED.calculated_at;
        """)
        
        logger.info("Customer metrics updated")
        
    except Exception as e:
        logger.warning("Failed to update customer metrics", error=str(e))
    finally:
        db.close()


# Create the DAG
with DAG(
    dag_id='customer_pipeline',
    default_args=default_args,
    description='Customer dimension pipeline with SCD Type 2',
    schedule_interval='0 7 * * *',  # Run at 7 AM UTC daily (after main ETL)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['customer', 'dimension', 'scd'],
    max_active_runs=1,
) as dag:
    
    start = EmptyOperator(task_id='start')
    
    extract = PythonOperator(
        task_id='extract_customer_updates',
        python_callable=extract_customer_updates,
    )
    
    transform = PythonOperator(
        task_id='transform_customers',
        python_callable=transform_customers,
    )
    
    scd = PythonOperator(
        task_id='apply_scd_type2',
        python_callable=apply_scd_type2,
    )
    
    metrics = PythonOperator(
        task_id='update_customer_metrics',
        python_callable=update_customer_metrics,
    )
    
    end = EmptyOperator(task_id='end')
    
    start >> extract >> transform >> scd >> metrics >> end

