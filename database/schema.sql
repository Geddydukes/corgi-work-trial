-- ============================================================================
-- Production PostgreSQL Schema for High-Volume Claims Processing
-- Optimized for 100M+ claims over 7 years with 10:1 read:write ratio
-- ============================================================================

-- Drop existing objects if they exist (for clean setup)
DROP SCHEMA IF EXISTS claims CASCADE;
CREATE SCHEMA claims;
SET search_path TO claims, public;

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

CREATE TYPE claim_status_enum AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed',
    'cancelled'
);

CREATE TYPE document_type_enum AS ENUM (
    'lease',
    'invoice',
    'addendum',
    'unknown',
    'supporting_doc'
);

CREATE TYPE processing_status_enum AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed'
);

CREATE TYPE decision_status_enum AS ENUM (
    'approve',
    'deny'
);

CREATE TYPE decision_type_enum AS ENUM (
    'automated',
    'manual_override',
    'appeal',
    'reprocessed'
);

CREATE TYPE audit_action_enum AS ENUM (
    'created',
    'overridden',
    'reviewed',
    'appealed',
    'superseded'
);

CREATE TYPE queue_status_enum AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed',
    'cancelled'
);

-- ============================================================================
-- PARTITIONED TABLES
-- ============================================================================

-- Main claims table (partitioned by created_at yearly)
CREATE TABLE claims (
    id BIGSERIAL,
    claim_tracking_number VARCHAR(50) NOT NULL,
    claim_amount NUMERIC(12,2) NOT NULL CHECK (claim_amount >= 0),
    max_benefit NUMERIC(12,2) CHECK (max_benefit >= 0),
    security_deposit_amount NUMERIC(12,2) CHECK (security_deposit_amount >= 0),
    policyholder_id VARCHAR(100),
    property_id VARCHAR(100),
    claim_date DATE NOT NULL,
    move_out_date DATE,
    lease_start_date DATE,
    lease_end_date DATE,
    status claim_status_enum DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    last_processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    PRIMARY KEY (id, created_at),
    CONSTRAINT claims_tracking_number_unique UNIQUE (claim_tracking_number)
) PARTITION BY RANGE (created_at);

-- Create yearly partitions for claims (2020-2027)
CREATE TABLE claims_2020 PARTITION OF claims
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');

CREATE TABLE claims_2021 PARTITION OF claims
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');

CREATE TABLE claims_2022 PARTITION OF claims
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');

CREATE TABLE claims_2023 PARTITION OF claims
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');

CREATE TABLE claims_2024 PARTITION OF claims
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE claims_2025 PARTITION OF claims
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE claims_2026 PARTITION OF claims
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE claims_2027 PARTITION OF claims
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

CREATE TABLE claims_default PARTITION OF claims
    DEFAULT;

-- ============================================================================
-- REGULAR TABLES
-- ============================================================================

CREATE TABLE claim_documents (
    id BIGSERIAL PRIMARY KEY,
    claim_id BIGINT NOT NULL,
    file_path TEXT NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_hash CHAR(64) NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    mime_type VARCHAR(100),
    document_type document_type_enum,
    classification_confidence NUMERIC(5,2) CHECK (classification_confidence BETWEEN 0 AND 100),
    extracted_text TEXT,
    extracted_text_tsv TSVECTOR,
    ocr_confidence NUMERIC(5,2) CHECK (ocr_confidence BETWEEN 0 AND 100),
    page_count INTEGER CHECK (page_count > 0),
    processing_status processing_status_enum DEFAULT 'pending',
    processing_error TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT claim_documents_claim_id_fkey FOREIGN KEY (claim_id) 
        REFERENCES claims(id) ON DELETE CASCADE,
    CONSTRAINT claim_documents_unique_claim_file UNIQUE (claim_id, file_hash)
);

CREATE TABLE decisions (
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
        REFERENCES claims(id) ON DELETE CASCADE,
    CONSTRAINT decisions_superseded_by_fkey FOREIGN KEY (superseded_by) 
        REFERENCES decisions(id),
    CONSTRAINT decisions_benefit_cap_check CHECK (
        proposed_benefit_amount <= cap_amount OR cap_amount IS NULL
    )
);

