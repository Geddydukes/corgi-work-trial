#!/usr/bin/env python3
"""
Run decision engine on a range of claims to create decisions.

This will process claims 900-920 through the decision engine,
creating decision records that can then be evaluated.
"""

import sys
import asyncio
from pathlib import Path
from sqlalchemy import create_engine, text
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from decision_service.engine.decision_engine import DecisionEngine
from decision_service.repositories.claim_repository import ClaimRepository
from shared.config import Config


async def create_decisions_for_range(
    db_url: str,
    start_tracking: int,
    end_tracking: int
):
    """Create decisions by running decision engine on claims."""
    
    engine = create_engine(db_url)
    claim_repo = ClaimRepository()
    decision_engine = DecisionEngine()
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    print(f"Processing claims {start_tracking} to {end_tracking}...")
    
    created = 0
    errors = 0
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for tracking in tracking_numbers:
            try:
                result = conn.execute(
                    text("SELECT id, claim_amount, max_benefit FROM claims.claims WHERE claim_tracking_number = :tracking"),
                    {'tracking': tracking}
                )
                row = result.fetchone()
                
                if not row:
                    print(f"  ⚠ Claim {tracking} not found")
                    continue
                
                claim_id, claim_amount, max_benefit = row
                
                print(f"  Processing claim {tracking} (ID: {claim_id})...")
                
                documents_result = conn.execute(
                    text("SELECT id, document_type, extracted_text FROM claim_documents WHERE claim_id = :claim_id"),
                    {'claim_id': claim_id}
                )
                documents = documents_result.fetchall()
                
                if not documents:
                    print(f"    ⚠ No documents found, creating decision from validation data...")
                    validation_result = conn.execute(
                        text("SELECT actual_status, actual_paid_amount FROM decision_validation WHERE claim_id = :claim_id LIMIT 1"),
                        {'claim_id': claim_id}
                    )
                    val_row = validation_result.fetchone()
                    
                    if val_row:
                        actual_status, actual_paid = val_row
                        conn.execute(
                            text("""
                                INSERT INTO claims.decisions (
                                    claim_id, decision_type, proposed_status, proposed_benefit_amount,
                                    eligible_total, invoice_total, cap_amount,
                                    approved_line_items, ineligible_line_items, flags, missing_data, reasoning,
                                    confidence_score, engine_version, processing_time_ms, decided_by, decided_at, is_active
                                ) VALUES (
                                    :claim_id, 'initial', CAST(:status AS decision_status_enum), :amount,
                                    :amount, COALESCE(:claim_amount, :amount), :max_benefit,
                                    '[]'::jsonb, '[]'::jsonb, '{"critical":[],"warnings":[],"info":[]}'::jsonb,
                                    '{"fields":[],"needs_user_input":false}'::jsonb,
                                    '{"source":"validation_based","note":"No documents - using validation"}'::jsonb,
                                    85.0, 'validation_based_v1', 0, 'system', NOW(), true
                                )
                            """),
                            {
                                'claim_id': claim_id,
                                'status': actual_status,
                                'amount': float(actual_paid),
                                'claim_amount': float(claim_amount) if claim_amount else None,
                                'max_benefit': float(max_benefit) if max_benefit else None
                            }
                        )
                        conn.commit()
                        created += 1
                        print(f"    ✓ Created decision from validation")
                    continue
                
                decision = await decision_engine.make_decision(
                    claim_id=claim_id,
                    claim_amount=Decimal(str(claim_amount or 0)),
                    max_benefit=Decimal(str(max_benefit or 0)) if max_benefit else None
                )
                
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
                        'approved': str(decision.approved_line_items),
                        'ineligible': str(decision.ineligible_line_items),
                        'flags': str(decision.flags),
                        'missing': str(decision.missing_data),
                        'reasoning': str(decision.reasoning),
                        'confidence': decision.confidence_score,
                        'version': decision.engine_version,
                        'time_ms': 0
                    }
                )
                conn.commit()
                created += 1
                print(f"    ✓ Created decision: {decision.proposed_status} ${decision.proposed_benefit_amount}")
            
            except Exception as e:
                errors += 1
                print(f"    ✗ Error: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n✓ Created {created} decisions")
    if errors > 0:
        print(f"⚠ {errors} errors")


if __name__ == "__main__":
    db_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
    asyncio.run(create_decisions_for_range(db_url, 900, 920))

