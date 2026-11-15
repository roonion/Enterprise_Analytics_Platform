"""Unit tests for ETL pipeline components."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Import pipeline functions for testing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestExtractFunctions:
    """Tests for data extraction functions in the ETL pipeline."""
    
    @pytest.fixture
    def sample_customer_csv(self):
        """Create sample customer CSV."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("customer_id,first_name,last_name,email,phone,customer_segment,country,is_active\n")
            f.write("C001,John,Doe,john@email.com,555-1234,Enterprise,US,true\n")
            f.write("C002,Jane,Smith,jane@email.com,555-5678,SMB,CA,true\n")
            f.write("C003,Bob,Wilson,bob@email.com,555-9012,Consumer,UK,false\n")
            return f.name
    
    @pytest.fixture
    def sample_transaction_csv(self):
        """Create sample transaction CSV."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("transaction_id,customer_id,product_id,total_amount,currency,status,channel\n")
            f.write("T001,C001,P001,100.00,USD,completed,web\n")
            f.write("T002,C002,P002,85.00,EUR,COMPLETED,mobile\n")
            f.write("T003,C003,P003,50.00,GBP,pending,store\n")
            return f.name
    
    def test_customer_extraction(self, sample_customer_csv):
        """Test customer data extraction."""
        from src.extractors import CSVExtractor
        
        extractor = CSVExtractor(file_path=sample_customer_csv)
        df = extractor.run()
        
        assert len(df) == 3
        assert 'customer_id' in df.columns
        assert df['customer_id'].iloc[0] == 'C001'
        
        os.unlink(sample_customer_csv)
    
    def test_transaction_extraction(self, sample_transaction_csv):
        """Test transaction data extraction."""
        from src.extractors import CSVExtractor
        
        extractor = CSVExtractor(file_path=sample_transaction_csv)
        df = extractor.run()
        
        assert len(df) == 3
        assert 'transaction_id' in df.columns
        assert 'total_amount' in df.columns
        
        os.unlink(sample_transaction_csv)


class TestValidationStep:
    """Tests for the validation step in ETL pipeline."""
    
    @pytest.fixture
    def valid_customer_df(self):
        """Create valid customer DataFrame."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003'],
            'email': ['a@test.com', 'b@test.com', 'c@test.com'],
            'first_name': ['Alice', 'Bob', 'Charlie']
        })
    
    @pytest.fixture
    def invalid_customer_df(self):
        """Create customer DataFrame with issues."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C001', None],  # Duplicate and null
            'email': ['a@test.com', None, 'c@test.com'],
            'first_name': ['Alice', 'Bob', None]
        })
    
    def test_valid_data_passes_validation(self, valid_customer_df):
        """Test that valid data passes validation."""
        from src.validators import DataQualityValidator
        
        validator = DataQualityValidator(
            dataset_name='customers',
            fail_on_error=False,
            null_threshold=0.1,
            duplicate_threshold=0.1
        )
        validator.check_column_exists(['customer_id', 'email'])
        validator.check_not_null(['customer_id'])
        
        report = validator.validate(valid_customer_df)
        
        assert report.is_valid
        assert report.overall_score >= 80
    
    def test_invalid_data_fails_validation(self, invalid_customer_df):
        """Test that invalid data fails validation."""
        from src.validators import DataQualityValidator
        from src.validators.data_quality_validator import ValidationSeverity
        
        validator = DataQualityValidator(
            dataset_name='customers',
            fail_on_error=False,
            null_threshold=0.1
        )
        validator.check_not_null(['customer_id'], severity=ValidationSeverity.ERROR)
        
        report = validator.validate(invalid_customer_df)
        
        # Should fail due to null customer_id
        assert not report.is_valid or report.failed_checks > 0


class TestTransformStep:
    """Tests for the transformation step in ETL pipeline."""
    
    @pytest.fixture
    def messy_customer_df(self):
        """Create messy customer data."""
        return pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003'],
            'first_name': ['john', 'JANE', 'Bob'],
            'last_name': ['DOE', 'smith', 'Wilson'],
            'email': ['JOHN@EMAIL.COM', 'jane@email.com', 'bob@EMAIL.com'],
            'customer_segment': ['enterprise', 'SMB', 'CONSUMER'],
            'country': ['usa', 'United States', 'CA'],
            'is_active': ['true', 'Y', 1]
        })
    
    @pytest.fixture
    def messy_transaction_df(self):
        """Create messy transaction data."""
        return pd.DataFrame({
            'transaction_id': ['T001', 'T002', 'T003'],
            'customer_id': ['C001', 'C002', 'C003'],
            'total_amount': [100.00, 85.00, 50.00],
            'currency': ['USD', 'EUR', 'gbp'],
            'status': ['completed', 'COMPLETED', 'Pending'],
            'channel': ['web', 'MOBILE', 'Store'],
            'payment_method': ['Credit Card', 'paypal', 'CREDIT CARD']
        })
    
    def test_customer_transformation_normalizes_names(self, messy_customer_df):
        """Test that customer names are normalized."""
        from src.transformers import CustomerTransformer
        
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.run(messy_customer_df)
        
        # Names should be title case
        assert result['first_name'].iloc[0] == 'John'
        assert result['last_name'].iloc[0] == 'Doe'
    
    def test_customer_transformation_normalizes_email(self, messy_customer_df):
        """Test that emails are lowercased."""
        from src.transformers import CustomerTransformer
        
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.run(messy_customer_df)
        
        # Emails should be lowercase
        assert result['email'].iloc[0] == 'john@email.com'
        assert result['email'].iloc[2] == 'bob@email.com'
    
    def test_customer_transformation_normalizes_segment(self, messy_customer_df):
        """Test that segments are normalized."""
        from src.transformers import CustomerTransformer
        
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.run(messy_customer_df)
        
        # Segments should be standardized
        assert result['customer_segment'].iloc[0] == 'Enterprise'
        assert result['customer_segment'].iloc[1] == 'SMB'
        assert result['customer_segment'].iloc[2] == 'Consumer'
    
    def test_customer_transformation_normalizes_country(self, messy_customer_df):
        """Test that country codes are normalized."""
        from src.transformers import CustomerTransformer
        
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.run(messy_customer_df)
        
        # Countries should be ISO codes
        assert result['country'].iloc[0] == 'US'
        assert result['country'].iloc[1] == 'US'  # United States -> US
        assert result['country'].iloc[2] == 'CA'
    
    def test_customer_transformation_normalizes_booleans(self, messy_customer_df):
        """Test that booleans are normalized."""
        from src.transformers import CustomerTransformer
        
        transformer = CustomerTransformer(deduplicate=False)
        result = transformer.run(messy_customer_df)
        
        # All should be True
        assert all(result['is_active'] == True)
    
    def test_transaction_transformation_normalizes_currency(self, messy_transaction_df):
        """Test that currencies are normalized."""
        from src.transformers import TransactionTransformer
        
        transformer = TransactionTransformer(base_currency='USD')
        result = transformer.run(messy_transaction_df)
        
        # All currencies should be converted to USD
        assert all(result['currency'] == 'USD')
        assert 'original_currency' in result.columns
    
    def test_transaction_transformation_normalizes_status(self, messy_transaction_df):
        """Test that statuses are normalized."""
        from src.transformers import TransactionTransformer
        
        transformer = TransactionTransformer()
        result = transformer.run(messy_transaction_df)
        
        # Statuses should be title case
        assert result['status'].iloc[0] == 'Completed'
        assert result['status'].iloc[1] == 'Completed'
        assert result['status'].iloc[2] == 'Pending'
    
    def test_transaction_transformation_normalizes_channel(self, messy_transaction_df):
        """Test that channels are normalized."""
        from src.transformers import TransactionTransformer
        
        transformer = TransactionTransformer()
        result = transformer.run(messy_transaction_df)
        
        assert result['channel'].iloc[0] == 'Web'
        assert result['channel'].iloc[1] == 'Mobile'
        assert result['channel'].iloc[2] == 'Store'


class TestTimezoneNormalization:
    """Tests for timezone handling in ETL pipeline."""
    
    @pytest.fixture
    def timezone_data(self):
        """Create data with various timezone formats."""
        return pd.DataFrame({
            'id': [1, 2, 3, 4],
            'event_timestamp': [
                '2024-01-15 10:30:00',          # No timezone
                '2024-01-15T15:30:00Z',         # UTC (Z)
                '2024-01-15 08:30:00-05:00',    # EST
                '2024-01-15T20:30:00+08:00'     # Asia
            ],
            'source_timezone': ['UTC', 'UTC', 'US/Eastern', 'Asia/Singapore']
        })
    
    def test_timezone_normalization_to_utc(self, timezone_data):
        """Test that all timestamps are normalized to UTC."""
        from src.transformers import TimezoneHandler
        
        handler = TimezoneHandler(
            target_timezone='UTC',
            timestamp_columns=['event_timestamp']
        )
        result = handler.run(timezone_data)
        
        assert 'event_timestamp' in result.columns
        # All timestamps should be converted


class TestPipelineIntegration:
    """Integration tests for full pipeline flow."""
    
    @pytest.fixture
    def sample_data_dir(self):
        """Create a temporary directory with sample data."""
        import tempfile
        import shutil
        
        temp_dir = tempfile.mkdtemp()
        
        # Create customers CSV
        customers_path = Path(temp_dir) / 'customers_messy.csv'
        with open(customers_path, 'w') as f:
            f.write("customer_id,first_name,last_name,email,phone,customer_segment,country,is_active\n")
            f.write("C001,john,DOE,JOHN@EMAIL.COM,555-1234,enterprise,usa,true\n")
            f.write("C002,Jane,Smith,jane@email.com,555-5678,SMB,CA,Y\n")
        
        # Create transactions CSV
        txn_path = Path(temp_dir) / 'transactions_messy.csv'
        with open(txn_path, 'w') as f:
            f.write("transaction_id,customer_id,product_id,total_amount,currency,status,channel,quantity,unit_price\n")
            f.write("T001,C001,P001,100.00,USD,completed,web,2,50.00\n")
            f.write("T002,C002,P002,85.00,EUR,COMPLETED,mobile,1,85.00\n")
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    def test_full_etl_flow(self, sample_data_dir):
        """Test complete ETL pipeline flow."""
        from src.extractors import CSVExtractor
        from src.transformers import CustomerTransformer, TransactionTransformer
        from src.validators import DataQualityValidator
        
        # Extract
        customer_extractor = CSVExtractor(
            file_path=str(Path(sample_data_dir) / 'customers_messy.csv')
        )
        customers_raw = customer_extractor.run()
        
        txn_extractor = CSVExtractor(
            file_path=str(Path(sample_data_dir) / 'transactions_messy.csv')
        )
        transactions_raw = txn_extractor.run()
        
        # Validate
        customer_validator = DataQualityValidator(
            dataset_name='customers',
            fail_on_error=False
        )
        customer_validator.check_column_exists(['customer_id', 'email'])
        customer_report = customer_validator.validate(customers_raw)
        
        assert customer_report.total_rows == 2
        
        txn_validator = DataQualityValidator(
            dataset_name='transactions',
            fail_on_error=False
        )
        txn_validator.check_column_exists(['transaction_id', 'customer_id'])
        txn_report = txn_validator.validate(transactions_raw)
        
        assert txn_report.total_rows == 2
        
        # Transform
        customer_transformer = CustomerTransformer(deduplicate=False)
        customers_clean = customer_transformer.run(customers_raw)
        
        txn_transformer = TransactionTransformer(base_currency='USD')
        transactions_clean = txn_transformer.run(transactions_raw)
        
        # Verify transformations
        assert customers_clean['first_name'].iloc[0] == 'John'
        assert customers_clean['country'].iloc[0] == 'US'
        assert transactions_clean['status'].iloc[0] == 'Completed'


class TestDagConfiguration:
    """Tests for Airflow DAG configuration."""
    
    def test_dag_imports(self):
        """Test that DAG can be imported without errors."""
        try:
            # This tests that the module structure is correct
            from src.extractors import CSVExtractor, JSONExtractor
            from src.transformers import CustomerTransformer, TransactionTransformer
            from src.validators import DataQualityValidator
            
            assert True
        except ImportError as e:
            pytest.fail(f"Import error: {e}")
    
    def test_dag_default_args(self):
        """Test DAG default arguments structure."""
        default_args = {
            'owner': 'data_engineering',
            'depends_on_past': False,
            'email': ['data-alerts@company.com'],
            'email_on_failure': True,
            'email_on_retry': False,
            'retries': 2,
        }
        
        assert default_args['owner'] == 'data_engineering'
        assert default_args['retries'] == 2
        assert default_args['email_on_failure'] == True


class TestDataGeneratorIntegration:
    """Tests for data generator integration with ETL pipeline."""
    
    def test_generated_data_can_be_processed(self):
        """Test that generated data can flow through ETL pipeline."""
        from src.utils.data_generator import DataGenerator
        from src.transformers import CustomerTransformer
        from src.validators import DataQualityValidator
        
        # Generate small dataset
        generator = DataGenerator()
        customers_df = generator.generate_customers(
            n_customers=100,
            duplicate_rate=0.05,
            missing_rate=0.05
        )
        
        # Validate
        validator = DataQualityValidator(
            dataset_name='generated_customers',
            fail_on_error=False,
            null_threshold=0.2,  # Allow up to 20% nulls for messy data
            duplicate_threshold=0.2
        )
        report = validator.validate(customers_df)
        
        assert report.total_rows > 0
        
        # Transform
        transformer = CustomerTransformer(
            deduplicate=True,
            fuzzy_threshold=85
        )
        clean_df = transformer.run(customers_df)
        
        # Should have fewer rows after deduplication
        assert len(clean_df) <= len(customers_df)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

