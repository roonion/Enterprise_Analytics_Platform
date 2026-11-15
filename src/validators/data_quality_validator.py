"""Data quality validator for comprehensive data validation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation failures."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check_name: str
    passed: bool
    severity: ValidationSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    affected_rows: int = 0
    affected_percentage: float = 0.0


@dataclass
class ValidationReport:
    """Complete validation report for a dataset."""
    dataset_name: str
    timestamp: datetime
    total_rows: int
    total_checks: int
    passed_checks: int
    failed_checks: int
    results: List[ValidationResult]
    overall_score: float
    is_valid: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            'dataset_name': self.dataset_name,
            'timestamp': self.timestamp.isoformat(),
            'total_rows': self.total_rows,
            'total_checks': self.total_checks,
            'passed_checks': self.passed_checks,
            'failed_checks': self.failed_checks,
            'overall_score': self.overall_score,
            'is_valid': self.is_valid,
            'results': [
                {
                    'check_name': r.check_name,
                    'passed': r.passed,
                    'severity': r.severity.value,
                    'message': r.message,
                    'details': r.details,
                    'affected_rows': r.affected_rows,
                    'affected_percentage': r.affected_percentage
                }
                for r in self.results
            ]
        }


class DataQualityValidator:
    """
    Comprehensive data quality validator.
    
    Performs:
    - Null checks
    - Duplicate detection
    - Data type validation
    - Range/value checks
    - Business rule validation
    - Freshness checks
    - Volume anomaly detection
    """
    
    def __init__(
        self,
        dataset_name: str,
        fail_on_error: bool = True,
        null_threshold: float = 0.05,
        duplicate_threshold: float = 0.01
    ):
        """
        Initialize the validator.
        
        Args:
            dataset_name: Name of the dataset being validated
            fail_on_error: Whether to raise exception on validation failure
            null_threshold: Maximum acceptable null rate
            duplicate_threshold: Maximum acceptable duplicate rate
        """
        self.dataset_name = dataset_name
        self.fail_on_error = fail_on_error
        self.null_threshold = null_threshold
        self.duplicate_threshold = duplicate_threshold
        
        self._checks: List[Callable] = []
        self._results: List[ValidationResult] = []
    
    def add_check(
        self,
        check_fn: Callable[[pd.DataFrame], ValidationResult]
    ) -> 'DataQualityValidator':
        """Add a custom validation check."""
        self._checks.append(check_fn)
        return self
    
    def validate(self, df: pd.DataFrame) -> ValidationReport:
        """
        Run all validations on the DataFrame.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            ValidationReport with results
        """
        self._results = []
        
        logger.info(
            "Starting validation",
            dataset=self.dataset_name,
            rows=len(df)
        )
        
        # Run built-in checks
        self._check_not_empty(df)
        self._check_null_rates(df)
        self._check_duplicates(df)
        
        # Run custom checks
        for check_fn in self._checks:
            try:
                result = check_fn(df)
                self._results.append(result)
            except Exception as e:
                logger.error("Check failed", check=check_fn.__name__, error=str(e))
                self._results.append(ValidationResult(
                    check_name=check_fn.__name__,
                    passed=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Check raised exception: {str(e)}"
                ))
        
        # Generate report
        report = self._generate_report(df)
        
        # Log results
        logger.info(
            "Validation complete",
            dataset=self.dataset_name,
            passed=report.passed_checks,
            failed=report.failed_checks,
            score=report.overall_score,
            is_valid=report.is_valid
        )
        
        # Fail if configured and validation failed
        if self.fail_on_error and not report.is_valid:
            error_results = [r for r in report.results 
                          if not r.passed and r.severity == ValidationSeverity.ERROR]
            raise ValueError(
                f"Validation failed for {self.dataset_name}: "
                f"{[r.message for r in error_results]}"
            )
        
        return report
    
    def _check_not_empty(self, df: pd.DataFrame) -> None:
        """Check that DataFrame is not empty."""
        passed = len(df) > 0
        self._results.append(ValidationResult(
            check_name="not_empty",
            passed=passed,
            severity=ValidationSeverity.ERROR,
            message="Dataset is empty" if not passed else "Dataset has data",
            details={'row_count': len(df)}
        ))
    
    def _check_null_rates(self, df: pd.DataFrame) -> None:
        """Check null rates for each column."""
        for col in df.columns:
            if col.startswith('_'):  # Skip metadata columns
                continue
            
            null_count = df[col].isna().sum()
            null_rate = null_count / len(df) if len(df) > 0 else 0
            passed = null_rate <= self.null_threshold
            
            self._results.append(ValidationResult(
                check_name=f"null_rate_{col}",
                passed=passed,
                severity=ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO,
                message=f"Null rate for {col}: {null_rate:.2%}",
                details={
                    'column': col,
                    'null_count': int(null_count),
                    'null_rate': null_rate,
                    'threshold': self.null_threshold
                },
                affected_rows=int(null_count),
                affected_percentage=null_rate * 100
            ))
    
    def _check_duplicates(self, df: pd.DataFrame) -> None:
        """Check for duplicate rows."""
        # Full row duplicates
        dup_count = df.duplicated().sum()
        dup_rate = dup_count / len(df) if len(df) > 0 else 0
        passed = dup_rate <= self.duplicate_threshold
        
        self._results.append(ValidationResult(
            check_name="duplicate_rows",
            passed=passed,
            severity=ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO,
            message=f"Duplicate row rate: {dup_rate:.2%}",
            details={
                'duplicate_count': int(dup_count),
                'duplicate_rate': dup_rate,
                'threshold': self.duplicate_threshold
            },
            affected_rows=int(dup_count),
            affected_percentage=dup_rate * 100
        ))
    
    def _generate_report(self, df: pd.DataFrame) -> ValidationReport:
        """Generate validation report from results."""
        passed_checks = sum(1 for r in self._results if r.passed)
        failed_checks = len(self._results) - passed_checks
        
        # Calculate score (weight errors more heavily)
        error_failures = sum(
            1 for r in self._results 
            if not r.passed and r.severity == ValidationSeverity.ERROR
        )
        warning_failures = sum(
            1 for r in self._results 
            if not r.passed and r.severity == ValidationSeverity.WARNING
        )
        
        if len(self._results) > 0:
            score = (
                (passed_checks - error_failures * 2 - warning_failures * 0.5) 
                / len(self._results)
            ) * 100
            score = max(0, min(100, score))
        else:
            score = 100.0
        
        # Dataset is valid if no error-level failures
        is_valid = error_failures == 0
        
        return ValidationReport(
            dataset_name=self.dataset_name,
            timestamp=datetime.now(),
            total_rows=len(df),
            total_checks=len(self._results),
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            results=self._results,
            overall_score=round(score, 2),
            is_valid=is_valid
        )
    
    # Convenience methods for common checks
    
    def check_column_exists(
        self,
        columns: List[str],
        severity: ValidationSeverity = ValidationSeverity.ERROR
    ) -> 'DataQualityValidator':
        """Add check for required columns."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            missing = [c for c in columns if c not in df.columns]
            return ValidationResult(
                check_name="required_columns",
                passed=len(missing) == 0,
                severity=severity,
                message=f"Missing columns: {missing}" if missing else "All required columns present",
                details={'required': columns, 'missing': missing}
            )
        return self.add_check(check_fn)
    
    def check_unique(
        self,
        columns: List[str],
        severity: ValidationSeverity = ValidationSeverity.ERROR
    ) -> 'DataQualityValidator':
        """Add check for unique values in columns."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            cols = [c for c in columns if c in df.columns]
            if not cols:
                return ValidationResult(
                    check_name=f"unique_{','.join(columns)}",
                    passed=False,
                    severity=severity,
                    message=f"Columns not found: {columns}"
                )
            
            dup_count = df.duplicated(subset=cols).sum()
            passed = dup_count == 0
            
            return ValidationResult(
                check_name=f"unique_{','.join(cols)}",
                passed=passed,
                severity=severity,
                message=f"Duplicates found: {dup_count}" if not passed else "All values unique",
                details={'columns': cols, 'duplicate_count': int(dup_count)},
                affected_rows=int(dup_count)
            )
        return self.add_check(check_fn)
    
    def check_not_null(
        self,
        columns: List[str],
        severity: ValidationSeverity = ValidationSeverity.ERROR
    ) -> 'DataQualityValidator':
        """Add check that columns have no null values."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            null_cols = {}
            for col in columns:
                if col in df.columns:
                    null_count = df[col].isna().sum()
                    if null_count > 0:
                        null_cols[col] = int(null_count)
            
            passed = len(null_cols) == 0
            return ValidationResult(
                check_name=f"not_null_{','.join(columns)}",
                passed=passed,
                severity=severity,
                message=f"Null values found: {null_cols}" if not passed else "No null values",
                details={'columns': columns, 'null_counts': null_cols},
                affected_rows=sum(null_cols.values()) if null_cols else 0
            )
        return self.add_check(check_fn)
    
    def check_values_in_set(
        self,
        column: str,
        valid_values: List[Any],
        severity: ValidationSeverity = ValidationSeverity.WARNING
    ) -> 'DataQualityValidator':
        """Add check that column values are in allowed set."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            if column not in df.columns:
                return ValidationResult(
                    check_name=f"values_in_set_{column}",
                    passed=False,
                    severity=severity,
                    message=f"Column not found: {column}"
                )
            
            invalid = df[~df[column].isin(valid_values) & df[column].notna()]
            invalid_values = invalid[column].unique().tolist()
            passed = len(invalid) == 0
            
            return ValidationResult(
                check_name=f"values_in_set_{column}",
                passed=passed,
                severity=severity,
                message=f"Invalid values: {invalid_values[:10]}" if not passed else "All values valid",
                details={
                    'column': column,
                    'valid_values': valid_values,
                    'invalid_values': invalid_values[:20],
                    'invalid_count': len(invalid)
                },
                affected_rows=len(invalid)
            )
        return self.add_check(check_fn)
    
    def check_range(
        self,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        severity: ValidationSeverity = ValidationSeverity.WARNING
    ) -> 'DataQualityValidator':
        """Add check that numeric column is within range."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            if column not in df.columns:
                return ValidationResult(
                    check_name=f"range_{column}",
                    passed=False,
                    severity=severity,
                    message=f"Column not found: {column}"
                )
            
            values = pd.to_numeric(df[column], errors='coerce')
            out_of_range = 0
            
            if min_value is not None:
                out_of_range += (values < min_value).sum()
            if max_value is not None:
                out_of_range += (values > max_value).sum()
            
            passed = out_of_range == 0
            
            return ValidationResult(
                check_name=f"range_{column}",
                passed=passed,
                severity=severity,
                message=f"Out of range values: {out_of_range}" if not passed else "All values in range",
                details={
                    'column': column,
                    'min': min_value,
                    'max': max_value,
                    'out_of_range_count': int(out_of_range),
                    'actual_min': float(values.min()) if len(values) > 0 else None,
                    'actual_max': float(values.max()) if len(values) > 0 else None
                },
                affected_rows=int(out_of_range)
            )
        return self.add_check(check_fn)
    
    def check_regex(
        self,
        column: str,
        pattern: str,
        severity: ValidationSeverity = ValidationSeverity.WARNING
    ) -> 'DataQualityValidator':
        """Add check that column values match regex pattern."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            if column not in df.columns:
                return ValidationResult(
                    check_name=f"regex_{column}",
                    passed=False,
                    severity=severity,
                    message=f"Column not found: {column}"
                )
            
            matches = df[column].astype(str).str.match(pattern, na=False)
            non_matches = (~matches & df[column].notna()).sum()
            passed = non_matches == 0
            
            return ValidationResult(
                check_name=f"regex_{column}",
                passed=passed,
                severity=severity,
                message=f"Pattern mismatches: {non_matches}" if not passed else "All values match pattern",
                details={
                    'column': column,
                    'pattern': pattern,
                    'mismatch_count': int(non_matches)
                },
                affected_rows=int(non_matches)
            )
        return self.add_check(check_fn)
    
    def check_freshness(
        self,
        date_column: str,
        max_age_hours: int = 24,
        severity: ValidationSeverity = ValidationSeverity.WARNING
    ) -> 'DataQualityValidator':
        """Add check for data freshness."""
        def check_fn(df: pd.DataFrame) -> ValidationResult:
            if date_column not in df.columns:
                return ValidationResult(
                    check_name=f"freshness_{date_column}",
                    passed=False,
                    severity=severity,
                    message=f"Column not found: {date_column}"
                )
            
            dates = pd.to_datetime(df[date_column], errors='coerce')
            max_date = dates.max()
            
            if pd.isna(max_date):
                return ValidationResult(
                    check_name=f"freshness_{date_column}",
                    passed=False,
                    severity=severity,
                    message="No valid dates found"
                )
            
            age_hours = (datetime.now() - max_date).total_seconds() / 3600
            passed = age_hours <= max_age_hours
            
            return ValidationResult(
                check_name=f"freshness_{date_column}",
                passed=passed,
                severity=severity,
                message=f"Data age: {age_hours:.1f} hours" + (" (stale)" if not passed else ""),
                details={
                    'column': date_column,
                    'max_date': max_date.isoformat(),
                    'age_hours': round(age_hours, 2),
                    'threshold_hours': max_age_hours
                }
            )
        return self.add_check(check_fn)

