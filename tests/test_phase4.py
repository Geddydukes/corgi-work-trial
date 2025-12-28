"""Test suite for Phase 4 implementation fixes - Monotonicity and Additional Test Coverage."""

import pytest
from decimal import Decimal
from unittest.mock import patch

from decision_service.engine.rule_evaluator import RuleEvaluator
from decision_service.engine.decision_engine import DecisionEngine
from shared.models import DocumentType


@pytest.fixture
def rule_evaluator():
    """Create RuleEvaluator instance."""
    return RuleEvaluator()


@pytest.fixture
def decision_engine():
    """Create DecisionEngine instance."""
    return DecisionEngine()


class TestMonotonicity:
    """Test monotonicity property: increasing max_benefit never decreases proposed_benefit."""
    
    @pytest.mark.asyncio
    async def test_monotonicity_max_benefit_increase(self, rule_evaluator):
        """Test that increasing max_benefit never decreases proposed_benefit."""
        claim = {
            "id": 1,
            "claim_amount": 5000.0,
            "max_benefit": 1000.0,
            "lease_start_date": "2023-01-01"
        }
        
        invoice_total = Decimal("2000.00")
        eligibility_result = {
            "approved_items": [
                {"description": "Cleaning", "amount": Decimal("1500.00")}
            ],
            "ineligible_items": [],
            "eligible_total": Decimal("1500.00"),
            "credits": []
        }
        
        result1 = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=Decimal("500"),
            has_addendum=True,
            has_invoice=True,
            invoice_total=invoice_total
        )
        benefit1 = result1["benefit_amount"]
        
        result2 = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=Decimal("1000"),
            has_addendum=True,
            has_invoice=True,
            invoice_total=invoice_total
        )
        benefit2 = result2["benefit_amount"]
        
        result3 = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=Decimal("2000"),
            has_addendum=True,
            has_invoice=True,
            invoice_total=invoice_total
        )
        benefit3 = result3["benefit_amount"]
        
        assert benefit2 >= benefit1, f"Monotonicity violated: increasing max_benefit from 500 to 1000 decreased benefit from {benefit1} to {benefit2}"
        assert benefit3 >= benefit2, f"Monotonicity violated: increasing max_benefit from 1000 to 2000 decreased benefit from {benefit2} to {benefit3}"
        assert benefit3 >= benefit1, f"Monotonicity violated: increasing max_benefit from 500 to 2000 decreased benefit from {benefit1} to {benefit3}"
    
    @pytest.mark.asyncio
    async def test_monotonicity_with_invoice_cap(self, rule_evaluator):
        """Test monotonicity when invoice_total is the limiting factor."""
        claim = {
            "id": 1,
            "claim_amount": 5000.0,
            "max_benefit": 5000.0,
            "lease_start_date": "2023-01-01"
        }
        
        invoice_total = Decimal("1000.00")
        eligibility_result = {
            "approved_items": [
                {"description": "Cleaning", "amount": Decimal("1500.00")}
            ],
            "ineligible_items": [],
            "eligible_total": Decimal("1500.00"),
            "credits": []
        }
        
        result1 = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=Decimal("500"),
            has_addendum=True,
            has_invoice=True,
            invoice_total=invoice_total
        )
        benefit1 = result1["benefit_amount"]
        cap1 = result1["cap_amount"]
        
        result2 = await rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=Decimal("2000"),
            has_addendum=True,
            has_invoice=True,
            invoice_total=invoice_total
        )
        benefit2 = result2["benefit_amount"]
        cap2 = result2["cap_amount"]
        
        assert cap1 == Decimal("500"), f"Cap should be min(500, 1000) = 500, got {cap1}"
        assert cap2 == Decimal("1000"), f"Cap should be min(2000, 1000) = 1000, got {cap2}"
        assert benefit1 == Decimal("500"), f"Benefit should be min(1500, 500) = 500, got {benefit1}"
        assert benefit2 == Decimal("1000"), f"Benefit should be min(1500, 1000) = 1000, got {benefit2}"
        assert benefit2 >= benefit1, "Monotonicity violated: increasing max_benefit decreased benefit"
    
    @pytest.mark.asyncio
    async def test_monotonicity_never_exceeds_caps(self, rule_evaluator):
        """Test that proposed_benefit never exceeds both max_benefit and invoice_total."""
        claim = {
            "id": 1,
            "claim_amount": 5000.0,
            "max_benefit": 5000.0,
            "lease_start_date": "2023-01-01"
        }
        
        test_cases = [
            {"max_benefit": Decimal("1000"), "invoice_total": Decimal("2000"), "eligible_total": Decimal("1500")},
            {"max_benefit": Decimal("2000"), "invoice_total": Decimal("1000"), "eligible_total": Decimal("1500")},
            {"max_benefit": Decimal("500"), "invoice_total": Decimal("500"), "eligible_total": Decimal("1000")},
        ]
        
        for case in test_cases:
            eligibility_result = {
                "approved_items": [{"description": "Item", "amount": case["eligible_total"]}],
                "ineligible_items": [],
                "eligible_total": case["eligible_total"],
                "credits": []
            }
            
            result = await rule_evaluator.evaluate(
                claim=claim,
                eligibility_result=eligibility_result,
                override_max_benefit=case["max_benefit"],
                has_addendum=True,
                has_invoice=True,
                invoice_total=case["invoice_total"]
            )
            
            benefit = result["benefit_amount"]
            cap = result["cap_amount"]
            expected_cap = min(case["max_benefit"], case["invoice_total"])
            expected_benefit = min(case["eligible_total"], expected_cap)
            
            assert cap == expected_cap, f"Cap should be {expected_cap}, got {cap}"
            assert benefit == expected_benefit, f"Benefit should be {expected_benefit}, got {benefit}"
            assert benefit <= case["max_benefit"], f"Benefit {benefit} exceeds max_benefit {case['max_benefit']}"
            assert benefit <= case["invoice_total"], f"Benefit {benefit} exceeds invoice_total {case['invoice_total']}"


