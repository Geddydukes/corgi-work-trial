"""Test suite for Phase 1 and Phase 2 implementation fixes."""

import pytest
import asyncio
from decimal import Decimal
from pathlib import Path

from decision_service.engine.eligibility import EligibilityEngine
from decision_service.engine.rule_evaluator import RuleEvaluator
from decision_service.engine.decision_engine import DecisionEngine
from shared.models import DocumentType


@pytest.fixture
def eligibility_engine():
    """Create EligibilityEngine instance."""
    return EligibilityEngine()


@pytest.fixture
def rule_evaluator():
    """Create RuleEvaluator instance."""
    return RuleEvaluator()


@pytest.fixture
def decision_engine():
    """Create DecisionEngine instance."""
    return DecisionEngine()


class TestEligibilityClassifierIntegration:
    """Test that EligibilityEngine uses EligibilityClassifier."""
    
    @pytest.mark.asyncio
    async def test_eligibility_engine_uses_classifier(self, eligibility_engine):
        """Verify EligibilityEngine uses EligibilityClassifier for classification."""
        claim = {"id": 1, "claim_amount": 1000.0}
        invoice_data = {
            "line_items": [
                {"description": "Professional carpet cleaning", "amount": Decimal("150.00")},
                {"description": "Normal wear and tear on walls", "amount": Decimal("75.00")},
            ],
            "total_amount": Decimal("225.00")
        }
        
        result = await eligibility_engine.calculate(claim, invoice_data)
        
        assert "approved_items" in result
        assert "ineligible_items" in result
        assert "eligible_total" in result
        
        approved_descriptions = [item["description"] for item in result["approved_items"]]
        ineligible_descriptions = [item["description"] for item in result["ineligible_items"]]
        
        assert "Professional carpet cleaning" in approved_descriptions
        assert "Normal wear and tear on walls" in ineligible_descriptions
        assert result["eligible_total"] == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_credit_filtering(self, eligibility_engine):
        """Test that credit items are filtered out."""
        claim = {"id": 1, "claim_amount": 1000.0}
        invoice_data = {
            "line_items": [
                {"description": "Cleaning fee", "amount": Decimal("150.00")},
                {"description": "Refund", "amount": Decimal("-50.00"), "is_credit": True},
                {"description": "Damage repair", "amount": Decimal("-25.00")},
            ],
            "total_amount": Decimal("75.00")
        }
        
        result = await eligibility_engine.calculate(claim, invoice_data)
        
        assert "credits" in result
        assert len(result["credits"]) == 2
        assert result["eligible_total"] == Decimal("150.00")
        assert len(result["approved_items"]) == 1


class TestDocumentValidation:
    """Test required document validation."""
    
    @pytest.mark.asyncio
    async def test_missing_addendum_denies(self, rule_evaluator):
        """Test that missing addendum results in denial."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=False,
            has_invoice=True,
            invoice_total=Decimal("150.00")
        )
        
        assert result["status"] == "deny"
        assert result["benefit_amount"] == Decimal("0")
        assert "missing_waiver_addendum" in result["flags"]["critical"]
    
    @pytest.mark.asyncio
    async def test_missing_invoice_denies(self, rule_evaluator):
        """Test that missing invoice results in denial."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=False,
            invoice_total=Decimal("0")
        )
        
        assert result["status"] == "deny"
        assert result["benefit_amount"] == Decimal("0")
        assert "missing_invoice" in result["flags"]["critical"]


