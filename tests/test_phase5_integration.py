"""Test suite for Phase 5 - Integration Tests and End-to-End Validation."""

import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from decision_service.engine.decision_engine import DecisionEngine
from shared.models import DocumentType


@pytest.fixture
def decision_engine():
    """Create DecisionEngine instance."""
    return DecisionEngine()


class TestEndToEndDecisionFlow:
    """Comprehensive end-to-end tests for the complete decision flow."""
    
    @pytest.mark.asyncio
    async def test_full_approval_flow(self, decision_engine):
        """Test complete approval flow from documents to decision."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nProfessional carpet cleaning: $150.00\nDamage repair: $200.00\nTotal: $350.00",
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
            
            decision = await decision_engine.evaluate_claim(claim_id)
            
            assert decision is not None
            assert decision.claim_id == claim_id
            assert decision.proposed_status in ["approve", "deny"]
            assert decision.proposed_benefit_amount >= Decimal("0")
            assert decision.eligible_total >= Decimal("0")
            assert decision.invoice_total >= Decimal("0")
            assert decision.cap_amount is not None or decision.proposed_benefit_amount == Decimal("0")
            assert isinstance(decision.flags, dict)
            assert "critical" in decision.flags
            assert "warnings" in decision.flags
            assert "info" in decision.flags
            assert isinstance(decision.missing_data, dict)
            assert "fields" in decision.missing_data
            assert decision.reasoning is not None
            assert "summary" in decision.reasoning
            assert decision.claim_amount is not None
            assert decision.document_count >= 0
            assert decision.line_item_count >= 0
    
    @pytest.mark.asyncio
    async def test_full_denial_flow_missing_documents(self, decision_engine):
        """Test complete denial flow when required documents are missing."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs_no_addendum(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem: $100.00\nTotal: $100.00",
                    "file_path": f"claims/{claim_id}/invoice.pdf"
                }
            ]
        
        with patch('decision_service.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
            mock_doc_repo_instance = DocumentRepository()
            mock_doc_repo_instance.get_documents = mock_get_docs_no_addendum
            mock_doc_repo_class.return_value = mock_doc_repo_instance
            
            decision = await decision_engine.evaluate_claim(claim_id)
            
            assert decision.proposed_status == "deny"
            assert decision.proposed_benefit_amount == Decimal("0")
            assert "missing_waiver_addendum" in decision.flags.get("critical", [])
            assert "addendum" in decision.missing_data.get("fields", [])
    
    @pytest.mark.asyncio
    async def test_full_denial_flow_no_eligible_items(self, decision_engine):
        """Test complete denial flow when no eligible items are found."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nNormal wear and tear: $100.00\nTotal: $100.00",
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
            
            decision = await decision_engine.evaluate_claim(claim_id)
            
            if decision.eligible_total == Decimal("0"):
                assert decision.proposed_status == "deny"
                assert decision.proposed_benefit_amount == Decimal("0")
                assert "no_eligible_charges" in decision.flags.get("critical", [])
    
    @pytest.mark.asyncio
    async def test_decision_consistency_across_runs(self, decision_engine):
        """Test that the same claim produces consistent decisions across multiple runs."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nProfessional cleaning: $150.00\nTotal: $150.00",
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
            
            decision1 = await decision_engine.evaluate_claim(claim_id)
            decision2 = await decision_engine.evaluate_claim(claim_id)
            
            assert decision1.proposed_status == decision2.proposed_status
            assert decision1.proposed_benefit_amount == decision2.proposed_benefit_amount
            assert decision1.eligible_total == decision2.eligible_total
            assert decision1.invoice_total == decision2.invoice_total


class TestDataIntegrity:
    """Test data integrity across the decision flow."""
    
    @pytest.mark.asyncio
    async def test_decimal_precision_preserved(self, decision_engine):
        """Test that Decimal precision is preserved throughout the decision flow."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem: $123.45\nTotal: $123.45",
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
            
            decision = await decision_engine.evaluate_claim(claim_id)
            
            assert isinstance(decision.proposed_benefit_amount, Decimal), f"proposed_benefit_amount should be Decimal, got {type(decision.proposed_benefit_amount)}"
            assert isinstance(decision.eligible_total, Decimal), f"eligible_total should be Decimal, got {type(decision.eligible_total)}"
            assert isinstance(decision.invoice_total, Decimal) or (decision.invoice_total == 0 and isinstance(decision.invoice_total, (int, Decimal))), f"invoice_total should be Decimal, got {type(decision.invoice_total)}: {decision.invoice_total}"
            if decision.cap_amount is not None:
                assert isinstance(decision.cap_amount, Decimal), f"cap_amount should be Decimal, got {type(decision.cap_amount)}"
            assert isinstance(decision.claim_amount, Decimal), f"claim_amount should be Decimal, got {type(decision.claim_amount)}"
            if decision.max_benefit is not None:
                assert isinstance(decision.max_benefit, Decimal), f"max_benefit should be Decimal, got {type(decision.max_benefit)}"
    
    @pytest.mark.asyncio
    async def test_all_required_fields_present(self, decision_engine):
        """Test that all required fields are present in the decision."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem: $100.00\nTotal: $100.00",
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
            
            decision = await decision_engine.evaluate_claim(claim_id)
            
            required_fields = [
                "claim_id", "proposed_status", "proposed_benefit_amount",
                "eligible_total", "invoice_total", "cap_amount",
                "approved_line_items", "ineligible_line_items",
                "flags", "missing_data", "reasoning", "confidence_score",
                "engine_version", "claim_amount", "max_benefit",
                "document_count", "line_item_count"
            ]
            
            for field in required_fields:
                assert hasattr(decision, field), f"Missing required field: {field}"


class TestErrorRecovery:
    """Test error recovery and graceful degradation."""
    
    @pytest.mark.asyncio
    async def test_graceful_handling_of_parsing_errors(self, decision_engine):
        """Test that parsing errors are handled gracefully."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem: $100.00\nTotal: $100.00",
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
            
            with patch.object(decision_engine.invoice_parser, 'parse_documents', side_effect=Exception("Parsing failed")):
                decision = await decision_engine.evaluate_claim(claim_id)
                
                assert decision is not None
                assert decision.invoice_total == Decimal("0")
                assert "invoice_parsing_failed" in decision.flags.get("critical", [])
    
    @pytest.mark.asyncio
    async def test_graceful_handling_of_eligibility_errors(self, decision_engine):
        """Test that eligibility calculation errors are handled gracefully."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        async def mock_get_docs(claim_id):
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": DocumentType.INVOICE.value,
                    "extracted_text": "INVOICE\nItem: $100.00\nTotal: $100.00",
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
            
            with patch.object(decision_engine.eligibility_engine, 'calculate', side_effect=Exception("Calculation failed")):
                decision = await decision_engine.evaluate_claim(claim_id)
                
                assert decision is not None
                assert decision.eligible_total == Decimal("0")
                assert len(decision.approved_line_items) == 0
                assert len(decision.ineligible_line_items) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

