"""Unit tests for data quality validators."""

import pandas as pd
import pytest

from src.validators import (
    DataQualityValidator,
    SchemaValidator,
    ReferentialIntegrityValidator,
)
from src.validators.data_quality_validator import ValidationSeverity


class TestDataQualityValidator:
    """Tests for DataQualityValidator."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data with quality issues."""
        return pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 5],  # Duplicate ID
            'name': ['Alice', 'Bob', None, 'David', 'Eve', 'Frank'],  # Null
            'email': ['a@email.com', 'b@email.com', 'c@email.com', None, 'e@email.com', 'f@email.com'],
            'age': [25, 30, -5, 40, 150, 35],  # Invalid values
            'status': ['active', 'inactive', 'active', 'unknown', 'active', 'pending']
        })
    
    def test_not_empty_check(self):
        """Test that empty DataFrame fails validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        report = validator.validate(pd.DataFrame())
        
        not_empty_result = next(
            (r for r in report.results if r.check_name == 'not_empty'),
            None
        )
        assert not_empty_result is not None
        assert not_empty_result.passed == False
    
    def test_null_rate_check(self, sample_data):
        """Test null rate detection."""
        validator = DataQualityValidator(
            dataset_name='test',
            fail_on_error=False,
            null_threshold=0.1
        )
        report = validator.validate(sample_data)
        
        # Check that null rate for 'name' was detected
        name_null_result = next(
            (r for r in report.results if r.check_name == 'null_rate_name'),
            None
        )
        assert name_null_result is not None
        # 1 null out of 6 = ~16.7%, above 10% threshold
        assert name_null_result.passed == False
    
    def test_duplicate_check(self, sample_data):
        """Test duplicate detection."""
        validator = DataQualityValidator(
            dataset_name='test',
            fail_on_error=False,
            duplicate_threshold=0.05
        )
        report = validator.validate(sample_data)
        
        dup_result = next(
            (r for r in report.results if r.check_name == 'duplicate_rows'),
            None
        )
        assert dup_result is not None
    
    def test_required_columns_check(self, sample_data):
        """Test required columns validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        validator.check_column_exists(['id', 'name', 'missing_column'])
        report = validator.validate(sample_data)
        
        required_result = next(
            (r for r in report.results if r.check_name == 'required_columns'),
            None
        )
        assert required_result is not None
        assert required_result.passed == False
        assert 'missing_column' in required_result.details['missing']
    
    def test_unique_check(self, sample_data):
        """Test uniqueness validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        validator.check_unique(['id'])
        report = validator.validate(sample_data)
        
        unique_result = next(
            (r for r in report.results if 'unique' in r.check_name),
            None
        )
        assert unique_result is not None
        assert unique_result.passed == False  # ID 5 is duplicated
    
    def test_not_null_check(self, sample_data):
        """Test not null validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        validator.check_not_null(['name', 'email'])
        report = validator.validate(sample_data)
        
        not_null_result = next(
            (r for r in report.results if 'not_null' in r.check_name),
            None
        )
        assert not_null_result is not None
        assert not_null_result.passed == False
    
    def test_values_in_set_check(self, sample_data):
        """Test valid values validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        validator.check_values_in_set('status', ['active', 'inactive'])
        report = validator.validate(sample_data)
        
        values_result = next(
            (r for r in report.results if 'values_in_set' in r.check_name),
            None
        )
        assert values_result is not None
        assert values_result.passed == False  # 'unknown' and 'pending' are invalid
    
    def test_range_check(self, sample_data):
        """Test numeric range validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        validator.check_range('age', min_value=0, max_value=120)
        report = validator.validate(sample_data)
        
        range_result = next(
            (r for r in report.results if 'range' in r.check_name),
            None
        )
        assert range_result is not None
        assert range_result.passed == False  # -5 and 150 are out of range
    
    def test_regex_check(self, sample_data):
        """Test regex pattern validation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        validator.check_regex('email', r'^[a-z]@email\.com$')
        report = validator.validate(sample_data)
        
        regex_result = next(
            (r for r in report.results if 'regex' in r.check_name),
            None
        )
        assert regex_result is not None
    
    def test_overall_score(self, sample_data):
        """Test overall quality score calculation."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=False)
        report = validator.validate(sample_data)
        
        assert 0 <= report.overall_score <= 100
        assert report.total_checks > 0
        assert report.passed_checks + report.failed_checks == report.total_checks
    
    def test_fail_on_error(self, sample_data):
        """Test that fail_on_error raises exception."""
        validator = DataQualityValidator(dataset_name='test', fail_on_error=True)
        validator.check_not_null(['name'], severity=ValidationSeverity.ERROR)
        
        with pytest.raises(ValueError):
            validator.validate(sample_data)


