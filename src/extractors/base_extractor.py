"""Base extractor class defining the interface for all extractors."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class BaseExtractor(ABC):
    """
    Abstract base class for all data extractors.
    
    Provides common functionality and defines the interface
    that all extractors must implement.
    """
    
    def __init__(self, source_name: str):
        """
        Initialize the extractor.
        
        Args:
            source_name: Name of the data source for logging
        """
        self.source_name = source_name
        self.extraction_timestamp = None
        self.rows_extracted = 0
        self.metadata: Dict[str, Any] = {}
    
    @abstractmethod
    def extract(self, **kwargs) -> pd.DataFrame:
        """
        Extract data from the source.
        
        Returns:
            DataFrame containing the extracted data
        """
        pass
    
    @abstractmethod
    def validate_source(self) -> bool:
        """
        Validate that the data source is accessible.
        
        Returns:
            True if source is valid and accessible
        """
        pass
    
    def pre_extract(self) -> None:
        """Hook called before extraction starts."""
        self.extraction_timestamp = datetime.now()
        logger.info(
            "Starting extraction",
            source=self.source_name,
            timestamp=self.extraction_timestamp.isoformat()
        )
    
    def post_extract(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Hook called after extraction completes.
        
        Args:
            df: Extracted DataFrame
            
        Returns:
            Processed DataFrame with metadata
        """
        self.rows_extracted = len(df)
        
        # Add extraction metadata
        df['_extracted_at'] = self.extraction_timestamp
        df['_source'] = self.source_name
        
        self.metadata = {
            'source': self.source_name,
            'extracted_at': self.extraction_timestamp.isoformat(),
            'rows_extracted': self.rows_extracted,
            'columns': list(df.columns)
        }
        
        logger.info(
            "Extraction complete",
            source=self.source_name,
            rows=self.rows_extracted
        )
        
        return df
    
    def run(self, **kwargs) -> pd.DataFrame:
        """
        Execute the full extraction process.
        
        Args:
            **kwargs: Arguments passed to extract()
            
        Returns:
            Extracted DataFrame
        """
        if not self.validate_source():
            raise ValueError(f"Invalid source: {self.source_name}")
        
        self.pre_extract()
        df = self.extract(**kwargs)
        df = self.post_extract(df)
        
        return df
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get extraction metadata."""
        return self.metadata

