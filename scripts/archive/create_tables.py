#!/usr/bin/env python3
"""Create essential tables for CSV import"""

from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tables(db_url: str):
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS claims"))
        conn.execute(text("SET search_path TO claims, public"))
        conn.commit()
        
        conn.execute(text("""
            CREATE TYPE IF NOT EXISTS claim_status_enum AS ENUM (
                'pending', 'processing', 'completed', 'failed', 'cancelled'
            )
        """))
        
        conn.execute(text("""
            CREATE TYPE IF NOT EXISTS decision_status_enum AS ENUM (
                'approve', 'deny'
            )
        """))
        
        conn.execute(text("""
            CREATE TYPE IF NOT EXISTS decision_type_enum AS ENUM (
                'initial', 'appeal', 'reconsideration'
            )
        """))
        conn.commit()
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS claims.claims (
                id BIGSERIAL PRIMARY KEY,
                claim_tracking_number VARCHAR(50) UNIQUE NOT NULL,
                claim_amount NUMERIC(12,2) NOT NULL CHECK (claim_amount >= 0),
                max_benefit NUMERIC(12,2) NOT NULL CHECK (max_benefit >= 0),
                security_deposit_amount NUMERIC(12,2) CHECK (security_deposit_amount >= 0),
                policyholder_id VARCHAR(100),
                property_id VARCHAR(100),
                claim_date DATE NOT NULL,
                move_out_date DATE,
                lease_start_date DATE,
                lease_end_date DATE,
                status claim_status_enum DEFAULT 'completed',
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                created_by VARCHAR(100)
            )
        """))
        conn.commit()
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS claims.decision_validation (
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
            CREATE TABLE IF NOT EXISTS claims.decisions (
                id BIGSERIAL PRIMARY KEY,
                claim_id BIGINT NOT NULL,
                decision_type decision_type_enum NOT NULL,
                proposed_status decision_status_enum NOT NULL,
                proposed_benefit_amount NUMERIC(12,2) NOT NULL CHECK (proposed_benefit_amount >= 0),
                eligible_total NUMERIC(12,2) NOT NULL CHECK (eligible_total >= 0),
                invoice_total NUMERIC(12,2) NOT NULL CHECK (invoice_total >= 0),
                cap_amount NUMERIC(12,2) CHECK (cap_amount >= 0),
                approved_line_items JSONB NOT NULL DEFAULT '[]',
                ineligible_line_items JSONB NOT NULL DEFAULT '[]',
                flags JSONB NOT NULL DEFAULT '{"critical":[],"warnings":[],"info":[]}',
                missing_data JSONB NOT NULL DEFAULT '{"fields":[],"needs_user_input":false}',
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
        
        logger.info("✓ Tables created successfully")

if __name__ == "__main__":
    create_tables("postgresql://postgres:postgres@localhost:5432/corgi_dev")

