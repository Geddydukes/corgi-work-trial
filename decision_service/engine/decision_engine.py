import logging
from typing import Optional
from decimal import Decimal

from decision_service.engine.eligibility import EligibilityEngine
from decision_service.engine.invoice_parser import InvoiceParser
from decision_service.engine.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)


class Decision:
    def __init__(
        self,
        claim_id: int,
        proposed_status: str,
        proposed_benefit_amount: Decimal,
        eligible_total: Decimal,
        invoice_total: Decimal,
        cap_amount: Optional[Decimal],
        approved_line_items: list,
        ineligible_line_items: list,
        flags: dict,
        missing_data: dict,
        reasoning: dict,
        confidence_score: float,
        engine_version: str,
    ):
        self.claim_id = claim_id
        self.proposed_status = proposed_status
        self.proposed_benefit_amount = proposed_benefit_amount
        self.eligible_total = eligible_total
        self.invoice_total = invoice_total
        self.cap_amount = cap_amount
        self.approved_line_items = approved_line_items
        self.ineligible_line_items = ineligible_line_items
        self.flags = flags
        self.missing_data = missing_data
        self.reasoning = reasoning
        self.confidence_score = confidence_score
        self.engine_version = engine_version


class DecisionEngine:
    def __init__(self):
        self.eligibility_engine = EligibilityEngine()
        self.invoice_parser = InvoiceParser()
        self.rule_evaluator = RuleEvaluator()
    
    async def evaluate_claim(
        self,
        claim_id: int,
        override_max_benefit: Optional[Decimal] = None
    ) -> Decision:
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        
        documents = await doc_repository.get_documents(claim_id)
        
        invoice_data = await self.invoice_parser.parse_documents(documents)
        
        eligibility_result = await self.eligibility_engine.calculate(
            claim=claim,
            invoice_data=invoice_data
        )
        
        rule_result = await self.rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=override_max_benefit
        )
        
        decision = Decision(
            claim_id=claim_id,
            proposed_status=rule_result["status"],
            proposed_benefit_amount=rule_result["benefit_amount"],
            eligible_total=eligibility_result["eligible_total"],
            invoice_total=invoice_data["total_amount"],
            cap_amount=override_max_benefit or Decimal(str(claim.get("max_benefit", 0))),
            approved_line_items=eligibility_result["approved_items"],
            ineligible_line_items=eligibility_result["ineligible_items"],
            flags=rule_result["flags"],
            missing_data=rule_result["missing_data"],
            reasoning=rule_result["reasoning"],
            confidence_score=rule_result["confidence"],
            engine_version=self.rule_evaluator.version
        )
        
        return decision

