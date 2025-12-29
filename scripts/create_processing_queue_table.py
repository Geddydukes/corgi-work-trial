#!/usr/bin/env python3
"""
Script to create the processing_queue table if it doesn't exist.
This fixes the error: relation "processing_queue" does not exist
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import shared modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
import os

def create_processing_queue_table():
    """Create the processing_queue table if it doesn't exist."""
    
    # Default database URL (matches docker-compose.yml configuration)
    default_database_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
    
    # Try to get DATABASE_URL from environment directly first
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        # Try importing Config as fallback (may fail if .env has permission issues)
        try:
            from shared.config import Config
            database_url = Config.DATABASE_URL
        except Exception as e:
            print(f"WARNING: Could not load config: {e}")
    
    # Use default if still not set
    if not database_url:
        print(f"Using default DATABASE_URL: {default_database_url}")
        database_url = default_database_url
    
    try:
        engine = create_engine(database_url)
    except Exception as e:
        print(f"ERROR: Failed to create database engine: {e}")
        return False
    
    # SQL statements to execute
    statements = [
        "SET search_path TO claims, public",
        
        # Ensure the enum type exists
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'queue_status_enum') THEN
                CREATE TYPE queue_status_enum AS ENUM (
                    'pending',
                    'processing',
                    'completed',
                    'failed',
                    'cancelled'
                );
            END IF;
        END
        $$
        """,
        
        # Create the processing_queue table if it doesn't exist
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = 'claims' 
                AND table_name = 'processing_queue'
            ) THEN
                CREATE TABLE processing_queue (
                    id BIGSERIAL PRIMARY KEY,
                    batch_id UUID DEFAULT gen_random_uuid() NOT NULL,
                    claim_id BIGINT NOT NULL,
                    priority INTEGER DEFAULT 0 NOT NULL,
                    status queue_status_enum DEFAULT 'pending' NOT NULL,
                    retry_count INTEGER DEFAULT 0 NOT NULL CHECK (retry_count >= 0),
                    max_retries INTEGER DEFAULT 3 NOT NULL CHECK (max_retries >= 0),
                    error_message TEXT,
                    scheduled_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    worker_id VARCHAR(100),
                    CONSTRAINT processing_queue_claim_id_fkey FOREIGN KEY (claim_id) 
                        REFERENCES claims(id) ON DELETE CASCADE
                );
            END IF;
        END
        $$
        """,
        
        # Create indexes if they don't exist
        """CREATE INDEX IF NOT EXISTS idx_processing_queue_status_priority_scheduled 
           ON processing_queue (status, priority DESC, scheduled_at) 
           WHERE status IN ('pending', 'processing')""",
        
        "CREATE INDEX IF NOT EXISTS idx_processing_queue_batch_id ON processing_queue (batch_id)",
        
        "CREATE INDEX IF NOT EXISTS idx_processing_queue_claim_id ON processing_queue (claim_id)",
        
        """CREATE INDEX IF NOT EXISTS idx_processing_queue_worker_id 
           ON processing_queue (worker_id) 
           WHERE worker_id IS NOT NULL"""
    ]
    
    try:
        with engine.begin() as conn:
            # Execute each SQL statement
            for statement in statements:
                conn.execute(text(statement))
            print("SUCCESS: processing_queue table created (or already exists)")
            return True
    except Exception as e:
        print(f"ERROR: Failed to create processing_queue table: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_processing_queue_table()
    sys.exit(0 if success else 1)