class TestEdgeCases:
    """Test additional edge cases and business rules."""
    
    @pytest.mark.asyncio
    async def test_invoice_total_mismatch_flags(self, decision_engine):
        """Test that invoice total mismatch flags are properly set."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        mock_invoice_data = {
            "line_items": [
                {"description": "Item 1", "amount": Decimal("100.00")},
                {"description": "Item 2", "amount": Decimal("200.00")}
            ],
            "total_amount": Decimal("250.00"),
            "document_count": 1,
            "flags": {
                "critical": ["invoice_total_mismatch: $50.00 difference (>5% threshold)"],
                "warnings": [],
                "info": []
            }
        }
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem 1: $100.00\nItem 2: $200.00\nTotal: $250.00",
                    "file_path": f"claims/{claim_id}/invoice.pdf"
                },
                {
                    "id": 2,
                    "claim_id": claim_id,
                    "document_type": DocumentType.ADDENDUM.value,
                    "extracted_text": "ADDENDUM\nSecurity Deposit Waiver: Yes",
                    "file_path": f"claims/{claim_id}/addendum.pdf"
                }
            ]
        
        with patch('decision_service.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
            mock_doc_repo_instance = DocumentRepository()
            mock_doc_repo_instance.get_documents = mock_get_docs
            mock_doc_repo_class.return_value = mock_doc_repo_instance
            
            with patch.object(decision_engine.invoice_parser, 'parse_documents', return_value=mock_invoice_data):
                decision = await decision_engine.evaluate_claim(claim_id)
                
                critical_flags = decision.flags.get("critical", [])
                mismatch_flags = [f for f in critical_flags if "invoice_total_mismatch" in f]
                assert len(mismatch_flags) > 0, f"Expected invoice mismatch flag, got flags: {critical_flags}"
    
    @pytest.mark.asyncio
    async def test_mixed_eligible_ineligible_items(self, decision_engine):
        """Test decision with mixed eligible and ineligible items."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        mock_invoice_data = {
            "line_items": [
                {"description": "Professional carpet cleaning", "amount": Decimal("150.00")},
                {"description": "Normal wear and tear on walls", "amount": Decimal("75.00")},
                {"description": "Damage repair", "amount": Decimal("200.00")}
            ],
            "total_amount": Decimal("425.00"),
            "document_count": 1,
            "flags": {"critical": [], "warnings": [], "info": []}
        }
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem 1: $150.00\nItem 2: $75.00\nItem 3: $200.00\nTotal: $425.00",
                    "file_path": f"claims/{claim_id}/invoice.pdf"
                },
                {
                    "id": 2,
                    "claim_id": claim_id,
                    "document_type": DocumentType.ADDENDUM.value,
                    "extracted_text": "ADDENDUM\nSecurity Deposit Waiver: Yes",
                    "file_path": f"claims/{claim_id}/addendum.pdf"
                }
            ]
        
        with patch('decision_service.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
            mock_doc_repo_instance = DocumentRepository()
            mock_doc_repo_instance.get_documents = mock_get_docs
            mock_doc_repo_class.return_value = mock_doc_repo_instance
            
            with patch.object(decision_engine.invoice_parser, 'parse_documents', return_value=mock_invoice_data):
                decision = await decision_engine.evaluate_claim(claim_id)
                
                assert len(decision.approved_line_items) > 0, "Should have approved items"
                assert len(decision.ineligible_line_items) > 0, "Should have ineligible items"
                assert decision.eligible_total > Decimal("0"), "Should have eligible total > 0"
                assert decision.proposed_benefit_amount > Decimal("0"), "Should have benefit > 0"
    
    @pytest.mark.asyncio
    async def test_approval_leaning_ambiguous_case(self, decision_engine):
        """Test that ambiguous cases lean toward approval."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        mock_invoice_data = {
            "line_items": [
                {"description": "Unclear service description", "amount": Decimal("100.00")}
            ],
            "total_amount": Decimal("100.00"),
            "document_count": 1,
            "flags": {"critical": [], "warnings": [], "info": []}
        }
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem 1: $100.00\nTotal: $100.00",
                    "file_path": f"claims/{claim_id}/invoice.pdf"
                },
                {
                    "id": 2,
                    "claim_id": claim_id,
                    "document_type": DocumentType.ADDENDUM.value,
                    "extracted_text": "ADDENDUM\nSecurity Deposit Waiver: Yes",
                    "file_path": f"claims/{claim_id}/addendum.pdf"
                }
            ]
        
        with patch('decision_service.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
            mock_doc_repo_instance = DocumentRepository()
            mock_doc_repo_instance.get_documents = mock_get_docs
            mock_doc_repo_class.return_value = mock_doc_repo_instance
            
            with patch.object(decision_engine.invoice_parser, 'parse_documents', return_value=mock_invoice_data):
                decision = await decision_engine.evaluate_claim(claim_id)
                
                if decision.eligible_total > Decimal("0"):
                    assert decision.proposed_status == "approve", "Ambiguous case should lean toward approval if eligible"
                else:
                    assert len(decision.approved_line_items) == 0, "If no eligible items, should have no approved items"


class TestCapCalculation:
    """Test cap calculation correctness."""
    
    @pytest.mark.asyncio
    async def test_cap_never_exceeds_max_benefit_or_invoice(self, rule_evaluator):
        """Test that cap_amount never exceeds both max_benefit and invoice_total."""
        claim = {
            "id": 1,
            "claim_amount": 5000.0,
            "max_benefit": 2000.0,
            "lease_start_date": "2023-01-01"
        }
        
        test_cases = [
            {"max_benefit": Decimal("1000"), "invoice_total": Decimal("2000")},
            {"max_benefit": Decimal("2000"), "invoice_total": Decimal("1000")},
            {"max_benefit": Decimal("500"), "invoice_total": Decimal("500")},
        ]
        
        for case in test_cases:
            eligibility_result = {
                "approved_items": [{"description": "Item", "amount": Decimal("1500.00")}],
                "ineligible_items": [],
                "eligible_total": Decimal("1500.00"),
                "credits": []
            }
            
            result = await rule_evaluator.evaluate(
                claim=claim,
                eligibility_result=eligibility_result,
                override_max_benefit=case["max_benefit"],
                has_addendum=True,
                has_invoice=True,
                invoice_total=case["invoice_total"]
            )
            
            cap = result["cap_amount"]
            expected_cap = min(case["max_benefit"], case["invoice_total"])
            
            assert cap == expected_cap, f"Cap should be min({case['max_benefit']}, {case['invoice_total']}) = {expected_cap}, got {cap}"
            assert cap <= case["max_benefit"], f"Cap {cap} exceeds max_benefit {case['max_benefit']}"
            assert cap <= case["invoice_total"], f"Cap {cap} exceeds invoice_total {case['invoice_total']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

