-- ============================================================================
-- Sample Data INSERT Script
-- 20 diverse test cases covering various scenarios
-- ============================================================================

SET search_path TO claims, public;

-- Clear existing data (optional - use with caution in production)
-- TRUNCATE TABLE processing_queue CASCADE;
-- TRUNCATE TABLE decision_audit_log CASCADE;
-- TRUNCATE TABLE decision_validation CASCADE;
-- TRUNCATE TABLE decisions CASCADE;
-- TRUNCATE TABLE claim_documents CASCADE;
-- TRUNCATE TABLE claims CASCADE;
-- TRUNCATE TABLE rules_changelog CASCADE;

-- Insert sample claims (20 diverse cases)
INSERT INTO claims (
    claim_tracking_number, claim_amount, max_benefit, security_deposit_amount,
    policyholder_id, property_id, claim_date, move_out_date,
    lease_start_date, lease_end_date, status, priority,
    created_at, created_by
) VALUES
-- Case 1: Standard approved claim with full benefit
('CLM-2024-001', 5000.00, 5000.00, 2000.00, 'POL-12345', 'PROP-001', 
 '2024-01-15', '2024-01-20', '2023-01-01', '2024-01-31', 'completed', 0,
 '2024-01-10 10:00:00+00', 'system'),

-- Case 2: High-value claim exceeding max benefit
('CLM-2024-002', 15000.00, 10000.00, 3000.00, 'POL-12346', 'PROP-002',
 '2024-02-01', '2024-02-15', '2022-06-01', '2024-02-28', 'completed', 1,
 '2024-01-25 14:30:00+00', 'system'),

-- Case 3: Pending claim with missing documents
('CLM-2024-003', 3500.00, 3500.00, 1500.00, 'POL-12347', 'PROP-003',
 '2024-02-10', NULL, '2023-03-01', '2024-02-29', 'pending', 2,
 '2024-02-05 09:15:00+00', 'user_001'),

-- Case 4: Failed processing claim
('CLM-2024-004', 2800.00, 2800.00, 1200.00, 'POL-12348', 'PROP-004',
 '2024-01-20', '2024-01-25', '2023-05-01', '2024-01-31', 'failed', 0,
 '2024-01-18 11:20:00+00', 'system'),

-- Case 5: Low priority claim
('CLM-2024-005', 1200.00, 1200.00, 500.00, 'POL-12349', 'PROP-005',
 '2024-03-01', '2024-03-05', '2023-07-01', '2024-03-31', 'processing', 5,
 '2024-02-28 16:45:00+00', 'system'),

-- Case 6: Claim with retry count
('CLM-2024-006', 4500.00, 4500.00, 1800.00, 'POL-12350', 'PROP-006',
 '2024-02-15', '2024-02-20', '2023-08-01', '2024-02-29', 'processing', 1,
 '2024-02-12 08:30:00+00', 'system'),

-- Case 7: Cancelled claim
('CLM-2024-007', 6000.00, 6000.00, 2500.00, 'POL-12351', 'PROP-007',
 '2024-01-30', NULL, '2023-09-01', '2024-01-31', 'cancelled', 0,
 '2024-01-28 13:10:00+00', 'user_002'),

-- Case 8: Claim with no security deposit
('CLM-2024-008', 2200.00, 2200.00, NULL, 'POL-12352', 'PROP-008',
 '2024-03-05', '2024-03-10', '2023-10-01', '2024-03-31', 'completed', 0,
 '2024-03-01 10:00:00+00', 'system'),

-- Case 9: Very old claim (2023)
('CLM-2023-001', 8000.00, 8000.00, 3500.00, 'POL-12353', 'PROP-009',
 '2023-12-15', '2023-12-20', '2022-01-01', '2023-12-31', 'completed', 0,
 '2023-12-10 09:00:00+00', 'system'),

