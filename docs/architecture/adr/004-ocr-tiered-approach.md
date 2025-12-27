# ADR-004: Tiered OCR Approach (Tesseract → Textract Fallback)

## Status
Accepted

## Context
We need OCR capabilities for document processing with:
- Cost optimization (minimize cloud OCR costs)
- High accuracy for various document types
- Fallback mechanism for difficult documents
- Processing time targets (< 30 seconds per document)
- Support for PDFs and scanned images

## Decision
We will use a **tiered OCR approach**:
1. **Tier 1**: PyPDF2 / pdfplumber (native PDF text extraction)
2. **Tier 2**: Tesseract OCR (open-source, local)
3. **Tier 3**: AWS Textract (cloud, fallback only)

## Rationale

### Tier 1: Native PDF Extraction
- **Cost**: Free (no OCR needed)
- **Speed**: < 100ms
- **Use Case**: Native PDFs with text layers
- **Coverage**: ~60% of documents

### Tier 2: Tesseract OCR
- **Cost**: Free (open-source)
- **Speed**: 1-3 seconds per page
- **Use Case**: Scanned PDFs, images
- **Coverage**: ~35% of documents
- **Accuracy**: Good for standard documents

### Tier 3: AWS Textract
- **Cost**: $0.0015 per page (expensive)
- **Speed**: 2-5 seconds per page
- **Use Case**: Complex documents, low confidence from Tesseract
- **Coverage**: ~5% of documents (fallback only)
- **Accuracy**: Highest accuracy, handles complex layouts

### Cost Optimization
- **Target**: < 5% of documents use Textract
- **Savings**: ~95% cost reduction vs. using Textract for all documents
- **Strategy**: Only use Textract when Tesseract confidence < 60%

## Alternatives Considered

### 1. Textract for All Documents
- **Pros**: Highest accuracy, managed service
- **Cons**: $0.0015/page × 100M documents = $150K+ per year
- **Decision**: Rejected due to cost

### 2. Tesseract Only
- **Pros**: Free, no cloud dependency
- **Cons**: Lower accuracy for complex documents, no fallback
- **Decision**: Rejected due to accuracy requirements

### 3. Google Cloud Vision API
- **Pros**: Good accuracy, competitive pricing
- **Cons**: Vendor lock-in, similar cost to Textract
- **Decision**: Rejected due to AWS ecosystem preference

### 4. Azure Form Recognizer
- **Pros**: Good accuracy, document understanding
- **Cons**: Vendor lock-in, higher cost
- **Decision**: Rejected due to AWS ecosystem preference

## Implementation Details

### Processing Flow
```
1. Try Tier 1 (PyPDF2/pdfplumber)
   → If text extracted with confidence > 80%: Use result
   → Else: Continue to Tier 2

2. Try Tier 2 (Tesseract)
   → If confidence > 60%: Use result
   → Else: Continue to Tier 3

3. Use Tier 3 (Textract)
   → Always use result (highest confidence)
```

### Confidence Thresholds
- **Tier 1 Success**: > 80% confidence
- **Tier 2 Success**: > 60% confidence
- **Tier 3**: Always used as fallback

### Cost Monitoring
- Track Textract usage percentage
- Alert if Textract usage > 10% (indicates Tesseract issues)
- Monthly cost reports

### Circuit Breaker
- If Textract fails 5 times in 60 seconds: Open circuit
- Fallback to manual review queue
- Half-open after 30 seconds

## Consequences

### Positive
- 95% cost reduction vs. Textract-only approach
- High accuracy with fallback mechanism
- No vendor lock-in for majority of documents
- Fast processing for native PDFs

### Negative
- More complex implementation (3 tiers)
- Tesseract requires local installation
- Textract dependency for fallback (external service)

### Mitigations
- Clear tier selection logic
- Docker image includes Tesseract
- Circuit breaker for Textract failures
- Manual review queue for failed OCR

## References
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [AWS Textract Pricing](https://aws.amazon.com/textract/pricing/)
- [PyPDF2 vs pdfplumber](https://github.com/jsvine/pdfplumber)