CREATE TABLE decision_validation (
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
        REFERENCES claims(id) ON DELETE CASCADE,
    CONSTRAINT decision_validation_decision_id_fkey FOREIGN KEY (decision_id) 
        REFERENCES decisions(id) ON DELETE SET NULL,
    CONSTRAINT decision_validation_unique_claim_date UNIQUE (claim_id, actual_decision_date)
);

CREATE TABLE rules_changelog (
    version VARCHAR(20) PRIMARY KEY,
    released_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    changes_summary TEXT NOT NULL,
    changes_details JSONB NOT NULL,
    author VARCHAR(100) NOT NULL,
    is_breaking_change BOOLEAN DEFAULT FALSE NOT NULL,
    affected_decision_count INTEGER CHECK (affected_decision_count >= 0)
);

CREATE TABLE decision_audit_log (
    id BIGSERIAL,
    decision_id BIGINT,
    claim_id BIGINT NOT NULL,
    action audit_action_enum NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    user_role VARCHAR(50),
    old_values JSONB,
    new_values JSONB,
    reason TEXT,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    PRIMARY KEY (id, created_at),
    CONSTRAINT decision_audit_log_decision_id_fkey FOREIGN KEY (decision_id) 
        REFERENCES decisions(id) ON DELETE SET NULL,
    CONSTRAINT decision_audit_log_claim_id_fkey FOREIGN KEY (claim_id) 
        REFERENCES claims(id) ON DELETE CASCADE
) PARTITION BY RANGE (created_at);

-- Create monthly partitions for decision_audit_log (last 24 months)
-- Note: In production, you'd create these dynamically or via a maintenance job
CREATE TABLE decision_audit_log_2024_01 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE decision_audit_log_2024_02 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
CREATE TABLE decision_audit_log_2024_03 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');
CREATE TABLE decision_audit_log_2024_04 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');
CREATE TABLE decision_audit_log_2024_05 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-05-01') TO ('2024-06-01');
CREATE TABLE decision_audit_log_2024_06 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');
CREATE TABLE decision_audit_log_2024_07 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-07-01') TO ('2024-08-01');
CREATE TABLE decision_audit_log_2024_08 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-08-01') TO ('2024-09-01');
CREATE TABLE decision_audit_log_2024_09 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-09-01') TO ('2024-10-01');
CREATE TABLE decision_audit_log_2024_10 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-10-01') TO ('2024-11-01');
CREATE TABLE decision_audit_log_2024_11 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');
CREATE TABLE decision_audit_log_2024_12 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');
CREATE TABLE decision_audit_log_2025_01 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE decision_audit_log_2025_02 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE decision_audit_log_2025_03 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE decision_audit_log_2025_04 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE decision_audit_log_2025_05 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE decision_audit_log_2025_06 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE decision_audit_log_2025_07 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE decision_audit_log_2025_08 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE decision_audit_log_2025_09 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE decision_audit_log_2025_10 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE decision_audit_log_2025_11 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE decision_audit_log_2025_12 PARTITION OF decision_audit_log
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
CREATE TABLE decision_audit_log_default PARTITION OF decision_audit_log
    DEFAULT;

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

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Claims indexes
CREATE UNIQUE INDEX idx_claims_tracking_number ON claims (claim_tracking_number);
CREATE INDEX idx_claims_status_created_at ON claims (status, created_at DESC);
CREATE INDEX idx_claims_claim_date ON claims (claim_date);
CREATE INDEX idx_claims_policyholder_id ON claims (policyholder_id);
CREATE INDEX idx_claims_property_id ON claims (property_id);
CREATE INDEX idx_claims_priority_status ON claims (priority DESC, status) 
    WHERE status IN ('pending', 'processing');

-- Claim documents indexes
CREATE INDEX idx_claim_documents_claim_id_type ON claim_documents (claim_id, document_type);
CREATE INDEX idx_claim_documents_file_hash ON claim_documents (file_hash);
CREATE INDEX idx_claim_documents_processing_status ON claim_documents (processing_status) 
    WHERE processing_status = 'pending';
CREATE INDEX idx_claim_documents_extracted_text_tsv ON claim_documents 
    USING GIST (extracted_text_tsv);

-- Decisions indexes
CREATE INDEX idx_decisions_claim_id_active ON decisions (claim_id, is_active) 
    WHERE is_active = TRUE;
