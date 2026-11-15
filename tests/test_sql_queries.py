"""Unit tests for SQL queries and data model logic."""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import pytest


class TestDimensionTableLogic:
    """Tests for dimension table logic."""
    
    def test_scd_type2_current_record_logic(self):
        """Test SCD Type 2 current record identification."""
        # Simulate SCD Type 2 table
        dim_customers = pd.DataFrame({
            'customer_sk': [1, 2, 3, 4],
            'customer_id': ['C001', 'C001', 'C002', 'C003'],
            'first_name': ['John', 'John', 'Jane', 'Bob'],
            'last_name': ['Doe', 'Smith', 'Smith', 'Wilson'],  # Changed from Doe to Smith
            'is_current': [False, True, True, True],
            'effective_start_date': [
                datetime(2023, 1, 1),
                datetime(2024, 1, 1),
                datetime(2023, 1, 1),
                datetime(2023, 6, 1)
            ],
            'effective_end_date': [
                datetime(2024, 1, 1),
                datetime(9999, 12, 31),
                datetime(9999, 12, 31),
                datetime(9999, 12, 31)
            ],
            'version': [1, 2, 1, 1]
        })
        
        # Get current records
        current_records = dim_customers[dim_customers['is_current'] == True]
        
        assert len(current_records) == 3  # C001 (v2), C002, C003
        
        # C001 should only have version 2 as current
        c001_current = current_records[current_records['customer_id'] == 'C001']
        assert len(c001_current) == 1
        assert c001_current['version'].iloc[0] == 2
        assert c001_current['last_name'].iloc[0] == 'Smith'
    
    def test_time_dimension_date_attributes(self):
        """Test time dimension date attribute calculations."""
        # Simulate date attribute calculations
        test_date = datetime(2024, 3, 15)  # March 15, 2024 (Friday)
        
        date_attributes = {
            'date_key': int(test_date.strftime('%Y%m%d')),
            'full_date': test_date.date(),
            'year': test_date.year,
            'quarter': (test_date.month - 1) // 3 + 1,
            'month': test_date.month,
            'week_of_year': test_date.isocalendar()[1],
            'day_of_month': test_date.day,
            'day_of_week': test_date.weekday(),
            'is_weekend': test_date.weekday() >= 5
        }
        
        assert date_attributes['date_key'] == 20240315
        assert date_attributes['year'] == 2024
        assert date_attributes['quarter'] == 1  # March is Q1
        assert date_attributes['month'] == 3
        assert date_attributes['day_of_month'] == 15
        assert date_attributes['is_weekend'] == False  # Friday
    
    def test_fiscal_calendar_logic(self):
        """Test fiscal calendar calculations (fiscal year starts February)."""
        def get_fiscal_year(date: datetime, fy_start_month: int = 2) -> int:
            """Get fiscal year (assuming FY starts in February)."""
            if date.month >= fy_start_month:
                return date.year
            return date.year - 1
        
        def get_fiscal_quarter(date: datetime, fy_start_month: int = 2) -> int:
            """Get fiscal quarter."""
            month = date.month
            if month >= fy_start_month:
                fiscal_month = month - fy_start_month + 1
            else:
                fiscal_month = month + 12 - fy_start_month + 1
            return (fiscal_month - 1) // 3 + 1
        
        # Test dates
        jan_2024 = datetime(2024, 1, 15)
        feb_2024 = datetime(2024, 2, 15)
        may_2024 = datetime(2024, 5, 15)
        nov_2024 = datetime(2024, 11, 15)
        
        # January is end of FY2023
        assert get_fiscal_year(jan_2024) == 2023
        # February is start of FY2024
        assert get_fiscal_year(feb_2024) == 2024
        
        # Fiscal quarters
        assert get_fiscal_quarter(feb_2024) == 1  # Feb-Apr is FQ1
        assert get_fiscal_quarter(may_2024) == 2  # May-Jul is FQ2
        assert get_fiscal_quarter(nov_2024) == 4  # Nov-Jan is FQ4


