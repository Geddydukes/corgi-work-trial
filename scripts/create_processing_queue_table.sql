-- ============================================================================
-- Script to create the processing_queue table
-- This fixes the error: relation "processing_queue" does not exist
-- ============================================================================

SET search_path TO claims, public;

-- Ensure the enum type exists (should already exist, but safe to create)
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
$$;

-- Create the processing_queue table if it doesn't exist
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
        
        RAISE NOTICE 'Created processing_queue table';
    ELSE
        RAISE NOTICE 'processing_queue table already exists';
    END IF;
END
$$;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_processing_queue_status_priority_scheduled 
    ON processing_queue (status, priority DESC, scheduled_at) 
    WHERE status IN ('pending', 'processing');

CREATE INDEX IF NOT EXISTS idx_processing_queue_batch_id 
    ON processing_queue (batch_id);

CREATE INDEX IF NOT EXISTS idx_processing_queue_claim_id 
    ON processing_queue (claim_id);

CREATE INDEX IF NOT EXISTS idx_processing_queue_worker_id 
    ON processing_queue (worker_id) 
    WHERE worker_id IS NOT NULL;



