"""Unit tests for data extractors."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.extractors import CSVExtractor, JSONExtractor


class TestCSVExtractor:
    """Tests for CSVExtractor."""
    
    @pytest.fixture
    def sample_csv_file(self):
        """Create a temporary CSV file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("id,name,value\n")
            f.write("1,Alice,100\n")
            f.write("2,Bob,200\n")
            f.write("3,Charlie,300\n")
            return f.name
    
    @pytest.fixture
    def messy_csv_file(self):
        """Create a CSV file with data quality issues."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("id,name,value,date\n")
            f.write("1,Alice,100,2024-01-15\n")
            f.write("2,,200,01/20/2024\n")  # Missing name, different date format
            f.write("3,Charlie,,2024-01-25\n")  # Missing value
            f.write("4,David,invalid,\n")  # Invalid value, missing date
            return f.name
    
    def test_basic_extraction(self, sample_csv_file):
        """Test basic CSV extraction."""
        extractor = CSVExtractor(file_path=sample_csv_file)
        df = extractor.run()
        
        assert len(df) == 3
        assert 'id' in df.columns
        assert 'name' in df.columns
        assert 'value' in df.columns
        
        # Clean up
        os.unlink(sample_csv_file)
    
    def test_metadata_added(self, sample_csv_file):
        """Test that metadata columns are added."""
        extractor = CSVExtractor(file_path=sample_csv_file)
        df = extractor.run()
        
        assert '_extracted_at' in df.columns
        assert '_source' in df.columns
        
        os.unlink(sample_csv_file)
    
    def test_encoding_detection(self, sample_csv_file):
        """Test encoding detection."""
        extractor = CSVExtractor(file_path=sample_csv_file)
        df = extractor.run()
        
        # Should successfully extract even without specifying encoding
        assert len(df) > 0
        
        os.unlink(sample_csv_file)
    
    def test_messy_data_extraction(self, messy_csv_file):
        """Test extraction of messy data."""
        extractor = CSVExtractor(file_path=messy_csv_file)
        df = extractor.run()
        
        # Should extract all rows including messy ones
        assert len(df) == 4
        
        # Should have null values
        assert df['name'].isna().sum() > 0
        
        os.unlink(messy_csv_file)
    
    def test_file_not_found(self):
        """Test handling of missing file."""
        extractor = CSVExtractor(file_path='nonexistent.csv')
        
        assert extractor.validate_source() == False
    
    def test_custom_delimiter(self):
        """Test extraction with custom delimiter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("id;name;value\n")
            f.write("1;Alice;100\n")
            f.write("2;Bob;200\n")
            file_path = f.name
        
        extractor = CSVExtractor(file_path=file_path, delimiter=';')
        df = extractor.run()
        
        assert len(df) == 2
        assert 'name' in df.columns
        
        os.unlink(file_path)


