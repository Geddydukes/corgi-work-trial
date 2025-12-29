"""
Shared database connection manager.

Provides a centralized way to get database connections with connection pooling.
All repositories and services should use this instead of creating their own engines.
"""

import logging
from typing import Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Global engine cache
_engine_cache: Optional[Engine] = None
_SessionLocal = None


def get_engine() -> Optional[Engine]:
    """
    Get or create a cached database engine with connection pooling.
    
    Returns:
        SQLAlchemy Engine instance, or None if DATABASE_URL is not configured
    """
    global _engine_cache
    
    if _engine_cache is not None:
        return _engine_cache
    
    from shared.config import Config
    
    if not Config.DATABASE_URL:
        logger.warning("DATABASE_URL not configured")
        return None
    
    try:
        # Add connection timeout to prevent hanging
        # connect_args will be passed to the underlying psycopg2 connection
        connect_args = {
            "connect_timeout": 3,  # 3 second connection timeout (aggressive)
            "options": "-c statement_timeout=3000"  # 3 second statement timeout (in milliseconds)
        }
        
        _engine_cache = create_engine(
            Config.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=10,  # Increased from 5 to handle more concurrent requests
            max_overflow=20,  # Increased from 10
            pool_recycle=3600,
            pool_timeout=5,  # Increased from 3 to 5 seconds for connection acquisition
            echo=False,
            connect_args=connect_args
        )
        logger.info("Database engine created with connection pooling and timeouts")
        return _engine_cache
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}", exc_info=True)
        return None


def get_session():
    """
    Get a database session (for ORM usage if needed in future).
    
    Returns:
        SQLAlchemy Session, or None if engine not available
    """
    global _SessionLocal
    
    engine = get_engine()
    if not engine:
        return None
    
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine)
    
    return _SessionLocal()


def row_to_dict(row, columns=None):
    """
    Convert a SQLAlchemy Row object to a dictionary.
    
    Args:
        row: SQLAlchemy Row object or tuple
        columns: Optional list of column names (for tuple rows)
    
    Returns:
        Dictionary with column names as keys
    """
    if row is None:
        return None
    
    # If it's already a dict-like object (Row with _mapping)
    if hasattr(row, '_mapping'):
        return dict(row._mapping)
    
    # If it's a Row object, convert to dict
    if hasattr(row, '_fields'):
        return {key: getattr(row, key) for key in row._fields}
    
    # If it's a tuple and we have column names
    if isinstance(row, tuple) and columns:
        return {col: val for col, val in zip(columns, row)}
    
    # Fallback: try to access as dict
    if hasattr(row, 'keys'):
        return {key: row[key] for key in row.keys()}
    
    # Last resort: return as-is (might be a tuple)
    return row