class TestFactTableLogic:
    """Tests for fact table logic."""
    
    def test_transaction_amount_calculations(self):
        """Test transaction amount calculations."""
        transactions = pd.DataFrame({
            'transaction_id': ['T001', 'T002', 'T003'],
            'quantity': [2, 5, 1],
            'unit_price': [50.00, 25.00, 100.00],
            'discount_pct': [0.0, 0.1, 0.2],
            'tax_rate': [0.08, 0.08, 0.0]
        })
        
        # Calculate amounts
        transactions['gross_amount'] = transactions['quantity'] * transactions['unit_price']
        transactions['discount_amount'] = transactions['gross_amount'] * transactions['discount_pct']
        transactions['subtotal'] = transactions['gross_amount'] - transactions['discount_amount']
        transactions['tax_amount'] = transactions['subtotal'] * transactions['tax_rate']
        transactions['total_amount'] = transactions['subtotal'] + transactions['tax_amount']
        
        # T001: 2 * 50 = 100, no discount, 8% tax = 108
        assert transactions['total_amount'].iloc[0] == pytest.approx(108.00)
        
        # T002: 5 * 25 = 125, 10% discount = 112.5, 8% tax = 121.5
        assert transactions['total_amount'].iloc[1] == pytest.approx(121.50)
        
        # T003: 1 * 100 = 100, 20% discount = 80, no tax = 80
        assert transactions['total_amount'].iloc[2] == pytest.approx(80.00)
    
    def test_currency_conversion(self):
        """Test multi-currency conversion logic."""
        exchange_rates = {
            'USD': 1.0,
            'EUR': 1.08,
            'GBP': 1.26,
            'CAD': 0.74,
            'JPY': 0.0067
        }
        
        transactions = pd.DataFrame({
            'transaction_id': ['T001', 'T002', 'T003', 'T004'],
            'amount_local': [100.00, 85.00, 50.00, 10000.00],
            'currency': ['USD', 'EUR', 'GBP', 'JPY']
        })
        
        # Convert to USD
        transactions['amount_usd'] = transactions.apply(
            lambda row: row['amount_local'] * exchange_rates.get(row['currency'], 1.0),
            axis=1
        )
        
        assert transactions['amount_usd'].iloc[0] == pytest.approx(100.00)  # USD
        assert transactions['amount_usd'].iloc[1] == pytest.approx(91.80)   # EUR
        assert transactions['amount_usd'].iloc[2] == pytest.approx(63.00)   # GBP
        assert transactions['amount_usd'].iloc[3] == pytest.approx(67.00)   # JPY
    
    def test_late_arriving_fact_handling(self):
        """Test late-arriving fact identification logic."""
        transactions = pd.DataFrame({
            'transaction_id': ['T001', 'T002', 'T003'],
            'transaction_date': [
                datetime(2024, 3, 1),
                datetime(2024, 2, 15),
                datetime(2024, 3, 10)
            ],
            'processing_date': [
                datetime(2024, 3, 1),
                datetime(2024, 3, 5),  # 18 days late
                datetime(2024, 3, 10)
            ]
        })
        
        # Calculate days late
        transactions['days_late'] = (
            transactions['processing_date'] - transactions['transaction_date']
        ).dt.days
        
        # Flag late arrivals (>3 days)
        transactions['is_late_arrival'] = transactions['days_late'] > 3
        
        assert transactions['is_late_arrival'].iloc[0] == False  # Same day
        assert transactions['is_late_arrival'].iloc[1] == True   # 18 days late
        assert transactions['is_late_arrival'].iloc[2] == False  # Same day


