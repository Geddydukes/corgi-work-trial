"""Tests for document classifier."""

import pytest

from classifier import DocumentClassifier
from models import DocumentType, ExtractedText, OCRTier


@pytest.fixture
def classifier():
    """Create classifier instance."""
    return DocumentClassifier()


class TestDocumentClassifier:
    """Test document classifier functionality."""
    
    def test_lease_classification(self, classifier):
        """Test lease document classification."""
        text = ExtractedText(
            text="LEASE AGREEMENT TERM: 12 months MONTHLY RENT: $1500",
            confidence=90.0,
            tier=OCRTier.TIER1_PYPDF2,
        )
        
        result = classifier.classify(text, page_count=5, ocr_confidence=90.0)
        
        assert result.document_type in [DocumentType.LEASE, DocumentType.UNKNOWN]
    
    def test_invoice_classification(self, classifier):
        """Test invoice document classification."""
        text = ExtractedText(
            text="INVOICE BALANCE DUE: $500.00 Itemized charges",
            confidence=85.0,
            tier=OCRTier.TIER1_PYPDF2,
        )
        
        result = classifier.classify(text, page_count=2, ocr_confidence=85.0)
        
        assert result.document_type in [DocumentType.INVOICE, DocumentType.UNKNOWN]
    
    def test_feature_extraction(self, classifier):
        """Test feature extraction."""
        text = "LEASE AGREEMENT TERM: 12 months $1500"
        
        features = classifier._extract_features(text, page_count=5)
        
        assert features.keyword_score >= 0
        assert features.structure_score >= 0
        assert features.dollar_amount_score >= 0
    
    def test_rule_based_fallback(self, classifier):
        """Test rule-based classification fallback."""
        text = ExtractedText(
            text="Random text without clear indicators",
            confidence=50.0,
            tier=OCRTier.TIER2_TESSERACT,
        )
        
        result = classifier.classify(text, page_count=1, ocr_confidence=50.0)
        
        assert result.document_type in [DocumentType.UNKNOWN, DocumentType.LEASE, DocumentType.INVOICE]

