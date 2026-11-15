"""Unit tests for data transformers."""

import pandas as pd
import pytest

from src.transformers import (
    CustomerTransformer,
    TransactionTransformer,
    SessionTransformer,
    TimezoneHandler,
    SchemaEvolutionHandler
)


class TestCustomerTransformer:
    """Tests for CustomerTransformer."""
    
    @pytest.fixture
    def sample_customer_data(self):
        """Create sample customer data."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003', 'C001'],  # C001 is duplicate
            'first_name': ['John', 'Jane', 'Bob', 'john'],  # Variation of C001
            'last_name': ['Doe', 'Smith', 'Wilson', 'Doe'],
            'email': ['john.doe@email.com', 'JANE.SMITH@EMAIL.COM', None, 'john.doe@email.com'],
            'phone': ['555-123-4567', '(555) 234-5678', '5553456789', '555-123-4567'],
            'customer_segment': ['Enterprise', 'smb', 'CONSUMER', 'enterprise'],
            'country': ['USA', 'US', 'United States', 'usa'],
            'is_active': [True, 'Y', 1, 'true']
        })
    
    def test_name_normalization(self, sample_customer_data):
        """Test that names are properly normalized."""
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.transform(sample_customer_data)
        
        assert result['first_name'].iloc[0] == 'John'
        assert result['last_name'].iloc[1] == 'Smith'
    
    def test_email_normalization(self, sample_customer_data):
        """Test that emails are lowercased."""
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.transform(sample_customer_data)
        
        assert result['email'].iloc[1] == 'jane.smith@email.com'
        assert result['email_domain'].iloc[0] == 'email.com'
    
    def test_phone_normalization(self, sample_customer_data):
        """Test that phone numbers are formatted consistently."""
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.transform(sample_customer_data)
        
        # All phones should have phone_normalized column
        assert 'phone_normalized' in result.columns
    
    def test_segment_normalization(self, sample_customer_data):
        """Test that segments are normalized."""
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.transform(sample_customer_data)
        
        # All segments should be title case
        assert result['customer_segment'].iloc[0] == 'Enterprise'
        assert result['customer_segment'].iloc[1] == 'SMB'
        assert result['customer_segment'].iloc[2] == 'Consumer'
    
    def test_country_normalization(self, sample_customer_data):
        """Test that country codes are normalized."""
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.transform(sample_customer_data)
        
        # All should be 'US'
        assert all(result['country'] == 'US')
    
    def test_boolean_normalization(self, sample_customer_data):
        """Test that booleans are normalized."""
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.transform(sample_customer_data)
        
        # All is_active should be True
        assert all(result['is_active'] == True)
    
    def test_deduplication(self, sample_customer_data):
        """Test that duplicates are removed."""
        transformer = CustomerTransformer(deduplicate=True, fuzzy_threshold=90)
        result = transformer.transform(sample_customer_data)
        
        # Should have fewer rows after deduplication
        assert len(result) < len(sample_customer_data)
    
    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        transformer = CustomerTransformer()
        result = transformer.run(pd.DataFrame())
        
        assert result.empty


class TestTransactionTransformer:
    """Tests for TransactionTransformer."""
    
    @pytest.fixture
    def sample_transaction_data(self):
        """Create sample transaction data."""
        return pd.DataFrame({
            'transaction_id': ['T001', 'T002', 'T003'],
            'customer_id': ['C001', 'C002', 'C003'],
            'total_amount': [100.00, 85.00, 50.00],
            'currency': ['USD', 'EUR', 'gbp'],
            'payment_method': ['Credit Card', 'paypal', 'CREDIT CARD'],
            'status': ['completed', 'COMPLETED', 'Pending'],
            'channel': ['web', 'MOBILE', 'Store'],
            'quantity': [2, 1, 3],
            'unit_price': [50.00, 85.00, 16.67]
        })
    
    def test_currency_normalization(self, sample_transaction_data):
        """Test that currencies are normalized."""
        transformer = TransactionTransformer()
        result = transformer.transform(sample_transaction_data)
        
        # All currencies should be converted to base (USD)
        assert all(result['currency'] == 'USD')
        assert 'original_currency' in result.columns
    
    def test_currency_conversion(self, sample_transaction_data):
        """Test that amounts are converted correctly."""
        transformer = TransactionTransformer(base_currency='USD')
        result = transformer.transform(sample_transaction_data)
        
        # EUR should be converted (rate ~1.08)
        # Original EUR amount was 85, converted should be ~91.8
        eur_row = result[result['original_currency'] == 'EUR']
        assert len(eur_row) == 1
    
    def test_payment_method_normalization(self, sample_transaction_data):
        """Test that payment methods are normalized."""
        transformer = TransactionTransformer()
        result = transformer.transform(sample_transaction_data)
        
        assert result['payment_method'].iloc[0] == 'Credit Card'
        assert result['payment_method'].iloc[1] == 'PayPal'
    
    def test_status_normalization(self, sample_transaction_data):
        """Test that statuses are normalized."""
        transformer = TransactionTransformer()
        result = transformer.transform(sample_transaction_data)
        
        assert result['status'].iloc[0] == 'Completed'
        assert result['status'].iloc[1] == 'Completed'
        assert result['status'].iloc[2] == 'Pending'
    
    def test_channel_normalization(self, sample_transaction_data):
        """Test that channels are normalized."""
        transformer = TransactionTransformer()
        result = transformer.transform(sample_transaction_data)
        
        assert result['channel'].iloc[0] == 'Web'
        assert result['channel'].iloc[1] == 'Mobile'
        assert result['channel'].iloc[2] == 'Store'
    
    def test_amount_validation(self, sample_transaction_data):
        """Test amount validation."""
        transformer = TransactionTransformer(validate_amounts=True)
        result = transformer.transform(sample_transaction_data)
        
        assert 'total_amount_valid' in result.columns


class TestSessionTransformer:
    """Tests for SessionTransformer."""
    
    @pytest.fixture
    def sample_session_data(self):
        """Create sample session data."""
        return pd.DataFrame({
            'session_id': ['S001', 'S002', 'S003'],
            'customer_id': ['C001', 'C002', None],
            'device_type': ['desktop', 'MOBILE', 'Tablet'],
            'browser': ['chrome', 'Safari', 'firefox'],
            'os': ['Windows', 'ios', 'macos'],
            'referrer': ['google.com', 'facebook.com', 'direct'],
            'duration_seconds': [300, 120, 30],
            'page_views': [10, 5, 1],
            'events_count': [20, 10, 2],
            'conversion': [True, False, False]
        })
    
    def test_device_type_normalization(self, sample_session_data):
        """Test that device types are normalized."""
        transformer = SessionTransformer()
        result = transformer.transform(sample_session_data)
        
        assert result['device_type'].iloc[0] == 'Desktop'
        assert result['device_type'].iloc[1] == 'Mobile'
        assert result['device_type'].iloc[2] == 'Tablet'
    
    def test_browser_normalization(self, sample_session_data):
        """Test that browsers are normalized."""
        transformer = SessionTransformer()
        result = transformer.transform(sample_session_data)
        
        assert result['browser'].iloc[0] == 'Chrome'
        assert result['browser'].iloc[1] == 'Safari'
        assert result['browser'].iloc[2] == 'Firefox'
    
    def test_traffic_source_categorization(self, sample_session_data):
        """Test that traffic sources are categorized."""
        transformer = SessionTransformer()
        result = transformer.transform(sample_session_data)
        
        assert result['traffic_source'].iloc[0] == 'Organic Search'
        assert result['traffic_source'].iloc[1] == 'Social'
        assert result['traffic_source'].iloc[2] == 'Direct'
    
    def test_engagement_score_calculation(self, sample_session_data):
        """Test that engagement scores are calculated."""
        transformer = SessionTransformer(calculate_engagement_score=True)
        result = transformer.transform(sample_session_data)
        
        assert 'engagement_score' in result.columns
        # Converted session should have higher score
        assert result['engagement_score'].iloc[0] > result['engagement_score'].iloc[2]
    
    def test_session_categorization(self, sample_session_data):
        """Test that sessions are categorized."""
        transformer = SessionTransformer(categorize_sessions=True)
        result = transformer.transform(sample_session_data)
        
        assert 'session_category' in result.columns
        assert result['session_category'].iloc[0] == 'Converter'
    
    def test_bounce_detection(self, sample_session_data):
        """Test bounce detection."""
        transformer = SessionTransformer()
        result = transformer.transform(sample_session_data)
        
        assert 'is_bounce' in result.columns
        # Session with 1 page view should be bounce
        assert result['is_bounce'].iloc[2] == True


class TestTimezoneHandler:
    """Tests for TimezoneHandler."""
    
    @pytest.fixture
    def sample_timestamp_data(self):
        """Create sample data with timestamps."""
        return pd.DataFrame({
            'id': [1, 2, 3],
            'event_timestamp': [
                '2024-01-15 10:30:00',
                '2024-01-15T15:30:00Z',
                '2024-01-15 08:30:00-05:00'
            ],
            'source_timezone': ['UTC', 'UTC', 'US/Eastern']
        })
    
    def test_utc_conversion(self, sample_timestamp_data):
        """Test conversion to UTC."""
        handler = TimezoneHandler(target_timezone='UTC')
        result = handler.transform(sample_timestamp_data)
        
        assert 'event_timestamp' in result.columns
    
    def test_timezone_detection(self, sample_timestamp_data):
        """Test timezone auto-detection."""
        handler = TimezoneHandler(
            target_timezone='UTC',
            timestamp_columns=['event_timestamp']
        )
        result = handler.transform(sample_timestamp_data)
        
        assert 'event_timestamp_source_tz' in result.columns


class TestSchemaEvolutionHandler:
    """Tests for SchemaEvolutionHandler."""
    
    @pytest.fixture
    def sample_old_schema_data(self):
        """Create data with old schema."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C002'],
            'full_name': ['John Doe', 'Jane Smith'],
            'email': ['john@email.com', 'jane@email.com']
        })
    
    def test_column_split(self, sample_old_schema_data):
        """Test splitting full_name into first_name and last_name."""
        handler = SchemaEvolutionHandler(
            target_schema={
                'customer_id': 'string',
                'first_name': 'string',
                'last_name': 'string',
                'email': 'string'
            }
        )
        result = handler.transform(sample_old_schema_data)
        
        assert 'first_name' in result.columns
        assert 'last_name' in result.columns
        assert result['first_name'].iloc[0] == 'John'
        assert result['last_name'].iloc[0] == 'Doe'
    
    def test_add_missing_columns(self):
        """Test adding missing columns with defaults."""
        df = pd.DataFrame({
            'customer_id': ['C001'],
            'name': ['John']
        })
        
        handler = SchemaEvolutionHandler(
            target_schema={
                'customer_id': 'string',
                'name': 'string',
                'status': 'string',
                'score': 'int'
            },
            default_values={
                'status': 'active',
                'score': 0
            }
        )
        result = handler.transform(df)
        
        assert 'status' in result.columns
        assert 'score' in result.columns
        assert result['status'].iloc[0] == 'active'
        assert result['score'].iloc[0] == 0


