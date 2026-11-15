"""Referential integrity validator for checking relationships between tables."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class IntegrityViolation:
    """Represents a referential integrity violation."""
    relationship_name: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    orphan_count: int
    sample_orphan_values: List[Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'relationship_name': self.relationship_name,
            'source_table': self.source_table,
            'source_column': self.source_column,
            'target_table': self.target_table,
            'target_column': self.target_column,
            'orphan_count': self.orphan_count,
            'sample_orphan_values': self.sample_orphan_values[:10]
        }


@dataclass
class IntegrityReport:
    """Report of referential integrity check."""
    timestamp: datetime
    total_relationships: int
    valid_relationships: int
    violated_relationships: int
    violations: List[IntegrityViolation]
    is_valid: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_relationships': self.total_relationships,
            'valid_relationships': self.valid_relationships,
            'violated_relationships': self.violated_relationships,
            'is_valid': self.is_valid,
            'violations': [v.to_dict() for v in self.violations]
        }


class ReferentialIntegrityValidator:
    """
    Validate referential integrity between related tables.
    
    Checks:
    - Foreign key relationships
    - Orphan records
    - Cardinality constraints
    - Circular references
    """
    
    def __init__(self, strict: bool = False):
        """
        Initialize the validator.
        
        Args:
            strict: If True, any violation fails the check
        """
        self.strict = strict
        self._relationships: List[Dict[str, Any]] = []
        self._tables: Dict[str, pd.DataFrame] = {}
    
    def register_table(
        self,
        name: str,
        df: pd.DataFrame
    ) -> 'ReferentialIntegrityValidator':
        """
        Register a table for validation.
        
        Args:
            name: Table name
            df: DataFrame representing the table
        """
        self._tables[name] = df
        logger.debug("Registered table", table=name, rows=len(df))
        return self
    
    def add_relationship(
        self,
        name: str,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        cardinality: str = "many-to-one",
        required: bool = True
    ) -> 'ReferentialIntegrityValidator':
        """
        Add a relationship to validate.
        
        Args:
            name: Relationship name
            source_table: Table containing the foreign key
            source_column: Foreign key column
            target_table: Referenced table
            target_column: Referenced column (usually primary key)
            cardinality: Relationship type (many-to-one, one-to-one, many-to-many)
            required: Whether the foreign key can be null
        """
        self._relationships.append({
            'name': name,
            'source_table': source_table,
            'source_column': source_column,
            'target_table': target_table,
            'target_column': target_column,
            'cardinality': cardinality,
            'required': required
        })
        return self
    
    def validate(self) -> IntegrityReport:
        """
        Validate all registered relationships.
        
        Returns:
            IntegrityReport with validation results
        """
        violations = []
        
        logger.info(
            "Starting referential integrity validation",
            tables=list(self._tables.keys()),
            relationships=len(self._relationships)
        )
        
        for rel in self._relationships:
            violation = self._check_relationship(rel)
            if violation:
                violations.append(violation)
        
        is_valid = len(violations) == 0 if self.strict else True
        
        report = IntegrityReport(
            timestamp=datetime.now(),
            total_relationships=len(self._relationships),
            valid_relationships=len(self._relationships) - len(violations),
            violated_relationships=len(violations),
            violations=violations,
            is_valid=is_valid
        )
        
        logger.info(
            "Referential integrity validation complete",
            valid=report.valid_relationships,
            violated=report.violated_relationships
        )
        
        return report
    
    def _check_relationship(
        self,
        relationship: Dict[str, Any]
    ) -> Optional[IntegrityViolation]:
        """Check a single relationship for violations."""
        source_table = relationship['source_table']
        source_column = relationship['source_column']
        target_table = relationship['target_table']
        target_column = relationship['target_column']
        required = relationship['required']
        
        # Get tables
        if source_table not in self._tables:
            logger.warning("Source table not found", table=source_table)
            return None
        if target_table not in self._tables:
            logger.warning("Target table not found", table=target_table)
            return None
        
        source_df = self._tables[source_table]
        target_df = self._tables[target_table]
        
        # Check columns exist
        if source_column not in source_df.columns:
            logger.warning("Source column not found", column=source_column)
            return None
        if target_column not in target_df.columns:
            logger.warning("Target column not found", column=target_column)
            return None
        
        # Get values
        source_values = source_df[source_column]
        target_values = set(target_df[target_column].dropna())
        
        # Handle nulls based on required flag
        if required:
            # All non-null values must exist in target
            orphans = source_values[
                source_values.notna() & 
                ~source_values.isin(target_values)
            ]
        else:
            # Only check non-null values
            orphans = source_values[
                source_values.notna() & 
                ~source_values.isin(target_values)
            ]
        
        if len(orphans) > 0:
            return IntegrityViolation(
                relationship_name=relationship['name'],
                source_table=source_table,
                source_column=source_column,
                target_table=target_table,
                target_column=target_column,
                orphan_count=len(orphans),
                sample_orphan_values=orphans.unique().tolist()[:20]
            )
        
        return None
    
    def check_cardinality(
        self,
        table_name: str,
        column: str,
        expected: str
    ) -> Dict[str, Any]:
        """
        Check cardinality of a column.
        
        Args:
            table_name: Table to check
            column: Column to check
            expected: Expected cardinality ('unique', 'one-to-many', etc.)
            
        Returns:
            Dictionary with cardinality analysis
        """
        if table_name not in self._tables:
            return {'error': f'Table {table_name} not found'}
        
        df = self._tables[table_name]
        if column not in df.columns:
            return {'error': f'Column {column} not found'}
        
        total_rows = len(df)
        unique_values = df[column].nunique()
        null_count = df[column].isna().sum()
        
        # Calculate value frequencies
        value_counts = df[column].value_counts()
        max_frequency = value_counts.max() if len(value_counts) > 0 else 0
        
        # Determine actual cardinality
        if unique_values == total_rows - null_count:
            actual = 'unique'
        elif max_frequency == 1:
            actual = 'one-to-one'
        else:
            actual = 'one-to-many'
        
        passed = (expected == actual) or (expected == 'one-to-many' and actual in ['unique', 'one-to-one'])
        
        return {
            'table': table_name,
            'column': column,
            'expected_cardinality': expected,
            'actual_cardinality': actual,
            'total_rows': total_rows,
            'unique_values': unique_values,
            'null_count': null_count,
            'max_frequency': max_frequency,
            'passed': passed
        }
    
    def get_orphan_records(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str
    ) -> pd.DataFrame:
        """
        Get all orphan records from a relationship.
        
        Returns:
            DataFrame with orphan records
        """
        if source_table not in self._tables or target_table not in self._tables:
            return pd.DataFrame()
        
        source_df = self._tables[source_table]
        target_df = self._tables[target_table]
        
        target_values = set(target_df[target_column].dropna())
        
        orphan_mask = (
            source_df[source_column].notna() & 
            ~source_df[source_column].isin(target_values)
        )
        
        return source_df[orphan_mask]
    
    def generate_integrity_report_sql(self) -> str:
        """
        Generate SQL queries for checking referential integrity.
        
        Returns:
            SQL script for integrity checks
        """
        queries = [
            "-- Referential Integrity Check Queries",
            f"-- Generated: {datetime.now().isoformat()}",
            ""
        ]
        
        for rel in self._relationships:
            query = f"""
-- Check: {rel['name']}
-- Orphan records in {rel['source_table']}.{rel['source_column']}
SELECT 
    '{rel['name']}' as relationship,
    COUNT(*) as orphan_count
FROM {rel['source_table']} s
LEFT JOIN {rel['target_table']} t 
    ON s.{rel['source_column']} = t.{rel['target_column']}
WHERE s.{rel['source_column']} IS NOT NULL
    AND t.{rel['target_column']} IS NULL;
"""
            queries.append(query)
        
        return '\n'.join(queries)

