-- ============================================================================
-- Rollback Script for Claims Processing Schema
-- This script safely removes all schema objects in reverse dependency order
-- ============================================================================

SET search_path TO claims, public;

-- Drop triggers first
DROP TRIGGER IF EXISTS trigger_decisions_audit_log ON decisions;
DROP TRIGGER IF EXISTS trigger_decisions_supersede ON decisions;
DROP TRIGGER IF EXISTS trigger_claim_documents_tsv ON claim_documents;
DROP TRIGGER IF EXISTS trigger_claims_updated_at ON claims;

-- Drop functions
DROP FUNCTION IF EXISTS log_decision_audit() CASCADE;
DROP FUNCTION IF EXISTS supersede_old_decisions() CASCADE;
DROP FUNCTION IF EXISTS update_extracted_text_tsv() CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
DROP FUNCTION IF EXISTS archive_old_claims(DATE) CASCADE;
DROP FUNCTION IF EXISTS supersede_decision(BIGINT, BIGINT) CASCADE;
DROP FUNCTION IF EXISTS calculate_decision_accuracy(DATE, DATE) CASCADE;
DROP FUNCTION IF EXISTS get_active_decision(BIGINT) CASCADE;

-- Drop indexes (automatically dropped with tables, but explicit for safety)
-- Note: Indexes are automatically dropped when tables are dropped

-- Drop tables (in reverse dependency order)
DROP TABLE IF EXISTS processing_queue CASCADE;
DROP TABLE IF EXISTS decision_audit_log CASCADE;
DROP TABLE IF EXISTS rules_changelog CASCADE;
DROP TABLE IF EXISTS decision_validation CASCADE;
DROP TABLE IF EXISTS decisions CASCADE;
DROP TABLE IF EXISTS claim_documents CASCADE;
DROP TABLE IF EXISTS claims CASCADE;

-- Drop enum types
DROP TYPE IF EXISTS queue_status_enum CASCADE;
DROP TYPE IF EXISTS audit_action_enum CASCADE;
DROP TYPE IF EXISTS decision_type_enum CASCADE;
DROP TYPE IF EXISTS decision_status_enum CASCADE;
DROP TYPE IF EXISTS processing_status_enum CASCADE;
DROP TYPE IF EXISTS document_type_enum CASCADE;
DROP TYPE IF EXISTS claim_status_enum CASCADE;

-- Drop schema
DROP SCHEMA IF EXISTS claims CASCADE;

-- Reset search path
RESET search_path;


