-- ============================================================================
-- Performance Test Queries with EXPLAIN ANALYZE
-- Targets: Claim lookup < 10ms, Decision insert < 50ms, 
--          Batch query < 500ms, Full-text search < 200ms
-- ============================================================================

SET search_path TO claims, public;

-- Enable timing
\timing on

-- ============================================================================
-- TEST 1: Claim Lookup by Tracking Number
-- Target: < 10ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    c.id,
    c.claim_tracking_number,
    c.claim_amount,
    c.status,
    c.claim_date,
    COUNT(cd.id) AS document_count
FROM claims c
LEFT JOIN claim_documents cd ON cd.claim_id = c.id
WHERE c.claim_tracking_number = 'CLM-2024-001'
GROUP BY c.id, c.claim_tracking_number, c.claim_amount, c.status, c.claim_date;

-- ============================================================================
-- TEST 2: Decision Insert with Audit Log (via trigger)
-- Target: < 50ms
-- ============================================================================

BEGIN;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
INSERT INTO decisions (
    claim_id, decision_type, proposed_status, proposed_benefit_amount,
    eligible_total, invoice_total, cap_amount, approved_line_items,
    ineligible_line_items, flags, missing_data, reasoning,
    confidence_score, engine_version, processing_time_ms,
    decided_by
)
SELECT 
    c.id,
    'automated'::decision_type_enum,
    'approve'::decision_status_enum,
    2500.00,
    2500.00,
    2500.00,
    2500.00,
    '[{"item":"Test","amount":2500.00}]'::JSONB,
    '[]'::JSONB,
    '{"critical":[],"warnings":[],"info":[]}'::JSONB,
    '{"fields":[],"needs_user_input":false}'::JSONB,
    '{"summary":"Test decision"}'::JSONB,
    95.00,
    'v2.1.0',
    1000,
    'system'
FROM claims c
WHERE c.claim_tracking_number = 'CLM-2024-003'
LIMIT 1;

ROLLBACK;

-- ============================================================================
-- TEST 3: Batch Evaluation Query (100 claims)
-- Target: < 500ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    c.id,
    c.claim_tracking_number,
    c.claim_amount,
    c.status,
    c.priority,
    d.proposed_status,
    d.proposed_benefit_amount,
    d.confidence_score,
    COUNT(cd.id) AS document_count,
    MAX(cd.processing_status) AS doc_processing_status
FROM claims c
LEFT JOIN decisions d ON d.claim_id = c.id AND d.is_active = TRUE
LEFT JOIN claim_documents cd ON cd.claim_id = c.id
WHERE c.status IN ('pending', 'processing')
    AND c.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.id, c.claim_tracking_number, c.claim_amount, c.status, 
         c.priority, d.proposed_status, d.proposed_benefit_amount, 
         d.confidence_score
ORDER BY c.priority DESC, c.created_at ASC
LIMIT 100;

-- ============================================================================
-- TEST 4: Full-Text Search Across Documents
-- Target: < 200ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    cd.id,
    cd.claim_id,
    cd.original_filename,
    cd.document_type,
    cd.classification_confidence,
    c.claim_tracking_number,
    ts_rank(cd.extracted_text_tsv, query) AS rank
FROM claim_documents cd
JOIN claims c ON c.id = cd.claim_id
CROSS JOIN to_tsquery('english', 'lease & agreement') AS query
WHERE cd.extracted_text_tsv @@ query
    AND cd.processing_status = 'completed'
ORDER BY rank DESC
LIMIT 50;

-- ============================================================================
-- TEST 5: Get Active Decision Function
-- Target: < 20ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT * FROM get_active_decision(
    (SELECT id FROM claims WHERE claim_tracking_number = 'CLM-2024-001' LIMIT 1)
);

-- ============================================================================
-- TEST 6: Decision Accuracy Calculation
-- Target: < 300ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT * FROM calculate_decision_accuracy(
    CURRENT_DATE - INTERVAL '90 days',
    CURRENT_DATE
);

-- ============================================================================
-- TEST 7: Claims by Policyholder (with pagination)
-- Target: < 100ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    c.id,
    c.claim_tracking_number,
    c.claim_date,
    c.status,
    c.claim_amount,
    d.proposed_status,
    d.proposed_benefit_amount
FROM claims c
LEFT JOIN decisions d ON d.claim_id = c.id AND d.is_active = TRUE
WHERE c.policyholder_id = 'POL-12345'
ORDER BY c.claim_date DESC
LIMIT 20 OFFSET 0;

-- ============================================================================
-- TEST 8: Processing Queue Query (worker assignment)
-- Target: < 50ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    pq.id,
    pq.claim_id,
    pq.priority,
    pq.batch_id,
    c.claim_tracking_number,
    c.claim_amount
