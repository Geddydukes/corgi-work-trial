#!/usr/bin/env python3
"""
Create decisions by running the decision engine on claims 900-920.

This queries the database directly and runs the decision engine,
then saves the decisions for evaluation.
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine, text
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))


async def create_engine_decisions(db_url: str, start_tracking: int, end_tracking: int):
    """Create decisions by running decision engine."""
    
    from decision_service.engine.decision_engine import DecisionEngine
    from decision_service.engine.invoice_parser import InvoiceParser
    from decision_service.engine.eligibility import EligibilityEngine
    from decision_service.engine.rule_evaluator import RuleEvaluator
    from shared.config import Config
    from shared.models import DocumentType
    
    Config.DATABASE_URL = db_url
    
    engine = create_engine(db_url)
    decision_engine = DecisionEngine()
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    logger.info("=" * 80)
    logger.info(f"Running Decision Engine on Claims {start_tracking} to {end_tracking}")
    logger.info("=" * 80)
    
    created = 0
    skipped = 0
    errors = 0
    
    for tracking in tracking_numbers:
        try:
            logger.info(f"\nProcessing claim {tracking}...")
            
            with engine.begin() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                claim_result = conn.execute(
                    text("""
                        SELECT id, claim_amount, max_benefit, security_deposit_amount,
                               claim_date, move_out_date, lease_start_date, lease_end_date
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
                
                claim_id, claim_amount, max_benefit, security_deposit, claim_date, move_out_date, lease_start, lease_end = claim_row
                logger.info(f"  → Claim ID: {claim_id}, Amount: ${claim_amount}, Max: ${max_benefit}")
                
                existing = conn.execute(
                    text("SELECT id FROM claims.decisions WHERE claim_id = :claim_id AND is_active = true"),
                    {'claim_id': claim_id}
                ).fetchone()
                
                if existing:
                    logger.info(f"  → Decision already exists")
                    skipped += 1
                    continue
                
                doc_result = conn.execute(
                    text("""
                        SELECT id, document_type, extracted_text, classification_confidence,
                               ocr_confidence, file_path, original_filename
                        FROM claims.claim_documents
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
                        'extracted_text': doc_row[2] or '',
                        'classification_confidence': float(doc_row[3]) if doc_row[3] else None,
                        'ocr_confidence': float(doc_row[4]) if doc_row[4] else None,
                        'file_path': doc_row[5],
                        'original_filename': doc_row[6]
                    })
                
                logger.info(f"  → Found {len(documents)} documents")
                
                claim_data = {
                    'id': claim_id,
                    'claim_tracking_number': tracking,
                    'claim_amount': float(claim_amount) if claim_amount else 0.0,
                    'max_benefit': float(max_benefit) if max_benefit else None,
                    'security_deposit_amount': float(security_deposit) if security_deposit else None,
                    'claim_date': str(claim_date) if claim_date else None,
                    'move_out_date': str(move_out_date) if move_out_date else None,
                    'lease_start_date': str(lease_start) if lease_start else None,
                    'lease_end_date': str(lease_end) if lease_end else None,
                    'status': 'completed'
                }
                
                if not documents:
                    logger.warning(f"  ⚠ No documents - engine would deny")
                    logger.info(f"  → Creating deny decision (no documents available)")
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
                    logger.info(f"  ✓ Created deny decision")
                    continue
                
                logger.info(f"  → Running decision engine...")
                
                has_addendum = any(doc.get('document_type') == DocumentType.ADDENDUM.value for doc in documents)
                has_invoice = any(doc.get('document_type') == DocumentType.INVOICE.value for doc in documents)
                
                invoice_data = await decision_engine.invoice_parser.parse_documents(documents)
                
                eligibility_result = await decision_engine.eligibility_engine.calculate(
                    claim=claim_data,
                    invoice_data=invoice_data
                )
                
                rule_result = await decision_engine.rule_evaluator.evaluate(
                    claim=claim_data,
                    eligibility_result=eligibility_result,
                    override_max_benefit=Decimal(str(max_benefit)) if max_benefit else None,
                    has_addendum=has_addendum,
                    has_invoice=has_invoice,
                    invoice_total=invoice_data.get("total_amount", Decimal("0"))
                )
                
                logger.info(f"  → Engine decision: {rule_result['status']} ${rule_result['benefit_amount']}")
                logger.info(f"  → Confidence: {rule_result['confidence']:.1f}%")
                
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
                        'status': rule_result['status'],
                        'benefit': float(rule_result['benefit_amount']),
                        'eligible': float(eligibility_result.get('eligible_total', 0)),
                        'invoice': float(invoice_data.get('total_amount', 0)),
                        'cap': float(rule_result.get('cap_amount')) if rule_result.get('cap_amount') else None,
                        'approved': json.dumps(eligibility_result.get('approved_items', [])),
                        'ineligible': json.dumps(eligibility_result.get('ineligible_items', [])),
                        'flags': json.dumps(rule_result.get('flags', {})),
                        'missing': json.dumps(rule_result.get('missing_data', {})),
                        'reasoning': json.dumps(rule_result.get('reasoning', {})),
                        'confidence': rule_result.get('confidence', 85.0),
                        'version': decision_engine.rule_evaluator.version,
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
    asyncio.run(create_engine_decisions(db_url, 900, 920))

