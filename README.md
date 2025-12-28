# Enterprise Document Ingestion Pipeline

Production-grade document processing pipeline with multi-tier OCR, ML-based classification, and comprehensive error handling.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Document Processor                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Validation  │→ │  Format      │→ │  OCR Service │     │
│  │  & Security  │  │  Detection   │  │  (Multi-tier)│     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         ↓                  ↓                  ↓             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Quality     │→ │  Classifier  │→ │  Result      │     │
│  │  Assessment  │  │  (ML+Rules)  │  │  Generation  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Supported Formats

- **PDFs**: Native and scanned documents
- **Images**: PNG, JPG, JPEG, TIFF, HEIC
- **Multi-page documents**: Automatic page splitting
- **Password-protected PDFs**: Attempts common passwords
- **Corrupted files**: Graceful degradation with partial results

### Multi-Tier OCR Strategy

1. **Tier 1** (Free, Fast): PyPDF2/pdfplumber for native PDFs

   - Processing time: < 100ms
   - Cost: $0.00

2. **Tier 2** (Free, Medium Quality): Tesseract OCR for scanned docs

   - Processing time: < 3sec/page
   - Cost: $0.00

3. **Tier 3** (Paid, High Quality): Google Gemini Flash or Mistral AI for complex layouts
   - Processing time: < 5sec/page
   - Cost: $0.0001/page (Gemini Flash) or $0.0002/page (Mistral)
   - Provider selectable via `TIER3_PROVIDER` environment variable

### Document Classification

- **ML-Based**: TF-IDF + Logistic Regression
- **Rule-Based Fallback**: Keyword matching and feature extraction
- **Document Types**: Lease, Invoice, Addendum, Unknown
- **Confidence Threshold**: 0.75 for auto-classification

### Processing Pipeline

1. **File Validation**

   - Size check (max 50MB)
   - MIME type validation
   - Virus scanning (ClamAV)
   - SHA-256 hash calculation
   - Unique processing ID generation

2. **Format Detection & Conversion**

   - Native vs scanned PDF detection
   - HEIC to JPG conversion
   - Image DPI normalization (300 DPI)
   - Multi-page splitting

3. **Text Extraction** (with fallback chain)

   - Try Tier 1 first (< 100ms)
   - If confidence < 60%, try Tier 2 (< 3sec/page)
   - If still < 60%, escalate to Tier 3 (< 5sec/page)

4. **Quality Assessment**

   - OCR confidence (char-level and page-level)
   - Blank page detection (< 10 words)
   - Table/form detection
   - Manual review flagging (confidence < 50%)

5. **Document Classification**
   - Feature extraction (keywords, structure, dollar amounts, dates)
   - ML classification with confidence scoring
   - Rule-based fallback
   - Manual review for low confidence

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install system dependencies
# Ubuntu/Debian
sudo apt-get install tesseract-ocr libmagic1 libheif-dev

# macOS
brew install tesseract libmagic libheif

# Install ClamAV (optional, for virus scanning)
sudo apt-get install clamav clamav-daemon
```

## Configuration

Set environment variables:

```bash
# OCR Configuration
OCR_TIER1_ENABLED=true
OCR_TIER2_ENABLED=true
OCR_TIER3_ENABLED=false  # Enable for high-quality processing
OCR_CONFIDENCE_THRESHOLD=60

# Classification
CLASSIFICATION_CONFIDENCE_THRESHOLD=0.75

# File Processing
MAX_FILE_SIZE_MB=50
PROCESSING_TIMEOUT_SEC=60

# Security
VIRUS_SCAN_ENABLED=true
CLAMAV_HOST=localhost
CLAMAV_PORT=3310

# Tier 3 OCR Provider (gemini or mistral)
TIER3_PROVIDER=gemini

# Google Gemini (for Tier 3 OCR)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash

# Mistral AI (for Tier 3 OCR, alternative to Gemini)
MISTRAL_API_KEY=your_mistral_api_key
MISTRAL_MODEL=pixtral-12b-2409

# Redis (for Celery)
REDIS_URL=redis://localhost:6379/0
```

## Usage

### Basic Usage

```python
from pathlib import Path
from document_processor import DocumentProcessor

processor = DocumentProcessor()

result = await processor.process_document(
    file_path=Path("document.pdf"),
    claim_id=123,
    processing_priority=0,
    force_high_quality=False,
)

print(f"Classification: {result.classification.document_type}")
print(f"Confidence: {result.classification.confidence}")
print(f"OCR Confidence: {result.best_extraction.confidence}")
print(f"Requires Review: {result.requires_manual_review}")
```

### With Celery (Async Processing)

```python
from celery import Celery
from document_processor import DocumentProcessor

app = Celery('document_processor', broker='redis://localhost:6379/0')

@app.task
def process_document_task(file_path: str, claim_id: int):
    processor = DocumentProcessor()
    return asyncio.run(processor.process_document(
        Path(file_path), claim_id
    ))
```

## Output Structure

```python
DocumentProcessingResult(
    processing_id="uuid",
    claim_id=123,
    file_metadata=FileMetadata(...),
    extraction_attempts=[...],
    best_extraction=ExtractedText(...),
    classification=DocumentClassification(...),
    quality_metrics=QualityMetrics(...),
    processing_metrics=ProcessingMetrics(...),
    errors=[],
    requires_manual_review=False,
    manual_review_reasons=[],
    cost_breakdown=CostBreakdown(...),
    created_at=datetime(...),
)
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test class
pytest tests/test_document_processor.py::TestClassification -v
```

## Performance

- **Single Document**: < 5 seconds (Tier 1), < 30 seconds (Tier 3)
- **Batch Processing**: 100 documents in < 5 minutes (with parallel workers)
- **Cost Optimization**: Automatically selects cheapest tier that meets quality threshold

## Error Handling

The pipeline handles various error conditions:

- **File Errors**: FileNotFoundError, PermissionError, CorruptedFileError
- **OCR Errors**: TesseractNotFound, OutOfMemoryError, CloudServiceError
- **Business Logic**: UnsupportedFileType, DocumentTooLarge, NoTextDetected

All errors are captured in the `errors` field of the result with detailed information.

## Monitoring

Structured JSON logs are emitted for each processed document:

```json
{
  "processing_id": "uuid",
  "claim_id": 123,
  "filename": "invoice.pdf",
  "file_size_mb": 2.3,
  "page_count": 3,
  "ocr_tier": "tier2_tesseract",
  "processing_time_ms": 2340,
  "ocr_confidence": 87.5,
  "classification": "invoice",
  "classification_confidence": 0.92,
  "errors": [],
  "cost_usd": 0.0
}
```

## Security

- **File Validation**: Magic bytes verification (not just extension)
- **Virus Scanning**: ClamAV integration
- **Metadata Stripping**: EXIF data removal from images
- **Sandboxing**: OCR processing can run in containers
- **Encryption**: Extracted text encrypted at rest

## Deduplication

Files are deduplicated by SHA-256 hash:

- Hash calculated before processing
- Cached results returned instantly for duplicates
- 90-day TTL on cache

## License

Proprietary - All rights reserved