CREATE INDEX idx_decisions_engine_version_decided_at ON decisions (engine_version, decided_at DESC);
CREATE INDEX idx_decisions_decided_at ON decisions (decided_at DESC);
CREATE INDEX idx_decisions_decision_type ON decisions (decision_type);
CREATE INDEX idx_decisions_superseded_by ON decisions (superseded_by) 
    WHERE superseded_by IS NOT NULL;

-- Decision validation indexes
CREATE INDEX idx_decision_validation_claim_id ON decision_validation (claim_id);
CREATE INDEX idx_decision_validation_decision_id ON decision_validation (decision_id) 
    WHERE decision_id IS NOT NULL;
CREATE INDEX idx_decision_validation_actual_decision_date ON decision_validation (actual_decision_date DESC);

-- Decision audit log indexes
CREATE INDEX idx_decision_audit_log_claim_id_created_at ON decision_audit_log (claim_id, created_at DESC);
CREATE INDEX idx_decision_audit_log_decision_id ON decision_audit_log (decision_id) 
    WHERE decision_id IS NOT NULL;
CREATE INDEX idx_decision_audit_log_user_id ON decision_audit_log (user_id, created_at DESC);
CREATE INDEX idx_decision_audit_log_action ON decision_audit_log (action, created_at DESC);

-- Processing queue indexes
CREATE INDEX idx_processing_queue_status_priority_scheduled ON processing_queue 
    (status, priority DESC, scheduled_at) 
    WHERE status IN ('pending', 'processing');
CREATE INDEX idx_processing_queue_batch_id ON processing_queue (batch_id);
CREATE INDEX idx_processing_queue_claim_id ON processing_queue (claim_id);
CREATE INDEX idx_processing_queue_worker_id ON processing_queue (worker_id) 
    WHERE worker_id IS NOT NULL;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to get active decision for a claim
