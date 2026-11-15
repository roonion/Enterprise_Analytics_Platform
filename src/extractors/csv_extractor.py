"""CSV file extractor with handling for messy data."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.extractors.base_extractor import BaseExtractor
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class CSVExtractor(BaseExtractor):
    """
    Extract data from CSV files with robust handling for messy data.
    
    Handles:
    - Multiple encodings
    - Inconsistent delimiters
    - Missing headers
    - Malformed rows
    - Large files with chunking
    """
    
    def __init__(
        self,
        file_path: Union[str, Path],
        delimiter: Optional[str] = None,
        encoding: Optional[str] = None,
        has_header: bool = True,
        column_names: Optional[List[str]] = None,
        dtype: Optional[Dict[str, Any]] = None,
        parse_dates: Optional[List[str]] = None,
        chunk_size: Optional[int] = None
    ):
        """
        Initialize the CSV extractor.
        
        Args:
            file_path: Path to the CSV file
            delimiter: Column delimiter (auto-detected if None)
            encoding: File encoding (auto-detected if None)
            has_header: Whether file has a header row
            column_names: Column names if no header
            dtype: Column data types
            parse_dates: Columns to parse as dates
            chunk_size: Number of rows per chunk for large files
        """
        self.file_path = Path(file_path)
        super().__init__(source_name=str(self.file_path))
        
        self.delimiter = delimiter
        self.encoding = encoding
        self.has_header = has_header
        self.column_names = column_names
        self.dtype = dtype or {}
        self.parse_dates = parse_dates or []
        self.chunk_size = chunk_size
        
        # Auto-detected settings
        self._detected_encoding = None
        self._detected_delimiter = None
    
    def validate_source(self) -> bool:
        """Check if the CSV file exists and is readable."""
        if not self.file_path.exists():
            logger.error("CSV file not found", path=str(self.file_path))
            return False
        
        if not self.file_path.is_file():
            logger.error("Path is not a file", path=str(self.file_path))
            return False
        
        # Check file is readable
        try:
            with open(self.file_path, 'rb') as f:
                f.read(1024)
            return True
        except Exception as e:
            logger.error("Cannot read file", path=str(self.file_path), error=str(e))
            return False
    
    def _detect_encoding(self) -> str:
        """Detect file encoding."""
        encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-16']
        
        for encoding in encodings_to_try:
            try:
                with open(self.file_path, 'r', encoding=encoding) as f:
                    f.read(10000)
                self._detected_encoding = encoding
                logger.debug("Detected encoding", encoding=encoding)
                return encoding
            except UnicodeDecodeError:
                continue
        
        # Fallback to latin-1 which accepts any byte sequence
        self._detected_encoding = 'latin-1'
        return 'latin-1'
    
    def _detect_delimiter(self, sample: str) -> str:
        """Detect column delimiter from sample data."""
        delimiters = [',', '\t', ';', '|']
        delimiter_counts = {}
        
        for d in delimiters:
            count = sample.count(d)
            if count > 0:
                delimiter_counts[d] = count
        
        if delimiter_counts:
            # Return delimiter with highest count
            detected = max(delimiter_counts, key=delimiter_counts.get)
            self._detected_delimiter = detected
            logger.debug("Detected delimiter", delimiter=repr(detected))
            return detected
        
        self._detected_delimiter = ','
        return ','
    
    def extract(self, **kwargs) -> pd.DataFrame:
        """
        Extract data from the CSV file.
        
        Args:
            **kwargs: Additional arguments passed to pd.read_csv
            
        Returns:
            DataFrame with extracted data
        """
        # Detect encoding if not specified
        encoding = self.encoding or self._detect_encoding()
        
        # Read sample for delimiter detection
        if not self.delimiter:
            with open(self.file_path, 'r', encoding=encoding) as f:
                sample = f.read(5000)
            delimiter = self._detect_delimiter(sample)
        else:
            delimiter = self.delimiter
        
        # Build read_csv arguments
        read_args = {
            'filepath_or_buffer': self.file_path,
            'sep': delimiter,
            'encoding': encoding,
            'on_bad_lines': 'warn',  # Handle malformed rows
            'low_memory': False,
            'dtype': self.dtype if self.dtype else None,
            **kwargs
        }
        
        # Handle header options
        if not self.has_header:
            read_args['header'] = None
            if self.column_names:
                read_args['names'] = self.column_names
        
        # Parse dates
        if self.parse_dates:
            read_args['parse_dates'] = self.parse_dates
        
        # Handle large files with chunking
        if self.chunk_size:
            chunks = []
            for chunk in pd.read_csv(chunksize=self.chunk_size, **read_args):
                chunks.append(chunk)
                logger.debug("Processed chunk", rows=len(chunk))
            df = pd.concat(chunks, ignore_index=True)
        else:
            df = pd.read_csv(**read_args)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Update metadata
        self.metadata.update({
            'encoding': encoding,
            'delimiter': delimiter,
            'file_size_bytes': self.file_path.stat().st_size
        })
        
        logger.info(
            "CSV extraction complete",
            file=str(self.file_path),
            rows=len(df),
            columns=len(df.columns)
        )
        
        return df
    
    def extract_with_schema_detection(self) -> pd.DataFrame:
        """
        Extract data and automatically detect column types.
        
        Returns:
            DataFrame with inferred types
        """
        # First pass: read as strings
        df = self.extract(dtype=str)
        
        # Detect and convert types
        for col in df.columns:
            if col.startswith('_'):  # Skip metadata columns
                continue
            
            # Try numeric conversion
            try:
                numeric_vals = pd.to_numeric(df[col], errors='coerce')
                if numeric_vals.notna().sum() / len(df) > 0.5:
                    df[col] = numeric_vals
                    continue
            except Exception:
                pass
            
            # Try datetime conversion
            try:
                date_vals = pd.to_datetime(df[col], errors='coerce', infer_datetime_format=True)
                if date_vals.notna().sum() / len(df) > 0.5:
                    df[col] = date_vals
                    continue
            except Exception:
                pass
            
            # Try boolean conversion
            bool_map = {'true': True, 'false': False, 'yes': True, 'no': False, 
                       '1': True, '0': False, 'y': True, 'n': False}
            if df[col].str.lower().isin(bool_map.keys()).mean() > 0.9:
                df[col] = df[col].str.lower().map(bool_map)
        
        return df