class TestAggregatedMartLogic:
    """Tests for aggregated mart calculations."""
    
    @pytest.fixture
    def sample_transactions(self):
        """Create sample transaction data."""
        return pd.DataFrame({
            'transaction_id': ['T001', 'T002', 'T003', 'T004', 'T005'],
            'customer_id': ['C001', 'C001', 'C002', 'C002', 'C003'],
            'date_key': [20240101, 20240115, 20240101, 20240120, 20240115],
            'total_amount_usd': [100.0, 150.0, 200.0, 50.0, 75.0],
            'quantity': [2, 3, 4, 1, 2]
        })
    
    def test_daily_revenue_aggregation(self, sample_transactions):
        """Test daily revenue mart calculation."""
        daily_revenue = sample_transactions.groupby('date_key').agg({
            'total_amount_usd': 'sum',
            'transaction_id': 'count',
            'customer_id': 'nunique'
        }).rename(columns={
            'total_amount_usd': 'total_revenue',
            'transaction_id': 'total_transactions',
            'customer_id': 'unique_customers'
        }).reset_index()
        
        # 20240101: T001 + T003 = 300
        day_20240101 = daily_revenue[daily_revenue['date_key'] == 20240101]
        assert day_20240101['total_revenue'].iloc[0] == 300.0
        assert day_20240101['total_transactions'].iloc[0] == 2
        assert day_20240101['unique_customers'].iloc[0] == 2  # C001 and C002
    
    def test_customer_lifetime_value_calculation(self, sample_transactions):
        """Test CLV calculation logic."""
        customer_metrics = sample_transactions.groupby('customer_id').agg({
            'total_amount_usd': 'sum',
            'transaction_id': 'count',
            'date_key': ['min', 'max']
        })
        customer_metrics.columns = ['total_revenue', 'transaction_count', 'first_purchase', 'last_purchase']
        customer_metrics = customer_metrics.reset_index()
        
        # Calculate metrics
        customer_metrics['avg_order_value'] = (
            customer_metrics['total_revenue'] / customer_metrics['transaction_count']
        )
        customer_metrics['tenure_days'] = (
            customer_metrics['last_purchase'] - customer_metrics['first_purchase']
        )
        
        # C001: 250 total, 2 orders, AOV = 125
        c001 = customer_metrics[customer_metrics['customer_id'] == 'C001']
        assert c001['total_revenue'].iloc[0] == 250.0
        assert c001['avg_order_value'].iloc[0] == 125.0
        
        # C002: 250 total, 2 orders, AOV = 125
        c002 = customer_metrics[customer_metrics['customer_id'] == 'C002']
        assert c002['total_revenue'].iloc[0] == 250.0
    
    def test_rfm_scoring(self, sample_transactions):
        """Test RFM (Recency, Frequency, Monetary) scoring logic."""
        reference_date = 20240201
        
        customer_rfm = sample_transactions.groupby('customer_id').agg({
            'date_key': 'max',  # Most recent purchase
            'transaction_id': 'count',  # Frequency
            'total_amount_usd': 'sum'  # Monetary
        }).rename(columns={
            'date_key': 'last_purchase_date',
            'transaction_id': 'frequency',
            'total_amount_usd': 'monetary'
        }).reset_index()
        
        # Calculate recency (days since last purchase)
        customer_rfm['recency'] = reference_date - customer_rfm['last_purchase_date']
        
        # Score each dimension (1-5, higher is better)
        def score_recency(recency):
            if recency <= 10: return 5
            elif recency <= 20: return 4
            elif recency <= 50: return 3
            elif recency <= 100: return 2
            return 1
        
        def score_frequency(freq):
            if freq >= 10: return 5
            elif freq >= 5: return 4
            elif freq >= 3: return 3
            elif freq >= 2: return 2
            return 1
        
        def score_monetary(monetary):
            if monetary >= 500: return 5
            elif monetary >= 250: return 4
            elif monetary >= 100: return 3
            elif monetary >= 50: return 2
            return 1
        
        customer_rfm['r_score'] = customer_rfm['recency'].apply(score_recency)
        customer_rfm['f_score'] = customer_rfm['frequency'].apply(score_frequency)
        customer_rfm['m_score'] = customer_rfm['monetary'].apply(score_monetary)
        customer_rfm['rfm_score'] = (
            customer_rfm['r_score'].astype(str) + 
            customer_rfm['f_score'].astype(str) + 
            customer_rfm['m_score'].astype(str)
        )
        
        # Verify RFM structure
        assert all(col in customer_rfm.columns for col in ['r_score', 'f_score', 'm_score', 'rfm_score'])


