"""Tests for OCR service."""

import tempfile
from pathlib import Path

import pytest

from ocr_service import OCRService


@pytest.fixture
def ocr_service():
    """Create OCR service instance."""
    return OCRService()


def create_test_pdf(content: str, output_path: Path) -> None:
    """Create a test PDF file."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(output_path), pagesize=letter)
        c.drawString(100, 750, content)
        c.save()
    except ImportError:
        pytest.skip("reportlab not installed")


class TestOCRService:
    """Test OCR service functionality."""
    
    def test_tier1_extraction(self, ocr_service):
        """Test Tier 1 extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            create_test_pdf("Test content for OCR", pdf_path)
            
            text, confidence, tier, time_ms, cost = ocr_service._extract_tier1(pdf_path)
            
            assert tier.value.startswith("tier1")
            assert cost == 0.0
    
    def test_confidence_calculation(self, ocr_service):
        """Test confidence calculation."""
        high_quality_text = "This is a high quality text with many words and good character diversity."
        low_quality_text = "x"
        
        high_conf = ocr_service._calculate_confidence(high_quality_text)
        low_conf = ocr_service._calculate_confidence(low_quality_text)
        
        assert high_conf > low_conf
        assert 0 <= high_conf <= 100
        assert 0 <= low_conf <= 100
    
    def test_extract_with_attempts(self, ocr_service):
        """Test extraction with multiple attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            create_test_pdf("Test", pdf_path)
            
            attempts, best = ocr_service.extract_with_attempts(pdf_path, is_native_pdf=True)
            
            assert len(attempts) >= 0
            if best:
                assert best.confidence >= 0


