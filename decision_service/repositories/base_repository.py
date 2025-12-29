

import logging
from typing import Optional, Any, Dict, List
from contextlib import contextmanager
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from shared.config import Config
from shared.database import get_engine

logger = logging.getLogger(__name__)


class BaseRepository:
    """
    Base repository class providing common database access patterns.
    
    All repositories should inherit from this class to:
    - Eliminate code duplication
    - Ensure consistent error handling
    - Use shared connection pooling
    - Standardize database access patterns
    """
    
    def __init__(self):
        """Initialize the repository."""
        self._engine: Optional[Engine] = None
    
    @property
    def engine(self) -> Optional[Engine]:
        """Get the database engine (cached)."""
        if self._engine is None:
            self._engine = get_engine()
        return self._engine
    
    def is_database_configured(self) -> bool:
        """Check if database is configured."""
        return Config.DATABASE_URL is not None and self.engine is not None
    
    @contextmanager
    def get_connection(self):
        """
        Get a database connection with proper setup.
        
        Usage:
            with self.get_connection() as conn:
                result = conn.execute(text("SELECT ..."), params)
                # For writes, use: conn.commit()
        """
        if not self.is_database_configured():
            raise ValueError("Database not configured")
        
        if self.engine is None:
            raise ValueError("Database engine is None")
        
        # Use autocommit=True for read operations, or begin() for transactions
        # This prevents hanging on connection acquisition
        try:
            with self.engine.connect() as conn:
                # Set statement timeout immediately to prevent hanging queries (3 seconds - aggressive)
                conn.execute(text("SET statement_timeout = '3s'"))
                # Set search_path
                conn.execute(text("SET search_path TO claims, public"))
                # Use autocommit mode to avoid transaction overhead for reads
                # For writes, call conn.commit() explicitly
                yield conn
        except Exception as e:
            logger.error(f"Error getting database connection: {e}", exc_info=True)
            raise
    
    async def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False
    ) -> Optional[Any]:
        """
        Execute a database query with common error handling.
        
        Args:
            query: SQL query string
            params: Query parameters
            fetch_one: If True, return single row
            fetch_all: If True, return all rows
            commit: If True, commit the transaction
        
        Returns:
            Query result (row, list of rows, or None)
        """
        if not self.is_database_configured():
            logger.warning("Database not configured, cannot execute query")
            return None
        
        try:
            with self.get_connection() as conn:
                result = conn.execute(text(query), params or {})
                
                if commit:
                    conn.commit()
                
                if fetch_one:
                    return result.fetchone()
                elif fetch_all:
                    return result.fetchall()
                else:
                    return result
        except Exception as e:
            logger.error(f"Error executing query: {e}", exc_info=True)
            raise
    
    def row_to_dict(self, row: Any, columns: List[str]) -> Optional[Dict[str, Any]]:
        """
        Convert a database row (tuple) to a dictionary.
        
        Args:
            row: Database row (tuple or Row object)
            columns: List of column names in order
        
        Returns:
            Dictionary with column names as keys, or None if row is None
        """
        if row is None:
            return None
        
        if hasattr(row, '_mapping'):
            return dict(row._mapping)
        
        if isinstance(row, tuple):
            return {col: row[i] if i < len(row) else None for i, col in enumerate(columns)}
        
        if hasattr(row, 'keys'):
            return {key: row[key] for key in row.keys()}
        
        return None