FROM processing_queue pq
JOIN claims c ON c.id = pq.claim_id
WHERE pq.status = 'pending'
    AND pq.scheduled_at <= NOW()
ORDER BY pq.priority DESC, pq.scheduled_at ASC
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- ============================================================================
-- TEST 9: Decision History with Audit Trail
-- Target: < 150ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    d.id,
    d.decision_type,
    d.proposed_status,
    d.proposed_benefit_amount,
    d.decided_at,
    d.is_active,
    d.superseded_by,
    COUNT(dal.id) AS audit_log_count,
    MAX(dal.created_at) AS last_audit_time
FROM decisions d
LEFT JOIN decision_audit_log dal ON dal.decision_id = d.id
WHERE d.claim_id = (SELECT id FROM claims WHERE claim_tracking_number = 'CLM-2024-001' LIMIT 1)
GROUP BY d.id, d.decision_type, d.proposed_status, d.proposed_benefit_amount,
         d.decided_at, d.is_active, d.superseded_by
ORDER BY d.decided_at DESC;

-- ============================================================================
-- TEST 10: Partition Pruning Test (date range query)
-- Target: < 50ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    COUNT(*) AS claim_count,
    SUM(claim_amount) AS total_amount,
    AVG(claim_amount) AS avg_amount,
    status
FROM claims
WHERE created_at >= '2024-01-01'
    AND created_at < '2024-02-01'
GROUP BY status;

-- ============================================================================
-- TEST 11: Validation Metrics Join
-- Target: < 200ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    d.engine_version,
    COUNT(*) AS total_decisions,
    COUNT(dv.id) AS validated_count,
    COUNT(*) FILTER (WHERE d.proposed_status = dv.actual_status) AS accurate_count,
    AVG(ABS(d.proposed_benefit_amount - COALESCE(dv.actual_paid_amount, 0))) AS avg_amount_diff
FROM decisions d
LEFT JOIN decision_validation dv ON dv.decision_id = d.id
WHERE d.decided_at >= CURRENT_DATE - INTERVAL '30 days'
    AND d.is_active = TRUE
GROUP BY d.engine_version
ORDER BY d.engine_version;

-- ============================================================================
-- TEST 12: Complex Multi-Table Join (dashboard query)
-- Target: < 500ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    DATE_TRUNC('day', c.created_at) AS claim_date,
    c.status,
    COUNT(DISTINCT c.id) AS claim_count,
    COUNT(DISTINCT d.id) AS decision_count,
    COUNT(DISTINCT cd.id) AS document_count,
    SUM(c.claim_amount) AS total_claim_amount,
    AVG(d.proposed_benefit_amount) AS avg_benefit_amount,
    AVG(d.confidence_score) AS avg_confidence
FROM claims c
LEFT JOIN decisions d ON d.claim_id = c.id AND d.is_active = TRUE
LEFT JOIN claim_documents cd ON cd.claim_id = c.id
WHERE c.created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE_TRUNC('day', c.created_at), c.status
ORDER BY claim_date DESC, c.status;

-- ============================================================================
-- TEST 13: Index-Only Scan Test
-- Target: < 20ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    status,
    COUNT(*) AS count,
    MIN(created_at) AS earliest,
    MAX(created_at) AS latest
FROM claims
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY status;

-- ============================================================================
-- TEST 14: GIN Index Full-Text Search Performance
-- Target: < 200ms
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    cd.id,
    cd.claim_id,
    cd.original_filename,
    LEFT(cd.extracted_text, 100) AS text_preview,
    ts_rank_cd(cd.extracted_text_tsv, query) AS rank
FROM claim_documents cd
CROSS JOIN to_tsquery('english', 'invoice | repair | damage') AS query
WHERE cd.extracted_text_tsv @@ query
    AND cd.processing_status = 'completed'
ORDER BY rank DESC
LIMIT 25;

-- ============================================================================
-- TEST 15: Batch Update Performance
-- Target: < 100ms
-- ============================================================================

BEGIN;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
UPDATE processing_queue
SET status = 'processing',
    started_at = NOW(),
    worker_id = 'test_worker'
WHERE id IN (
    SELECT id FROM processing_queue
    WHERE status = 'pending'
        AND scheduled_at <= NOW()
    ORDER BY priority DESC, scheduled_at ASC
    LIMIT 10
);

ROLLBACK;

-- ============================================================================
-- Performance Summary Query
-- ============================================================================

SELECT
    'Performance Test Summary' AS test_name,
    'Run EXPLAIN ANALYZE on queries above' AS instructions,
    'Check execution times against targets' AS notes;

