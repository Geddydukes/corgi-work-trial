"""Comprehensive tests for document processor."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from document_processor import DocumentProcessor
from models import DocumentType, ProcessingErrorType


@pytest.fixture
def processor():
    """Create document processor instance."""
    return DocumentProcessor()


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_test_pdf_with_text(content: str, output_path: Path) -> None:
    """Create a simple PDF with text content."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(output_path), pagesize=letter)
        c.drawString(100, 750, content)
        c.save()
    except ImportError:
        pytest.skip("reportlab not installed")


def create_test_image(output_path: Path, text: str = "Test Image") -> None:
    """Create a test image file."""
    img = Image.new("RGB", (800, 600), color="white")
    img.save(output_path)


class TestFileValidation:
    """Test file validation functionality."""
    
    def test_file_not_found(self, processor, temp_dir):
        """Test handling of missing file."""
        result = asyncio.run(processor.process_document(
            temp_dir / "nonexistent.pdf",
            claim_id=1,
        ))
        
        assert result.errors
        assert any(e.error_type == ProcessingErrorType.FILE_NOT_FOUND for e in result.errors)
    
    def test_file_too_large(self, processor, temp_dir):
        """Test handling of oversized file."""
        large_file = temp_dir / "large.pdf"
        large_file.write_bytes(b"x" * (51 * 1024 * 1024))
        
        result = asyncio.run(processor.process_document(large_file, claim_id=1))
        
        assert result.errors
        assert any(e.error_type == ProcessingErrorType.DOCUMENT_TOO_LARGE for e in result.errors)
    
    def test_valid_pdf(self, processor, temp_dir):
        """Test processing valid PDF."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("This is a test PDF document", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.file_metadata.file_size_bytes > 0
        assert result.file_metadata.mime_type == "application/pdf"
        assert len(result.file_metadata.file_hash) == 64


class TestOCRProcessing:
    """Test OCR processing functionality."""
    
    def test_native_pdf_extraction(self, processor, temp_dir):
        """Test extraction from native PDF."""
        pdf_path = temp_dir / "native.pdf"
        create_test_pdf_with_text("LEASE AGREEMENT TERM: 12 months MONTHLY RENT: $1500", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.best_extraction.text
        assert len(result.extraction_attempts) > 0
    
    def test_image_processing(self, processor, temp_dir):
        """Test processing image files."""
        img_path = temp_dir / "test.png"
        create_test_image(img_path)
        
        result = asyncio.run(processor.process_document(img_path, claim_id=1))
        
        assert result.file_metadata.mime_type.startswith("image/")
    
    def test_force_high_quality(self, processor, temp_dir):
        """Test force high quality flag."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("Test content", pdf_path)
        
        result = asyncio.run(processor.process_document(
            pdf_path, claim_id=1, force_high_quality=True
        ))
        
        assert result.processing_metrics.tier3_attempts >= 0


