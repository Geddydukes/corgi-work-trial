import logging
from decimal import Decimal
from typing import Dict, List
from pathlib import Path

from decision_service.engine.eligibility_classifier import (
    EligibilityClassifier,
    EligibilityStatus
)

logger = logging.getLogger(__name__)


class EligibilityEngine:
    def __init__(self):
        rules_path = Path(__file__).parent.parent.parent / "rules" / "rules_v1.0.yaml"
        self.classifier = EligibilityClassifier(str(rules_path))
    
    async def calculate(
        self,
        claim: dict,
        invoice_data: dict
    ) -> dict:
        """
        Calculate eligible amounts for each line item using EligibilityClassifier.
        
        Policy Rules:
        - Uses multi-layer classification with externalized YAML rules
        - Defaults to eligible with low confidence per approval-leaning policy
        - Filters out credit items (negative amounts)
        """
        approved_items = []
        ineligible_items = []
        credits = []
        
        for line_item in invoice_data.get("line_items", []):
            amount = Decimal(str(line_item.get("amount", 0)))
            
            if amount < 0 or line_item.get("is_credit", False):
                credits.append({
                    "description": line_item.get("description", ""),
                    "amount": amount
                })
                continue
            
            eligibility = await self._evaluate_line_item(
                line_item=line_item,
                claim=claim
            )
            
            if eligibility["is_eligible"]:
                approved_items.append({
                    "description": line_item.get("description", ""),
                    "amount": amount,
                    "reason": eligibility["reason"]
                })
            else:
                ineligible_items.append({
                    "description": line_item.get("description", ""),
                    "amount": amount,
                    "reason": eligibility["reason"]
                })
        
        eligible_total = sum(item["amount"] for item in approved_items)
        
        result = {
            "approved_items": approved_items,
            "ineligible_items": ineligible_items,
            "eligible_total": Decimal(str(eligible_total))
        }
        
        if credits:
            result["credits"] = credits
        
        return result
    
    async def _evaluate_line_item(
        self,
        line_item: dict,
        claim: dict
    ) -> dict:
        classified = self.classifier.classify({
            "description": line_item.get("description", ""),
            "amount": Decimal(str(line_item.get("amount", 0))),
            "line_number": line_item.get("line_number", 0)
        })
        
        status = classified.classification.status
        approval_bias = self.classifier.rules.get('approval_bias', True)
        
        is_eligible = (
            status == EligibilityStatus.ELIGIBLE or 
            (status == EligibilityStatus.AMBIGUOUS and approval_bias)
        )
        
        return {
            "is_eligible": is_eligible,
            "reason": classified.classification.reasoning
        }

