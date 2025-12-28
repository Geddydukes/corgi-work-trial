#!/usr/bin/env python3
"""
Setup database and import CSV data
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_database(db_url_base: str = "postgresql://postgres:postgres@localhost:5432"):
    """Create database and schema if needed."""
    try:
        admin_engine = create_engine(f"{db_url_base}/postgres")
        
        with admin_engine.connect() as conn:
            conn.execute(text("COMMIT"))
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'corgi_dev'"))
            exists = result.fetchone()
            
            if not exists:
                logger.info("Creating database corgi_dev...")
                conn.execute(text("COMMIT"))
                conn.execute(text("CREATE DATABASE corgi_dev"))
                logger.info("✓ Database created")
            else:
                logger.info("✓ Database already exists")
        
        db_engine = create_engine(f"{db_url_base}/corgi_dev")
        
        with db_engine.connect() as conn:
            conn.execute(text("SET search_path TO claims, public"))
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'claims' 
                    AND table_name = 'claims'
                )
            """))
            schema_exists = result.scalar()
            
            if not schema_exists:
                logger.info("Loading schema...")
                with open('database/schema.sql', 'r') as f:
                    schema_sql = f.read()
                    conn.execute(text("SET search_path TO claims, public"))
                    for statement in schema_sql.split(';'):
                        statement = statement.strip()
                        if statement and not statement.startswith('--') and len(statement) > 5:
                            try:
                                conn.execute(text(statement))
                                conn.commit()
                            except Exception as e:
                                error_str = str(e).lower()
                                if 'already exists' not in error_str and 'does not exist' not in error_str:
                                    logger.warning(f"Schema statement: {statement[:50]}... -> {e}")
                logger.info("✓ Schema loaded")
            else:
                logger.info("✓ Schema already exists")
        
        return f"{db_url_base}/corgi_dev"
    
    except OperationalError as e:
        logger.error(f"Cannot connect to PostgreSQL: {e}")
        logger.error("Make sure PostgreSQL is running:")
        logger.error("  docker-compose up -d postgres")
        logger.error("  OR")
        logger.error("  Start PostgreSQL manually and ensure it's accessible")
        sys.exit(1)

if __name__ == "__main__":
    db_url = setup_database()
    logger.info(f"Database ready: {db_url}")
    
    from import_claims_csv import import_csv_to_database
    
    csv_path = "/Users/geddydukes/Downloads/Security Deposit Claims - Security Deposit Claims.csv"
    logger.info(f"Importing from: {csv_path}")
    
    claims, validations, decisions, errors = import_csv_to_database(
        csv_path,
        db_url,
        dry_run=False,
        create_decisions=True
    )
    
    logger.info("=" * 60)
    logger.info("IMPORT COMPLETE")
    logger.info(f"Claims: {claims}")
    logger.info(f"Validations: {validations}")
    logger.info(f"Decisions: {decisions}")
    logger.info(f"Errors: {len(errors)}")
    logger.info("=" * 60)