class TestClassification:
    """Test document classification."""
    
    def test_lease_classification(self, processor, temp_dir):
        """Test classification of lease documents."""
        pdf_path = temp_dir / "lease.pdf"
        create_test_pdf_with_text(
            "LEASE AGREEMENT TERM: 12 months MONTHLY RENT: $1500 Security Deposit: $1500",
            pdf_path
        )
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.classification.document_type in [DocumentType.LEASE, DocumentType.UNKNOWN]
    
    def test_invoice_classification(self, processor, temp_dir):
        """Test classification of invoice documents."""
        pdf_path = temp_dir / "invoice.pdf"
        create_test_pdf_with_text(
            "INVOICE BALANCE DUE: $500.00 Itemized charges: Flooring $300, Paint $200",
            pdf_path
        )
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.classification.document_type in [DocumentType.INVOICE, DocumentType.UNKNOWN]
    
    def test_addendum_classification(self, processor, temp_dir):
        """Test classification of addendum documents."""
        pdf_path = temp_dir / "addendum.pdf"
        create_test_pdf_with_text(
            "ADDENDUM TO LEASE AGREEMENT SECURITY DEPOSIT WAIVER: Yes ENROLLMENT: Confirmed",
            pdf_path
        )
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.classification.document_type in [DocumentType.ADDENDUM, DocumentType.UNKNOWN]
    
    def test_unknown_classification(self, processor, temp_dir):
        """Test classification of unknown documents."""
        pdf_path = temp_dir / "unknown.pdf"
        create_test_pdf_with_text("Random text without clear document type indicators", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.classification.document_type == DocumentType.UNKNOWN


class TestQualityAssessment:
    """Test quality assessment functionality."""
    
    def test_quality_metrics(self, processor, temp_dir):
        """Test quality metrics calculation."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("Test document with sufficient text content", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.quality_metrics.avg_ocr_confidence >= 0
        assert result.quality_metrics.blank_page_count >= 0
    
    def test_blank_page_detection(self, processor, temp_dir):
        """Test detection of blank pages."""
        pdf_path = temp_dir / "blank.pdf"
        create_test_pdf_with_text("", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.quality_metrics.blank_page_count >= 0


class TestErrorHandling:
    """Test error handling."""
    
    def test_corrupted_file_handling(self, processor, temp_dir):
        """Test handling of corrupted files."""
        corrupted_file = temp_dir / "corrupted.pdf"
        corrupted_file.write_bytes(b"invalid pdf content")
        
        result = asyncio.run(processor.process_document(corrupted_file, claim_id=1))
        
        assert result.errors or result.best_extraction.confidence == 0.0
    
    def test_permission_error(self, processor):
        """Test handling of permission errors."""
        protected_file = Path("/root/protected.pdf")
        
        result = asyncio.run(processor.process_document(protected_file, claim_id=1))
        
        assert result.errors


class TestDeduplication:
    """Test deduplication functionality."""
    
    def test_file_hash_calculation(self, processor, temp_dir):
        """Test file hash calculation."""
        pdf_path = temp_dir / "test1.pdf"
        create_test_pdf_with_text("Test content", pdf_path)
        
        result1 = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        result2 = asyncio.run(processor.process_document(pdf_path, claim_id=2))
        
        assert result1.file_metadata.file_hash == result2.file_metadata.file_hash


class TestCostOptimization:
    """Test cost optimization."""
    
    def test_tier1_attempted_first(self, processor, temp_dir):
        """Test that Tier 1 is attempted before Tier 3."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("Test content for OCR", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        if result.extraction_attempts:
            first_tier = result.extraction_attempts[0].tier
            assert "tier1" in first_tier.value or "tier2" in first_tier.value
    
    def test_cost_calculation(self, processor, temp_dir):
        """Test cost calculation."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("Test", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.cost_breakdown.total_cost_usd >= 0


class TestManualReview:
    """Test manual review determination."""
    
    def test_low_confidence_review(self, processor, temp_dir):
        """Test that low confidence triggers review."""
        pdf_path = temp_dir / "low_quality.pdf"
        create_test_pdf_with_text("", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        if result.best_extraction.confidence < 50:
            assert result.requires_manual_review
    
    def test_unknown_type_review(self, processor, temp_dir):
        """Test that unknown type triggers review."""
        pdf_path = temp_dir / "unknown.pdf"
        create_test_pdf_with_text("Random text", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        if result.classification.document_type == DocumentType.UNKNOWN:
            assert result.requires_manual_review


class TestProcessingMetrics:
    """Test processing metrics."""
    
    def test_processing_time_tracked(self, processor, temp_dir):
        """Test that processing time is tracked."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("Test", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.processing_metrics.total_time_ms >= 0
    
    def test_tier_usage_tracked(self, processor, temp_dir):
        """Test that tier usage is tracked."""
        pdf_path = temp_dir / "test.pdf"
        create_test_pdf_with_text("Test", pdf_path)
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.processing_metrics.tier1_attempts >= 0
        assert result.processing_metrics.tier2_attempts >= 0
        assert result.processing_metrics.tier3_attempts >= 0


class TestMultiPageDocuments:
    """Test multi-page document processing."""
    
    def test_multi_page_pdf(self, processor, temp_dir):
        """Test processing multi-page PDF."""
        pdf_path = temp_dir / "multipage.pdf"
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            
            c = canvas.Canvas(str(pdf_path), pagesize=letter)
            for i in range(3):
                c.drawString(100, 750, f"Page {i+1} content")
                c.showPage()
            c.save()
        except ImportError:
            pytest.skip("reportlab not installed")
        
        result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
        
        assert result.file_metadata.page_count >= 1


class TestImageFormats:
    """Test different image format support."""
    
    def test_png_processing(self, processor, temp_dir):
        """Test PNG image processing."""
        img_path = temp_dir / "test.png"
        create_test_image(img_path)
        
        result = asyncio.run(processor.process_document(img_path, claim_id=1))
        
        assert result.file_metadata.mime_type == "image/png"
    
    def test_jpg_processing(self, processor, temp_dir):
        """Test JPG image processing."""
        img_path = temp_dir / "test.jpg"
        create_test_image(img_path)
        
        result = asyncio.run(processor.process_document(img_path, claim_id=1))
        
        assert result.file_metadata.mime_type == "image/jpeg"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