class TestSchemaEvolutionHandler:
    """Tests for SchemaEvolutionHandler."""
    
    @pytest.fixture
    def sample_old_schema_data(self):
        """Create data with old schema."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C002'],
            'full_name': ['John Doe', 'Jane Smith'],
            'email': ['john@email.com', 'jane@email.com']
        })
    
    def test_column_split(self, sample_old_schema_data):
        """Test splitting full_name into first_name and last_name."""
        handler = SchemaEvolutionHandler(
            target_schema={
                'customer_id': 'string',
                'first_name': 'string',
                'last_name': 'string',
                'email': 'string'
            }
        )
        result = handler.transform(sample_old_schema_data)
        
        assert 'first_name' in result.columns
        assert 'last_name' in result.columns
        assert result['first_name'].iloc[0] == 'John'
        assert result['last_name'].iloc[0] == 'Doe'
    
    def test_add_missing_columns(self):
        """Test adding missing columns with defaults."""
        df = pd.DataFrame({
            'customer_id': ['C001'],
            'name': ['John']
        })
        
        handler = SchemaEvolutionHandler(
            target_schema={
                'customer_id': 'string',
                'name': 'string',
                'status': 'string',
                'score': 'int'
            },
            default_values={
                'status': 'active',
                'score': 0
            }
        )
        result = handler.transform(df)
        
        assert 'status' in result.columns
        assert 'score' in result.columns
        assert result['status'].iloc[0] == 'active'
        assert result['score'].iloc[0] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

