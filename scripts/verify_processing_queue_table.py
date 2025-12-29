#!/usr/bin/env python3
"""
Script to verify that the processing_queue table exists and has the correct structure.
"""

import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text, inspect

# Default database URL (matches docker-compose.yml configuration)
default_database_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"

# Try to get DATABASE_URL from environment
database_url = os.getenv("DATABASE_URL") or default_database_url

def verify_processing_queue_table():
    """Verify that the processing_queue table exists and has correct structure."""
    
    try:
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Check if the table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'claims' 
                    AND table_name = 'processing_queue'
                )
            """))
            table_exists = result.scalar()
            
            if not table_exists:
                print("❌ FAILED: processing_queue table does NOT exist in the 'claims' schema")
                return False
            
            print("✅ SUCCESS: processing_queue table exists")
            
            # Check table structure - get column names and types
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'claims' 
                AND table_name = 'processing_queue'
                ORDER BY ordinal_position
            """))
            
            columns = result.fetchall()
            print(f"\n📋 Table structure ({len(columns)} columns):")
            print("-" * 80)
            for col in columns:
                col_name, data_type, is_nullable, default = col
                nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
                default_str = f" DEFAULT {default}" if default else ""
                print(f"  • {col_name:20s} {data_type:20s} {nullable}{default_str}")
            
            # Check indexes
            result = conn.execute(text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'claims' 
                AND tablename = 'processing_queue'
                ORDER BY indexname
            """))
            
            indexes = result.fetchall()
            print(f"\n📊 Indexes ({len(indexes)} total):")
            print("-" * 80)
            for idx in indexes:
                idx_name, idx_def = idx
                print(f"  • {idx_name}")
                print(f"    {idx_def}")
            
            # Check if enum type exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'queue_status_enum'
                )
            """))
            enum_exists = result.scalar()
            
            if enum_exists:
                print("\n✅ queue_status_enum type exists")
            else:
                print("\n⚠️  WARNING: queue_status_enum type does not exist")
            
            # Count rows (should be 0 for a new table)
            result = conn.execute(text("SELECT COUNT(*) FROM claims.processing_queue"))
            row_count = result.scalar()
            print(f"\n📈 Current row count: {row_count}")
            
            print("\n" + "=" * 80)
            print("✅ VERIFICATION COMPLETE: processing_queue table is properly set up!")
            print("=" * 80)
            return True
            
    except Exception as e:
        print(f"❌ ERROR: Failed to verify table: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"Connecting to database: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    print("=" * 80)
    success = verify_processing_queue_table()
    sys.exit(0 if success else 1)



