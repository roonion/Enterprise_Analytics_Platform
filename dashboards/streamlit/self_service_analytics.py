"""
Self-Service Analytics - SQL Query Tool
Enterprise Analytics Platform
"""

import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# Page configuration
st.set_page_config(
    page_title="Self-Service Analytics",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)


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


# Predefined queries
SAVED_QUERIES = {
    "Daily Revenue Summary": """
SELECT 
    dt.full_date as date,
    SUM(ft.total_amount_usd) as revenue,
    COUNT(*) as transactions,
    COUNT(DISTINCT ft.customer_sk) as customers,
    AVG(ft.total_amount_usd) as avg_order_value
FROM analytics.fact_transactions ft
JOIN analytics.dim_time dt ON ft.date_key = dt.date_key
WHERE ft.status = 'Completed'
AND dt.full_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY dt.full_date
ORDER BY dt.full_date DESC
    """,
    
    "Customer Segment Analysis": """
SELECT 
    dc.customer_segment,
    COUNT(DISTINCT dc.customer_sk) as customer_count,
    SUM(ft.total_amount_usd) as total_revenue,
    AVG(ft.total_amount_usd) as avg_order_value,
    COUNT(ft.transaction_sk) as total_orders
FROM analytics.dim_customers dc
LEFT JOIN analytics.fact_transactions ft ON dc.customer_sk = ft.customer_sk
WHERE dc.is_current = TRUE
GROUP BY dc.customer_segment
ORDER BY total_revenue DESC
    """,
    
    "Top Products by Revenue": """
SELECT 
    dp.product_name,
    dp.category,
    dp.brand,
    SUM(ft.quantity) as units_sold,
    SUM(ft.total_amount_usd) as revenue,
    AVG(ft.total_amount_usd) as avg_price
FROM analytics.fact_transactions ft
JOIN analytics.dim_products dp ON ft.product_sk = dp.product_sk
WHERE ft.status = 'Completed'
AND dp.is_current = TRUE
GROUP BY dp.product_name, dp.category, dp.brand
ORDER BY revenue DESC
LIMIT 20
    """,
    
    "Channel Performance": """
SELECT 
    ch.channel_name,
    ch.channel_category,
    COUNT(*) as transactions,
    SUM(ft.total_amount_usd) as revenue,
    AVG(ft.total_amount_usd) as avg_order_value,
    COUNT(DISTINCT ft.customer_sk) as unique_customers
FROM analytics.fact_transactions ft
JOIN analytics.dim_channels ch ON ft.channel_sk = ch.channel_sk
WHERE ft.status = 'Completed'
GROUP BY ch.channel_name, ch.channel_category
ORDER BY revenue DESC
    """,
    
    "Session Engagement Analysis": """
SELECT 
    traffic_source,
    device_type,
    COUNT(*) as sessions,
    AVG(duration_seconds) as avg_duration,
    AVG(page_views) as avg_page_views,
    AVG(engagement_score) as avg_engagement,
    100.0 * SUM(CASE WHEN conversion THEN 1 ELSE 0 END) / COUNT(*) as conversion_rate
FROM analytics.fact_customer_sessions
WHERE session_start >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY traffic_source, device_type
ORDER BY sessions DESC
    """,
    
    "Monthly Cohort Retention": """
WITH cohorts AS (
    SELECT 
        customer_sk,
        DATE_TRUNC('month', MIN(transaction_timestamp))::DATE as cohort_month
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    GROUP BY customer_sk
)
SELECT 
    c.cohort_month,
    DATE_TRUNC('month', ft.transaction_timestamp)::DATE as activity_month,
    COUNT(DISTINCT c.customer_sk) as active_customers
FROM cohorts c
JOIN analytics.fact_transactions ft ON c.customer_sk = ft.customer_sk
WHERE ft.status = 'Completed'
GROUP BY c.cohort_month, DATE_TRUNC('month', ft.transaction_timestamp)
ORDER BY c.cohort_month, activity_month
LIMIT 100
    """
}


def execute_query(query: str, limit: int = 1000) -> pd.DataFrame:
    """Execute SQL query and return results."""
    engine = get_db_connection()
    
    # Add limit if not present
    query_lower = query.lower().strip()
    if 'limit' not in query_lower:
        query = f"{query.rstrip(';')}\nLIMIT {limit}"
    
    try:
        with engine.connect() as conn:
            result = pd.read_sql(text(query), conn)
        return result
    except Exception as e:
        st.error(f"Query Error: {str(e)}")
        return pd.DataFrame()


def detect_chart_type(df: pd.DataFrame) -> str:
    """Detect best chart type based on data."""
    if df.empty:
        return "table"
    
    # Check for date column
    date_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()]
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    
    if date_cols and numeric_cols:
        return "line"
    elif len(numeric_cols) >= 1 and len(df) <= 20:
        return "bar"
    else:
        return "table"


