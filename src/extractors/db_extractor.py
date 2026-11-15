"""Database extractor for extracting data from source databases."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.extractors.base_extractor import BaseExtractor
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseExtractor(BaseExtractor):
    """
    Extract data from relational databases.
    
    Supports:
    - Full table extracts
    - Incremental extracts by timestamp/ID
    - Custom SQL queries
    - Chunked reading for large tables
    """
    
    def __init__(
        self,
        connection_string: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        db_type: str = 'postgresql'
    ):
        """
        Initialize the database extractor.
        
        Args:
            connection_string: Full SQLAlchemy connection string
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            db_type: Database type (postgresql, mysql, mssql, etc.)
        """
        if connection_string:
            self.connection_string = connection_string
        else:
            self.host = host
            self.port = port
            self.database = database
            self.user = user
            self.password = password
            self.db_type = db_type
            
            # Build connection string based on db type
            if db_type == 'postgresql':
                driver = 'postgresql+psycopg2'
            elif db_type == 'mysql':
                driver = 'mysql+pymysql'
            elif db_type == 'mssql':
                driver = 'mssql+pyodbc'
            else:
                driver = db_type
            
            self.connection_string = (
                f"{driver}://{user}:{password}@{host}:{port}/{database}"
            )
        
        super().__init__(source_name=f"DB:{database or 'unknown'}")
        
        self._engine: Optional[Engine] = None
    
    @property
    def engine(self) -> Engine:
        """Get or create SQLAlchemy engine."""
        if self._engine is None:
            self._engine = create_engine(
                self.connection_string,
                pool_pre_ping=True,
                echo=False
            )
        return self._engine
    
    def validate_source(self) -> bool:
        """Test database connection."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("Database connection failed", error=str(e))
            return False
    
    def extract(
        self,
        table: Optional[str] = None,
        query: Optional[str] = None,
        schema: Optional[str] = None,
        columns: Optional[List[str]] = None,
        where: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        chunk_size: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Extract data from database.
        
        Args:
            table: Table name to extract from
            query: Custom SQL query (overrides table)
            schema: Database schema
            columns: List of columns to select
            where: WHERE clause conditions
            params: Query parameters
            chunk_size: Number of rows per chunk
            
        Returns:
            DataFrame with extracted data
        """
        if query:
            sql = query
        elif table:
            # Build SELECT query
            cols = ', '.join(columns) if columns else '*'
            full_table = f"{schema}.{table}" if schema else table
            sql = f"SELECT {cols} FROM {full_table}"
            
            if where:
                sql += f" WHERE {where}"
        else:
            raise ValueError("Either 'table' or 'query' must be provided")
        
        logger.debug("Executing query", sql=sql[:200])
        
        if chunk_size:
            chunks = []
            for chunk in pd.read_sql(
                sql,
                self.engine,
                params=params,
                chunksize=chunk_size
            ):
                chunks.append(chunk)
                logger.debug("Read chunk", rows=len(chunk))
            df = pd.concat(chunks, ignore_index=True)
        else:
            df = pd.read_sql(sql, self.engine, params=params)
        
        self.metadata.update({
            'query': sql[:500],
            'table': table,
            'schema': schema
        })
        
        logger.info(
            "Database extraction complete",
            table=table,
            rows=len(df)
        )
        
        return df
    
    def extract_incremental(
        self,
        table: str,
        incremental_column: str,
        last_value: Union[datetime, int, str],
        schema: Optional[str] = None,
        columns: Optional[List[str]] = None,
        additional_where: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Extract data incrementally based on a column value.
        
        Args:
            table: Table name
            incremental_column: Column to use for incremental logic
            last_value: Last extracted value
            schema: Database schema
            columns: Columns to select
            additional_where: Additional WHERE conditions
            
        Returns:
            DataFrame with new/updated records
        """
        where_clause = f"{incremental_column} > :last_value"
        
        if additional_where:
            where_clause += f" AND ({additional_where})"
        
        return self.extract(
            table=table,
            schema=schema,
            columns=columns,
            where=where_clause,
            params={'last_value': last_value}
        )
    
    def extract_with_watermark(
        self,
        table: str,
        watermark_column: str,
        watermark_table: str = '_watermarks',
        schema: Optional[str] = None,
        columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Extract data using a watermark table for tracking.
        
        Args:
            table: Source table name
            watermark_column: Column for watermark tracking
            watermark_table: Table storing watermarks
            schema: Database schema
            columns: Columns to select
            
        Returns:
            DataFrame with records since last watermark
        """
        full_table = f"{schema}.{table}" if schema else table
        full_watermark = f"{schema}.{watermark_table}" if schema else watermark_table
        
        # Get last watermark
        try:
            watermark_query = f"""
            SELECT watermark_value 
            FROM {full_watermark} 
            WHERE table_name = :table_name
            """
            result = pd.read_sql(
                watermark_query,
                self.engine,
                params={'table_name': table}
            )
            last_value = result.iloc[0]['watermark_value'] if len(result) > 0 else None
        except Exception:
            last_value = None
        
        if last_value:
            df = self.extract_incremental(
                table=table,
                incremental_column=watermark_column,
                last_value=last_value,
                schema=schema,
                columns=columns
            )
        else:
            df = self.extract(table=table, schema=schema, columns=columns)
        
        # Update watermark
        if len(df) > 0:
            new_watermark = df[watermark_column].max()
            update_query = f"""
            INSERT INTO {full_watermark} (table_name, watermark_value, updated_at)
            VALUES (:table_name, :watermark_value, :updated_at)
            ON CONFLICT (table_name) 
            DO UPDATE SET watermark_value = :watermark_value, updated_at = :updated_at
            """
            with self.engine.connect() as conn:
                conn.execute(
                    text(update_query),
                    {
                        'table_name': table,
                        'watermark_value': new_watermark,
                        'updated_at': datetime.now()
                    }
                )
                conn.commit()
        
        return df
    
    def get_table_metadata(self, table: str, schema: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metadata about a table.
        
        Args:
            table: Table name
            schema: Database schema
            
        Returns:
            Dictionary with table metadata
        """
        schema = schema or 'public'
        
        # Get column info
        columns_query = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
        columns_df = pd.read_sql(
            columns_query,
            self.engine,
            params={'schema': schema, 'table': table}
        )
        
        # Get row count estimate
        count_query = f"SELECT COUNT(*) as cnt FROM {schema}.{table}"
        try:
            count_df = pd.read_sql(count_query, self.engine)
            row_count = count_df.iloc[0]['cnt']
        except Exception:
            row_count = None
        
        return {
            'table': table,
            'schema': schema,
            'columns': columns_df.to_dict(orient='records'),
            'row_count': row_count
        }
    
    def close(self) -> None:
        """Close the database connection."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database connection closed")

