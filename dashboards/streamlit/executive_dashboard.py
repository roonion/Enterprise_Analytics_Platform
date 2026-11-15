"""
Executive Dashboard - Streamlit Application
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
    page_title="Executive Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
        margin-bottom: 1rem;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .metric-delta {
        font-size: 0.85rem;
        margin-top: 0.5rem;
    }
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        margin: 2rem 0 1rem 0;
        color: #1f2937;
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


@st.cache_data(ttl=300)
def get_kpis(start_date, end_date):
    """Get KPI metrics."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        COALESCE(SUM(total_amount_usd), 0) as revenue,
        COUNT(*) as transactions,
        COUNT(DISTINCT customer_sk) as customers,
        COALESCE(AVG(total_amount_usd), 0) as aov
    FROM analytics.fact_transactions
    WHERE status = 'Completed'
    AND transaction_timestamp BETWEEN :start AND :end
    """
    
    try:
        df = pd.read_sql(query, engine, params={'start': start_date, 'end': end_date})
        return df.iloc[0].to_dict()
    except Exception as e:
        st.error(f"Error loading KPIs: {e}")
        return {'revenue': 0, 'transactions': 0, 'customers': 0, 'aov': 0}


@st.cache_data(ttl=300)
def get_revenue_trend(start_date, end_date):
    """Get daily revenue trend."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        dt.full_date as date,
        COALESCE(SUM(ft.total_amount_usd), 0) as revenue,
        COUNT(ft.transaction_sk) as transactions
    FROM analytics.dim_time dt
    LEFT JOIN analytics.fact_transactions ft 
        ON dt.date_key = ft.date_key 
        AND ft.status = 'Completed'
    WHERE dt.full_date BETWEEN :start AND :end
    GROUP BY dt.full_date
    ORDER BY dt.full_date
    """
    
    try:
        return pd.read_sql(query, engine, params={'start': start_date, 'end': end_date})
    except Exception:
        return pd.DataFrame(columns=['date', 'revenue', 'transactions'])


@st.cache_data(ttl=300)
def get_channel_breakdown(start_date, end_date):
    """Get revenue by channel."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        COALESCE(ch.channel_name, 'Unknown') as channel,
        SUM(ft.total_amount_usd) as revenue,
        COUNT(*) as transactions
    FROM analytics.fact_transactions ft
    LEFT JOIN analytics.dim_channels ch ON ft.channel_sk = ch.channel_sk
    WHERE ft.status = 'Completed'
    AND ft.transaction_timestamp BETWEEN :start AND :end
    GROUP BY ch.channel_name
    ORDER BY revenue DESC
    """
    
    try:
        return pd.read_sql(query, engine, params={'start': start_date, 'end': end_date})
    except Exception:
        return pd.DataFrame(columns=['channel', 'revenue', 'transactions'])


@st.cache_data(ttl=300)
def get_segment_performance(start_date, end_date):
    """Get performance by customer segment."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        COALESCE(dc.customer_segment, 'Unknown') as segment,
        COUNT(DISTINCT ft.customer_sk) as customers,
        SUM(ft.total_amount_usd) as revenue,
        AVG(ft.total_amount_usd) as avg_order_value
    FROM analytics.fact_transactions ft
    LEFT JOIN analytics.dim_customers dc ON ft.customer_sk = dc.customer_sk
    WHERE ft.status = 'Completed'
    AND ft.transaction_timestamp BETWEEN :start AND :end
    GROUP BY dc.customer_segment
    ORDER BY revenue DESC
    """
    
    try:
        return pd.read_sql(query, engine, params={'start': start_date, 'end': end_date})
    except Exception:
        return pd.DataFrame(columns=['segment', 'customers', 'revenue', 'avg_order_value'])


@st.cache_data(ttl=300)
def get_top_products(start_date, end_date, limit=10):
    """Get top products by revenue."""
    engine = get_db_connection()
    
    query = """
    SELECT 
        dp.product_name,
        dp.category,
        SUM(ft.quantity) as units_sold,
        SUM(ft.total_amount_usd) as revenue
    FROM analytics.fact_transactions ft
    JOIN analytics.dim_products dp ON ft.product_sk = dp.product_sk
    WHERE ft.status = 'Completed'
    AND dp.is_current = TRUE
    AND ft.transaction_timestamp BETWEEN :start AND :end
    GROUP BY dp.product_name, dp.category
    ORDER BY revenue DESC
    LIMIT :limit
    """
    
    try:
        return pd.read_sql(query, engine, params={'start': start_date, 'end': end_date, 'limit': limit})
    except Exception:
        return pd.DataFrame(columns=['product_name', 'category', 'units_sold', 'revenue'])


def format_currency(value):
    """Format value as currency."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}K"
    else:
        return f"${value:.2f}"


