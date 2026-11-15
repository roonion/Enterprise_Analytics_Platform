"""Base transformer class defining the interface for all transformers."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class BaseTransformer(ABC):
    """
    Abstract base class for all data transformers.
    
    Provides common functionality and defines the interface
    that all transformers must implement.
    """
    
    def __init__(self, name: str):
        """
        Initialize the transformer.
        
        Args:
            name: Name of the transformer for logging
        """
        self.name = name
        self.transform_timestamp = None
        self.rows_input = 0
        self.rows_output = 0
        self.metadata: Dict[str, Any] = {}
    
    @abstractmethod
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Transform the input DataFrame.
        
        Args:
            df: Input DataFrame
            **kwargs: Additional transformation arguments
            
        Returns:
            Transformed DataFrame
        """
        pass
    
    def validate_input(self, df: pd.DataFrame) -> bool:
        """
        Validate input DataFrame before transformation.
        
        Args:
            df: Input DataFrame to validate
            
        Returns:
            True if validation passes
        """
        if df is None or df.empty:
            logger.warning("Empty DataFrame provided", transformer=self.name)
            return False
        return True
    
    def pre_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Hook called before transformation starts.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Preprocessed DataFrame
        """
        self.transform_timestamp = datetime.now()
        self.rows_input = len(df)
        
        logger.info(
            "Starting transformation",
            transformer=self.name,
            input_rows=self.rows_input
        )
        
        return df
    
    def post_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Hook called after transformation completes.
        
        Args:
            df: Transformed DataFrame
            
        Returns:
            Post-processed DataFrame
        """
        self.rows_output = len(df)
        
        # Add transformation metadata
        df['_transformed_at'] = self.transform_timestamp
        df['_transformer'] = self.name
        
        self.metadata = {
            'transformer': self.name,
            'transformed_at': self.transform_timestamp.isoformat(),
            'rows_input': self.rows_input,
            'rows_output': self.rows_output,
            'rows_changed': self.rows_input - self.rows_output
        }
        
        logger.info(
            "Transformation complete",
            transformer=self.name,
            input_rows=self.rows_input,
            output_rows=self.rows_output
        )
        
        return df
    
    def run(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Execute the full transformation pipeline.
        
        Args:
            df: Input DataFrame
            **kwargs: Arguments passed to transform()
            
        Returns:
            Transformed DataFrame
        """
        if not self.validate_input(df):
            return pd.DataFrame()
        
        df = self.pre_transform(df)
        df = self.transform(df, **kwargs)
        df = self.post_transform(df)
        
        return df
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get transformation metadata."""
        return self.metadata


class CompositeTransformer(BaseTransformer):
    """
    Transformer that chains multiple transformers together.
    """
    
    def __init__(self, name: str, transformers: List[BaseTransformer]):
        """
        Initialize the composite transformer.
        
        Args:
            name: Name of the composite transformer
            transformers: List of transformers to chain
        """
        super().__init__(name)
        self.transformers = transformers
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Apply all transformers in sequence.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Transformed DataFrame
        """
        result = df.copy()
        
        for transformer in self.transformers:
            result = transformer.transform(result, **kwargs)
            logger.debug(
                "Applied transformer",
                transformer=transformer.name,
                rows=len(result)
            )
        
        return result

