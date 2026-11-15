"""
Operational Dashboard - Pipeline Health & Data Quality
Enterprise Analytics Platform
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine

# Page configuration
st.set_page_config(
    page_title="Operational Dashboard",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .status-healthy {
        background-color: #10B981;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
    }
    .status-warning {
        background-color: #F59E0B;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
    }
    .status-error {
        background-color: #EF4444;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db_connection():
    """Create database connection."""
    connection_string = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'analytics_user')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'analytics_password')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5433')}/"
        f"{os.getenv('POSTGRES_DB', 'analytics_warehouse')}"
    )
    return create_engine(connection_string)


@st.cache_data(ttl=60)
def get_pipeline_health(days=7):
    """Get pipeline health metrics."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        dag_id,
        COUNT(*) as total_runs,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
        AVG(duration_seconds) as avg_duration,
        MAX(end_time) as last_run
    FROM analytics._pipeline_log
    WHERE start_time >= CURRENT_DATE - INTERVAL :days || ' days'
    GROUP BY dag_id
    """
    
    try:
        return pd.read_sql(query, engine, params={'days': str(days)})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_pipeline_history(days=7):
    """Get pipeline execution history."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        dag_id,
        dag_run_id,
        start_time,
        end_time,
        duration_seconds,
        status,
        rows_processed,
        error_message
    FROM analytics._pipeline_log
    WHERE start_time >= CURRENT_DATE - INTERVAL :days || ' days'
    ORDER BY start_time DESC
    LIMIT 100
    """
    
    try:
        return pd.read_sql(query, engine, params={'days': str(days)})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_data_quality_summary(days=7):
    """Get data quality check summary."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        dataset_name,
        COUNT(*) as total_checks,
        SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed,
        SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) as failed,
        MAX(run_timestamp) as last_check
    FROM analytics._data_quality_log
    WHERE run_timestamp >= CURRENT_DATE - INTERVAL :days || ' days'
    GROUP BY dataset_name
    """
    
    try:
        return pd.read_sql(query, engine, params={'days': str(days)})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_dq_issues(days=7):
    """Get recent data quality issues."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        run_timestamp,
        dataset_name,
        check_name,
        severity,
        message,
        affected_rows
    FROM analytics._data_quality_log
    WHERE NOT passed
    AND run_timestamp >= CURRENT_DATE - INTERVAL :days || ' days'
    ORDER BY run_timestamp DESC
    LIMIT 50
    """
    
    try:
        return pd.read_sql(query, engine, params={'days': str(days)})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_data_freshness():
    """Check data freshness for key tables."""
    engine = get_db_connection()
    
    tables = [
        ('fact_transactions', '_loaded_at'),
        ('fact_customer_sessions', '_loaded_at'),
        ('dim_customers', 'updated_at'),
        ('dim_products', 'updated_at')
    ]
    
    results = []
    for table, timestamp_col in tables:
        query = f"""
        SELECT 
            '{table}' as table_name,
            MAX({timestamp_col}) as last_updated,
            EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MAX({timestamp_col})) / 3600 as hours_old
        FROM analytics.{table}
        """
        try:
            df = pd.read_sql(query, engine)
            if not df.empty:
                results.append(df.iloc[0].to_dict())
        except Exception:
            results.append({'table_name': table, 'last_updated': None, 'hours_old': None})
    
    return pd.DataFrame(results)


def get_status_badge(status):
    """Get status badge HTML."""
    if status in ['success', 'healthy', 'fresh']:
        return '<span class="status-healthy">✓ Healthy</span>'
    elif status in ['warning', 'at_risk']:
        return '<span class="status-warning">⚠ Warning</span>'
    else:
        return '<span class="status-error">✗ Error</span>'


def calculate_health_score(df):
    """Calculate overall health score."""
    if df.empty:
        return 0
    
    total_runs = df['total_runs'].sum()
    successful_runs = df['successful'].sum()
    
    if total_runs == 0:
        return 100
    
    return round(successful_runs / total_runs * 100, 1)


def main():
    st.title("⚙️ Operational Dashboard")
    st.markdown("Pipeline Health & Data Quality Monitoring")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        
        lookback_days = st.selectbox(
            "Lookback Period",
            [1, 7, 14, 30],
            index=1,
            format_func=lambda x: f"{x} day{'s' if x > 1 else ''}"
        )
        
        auto_refresh = st.checkbox("Auto Refresh (60s)", value=False)
        
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        st.markdown(f"**Last Updated:** {datetime.now().strftime('%H:%M:%S')}")
    
    # Health Score Cards
    pipeline_health = get_pipeline_health(lookback_days)
    dq_summary = get_data_quality_summary(lookback_days)
    
    pipeline_score = calculate_health_score(pipeline_health)
    dq_score = 100 if dq_summary.empty else round(
        dq_summary['passed'].sum() / max(dq_summary['total_checks'].sum(), 1) * 100, 1
    )
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Pipeline Health Score",
            value=f"{pipeline_score}%",
            delta=None
        )
        if pipeline_score >= 95:
            st.success("All systems operational")
        elif pipeline_score >= 80:
            st.warning("Some issues detected")
        else:
            st.error("Critical issues")
    
    with col2:
        st.metric(
            label="Data Quality Score",
            value=f"{dq_score}%",
            delta=None
        )
        if dq_score >= 95:
            st.success("Data quality good")
        elif dq_score >= 80:
            st.warning("Quality degraded")
        else:
            st.error("Quality issues")
    
    with col3:
        total_runs = pipeline_health['total_runs'].sum() if not pipeline_health.empty else 0
        st.metric(
            label="Total Pipeline Runs",
            value=f"{total_runs:,}",
            delta=f"Last {lookback_days} days"
        )
    
    with col4:
        failed_runs = pipeline_health['failed'].sum() if not pipeline_health.empty else 0
        st.metric(
            label="Failed Runs",
            value=f"{failed_runs:,}",
            delta=None
        )
        if failed_runs > 0:
            st.error(f"{failed_runs} failures need attention")
    
    st.markdown("---")
    
    # Pipeline Status
    st.subheader("🔄 Pipeline Status")
    
    if not pipeline_health.empty:
        pipeline_health['success_rate'] = (
            pipeline_health['successful'] / pipeline_health['total_runs'] * 100
        ).round(1)
        pipeline_health['avg_duration'] = pipeline_health['avg_duration'].round(0)
        
        # Pipeline health table
        st.dataframe(
            pipeline_health[['dag_id', 'total_runs', 'successful', 'failed', 'success_rate', 'avg_duration', 'last_run']].rename(
                columns={
                    'dag_id': 'Pipeline',
                    'total_runs': 'Total Runs',
                    'successful': 'Successful',
                    'failed': 'Failed',
                    'success_rate': 'Success Rate (%)',
                    'avg_duration': 'Avg Duration (s)',
                    'last_run': 'Last Run'
                }
            ),
            use_container_width=True,
            hide_index=True
        )
        
        # Pipeline duration trend
        history = get_pipeline_history(lookback_days)
        if not history.empty and 'duration_seconds' in history.columns:
            fig = px.line(
                history[history['status'] == 'success'].sort_values('start_time'),
                x='start_time',
                y='duration_seconds',
                color='dag_id',
                title='Pipeline Duration Trend'
            )
            fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Duration (seconds)",
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No pipeline execution data available")
    
    st.markdown("---")
    
    # Data Quality
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("✅ Data Quality Summary")
        
        if not dq_summary.empty:
            dq_summary['pass_rate'] = (
                dq_summary['passed'] / dq_summary['total_checks'] * 100
            ).round(1)
            
            fig = px.bar(
                dq_summary,
                x='dataset_name',
                y=['passed', 'failed'],
                barmode='stack',
                color_discrete_map={'passed': '#10B981', 'failed': '#EF4444'},
                title='Data Quality Checks by Dataset'
            )
            fig.update_layout(
                xaxis_title="Dataset",
                yaxis_title="Check Count",
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data quality checks recorded")
    
    with col2:
        st.subheader("🕐 Data Freshness")
        
        freshness = get_data_freshness()
        
        if not freshness.empty:
            freshness['status'] = freshness['hours_old'].apply(
                lambda x: 'Fresh' if x and x < 24 else ('Stale' if x else 'Unknown')
            )
            freshness['hours_old'] = freshness['hours_old'].apply(
                lambda x: f"{x:.1f}h" if x else "N/A"
            )
            
            st.dataframe(
                freshness[['table_name', 'last_updated', 'hours_old', 'status']].rename(
                    columns={
                        'table_name': 'Table',
                        'last_updated': 'Last Updated',
                        'hours_old': 'Age',
                        'status': 'Status'
                    }
                ),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No freshness data available")
    
    # Recent Issues
    st.subheader("⚠️ Recent Data Quality Issues")
    
    issues = get_dq_issues(lookback_days)
    
    if not issues.empty:
        st.dataframe(
            issues.rename(columns={
                'run_timestamp': 'Timestamp',
                'dataset_name': 'Dataset',
                'check_name': 'Check',
                'severity': 'Severity',
                'message': 'Message',
                'affected_rows': 'Affected Rows'
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.success("No data quality issues in the selected period! 🎉")
    
    # Recent Pipeline Runs
    st.subheader("📜 Recent Pipeline Runs")
    
    history = get_pipeline_history(lookback_days)
    
    if not history.empty:
        st.dataframe(
            history[['dag_id', 'start_time', 'end_time', 'duration_seconds', 'status', 'rows_processed']].rename(
                columns={
                    'dag_id': 'Pipeline',
                    'start_time': 'Start Time',
                    'end_time': 'End Time',
                    'duration_seconds': 'Duration (s)',
                    'status': 'Status',
                    'rows_processed': 'Rows'
                }
            ).head(20),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No recent pipeline runs")
    
    # Auto refresh
    if auto_refresh:
        import time
        time.sleep(60)
        st.rerun()


if __name__ == "__main__":
    main()