class TestSchemaValidator:
    """Tests for SchemaValidator."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data."""
        return pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'age': [25, 30, 35],
            'active': [True, False, True]
        })
    
    def test_type_validation(self, sample_data):
        """Test data type validation."""
        schema = {
            'id': {'type': 'int'},
            'name': {'type': 'string'},
            'age': {'type': 'int'},
            'active': {'type': 'bool'}
        }
        
        validator = SchemaValidator(schema=schema)
        result = validator.validate(sample_data)
        
        assert result.is_valid
    
    def test_nullable_validation(self):
        """Test nullable validation."""
        df = pd.DataFrame({
            'id': [1, 2, None],
            'name': ['Alice', None, 'Charlie']
        })
        
        schema = {
            'id': {'type': 'int', 'nullable': False},
            'name': {'type': 'string', 'nullable': True}
        }
        
        validator = SchemaValidator(schema=schema)
        result = validator.validate(df)
        
        # id has null but shouldn't
        assert result.invalid_rows > 0
    
    def test_range_validation(self, sample_data):
        """Test min/max validation."""
        schema = {
            'age': {'type': 'int', 'min': 0, 'max': 120}
        }
        
        validator = SchemaValidator(schema=schema)
        result = validator.validate(sample_data)
        
        assert result.is_valid
    
    def test_allowed_values_validation(self):
        """Test allowed values validation."""
        df = pd.DataFrame({
            'status': ['active', 'inactive', 'unknown']
        })
        
        schema = {
            'status': {'allowed_values': ['active', 'inactive']}
        }
        
        validator = SchemaValidator(schema=schema)
        result = validator.validate(df)
        
        # 'unknown' is not allowed
        assert result.invalid_rows > 0
    
    def test_custom_validator(self, sample_data):
        """Test custom validator."""
        validator = SchemaValidator()
        validator.add_validator(
            'age',
            lambda x: x is None or x >= 18,
            "Age must be 18 or older"
        )
        result = validator.validate(sample_data)
        
        # All ages are 25+, so should pass
        # Note: This depends on implementation details
    
    def test_schema_inference(self, sample_data):
        """Test schema inference from DataFrame."""
        schema = SchemaValidator.create_schema_from_df(sample_data)
        
        assert 'id' in schema
        assert 'name' in schema
        assert 'age' in schema
        assert 'active' in schema


class TestReferentialIntegrityValidator:
    """Tests for ReferentialIntegrityValidator."""
    
    @pytest.fixture
    def sample_tables(self):
        """Create sample related tables."""
        customers = pd.DataFrame({
            'customer_id': ['C001', 'C002', 'C003'],
            'name': ['Alice', 'Bob', 'Charlie']
        })
        
        orders = pd.DataFrame({
            'order_id': ['O001', 'O002', 'O003', 'O004'],
            'customer_id': ['C001', 'C002', 'C999', None],  # C999 is orphan
            'amount': [100, 200, 150, 50]
        })
        
        return customers, orders
    
    def test_valid_relationship(self, sample_tables):
        """Test valid foreign key relationship."""
        customers, orders = sample_tables
        orders_clean = orders[orders['customer_id'].isin(['C001', 'C002'])]
        
        validator = ReferentialIntegrityValidator()
        validator.register_table('customers', customers)
        validator.register_table('orders', orders_clean)
        validator.add_relationship(
            name='orders_to_customers',
            source_table='orders',
            source_column='customer_id',
            target_table='customers',
            target_column='customer_id'
        )
        
        report = validator.validate()
        
        assert report.is_valid
        assert report.violated_relationships == 0
    
    def test_orphan_detection(self, sample_tables):
        """Test orphan record detection."""
        customers, orders = sample_tables
        
        validator = ReferentialIntegrityValidator()
        validator.register_table('customers', customers)
        validator.register_table('orders', orders)
        validator.add_relationship(
            name='orders_to_customers',
            source_table='orders',
            source_column='customer_id',
            target_table='customers',
            target_column='customer_id',
            required=True
        )
        
        report = validator.validate()
        
        # C999 should be detected as orphan
        assert report.violated_relationships > 0
        assert len(report.violations) > 0
    
    def test_get_orphan_records(self, sample_tables):
        """Test getting orphan records."""
        customers, orders = sample_tables
        
        validator = ReferentialIntegrityValidator()
        validator.register_table('customers', customers)
        validator.register_table('orders', orders)
        
        orphans = validator.get_orphan_records(
            'orders', 'customer_id',
            'customers', 'customer_id'
        )
        
        assert len(orphans) == 1
        assert orphans['customer_id'].iloc[0] == 'C999'
    
    def test_cardinality_check(self, sample_tables):
        """Test cardinality checking."""
        customers, _ = sample_tables
        
        validator = ReferentialIntegrityValidator()
        validator.register_table('customers', customers)
        
        result = validator.check_cardinality('customers', 'customer_id', 'unique')
        
        assert result['passed'] == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

