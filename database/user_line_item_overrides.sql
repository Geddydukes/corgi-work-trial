-- Table for storing user overrides of line item decisions
-- Used to collect training data for improving deterministic rules

CREATE TABLE IF NOT EXISTS claims.user_line_item_overrides (
    id BIGSERIAL PRIMARY KEY,
    decision_id BIGINT NOT NULL,
    claim_id BIGINT NOT NULL,
    line_item_index INTEGER NOT NULL,
    line_item_description TEXT NOT NULL,
    line_item_amount NUMERIC(12,2) NOT NULL,
    
    -- Original system decision
    system_should_be_included BOOLEAN NOT NULL,
    system_categories JSONB NOT NULL DEFAULT '{}',
    system_reasoning TEXT,
    system_confidence NUMERIC(5,2),
    
    -- User override
    user_should_be_included BOOLEAN NOT NULL,
    user_reasoning TEXT,
    user_id VARCHAR(100) NOT NULL,
    user_role VARCHAR(50),
    
    -- Metadata
    override_timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    batch_id VARCHAR(100),  -- For grouping overrides into batches for rule improvement
    is_applied_to_rules BOOLEAN DEFAULT FALSE,  -- Whether this override has been used to improve rules
    
    CONSTRAINT user_line_item_overrides_decision_id_fkey 
        FOREIGN KEY (decision_id) REFERENCES claims.decisions(id) ON DELETE CASCADE,
    CONSTRAINT user_line_item_overrides_claim_id_fkey 
        FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    CONSTRAINT user_line_item_overrides_unique_decision_line 
        UNIQUE (decision_id, line_item_index)
);

-- Index for querying overrides by batch
CREATE INDEX IF NOT EXISTS idx_user_overrides_batch_id 
    ON claims.user_line_item_overrides(batch_id) 
    WHERE batch_id IS NOT NULL;

-- Index for querying unprocessed overrides
CREATE INDEX IF NOT EXISTS idx_user_overrides_unprocessed 
    ON claims.user_line_item_overrides(decision_id, is_applied_to_rules) 
    WHERE is_applied_to_rules = FALSE;

-- Index for querying by claim
CREATE INDEX IF NOT EXISTS idx_user_overrides_claim_id 
    ON claims.user_line_item_overrides(claim_id);

COMMENT ON TABLE claims.user_line_item_overrides IS 
    'Stores user overrides of line item decisions for training deterministic rules';

COMMENT ON COLUMN claims.user_line_item_overrides.batch_id IS 
    'Groups overrides into batches (e.g., "batch_2025_01_28") for rule improvement';

COMMENT ON COLUMN claims.user_line_item_overrides.is_applied_to_rules IS 
    'True if this override has been processed and used to improve deterministic rules';