class TestCapCalculation:
    """Test cap calculation fixes."""
    
    @pytest.mark.asyncio
    async def test_cap_uses_min_of_max_benefit_and_invoice_total(self, rule_evaluator):
        """Test that cap = min(max_benefit, invoice_total)."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("3000.00")
        )
        
        assert result["cap_amount"] == Decimal("3000.00")
        assert result["benefit_amount"] == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_cap_when_invoice_total_less_than_max_benefit(self, rule_evaluator):
        """Test cap when invoice_total < max_benefit."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("2000.00")
        )
        
        assert result["cap_amount"] == Decimal("2000.00")
    
    @pytest.mark.asyncio
    async def test_cap_when_max_benefit_less_than_invoice_total(self, rule_evaluator):
        """Test cap when max_benefit < invoice_total."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 1000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("5000.00")
        )
        
        assert result["cap_amount"] == Decimal("1000.00")


class TestClaimAmountZeroRule:
    """Test claim_amount=0 rule."""
    
    @pytest.mark.asyncio
    async def test_claim_amount_zero_approves(self, rule_evaluator):
        """Test that claim_amount=0 results in approve with benefit=0."""
        claim = {"id": 1, "claim_amount": 0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("150.00")
        )
        
        assert result["status"] == "approve"
        assert result["benefit_amount"] == Decimal("0")
        assert "claim_amount_zero" in result["flags"]["info"]


class TestMissingMaxBenefit:
    """Test missing max_benefit handling."""
    
    @pytest.mark.asyncio
    async def test_missing_max_benefit_denies(self, rule_evaluator):
        """Test that missing max_benefit results in denial."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": None}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("150.00")
        )
        
        assert result["status"] == "deny"
        assert result["benefit_amount"] == Decimal("0")
        assert "missing_max_benefit" in result["flags"]["critical"]
        assert result["missing_data"]["needs_user_input"] is True
    
    @pytest.mark.asyncio
    async def test_empty_max_benefit_denies(self, rule_evaluator):
        """Test that empty string max_benefit results in denial."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": ""}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("150.00")
        )
        
        assert result["status"] == "deny"
        assert "missing_max_benefit" in result["flags"]["critical"]


class TestEligibleTotalZero:
    """Test eligible_total=0 rule."""
    
    @pytest.mark.asyncio
    async def test_eligible_total_zero_denies(self, rule_evaluator):
        """Test that eligible_total=0 results in denial."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [],
            "ineligible_items": [{"description": "Normal wear", "amount": Decimal("75.00")}],
            "eligible_total": Decimal("0")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("75.00")
        )
        
        assert result["status"] == "deny"
        assert result["benefit_amount"] == Decimal("0")
        assert "no_eligible_charges" in result["flags"]["critical"]


class TestCreditFlags:
    """Test credit flag propagation."""
    
    @pytest.mark.asyncio
    async def test_credits_flag_when_present(self, rule_evaluator):
        """Test that credits are flagged when present."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00"),
            "credits": [
                {"description": "Refund", "amount": Decimal("-50.00")}
            ]
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("100.00")
        )
        
        credit_flags = [f for f in result["flags"]["warnings"] if "credits_detected" in f]
        assert len(credit_flags) > 0


class TestDecisionFields:
    """Test new fields in Decision object."""
    
    @pytest.mark.asyncio
    async def test_decision_includes_new_fields(self, decision_engine):
        """Test that Decision includes all new fields."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        documents = await doc_repository.get_documents(claim_id)
        
        decision = await decision_engine.evaluate_claim(claim_id)
        
        assert hasattr(decision, "claim_amount")
        assert hasattr(decision, "max_benefit")
        assert hasattr(decision, "document_count")
        assert hasattr(decision, "line_item_count")
        assert decision.document_count == len(documents)


class TestReasoningEnhancement:
    """Test enhanced reasoning text."""
    
    @pytest.mark.asyncio
    async def test_reasoning_has_summary(self, rule_evaluator):
        """Test that reasoning includes human-readable summary."""
        claim = {"id": 1, "claim_amount": 1000.0, "max_benefit": 5000.0}
        eligibility_result = {
            "approved_items": [{"description": "Cleaning", "amount": Decimal("150.00")}],
            "ineligible_items": [],
            "eligible_total": Decimal("150.00")
        }
        
        result = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            has_addendum=True,
            has_invoice=True,
            invoice_total=Decimal("150.00")
        )
        
        assert "summary" in result["reasoning"]
        assert "key_metrics" in result["reasoning"]
        assert "flag_explanations" in result["reasoning"]
        assert "Approved" in result["reasoning"]["summary"] or "Denied" in result["reasoning"]["summary"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

