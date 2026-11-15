"""Schema evolution handler for managing data schema changes over time."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.transformers.base_transformer import BaseTransformer
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SchemaEvolutionHandler(BaseTransformer):
    """
    Handle schema evolution and changes over time.
    
    Handles:
    - Column renames
    - Data type changes
    - New column additions
    - Column splits/merges
    - Default value handling
    - Version-aware transformations
    """
    
    def __init__(
        self,
        target_schema: Dict[str, str],
        schema_version: Optional[str] = None,
        column_mappings: Optional[Dict[str, str]] = None,
        type_conversions: Optional[Dict[str, Callable]] = None,
        default_values: Optional[Dict[str, Any]] = None,
        required_columns: Optional[List[str]] = None
    ):
        """
        Initialize the schema evolution handler.
        
        Args:
            target_schema: Target schema definition {column: dtype}
            schema_version: Current schema version
            column_mappings: Mappings from old column names to new
            type_conversions: Custom type conversion functions
            default_values: Default values for missing columns
            required_columns: Columns that must be present
        """
        super().__init__(name="SchemaEvolutionHandler")
        self.target_schema = target_schema
        self.schema_version = schema_version or datetime.now().strftime('%Y%m%d')
        self.column_mappings = column_mappings or {}
        self.type_conversions = type_conversions or {}
        self.default_values = default_values or {}
        self.required_columns = required_columns or []
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Transform DataFrame to target schema.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame conforming to target schema
        """
        df = df.copy()
        source_version = kwargs.get('source_version')
        
        logger.info(
            "Processing schema evolution",
            source_version=source_version,
            target_version=self.schema_version,
            source_columns=list(df.columns)
        )
        
        # Apply column mappings (renames)
        df = self._apply_column_mappings(df)
        
        # Handle column splits/merges
        df = self._handle_column_splits(df)
        df = self._handle_column_merges(df)
        
        # Add missing columns with defaults
        df = self._add_missing_columns(df)
        
        # Convert data types
        df = self._convert_data_types(df)
        
        # Validate required columns
        self._validate_required_columns(df)
        
        # Reorder columns to match target schema
        df = self._reorder_columns(df)
        
        # Add schema metadata
        df['_schema_version'] = self.schema_version
        
        return df
    
    def _apply_column_mappings(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply column rename mappings."""
        renames_applied = {}
        
        for old_name, new_name in self.column_mappings.items():
            if old_name in df.columns and new_name not in df.columns:
                df = df.rename(columns={old_name: new_name})
                renames_applied[old_name] = new_name
        
        if renames_applied:
            logger.info("Columns renamed", mappings=renames_applied)
        
        return df
    
    def _handle_column_splits(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handle columns that need to be split."""
        # Example: Split full_name into first_name and last_name
        if 'full_name' in df.columns and 'first_name' not in df.columns:
            names = df['full_name'].str.split(' ', n=1, expand=True)
            df['first_name'] = names[0] if 0 in names.columns else ''
            df['last_name'] = names[1] if 1 in names.columns else ''
            logger.info("Split column", source='full_name', targets=['first_name', 'last_name'])
        
        # Example: Split address into components
        if 'full_address' in df.columns and 'street_address' not in df.columns:
            # Simple split by comma
            parts = df['full_address'].str.split(',', expand=True)
            if parts.shape[1] >= 3:
                df['street_address'] = parts[0].str.strip()
                df['city'] = parts[1].str.strip() if 1 in parts.columns else ''
                df['state_zip'] = parts[2].str.strip() if 2 in parts.columns else ''
            logger.info("Split column", source='full_address')
        
        return df
    
    def _handle_column_merges(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handle columns that need to be merged."""
        # Example: Merge first_name and last_name into full_name
        if ('first_name' in df.columns and 'last_name' in df.columns 
            and 'full_name' in self.target_schema and 'full_name' not in df.columns):
            df['full_name'] = df['first_name'].fillna('') + ' ' + df['last_name'].fillna('')
            df['full_name'] = df['full_name'].str.strip()
            logger.info("Merged columns", sources=['first_name', 'last_name'], target='full_name')
        
        return df
    
    def _add_missing_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add columns that are in target schema but missing from data."""
        missing_columns = []
        
        for col, dtype in self.target_schema.items():
            if col not in df.columns:
                default = self.default_values.get(col)
                df[col] = default
                missing_columns.append(col)
        
        if missing_columns:
            logger.info(
                "Added missing columns",
                columns=missing_columns,
                defaults={c: self.default_values.get(c) for c in missing_columns}
            )
        
        return df
    
    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert columns to target data types."""
        type_errors = {}
        
        for col, target_dtype in self.target_schema.items():
            if col not in df.columns:
                continue
            
            # Check for custom conversion function
            if col in self.type_conversions:
                try:
                    df[col] = self.type_conversions[col](df[col])
                    continue
                except Exception as e:
                    type_errors[col] = str(e)
                    continue
            
            # Standard type conversions
            try:
                if target_dtype in ['int', 'int64', 'integer']:
                    df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
                elif target_dtype in ['float', 'float64', 'decimal']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                elif target_dtype in ['str', 'string', 'text', 'varchar']:
                    df[col] = df[col].astype(str).replace('nan', None)
                elif target_dtype in ['bool', 'boolean']:
                    df[col] = df[col].map(self._to_boolean)
                elif target_dtype in ['datetime', 'timestamp']:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                elif target_dtype == 'date':
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            except Exception as e:
                type_errors[col] = str(e)
        
        if type_errors:
            logger.warning("Type conversion errors", errors=type_errors)
        
        return df
    
    def _to_boolean(self, value: Any) -> Optional[bool]:
        """Convert value to boolean."""
        if pd.isna(value):
            return None
        
        if isinstance(value, bool):
            return value
        
        str_val = str(value).lower().strip()
        
        if str_val in ['true', 'yes', 'y', '1', 't']:
            return True
        elif str_val in ['false', 'no', 'n', '0', 'f']:
            return False
        
        return None
    
    def _validate_required_columns(self, df: pd.DataFrame) -> None:
        """Validate that all required columns are present."""
        missing = [col for col in self.required_columns if col not in df.columns]
        
        if missing:
            logger.error("Missing required columns", columns=missing)
            raise ValueError(f"Missing required columns: {missing}")
    
    def _reorder_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reorder columns to match target schema."""
        # Get target column order
        target_columns = list(self.target_schema.keys())
        
        # Add any extra columns not in target schema
        extra_columns = [c for c in df.columns if c not in target_columns]
        
        # Final column order
        final_order = target_columns + extra_columns
        existing_columns = [c for c in final_order if c in df.columns]
        
        return df[existing_columns]
    
    def detect_schema_changes(
        self,
        old_df: pd.DataFrame,
        new_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Detect schema changes between two DataFrames.
        
        Args:
            old_df: Old DataFrame
            new_df: New DataFrame
            
        Returns:
            Dictionary describing schema changes
        """
        old_cols = set(old_df.columns)
        new_cols = set(new_df.columns)
        
        changes = {
            'added_columns': list(new_cols - old_cols),
            'removed_columns': list(old_cols - new_cols),
            'common_columns': list(old_cols & new_cols),
            'type_changes': {}
        }
        
        # Check for type changes in common columns
        for col in changes['common_columns']:
            old_dtype = str(old_df[col].dtype)
            new_dtype = str(new_df[col].dtype)
            if old_dtype != new_dtype:
                changes['type_changes'][col] = {
                    'old': old_dtype,
                    'new': new_dtype
                }
        
        return changes
    
    def create_migration_script(
        self,
        changes: Dict[str, Any],
        table_name: str
    ) -> str:
        """
        Generate SQL migration script for schema changes.
        
        Args:
            changes: Schema changes dictionary
            table_name: Target table name
            
        Returns:
            SQL migration script
        """
        lines = [
            f"-- Schema migration for {table_name}",
            f"-- Generated: {datetime.now().isoformat()}",
            ""
        ]
        
        # Add new columns
        for col in changes.get('added_columns', []):
            dtype = self.target_schema.get(col, 'TEXT')
            sql_type = self._python_to_sql_type(dtype)
            default = self.default_values.get(col)
            default_clause = f" DEFAULT '{default}'" if default else ""
            lines.append(f"ALTER TABLE {table_name} ADD COLUMN {col} {sql_type}{default_clause};")
        
        # Type changes
        for col, type_info in changes.get('type_changes', {}).items():
            new_dtype = self.target_schema.get(col, 'TEXT')
            sql_type = self._python_to_sql_type(new_dtype)
            lines.append(f"ALTER TABLE {table_name} ALTER COLUMN {col} TYPE {sql_type};")
        
        # Note about removed columns (don't auto-drop)
        for col in changes.get('removed_columns', []):
            lines.append(f"-- REVIEW: Column {col} exists in old schema but not in new")
        
        return '\n'.join(lines)
    
    def _python_to_sql_type(self, python_type: str) -> str:
        """Convert Python type hint to SQL type."""
        type_map = {
            'int': 'INTEGER',
            'int64': 'BIGINT',
            'integer': 'INTEGER',
            'float': 'DOUBLE PRECISION',
            'float64': 'DOUBLE PRECISION',
            'decimal': 'DECIMAL',
            'str': 'TEXT',
            'string': 'TEXT',
            'text': 'TEXT',
            'varchar': 'VARCHAR(255)',
            'bool': 'BOOLEAN',
            'boolean': 'BOOLEAN',
            'datetime': 'TIMESTAMP',
            'timestamp': 'TIMESTAMP',
            'date': 'DATE'
        }
        return type_map.get(python_type.lower(), 'TEXT')

