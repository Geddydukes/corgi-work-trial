"""Add soft delete, UTC enforcement, encryption metadata, and update FK behaviors

Revision ID: 002_soft_delete_utc_encryption
Revises: 001_initial_schema
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_soft_delete_utc_encryption'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET search_path TO claims, public")
    
    # ============================================================================
    # 1. Create UTC function for timestamp defaults
    # ============================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION utc_now()
        RETURNS TIMESTAMPTZ AS $$
        BEGIN
            RETURN (NOW() AT TIME ZONE 'UTC');
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)
    
    # ============================================================================
    # 2. Add deleted_at column to all tables (except audit log and changelog)
    # ============================================================================
    
    # Claims table
    op.execute("ALTER TABLE claims ADD COLUMN deleted_at TIMESTAMPTZ NULL")
    op.execute("""
        CREATE INDEX idx_claims_deleted_at_null ON claims (id) 
        WHERE deleted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX idx_claims_deleted_at ON claims (deleted_at) 
        WHERE deleted_at IS NOT NULL
    """)
    op.execute("""
        COMMENT ON COLUMN claims.deleted_at IS 
        'Soft delete timestamp. NULL = active, NOT NULL = deleted. UTC timezone.'
    """)
    
    # Claim documents table
    op.execute("ALTER TABLE claim_documents ADD COLUMN deleted_at TIMESTAMPTZ NULL")
    op.execute("""
        CREATE INDEX idx_claim_documents_deleted_at_null ON claim_documents (claim_id, document_type) 
        WHERE deleted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX idx_claim_documents_deleted_at ON claim_documents (deleted_at) 
        WHERE deleted_at IS NOT NULL
    """)
    op.execute("""
        COMMENT ON COLUMN claim_documents.deleted_at IS 
        'Soft delete timestamp. NULL = active, NOT NULL = deleted. UTC timezone.'
    """)
    
    # Decisions table
    op.execute("ALTER TABLE decisions ADD COLUMN deleted_at TIMESTAMPTZ NULL")
    op.execute("""
        CREATE INDEX idx_decisions_deleted_at_null ON decisions (claim_id, is_active) 
        WHERE deleted_at IS NULL AND is_active = TRUE
    """)
    op.execute("""
        CREATE INDEX idx_decisions_deleted_at ON decisions (deleted_at) 
        WHERE deleted_at IS NOT NULL
    """)
    op.execute("""
        COMMENT ON COLUMN decisions.deleted_at IS 
        'Soft delete timestamp. NULL = active, NOT NULL = deleted. UTC timezone.'
    """)
    
    # Decision validation table
    op.execute("ALTER TABLE decision_validation ADD COLUMN deleted_at TIMESTAMPTZ NULL")
    op.execute("""
        CREATE INDEX idx_decision_validation_deleted_at_null ON decision_validation (claim_id) 
        WHERE deleted_at IS NULL
    """)
    op.execute("""
        COMMENT ON COLUMN decision_validation.deleted_at IS 
        'Soft delete timestamp. NULL = active, NOT NULL = deleted. UTC timezone.'
    """)
    
    # Processing queue table
    op.execute("ALTER TABLE processing_queue ADD COLUMN deleted_at TIMESTAMPTZ NULL")
    op.execute("""
        CREATE INDEX idx_processing_queue_deleted_at_null ON processing_queue (status, priority, scheduled_at) 
        WHERE deleted_at IS NULL AND status IN ('pending', 'processing')
    """)
    op.execute("""
        COMMENT ON COLUMN processing_queue.deleted_at IS 
        'Soft delete timestamp. NULL = active, NOT NULL = deleted. UTC timezone.'
    """)
    
    # Note: decision_audit_log and rules_changelog do NOT get deleted_at
    # (audit trail and version history should never be deleted)
    
    # ============================================================================
    # 3. Add encryption metadata columns to claim_documents
    # ============================================================================
    op.execute("""
        ALTER TABLE claim_documents 
        ADD COLUMN encryption_key_id VARCHAR(100) NULL,
        ADD COLUMN encryption_algorithm VARCHAR(50) DEFAULT 'AES-256-GCM',
        ADD COLUMN encryption_iv BYTEA NULL
    """)
    op.execute("""
        COMMENT ON COLUMN claim_documents.extracted_text IS 
        'Encrypted OCR text. Must be decrypted using encryption_key_id and encryption_iv. Algorithm: AES-256-GCM. Stored in UTC.'
    """)
    op.execute("""
        COMMENT ON COLUMN claim_documents.encryption_key_id IS 
        'Key identifier from key management service (e.g., AWS KMS key ID)'
    """)
    op.execute("""
        COMMENT ON COLUMN claim_documents.encryption_algorithm IS 
        'Encryption algorithm used. Default: AES-256-GCM'
    """)
    op.execute("""
        COMMENT ON COLUMN claim_documents.encryption_iv IS 
        'Initialization vector for encryption (stored as BYTEA)'
    """)
    
    # ============================================================================
    # 4. Update timestamp defaults to use UTC function
    # ============================================================================
    
    # Note: For existing columns, we can't change the default directly
    # We'll update the trigger functions instead
    # New columns will use utc_now() by default
    
    # ============================================================================
    # 5. Update trigger functions to use UTC
    # ============================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = utc_now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # ============================================================================
    # 6. Create soft delete functions
    # ============================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION soft_delete_claim(
            p_claim_id BIGINT, 
            p_deleted_by VARCHAR(100)
        )
        RETURNS VOID AS $$
        BEGIN
            -- Soft delete claim
            UPDATE claims
            SET deleted_at = utc_now(),
                updated_at = utc_now(),
                updated_by = p_deleted_by
            WHERE id = p_claim_id
                AND deleted_at IS NULL;
            
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Claim % not found or already deleted', p_claim_id;
            END IF;
            
            -- Cascade soft delete to related records
            UPDATE claim_documents
            SET deleted_at = utc_now()
            WHERE claim_id = p_claim_id
                AND deleted_at IS NULL;
            
            UPDATE decisions
            SET deleted_at = utc_now()
            WHERE claim_id = p_claim_id
                AND deleted_at IS NULL;
            
            UPDATE processing_queue
            SET deleted_at = utc_now()
            WHERE claim_id = p_claim_id
                AND deleted_at IS NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE OR REPLACE FUNCTION restore_soft_deleted_claim(p_claim_id BIGINT)
        RETURNS VOID AS $$
        BEGIN
            UPDATE claims
            SET deleted_at = NULL,
                updated_at = utc_now()
            WHERE id = p_claim_id
                AND deleted_at IS NOT NULL;
            
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Claim % not found or not deleted', p_claim_id;
            END IF;
            
            -- Restore related records
            UPDATE claim_documents
            SET deleted_at = NULL
            WHERE claim_id = p_claim_id
                AND deleted_at IS NOT NULL;
            
            UPDATE decisions
            SET deleted_at = NULL
            WHERE claim_id = p_claim_id
                AND deleted_at IS NOT NULL;
            
            UPDATE processing_queue
            SET deleted_at = NULL
            WHERE claim_id = p_claim_id
                AND deleted_at IS NOT NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # ============================================================================
    # 7. Update foreign key constraints (CASCADE -> RESTRICT for critical tables)
    # ============================================================================
    
    # Drop existing constraints
    op.execute("ALTER TABLE claim_documents DROP CONSTRAINT IF EXISTS claim_documents_claim_id_fkey")
    op.execute("ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_claim_id_fkey")
    op.execute("ALTER TABLE processing_queue DROP CONSTRAINT IF EXISTS processing_queue_claim_id_fkey")
    op.execute("ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_superseded_by_fkey")
    
    # Recreate with RESTRICT behavior
    op.execute("""
        ALTER TABLE claim_documents 
        ADD CONSTRAINT claim_documents_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
    """)
    
    op.execute("""
        ALTER TABLE decisions 
        ADD CONSTRAINT decisions_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
    """)
    
    op.execute("""
        ALTER TABLE processing_queue 
        ADD CONSTRAINT processing_queue_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
    """)
    
    op.execute("""
        ALTER TABLE decisions 
        ADD CONSTRAINT decisions_superseded_by_fkey 
        FOREIGN KEY (superseded_by) REFERENCES decisions(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
    """)
    
    # Note: decision_validation and decision_audit_log keep CASCADE
    # (historical data and audit trail)
    
    # ============================================================================
    # 8. Create data retention policy tables
    # ============================================================================
    op.execute("""
        CREATE TABLE data_retention_policy (
            table_name VARCHAR(100) PRIMARY KEY,
            retention_days INTEGER NOT NULL,
            archive_table VARCHAR(100),
            purge_after_archive BOOLEAN DEFAULT FALSE NOT NULL,
            last_archived_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT utc_now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT utc_now() NOT NULL
        )
    """)
    
    op.execute("""
        INSERT INTO data_retention_policy (table_name, retention_days, archive_table, purge_after_archive, notes) VALUES
        ('claims', 2555, 'claims_archive', FALSE, '7 years for completed claims'),
        ('claim_documents', 2555, 'claim_documents_archive', FALSE, '7 years, archive with encryption'),
        ('decisions', 2555, 'decisions_archive', FALSE, '7 years'),
        ('decision_validation', 2555, 'decision_validation_archive', FALSE, '7 years'),
        ('decision_audit_log', 3650, 'decision_audit_log_archive', FALSE, '10 years'),
        ('processing_queue', 30, NULL, TRUE, '30 days then purge'),
        ('soft_deleted_claims', 90, NULL, TRUE, '90 days then hard delete')
    """)
    
    # ============================================================================
    # 9. Create retention and purge functions
    # ============================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION purge_soft_deleted_claims()
        RETURNS TABLE (
            purged_count BIGINT,
            purged_claim_ids BIGINT[]
        ) AS $$
        DECLARE
            v_cutoff_date TIMESTAMPTZ;
            v_claim_ids BIGINT[];
            v_count BIGINT;
        BEGIN
            v_cutoff_date := utc_now() - INTERVAL '90 days';
            
            -- Get IDs to purge
            SELECT ARRAY_AGG(id)
            INTO v_claim_ids
            FROM claims
            WHERE deleted_at IS NOT NULL
                AND deleted_at < v_cutoff_date;
            
            -- Hard delete (CASCADE will handle related records)
            WITH deleted_claims AS (
                DELETE FROM claims
                WHERE deleted_at IS NOT NULL
                    AND deleted_at < v_cutoff_date
                RETURNING id
            )
            SELECT COUNT(*) INTO v_count FROM deleted_claims;
            
            RETURN QUERY
            SELECT 
                COALESCE(v_count, 0)::BIGINT,
                COALESCE(v_claim_ids, ARRAY[]::BIGINT[]);
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # ============================================================================
    # 10. Add timezone comments to all timestamp columns
    # ============================================================================
    op.execute("""
        COMMENT ON COLUMN claims.created_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN claims.updated_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN claims.last_processed_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN claim_documents.created_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN claim_documents.processed_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN decisions.created_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN decisions.decided_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN decision_validation.created_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN decision_validation.actual_decision_date IS 'Date only, no timezone';
        COMMENT ON COLUMN rules_changelog.released_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN decision_audit_log.created_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN processing_queue.scheduled_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN processing_queue.started_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
        COMMENT ON COLUMN processing_queue.completed_at IS 'UTC timestamp, stored as TIMESTAMPTZ';
    """)
    
    # ============================================================================
    # 11. Create FK cascade policy documentation table
    # ============================================================================
    op.execute("""
        CREATE TABLE fk_cascade_policy (
            table_name VARCHAR(100),
            column_name VARCHAR(100),
            references_table VARCHAR(100),
            on_delete_action VARCHAR(20) NOT NULL,
            on_update_action VARCHAR(20) NOT NULL,
            rationale TEXT,
            created_at TIMESTAMPTZ DEFAULT utc_now() NOT NULL,
            PRIMARY KEY (table_name, column_name)
        )
    """)
    
    op.execute("""
        INSERT INTO fk_cascade_policy (table_name, column_name, references_table, on_delete_action, on_update_action, rationale) VALUES
        ('claim_documents', 'claim_id', 'claims', 'RESTRICT', 'CASCADE', 'Prevent accidental deletion of documents when claim is deleted'),
        ('decisions', 'claim_id', 'claims', 'RESTRICT', 'CASCADE', 'Decisions are critical records, require explicit deletion'),
        ('decisions', 'superseded_by', 'decisions', 'RESTRICT', 'CASCADE', 'Prevent orphaned decision references'),
        ('decision_validation', 'claim_id', 'claims', 'CASCADE', 'CASCADE', 'Historical validation data can be deleted with claim'),
        ('decision_validation', 'decision_id', 'decisions', 'SET NULL', 'CASCADE', 'Validation independent of decision'),
        ('decision_audit_log', 'claim_id', 'claims', 'CASCADE', 'CASCADE', 'Audit trail can be deleted with claim'),
        ('decision_audit_log', 'decision_id', 'decisions', 'SET NULL', 'CASCADE', 'Audit log independent of decision'),
        ('processing_queue', 'claim_id', 'claims', 'RESTRICT', 'CASCADE', 'Queue items should be handled explicitly')
    """)


def downgrade():
    op.execute("SET search_path TO claims, public")
    
    # Drop documentation tables
    op.execute("DROP TABLE IF EXISTS fk_cascade_policy CASCADE")
    op.execute("DROP TABLE IF EXISTS data_retention_policy CASCADE")
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS purge_soft_deleted_claims() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS restore_soft_deleted_claim(BIGINT) CASCADE")
    op.execute("DROP FUNCTION IF EXISTS soft_delete_claim(BIGINT, VARCHAR) CASCADE")
    
    # Revert foreign key constraints to original CASCADE behavior
    op.execute("ALTER TABLE claim_documents DROP CONSTRAINT IF EXISTS claim_documents_claim_id_fkey")
    op.execute("ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_claim_id_fkey")
    op.execute("ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_superseded_by_fkey")
    op.execute("ALTER TABLE processing_queue DROP CONSTRAINT IF EXISTS processing_queue_claim_id_fkey")
    
    # Restore original CASCADE constraints
    op.execute("""
        ALTER TABLE claim_documents 
        ADD CONSTRAINT claim_documents_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
    """)
    
    op.execute("""
        ALTER TABLE decisions 
        ADD CONSTRAINT decisions_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
    """)
    
    op.execute("""
        ALTER TABLE decisions 
        ADD CONSTRAINT decisions_superseded_by_fkey 
        FOREIGN KEY (superseded_by) REFERENCES decisions(id)
    """)
    
    op.execute("""
        ALTER TABLE processing_queue 
        ADD CONSTRAINT processing_queue_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
    """)
    
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_processing_queue_deleted_at_null")
    op.execute("DROP INDEX IF EXISTS idx_decision_validation_deleted_at_null")
    op.execute("DROP INDEX IF EXISTS idx_decisions_deleted_at")
    op.execute("DROP INDEX IF EXISTS idx_decisions_deleted_at_null")
    op.execute("DROP INDEX IF EXISTS idx_claim_documents_deleted_at")
    op.execute("DROP INDEX IF EXISTS idx_claim_documents_deleted_at_null")
    op.execute("DROP INDEX IF EXISTS idx_claims_deleted_at")
    op.execute("DROP INDEX IF EXISTS idx_claims_deleted_at_null")
    
    # Drop columns
    op.execute("ALTER TABLE processing_queue DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE decision_validation DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE decisions DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE claim_documents DROP COLUMN IF EXISTS encryption_iv")
    op.execute("ALTER TABLE claim_documents DROP COLUMN IF EXISTS encryption_algorithm")
    op.execute("ALTER TABLE claim_documents DROP COLUMN IF EXISTS encryption_key_id")
    op.execute("ALTER TABLE claim_documents DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE claims DROP COLUMN IF EXISTS deleted_at")
    
    # Revert trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Drop UTC function
    op.execute("DROP FUNCTION IF EXISTS utc_now() CASCADE")

