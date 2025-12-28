"""Integration tests with real sample documents."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from document_processor import DocumentProcessor
from models import DocumentType


@pytest.fixture
def processor():
    """Create document processor instance."""
    return DocumentProcessor()


def create_sample_lease_pdf(output_path: Path) -> None:
    """Create a sample lease agreement PDF."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(output_path), pagesize=letter)
        c.drawString(100, 750, "LEASE AGREEMENT")
        c.drawString(100, 730, "This lease agreement is entered into on January 1, 2024")
        c.drawString(100, 710, "TERM: 12 months")
        c.drawString(100, 690, "MONTHLY RENT: $1,500.00")
        c.drawString(100, 670, "Security Deposit: $1,500.00")
        c.drawString(100, 650, "Property Address: 123 Main Street")
        c.save()
    except ImportError:
        pytest.skip("reportlab not installed")


def create_sample_invoice_pdf(output_path: Path) -> None:
    """Create a sample invoice PDF."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(output_path), pagesize=letter)
        c.drawString(100, 750, "INVOICE")
        c.drawString(100, 730, "Invoice Number: INV-001")
        c.drawString(100, 710, "Date: January 15, 2024")
        c.drawString(100, 690, "Itemized charges:")
        c.drawString(100, 670, "Flooring replacement: $3,000.00")
        c.drawString(100, 650, "Paint: $1,500.00")
        c.drawString(100, 630, "Cleaning: $500.00")
        c.drawString(100, 610, "BALANCE DUE: $5,000.00")
        c.save()
    except ImportError:
        pytest.skip("reportlab not installed")


def create_sample_addendum_pdf(output_path: Path) -> None:
    """Create a sample addendum PDF."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(output_path), pagesize=letter)
        c.drawString(100, 750, "ADDENDUM TO LEASE AGREEMENT")
        c.drawString(100, 730, "This addendum modifies the original lease agreement")
        c.drawString(100, 710, "SECURITY DEPOSIT WAIVER: Yes")
        c.drawString(100, 690, "ENROLLMENT: Confirmed")
        c.save()
    except ImportError:
        pytest.skip("reportlab not installed")


class TestIntegration:
    """Integration tests with sample documents."""
    
    def test_lease_processing(self, processor):
        """Test processing a lease document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "lease.pdf"
            create_sample_lease_pdf(pdf_path)
            
            result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
            
            assert result.file_metadata.page_count > 0
            assert result.best_extraction.text
            assert result.classification.document_type in [DocumentType.LEASE, DocumentType.UNKNOWN]
    
    def test_invoice_processing(self, processor):
        """Test processing an invoice document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "invoice.pdf"
            create_sample_invoice_pdf(pdf_path)
            
            result = asyncio.run(processor.process_document(pdf_path, claim_id=2))
            
            assert result.file_metadata.page_count > 0
            assert result.best_extraction.text
            assert result.classification.document_type in [DocumentType.INVOICE, DocumentType.UNKNOWN]
    
    def test_addendum_processing(self, processor):
        """Test processing an addendum document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "addendum.pdf"
            create_sample_addendum_pdf(pdf_path)
            
            result = asyncio.run(processor.process_document(pdf_path, claim_id=3))
            
            assert result.file_metadata.page_count > 0
            assert result.best_extraction.text
            assert result.classification.document_type in [DocumentType.ADDENDUM, DocumentType.UNKNOWN]
    
    def test_end_to_end_processing(self, processor):
        """Test complete end-to-end processing pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            create_sample_lease_pdf(pdf_path)
            
            result = asyncio.run(processor.process_document(
                pdf_path, claim_id=4, force_high_quality=False
            ))
            
            assert result.processing_id
            assert result.claim_id == 4
            assert result.file_metadata.file_hash
            assert result.best_extraction
            assert result.classification
            assert result.quality_metrics
            assert result.processing_metrics
            assert result.cost_breakdown
            assert isinstance(result.errors, list)
    
    def test_processing_with_priority(self, processor):
        """Test processing with different priorities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            create_sample_lease_pdf(pdf_path)
            
            result = asyncio.run(processor.process_document(
                pdf_path, claim_id=5, processing_priority=10
            ))
            
            assert result.processing_id
            assert result.claim_id == 5

