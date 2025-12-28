#!/usr/bin/env python3
"""
Run decision engine on claims 900-920 to create decisions.

This will process each claim through the actual decision engine,
creating decision records that can then be evaluated against validations.
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))


async def run_engine_on_claims(db_url: str, start_tracking: int, end_tracking: int):
    """Run decision engine on a range of claims."""
    
    from decision_service.engine.decision_engine import DecisionEngine
    from decision_service.repositories.claim_repository import ClaimRepository
    from decision_service.repositories.document_repository import DocumentRepository
    from shared.config import Config
    
    Config.DATABASE_URL = db_url
    
    engine = create_engine(db_url)
    decision_engine = DecisionEngine()
    claim_repo = ClaimRepository()
    doc_repo = DocumentRepository()
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    logger.info("=" * 80)
    logger.info(f"Running Decision Engine on Claims {start_tracking} to {end_tracking}")
    logger.info("=" * 80)
    
    created = 0
    skipped = 0
    errors = 0
    
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for tracking in tracking_numbers:
            try:
                logger.info(f"\nProcessing claim {tracking}...")
                
                claim_result = conn.execute(
                    text("""
                        SELECT id, claim_amount, max_benefit, security_deposit_amount
                        FROM claims.claims 
                        WHERE claim_tracking_number = :tracking
                    """),
                    {'tracking': tracking}
                )
                claim_row = claim_result.fetchone()
                
                if not claim_row:
                    logger.warning(f"  ⚠ Claim {tracking} not found")
                    skipped += 1
                    continue
                
                claim_id, claim_amount, max_benefit, security_deposit = claim_row
                logger.info(f"  → Claim ID: {claim_id}, Amount: ${claim_amount}, Max Benefit: ${max_benefit}")
                
                existing_decision = conn.execute(
                    text("SELECT id FROM claims.decisions WHERE claim_id = :claim_id AND is_active = true"),
                    {'claim_id': claim_id}
                ).fetchone()
                
                if existing_decision:
                    logger.info(f"  → Decision already exists, skipping")
                    skipped += 1
                    continue
                
                claim_result = conn.execute(
                    text("""
                        SELECT 
                            id, claim_tracking_number, claim_amount, max_benefit,
                            security_deposit_amount, claim_date, move_out_date,
                            lease_start_date, lease_end_date, status
                        FROM claims.claims
                        WHERE id = :claim_id
                    """),
                    {'claim_id': claim_id}
                )
                claim_row = claim_result.fetchone()
                
                if not claim_row:
                    logger.warning(f"  ⚠ Could not load claim data")
                    skipped += 1
                    continue
                
                claim_data = {
                    'id': claim_row[0],
                    'claim_tracking_number': claim_row[1],
                    'claim_amount': float(claim_row[2]) if claim_row[2] else 0.0,
                    'max_benefit': float(claim_row[3]) if claim_row[3] else None,
                    'security_deposit_amount': float(claim_row[4]) if claim_row[4] else None,
                    'claim_date': str(claim_row[5]) if claim_row[5] else None,
                    'move_out_date': str(claim_row[6]) if claim_row[6] else None,
                    'lease_start_date': str(claim_row[7]) if claim_row[7] else None,
                    'lease_end_date': str(claim_row[8]) if claim_row[8] else None,
                    'status': claim_row[9] if claim_row[9] else 'pending'
                }
                
                doc_result = conn.execute(
                    text("""
                        SELECT 
                            id, document_type, extracted_text, classification_confidence,
                            ocr_confidence, file_path, original_filename
                        FROM claim_documents
                        WHERE claim_id = :claim_id
                    """),
                    {'claim_id': claim_id}
                )
                doc_rows = doc_result.fetchall()
                
                documents = []
                for doc_row in doc_rows:
                    documents.append({
                        'id': doc_row[0],
                        'document_type': doc_row[1],
                        'extracted_text': doc_row[2],
                        'classification_confidence': float(doc_row[3]) if doc_row[3] else None,
                        'ocr_confidence': float(doc_row[4]) if doc_row[4] else None,
                        'file_path': doc_row[5],
                        'original_filename': doc_row[6]
                    })
                
                logger.info(f"  → Found {len(documents)} documents")
                
                if not documents:
                    logger.warning(f"  ⚠ No documents found - engine needs documents to make decisions")
                    logger.info(f"  → Creating deny decision (no documents)")
                    
                    conn.execute(
                        text("""
                            INSERT INTO claims.decisions (
                                claim_id, decision_type, proposed_status, proposed_benefit_amount,
                                eligible_total, invoice_total, cap_amount,
                                approved_line_items, ineligible_line_items, flags, missing_data, reasoning,
                                confidence_score, engine_version, processing_time_ms, decided_by, decided_at, is_active
                            ) VALUES (
                                :claim_id, 'initial', 'deny', 0.00,
                                0.00, :claim_amount, :max_benefit,
                                '[]'::jsonb, '[]'::jsonb,
                                '{"critical":["no_documents"],"warnings":[],"info":[]}'::jsonb,
                                '{"fields":["documents"],"needs_user_input":true}'::jsonb,
                                '{"reason":"No documents available for processing"}'::jsonb,
                                50.0, 'rules_v1.0.0', 0, 'system', NOW(), true
                            )
                        """),
                        {
                            'claim_id': claim_id,
                            'claim_amount': float(claim_amount) if claim_amount else 0.0,
                            'max_benefit': float(max_benefit) if max_benefit else None
                        }
                    )
                    created += 1
                    logger.info(f"  ✓ Created deny decision (no documents)")
                    continue
                
                logger.info(f"  → Running decision engine...")
                decision = await decision_engine.evaluate_claim(
                    claim_id=claim_id,
                    override_max_benefit=Decimal(str(max_benefit)) if max_benefit else None
                )
                
                logger.info(f"  → Engine decision: {decision.proposed_status} ${decision.proposed_benefit_amount}")
                logger.info(f"  → Confidence: {decision.confidence_score:.1f}%")
                
                import json
                conn.execute(
                    text("""
                        INSERT INTO claims.decisions (
                            claim_id, decision_type, proposed_status, proposed_benefit_amount,
                            eligible_total, invoice_total, cap_amount,
                            approved_line_items, ineligible_line_items, flags, missing_data, reasoning,
                            confidence_score, engine_version, processing_time_ms, decided_by, decided_at, is_active
                        ) VALUES (
                            :claim_id, 'initial', CAST(:status AS decision_status_enum), :benefit,
                            :eligible, :invoice, :cap,
                            CAST(:approved AS jsonb), CAST(:ineligible AS jsonb),
                            CAST(:flags AS jsonb), CAST(:missing AS jsonb),
                            CAST(:reasoning AS jsonb),
                            :confidence, :version, :time_ms, 'system', NOW(), true
                        )
                    """),
                    {
                        'claim_id': claim_id,
                        'status': decision.proposed_status,
                        'benefit': float(decision.proposed_benefit_amount),
                        'eligible': float(decision.eligible_total),
                        'invoice': float(decision.invoice_total),
                        'cap': float(decision.cap_amount) if decision.cap_amount else None,
                        'approved': json.dumps(decision.approved_line_items),
                        'ineligible': json.dumps(decision.ineligible_line_items),
                        'flags': json.dumps(decision.flags),
                        'missing': json.dumps(decision.missing_data),
                        'reasoning': json.dumps(decision.reasoning),
                        'confidence': decision.confidence_score,
                        'version': decision.engine_version,
                        'time_ms': 0
                    }
                )
                
                created += 1
                logger.info(f"  ✓ Decision saved")
            
            except Exception as e:
                errors += 1
                logger.error(f"  ✗ Error processing claim {tracking}: {e}")
                import traceback
                traceback.print_exc()
    
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Decisions created: {created}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Errors: {errors}")
    logger.info("=" * 80)


if __name__ == "__main__":
    db_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
    asyncio.run(run_engine_on_claims(db_url, 900, 920))