def format_number(value):
    """Format large numbers."""
    if value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value/1_000:.1f}K"
    else:
        return f"{value:,.0f}"


# Main dashboard
def main():
    st.title("📊 Executive Dashboard")
    st.markdown("---")
    
    # Sidebar filters
    with st.sidebar:
        st.header("Filters")
        
        # Date range selector
        date_range = st.selectbox(
            "Date Range",
            ["Last 7 Days", "Last 30 Days", "Last 90 Days", "Month to Date", "Year to Date", "Custom"]
        )
        
        today = datetime.now().date()
        
        if date_range == "Last 7 Days":
            start_date = today - timedelta(days=7)
            end_date = today
        elif date_range == "Last 30 Days":
            start_date = today - timedelta(days=30)
            end_date = today
        elif date_range == "Last 90 Days":
            start_date = today - timedelta(days=90)
            end_date = today
        elif date_range == "Month to Date":
            start_date = today.replace(day=1)
            end_date = today
        elif date_range == "Year to Date":
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", today - timedelta(days=30))
            with col2:
                end_date = st.date_input("End Date", today)
        
        st.markdown("---")
        st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    
    # KPI Cards
    kpis = get_kpis(start_date, end_date)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Revenue",
            value=format_currency(kpis['revenue']),
            delta="vs prior period"
        )
    
    with col2:
        st.metric(
            label="Transactions",
            value=format_number(kpis['transactions']),
            delta="vs prior period"
        )
    
    with col3:
        st.metric(
            label="Unique Customers",
            value=format_number(kpis['customers']),
            delta="vs prior period"
        )
    
    with col4:
        st.metric(
            label="Avg Order Value",
            value=f"${kpis['aov']:.2f}",
            delta="vs prior period"
        )
    
    st.markdown("---")
    
    # Revenue Trend
    st.subheader("📈 Revenue Trend")
    
    revenue_df = get_revenue_trend(start_date, end_date)
    
    if not revenue_df.empty:
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=revenue_df['date'],
            y=revenue_df['revenue'],
            mode='lines+markers',
            name='Revenue',
            line=dict(color='#667eea', width=3),
            marker=dict(size=6)
        ))
        
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Revenue ($)",
            hovermode='x unified',
            template='plotly_white',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available for the selected period")
    
    # Two column layout for breakdowns
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Revenue by Channel")
        
        channel_df = get_channel_breakdown(start_date, end_date)
        
        if not channel_df.empty:
            fig = px.pie(
                channel_df,
                values='revenue',
                names='channel',
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(showlegend=True, height=400)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No channel data available")
    
    with col2:
        st.subheader("👥 Segment Performance")
        
        segment_df = get_segment_performance(start_date, end_date)
        
        if not segment_df.empty:
            fig = px.bar(
                segment_df,
                x='segment',
                y='revenue',
                color='segment',
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig.update_layout(
                xaxis_title="Customer Segment",
                yaxis_title="Revenue ($)",
                showlegend=False,
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No segment data available")
    
    # Top Products
    st.subheader("🏆 Top Products")
    
    products_df = get_top_products(start_date, end_date)
    
    if not products_df.empty:
        products_df['revenue_formatted'] = products_df['revenue'].apply(format_currency)
        
        st.dataframe(
            products_df[['product_name', 'category', 'units_sold', 'revenue_formatted']].rename(
                columns={
                    'product_name': 'Product',
                    'category': 'Category',
                    'units_sold': 'Units Sold',
                    'revenue_formatted': 'Revenue'
                }
            ),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No product data available")


if __name__ == "__main__":
    main()

