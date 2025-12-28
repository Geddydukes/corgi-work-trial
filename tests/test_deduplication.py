"""Tests for deduplication service."""

import pytest

from deduplication import DeduplicationService
from models import DocumentProcessingResult, FileMetadata, ExtractedText, DocumentClassification, QualityMetrics, ProcessingMetrics, OCRTier, DocumentType


@pytest.fixture
def dedup_service():
    """Create deduplication service instance."""
    return DeduplicationService()


class TestDeduplication:
    """Test deduplication functionality."""
    
    def test_cache_result(self, dedup_service):
        """Test caching a result."""
        file_hash = "test_hash_12345"
        result = DocumentProcessingResult(
            processing_id="test_id",
            claim_id=1,
            file_metadata=FileMetadata(
                original_filename="test.pdf",
                file_size_bytes=1000,
                mime_type="application/pdf",
                file_hash=file_hash,
                page_count=1,
            ),
            best_extraction=ExtractedText(
                text="test",
                confidence=90.0,
                tier=OCRTier.TIER1_PYPDF2,
            ),
            classification=DocumentClassification(
                document_type=DocumentType.UNKNOWN,
                confidence=0.9,
            ),
            quality_metrics=QualityMetrics(avg_ocr_confidence=90.0),
            processing_metrics=ProcessingMetrics(
                total_time_ms=100,
                tier_used=OCRTier.TIER1_PYPDF2,
                pages_processed=1,
            ),
        )
        
        dedup_service.cache_result(file_hash, result)
        
        cached = dedup_service.get_cached_result(file_hash)
        assert cached is not None
        assert cached["processing_id"] == "test_id"
    
    def test_get_cached_result_nonexistent(self, dedup_service):
        """Test getting non-existent cached result."""
        cached = dedup_service.get_cached_result("nonexistent_hash")
        assert cached is None
    
    def test_check_duplicate(self, dedup_service):
        """Test duplicate checking."""
        file_hash = "test_hash_67890"
        
        assert not dedup_service.check_duplicate(file_hash)
        
        result = DocumentProcessingResult(
            processing_id="test_id_2",
            claim_id=2,
            file_metadata=FileMetadata(
                original_filename="test2.pdf",
                file_size_bytes=2000,
                mime_type="application/pdf",
                file_hash=file_hash,
                page_count=2,
            ),
            best_extraction=ExtractedText(
                text="test2",
                confidence=85.0,
                tier=OCRTier.TIER2_TESSERACT,
            ),
            classification=DocumentClassification(
                document_type=DocumentType.UNKNOWN,
                confidence=0.85,
            ),
            quality_metrics=QualityMetrics(avg_ocr_confidence=85.0),
            processing_metrics=ProcessingMetrics(
                total_time_ms=200,
                tier_used=OCRTier.TIER2_TESSERACT,
                pages_processed=2,
            ),
        )
        
        dedup_service.cache_result(file_hash, result)
        
        assert dedup_service.check_duplicate(file_hash)

