"""Database utility functions for the Enterprise Analytics Platform."""

import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseUtils:
    """Utility class for database operations."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        connection_string: Optional[str] = None
    ):
        """
        Initialize database connection.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            connection_string: Full connection string (overrides other params)
        """
        if connection_string:
            self.connection_string = connection_string
        else:
            self.host = host or os.getenv("POSTGRES_HOST", "localhost")
            self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
            self.database = database or os.getenv("POSTGRES_DB", "analytics_warehouse")
            self.user = user or os.getenv("POSTGRES_USER", "analytics_user")
            self.password = password or os.getenv("POSTGRES_PASSWORD", "")
            self.connection_string = (
                f"postgresql+psycopg2://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
            )
        
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
    
    @property
    def engine(self) -> Engine:
        """Get or create SQLAlchemy engine."""
        if self._engine is None:
            self._engine = create_engine(
                self.connection_string,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False
            )
            logger.info("Database engine created", database=self.database)
        return self._engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.
        
        Yields:
            SQLAlchemy session
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            session.close()
    
    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            List of result dictionaries
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            if result.returns_rows:
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
            return []
    
    def execute_query_df(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Execute a SQL query and return results as DataFrame.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            DataFrame with query results
        """
        return pd.read_sql(text(query), self.engine, params=params or {})
    
    def load_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: Optional[str] = None,
        if_exists: str = "append",
        index: bool = False,
        chunksize: int = 10000
    ) -> int:
        """
        Load a DataFrame into a database table.
        
        Args:
            df: DataFrame to load
            table_name: Target table name
            schema: Database schema
            if_exists: How to behave if table exists ('fail', 'replace', 'append')
            index: Whether to write DataFrame index
            chunksize: Number of rows to insert at a time
            
        Returns:
            Number of rows loaded
        """
        rows_loaded = len(df)
        df.to_sql(
            table_name,
            self.engine,
            schema=schema,
            if_exists=if_exists,
            index=index,
            chunksize=chunksize,
            method="multi"
        )
        logger.info(
            "Data loaded to table",
            table=table_name,
            rows=rows_loaded
        )
        return rows_loaded
    
    def upsert_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        key_columns: List[str],
        schema: Optional[str] = None
    ) -> int:
        """
        Upsert a DataFrame into a database table.
        
        Args:
            df: DataFrame to upsert
            table_name: Target table name
            key_columns: Columns to use for matching existing rows
            schema: Database schema
            
        Returns:
            Number of rows processed
        """
        # Create temp table
        temp_table = f"_temp_{table_name}"
        df.to_sql(temp_table, self.engine, if_exists="replace", index=False)
        
        # Get all columns
        columns = df.columns.tolist()
        update_columns = [c for c in columns if c not in key_columns]
        
        # Build UPSERT query
        full_table = f"{schema}.{table_name}" if schema else table_name
        key_match = " AND ".join([f"t.{k} = s.{k}" for k in key_columns])
        update_set = ", ".join([f"{c} = s.{c}" for c in update_columns])
        insert_cols = ", ".join(columns)
        insert_vals = ", ".join([f"s.{c}" for c in columns])
        
        upsert_query = f"""
        MERGE INTO {full_table} t
        USING {temp_table} s
        ON {key_match}
        WHEN MATCHED THEN
            UPDATE SET {update_set}
        WHEN NOT MATCHED THEN
            INSERT ({insert_cols})
            VALUES ({insert_vals});
        """
        
        # For PostgreSQL, use INSERT ON CONFLICT
        pg_upsert_query = f"""
        INSERT INTO {full_table} ({insert_cols})
        SELECT {insert_cols} FROM {temp_table}
        ON CONFLICT ({", ".join(key_columns)})
        DO UPDATE SET {", ".join([f"{c} = EXCLUDED.{c}" for c in update_columns])};
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(pg_upsert_query))
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
            conn.commit()
        
        logger.info(
            "Data upserted to table",
            table=table_name,
            rows=len(df)
        )
        return len(df)
    
    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """Check if a table exists."""
        query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = :schema
            AND table_name = :table_name
        );
        """
        result = self.execute_query(
            query,
            {"schema": schema or "public", "table_name": table_name}
        )
        return result[0]["exists"] if result else False
    
    def get_table_row_count(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> int:
        """Get the row count of a table."""
        full_table = f"{schema}.{table_name}" if schema else table_name
        result = self.execute_query(f"SELECT COUNT(*) as cnt FROM {full_table}")
        return result[0]["cnt"] if result else 0
    
    def close(self) -> None:
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database connection closed")