-- Case 10: Claim with multiple documents
('CLM-2024-009', 5500.00, 5500.00, 2200.00, 'POL-12354', 'PROP-010',
 '2024-02-20', '2024-02-25', '2023-11-01', '2024-02-29', 'processing', 1,
 '2024-02-18 14:20:00+00', 'system'),

-- Case 11: Denied claim
('CLM-2024-010', 3000.00, 3000.00, 1500.00, 'POL-12355', 'PROP-011',
 '2024-01-25', '2024-01-30', '2023-12-01', '2024-01-31', 'completed', 0,
 '2024-01-22 11:30:00+00', 'system'),

-- Case 12: Claim with partial benefit
('CLM-2024-011', 7000.00, 5000.00, 2800.00, 'POL-12356', 'PROP-012',
 '2024-03-10', '2024-03-15', '2023-04-01', '2024-03-31', 'completed', 2,
 '2024-03-05 15:00:00+00', 'system'),

-- Case 13: High priority urgent claim
('CLM-2024-012', 4200.00, 4200.00, 1700.00, 'POL-12357', 'PROP-013',
 '2024-02-28', '2024-03-05', '2023-06-01', '2024-02-29', 'pending', 10,
 '2024-02-25 12:00:00+00', 'user_003'),

-- Case 14: Claim with long lease period
('CLM-2024-013', 9500.00, 9500.00, 4000.00, 'POL-12358', 'PROP-014',
 '2024-01-10', '2024-01-15', '2020-01-01', '2024-01-31', 'completed', 1,
 '2024-01-05 08:00:00+00', 'system'),

-- Case 15: Small claim amount
('CLM-2024-014', 500.00, 500.00, 200.00, 'POL-12359', 'PROP-015',
 '2024-03-15', '2024-03-20', '2023-12-01', '2024-03-31', 'pending', 0,
 '2024-03-12 10:30:00+00', 'system'),

-- Case 16: Claim with missing move-out date
('CLM-2024-015', 3800.00, 3800.00, 1600.00, 'POL-12360', 'PROP-016',
 '2024-02-05', NULL, '2023-08-01', '2024-02-29', 'processing', 1,
 '2024-02-01 13:45:00+00', 'system'),

-- Case 17: Claim with zero benefit
('CLM-2024-016', 2000.00, 0.00, 1000.00, 'POL-12361', 'PROP-017',
 '2024-01-05', '2024-01-10', '2023-02-01', '2024-01-31', 'completed', 0,
 '2024-01-01 09:00:00+00', 'system'),

-- Case 18: Claim with appeal decision
('CLM-2024-017', 6500.00, 6500.00, 2700.00, 'POL-12362', 'PROP-018',
 '2024-02-12', '2024-02-18', '2023-09-01', '2024-02-29', 'completed', 2,
 '2024-02-08 14:15:00+00', 'system'),

-- Case 19: Claim with manual override
('CLM-2024-018', 4800.00, 4800.00, 2000.00, 'POL-12363', 'PROP-019',
 '2024-03-08', '2024-03-12', '2023-10-01', '2024-03-31', 'completed', 1,
 '2024-03-03 11:00:00+00', 'user_004'),

-- Case 20: Recent high-value claim
('CLM-2024-019', 12000.00, 10000.00, 5000.00, 'POL-12364', 'PROP-020',
 '2024-03-20', '2024-03-25', '2023-01-01', '2024-03-31', 'pending', 3,
 '2024-03-18 16:30:00+00', 'system');

-- Get claim IDs for foreign key references
DO $$
DECLARE
    v_claim_ids BIGINT[];
    v_claim_1 BIGINT;
    v_claim_2 BIGINT;
    v_claim_3 BIGINT;
    v_claim_10 BIGINT;
    v_claim_11 BIGINT;
    v_claim_17 BIGINT;
    v_claim_18 BIGINT;
    v_claim_19 BIGINT;