CREATE OR REPLACE FUNCTION get_active_decision(p_claim_id BIGINT)
RETURNS TABLE (
    id BIGINT,
    decision_type decision_type_enum,
    proposed_status decision_status_enum,
    proposed_benefit_amount NUMERIC,
    confidence_score NUMERIC,
    decided_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        d.id,
        d.decision_type,
        d.proposed_status,
        d.proposed_benefit_amount,
        d.confidence_score,
        d.decided_at
    FROM decisions d
    WHERE d.claim_id = p_claim_id
        AND d.is_active = TRUE
    ORDER BY d.decided_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to calculate decision accuracy metrics
CREATE OR REPLACE FUNCTION calculate_decision_accuracy(
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE (
    total_validations BIGINT,
    accurate_predictions BIGINT,
    accuracy_percentage NUMERIC,
    avg_amount_difference NUMERIC,
    avg_absolute_difference NUMERIC
) AS $$
DECLARE
    v_start_date DATE;
    v_end_date DATE;
BEGIN
    v_start_date := COALESCE(p_start_date, CURRENT_DATE - INTERVAL '30 days');
    v_end_date := COALESCE(p_end_date, CURRENT_DATE);
    
    RETURN QUERY
    WITH validation_metrics AS (
        SELECT 
            COUNT(*) AS total_count,
            COUNT(*) FILTER (
                WHERE d.proposed_status = dv.actual_status
            ) AS accurate_count,
            AVG(ABS(d.proposed_benefit_amount - dv.actual_paid_amount)) AS avg_abs_diff,
            AVG(d.proposed_benefit_amount - dv.actual_paid_amount) AS avg_diff
        FROM decision_validation dv
        INNER JOIN decisions d ON d.id = dv.decision_id
        WHERE dv.actual_decision_date BETWEEN v_start_date AND v_end_date
            AND d.is_active = TRUE
    )
    SELECT 
        vm.total_count,
        vm.accurate_count,
        CASE 
            WHEN vm.total_count > 0 
            THEN ROUND((vm.accurate_count::NUMERIC / vm.total_count::NUMERIC) * 100, 2)
            ELSE 0
        END AS accuracy_pct,
        ROUND(COALESCE(vm.avg_diff, 0), 2) AS avg_amount_diff,
        ROUND(COALESCE(vm.avg_abs_diff, 0), 2) AS avg_absolute_diff
    FROM validation_metrics vm;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to supersede a decision
CREATE OR REPLACE FUNCTION supersede_decision(
    p_old_decision_id BIGINT,
    p_new_decision_id BIGINT
)
RETURNS VOID AS $$
BEGIN
    UPDATE decisions
    SET is_active = FALSE,
        superseded_by = p_new_decision_id
    WHERE id = p_old_decision_id
        AND is_active = TRUE;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Decision % not found or already superseded', p_old_decision_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to archive old claims (placeholder - would move to archive table)
CREATE OR REPLACE FUNCTION archive_old_claims(p_cutoff_date DATE)
RETURNS TABLE (
    archived_count BIGINT,
    archived_claim_ids BIGINT[]
) AS $$
DECLARE
    v_claim_ids BIGINT[];
BEGIN
    SELECT ARRAY_AGG(id)
    INTO v_claim_ids
    FROM claims
    WHERE created_at < p_cutoff_date
        AND status = 'completed';
    
    RETURN QUERY
    SELECT 
        COALESCE(ARRAY_LENGTH(v_claim_ids, 1), 0)::BIGINT AS archived_count,
        COALESCE(v_claim_ids, ARRAY[]::BIGINT[]) AS archived_claim_ids;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Trigger function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to claims
CREATE TRIGGER trigger_claims_updated_at
    BEFORE UPDATE ON claims
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger function to update TSVECTOR from extracted_text
CREATE OR REPLACE FUNCTION update_extracted_text_tsv()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.extracted_text IS NOT NULL THEN
        NEW.extracted_text_tsv := to_tsvector('english', COALESCE(NEW.extracted_text, ''));
    ELSE
        NEW.extracted_text_tsv := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply TSVECTOR trigger to claim_documents
CREATE TRIGGER trigger_claim_documents_tsv
    BEFORE INSERT OR UPDATE OF extracted_text ON claim_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_extracted_text_tsv();

-- Trigger function to supersede old decisions when new active decision created
CREATE OR REPLACE FUNCTION supersede_old_decisions()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_active = TRUE THEN
        UPDATE decisions
        SET is_active = FALSE,
            superseded_by = NEW.id
        WHERE claim_id = NEW.claim_id
            AND id != NEW.id
            AND is_active = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply supersede trigger to decisions
CREATE TRIGGER trigger_decisions_supersede
    AFTER INSERT ON decisions
    FOR EACH ROW
    WHEN (NEW.is_active = TRUE)
    EXECUTE FUNCTION supersede_old_decisions();

-- Trigger function for decision audit logging
CREATE OR REPLACE FUNCTION log_decision_audit()
RETURNS TRIGGER AS $$
DECLARE
    v_action audit_action_enum;
    v_old_values JSONB;
    v_new_values JSONB;
BEGIN
    v_old_values := NULL;
    v_new_values := NULL;
    
    IF TG_OP = 'INSERT' THEN
        v_action := 'created';
        v_new_values := to_jsonb(NEW);
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.is_active = TRUE AND NEW.is_active = FALSE THEN
            v_action := 'superseded';
        ELSIF NEW.decision_type = 'manual_override' AND OLD.decision_type != 'manual_override' THEN
            v_action := 'overridden';
        ELSE
            v_action := 'reviewed';
        END IF;
        v_old_values := to_jsonb(OLD);
        v_new_values := to_jsonb(NEW);
    END IF;
    
    INSERT INTO decision_audit_log (
        decision_id,
        claim_id,
        action,
        user_id,
        old_values,
        new_values
    ) VALUES (
        NEW.id,
        NEW.claim_id,
        v_action,
        COALESCE(NEW.decided_by, 'system'),
        v_old_values,
        v_new_values
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply audit log trigger to decisions
CREATE TRIGGER trigger_decisions_audit_log
    AFTER INSERT OR UPDATE ON decisions
    FOR EACH ROW
    EXECUTE FUNCTION log_decision_audit();

-- ============================================================================
-- GRANTS (adjust based on your security requirements)
-- ============================================================================

-- Example grants (uncomment and adjust as needed)
-- GRANT USAGE ON SCHEMA claims TO application_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA claims TO application_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA claims TO application_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA claims TO application_user;