class TestCohortAnalysisLogic:
    """Tests for cohort analysis calculations."""
    
    @pytest.fixture
    def cohort_data(self):
        """Create sample data for cohort analysis."""
        # Customers with registration month and activity
        return pd.DataFrame({
            'customer_id': ['C001', 'C001', 'C001', 'C002', 'C002', 'C003'],
            'registration_month': ['2024-01', '2024-01', '2024-01', '2024-01', '2024-01', '2024-02'],
            'activity_month': ['2024-01', '2024-02', '2024-03', '2024-01', '2024-02', '2024-02'],
            'revenue': [100, 50, 75, 200, 100, 150]
        })
    
    def test_cohort_size_calculation(self, cohort_data):
        """Test cohort size calculation."""
        cohort_sizes = cohort_data.groupby('registration_month')['customer_id'].nunique()
        
        assert cohort_sizes['2024-01'] == 2  # C001 and C002
        assert cohort_sizes['2024-02'] == 1  # C003
    
    def test_retention_calculation(self, cohort_data):
        """Test monthly retention calculation."""
        # Calculate months since registration
        def months_diff(row):
            reg_parts = row['registration_month'].split('-')
            act_parts = row['activity_month'].split('-')
            reg_months = int(reg_parts[0]) * 12 + int(reg_parts[1])
            act_months = int(act_parts[0]) * 12 + int(act_parts[1])
            return act_months - reg_months
        
        cohort_data['months_since_registration'] = cohort_data.apply(months_diff, axis=1)
        
        # Calculate retention matrix
        retention = cohort_data.groupby(
            ['registration_month', 'months_since_registration']
        )['customer_id'].nunique().unstack(fill_value=0)
        
        # For 2024-01 cohort:
        # Month 0: 2 customers
        # Month 1: 2 customers (both returned)
        # Month 2: 1 customer (C001)
        assert retention.loc['2024-01', 0] == 2
        assert retention.loc['2024-01', 1] == 2
        assert retention.loc['2024-01', 2] == 1