def create_visualization(df: pd.DataFrame, chart_type: str):
    """Create visualization based on chart type."""
    if df.empty:
        st.warning("No data to visualize")
        return
    
    if chart_type == "table":
        st.dataframe(df, use_container_width=True)
    
    elif chart_type == "line":
        # Find date and numeric columns
        date_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()]
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if date_cols and numeric_cols:
            x_col = st.selectbox("X-axis (Date)", date_cols)
            y_cols = st.multiselect("Y-axis (Metrics)", numeric_cols, default=[numeric_cols[0]])
            
            if y_cols:
                fig = px.line(df, x=x_col, y=y_cols)
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
    
    elif chart_type == "bar":
        cols = df.columns.tolist()
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        x_col = st.selectbox("X-axis", [c for c in cols if c not in numeric_cols] or cols)
        y_col = st.selectbox("Y-axis", numeric_cols or cols)
        
        fig = px.bar(df, x=x_col, y=y_col)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    elif chart_type == "pie":
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        other_cols = [c for c in df.columns if c not in numeric_cols]
        
        names_col = st.selectbox("Labels", other_cols or df.columns.tolist())
        values_col = st.selectbox("Values", numeric_cols or df.columns.tolist())
        
        fig = px.pie(df, names=names_col, values=values_col)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    elif chart_type == "scatter":
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if len(numeric_cols) >= 2:
            x_col = st.selectbox("X-axis", numeric_cols, index=0)
            y_col = st.selectbox("Y-axis", numeric_cols, index=min(1, len(numeric_cols)-1))
            
            fig = px.scatter(df, x=x_col, y=y_col)
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)


def main():
    st.title("🔍 Self-Service Analytics")
    st.markdown("Query the data warehouse with custom SQL or use pre-built queries")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("Saved Queries")
        
        selected_query = st.selectbox(
            "Select a query",
            ["Custom Query"] + list(SAVED_QUERIES.keys())
        )
        
        st.markdown("---")
        
        st.header("Settings")
        result_limit = st.number_input("Result Limit", 100, 10000, 1000, step=100)
        
        st.markdown("---")
        
        st.header("Available Tables")
        st.markdown("""
        **Fact Tables:**
        - `analytics.fact_transactions`
        - `analytics.fact_customer_sessions`
        - `analytics.fact_support_interactions`
        
        **Dimension Tables:**
        - `analytics.dim_customers`
        - `analytics.dim_products`
        - `analytics.dim_time`
        - `analytics.dim_channels`
        - `analytics.dim_payment_methods`
        - `analytics.dim_geography`
        
        **Marts:**
        - `analytics.mart_daily_revenue`
        - `analytics.mart_customer_lifetime_value`
        - `analytics.mart_product_performance`
        """)
    
    # Main content
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("SQL Query")
    
    with col2:
        if st.button("📋 Clear"):
            st.session_state['query'] = ""
    
    # Query input
    if selected_query != "Custom Query":
        default_query = SAVED_QUERIES[selected_query]
    else:
        default_query = st.session_state.get('query', "SELECT * FROM analytics.dim_time LIMIT 10")
    
    query = st.text_area(
        "Enter your SQL query:",
        value=default_query,
        height=200,
        key="query_input"
    )
    
    col1, col2, col3 = st.columns([1, 1, 4])
    
    with col1:
        run_query = st.button("▶️ Run Query", type="primary")
    
    with col2:
        explain_query = st.button("📊 Explain")
    
    # Execute query
    if run_query and query.strip():
        with st.spinner("Executing query..."):
            start_time = datetime.now()
            result = execute_query(query, result_limit)
            end_time = datetime.now()
            
            if not result.empty:
                execution_time = (end_time - start_time).total_seconds()
                st.success(f"Query executed in {execution_time:.2f}s. Returned {len(result):,} rows.")
                
                # Store results in session state
                st.session_state['query_result'] = result
                st.session_state['query_time'] = execution_time
    
    if explain_query and query.strip():
        with st.spinner("Getting execution plan..."):
            explain_result = execute_query(f"EXPLAIN ANALYZE {query}", result_limit)
            if not explain_result.empty:
                st.subheader("Query Execution Plan")
                st.code('\n'.join(explain_result.iloc[:, 0].tolist()))
    
    # Display results
    if 'query_result' in st.session_state:
        result = st.session_state['query_result']
        
        st.markdown("---")
        st.subheader("Results")
        
        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["📊 Table", "📈 Chart", "📥 Export"])
        
        with tab1:
            st.dataframe(result, use_container_width=True, height=400)
            
            # Quick stats
            st.markdown("**Quick Stats:**")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Rows", f"{len(result):,}")
            with col2:
                st.metric("Columns", len(result.columns))
            with col3:
                numeric_cols = result.select_dtypes(include=['number']).columns
                st.metric("Numeric Columns", len(numeric_cols))
            with col4:
                st.metric("Query Time", f"{st.session_state.get('query_time', 0):.2f}s")
        
        with tab2:
            # Chart type selector
            detected_type = detect_chart_type(result)
            chart_type = st.selectbox(
                "Chart Type",
                ["table", "line", "bar", "pie", "scatter"],
                index=["table", "line", "bar", "pie", "scatter"].index(detected_type)
            )
            
            create_visualization(result, chart_type)
        
        with tab3:
            st.download_button(
                label="📥 Download CSV",
                data=result.to_csv(index=False),
                file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            st.download_button(
                label="📥 Download JSON",
                data=result.to_json(orient='records', indent=2),
                file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )


if __name__ == "__main__":
    main()

