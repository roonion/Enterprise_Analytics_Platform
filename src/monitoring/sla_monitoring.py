"""SLA monitoring for data pipelines."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from src.utils.db_utils import DatabaseUtils
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SLAStatus(Enum):
    """SLA compliance status."""
    MET = "met"
    MISSED = "missed"
    AT_RISK = "at_risk"
    PENDING = "pending"


@dataclass
class SLADefinition:
    """Definition of an SLA."""
    name: str
    dag_id: str
    target_time: time  # Expected completion time
    max_delay_minutes: int  # Grace period
    priority: str  # critical, high, medium, low
    notification_channels: List[str]
    
    def __post_init__(self):
        self.target_datetime = None


@dataclass
class SLAResult:
    """Result of an SLA check."""
    sla_name: str
    dag_id: str
    check_time: datetime
    status: SLAStatus
    target_time: datetime
    actual_time: Optional[datetime]
    delay_minutes: Optional[int]
    message: str


class SLAMonitor:
    """
    Monitor and track SLA compliance.
    
    Features:
    - Define SLAs for pipelines
    - Track compliance
    - Generate alerts
    - Historical reporting
    """
    
    def __init__(self, db: Optional[DatabaseUtils] = None):
        """
        Initialize the SLA monitor.
        
        Args:
            db: Database utilities instance
        """
        self.db = db
        self._sla_definitions: Dict[str, SLADefinition] = {}
    
    def register_sla(self, sla: SLADefinition) -> None:
        """
        Register an SLA definition.
        
        Args:
            sla: SLA definition to register
        """
        self._sla_definitions[sla.name] = sla
        logger.info("SLA registered", name=sla.name, dag_id=sla.dag_id)
    
    def check_sla(self, sla_name: str, execution_date: datetime) -> SLAResult:
        """
        Check SLA compliance for a specific run.
        
        Args:
            sla_name: SLA name to check
            execution_date: Execution date
            
        Returns:
            SLA check result
        """
        sla = self._sla_definitions.get(sla_name)
        if not sla:
            return SLAResult(
                sla_name=sla_name,
                dag_id='unknown',
                check_time=datetime.now(),
                status=SLAStatus.PENDING,
                target_time=datetime.now(),
                actual_time=None,
                delay_minutes=None,
                message=f"SLA '{sla_name}' not found"
            )
        
        # Calculate target time for this execution date
        target_datetime = datetime.combine(execution_date.date(), sla.target_time)
        
        # Get actual completion time from pipeline log
        actual_time = None
        if self.db:
            results = self.db.execute_query("""
                SELECT end_time, status
                FROM analytics._pipeline_log
                WHERE dag_id = :dag_id
                AND execution_date::DATE = :exec_date
                ORDER BY end_time DESC
                LIMIT 1
            """, {
                'dag_id': sla.dag_id,
                'exec_date': execution_date.date()
            })
            
            if results and results[0]['end_time']:
                actual_time = results[0]['end_time']
        
        # Determine status
        now = datetime.now()
        
        if actual_time:
            delay_minutes = int((actual_time - target_datetime).total_seconds() / 60)
            
            if delay_minutes <= 0:
                status = SLAStatus.MET
                message = f"SLA met. Completed {abs(delay_minutes)} minutes early."
            elif delay_minutes <= sla.max_delay_minutes:
                status = SLAStatus.MET
                message = f"SLA met within grace period. Delay: {delay_minutes} minutes."
            else:
                status = SLAStatus.MISSED
                message = f"SLA missed by {delay_minutes - sla.max_delay_minutes} minutes."
        else:
            delay_minutes = None
            if now > target_datetime + timedelta(minutes=sla.max_delay_minutes):
                status = SLAStatus.MISSED
                message = "SLA missed. Pipeline not completed."
            elif now > target_datetime:
                status = SLAStatus.AT_RISK
                message = f"SLA at risk. {int((now - target_datetime).total_seconds() / 60)} minutes past target."
            else:
                status = SLAStatus.PENDING
                minutes_remaining = int((target_datetime - now).total_seconds() / 60)
                message = f"SLA pending. {minutes_remaining} minutes until deadline."
        
        result = SLAResult(
            sla_name=sla_name,
            dag_id=sla.dag_id,
            check_time=now,
            status=status,
            target_time=target_datetime,
            actual_time=actual_time,
            delay_minutes=delay_minutes,
            message=message
        )
        
        # Log result
        self._log_sla_result(result)
        
        return result
    
    def check_all_slas(self, execution_date: datetime) -> List[SLAResult]:
        """
        Check all registered SLAs.
        
        Args:
            execution_date: Execution date to check
            
        Returns:
            List of SLA results
        """
        results = []
        for sla_name in self._sla_definitions:
            result = self.check_sla(sla_name, execution_date)
            results.append(result)
        
        return results
    
    def _log_sla_result(self, result: SLAResult) -> None:
        """Log SLA result to database."""
        if not self.db:
            return
        
        try:
            self.db.execute_query("""
                INSERT INTO analytics._sla_log (
                    sla_name, dag_id, check_time, status,
                    target_time, actual_time, delay_minutes, message
                ) VALUES (
                    :sla_name, :dag_id, :check_time, :status,
                    :target_time, :actual_time, :delay_minutes, :message
                )
            """, {
                'sla_name': result.sla_name,
                'dag_id': result.dag_id,
                'check_time': result.check_time,
                'status': result.status.value,
                'target_time': result.target_time,
                'actual_time': result.actual_time,
                'delay_minutes': result.delay_minutes,
                'message': result.message
            })
        except Exception as e:
            logger.warning("Failed to log SLA result", error=str(e))
    
    def get_sla_compliance_report(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate SLA compliance report.
        
        Args:
            days: Number of days to include
            
        Returns:
            Compliance report dictionary
        """
        if not self.db:
            return {'error': 'No database connection'}
        
        try:
            results = self.db.execute_query("""
                SELECT 
                    sla_name,
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN status = 'met' THEN 1 ELSE 0 END) as met_count,
                    SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END) as missed_count,
                    AVG(delay_minutes) as avg_delay,
                    MAX(delay_minutes) as max_delay
                FROM analytics._sla_log
                WHERE check_time >= CURRENT_DATE - INTERVAL ':days days'
                GROUP BY sla_name
            """, {'days': days})
            
            report = {
                'period_days': days,
                'generated_at': datetime.now().isoformat(),
                'slas': {}
            }
            
            for row in results:
                compliance_rate = (
                    row['met_count'] / row['total_checks'] * 100
                    if row['total_checks'] > 0 else 0
                )
                
                report['slas'][row['sla_name']] = {
                    'total_checks': row['total_checks'],
                    'met_count': row['met_count'],
                    'missed_count': row['missed_count'],
                    'compliance_rate': round(compliance_rate, 2),
                    'avg_delay_minutes': round(row['avg_delay'] or 0, 2),
                    'max_delay_minutes': row['max_delay']
                }
            
            # Calculate overall compliance
            total_checks = sum(s['total_checks'] for s in report['slas'].values())
            total_met = sum(s['met_count'] for s in report['slas'].values())
            
            report['overall'] = {
                'total_checks': total_checks,
                'compliance_rate': round(total_met / total_checks * 100, 2) if total_checks > 0 else 0
            }
            
            return report
            
        except Exception as e:
            logger.error("Failed to generate compliance report", error=str(e))
            return {'error': str(e)}
    
    def get_default_slas(self) -> List[SLADefinition]:
        """
        Get default SLA definitions for the platform.
        
        Returns:
            List of default SLA definitions
        """
        return [
            SLADefinition(
                name='daily_etl_sla',
                dag_id='daily_etl',
                target_time=time(8, 0),  # 8:00 AM
                max_delay_minutes=60,
                priority='critical',
                notification_channels=['email', 'slack']
            ),
            SLADefinition(
                name='customer_pipeline_sla',
                dag_id='customer_pipeline',
                target_time=time(9, 0),  # 9:00 AM
                max_delay_minutes=30,
                priority='high',
                notification_channels=['email']
            ),
            SLADefinition(
                name='metrics_refresh_sla',
                dag_id='daily_etl',
                target_time=time(10, 0),  # 10:00 AM (after metrics task)
                max_delay_minutes=60,
                priority='medium',
                notification_channels=['email']
            )
        ]

