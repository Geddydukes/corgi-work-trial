#!/usr/bin/env python3
"""
Fix schema and import CSV - creates tables without partition issues
"""

from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_fixed_schema(db_url: str):
    """Create schema with non-partitioned claims table for CSV import"""
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS claims"))
        conn.execute(text("SET search_path TO claims, public"))
        conn.commit()
        
        enums = [
            ("claim_status_enum", "('pending', 'processing', 'completed', 'failed', 'cancelled')"),
            ("document_type_enum", "('lease', 'invoice', 'addendum', 'unknown', 'supporting_doc')"),
            ("processing_status_enum", "('pending', 'processing', 'completed', 'failed')"),
            ("decision_status_enum", "('approve', 'deny')"),
            ("decision_type_enum", "('initial', 'appeal', 'reconsideration')"),
            ("audit_action_enum", "('create', 'update', 'delete', 'supersede')"),
            ("queue_status_enum", "('pending', 'processing', 'completed', 'failed', 'cancelled')"),
        ]
        
        for enum_name, values in enums:
            try:
                conn.execute(text(f"DROP TYPE IF EXISTS {enum_name} CASCADE"))
                conn.commit()
                conn.execute(text(f"CREATE TYPE {enum_name} AS ENUM {values}"))
                conn.commit()
            except Exception as e:
                logger.warning(f"Enum {enum_name}: {e}")
                conn.rollback()
        
        conn.execute(text("DROP TABLE IF EXISTS claims.decisions CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS claims.decision_validation CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS claims.claims CASCADE"))
        conn.commit()
        
        conn.execute(text("""
            CREATE TABLE claims.claims (
                id BIGSERIAL PRIMARY KEY,
                claim_tracking_number VARCHAR(50) UNIQUE NOT NULL,
                claim_amount NUMERIC(12,2) NOT NULL CHECK (claim_amount >= 0),
                max_benefit NUMERIC(12,2) CHECK (max_benefit >= 0),
                security_deposit_amount NUMERIC(12,2) CHECK (security_deposit_amount >= 0),
                policyholder_id VARCHAR(100),
                property_id VARCHAR(100),
                claim_date DATE NOT NULL,
                move_out_date DATE,
                lease_start_date DATE,
                lease_end_date DATE,
                status claim_status_enum DEFAULT 'completed',
                priority INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                last_processed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                created_by VARCHAR(100),
                updated_by VARCHAR(100)
            )
        """))
        conn.commit()
        
        conn.execute(text("""
            CREATE TABLE claims.decision_validation (
                id BIGSERIAL PRIMARY KEY,
                claim_id BIGINT NOT NULL,
                decision_id BIGINT,
                actual_status decision_status_enum NOT NULL,
                actual_paid_amount NUMERIC(12,2) NOT NULL CHECK (actual_paid_amount >= 0),
                actual_decision_date DATE NOT NULL,
                adjudication_notes TEXT,
                adjudicator_id VARCHAR(100),
                validation_source VARCHAR(50) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                CONSTRAINT decision_validation_claim_id_fkey FOREIGN KEY (claim_id) 
                    REFERENCES claims.claims(id) ON DELETE CASCADE,
                CONSTRAINT decision_validation_unique_claim_date UNIQUE (claim_id, actual_decision_date)
            )
        """))
        conn.commit()
        
        conn.execute(text("""
            CREATE TABLE claims.decisions (
                id BIGSERIAL PRIMARY KEY,
                claim_id BIGINT NOT NULL,
                decision_type decision_type_enum NOT NULL,
                proposed_status decision_status_enum NOT NULL,
                proposed_benefit_amount NUMERIC(12,2) NOT NULL CHECK (proposed_benefit_amount >= 0),
                eligible_total NUMERIC(12,2) NOT NULL CHECK (eligible_total >= 0),
                invoice_total NUMERIC(12,2) NOT NULL CHECK (invoice_total >= 0),
                cap_amount NUMERIC(12,2) CHECK (cap_amount >= 0),
                approved_line_items JSONB NOT NULL,
                ineligible_line_items JSONB NOT NULL,
                flags JSONB NOT NULL,
                missing_data JSONB NOT NULL,
                reasoning JSONB NOT NULL,
                confidence_score NUMERIC(5,2) CHECK (confidence_score BETWEEN 0 AND 100),
                engine_version VARCHAR(20) NOT NULL,
                processing_time_ms INTEGER CHECK (processing_time_ms >= 0),
                decided_by VARCHAR(100) NOT NULL,
                decided_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                superseded_by BIGINT,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                CONSTRAINT decisions_claim_id_fkey FOREIGN KEY (claim_id) 
                    REFERENCES claims.claims(id) ON DELETE CASCADE
            )
        """))
        conn.commit()
        
        logger.info("✓ Schema created successfully")

if __name__ == "__main__":
    import sys
    from import_claims_csv import import_csv_to_database
    
    db_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
    
    logger.info("Creating schema...")
    create_fixed_schema(db_url)
    
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
    
    if claims > 0:
        logger.info("✓ Data successfully imported!")
    else:
        logger.error("✗ Import failed - check errors above")

