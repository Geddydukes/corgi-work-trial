"""Main document processing pipeline orchestrator."""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

try:
    import magic
except ImportError:
    magic = None

try:
    import pyheif
except ImportError:
    pyheif = None

from shared import config
from shared.deduplication import DeduplicationService
from shared.error_budget_tracker import ErrorBudgetTracker
from shared.language_detector import LanguageDetector
from shared.models import (
    CostBreakdown,
    DocumentClassification,
    DocumentProcessingResult,
    DocumentType,
    ExtractedText,
    ExtractionAttempt,
    FileMetadata,
    ProcessingError,
    ProcessingErrorType,
    QualityMetrics,
    ProcessingMetrics,
)
from shared.pii_detector import PIIDetector, PIIRedactor
from shared.sla_tracker import SLATracker

from document_service.classifier import DocumentClassifier
from document_service.ocr.service import OCRService

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Enterprise-grade document processing pipeline."""
    
    def __init__(self):
        """Initialize document processor."""
        self.ocr_service = OCRService()
        self.classifier = DocumentClassifier()
        self.dedup_service = DeduplicationService()
        
        self.pii_detector = PIIDetector(use_ml_model=config.Config.PII_USE_ML_MODEL)
        self.pii_redactor = PIIRedactor(mode=config.Config.PII_REDACTION_MODE)
        self.language_detector = LanguageDetector()
        self.sla_tracker = SLATracker()
        self.error_budget_tracker = ErrorBudgetTracker()
        
        config.Config.ensure_temp_dir()
    
    async def process_document(
        self,
        file_path: Path,
        claim_id: int,
        processing_priority: int = 0,
        force_high_quality: bool = False,
    ) -> DocumentProcessingResult:
        """
        Process a document through the complete pipeline.
        
        Args:
            file_path: Path to the document file
            claim_id: Associated claim ID
            processing_priority: Processing priority (higher = more urgent)
            force_high_quality: Force high-quality OCR (skip to Tier 3)
        
        Returns:
            DocumentProcessingResult with all processing information
        """
        start_time = time.time()
        processing_id = f"{claim_id}_{int(time.time())}"
        errors = []
        extraction_attempts = []
        
        logger.info(f"Processing document: {file_path} for claim {claim_id}")
        
        try:
            file_metadata = await self._validate_and_analyze_file(file_path, errors)
            
            if file_metadata:
                cached_result = self.dedup_service.get_cached_result(file_metadata.file_hash)
                if cached_result:
                    logger.info(f"Returning cached result for {file_metadata.file_hash[:16]}...")
                    return self._result_from_dict(cached_result)
            
            if not file_metadata:
                return self._create_error_result(
                    processing_id, claim_id, file_path, errors,
                    ProcessingErrorType.FILE_NOT_FOUND,
                )
            
            is_native_pdf = file_metadata.is_native_pdf
            
            if self.error_budget_tracker.should_escalate() and not force_high_quality:
                logger.warning("Error budget exhausted, forcing high quality OCR")
                force_high_quality = True
            
            extraction_attempts, best_attempt = self.ocr_service.extract_with_attempts(
                file_path, is_native_pdf=is_native_pdf, force_high_quality=force_high_quality
            )
            
            if best_attempt:
                self.error_budget_tracker.record_document(
                    confidence=best_attempt.confidence,
                    tier=best_attempt.tier.value if best_attempt.tier else None,
                )
            
            if not best_attempt or not best_attempt.extracted_text:
                errors.append(ProcessingError(
                    error_type=ProcessingErrorType.NO_TEXT_DETECTED,
                    message="No text could be extracted from document",
                ))
                best_extraction = ExtractedText(
                    text="",
                    confidence=0.0,
                    tier_used=extraction_attempts[0].tier if extraction_attempts else None,
                )
            else:
                best_extraction = ExtractedText(
                    text=best_attempt.extracted_text,
                    confidence=best_attempt.confidence,
                    tier_used=best_attempt.tier,
                )
            
            if best_extraction.text and config.Config.LANGUAGE_DETECTION_ENABLED:
                language, lang_confidence, is_rtl = self.language_detector.detect_language(best_extraction.text)
                file_metadata.detected_language = language
                file_metadata.is_rtl = is_rtl
            
            if config.Config.PII_DETECTION_ENABLED and best_extraction.text:
                pii_detections = self.pii_detector.detect(best_extraction.text)
                
                if pii_detections:
                    file_metadata.pii_detected = True
                    
                    if config.Config.PII_REDACTION_MODE != "NONE":
                        redacted_text, redaction_applied = self.pii_redactor.redact(
                            best_extraction.text, pii_detections
                        )
                        best_extraction.redacted_text = redacted_text
            
            quality_metrics = self._assess_quality(best_extraction, file_metadata.page_count)
            
            classification = self.classifier.classify(
                best_extraction,
                file_metadata.page_count,
                best_extraction.confidence,
                filename=file_metadata.original_filename,
            )
            
            # Escalate to Tier 3 OCR if:
            # 1. Classification is UNKNOWN (regardless of confidence)
            # 2. Classification confidence is too low (< 75%)
            # 3. OCR confidence is below 85%
            from shared.models import DocumentType
            
            is_unknown = classification.document_type == DocumentType.UNKNOWN
            low_classification_confidence = classification.confidence < config.Config.CLASSIFICATION_CONFIDENCE_THRESHOLD
            low_ocr_confidence = best_extraction.confidence < 85.0
            
            should_escalate = (
                (is_unknown or low_classification_confidence or low_ocr_confidence) and
                not force_high_quality and 
                config.Config.OCR_TIER3_ENABLED
            )
            
            # Check if we haven't already used Tier 3
            already_tier3 = (
                best_extraction.tier_used is not None and 
                "tier3" in best_extraction.tier_used.value
            )
            
            if should_escalate and not already_tier3:
                escalation_reason = []
                if is_unknown:
                    escalation_reason.append("document classified as UNKNOWN")
                if low_classification_confidence:
                    escalation_reason.append(f"low classification confidence ({classification.confidence*100:.1f}%)")
                if low_ocr_confidence:
                    escalation_reason.append(f"low OCR confidence ({best_extraction.confidence:.1f}%)")
                
                logger.warning(
                    f"Escalating to Tier 3 OCR: {', '.join(escalation_reason)} "
                    f"(current tier: {best_extraction.tier_used.value if best_extraction.tier_used else 'none'})"
                )
                logger.warning(
                    f"Low classification confidence ({classification.confidence*100:.1f}%) "
                    f"with {best_extraction.tier_used.value}, retrying with Tier 3 OCR"
                )
                # Retry with Tier 3
                tier3_attempts, tier3_best = self.ocr_service.extract_with_attempts(
                    file_path, is_native_pdf=is_native_pdf, force_high_quality=True
                )
                if tier3_best and tier3_best.extracted_text:
                    extraction_attempts.extend(tier3_attempts)
                    best_attempt = tier3_best
                    best_extraction = ExtractedText(
                        text=tier3_best.extracted_text,
                        confidence=tier3_best.confidence,
                        tier_used=tier3_best.tier,
                    )
                    # Re-classify with better OCR (pass filename for move-out-statement detection)
                    classification = self.classifier.classify(
                        best_extraction, file_metadata.page_count, best_extraction.confidence,
                        filename=file_metadata.original_filename
                    )
                    logger.info(
                        f"Tier 3 OCR improved classification confidence to {classification.confidence*100:.1f}%"
                    )
                    # Re-assess quality with new extraction
                    quality_metrics = self._assess_quality(best_extraction, file_metadata.page_count)
            
            requires_manual_review, review_reasons = self._determine_manual_review(
                classification, quality_metrics, best_extraction.confidence
            )
            
            cost_breakdown = self._calculate_costs(extraction_attempts, file_metadata.page_count)
            
            total_time_ms = int((time.time() - start_time) * 1000)
            
            tier_used = best_attempt.tier if best_attempt else None
            processing_metrics = ProcessingMetrics(
                total_time_ms=total_time_ms,
                tier_used=tier_used,
                pages_processed=file_metadata.page_count,
                tier1_attempts=sum(1 for a in extraction_attempts if "tier1" in a.tier.value),
                tier2_attempts=sum(1 for a in extraction_attempts if "tier2" in a.tier.value),
                tier3_attempts=sum(1 for a in extraction_attempts if "tier3" in a.tier.value),
            )
            
            result = DocumentProcessingResult(
                processing_id=processing_id,
                claim_id=claim_id,
                file_metadata=file_metadata,
                extraction_attempts=extraction_attempts,
                best_extraction=best_extraction,
                classification=classification,
                quality_metrics=quality_metrics,
                processing_metrics=processing_metrics,
                errors=errors,
                requires_manual_review=requires_manual_review,
                manual_review_reasons=review_reasons,
                cost_breakdown=cost_breakdown,
            )
            
            self.sla_tracker.record_processing_time(
                processing_time_ms=total_time_ms,
                document_type=classification.document_type.value,
            )
            
            self._log_processing_result(result)
            
            if file_metadata:
                self.dedup_service.cache_result(file_metadata.file_hash, result)
            
            return result
            
        except Exception as e:
            logger.exception(f"Unexpected error processing document: {e}")
            errors.append(ProcessingError(
                error_type=ProcessingErrorType.OTHER,
                message=str(e),
                stack_trace=str(e.__traceback__) if hasattr(e, "__traceback__") else None,
            ))
            return self._create_error_result(processing_id, claim_id, file_path, errors, ProcessingErrorType.OTHER)
    
    async def _validate_and_analyze_file(
        self, file_path: Path, errors: list[ProcessingError]
    ) -> Optional[FileMetadata]:
        """Validate file and extract metadata."""
        if not file_path.exists():
            errors.append(ProcessingError(
                error_type=ProcessingErrorType.FILE_NOT_FOUND,
                message=f"File not found: {file_path}",
            ))
            return None
        
        try:
            file_size = file_path.stat().st_size
            
            if file_size > config.Config.MAX_FILE_SIZE_BYTES:
                errors.append(ProcessingError(
                    error_type=ProcessingErrorType.DOCUMENT_TOO_LARGE,
                    message=f"File size {file_size} exceeds maximum {config.Config.MAX_FILE_SIZE_BYTES}",
                ))
                return None
            
            if magic:
                mime_type = magic.from_file(str(file_path), mime=True)
            else:
                mime_type = self._guess_mime_type(file_path)
            
            if config.Config.VIRUS_SCAN_ENABLED:
                if not await self._scan_for_viruses(file_path):
                    errors.append(ProcessingError(
                        error_type=ProcessingErrorType.VIRUS_DETECTED,
                        message="Virus detected in file",
                    ))
                    return None
            
            file_hash = self._calculate_file_hash(file_path)
            
            is_password_protected = False
            is_native_pdf = False
            is_scanned = False
            page_count = 1
            
            if mime_type == "application/pdf":
                is_password_protected, is_native_pdf, page_count = self._analyze_pdf(file_path)
                is_scanned = not is_native_pdf
            elif mime_type.startswith("image/"):
                page_count = 1
                if mime_type == "image/heic":
                    file_path = await self._convert_heic_to_jpg(file_path)
                    mime_type = "image/jpeg"
            
            return FileMetadata(
                original_filename=file_path.name,
                file_size_bytes=file_size,
                mime_type=mime_type,
                file_hash=file_hash,
                page_count=page_count,
                is_password_protected=is_password_protected,
                is_native_pdf=is_native_pdf,
                is_scanned=is_scanned,
            )
            
        except PermissionError as e:
            errors.append(ProcessingError(
                error_type=ProcessingErrorType.PERMISSION_ERROR,
                message=f"Permission denied: {e}",
            ))
            return None
        except Exception as e:
            errors.append(ProcessingError(
                error_type=ProcessingErrorType.OTHER,
                message=f"File validation error: {e}",
            ))
            return None
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _analyze_pdf(self, file_path: Path) -> Tuple[bool, bool, int]:
        """Analyze PDF to determine if password-protected, native, and page count."""
        is_password_protected = False
        is_native = False
        page_count = 0
        
        try:
            from pypdf import PdfReader
            
            with open(file_path, "rb") as f:
                reader = PdfReader(f)
                
                if reader.is_encrypted:
                    is_password_protected = True
                    common_passwords = ["", "password", "123456"]
                    for pwd in common_passwords:
                        if reader.decrypt(pwd):
                            is_password_protected = False
                            break
                
                page_count = len(reader.pages)
                
                if page_count > 0:
                    first_page = reader.pages[0]
                    text = first_page.extract_text()
                    if text and len(text.strip()) > 50:
                        is_native = True
        except Exception as e:
            logger.warning(f"PDF analysis error: {e}")
        
        return is_password_protected, is_native, page_count
    
    async def _scan_for_viruses(self, file_path: Path) -> bool:
        """Scan file for viruses using ClamAV."""
        try:
            import pyclamd
            
            cd = pyclamd.ClamdUnixSocket()
            result = cd.scan_file(str(file_path))
            
            if result:
                return False
            
            return True
        except ImportError:
            logger.warning("pyclamd not installed, skipping virus scan")
            return True
        except Exception as e:
            logger.warning(f"Virus scan error: {e}")
            return True
    
    def _guess_mime_type(self, file_path: Path) -> str:
        """Guess MIME type from file extension."""
        ext = file_path.suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".heic": "image/heic",
        }
        return mime_map.get(ext, "application/octet-stream")
    
    async def _convert_heic_to_jpg(self, file_path: Path) -> Path:
        """Convert HEIC image to JPG."""
        if not pyheif:
            logger.warning("pyheif not available, cannot convert HEIC")
            return file_path
        
        try:
            heif_file = pyheif.read(str(file_path))
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            
            output_path = config.Config.TEMP_DIR / f"{file_path.stem}.jpg"
            image.save(output_path, "JPEG", quality=95)
            
            return output_path
        except Exception as e:
            logger.error(f"HEIC conversion error: {e}")
            return file_path
    
    def _assess_quality(self, extracted_text: ExtractedText, page_count: int) -> QualityMetrics:
        """Assess quality of extracted text."""
        if not extracted_text.text:
            return QualityMetrics(
                avg_ocr_confidence=0.0,
                blank_page_count=page_count,
                low_confidence_page_count=page_count,
            )
        
        pages = extracted_text.text.split("\n\n")
        blank_pages = sum(1 for page in pages if len(page.strip().split()) < 10)
        low_confidence_pages = []
        
        avg_confidence = extracted_text.confidence
        
        has_table = "|" in extracted_text.text or "\t" in extracted_text.text
        has_form = any(keyword in extracted_text.text.lower() for keyword in ["form", "field", "checkbox"])
        
        pages_needing_review = []
        for i, page in enumerate(pages):
            if len(page.strip().split()) < 10:
                pages_needing_review.append(i + 1)
        
        return QualityMetrics(
            avg_ocr_confidence=avg_confidence,
            blank_page_count=blank_pages,
            low_confidence_page_count=len(low_confidence_pages),
            table_detected=has_table,
            form_detected=has_form,
            pages_needing_review=pages_needing_review,
        )
    
    def _determine_manual_review(
        self,
        classification: DocumentClassification,
        quality_metrics: QualityMetrics,
        ocr_confidence: float,
    ) -> tuple[bool, list[str]]:
        """Determine if manual review is required."""
        requires_review = False
        reasons = []
        
        if classification.confidence < config.Config.CLASSIFICATION_CONFIDENCE_THRESHOLD:
            requires_review = True
            reasons.append(f"Low classification confidence: {classification.confidence:.2f}")
        
        if ocr_confidence < 50.0:
            requires_review = True
            reasons.append(f"Low OCR confidence: {ocr_confidence:.1f}%")
        
        if quality_metrics.blank_page_count > 0:
            requires_review = True
            reasons.append(f"Blank pages detected: {quality_metrics.blank_page_count}")
        
        if classification.document_type == DocumentType.UNKNOWN:
            requires_review = True
            reasons.append("Document type could not be determined")
        
        if quality_metrics.pages_needing_review:
            requires_review = True
            reasons.append(f"Pages needing review: {len(quality_metrics.pages_needing_review)}")
        
        return requires_review, reasons
    
    def _calculate_costs(self, extraction_attempts: list[ExtractionAttempt], page_count: int) -> CostBreakdown:
        """Calculate processing costs."""
        tier3_pages = 0
        tier3_cost = 0.0
        
        for attempt in extraction_attempts:
            if "tier3" in attempt.tier.value:
                tier3_pages += attempt.page_count
                tier3_cost += attempt.cost
        
        return CostBreakdown(
            tier3_pages=tier3_pages,
            tier3_cost=tier3_cost,
            total_cost_usd=tier3_cost,
        )
    
    def _log_processing_result(self, result: DocumentProcessingResult) -> None:
        """Log processing result in structured JSON format."""
        log_data = {
            "processing_id": result.processing_id,
            "claim_id": result.claim_id,
            "filename": result.file_metadata.original_filename,
            "file_size_mb": round(result.file_metadata.file_size_bytes / 1024 / 1024, 2),
            "page_count": result.file_metadata.page_count,
            "ocr_tier": result.processing_metrics.tier_used.value if result.processing_metrics.tier_used else None,
            "processing_time_ms": result.processing_metrics.total_time_ms,
            "ocr_confidence": round(result.best_extraction.confidence, 1),
            "classification": result.classification.document_type.value,
            "classification_confidence": round(result.classification.confidence, 2),
            "errors": [e.error_type.value for e in result.errors],
            "cost_usd": round(result.cost_breakdown.total_cost_usd, 4),
        }
        
        logger.info(f"Processing complete: {log_data}")
    
    def _result_from_dict(self, data: dict) -> DocumentProcessingResult:
        """Reconstruct DocumentProcessingResult from dictionary."""
        from shared.models import (
            FileMetadata, ExtractedText, DocumentClassification,
            QualityMetrics, ProcessingMetrics, CostBreakdown,
            ExtractionAttempt, ProcessingError,
        )
        from datetime import datetime
        
        return DocumentProcessingResult(
            processing_id=data["processing_id"],
            claim_id=data["claim_id"],
            file_metadata=FileMetadata(**data["file_metadata"]),
            extraction_attempts=[ExtractionAttempt(**attempt) for attempt in data["extraction_attempts"]],
            best_extraction=ExtractedText(**data["best_extraction"]),
            classification=DocumentClassification(**data["classification"]),
            quality_metrics=QualityMetrics(**data["quality_metrics"]),
            processing_metrics=ProcessingMetrics(**data["processing_metrics"]),
            errors=[ProcessingError(**error) for error in data["errors"]],
            requires_manual_review=data["requires_manual_review"],
            manual_review_reasons=data["manual_review_reasons"],
            cost_breakdown=CostBreakdown(**data["cost_breakdown"]),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"],
        )
    
    def _create_error_result(
        self,
        processing_id: str,
        claim_id: int,
        file_path: Path,
        errors: list[ProcessingError],
        error_type: ProcessingErrorType,
    ) -> DocumentProcessingResult:
        """Create error result when processing fails."""
        from shared.models import FileMetadata, ExtractedText, DocumentClassification, QualityMetrics, ProcessingMetrics
        
        return DocumentProcessingResult(
            processing_id=processing_id,
            claim_id=claim_id,
            file_metadata=FileMetadata(
                original_filename=file_path.name if file_path.exists() else "unknown",
                file_size_bytes=0,
                mime_type="unknown",
                file_hash="",
                page_count=0,
            ),
            extraction_attempts=[],
            best_extraction=ExtractedText(
                text="",
                confidence=0.0,
                tier_used=None,
            ),
            classification=DocumentClassification(
                document_type=DocumentType.UNKNOWN,
                confidence=0.0,
            ),
            quality_metrics=QualityMetrics(avg_ocr_confidence=0.0),
            processing_metrics=ProcessingMetrics(
                total_time_ms=0,
                tier_used=None,
                pages_processed=0,
            ),
            errors=errors,
            requires_manual_review=True,
            manual_review_reasons=["Processing failed"],
        )

