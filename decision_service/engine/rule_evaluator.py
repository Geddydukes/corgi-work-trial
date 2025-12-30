import logging
from decimal import Decimal

from shared.config import Config
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RuleEvaluator:
    def __init__(self):
        self.version = "v2.1.0"
    
    async def evaluate(
        self,
        claim: dict,
        eligibility_result: dict,
        override_max_benefit: Optional[Decimal] = None,
        has_addendum: bool = True,
        has_invoice: bool = True,
        invoice_total: Optional[Decimal] = None,
        document_confidence: Optional[float] = None,
        mode: str = "production"
    ) -> dict:
        flags = {"critical": [], "warnings": [], "info": []}
        missing_data = {"fields": [], "needs_user_input": False}
        
        eligibility_flags = eligibility_result.get("flags", {})
        if eligibility_flags:
            for severity in ["critical", "warnings", "info"]:
                if severity in eligibility_flags:
                    flags[severity].extend(eligibility_flags[severity])
        
        # Check if we have low confidence documents - be more lenient
        low_confidence_threshold = 50.0
        has_low_confidence = document_confidence is not None and document_confidence < low_confidence_threshold
        
        if not has_addendum:
            if has_low_confidence:
                # Low confidence - might be misclassified, flag for review instead of denying
                flags["warnings"].append("addendum_not_confidently_detected")
                flags["info"].append(f"document_confidence_{document_confidence:.1f}%_may_affect_classification")
                missing_data["fields"].append("addendum")
                missing_data["needs_user_input"] = True
                # Don't deny immediately - proceed with warning
                logger.warning(f"Low document confidence ({document_confidence:.1f}%) - addendum may be misclassified, proceeding with warning")
            else:
                # High confidence but no addendum - deny
                return {
                    "status": "deny",
                    "benefit_amount": Decimal("0"),
                    "cap_amount": None,
                    "flags": {"critical": ["missing_waiver_addendum"], "warnings": [], "info": []},
                    "missing_data": {"fields": ["addendum"], "needs_user_input": False},
                    "reasoning": {
                        "reason": "Missing required waiver addendum",
                        "rule_version": self.version
                    },
                    "confidence": 100.0
                }
        
        if not has_invoice:
            if has_low_confidence:
                # Low confidence - might be misclassified, flag for review instead of denying
                flags["warnings"].append("invoice_not_confidently_detected")
                flags["info"].append(f"document_confidence_{document_confidence:.1f}%_may_affect_classification")
                missing_data["fields"].append("invoice")
                missing_data["needs_user_input"] = True
                # Don't deny immediately - proceed with warning and use claim_amount as fallback
                if invoice_total is None or invoice_total == 0:
                    invoice_total = Decimal(str(claim.get("claim_amount", 0)))
                logger.warning(f"Low document confidence ({document_confidence:.1f}%) - invoice may be misclassified, using claim_amount as fallback")
            else:
                # High confidence but no invoice - deny
                return {
                    "status": "deny",
                    "benefit_amount": Decimal("0"),
                    "cap_amount": None,
                    "flags": {"critical": ["missing_invoice"], "warnings": [], "info": []},
                    "missing_data": {"fields": ["invoice"], "needs_user_input": False},
                    "reasoning": {
                        "reason": "Missing required invoice",
                        "rule_version": self.version
                    },
                    "confidence": 100.0
                }
        
        claim_amount_raw = claim.get("claim_amount")
        claim_amount = Decimal(str(claim_amount_raw)) if claim_amount_raw is not None else None
        
        max_benefit_raw = claim.get("max_benefit")
        if max_benefit_raw is None or max_benefit_raw == "":
            if mode == "backtest":
                return {
                    "status": "pending",
                    "benefit_amount": None,
                    "cap_amount": None,
                    "flags": {
                        "critical": ["missing_max_benefit"],
                        "warnings": [],
                        "info": []
                    },
                    "missing_data": {
                        "fields": ["max_benefit"],
                        "needs_user_input": True
                    },
                    "reasoning": {
                        "reason": "Cannot determine cap without max_benefit (backtest mode)",
                        "rule_version": self.version
                    },
                    "confidence": 100.0
                }
            else:
                return {
                    "status": "deny",
                    "benefit_amount": Decimal("0"),
                    "cap_amount": None,
                    "flags": {
                        "critical": ["missing_max_benefit"],
                        "warnings": [],
                        "info": []
                    },
                    "missing_data": {
                        "fields": ["max_benefit"],
                        "needs_user_input": True
                    },
                    "reasoning": {
                        "reason": "Cannot determine cap without max_benefit",
                        "rule_version": self.version
                    },
                    "confidence": 100.0
                }
        
        max_benefit = override_max_benefit or (Decimal(str(max_benefit_raw)) if max_benefit_raw is not None else None)
        
        # Handle case where claim_amount is explicitly 0 (not NULL)
        # If claim_amount is 0 and no max_benefit, approve $0
        # If claim_amount is NULL/None, treat as "no cap" and use max_benefit only
        if claim_amount == 0 and max_benefit is None:
            return {
                "status": "approve",
                "benefit_amount": Decimal("0"),
                "cap_amount": None,
                "flags": {"critical": [], "warnings": [], "info": ["claim_amount_zero"]},
                "missing_data": {"fields": [], "needs_user_input": False},
                "reasoning": {
                    "reason": "Claim amount is zero and no max_benefit, approving with zero benefit",
                    "rule_version": self.version
                },
                "confidence": 100.0
            }
        
        # Never approve more than min(claim_amount, max_benefit)
        # If claim_amount is None, only use max_benefit as cap
        if claim_amount is not None and claim_amount > 0 and max_benefit is not None and max_benefit > 0:
            effective_cap = min(claim_amount, max_benefit)
        elif claim_amount is not None and claim_amount > 0:
            effective_cap = claim_amount
        elif max_benefit is not None and max_benefit > 0:
            effective_cap = max_benefit
        else:
            effective_cap = None
        
        if invoice_total is None:
            invoice_total = Decimal("0")
        else:
            invoice_total = Decimal(str(invoice_total))
        
        # Sanity check: invoice_total should not be negative
        if invoice_total < Decimal("0"):
            logger.warning(f"Invoice total ${invoice_total} is negative, setting to 0")
            invoice_total = Decimal("0")
            flags["warnings"].append("invoice_total_negative_set_to_zero")
        
        # Sanity check: invoice_total should not exceed claim_amount by configurable multiplier
        # This catches data corruption (e.g., Claim 901 with billions)
        # Only apply if claim_amount is set (not NULL)
        invoice_claim_multiplier = Decimal(str(Config.INVOICE_TO_CLAIM_SANITY_MULTIPLIER))
        if claim_amount is not None and invoice_total > claim_amount * invoice_claim_multiplier and claim_amount > 0:
            logger.warning(f"Invoice total ${invoice_total} exceeds claim_amount ${claim_amount} by multiplier>{invoice_claim_multiplier}, applying sanity cap")
            invoice_total = claim_amount * invoice_claim_multiplier
            flags["warnings"].append(f"invoice_total_sanity_check_applied: capped to ${invoice_total}")
        
        # DETERMINISTIC CAP CALCULATION (monotonic in max_benefit)
        # Never approve more than min(claim_amount, max_benefit, invoice_total)
        if effective_cap is not None:
            cap_amount = min(effective_cap, invoice_total)
        else:
            cap_amount = invoice_total
        
        if eligibility_result["eligible_total"] == 0:
            return {
                "status": "deny",
                "benefit_amount": Decimal("0"),
                "cap_amount": cap_amount,
                "flags": {
                    "critical": ["no_eligible_charges"],
                    "warnings": [],
                    "info": []
                },
                "missing_data": {"fields": [], "needs_user_input": False},
                "reasoning": {
                    "reason": "No eligible charges found",
                    "rule_version": self.version
                },
                "confidence": 100.0
            }
        
        benefit_amount = min(eligibility_result["eligible_total"], cap_amount)
        
        if eligibility_result.get("credits"):
            flags["warnings"].append(f"credits_detected: {len(eligibility_result['credits'])} credit items found")
        
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
        
        # Adjust confidence based on document classification confidence
        if has_low_confidence:
            # Reduce decision confidence if documents have low classification confidence
            confidence_penalty = (low_confidence_threshold - document_confidence) / low_confidence_threshold * 30
            confidence = max(50.0, confidence - confidence_penalty)
            flags["warnings"].append(f"low_document_confidence_{document_confidence:.1f}%_reduces_decision_confidence_to_{confidence:.1f}%")
        
        reasoning = {
            "summary": f"{'Approved' if status == 'approve' else 'Denied'} ${benefit_amount} benefit from ${eligibility_result['eligible_total']} eligible charges, capped at ${cap_amount}.",
            "eligible_total": str(eligibility_result["eligible_total"]),
            "invoice_total": str(invoice_total),
            "max_benefit": str(max_benefit),
            "cap_amount": str(cap_amount),
            "final_amount": str(benefit_amount),
            "key_metrics": {
                "eligible_line_items": len(eligibility_result.get("approved_items", [])),
                "ineligible_line_items": len(eligibility_result.get("ineligible_items", [])),
                "invoice_total": str(invoice_total),
                "cap_amount": str(cap_amount)
            },
            "flag_explanations": {
                flag: self._get_flag_explanation(flag) 
                for flag in flags["critical"] + flags["warnings"]
            },
            "rule_version": self.version
        }
        
        return {
            "status": status,
            "benefit_amount": benefit_amount,
            "cap_amount": cap_amount,
            "flags": flags,
            "missing_data": missing_data,
            "reasoning": reasoning,
            "confidence": max(0.0, min(100.0, confidence))
        }
    
    def _get_flag_explanation(self, flag: str) -> str:
        explanations = {
            "missing_waiver_addendum": "Required waiver addendum document not found",
            "missing_invoice": "Required invoice document not found",
            "missing_max_benefit": "Maximum benefit amount not provided",
            "no_eligible_charges": "No charges were classified as eligible",
            "credits_detected": "Credit/refund items found in invoice",
            "claim_amount_zero": "Claim amount is zero",
            "Missing lease start date": "Lease start date is missing"
        }
        return explanations.get(flag, f"Flag: {flag}")
