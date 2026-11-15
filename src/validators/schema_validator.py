"""Schema validator using Pydantic and Great Expectations patterns."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type, Union

import pandas as pd
from pydantic import BaseModel, ValidationError, create_model, field_validator

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SchemaValidationResult:
    """Result of schema validation."""
    
    def __init__(
        self,
        is_valid: bool,
        valid_rows: int,
        invalid_rows: int,
        errors: List[Dict[str, Any]]
    ):
        self.is_valid = is_valid
        self.valid_rows = valid_rows
        self.invalid_rows = invalid_rows
        self.errors = errors
        self.validation_time = datetime.now()
    
    @property
    def error_rate(self) -> float:
        """Get error rate as percentage."""
        total = self.valid_rows + self.invalid_rows
        return (self.invalid_rows / total * 100) if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'is_valid': self.is_valid,
            'valid_rows': self.valid_rows,
            'invalid_rows': self.invalid_rows,
            'error_rate': self.error_rate,
            'validation_time': self.validation_time.isoformat(),
            'error_count': len(self.errors),
            'errors': self.errors[:100]  # Limit errors in output
        }


class SchemaValidator:
    """
    Validate DataFrame against a schema definition.
    
    Supports:
    - Type validation
    - Required field validation
    - Custom validators
    - Pydantic model validation
    """
    
    def __init__(
        self,
        schema: Optional[Dict[str, Any]] = None,
        pydantic_model: Optional[Type[BaseModel]] = None,
        strict: bool = False,
        sample_errors: int = 100
    ):
        """
        Initialize the schema validator.
        
        Args:
            schema: Dictionary schema definition
            pydantic_model: Pydantic model for validation
            strict: Whether to fail on any schema violation
            sample_errors: Maximum number of errors to capture
        """
        self.schema = schema or {}
        self.pydantic_model = pydantic_model
        self.strict = strict
        self.sample_errors = sample_errors
        
        self._custom_validators: Dict[str, List[Callable]] = {}
    
    def add_validator(
        self,
        column: str,
        validator_fn: Callable[[Any], bool],
        error_message: str = "Validation failed"
    ) -> 'SchemaValidator':
        """
        Add custom validator for a column.
        
        Args:
            column: Column to validate
            validator_fn: Function that returns True if valid
            error_message: Error message on failure
        """
        if column not in self._custom_validators:
            self._custom_validators[column] = []
        
        self._custom_validators[column].append({
            'fn': validator_fn,
            'message': error_message
        })
        return self
    
    def validate(self, df: pd.DataFrame) -> SchemaValidationResult:
        """
        Validate DataFrame against schema.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            SchemaValidationResult
        """
        errors = []
        valid_rows = 0
        invalid_rows = 0
        
        logger.info("Starting schema validation", rows=len(df))
        
        # Validate using Pydantic model if provided
        if self.pydantic_model:
            valid_rows, invalid_rows, errors = self._validate_with_pydantic(df)
        else:
            # Validate using schema dictionary
            valid_rows, invalid_rows, errors = self._validate_with_schema(df)
        
        # Run custom validators
        custom_errors = self._run_custom_validators(df)
        errors.extend(custom_errors)
        
        is_valid = invalid_rows == 0 if self.strict else (invalid_rows / len(df)) < 0.1
        
        result = SchemaValidationResult(
            is_valid=is_valid,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            errors=errors[:self.sample_errors]
        )
        
        logger.info(
            "Schema validation complete",
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            error_rate=f"{result.error_rate:.2f}%"
        )
        
        return result
    
    def _validate_with_pydantic(
        self,
        df: pd.DataFrame
    ) -> tuple:
        """Validate using Pydantic model."""
        errors = []
        valid_rows = 0
        invalid_rows = 0
        
        for idx, row in df.iterrows():
            try:
                # Convert row to dict, handling NaN values
                row_dict = {
                    k: (None if pd.isna(v) else v) 
                    for k, v in row.to_dict().items()
                }
                self.pydantic_model(**row_dict)
                valid_rows += 1
            except ValidationError as e:
                invalid_rows += 1
                if len(errors) < self.sample_errors:
                    errors.append({
                        'row_index': idx,
                        'errors': e.errors()
                    })
        
        return valid_rows, invalid_rows, errors
    
    def _validate_with_schema(
        self,
        df: pd.DataFrame
    ) -> tuple:
        """Validate using schema dictionary."""
        errors = []
        row_errors = set()
        
        # Check required columns
        required_cols = [
            col for col, spec in self.schema.items() 
            if spec.get('required', False)
        ]
        missing_cols = [c for c in required_cols if c not in df.columns]
        
        if missing_cols:
            errors.append({
                'type': 'missing_columns',
                'columns': missing_cols
            })
        
        # Validate each column
        for col, spec in self.schema.items():
            if col not in df.columns:
                continue
            
            # Type validation
            expected_type = spec.get('type')
            if expected_type:
                type_errors = self._validate_column_type(df, col, expected_type)
                for err in type_errors:
                    row_errors.add(err['row_index'])
                if len(errors) < self.sample_errors:
                    errors.extend(type_errors[:10])
            
            # Nullable validation
            if not spec.get('nullable', True):
                null_mask = df[col].isna()
                null_indices = df[null_mask].index.tolist()
                for idx in null_indices:
                    row_errors.add(idx)
                if null_indices and len(errors) < self.sample_errors:
                    errors.append({
                        'column': col,
                        'type': 'null_not_allowed',
                        'row_indices': null_indices[:10]
                    })
            
            # Min/max validation
            if 'min' in spec or 'max' in spec:
                range_errors = self._validate_range(
                    df, col, spec.get('min'), spec.get('max')
                )
                for err in range_errors:
                    row_errors.add(err.get('row_index'))
                if len(errors) < self.sample_errors:
                    errors.extend(range_errors[:10])
            
            # Allowed values validation
            if 'allowed_values' in spec:
                allowed = spec['allowed_values']
                invalid_mask = ~df[col].isin(allowed) & df[col].notna()
                invalid_indices = df[invalid_mask].index.tolist()
                for idx in invalid_indices:
                    row_errors.add(idx)
                if invalid_indices and len(errors) < self.sample_errors:
                    errors.append({
                        'column': col,
                        'type': 'invalid_value',
                        'row_indices': invalid_indices[:10],
                        'invalid_values': df.loc[invalid_indices[:5], col].tolist()
                    })
        
        valid_rows = len(df) - len(row_errors)
        invalid_rows = len(row_errors)
        
        return valid_rows, invalid_rows, errors
    
    def _validate_column_type(
        self,
        df: pd.DataFrame,
        column: str,
        expected_type: str
    ) -> List[Dict]:
        """Validate column data type."""
        errors = []
        
        type_checks = {
            'int': lambda x: pd.to_numeric(x, errors='coerce').notna() | x.isna(),
            'float': lambda x: pd.to_numeric(x, errors='coerce').notna() | x.isna(),
            'string': lambda x: x.apply(lambda v: isinstance(v, str) or pd.isna(v)),
            'bool': lambda x: x.isin([True, False, None]) | x.isna(),
            'datetime': lambda x: pd.to_datetime(x, errors='coerce').notna() | x.isna()
        }
        
        check_fn = type_checks.get(expected_type)
        if check_fn:
            valid_mask = check_fn(df[column])
            invalid_indices = df[~valid_mask].index.tolist()
            
            for idx in invalid_indices[:10]:
                errors.append({
                    'column': column,
                    'type': 'type_error',
                    'row_index': idx,
                    'expected_type': expected_type,
                    'actual_value': str(df.loc[idx, column])
                })
        
        return errors
    
    def _validate_range(
        self,
        df: pd.DataFrame,
        column: str,
        min_val: Optional[float],
        max_val: Optional[float]
    ) -> List[Dict]:
        """Validate numeric range."""
        errors = []
        values = pd.to_numeric(df[column], errors='coerce')
        
        if min_val is not None:
            below_min = (values < min_val) & values.notna()
            for idx in df[below_min].index[:10]:
                errors.append({
                    'column': column,
                    'type': 'below_minimum',
                    'row_index': idx,
                    'value': float(values[idx]),
                    'minimum': min_val
                })
        
        if max_val is not None:
            above_max = (values > max_val) & values.notna()
            for idx in df[above_max].index[:10]:
                errors.append({
                    'column': column,
                    'type': 'above_maximum',
                    'row_index': idx,
                    'value': float(values[idx]),
                    'maximum': max_val
                })
        
        return errors
    
    def _run_custom_validators(self, df: pd.DataFrame) -> List[Dict]:
        """Run custom validators on columns."""
        errors = []
        
        for column, validators in self._custom_validators.items():
            if column not in df.columns:
                continue
            
            for validator in validators:
                for idx, value in df[column].items():
                    try:
                        if not validator['fn'](value):
                            if len(errors) < self.sample_errors:
                                errors.append({
                                    'column': column,
                                    'type': 'custom_validation',
                                    'row_index': idx,
                                    'message': validator['message'],
                                    'value': str(value)
                                })
                    except Exception:
                        pass
        
        return errors
    
    @staticmethod
    def create_schema_from_df(
        df: pd.DataFrame,
        sample_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Infer schema from DataFrame.
        
        Args:
            df: DataFrame to analyze
            sample_size: Number of rows to sample
            
        Returns:
            Inferred schema dictionary
        """
        schema = {}
        sample_df = df.head(sample_size) if len(df) > sample_size else df
        
        for col in df.columns:
            col_spec = {
                'nullable': df[col].isna().any(),
            }
            
            # Infer type
            dtype = df[col].dtype
            if pd.api.types.is_integer_dtype(dtype):
                col_spec['type'] = 'int'
                col_spec['min'] = int(df[col].min()) if df[col].notna().any() else None
                col_spec['max'] = int(df[col].max()) if df[col].notna().any() else None
            elif pd.api.types.is_float_dtype(dtype):
                col_spec['type'] = 'float'
                col_spec['min'] = float(df[col].min()) if df[col].notna().any() else None
                col_spec['max'] = float(df[col].max()) if df[col].notna().any() else None
            elif pd.api.types.is_bool_dtype(dtype):
                col_spec['type'] = 'bool'
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                col_spec['type'] = 'datetime'
            else:
                col_spec['type'] = 'string'
                # Check for categorical
                unique_ratio = df[col].nunique() / len(df) if len(df) > 0 else 0
                if unique_ratio < 0.05 and df[col].nunique() < 100:
                    col_spec['allowed_values'] = df[col].dropna().unique().tolist()
            
            schema[col] = col_spec
        
        return schema

