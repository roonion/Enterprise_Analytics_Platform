"""Streaming data extractor for handling real-time data sources."""

import json
import time
from datetime import datetime, timedelta
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable, Dict, Generator, List, Optional

import pandas as pd

from src.extractors.base_extractor import BaseExtractor
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class StreamingExtractor(BaseExtractor):
    """
    Extract data from streaming sources.
    
    Supports:
    - Micro-batch processing
    - Windowed aggregations
    - Late arrival handling
    - Watermark-based processing
    """
    
    def __init__(
        self,
        source_name: str,
        batch_size: int = 1000,
        batch_timeout_seconds: float = 5.0,
        watermark_delay_seconds: int = 60,
        late_arrival_threshold_seconds: int = 3600
    ):
        """
        Initialize the streaming extractor.
        
        Args:
            source_name: Name of the streaming source
            batch_size: Maximum records per batch
            batch_timeout_seconds: Max time to wait for batch completion
            watermark_delay_seconds: Watermark delay for late data handling
            late_arrival_threshold_seconds: Threshold for marking data as late
        """
        super().__init__(source_name=source_name)
        
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout_seconds
        self.watermark_delay = timedelta(seconds=watermark_delay_seconds)
        self.late_threshold = timedelta(seconds=late_arrival_threshold_seconds)
        
        self._buffer: Queue = Queue()
        self._stop_event = Event()
        self._current_watermark: Optional[datetime] = None
        self._processing_thread: Optional[Thread] = None
    
    def validate_source(self) -> bool:
        """Validate streaming source is accessible."""
        # Override in subclass for specific validation
        return True
    
    def extract(self, **kwargs) -> pd.DataFrame:
        """
        Extract a batch of data from the stream.
        
        Returns:
            DataFrame with batch data
        """
        return self.get_batch()
    
    def push_record(self, record: Dict[str, Any]) -> None:
        """
        Push a record to the buffer.
        
        Args:
            record: Record to add to buffer
        """
        # Add ingestion timestamp
        record['_ingested_at'] = datetime.now().isoformat()
        self._buffer.put(record)
    
    def push_records(self, records: List[Dict[str, Any]]) -> None:
        """
        Push multiple records to the buffer.
        
        Args:
            records: List of records to add
        """
        for record in records:
            self.push_record(record)
    
    def get_batch(
        self,
        event_time_column: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get a batch of records from the buffer.
        
        Args:
            event_time_column: Column containing event timestamp
            
        Returns:
            DataFrame with batch data
        """
        records = []
        deadline = time.time() + self.batch_timeout
        
        while len(records) < self.batch_size and time.time() < deadline:
            try:
                timeout = max(0.1, deadline - time.time())
                record = self._buffer.get(timeout=timeout)
                records.append(record)
            except Empty:
                break
        
        if not records:
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        
        # Handle late arrivals
        if event_time_column and event_time_column in df.columns:
            df = self._mark_late_arrivals(df, event_time_column)
            self._update_watermark(df, event_time_column)
        
        logger.debug("Batch extracted", records=len(df))
        return df
    
    def _mark_late_arrivals(
        self,
        df: pd.DataFrame,
        event_time_column: str
    ) -> pd.DataFrame:
        """
        Mark records that arrived late based on watermark.
        
        Args:
            df: DataFrame to process
            event_time_column: Event time column name
            
        Returns:
            DataFrame with late arrival markers
        """
        df = df.copy()
        
        # Convert event time to datetime
        df[event_time_column] = pd.to_datetime(df[event_time_column])
        
        # Calculate late arrivals
        now = datetime.now()
        threshold = now - self.late_threshold
        
        df['_is_late_arrival'] = df[event_time_column] < threshold
        df['_arrival_delay_seconds'] = (
            now - df[event_time_column]
        ).dt.total_seconds()
        
        late_count = df['_is_late_arrival'].sum()
        if late_count > 0:
            logger.warning(
                "Late arrivals detected",
                count=int(late_count),
                max_delay_seconds=float(df['_arrival_delay_seconds'].max())
            )
        
        return df
    
    def _update_watermark(
        self,
        df: pd.DataFrame,
        event_time_column: str
    ) -> None:
        """
        Update the watermark based on processed data.
        
        Args:
            df: Processed DataFrame
            event_time_column: Event time column name
        """
        if len(df) == 0:
            return
        
        max_event_time = df[event_time_column].max()
        new_watermark = max_event_time - self.watermark_delay
        
        if self._current_watermark is None or new_watermark > self._current_watermark:
            self._current_watermark = new_watermark
            logger.debug("Watermark updated", watermark=self._current_watermark.isoformat())
    
    def stream_batches(
        self,
        event_time_column: Optional[str] = None,
        max_batches: Optional[int] = None
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Generator that yields batches as they become available.
        
        Args:
            event_time_column: Column containing event timestamp
            max_batches: Maximum number of batches to yield
            
        Yields:
            DataFrames containing batch data
        """
        batch_count = 0
        
        while not self._stop_event.is_set():
            df = self.get_batch(event_time_column=event_time_column)
            
            if len(df) > 0:
                yield df
                batch_count += 1
                
                if max_batches and batch_count >= max_batches:
                    break
            else:
                # Sleep briefly if no data
                time.sleep(0.1)
    
    def get_windowed_aggregation(
        self,
        df: pd.DataFrame,
        event_time_column: str,
        window_size_seconds: int,
        group_columns: List[str],
        aggregations: Dict[str, str]
    ) -> pd.DataFrame:
        """
        Perform windowed aggregation on streaming data.
        
        Args:
            df: DataFrame to aggregate
            event_time_column: Event time column
            window_size_seconds: Window size in seconds
            group_columns: Columns to group by
            aggregations: Dict of column -> aggregation function
            
        Returns:
            Aggregated DataFrame
        """
        df = df.copy()
        df[event_time_column] = pd.to_datetime(df[event_time_column])
        
        # Create window column
        window_size = f'{window_size_seconds}s'
        df['_window'] = df[event_time_column].dt.floor(window_size)
        
        # Aggregate
        agg_dict = {col: func for col, func in aggregations.items()}
        result = df.groupby(['_window'] + group_columns).agg(agg_dict).reset_index()
        
        return result
    
    def simulate_stream(
        self,
        source_df: pd.DataFrame,
        event_time_column: str,
        speed_multiplier: float = 1.0,
        add_late_arrivals: bool = True,
        late_arrival_rate: float = 0.05
    ) -> None:
        """
        Simulate streaming from a static DataFrame.
        
        Args:
            source_df: Source DataFrame to stream
            event_time_column: Event time column
            speed_multiplier: Playback speed multiplier
            add_late_arrivals: Whether to simulate late arrivals
            late_arrival_rate: Fraction of records to delay
        """
        import random
        
        df = source_df.copy()
        df[event_time_column] = pd.to_datetime(df[event_time_column])
        df = df.sort_values(event_time_column)
        
        records = df.to_dict(orient='records')
        start_time = df[event_time_column].min()
        base_real_time = datetime.now()
        
        for record in records:
            # Calculate delay
            event_time = record[event_time_column]
            elapsed = (event_time - start_time).total_seconds() / speed_multiplier
            target_time = base_real_time + timedelta(seconds=elapsed)
            
            # Simulate late arrivals
            if add_late_arrivals and random.random() < late_arrival_rate:
                delay = random.uniform(60, 3600)  # 1 min to 1 hour delay
                target_time += timedelta(seconds=delay)
                record['_simulated_late'] = True
            
            # Wait until target time
            wait_seconds = (target_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                time.sleep(min(wait_seconds, 1.0))  # Cap wait to 1 second
            
            self.push_record(record)
        
        logger.info("Stream simulation complete", records=len(records))
    
    def stop(self) -> None:
        """Stop the streaming extractor."""
        self._stop_event.set()
        if self._processing_thread:
            self._processing_thread.join(timeout=5)
        logger.info("Streaming extractor stopped")
    
    def get_buffer_size(self) -> int:
        """Get current buffer size."""
        return self._buffer.qsize()
    
    def get_watermark(self) -> Optional[datetime]:
        """Get current watermark."""
        return self._current_watermark

