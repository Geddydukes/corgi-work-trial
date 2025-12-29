"""Performance tests for document processing."""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from document_processor import DocumentProcessor


@pytest.fixture
def processor():
    """Create document processor instance."""
    return DocumentProcessor()


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


class TestPerformance:
    """Performance tests."""
    
    def test_single_document_performance(self, processor):
        """Test single document processing time."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            create_test_pdf("Test content", pdf_path)
            
            start_time = time.time()
            result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
            elapsed = time.time() - start_time
            
            assert elapsed < 30.0
            assert result.processing_metrics.total_time_ms < 30000
    
    @pytest.mark.slow
    def test_batch_processing_performance(self, processor):
        """Test batch processing 100 documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_files = []
            for i in range(100):
                pdf_path = Path(tmpdir) / f"test_{i}.pdf"
                create_test_pdf(f"Test content {i}", pdf_path)
                pdf_files.append(pdf_path)
            
            start_time = time.time()
            results = []
            for pdf_path in pdf_files:
                result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
                results.append(result)
            elapsed = time.time() - start_time
            
            assert len(results) == 100
            assert elapsed < 300.0
    
    def test_tier1_performance(self, processor):
        """Test Tier 1 OCR performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            create_test_pdf("Test content for OCR", pdf_path)
            
            start_time = time.time()
            result = asyncio.run(processor.process_document(pdf_path, claim_id=1))
            elapsed = time.time() - start_time
            
            if result.processing_metrics.tier_used:
                if "tier1" in result.processing_metrics.tier_used.value:
                    assert elapsed < 1.0


