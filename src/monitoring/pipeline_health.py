"""Pipeline health monitoring utilities."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.db_utils import DatabaseUtils
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class PipelineStatus(Enum):
    """Pipeline execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass
class PipelineMetrics:
    """Metrics for a pipeline run."""
    dag_id: str
    run_id: str
    status: PipelineStatus
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[int]
    rows_processed: int
    errors: List[str] = field(default_factory=list)
    
    @property
    def is_healthy(self) -> bool:
        """Check if pipeline run was healthy."""
        return self.status == PipelineStatus.SUCCESS


class PipelineHealthMonitor:
    """
    Monitor pipeline health and execution metrics.
    
    Tracks:
    - Pipeline success/failure rates
    - Execution durations
    - Data volume anomalies
    - SLA compliance
    """
    
    def __init__(self, db: Optional[DatabaseUtils] = None):
        """
        Initialize the pipeline health monitor.
        
        Args:
            db: Database utilities instance
        """
        self.db = db
        self._metrics_cache: Dict[str, PipelineMetrics] = {}
    
    def log_pipeline_start(
        self,
        dag_id: str,
        run_id: str,
        execution_date: datetime
    ) -> None:
        """
        Log the start of a pipeline run.
        
        Args:
            dag_id: DAG identifier
            run_id: Run identifier
            execution_date: Execution date
        """
        metrics = PipelineMetrics(
            dag_id=dag_id,
            run_id=run_id,
            status=PipelineStatus.RUNNING,
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=None,
            rows_processed=0
        )
        self._metrics_cache[run_id] = metrics
        
        if self.db:
            self.db.execute_query("""
                INSERT INTO analytics._pipeline_log 
                (dag_id, dag_run_id, execution_date, start_time, status)
                VALUES (:dag_id, :run_id, :exec_date, :start_time, 'running')
            """, {
                'dag_id': dag_id,
                'run_id': run_id,
                'exec_date': execution_date,
                'start_time': metrics.start_time
            })
        
        logger.info("Pipeline started", dag_id=dag_id, run_id=run_id)
    
    def log_pipeline_end(
        self,
        run_id: str,
        status: PipelineStatus,
        rows_processed: int = 0,
        error_message: Optional[str] = None
    ) -> PipelineMetrics:
        """
        Log the end of a pipeline run.
        
        Args:
            run_id: Run identifier
            status: Final status
            rows_processed: Number of rows processed
            error_message: Error message if failed
            
        Returns:
            Updated pipeline metrics
        """
        metrics = self._metrics_cache.get(run_id)
        
        if metrics:
            metrics.end_time = datetime.now()
            metrics.status = status
            metrics.rows_processed = rows_processed
            metrics.duration_seconds = int(
                (metrics.end_time - metrics.start_time).total_seconds()
            )
            if error_message:
                metrics.errors.append(error_message)
        else:
            metrics = PipelineMetrics(
                dag_id='unknown',
                run_id=run_id,
                status=status,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=0,
                rows_processed=rows_processed,
                errors=[error_message] if error_message else []
            )
        
        if self.db:
            self.db.execute_query("""
                UPDATE analytics._pipeline_log
                SET end_time = :end_time,
                    duration_seconds = :duration,
                    status = :status,
                    rows_processed = :rows,
                    error_message = :error
                WHERE dag_run_id = :run_id
            """, {
                'end_time': metrics.end_time,
                'duration': metrics.duration_seconds,
                'status': status.value,
                'rows': rows_processed,
                'error': error_message,
                'run_id': run_id
            })
        
        logger.info(
            "Pipeline completed",
            run_id=run_id,
            status=status.value,
            duration=metrics.duration_seconds
        )
        
        return metrics
    
    def get_pipeline_health_summary(
        self,
        dag_id: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get pipeline health summary.
        
        Args:
            dag_id: Filter by DAG ID
            days: Number of days to look back
            
        Returns:
            Health summary dictionary
        """
        if not self.db:
            return {}
        
        query = """
            SELECT 
                dag_id,
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                AVG(duration_seconds) as avg_duration,
                MAX(duration_seconds) as max_duration,
                MIN(duration_seconds) as min_duration,
                SUM(rows_processed) as total_rows_processed,
                MAX(end_time) as last_run
            FROM analytics._pipeline_log
            WHERE start_time >= CURRENT_DATE - INTERVAL ':days days'
            {dag_filter}
            GROUP BY dag_id
        """.format(
            dag_filter="AND dag_id = :dag_id" if dag_id else ""
        )
        
        params = {'days': days}
        if dag_id:
            params['dag_id'] = dag_id
        
        try:
            results = self.db.execute_query(query, params)
            
            summary = {}
            for row in results:
                summary[row['dag_id']] = {
                    'total_runs': row['total_runs'],
                    'successful_runs': row['successful_runs'],
                    'failed_runs': row['failed_runs'],
                    'success_rate': round(
                        row['successful_runs'] / row['total_runs'] * 100, 2
                    ) if row['total_runs'] > 0 else 0,
                    'avg_duration_seconds': round(row['avg_duration'] or 0, 2),
                    'max_duration_seconds': row['max_duration'],
                    'total_rows_processed': row['total_rows_processed'],
                    'last_run': row['last_run']
                }
            
            return summary
            
        except Exception as e:
            logger.error("Failed to get health summary", error=str(e))
            return {}
    
    def check_volume_anomaly(
        self,
        table_name: str,
        threshold_pct: float = 0.3
    ) -> Dict[str, Any]:
        """
        Check for data volume anomalies.
        
        Args:
            table_name: Table to check
            threshold_pct: Threshold for anomaly (30% deviation)
            
        Returns:
            Anomaly check results
        """
        if not self.db:
            return {'error': 'No database connection'}
        
        query = """
            WITH daily_counts AS (
                SELECT 
                    _loaded_at::DATE as load_date,
                    COUNT(*) as row_count
                FROM analytics.{table}
                WHERE _loaded_at >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY _loaded_at::DATE
            ),
            stats AS (
                SELECT 
                    AVG(row_count) as avg_count,
                    STDDEV(row_count) as stddev_count
                FROM daily_counts
            )
            SELECT 
                dc.load_date,
                dc.row_count,
                s.avg_count,
                s.stddev_count,
                ABS(dc.row_count - s.avg_count) / NULLIF(s.avg_count, 0) as deviation_pct
            FROM daily_counts dc
            CROSS JOIN stats s
            ORDER BY dc.load_date DESC
            LIMIT 1
        """.format(table=table_name)
        
        try:
            results = self.db.execute_query(query)
            
            if not results:
                return {'table': table_name, 'status': 'no_data'}
            
            latest = results[0]
            is_anomaly = (latest['deviation_pct'] or 0) > threshold_pct
            
            return {
                'table': table_name,
                'load_date': latest['load_date'],
                'row_count': latest['row_count'],
                'avg_count': round(latest['avg_count'] or 0, 2),
                'deviation_pct': round((latest['deviation_pct'] or 0) * 100, 2),
                'is_anomaly': is_anomaly,
                'status': 'anomaly_detected' if is_anomaly else 'normal'
            }
            
        except Exception as e:
            logger.error("Volume check failed", table=table_name, error=str(e))
            return {'table': table_name, 'status': 'error', 'error': str(e)}
    
    def get_data_freshness(
        self,
        table_name: str,
        timestamp_column: str = '_loaded_at'
    ) -> Dict[str, Any]:
        """
        Check data freshness for a table.
        
        Args:
            table_name: Table to check
            timestamp_column: Column with load timestamp
            
        Returns:
            Freshness check results
        """
        if not self.db:
            return {'error': 'No database connection'}
        
        query = f"""
            SELECT 
                MAX({timestamp_column}) as latest_timestamp,
                EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MAX({timestamp_column})) / 3600 as hours_since_update
            FROM analytics.{table_name}
        """
        
        try:
            results = self.db.execute_query(query)
            
            if not results or not results[0]['latest_timestamp']:
                return {'table': table_name, 'status': 'no_data'}
            
            row = results[0]
            hours_old = row['hours_since_update'] or 0
            
            return {
                'table': table_name,
                'latest_timestamp': row['latest_timestamp'],
                'hours_since_update': round(hours_old, 2),
                'is_stale': hours_old > 24,
                'status': 'stale' if hours_old > 24 else 'fresh'
            }
            
        except Exception as e:
            logger.error("Freshness check failed", table=table_name, error=str(e))
            return {'table': table_name, 'status': 'error', 'error': str(e)}