class TestJSONExtractor:
    """Tests for JSONExtractor."""
    
    @pytest.fixture
    def sample_json_file(self):
        """Create a temporary JSON file."""
        data = [
            {"id": 1, "name": "Alice", "value": 100},
            {"id": 2, "name": "Bob", "value": 200},
            {"id": 3, "name": "Charlie", "value": 300}
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            return f.name
    
    @pytest.fixture
    def nested_json_file(self):
        """Create a JSON file with nested structure."""
        data = {
            "status": "success",
            "data": {
                "items": [
                    {"id": 1, "name": "Alice", "meta": {"score": 95}},
                    {"id": 2, "name": "Bob", "meta": {"score": 87}}
                ]
            },
            "pagination": {"page": 1, "total": 2}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            return f.name
    
    @pytest.fixture
    def jsonl_file(self):
        """Create a JSON Lines file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"id": 1, "name": "Alice"}\n')
            f.write('{"id": 2, "name": "Bob"}\n')
            f.write('{"id": 3, "name": "Charlie"}\n')
            return f.name
    
    def test_basic_extraction(self, sample_json_file):
        """Test basic JSON extraction."""
        extractor = JSONExtractor(source=sample_json_file, is_api=False)
        df = extractor.run()
        
        assert len(df) == 3
        assert 'id' in df.columns
        assert 'name' in df.columns
        
        os.unlink(sample_json_file)
    
    def test_nested_extraction(self, nested_json_file):
        """Test extraction with data path."""
        extractor = JSONExtractor(
            source=nested_json_file,
            is_api=False,
            data_path='data.items',
            flatten_nested=True
        )
        df = extractor.run()
        
        assert len(df) == 2
        assert 'id' in df.columns
        # Nested meta.score should be flattened
        assert 'meta_score' in df.columns or 'score' in df.columns
        
        os.unlink(nested_json_file)
    
    def test_jsonl_extraction(self, jsonl_file):
        """Test JSON Lines extraction."""
        extractor = JSONExtractor(
            source=jsonl_file,
            is_api=False,
            json_lines=True
        )
        df = extractor.run()
        
        assert len(df) == 3
        
        os.unlink(jsonl_file)
    
    def test_metadata_added(self, sample_json_file):
        """Test that metadata is added."""
        extractor = JSONExtractor(source=sample_json_file, is_api=False)
        df = extractor.run()
        
        assert '_extracted_at' in df.columns
        assert '_source' in df.columns
        
        os.unlink(sample_json_file)
    
    def test_file_not_found(self):
        """Test handling of missing file."""
        extractor = JSONExtractor(source='nonexistent.json', is_api=False)
        
        assert extractor.validate_source() == False


class TestDatabaseExtractor:
    """Tests for DatabaseExtractor."""
    
    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        from unittest.mock import MagicMock, patch
        from sqlalchemy.engine import Engine
        
        mock_engine = MagicMock(spec=Engine)
        return mock_engine
    
    def test_connection_string_building(self):
        """Test connection string construction."""
        from src.extractors import DatabaseExtractor
        
        extractor = DatabaseExtractor(
            host='localhost',
            port=5432,
            database='test_db',
            user='test_user',
            password='test_pass',
            db_type='postgresql'
        )
        
        assert 'postgresql' in extractor.connection_string
        assert 'test_db' in extractor.connection_string
        assert 'test_user' in extractor.connection_string
    
    def test_mysql_connection_string(self):
        """Test MySQL connection string."""
        from src.extractors import DatabaseExtractor
        
        extractor = DatabaseExtractor(
            host='localhost',
            port=3306,
            database='test_db',
            user='test_user',
            password='test_pass',
            db_type='mysql'
        )
        
        assert 'mysql' in extractor.connection_string
    
    @patch('src.extractors.db_extractor.create_engine')
    def test_extract_with_query(self, mock_create_engine):
        """Test extraction with custom SQL query."""
        from src.extractors import DatabaseExtractor
        import pandas as pd
        from unittest.mock import MagicMock
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        df_result = pd.DataFrame({'id': [1, 2], 'name': ['A', 'B']})
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value = None
        with patch('pandas.read_sql', return_value=df_result):
            extractor = DatabaseExtractor(
                connection_string='postgresql://user:pass@host/db'
            )
            result = extractor.extract(query='SELECT * FROM test')
            
            assert len(result) == 2
            assert 'id' in result.columns


class TestStreamingExtractor:
    """Tests for StreamingExtractor."""
    
    def test_push_and_get_record(self):
        """Test pushing and retrieving records."""
        from src.extractors import StreamingExtractor
        
        extractor = StreamingExtractor(source_name='test_stream')
        
        record = {'id': 1, 'value': 100, 'timestamp': '2024-01-01T10:00:00'}
        extractor.push_record(record)
        
        batch = extractor.get_batch()
        
        assert len(batch) == 1
        assert batch['id'].iloc[0] == 1
        assert '_ingested_at' in batch.columns
    
    def test_batch_size_limit(self):
        """Test that batches respect size limits."""
        from src.extractors import StreamingExtractor
        
        extractor = StreamingExtractor(source_name='test', batch_size=5)
        
        # Push 10 records
        for i in range(10):
            extractor.push_record({'id': i, 'value': i})
        
        batch = extractor.get_batch()
        
        assert len(batch) == 5  # Should only get batch_size records
    
    def test_late_arrival_detection(self):
        """Test late arrival marking."""
        from src.extractors import StreamingExtractor
        from datetime import datetime, timedelta
        
        extractor = StreamingExtractor(
            source_name='test',
            late_arrival_threshold_seconds=3600
        )
        
        # Old record (2 hours ago)
        old_record = {
            'id': 1,
            'event_time': (datetime.now() - timedelta(hours=2)).isoformat()
        }
        
        # Recent record
        recent_record = {
            'id': 2,
            'event_time': datetime.now().isoformat()
        }
        
        extractor.push_record(old_record)
        extractor.push_record(recent_record)
        
        batch = extractor.get_batch(event_time_column='event_time')
        
        # Old record should be marked as late
        old_row = batch[batch['id'] == 1]
        assert old_row['_is_late_arrival'].iloc[0] == True
        
        # Recent record should not be late
        recent_row = batch[batch['id'] == 2]
        assert recent_row['_is_late_arrival'].iloc[0] == False
    
    def test_watermark_update(self):
        """Test watermark tracking."""
        from src.extractors import StreamingExtractor
        from datetime import datetime, timedelta
        
        extractor = StreamingExtractor(source_name='test')
        
        record = {
            'id': 1,
            'event_time': datetime.now().isoformat()
        }
        extractor.push_record(record)
        
        batch = extractor.get_batch(event_time_column='event_time')
        
        watermark = extractor.get_watermark()
        assert watermark is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