BEGIN
    SELECT ARRAY_AGG(id ORDER BY created_at) INTO v_claim_ids FROM claims;
    v_claim_1 := v_claim_ids[1];
    v_claim_2 := v_claim_ids[2];
    v_claim_3 := v_claim_ids[3];
    v_claim_10 := v_claim_ids[10];
    v_claim_11 := v_claim_ids[11];
    v_claim_17 := v_claim_ids[17];
    v_claim_18 := v_claim_ids[18];
    v_claim_19 := v_claim_ids[19];

    -- Insert claim documents
    INSERT INTO claim_documents (
        claim_id, file_path, original_filename, file_hash,
        file_size_bytes, mime_type, document_type,
        classification_confidence, extracted_text, ocr_confidence,
        page_count, processing_status, processed_at
    ) VALUES
    -- Documents for claim 1
    (v_claim_1, 's3://bucket/claims/CLM-2024-001/lease.pdf', 'lease_agreement.pdf',
     'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2',
     245678, 'application/pdf', 'lease', 95.50,
     'This is a standard residential lease agreement for property located at 123 Main St...',
     98.20, 5, 'completed', '2024-01-10 10:15:00+00'),
    
    (v_claim_1, 's3://bucket/claims/CLM-2024-001/invoice.pdf', 'damage_invoice.pdf',
     'b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3',
     189234, 'application/pdf', 'invoice', 92.30,
     'Invoice for property damage repairs: Flooring replacement $3000, Paint $1500, Cleaning $500...',
     96.80, 3, 'completed', '2024-01-10 10:20:00+00'),
    
    -- Documents for claim 2
    (v_claim_2, 's3://bucket/claims/CLM-2024-002/lease.pdf', 'lease.pdf',
     'c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4',
     312456, 'application/pdf', 'lease', 98.10,
     'Commercial lease agreement for office space...', 97.50, 8, 'completed',
     '2024-01-25 14:35:00+00'),
    
    -- Documents for claim 3 (pending processing)
    (v_claim_3, 's3://bucket/claims/CLM-2024-003/lease.pdf', 'lease.pdf',
     'd4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5',
     198765, 'application/pdf', 'lease', 88.50,
     NULL, NULL, 4, 'pending', NULL),
    
    -- Documents for claim 10 (multiple documents)
    (v_claim_10, 's3://bucket/claims/CLM-2024-009/lease.pdf', 'lease.pdf',
     'e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5d6',
     267890, 'application/pdf', 'lease', 94.20,
     'Residential lease agreement...', 95.10, 6, 'completed',
     '2024-02-18 14:25:00+00'),
    
    (v_claim_10, 's3://bucket/claims/CLM-2024-009/invoice1.pdf', 'repair_invoice_1.pdf',
     'f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5d6e7',
     145678, 'application/pdf', 'invoice', 91.80,
     'Plumbing repairs invoice...', 93.40, 2, 'completed',
     '2024-02-18 14:30:00+00'),
    
    (v_claim_10, 's3://bucket/claims/CLM-2024-009/invoice2.pdf', 'repair_invoice_2.pdf',
     'g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5d6e7f8',
     178234, 'application/pdf', 'invoice', 90.50,
     'Electrical work invoice...', 92.60, 2, 'completed',
     '2024-02-18 14:35:00+00'),
    
    (v_claim_10, 's3://bucket/claims/CLM-2024-009/addendum.pdf', 'lease_addendum.pdf',
     'h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5d6e7f8g9',
     98765, 'application/pdf', 'addendum', 87.30,
     'Lease addendum for pet policy...', 89.20, 1, 'completed',
     '2024-02-18 14:40:00+00'),
    
    -- Document for claim 11 (denied)
    (v_claim_11, 's3://bucket/claims/CLM-2024-010/lease.pdf', 'lease.pdf',
     'i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5d6e7f8g9h0',
     223456, 'application/pdf', 'lease', 96.70,
     'Lease agreement...', 97.20, 5, 'completed',
     '2024-01-22 11:35:00+00');

    -- Insert decisions
    INSERT INTO decisions (
        claim_id, decision_type, proposed_status, proposed_benefit_amount,
        eligible_total, invoice_total, cap_amount, approved_line_items,
        ineligible_line_items, flags, missing_data, reasoning,
        confidence_score, engine_version, processing_time_ms,
        decided_by, decided_at
    ) VALUES
    -- Decision for claim 1 (approved, full amount)
    (v_claim_1, 'automated', 'approve', 5000.00, 5000.00, 5000.00, 5000.00,
     '[{"item":"Flooring","amount":3000.00},{"item":"Paint","amount":1500.00},{"item":"Cleaning","amount":500.00}]',
     '[]',
     '{"critical":[],"warnings":[],"info":["All documents verified"]}',
     '{"fields":[],"needs_user_input":false}',
     '{"summary":"All line items approved within policy limits","details":"Standard wear and tear covered"}',
     94.50, 'v2.1.0', 1250, 'system', '2024-01-10 10:30:00+00'),
    
    -- Decision for claim 2 (approved, capped at max benefit)
    (v_claim_2, 'automated', 'approve', 10000.00, 15000.00, 15000.00, 10000.00,
     '[{"item":"Structural repairs","amount":8000.00},{"item":"HVAC","amount":2000.00}]',
     '[{"item":"Upgrades","amount":5000.00,"reason":"Not covered by policy"}]',
     '{"critical":[],"warnings":["Claim exceeds max benefit"],"info":[]}',
     '{"fields":[],"needs_user_input":false}',
     '{"summary":"Approved up to max benefit cap","details":"$5000 ineligible upgrades excluded"}',
     89.20, 'v2.1.0', 1890, 'system', '2024-01-25 14:45:00+00'),
    
    -- Decision for claim 11 (denied)
    (v_claim_11, 'automated', 'deny', 0.00, 0.00, 3000.00, 0.00,
     '[]',
     '[{"item":"All damages","amount":3000.00,"reason":"Pre-existing condition, not covered"}]',
     '{"critical":["Pre-existing damage"],"warnings":[],"info":[]}',
     '{"fields":[],"needs_user_input":false}',
     '{"summary":"Claim denied due to pre-existing condition","details":"Damage documented before lease start"}',
     92.80, 'v2.1.0', 980, 'system', '2024-01-22 11:40:00+00'),
    
    -- Decision for claim 17 (appeal - approved after initial denial)
    (v_claim_17, 'appeal', 'approve', 6500.00, 6500.00, 6500.00, 6500.00,
     '[{"item":"All repairs","amount":6500.00}]',
     '[]',
     '{"critical":[],"warnings":[],"info":["Appeal approved with additional documentation"]}',
     '{"fields":[],"needs_user_input":false}',
     '{"summary":"Appeal approved","details":"Additional evidence provided supports claim"}',
     88.50, 'v2.1.0', 2100, 'user_005', '2024-02-08 14:30:00+00'),
    
    -- Decision for claim 18 (manual override)
    (v_claim_18, 'manual_override', 'approve', 4800.00, 4800.00, 4800.00, 4800.00,
     '[{"item":"Repairs","amount":4800.00}]',
     '[]',
     '{"critical":[],"warnings":[],"info":["Manually reviewed and approved"]}',
     '{"fields":[],"needs_user_input":false}',
     '{"summary":"Manually approved by adjudicator","details":"Edge case requiring human judgment"}',
     100.00, 'v2.1.0', 450, 'user_004', '2024-03-03 11:15:00+00'),
    
    -- Decision for claim 19 (reprocessed)
    (v_claim_19, 'reprocessed', 'approve', 10000.00, 12000.00, 12000.00, 10000.00,
     '[{"item":"Major repairs","amount":10000.00}]',
     '[{"item":"Upgrades","amount":2000.00,"reason":"Exceeds cap"}]',
     '{"critical":[],"warnings":["Capped at max benefit"],"info":[]}',
     '{"fields":[],"needs_user_input":false}',
     '{"summary":"Reprocessed with updated rules","details":"Initial processing error corrected"}',
     91.30, 'v2.2.0', 1650, 'system', '2024-03-18 16:45:00+00');

    -- Insert decision validations
    INSERT INTO decision_validation (
        claim_id, decision_id, actual_status, actual_paid_amount,
        actual_decision_date, adjudication_notes, adjudicator_id,
        validation_source
    ) VALUES
    -- Validation for claim 1
    (v_claim_1, (SELECT id FROM decisions WHERE claim_id = v_claim_1 LIMIT 1),
     'approve', 5000.00, '2024-01-12',
     'Decision matched actual outcome. Payment processed successfully.',
     'adj_001', 'payment_system'),
    
    -- Validation for claim 2
    (v_claim_2, (SELECT id FROM decisions WHERE claim_id = v_claim_2 LIMIT 1),
     'approve', 10000.00, '2024-01-27',
     'Payment capped at max benefit as predicted.',
     'adj_002', 'payment_system'),
    
    -- Validation for claim 11
    (v_claim_11, (SELECT id FROM decisions WHERE claim_id = v_claim_11 LIMIT 1),
     'deny', 0.00, '2024-01-24',
     'Claim correctly denied. No payment issued.',
     'adj_003', 'manual_entry');

    -- Insert rules changelog entries
    INSERT INTO rules_changelog (
        version, released_at, changes_summary, changes_details,
        author, is_breaking_change, affected_decision_count
    ) VALUES
    ('v2.1.0', '2024-01-01 00:00:00+00',
     'Initial production release with core decision logic',
     '{"added":["Basic eligibility rules","Damage assessment logic"],"modified":[],"removed":[]}',
     'dev_team', FALSE, 0),
    
    ('v2.2.0', '2024-03-15 00:00:00+00',
     'Updated cap calculation and added appeal processing',
     '{"added":["Appeal workflow","Enhanced cap logic"],"modified":["Benefit calculation"],"removed":[]}',
     'dev_team', FALSE, 5);

    -- Insert processing queue entries
    INSERT INTO processing_queue (
        batch_id, claim_id, priority, status, retry_count,
        scheduled_at, worker_id
    ) VALUES
    (gen_random_uuid(), v_claim_3, 2, 'pending', 0,
     '2024-02-05 09:20:00+00', NULL),
    
    (gen_random_uuid(), v_claim_5, 5, 'processing', 0,
     '2024-02-28 16:50:00+00', 'worker_001'),
    
    (gen_random_uuid(), v_claim_6, 1, 'processing', 1,
     '2024-02-12 08:35:00+00', 'worker_002'),
    
    (gen_random_uuid(), v_claim_10, 1, 'processing', 0,
     '2024-02-18 14:45:00+00', 'worker_001'),
    
    (gen_random_uuid(), v_claim_12, 2, 'pending', 0,
     '2024-03-05 15:05:00+00', NULL),
    
    (gen_random_uuid(), v_claim_13, 10, 'pending', 0,
     '2024-02-25 12:05:00+00', NULL),
    
    (gen_random_uuid(), v_claim_15, 0, 'pending', 0,
     '2024-03-12 10:35:00+00', NULL),
    
    (gen_random_uuid(), v_claim_19, 3, 'pending', 0,
     '2024-03-18 16:35:00+00', NULL);

END $$;

-- Verify data counts
SELECT 'Claims' AS table_name, COUNT(*) AS record_count FROM claims
UNION ALL
SELECT 'Claim Documents', COUNT(*) FROM claim_documents
UNION ALL
SELECT 'Decisions', COUNT(*) FROM decisions
UNION ALL
SELECT 'Decision Validations', COUNT(*) FROM decision_validation
UNION ALL
SELECT 'Rules Changelog', COUNT(*) FROM rules_changelog
UNION ALL
SELECT 'Processing Queue', COUNT(*) FROM processing_queue
UNION ALL
SELECT 'Decision Audit Log', COUNT(*) FROM decision_audit_log;