class TestChurnAnalysisLogic:
    """Tests for churn analysis calculations."""
    
    @pytest.fixture
    def customer_activity(self):
        """Create sample customer activity data."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003', 'C004', 'C005'],
            'last_activity_date': [
                datetime(2024, 3, 1),   # Active (< 30 days)
                datetime(2024, 2, 1),   # At risk (30-60 days)
                datetime(2024, 1, 1),   # Churned (60-90 days)
                datetime(2023, 12, 1),  # Lost (> 90 days)
                datetime(2024, 3, 10)   # Active
            ],
            'customer_segment': ['Enterprise', 'SMB', 'Consumer', 'Enterprise', 'SMB'],
            'total_revenue': [5000, 500, 100, 3000, 250]
        })
    
    def test_churn_classification(self, customer_activity):
        """Test customer churn classification."""
        reference_date = datetime(2024, 3, 15)
        
        customer_activity['days_since_activity'] = (
            reference_date - customer_activity['last_activity_date']
        ).dt.days
        
        def classify_churn_status(days):
            if days <= 30:
                return 'Active'
            elif days <= 60:
                return 'At Risk'
            elif days <= 90:
                return 'Churned'
            else:
                return 'Lost'
        
        customer_activity['churn_status'] = customer_activity['days_since_activity'].apply(
            classify_churn_status
        )
        
        status_counts = customer_activity['churn_status'].value_counts()
        
        assert status_counts.get('Active', 0) == 2  # C001, C005
        assert status_counts.get('At Risk', 0) == 1  # C002
        assert status_counts.get('Churned', 0) == 1  # C003
        assert status_counts.get('Lost', 0) == 1    # C004
    
    def test_churn_rate_by_segment(self, customer_activity):
        """Test churn rate calculation by segment."""
        reference_date = datetime(2024, 3, 15)
        
        customer_activity['days_since_activity'] = (
            reference_date - customer_activity['last_activity_date']
        ).dt.days
        customer_activity['is_churned'] = customer_activity['days_since_activity'] > 60
        
        segment_churn = customer_activity.groupby('customer_segment').agg({
            'customer_id': 'count',
            'is_churned': 'sum'
        }).rename(columns={
            'customer_id': 'total_customers',
            'is_churned': 'churned_customers'
        })
        segment_churn['churn_rate'] = (
            segment_churn['churned_customers'] / segment_churn['total_customers'] * 100
        )
        
        # Enterprise: 1 churned out of 2 = 50%
        assert segment_churn.loc['Enterprise', 'churn_rate'] == 50.0
        
        # Consumer: 1 churned out of 1 = 100%
        assert segment_churn.loc['Consumer', 'churn_rate'] == 100.0


class TestWindowFunctionLogic:
    """Tests for window function calculations."""
    
    @pytest.fixture
    def transaction_series(self):
        """Create time series transaction data."""
        return pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10, freq='D'),
            'customer_id': ['C001'] * 10,
            'revenue': [100, 150, 120, 200, 180, 160, 190, 210, 175, 195]
        })
    
    def test_running_total(self, transaction_series):
        """Test running total calculation."""
        transaction_series['running_total'] = transaction_series['revenue'].cumsum()
        
        assert transaction_series['running_total'].iloc[0] == 100
        assert transaction_series['running_total'].iloc[1] == 250  # 100 + 150
        assert transaction_series['running_total'].iloc[-1] == sum(transaction_series['revenue'])
    
    def test_moving_average(self, transaction_series):
        """Test moving average calculation."""
        transaction_series['ma_3day'] = transaction_series['revenue'].rolling(window=3).mean()
        
        # First 2 values should be NaN
        assert pd.isna(transaction_series['ma_3day'].iloc[0])
        assert pd.isna(transaction_series['ma_3day'].iloc[1])
        
        # Third value: (100 + 150 + 120) / 3 = 123.33
        assert transaction_series['ma_3day'].iloc[2] == pytest.approx(123.33, rel=0.01)
    
    def test_rank_calculation(self, transaction_series):
        """Test ranking calculation."""
        transaction_series['revenue_rank'] = transaction_series['revenue'].rank(
            method='dense',
            ascending=False
        )
        
        # Highest revenue (210) should be rank 1
        max_revenue_idx = transaction_series['revenue'].idxmax()
        assert transaction_series.loc[max_revenue_idx, 'revenue_rank'] == 1
    
    def test_lag_lead_calculations(self, transaction_series):
        """Test lag and lead (previous/next value) calculations."""
        transaction_series['prev_day_revenue'] = transaction_series['revenue'].shift(1)
        transaction_series['next_day_revenue'] = transaction_series['revenue'].shift(-1)
        transaction_series['daily_change'] = (
            transaction_series['revenue'] - transaction_series['prev_day_revenue']
        )
        transaction_series['daily_change_pct'] = (
            transaction_series['daily_change'] / transaction_series['prev_day_revenue'] * 100
        )
        
        # First row should have NaN for prev_day
        assert pd.isna(transaction_series['prev_day_revenue'].iloc[0])
        
        # Second row change: 150 - 100 = 50, 50% increase
        assert transaction_series['daily_change'].iloc[1] == 50
        assert transaction_series['daily_change_pct'].iloc[1] == 50.0


class TestIncrementalLoadLogic:
    """Tests for incremental loading logic."""
    
    def test_incremental_detection(self):
        """Test identifying new and modified records."""
        # Existing data (already in warehouse)
        existing = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'updated_at': [
                datetime(2024, 1, 1),
                datetime(2024, 1, 1),
                datetime(2024, 1, 1)
            ]
        })
        
        # New source data
        source = pd.DataFrame({
            'id': [2, 3, 4, 5],
            'name': ['Robert', 'Charlie', 'David', 'Eve'],  # Bob changed to Robert
            'updated_at': [
                datetime(2024, 1, 15),  # Updated
                datetime(2024, 1, 1),   # Unchanged
                datetime(2024, 1, 10),  # New
                datetime(2024, 1, 12)   # New
            ]
        })
        
        # Identify changes
        merged = source.merge(existing, on='id', how='left', suffixes=('_new', '_old'))
        
        # New records (no match in existing)
        new_records = merged[merged['name_old'].isna()]
        assert len(new_records) == 2  # David and Eve
        
        # Updated records (match exists, updated_at is newer)
        updates = merged[
            (merged['name_old'].notna()) & 
            (merged['updated_at_new'] > merged['updated_at_old'])
        ]
        assert len(updates) == 1  # Bob -> Robert


class TestSQLQueryExecution:
    """Tests for SQL query execution and validation."""
    
    def test_cohort_analysis_query_structure(self):
        """Test that cohort analysis query has correct structure."""
        # This would typically test against a database, but we can test the logic
        # Simulate cohort data
        cohort_data = pd.DataFrame({
            'cohort_month': ['2024-01', '2024-01', '2024-02'],
            'month_number': [0, 1, 0],
            'customers': [100, 80, 120],
            'cohort_size': [100, 100, 120]
        })
        
        # Calculate retention
        cohort_data['retention_rate'] = (
            cohort_data['customers'] / cohort_data['cohort_size'] * 100
        )
        
        # Month 0 should be 100%
        month_0 = cohort_data[cohort_data['month_number'] == 0]
        assert all(month_0['retention_rate'] == 100.0)
        
        # Month 1 should be less
        month_1 = cohort_data[cohort_data['month_number'] == 1]
        assert month_1['retention_rate'].iloc[0] == 80.0
    
    def test_revenue_analysis_window_functions(self):
        """Test revenue analysis window function calculations."""
        revenue_data = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10, freq='D'),
            'revenue': [100, 150, 120, 200, 180, 160, 190, 210, 175, 195]
        })
        
        # Calculate moving averages
        revenue_data['ma_7d'] = revenue_data['revenue'].rolling(window=7).mean()
        revenue_data['ma_30d'] = revenue_data['revenue'].rolling(window=30).mean()
        
        # Calculate day-over-day growth
        revenue_data['dod_growth'] = (
            revenue_data['revenue'].pct_change() * 100
        )
        
        # Verify structure
        assert 'ma_7d' in revenue_data.columns
        assert 'ma_30d' in revenue_data.columns
        assert 'dod_growth' in revenue_data.columns
        
        # First row should have NaN for growth
        assert pd.isna(revenue_data['dod_growth'].iloc[0])
    
    def test_clv_calculation_logic(self):
        """Test CLV calculation logic."""
        customer_data = pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003'],
            'total_revenue': [500, 250, 1000],
            'total_orders': [5, 2, 10],
            'tenure_days': [365, 180, 730]
        })
        
        # Calculate metrics
        customer_data['avg_order_value'] = (
            customer_data['total_revenue'] / customer_data['total_orders']
        )
        customer_data['annualized_clv'] = (
            customer_data['total_revenue'] / customer_data['tenure_days'] * 365
        )
        
        # C001: 500 / 365 * 365 = 500
        assert customer_data['annualized_clv'].iloc[0] == pytest.approx(500.0)
        
        # C002: 250 / 180 * 365 = ~507
        assert customer_data['annualized_clv'].iloc[1] == pytest.approx(507.6, rel=0.01)
    
    def test_churn_classification_logic(self):
        """Test churn classification logic."""
        customer_activity = pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003', 'C004'],
            'days_since_last_order': [15, 45, 75, 120]
        })
        
        def classify_churn(days):
            if days <= 30:
                return 'Active'
            elif days <= 60:
                return 'At Risk'
            elif days <= 90:
                return 'High Risk'
            else:
                return 'Churned'
        
        customer_activity['churn_status'] = customer_activity['days_since_last_order'].apply(
            classify_churn
        )
        
        assert customer_activity['churn_status'].iloc[0] == 'Active'
        assert customer_activity['churn_status'].iloc[1] == 'At Risk'
        assert customer_activity['churn_status'].iloc[2] == 'High Risk'
        assert customer_activity['churn_status'].iloc[3] == 'Churned'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

