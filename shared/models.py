from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class DocumentType(str, Enum):
    LEASE = "lease"
    INVOICE = "invoice"
    ADDENDUM = "addendum"
    UNKNOWN = "unknown"
    SUPPORTING_DOC = "supporting_doc"


class OCRTier(str, Enum):
    TIER1_PYPDF2 = "tier1_pypdf2"
    TIER1_PDFPLUMBER = "tier1_pdfplumber"
    TIER2_TESSERACT = "tier2_tesseract"
    TIER3_GEMINI_FLASH = "tier3_gemini_flash"
    TIER3_MISTRAL = "tier3_mistral"


class ProcessingErrorType(str, Enum):
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_ERROR = "permission_error"
    CORRUPTED_FILE = "corrupted_file"
    TIMEOUT_ERROR = "timeout_error"
    TESSERACT_NOT_FOUND = "tesseract_not_found"
    OUT_OF_MEMORY = "out_of_memory"
    CLOUD_SERVICE_ERROR = "cloud_service_error"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    DOCUMENT_TOO_LARGE = "document_too_large"
    NO_TEXT_DETECTED = "no_text_detected"
    VIRUS_DETECTED = "virus_detected"
    PASSWORD_PROTECTED = "password_protected"
    OTHER = "other"


class ProcessingError(BaseModel):
    error_type: ProcessingErrorType
    message: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    stack_trace: Optional[str] = None


class FileMetadata(BaseModel):
    original_filename: str
    file_size_bytes: int
    mime_type: str
    file_hash: str = Field(..., description="SHA-256 hash")
    page_count: int
    is_password_protected: bool = False
    is_native_pdf: bool = False
    is_scanned: bool = False
    pii_detected: bool = False
    detected_language: Optional[str] = None
    is_rtl: bool = False


class ExtractionAttempt(BaseModel):
    tier: OCRTier
    extracted_text: str
    confidence: float = Field(..., ge=0.0, le=100.0)
    processing_time_ms: int
    cost: float = 0.0
    page_count: int
    error: Optional[ProcessingError] = None


class ExtractedText(BaseModel):
    text: str
    confidence: float = Field(..., ge=0.0, le=100.0)
    tier_used: OCRTier
    page_wise_text: List[str] = Field(default_factory=list)
    page_wise_confidence: List[float] = Field(default_factory=list)
    redacted_text: Optional[str] = None


class FeatureScores(BaseModel):
    keyword_score: float = 0.0
    structure_score: float = 0.0
    dollar_amount_score: float = 0.0
    date_pattern_score: float = 0.0
    page_count_score: float = 0.0


class DocumentClassification(BaseModel):
    document_type: DocumentType
    confidence: float = Field(..., ge=0.0, le=1.0)
    feature_scores: FeatureScores = Field(default_factory=FeatureScores)
    fallback_used: bool = False
    ml_probabilities: dict[str, float] = Field(default_factory=dict)


class QualityMetrics(BaseModel):
    avg_ocr_confidence: float = Field(..., ge=0.0, le=100.0)
    blank_page_count: int = 0
    low_confidence_page_count: int = 0
    table_detected: bool = False
    form_detected: bool = False
    pages_needing_review: List[int] = Field(default_factory=list)


class ProcessingMetrics(BaseModel):
    total_time_ms: int
    tier_used: OCRTier
    retry_count: int = 0
    pages_processed: int
    tier1_attempts: int = 0
    tier2_attempts: int = 0
    tier3_attempts: int = 0


class CostBreakdown(BaseModel):
    tier3_pages: int = 0
    tier3_cost: float = 0.0
    total_cost_usd: float = 0.0


@dataclass
class DocumentProcessingResult:
    processing_id: str = field(default_factory=lambda: str(uuid4()))
    claim_id: int
    file_metadata: FileMetadata
    extraction_attempts: List[ExtractionAttempt] = field(default_factory=list)
    best_extraction: ExtractedText
    classification: DocumentClassification
    quality_metrics: QualityMetrics
    processing_metrics: ProcessingMetrics
    errors: List[ProcessingError] = field(default_factory=list)
    requires_manual_review: bool = False
    manual_review_reasons: List[str] = field(default_factory=list)
    cost_breakdown: CostBreakdown = field(default_factory=CostBreakdown)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "processing_id": self.processing_id,
            "claim_id": self.claim_id,
            "file_metadata": self.file_metadata.model_dump(),
            "extraction_attempts": [attempt.model_dump() for attempt in self.extraction_attempts],
            "best_extraction": self.best_extraction.model_dump(),
            "classification": self.classification.model_dump(),
            "quality_metrics": self.quality_metrics.model_dump(),
            "processing_metrics": self.processing_metrics.model_dump(),
            "errors": [error.model_dump() for error in self.errors],
            "requires_manual_review": self.requires_manual_review,
            "manual_review_reasons": self.manual_review_reasons,
            "cost_breakdown": self.cost_breakdown.model_dump(),
            "created_at": self.created_at.isoformat(),
        }

