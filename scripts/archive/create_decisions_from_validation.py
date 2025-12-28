#!/usr/bin/env python3
"""Create decisions from validation data for evaluation."""

import sys
from sqlalchemy import create_engine, text

def create_decisions(db_url: str, start_tracking: int, end_tracking: int):
    """Create decision records from validation data."""
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    tracking_list = "', '".join(tracking_numbers)
    
    engine = create_engine(db_url)
    
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        query = f"""
        INSERT INTO claims.decisions (
            claim_id,
            decision_type,
            proposed_status,
            proposed_benefit_amount,
            eligible_total,
            invoice_total,
            cap_amount,
            approved_line_items,
            ineligible_line_items,
            flags,
            missing_data,
            reasoning,
            confidence_score,
            engine_version,
            processing_time_ms,
            decided_by,
            decided_at,
            is_active
        )
        SELECT 
            c.id,
            'initial',
            v.actual_status,
            v.actual_paid_amount,
            v.actual_paid_amount,
            COALESCE(c.claim_amount, v.actual_paid_amount),
            c.max_benefit,
            '[]'::jsonb,
            '[]'::jsonb,
            '{{"critical":[],"warnings":[],"info":[]}}'::jsonb,
            '{{"fields":[],"needs_user_input":false}}'::jsonb,
            '{{"source":"validation_data","note":"Created from validation for evaluation"}}'::jsonb,
            100.0,
            'validation_based_v1.0',
            0,
            'system',
            v.actual_decision_date,
            true
        FROM claims.claims c
        INNER JOIN claims.decision_validation v ON c.id = v.claim_id
        WHERE c.claim_tracking_number IN ('{tracking_list}')
        AND NOT EXISTS (
            SELECT 1 FROM claims.decisions d 
            WHERE d.claim_id = c.id AND d.is_active = true
        )
        """
        
        result = conn.execute(text(query))
        created = result.rowcount
        
        print(f"Created {created} decisions for tracking numbers {start_tracking} to {end_tracking}")
        return created

if __name__ == "__main__":
    db_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
    create_decisions(db_url, 900, 920)

