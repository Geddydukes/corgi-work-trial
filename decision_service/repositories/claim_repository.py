import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class ClaimRepository:
    async def get_claim(self, claim_id: int) -> Optional[dict]:
        from shared.config import Config
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock data")
            return {
                "id": claim_id,
                "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                "claim_amount": 5000.0,
                "max_benefit": 5000.0,
                "lease_start_date": "2023-01-01",
            }
        
        return None
    
    async def get_claim_by_tracking_number(self, tracking_number: str) -> Optional[dict]:
        from shared.config import Config
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock data")
            return {
                "id": 12345,
                "claim_tracking_number": tracking_number,
                "claim_amount": 5000.0,
                "max_benefit": 5000.0,
                "lease_start_date": "2023-01-01",
            }
        
        return None
    
    async def create_decision(self, decision, user_id: str) -> dict:
        from shared.config import Config
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock decision")
            return {
                "id": 1,
                "claim_id": decision.claim_id,
                "tracking_number": f"CLM-2024-{decision.claim_id:06d}",
                "decision_type": "automated",
                "proposed_status": decision.proposed_status,
                "proposed_benefit_amount": float(decision.proposed_benefit_amount),
                "eligible_total": float(decision.eligible_total),
                "invoice_total": float(decision.invoice_total),
                "cap_amount": float(decision.cap_amount) if decision.cap_amount else None,
                "approved_line_items": decision.approved_line_items,
                "ineligible_line_items": decision.ineligible_line_items,
                "flags": decision.flags,
                "missing_data": decision.missing_data,
                "reasoning": decision.reasoning,
                "confidence_score": decision.confidence_score,
                "engine_version": decision.engine_version,
                "decided_at": datetime.utcnow(),
            }
        
        return None

