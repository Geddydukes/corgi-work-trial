"""Test suite for Phase 3 implementation fixes - Error Handling."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from decision_service.engine.decision_engine import DecisionEngine
from decision_service.engine.rule_evaluator import RuleEvaluator
from shared.models import DocumentType


@pytest.fixture
def decision_engine():
    """Create DecisionEngine instance."""
    return DecisionEngine()


@pytest.fixture
def rule_evaluator():
    """Create RuleEvaluator instance."""
    return RuleEvaluator()


class TestExceptionHandling:
    """Test exception handling in DecisionEngine."""
    
    @pytest.mark.asyncio
    async def test_invoice_parsing_failure_graceful_degradation(self, decision_engine):
        """Test that invoice parsing failure is handled gracefully."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        documents = await doc_repository.get_documents(claim_id)
        
        with patch.object(decision_engine.invoice_parser, 'parse_documents', side_effect=Exception("Parsing failed")):
            decision = await decision_engine.evaluate_claim(claim_id)
            
            assert decision.invoice_total == Decimal("0")
            assert decision.line_item_count == 0
            assert "invoice_parsing_failed" in decision.flags.get("critical", [])
    
    @pytest.mark.asyncio
    async def test_eligibility_calculation_failure_graceful_degradation(self, decision_engine):
        """Test that eligibility calculation failure is handled gracefully."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        documents = await doc_repository.get_documents(claim_id)
        
        with patch.object(decision_engine.eligibility_engine, 'calculate', side_effect=Exception("Calculation failed")):
            decision = await decision_engine.evaluate_claim(claim_id)
            
            assert decision.eligible_total == Decimal("0")
            assert len(decision.approved_line_items) == 0
            assert len(decision.ineligible_line_items) == 0


class TestInvoiceFlagPropagation:
    """Test invoice flag propagation from parser to decision."""
    
    @pytest.mark.asyncio
    async def test_invoice_mismatch_flags_propagate(self, decision_engine):
        """Test that invoice total mismatch flags propagate to final decision."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        documents = await doc_repository.get_documents(claim_id)
        
        mock_invoice_data = {
            "line_items": [
                {"description": "Cleaning", "amount": Decimal("150.00")}
            ],
            "total_amount": Decimal("150.00"),
            "document_count": 1,
            "flags": {
                "critical": ["invoice_total_mismatch: $50.00 difference (>5% threshold)"],
                "warnings": [],
                "info": []
            }
        }
        
        with patch.object(decision_engine.invoice_parser, 'parse_documents', return_value=mock_invoice_data):
            decision = await decision_engine.evaluate_claim(claim_id)
            
            critical_flags = decision.flags.get("critical", [])
            mismatch_flags = [f for f in critical_flags if "invoice_total_mismatch" in f]
            assert len(mismatch_flags) > 0


class TestOCRConfidenceFlags:
    """Test OCR confidence flagging."""
    
    @pytest.mark.asyncio
    async def test_low_ocr_confidence_flagged(self, decision_engine):
        """Test that low OCR confidence documents are flagged."""
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        from shared.models import DocumentType
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim_id = 12345
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            pytest.skip("Mock data not available")
        
        mock_documents_with_low_confidence = [
            {
                "id": 1,
                "claim_id": claim_id,
                "document_type": DocumentType.INVOICE.value,
                "extracted_text": "INVOICE\nItem 1: $500.00\nTotal: $500.00",
                "file_path": f"claims/{claim_id}/invoice.pdf",
                "ocr_confidence": 45.0
            },
            {
                "id": 2,
                "claim_id": claim_id,
                "document_type": DocumentType.ADDENDUM.value,
                "extracted_text": "ADDENDUM\nSecurity Deposit Waiver: Yes",
                "file_path": f"claims/{claim_id}/addendum.pdf",
                "ocr_confidence": 45.0
            }
        ]
        
        async def mock_get_docs(claim_id):
            return mock_documents_with_low_confidence
        
        with patch('decision_service.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
            mock_doc_repo_instance = DocumentRepository()
            mock_doc_repo_instance.get_documents = mock_get_docs
            mock_doc_repo_class.return_value = mock_doc_repo_instance
            
            decision = await decision_engine.evaluate_claim(claim_id)
            
            warning_flags = decision.flags.get("warnings", [])
            ocr_flags = [f for f in warning_flags if "low_ocr_confidence" in f.lower() or "ocr" in f.lower()]
            assert len(ocr_flags) > 0, f"Expected OCR confidence flag, got flags: {warning_flags}"


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""
    
    @pytest.mark.asyncio
    async def test_full_flow_with_errors(self, decision_engine):
        """Test full decision flow handles errors at each stage."""
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
        
        assert decision is not None
        assert hasattr(decision, "flags")
        assert hasattr(decision, "proposed_status")
        assert decision.proposed_status in ["approve", "deny"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

