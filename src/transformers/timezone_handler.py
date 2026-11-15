"""Timezone handling and normalization."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import pytz

from src.transformers.base_transformer import BaseTransformer
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class TimezoneHandler(BaseTransformer):
    """
    Handle timezone inconsistencies in data.
    
    Handles:
    - Converting all timestamps to UTC
    - Detecting timezone from various formats
    - Preserving original timezone info
    - Adding local time columns
    """
    
    # Common timezone abbreviations and their pytz equivalents
    TIMEZONE_MAPPING = {
        'EST': 'US/Eastern',
        'EDT': 'US/Eastern',
        'CST': 'US/Central',
        'CDT': 'US/Central',
        'MST': 'US/Mountain',
        'MDT': 'US/Mountain',
        'PST': 'US/Pacific',
        'PDT': 'US/Pacific',
        'GMT': 'GMT',
        'UTC': 'UTC',
        'BST': 'Europe/London',
        'CET': 'Europe/Paris',
        'CEST': 'Europe/Paris',
        'IST': 'Asia/Kolkata',
        'JST': 'Asia/Tokyo',
        'AEST': 'Australia/Sydney',
        'AEDT': 'Australia/Sydney'
    }
    
    def __init__(
        self,
        target_timezone: str = 'UTC',
        timestamp_columns: Optional[List[str]] = None,
        source_timezone_column: Optional[str] = None,
        default_timezone: str = 'UTC',
        add_local_time: bool = False,
        local_timezones: Optional[List[str]] = None
    ):
        """
        Initialize the timezone handler.
        
        Args:
            target_timezone: Target timezone for conversion
            timestamp_columns: List of timestamp columns to process
            source_timezone_column: Column containing source timezone info
            default_timezone: Default timezone when not specified
            add_local_time: Whether to add local time columns
            local_timezones: Timezones for local time columns
        """
        super().__init__(name="TimezoneHandler")
        self.target_timezone = target_timezone
        self.timestamp_columns = timestamp_columns
        self.source_tz_column = source_timezone_column
        self.default_timezone = default_timezone
        self.add_local_time = add_local_time
        self.local_timezones = local_timezones or ['US/Eastern', 'US/Pacific', 'Europe/London']
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Transform timestamps to target timezone.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Transformed DataFrame with normalized timezones
        """
        df = df.copy()
        
        # Auto-detect timestamp columns if not specified
        if not self.timestamp_columns:
            self.timestamp_columns = self._detect_timestamp_columns(df)
        
        logger.info(
            "Processing timestamp columns",
            columns=self.timestamp_columns
        )
        
        # Process each timestamp column
        for col in self.timestamp_columns:
            if col not in df.columns:
                continue
            
            df = self._process_timestamp_column(df, col)
        
        # Add local time columns if requested
        if self.add_local_time:
            df = self._add_local_time_columns(df)
        
        return df
    
    def _detect_timestamp_columns(self, df: pd.DataFrame) -> List[str]:
        """Auto-detect timestamp columns in DataFrame."""
        timestamp_cols = []
        
        for col in df.columns:
            # Check column name patterns
            col_lower = col.lower()
            if any(pattern in col_lower for pattern in 
                   ['timestamp', 'datetime', 'date', 'time', 'created', 'updated', 'at']):
                timestamp_cols.append(col)
                continue
            
            # Check data type
            if df[col].dtype == 'datetime64[ns]':
                timestamp_cols.append(col)
                continue
            
            # Try parsing sample values
            sample = df[col].dropna().head(100)
            if len(sample) > 0:
                try:
                    parsed = pd.to_datetime(sample, errors='coerce')
                    if parsed.notna().mean() > 0.8:
                        timestamp_cols.append(col)
                except Exception:
                    pass
        
        return timestamp_cols
    
    def _process_timestamp_column(
        self,
        df: pd.DataFrame,
        column: str
    ) -> pd.DataFrame:
        """
        Process a single timestamp column.
        
        Args:
            df: Input DataFrame
            column: Column name to process
            
        Returns:
            DataFrame with processed column
        """
        # Store original value
        df[f'{column}_original'] = df[column]
        
        # Parse timestamps
        df[column] = self._parse_timestamps(df[column])
        
        # Detect source timezone for each row
        if self.source_tz_column and self.source_tz_column in df.columns:
            source_tz = df[self.source_tz_column].apply(self._normalize_timezone)
        else:
            # Try to extract timezone from the original values
            source_tz = df[f'{column}_original'].apply(self._extract_timezone)
        
        df[f'{column}_source_tz'] = source_tz
        
        # Convert to target timezone
        df[column] = df.apply(
            lambda row: self._convert_to_target_tz(
                row[column],
                row[f'{column}_source_tz']
            ),
            axis=1
        )
        
        # Count timezone conversions
        tz_counts = df[f'{column}_source_tz'].value_counts()
        logger.info(
            "Timezone conversion complete",
            column=column,
            timezone_distribution=tz_counts.to_dict()
        )
        
        return df
    
    def _parse_timestamps(self, series: pd.Series) -> pd.Series:
        """Parse timestamps from various formats."""
        # Try parsing with pandas
        parsed = pd.to_datetime(series, errors='coerce', utc=True)
        
        # For values that failed, try additional formats
        failed_mask = parsed.isna() & series.notna()
        if failed_mask.any():
            additional_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%m/%d/%Y %H:%M:%S',
                '%d-%m-%Y %H:%M:%S',
                '%Y/%m/%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S%z'
            ]
            
            for fmt in additional_formats:
                still_failed = parsed.isna() & series.notna()
                if not still_failed.any():
                    break
                try:
                    new_parsed = pd.to_datetime(
                        series[still_failed],
                        format=fmt,
                        errors='coerce'
                    )
                    parsed = parsed.fillna(new_parsed)
                except Exception:
                    pass
        
        return parsed
    
    def _extract_timezone(self, value: Any) -> str:
        """Extract timezone from a timestamp string."""
        if pd.isna(value):
            return self.default_timezone
        
        value_str = str(value)
        
        # Check for timezone abbreviations
        for abbrev, tz in self.TIMEZONE_MAPPING.items():
            if abbrev in value_str:
                return tz
        
        # Check for offset patterns like +05:30 or -08:00
        import re
        offset_match = re.search(r'([+-])(\d{2}):?(\d{2})', value_str)
        if offset_match:
            sign, hours, minutes = offset_match.groups()
            total_offset = int(hours) * 60 + int(minutes)
            if sign == '-':
                total_offset = -total_offset
            
            # Map common offsets to timezones
            offset_map = {
                0: 'UTC',
                -300: 'US/Eastern',
                -360: 'US/Central',
                -420: 'US/Mountain',
                -480: 'US/Pacific',
                60: 'Europe/Paris',
                330: 'Asia/Kolkata',
                540: 'Asia/Tokyo'
            }
            return offset_map.get(total_offset, 'UTC')
        
        # Check for 'Z' (Zulu/UTC)
        if value_str.endswith('Z'):
            return 'UTC'
        
        return self.default_timezone
    
    def _normalize_timezone(self, tz_value: Any) -> str:
        """Normalize timezone string to pytz timezone."""
        if pd.isna(tz_value):
            return self.default_timezone
        
        tz_str = str(tz_value).strip().upper()
        
        # Check mapping
        if tz_str in self.TIMEZONE_MAPPING:
            return self.TIMEZONE_MAPPING[tz_str]
        
        # Try as pytz timezone
        try:
            pytz.timezone(tz_value)
            return tz_value
        except Exception:
            pass
        
        return self.default_timezone
    
    def _convert_to_target_tz(
        self,
        timestamp: pd.Timestamp,
        source_tz: str
    ) -> Optional[pd.Timestamp]:
        """Convert timestamp from source to target timezone."""
        if pd.isna(timestamp):
            return None
        
        try:
            # If timestamp is timezone-naive, localize it
            if timestamp.tzinfo is None:
                source_pytz = pytz.timezone(source_tz)
                timestamp = source_pytz.localize(timestamp.to_pydatetime())
            
            # Convert to target timezone
            target_pytz = pytz.timezone(self.target_timezone)
            converted = timestamp.astimezone(target_pytz)
            
            return pd.Timestamp(converted)
        except Exception as e:
            logger.warning(
                "Timezone conversion failed",
                timestamp=str(timestamp),
                source_tz=source_tz,
                error=str(e)
            )
            return timestamp
    
    def _add_local_time_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add columns with local times in specified timezones."""
        for col in self.timestamp_columns:
            if col not in df.columns:
                continue
            
            for tz in self.local_timezones:
                tz_name = tz.replace('/', '_').replace(' ', '_')
                new_col = f'{col}_{tz_name}'
                
                df[new_col] = df[col].apply(
                    lambda x: self._convert_single_timestamp(x, tz)
                )
        
        return df
    
    def _convert_single_timestamp(
        self,
        timestamp: pd.Timestamp,
        target_tz: str
    ) -> Optional[pd.Timestamp]:
        """Convert a single timestamp to target timezone."""
        if pd.isna(timestamp):
            return None
        
        try:
            target_pytz = pytz.timezone(target_tz)
            converted = timestamp.astimezone(target_pytz)
            return pd.Timestamp(converted)
        except Exception:
            return timestamp

