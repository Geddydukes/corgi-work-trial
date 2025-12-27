import logging
from decimal import Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RuleEvaluator:
    def __init__(self):
        self.version = "v2.1.0"
    
    async def evaluate(
        self,
        claim: dict,
        eligibility_result: dict,
        override_max_benefit: Optional[Decimal] = None
    ) -> dict:
        flags = {"critical": [], "warnings": [], "info": []}
        missing_data = {"fields": [], "needs_user_input": False}
        
        max_benefit = override_max_benefit or Decimal(str(claim.get("max_benefit", 999999.99)))
        
        benefit_amount = min(
            eligibility_result["eligible_total"],
            max_benefit
        )
        
        if not claim.get("lease_start_date"):
            missing_data["fields"].append("lease_start_date")
            flags["warnings"].append("Missing lease start date")
        
        if benefit_amount > 0:
            status = "approve"
        else:
            status = "deny"
        
        confidence = 85.0
        if missing_data["fields"]:
            confidence -= 10.0
        if eligibility_result["eligible_total"] == 0:
            confidence -= 20.0
        
        reasoning = {
            "eligible_total": str(eligibility_result["eligible_total"]),
            "cap_applied": str(max_benefit),
            "final_amount": str(benefit_amount),
            "rule_version": self.version
        }
        
        return {
            "status": status,
            "benefit_amount": benefit_amount,
            "flags": flags,
            "missing_data": missing_data,
            "reasoning": reasoning,
            "confidence": max(0.0, min(100.0, confidence))
        }

