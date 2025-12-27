import logging
from decimal import Decimal
from typing import Dict, List

logger = logging.getLogger(__name__)


class EligibilityEngine:
    async def calculate(
        self,
        claim: dict,
        invoice_data: dict
    ) -> dict:
        """
        Calculate eligible amounts for each line item.
        
        Policy Rules:
        - Normal wear and tear: Ineligible
        - Pre-existing damage: Ineligible
        - Tenant-caused damage: Eligible (up to cap)
        - Cleaning fees: Eligible if beyond normal wear
        """
        approved_items = []
        ineligible_items = []
        
        for line_item in invoice_data.get("line_items", []):
            eligibility = await self._evaluate_line_item(
                line_item=line_item,
                claim=claim
            )
            
            if eligibility["is_eligible"]:
                approved_items.append({
                    "description": line_item.get("description", ""),
                    "amount": line_item.get("amount", 0.0),
                    "reason": eligibility["reason"]
                })
            else:
                ineligible_items.append({
                    "description": line_item.get("description", ""),
                    "amount": line_item.get("amount", 0.0),
                    "reason": eligibility["reason"]
                })
        
        eligible_total = sum(item["amount"] for item in approved_items)
        
        return {
            "approved_items": approved_items,
            "ineligible_items": ineligible_items,
            "eligible_total": Decimal(str(eligible_total))
        }
    
    async def _evaluate_line_item(
        self,
        line_item: dict,
        claim: dict
    ) -> dict:
        description = line_item.get("description", "").lower()
        
        if any(keyword in description for keyword in ["normal wear", "wear and tear", "preexisting"]):
            return {
                "is_eligible": False,
                "reason": "Normal wear and tear or pre-existing damage"
            }
        
        if any(keyword in description for keyword in ["cleaning", "repair", "damage", "replacement"]):
            return {
                "is_eligible": True,
                "reason": "Tenant-caused damage or cleaning beyond normal wear"
            }
        
        return {
            "is_eligible": True,
            "reason": "Eligible expense"
        }

