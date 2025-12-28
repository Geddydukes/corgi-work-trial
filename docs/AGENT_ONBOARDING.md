# Agent Onboarding Guide

**Purpose**: This document helps AI agents quickly understand the codebase structure, architecture, and key patterns to be productive immediately.

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Key Components](#key-components)
4. [Data Models](#data-models)
5. [Processing Flows](#processing-flows)
6. [Critical Requirements](#critical-requirements)
7. [File Organization](#file-organization)
8. [Common Patterns](#common-patterns)
9. [Development Guidelines](#development-guidelines)
10. [Quick Reference](#quick-reference)

---

## System Overview

### What This System Does

**Security Deposit Claims Decision Engine** - An enterprise-grade system that:

- Processes security deposit claim documents (PDFs, images) using multi-tier OCR
- Classifies documents (lease, invoice, addendum, etc.)
- Parses invoices to extract line items and amounts
- Evaluates claim eligibility based on business rules
- Generates automated decisions (approve/deny) with confidence scores
- Handles high-volume processing (100M+ claims over 7 years)

### Core Services

1. **Decision Service** (`decision_service/`) - FastAPI service for claim evaluation

   - Port: 8000 (default)
   - Main entry: `decision_service/main.py`
   - Routes: `decision_service/routes/claims.py`

2. **Document Service** (`document_service/`) - FastAPI service for document processing

   - Port: 8001 (default)
   - Main entry: `document_service/main.py`
   - Routes: `document_service/routes/documents.py`

3. **Shared Code** (`shared/`) - Common utilities, models, config

   - Models: `shared/models.py`
   - Config: `shared/config.py`
   - Deduplication: `shared/deduplication.py`

4. **Task Queue** (`tasks/`) - Celery for async processing
   - Celery app: `tasks/celery_app.py`

---

## Architecture

### High-Level Architecture

```
┌─────────────────┐
│  API Gateway    │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼────┐
│Decision│ │Document│
│Service │ │Service │
└───┬───┘ └──┬─────┘
    │        │
    │    ┌───▼────┐
    │    │  OCR   │
    │    │ Service│
    │    └────────┘
    │
┌───▼──────────────┐
│   PostgreSQL     │
│  (with replicas) │
└──────────────────┘
```

### Technology Stack

- **Language**: Python 3.11
- **Framework**: FastAPI (async)
- **Database**: PostgreSQL 14+ (partitioned tables, read replicas)
- **Cache/Queue**: Redis
- **Task Queue**: Celery
- **OCR**: Multi-tier (PyPDF2 → Tesseract → Gemini/Mistral)
- **ML**: scikit-learn (TF-IDF + Logistic Regression)
- **Containerization**: Docker
- **Orchestration**: Kubernetes (planned)

### Key Design Principles

1. **Stateless Services** - All services are horizontally scalable
2. **Separation of Concerns** - Clear boundaries between API, business logic, data
3. **Fault Tolerance** - Circuit breakers, retries, graceful degradation
4. **Security First** - Encryption at rest, PII protection, audit logging
5. **Observability** - Structured JSON logs, metrics, tracing

---

## Key Components

### Decision Service Components

#### Decision Engine (`decision_service/engine/decision_engine.py`)

- **Purpose**: Main orchestrator for claim evaluation
- **Key Method**: `evaluate_claim(claim_id, override_max_benefit=None) -> Decision`
- **Dependencies**: EligibilityEngine, InvoiceParser, RuleEvaluator

#### Eligibility Engine (`decision_service/engine/eligibility.py`)

- **Purpose**: Calculates eligible amounts from invoice line items
- **Key Method**: `calculate(claim, invoice_data) -> eligibility_result`
- **Output**: Approved/ineligible line items, eligible total

#### Invoice Parser (`decision_service/engine/invoice_parser.py`)

- **Purpose**: Extracts structured data from invoice documents
- **Key Method**: `parse_documents(documents) -> invoice_data`
- **Advanced Parser**: `invoice_parser_advanced.py` (handles complex layouts)
- **Supporting**: `amount_extractor.py`, `table_detector.py`, `reconciliation.py`

#### Rule Evaluator (`decision_service/engine/rule_evaluator.py`)

- **Purpose**: Applies business rules to generate final decision
- **Key Method**: `evaluate(claim, eligibility_result, override_max_benefit) -> rule_result`
- **Output**: Status (approve/deny), benefit amount, flags, reasoning

#### Repositories (`decision_service/repositories/`)

- **ClaimRepository**: Data access for claims
- **DocumentRepository**: Data access for documents
- **Pattern**: Currently returns mock data if `DATABASE_URL` not set

### Document Service Components

#### Document Processor (`document_service/processor.py`)

- **Purpose**: Main orchestrator for document processing pipeline
- **Key Method**: `process_document(file_path, claim_id, ...) -> DocumentProcessingResult`
- **Pipeline**: Validation → OCR → Classification → Quality Assessment

#### OCR Service (`document_service/ocr/service.py`)

- **Purpose**: Multi-tier OCR text extraction
- **Tiers**:
  1. Tier 1: PyPDF2/pdfplumber (native PDFs, < 100ms, free)
  2. Tier 2: Tesseract (scanned docs, < 3sec/page, free)
  3. Tier 3: Gemini/Mistral (complex layouts, < 5sec/page, paid)
- **Strategy**: Try Tier 1 → Tier 2 → Tier 3 if confidence < 60%

#### Document Classifier (`document_service/classifier.py`)

- **Purpose**: ML + rule-based document classification
- **Types**: lease, invoice, addendum, unknown, supporting_doc
- **Method**: TF-IDF + Logistic Regression, with rule-based fallback
- **Threshold**: 0.75 confidence for auto-classification

#### Deduplication Service (`shared/deduplication.py`)

- **Purpose**: Prevents duplicate processing using SHA-256 hashes
- **TTL**: 90 days cache retention
- **Strategy**: Hash before processing, return cached results

#### PII Detection Service (`shared/pii_detector.py`)

- **Purpose**: Detects and redacts PII in extracted text
- **Detection Methods**: Pattern-based (regex) and ML-based (spaCy NER)
- **PII Types**: SSN, Phone, Email, Credit Card, Bank Account, Names, Address
- **Redaction Modes**: REDACT, TAG, MASK, NONE
- **Integration**: Automatically detects PII after OCR extraction

#### Language Detector (`shared/language_detector.py`)

- **Purpose**: Detects document language and RTL support
- **RTL Languages**: Arabic, Hebrew, Urdu, Persian, Yiddish
- **Method**: Uses langdetect library
- **Integration**: Detects language before OCR processing

#### SLA Tracker (`shared/sla_tracker.py`)

- **Purpose**: Tracks SLA compliance for processing times
- **Targets**: Average < 5s, P95 < 15s, P99 < 30s, Max < 60s
- **Features**: Per-document-type tracking, violation detection, alerting
- **Integration**: Records processing time after each document

#### Error Budget Tracker (`shared/error_budget_tracker.py`)

- **Purpose**: Tracks error budget for low OCR confidence cases
- **Budget**: < 5% of documents with OCR confidence < 50%
- **Features**: Rolling window (24h), per-tier tracking, auto-escalation
- **Integration**: Records OCR confidence, escalates to Tier 3 when budget exhausted

#### Queue Manager (`shared/queue_manager.py`)

- **Purpose**: Manages processing queue with concurrency and depth limits
- **Features**: Semaphore-based concurrency, rate limiting, queue depth monitoring
- **Limits**: Configurable max workers, queue depth, rate limits per claim/user
- **Integration**: Used by Celery tasks for async processing

---

## Data Models

### Core Models (`shared/models.py`)

#### DocumentProcessingResult

- **Purpose**: Complete result from document processing
- **Key Fields**:
  - `processing_id`: UUID
  - `claim_id`: int
  - `file_metadata`: FileMetadata
  - `best_extraction`: ExtractedText
  - `classification`: DocumentClassification
  - `quality_metrics`: QualityMetrics
  - `requires_manual_review`: bool

#### ExtractedText

- **Fields**: `text`, `confidence`, `tier_used`, `page_wise_text`, `page_wise_confidence`, `redacted_text` (if PII redaction enabled)

#### DocumentClassification

- **Fields**: `document_type` (enum), `confidence`, `feature_scores`, `fallback_used`

#### FileMetadata

- **Fields**: `original_filename`, `file_size_bytes`, `mime_type`, `file_hash` (SHA-256), `page_count`, `is_password_protected`, `is_native_pdf`, `is_scanned`, `pii_detected`

### Database Schema (`database/schema.sql`)

#### Key Tables

**claims**

- Partitioned by `created_at` (yearly partitions)
- Fields: `id`, `claim_tracking_number`, `claim_amount`, `max_benefit`, `status`, `deleted_at` (soft delete)
- Indexes: `claim_tracking_number` (unique), `created_at`, `status`

**claim_documents**

- Fields: `id`, `claim_id`, `file_path`, `extracted_text` (encrypted), `encryption_key_id`, `encryption_iv`, `document_type`, `deleted_at`
- Foreign Key: `claim_id → claims.id` (RESTRICT on delete)

**decisions**

- Fields: `id`, `claim_id`, `status` (approve/deny), `benefit_amount`, `confidence_score`, `reasoning` (JSONB, encrypted), `deleted_at`
- Foreign Key: `claim_id → claims.id` (RESTRICT on delete)

**decision_audit_log**

- Fields: `id`, `claim_id`, `decision_id`, `action`, `old_values`, `new_values` (JSONB, encrypted)
- **No soft delete** (audit trail must persist)

### Critical Database Constraints

1. **Soft Delete**: All tables (except audit logs) have `deleted_at TIMESTAMPTZ NULL`

   - **REQUIRED**: All SELECT queries must filter `WHERE deleted_at IS NULL`
   - Use `soft_delete_claim(claim_id, deleted_by)` function, not DELETE

2. **UTC Timestamps**: All timestamps are `TIMESTAMPTZ` with UTC timezone

   - Use `utc_now()` function in SQL
   - Application must use UTC: `datetime.utcnow()` or `datetime.now(timezone.utc)`

3. **Encryption**: PII fields must be encrypted at application level

   - Encrypted: `extracted_text`, `reasoning`, `adjudication_notes`, audit log values
   - Store: `encryption_key_id`, `encryption_iv`, `encryption_algorithm`
   - Method: AES-256-GCM

4. **Foreign Keys**: Critical FKs use RESTRICT (not CASCADE)
   - Prevents accidental data loss
   - Must soft delete before hard delete

---

## Processing Flows

### Document Processing Flow

```
1. File Upload → Document Service
2. Validation (size, MIME type, virus scan)
3. Format Detection (native PDF vs scanned)
4. OCR Extraction (Tier 1 → Tier 2 → Tier 3 if needed)
5. Quality Assessment (confidence, blank pages)
6. Classification (ML + rules)
7. Store Result → Database
8. Return DocumentProcessingResult
```

### Claim Decision Flow

```
1. POST /api/v1/claims/{tracking_number}/decision
2. Fetch Claim → ClaimRepository
3. Fetch Documents → DocumentRepository
4. Parse Invoices → InvoiceParser
5. Calculate Eligibility → EligibilityEngine
6. Evaluate Rules → RuleEvaluator
7. Create Decision Record → ClaimRepository
8. Return DecisionResponse
```

### Async Processing Flow (Celery)

```
1. POST /api/v1/documents/process (async)
2. Create Celery Task → Redis Queue
3. Worker Picks Up Task
4. Process Document → DocumentProcessor
5. Store Result → Database
6. Send Webhook (if configured)
```

---

## Critical Requirements

### Production Requirements (`docs/CRITICAL_REQUIREMENTS.md`)

1. **Soft Delete**: Never use `DELETE`, always use soft delete functions

   ```python
   # ❌ WRONG
   DELETE FROM claims WHERE id = 123;

   # ✅ CORRECT
   SELECT soft_delete_claim(123, 'user_001');
   ```

2. **UTC Timestamps**: Always use UTC

   ```python
   # ❌ WRONG
   datetime.now()

   # ✅ CORRECT
   datetime.utcnow()  # or datetime.now(timezone.utc)
   ```

3. **Query Filtering**: Always filter deleted records

   ```python
   # ❌ WRONG
   SELECT * FROM claims WHERE id = 123;

   # ✅ CORRECT
   SELECT * FROM claims WHERE id = 123 AND deleted_at IS NULL;
   ```

4. **Encryption**: Encrypt all PII before storing

   ```python
   # Before INSERT
   encrypted_text, key_id, iv = encrypt(text, kms_key)
   INSERT INTO claim_documents (extracted_text, encryption_key_id, encryption_iv)
   VALUES (encrypted_text, key_id, iv);
   ```

5. **Foreign Key Deletes**: Will fail with RESTRICT
   - Must soft delete parent first
   - Use `soft_delete_claim()` which handles cascading soft deletes

### PII Retention Rules

- **Active claims**: Indefinite
- **Completed claims**: 7 years (archive to cold storage)
- **Soft-deleted claims**: 90 days (hard delete after)
- **Audit logs**: 10 years
- **OCR text**: 7 years (encrypted)

### Performance Targets

- **P95 Response Time**: < 3 seconds
- **Throughput**: 1000 decisions/minute peak
- **Database Lookup**: < 10ms
- **Cache Hit Rate**: > 80%
- **Availability**: 99.9% uptime

---

## File Organization

### Directory Structure

```
Corgi/
├── decision_service/          # Decision API Service
│   ├── main.py                # FastAPI app entry point
│   ├── routes/                # API endpoints
│   │   ├── claims.py         # Claim decision endpoints
│   │   └── health.py          # Health checks
│   ├── schemas/               # Request/response schemas
│   │   ├── request.py
│   │   └── response.py
│   ├── engine/                # Business logic
│   │   ├── decision_engine.py # Main orchestrator
│   │   ├── eligibility.py     # Eligibility calculation
│   │   ├── invoice_parser.py  # Invoice parsing
│   │   ├── invoice_parser_advanced.py  # Advanced parsing
│   │   ├── rule_evaluator.py  # Rule evaluation
│   │   ├── amount_extractor.py
│   │   ├── table_detector.py
│   │   └── reconciliation.py
│   └── repositories/          # Data access layer
│       ├── claim_repository.py
│       └── document_repository.py
│
├── document_service/          # Document Processing Service
│   ├── main.py                # FastAPI app entry point
│   ├── routes/                # API endpoints
│   │   ├── documents.py       # Document processing endpoints
│   │   └── health.py          # Health checks
│   ├── processor.py           # Main processing orchestrator
│   ├── classifier.py          # Document classification
│   └── ocr/                    # OCR service
│       └── service.py         # Multi-tier OCR
│
├── shared/                    # Shared code
│   ├── models.py              # Pydantic models
│   ├── config.py              # Configuration
│   ├── deduplication.py       # Deduplication service
│   ├── pii_detector.py        # PII detection & redaction
│   ├── language_detector.py   # Language detection (RTL support)
│   ├── sla_tracker.py         # SLA tracking & compliance
│   ├── error_budget_tracker.py # Error budget tracking
│   └── queue_manager.py        # Queue management & rate limiting
│
├── tasks/                     # Celery tasks
│   └── celery_app.py          # Celery configuration
│
├── database/                   # Database files
│   ├── schema.sql             # Main schema
│   ├── sample_data.sql        # Sample data
│   └── performance_tests.sql  # Performance tests
│
├── migrations/                # Alembic migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_soft_delete_utc_encryption.py
│
├── tests/                     # Test suite
│   ├── test_integration.py
│   ├── test_document_processor.py
│   ├── test_invoice_parser_advanced.py
│   └── ...
│
├── docs/                      # Documentation
│   ├── architecture/          # Architecture docs
│   ├── CRITICAL_REQUIREMENTS.md
│   ├── DATA_DICTIONARY.md
│   └── ...
│
├── docker-compose.yml         # Local development
├── Dockerfile                 # Container image
├── requirements.txt           # Python dependencies
└── README.md                  # Project overview
```

### Key Files to Know

**Configuration**

- `shared/config.py` - All environment variables and config
- `docker-compose.yml` - Local development stack

**Entry Points**

- `decision_service/main.py` - Decision service FastAPI app
- `document_service/main.py` - Document service FastAPI app
- `tasks/celery_app.py` - Celery worker configuration

**Business Logic**

- `decision_service/engine/decision_engine.py` - Main decision orchestrator
- `document_service/processor.py` - Document processing pipeline
- `decision_service/engine/invoice_parser_advanced.py` - Advanced invoice parsing

**Data Access**

- `decision_service/repositories/claim_repository.py` - Claim data access
- `decision_service/repositories/document_repository.py` - Document data access

**Documentation**

- `docs/CRITICAL_REQUIREMENTS.md` - Production requirements (MUST READ)
- `docs/architecture/README.md` - Architecture overview
- `database/schema.sql` - Database schema

---

## Common Patterns

### FastAPI Route Pattern

```python
from fastapi import APIRouter, HTTPException
from decision_service.schemas.response import DecisionResponse

router = APIRouter()

@router.post("/claims/{tracking_number}/decision", response_model=DecisionResponse)
async def create_decision(tracking_number: str):
    try:
        # Business logic here
        result = await some_service.process()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Repository Pattern

```python
class ClaimRepository:
    async def get_claim(self, claim_id: int) -> Optional[dict]:
        # Always filter deleted_at IS NULL
        query = "SELECT * FROM claims WHERE id = $1 AND deleted_at IS NULL"
        # Execute query...
```

### Error Handling Pattern

```python
from shared.models import ProcessingError, ProcessingErrorType

try:
    result = process()
except SomeError as e:
    error = ProcessingError(
        error_type=ProcessingErrorType.SOME_ERROR,
        message=str(e),
        occurred_at=datetime.utcnow()
    )
    result.errors.append(error)
```

### Configuration Pattern

```python
from shared.config import Config

if Config.OCR_TIER3_ENABLED:
    # Use Tier 3 OCR
    result = await tier3_ocr.extract()
```

### Async Processing Pattern

```python
from tasks.celery_app import celery_app

@celery_app.task
def process_document_task(file_path: str, claim_id: int):
    processor = DocumentProcessor()
    return asyncio.run(processor.process_document(Path(file_path), claim_id))
```

---

## Function Signatures

### Decision Service

#### DecisionEngine.evaluate_claim()

**Location**: `decision_service/engine/decision_engine.py`

```python
async def evaluate_claim(
    claim_id: int,
    override_max_benefit: Optional[Decimal] = None
) -> Decision
```

**Parameters**:

- `claim_id` (int): The claim ID to evaluate
- `override_max_benefit` (Optional[Decimal]): Override the maximum benefit amount from claim

**Returns**: `Decision` object with:

- `claim_id`: int
- `proposed_status`: str ("approve" or "deny")
- `proposed_benefit_amount`: Decimal
- `eligible_total`: Decimal
- `invoice_total`: Decimal
- `cap_amount`: Optional[Decimal]
- `approved_line_items`: list[dict] - Each dict has: `description`, `amount`, `reason`
- `ineligible_line_items`: list[dict] - Same structure as approved
- `flags`: dict with keys: `critical`, `warnings`, `info` (each is list[str])
- `missing_data`: dict with keys: `fields` (list[str]), `needs_user_input` (bool)
- `reasoning`: dict - Contains decision reasoning details
- `confidence_score`: float (0.0-100.0)
- `engine_version`: str

**Example**:

```python
engine = DecisionEngine()
decision = await engine.evaluate_claim(claim_id=123, override_max_benefit=Decimal("5000.00"))
```

---

#### EligibilityEngine.calculate()

**Location**: `decision_service/engine/eligibility.py`

```python
async def calculate(
    claim: dict,
    invoice_data: dict
) -> dict
```

**Parameters**:

- `claim` (dict): Claim data with keys like `id`, `claim_amount`, `max_benefit`, `lease_start_date`, etc.
- `invoice_data` (dict): Invoice data with keys:
  - `line_items` (list[dict]): Each dict has `description` (str), `amount` (float/Decimal)
  - `total_amount` (Decimal)
  - `document_count` (int)

**Returns**: dict with:

- `approved_items` (list[dict]): Each dict has `description`, `amount`, `reason`
- `ineligible_items` (list[dict]): Same structure as approved_items
- `eligible_total` (Decimal): Sum of all approved item amounts

**Example**:

```python
eligibility_engine = EligibilityEngine()
result = await eligibility_engine.calculate(claim=claim_data, invoice_data=invoice_data)
```

---

#### InvoiceParser.parse_documents()

**Location**: `decision_service/engine/invoice_parser.py`

```python
async def parse_documents(
    documents: List[dict]
) -> dict
```

**Parameters**:

- `documents` (List[dict]): List of document dicts, each with:
  - `id` (int): Document ID
  - `document_type` (str): Must be "invoice" to be processed
  - `extracted_text` (str): OCR-extracted text from document

**Returns**: dict with:

- `line_items` (list[dict]): Each dict has `description` (str), `amount` (float/Decimal)
- `total_amount` (Decimal): Sum of all line item amounts
- `document_count` (int): Number of invoice documents processed
- `parse_results` (list[dict]): Advanced parsing results (from `invoice_parser_advanced.py`)

**Example**:

```python
parser = InvoiceParser()
invoice_data = await parser.parse_documents(documents=document_list)
```

---

#### AdvancedInvoiceParser.parse_invoice()

**Location**: `decision_service/engine/invoice_parser_advanced.py`

```python
def parse_invoice(
    extracted_text: str,
    document_id: Optional[int] = None,
    claim_context: Optional[Dict] = None
) -> InvoiceParseResult
```

**Parameters**:

- `extracted_text` (str): Raw OCR text from invoice document
- `document_id` (Optional[int]): Document ID for logging/tracking
- `claim_context` (Optional[Dict]): Additional context about the claim

**Returns**: `InvoiceParseResult` object (see `invoice_models.py`) with:

- `line_items` (List[LineItem]): Structured line items with confidence scores
- `metadata` (InvoiceMetadata): Invoice metadata (totals, dates, etc.)
- `quality_metrics` (ParsingQualityMetrics): Quality assessment
- `reconciliation` (dict): Total reconciliation results

**Example**:

```python
parser = AdvancedInvoiceParser()
result = parser.parse_invoice(extracted_text="INVOICE\nItem 1: $500.00...", document_id=1)
```

---

#### RuleEvaluator.evaluate()

**Location**: `decision_service/engine/rule_evaluator.py`

```python
async def evaluate(
    claim: dict,
    eligibility_result: dict,
    override_max_benefit: Optional[Decimal] = None
) -> dict
```

**Parameters**:

- `claim` (dict): Claim data dictionary
- `eligibility_result` (dict): Output from `EligibilityEngine.calculate()` with keys:
  - `eligible_total` (Decimal)
  - `approved_items` (list)
  - `ineligible_items` (list)
- `override_max_benefit` (Optional[Decimal]): Override maximum benefit

**Returns**: dict with:

- `status` (str): "approve" or "deny"
- `benefit_amount` (Decimal): Final benefit amount (capped by max_benefit)
- `flags` (dict): `{"critical": [], "warnings": [], "info": []}`
- `missing_data` (dict): `{"fields": [], "needs_user_input": bool}`
- `reasoning` (dict): Decision reasoning details
- `confidence` (float): 0.0-100.0

**Example**:

```python
evaluator = RuleEvaluator()
rule_result = await evaluator.evaluate(
    claim=claim_data,
    eligibility_result=eligibility_result,
    override_max_benefit=Decimal("5000.00")
)
```

---

#### ClaimRepository.get_claim()

**Location**: `decision_service/repositories/claim_repository.py`

```python
async def get_claim(claim_id: int) -> Optional[dict]
```

**Parameters**:

- `claim_id` (int): Claim ID to retrieve

**Returns**: Optional[dict] with keys:

- `id` (int)
- `claim_tracking_number` (str)
- `claim_amount` (float)
- `max_benefit` (float)
- `lease_start_date` (str, ISO date format)
- `lease_end_date` (str, optional)
- `move_out_date` (str, optional)
- `status` (str)
- Other claim fields

**Note**: Returns `None` if claim not found. Returns mock data if `DATABASE_URL` not configured.

---

#### ClaimRepository.get_claim_by_tracking_number()

**Location**: `decision_service/repositories/claim_repository.py`

```python
async def get_claim_by_tracking_number(tracking_number: str) -> Optional[dict]
```

**Parameters**:

- `tracking_number` (str): Claim tracking number (e.g., "CLM-2024-000123")

**Returns**: Same structure as `get_claim()`

---

#### ClaimRepository.create_decision()

**Location**: `decision_service/repositories/claim_repository.py`

```python
async def create_decision(decision: Decision, user_id: str) -> dict
```

**Parameters**:

- `decision` (Decision): Decision object from `DecisionEngine.evaluate_claim()`
- `user_id` (str): User ID who created the decision

**Returns**: dict with decision record fields:

- `id` (int): Decision record ID
- `claim_id` (int)
- `tracking_number` (str)
- `decision_type` (str): "automated", "manual_override", etc.
- `proposed_status` (str)
- `proposed_benefit_amount` (float)
- `eligible_total` (float)
- `invoice_total` (float)
- `cap_amount` (float, optional)
- `approved_line_items` (list)
- `ineligible_line_items` (list)
- `flags` (dict)
- `missing_data` (dict)
- `reasoning` (dict)
- `confidence_score` (float)
- `engine_version` (str)
- `decided_at` (datetime)

---

#### DocumentRepository.get_documents()

**Location**: `decision_service/repositories/document_repository.py`

```python
async def get_documents(claim_id: int) -> List[dict]
```

**Parameters**:

- `claim_id` (int): Claim ID

**Returns**: List[dict], each dict has:

- `id` (int): Document ID
- `claim_id` (int)
- `document_type` (str): "lease", "invoice", "addendum", etc.
- `extracted_text` (str): OCR-extracted text (may be encrypted)
- `file_path` (str): Path to document file

**Note**: Returns empty list if no documents found. Returns mock data if `DATABASE_URL` not configured.

---

### Document Service

#### DocumentProcessor.process_document()

**Location**: `document_service/processor.py`

```python
async def process_document(
    file_path: Path,
    claim_id: int,
    processing_priority: int = 0,
    force_high_quality: bool = False,
) -> DocumentProcessingResult
```

**Parameters**:

- `file_path` (Path): Path to document file (PDF, image, etc.)
- `claim_id` (int): Associated claim ID
- `processing_priority` (int): Processing priority (higher = more urgent), default 0
- `force_high_quality` (bool): Skip to Tier 3 OCR, default False

**Returns**: `DocumentProcessingResult` (dataclass) with:

- `processing_id` (str): UUID
- `claim_id` (int)
- `file_metadata` (FileMetadata): File info (filename, size, hash, page_count, etc.)
- `extraction_attempts` (List[ExtractionAttempt]): All OCR attempts
- `best_extraction` (ExtractedText): Best OCR result with:
  - `text` (str): Extracted text
  - `confidence` (float): 0.0-100.0
  - `tier_used` (OCRTier): Which OCR tier was used
  - `page_wise_text` (List[str])
  - `page_wise_confidence` (List[float])
- `classification` (DocumentClassification): Document type classification
- `quality_metrics` (QualityMetrics): Quality assessment
- `processing_metrics` (ProcessingMetrics): Processing stats
- `errors` (List[ProcessingError]): Any errors encountered
- `requires_manual_review` (bool): Whether manual review needed
- `manual_review_reasons` (List[str]): Reasons for manual review
- `cost_breakdown` (CostBreakdown): Cost information
- `created_at` (datetime)

**Example**:

```python
processor = DocumentProcessor()
result = await processor.process_document(
    file_path=Path("invoice.pdf"),
    claim_id=123,
    processing_priority=1,
    force_high_quality=False
)
```

---

#### DocumentClassifier.classify()

**Location**: `document_service/classifier.py`

```python
def classify(
    extracted_text: ExtractedText,
    page_count: int,
    ocr_confidence: float,
) -> DocumentClassification
```

**Parameters**:

- `extracted_text` (ExtractedText): OCR extraction result with `text` and `confidence`
- `page_count` (int): Number of pages in document
- `ocr_confidence` (float): OCR confidence score (0.0-100.0)

**Returns**: `DocumentClassification` with:

- `document_type` (DocumentType enum): "lease", "invoice", "addendum", "unknown", "supporting_doc"
- `confidence` (float): 0.0-1.0 classification confidence
- `feature_scores` (FeatureScores): Individual feature scores
- `fallback_used` (bool): Whether rule-based fallback was used
- `ml_probabilities` (dict): ML model probabilities for each type

**Example**:

```python
classifier = DocumentClassifier()
classification = classifier.classify(
    extracted_text=extracted_text_obj,
    page_count=3,
    ocr_confidence=87.5
)
```

---

#### OCRService.extract_text()

**Location**: `document_service/ocr/service.py`

```python
def extract_text(
    file_path: Path,
    is_native_pdf: bool = False,
    force_high_quality: bool = False,
) -> Tuple[Optional[str], float, OCRTier, int, float]
```

**Parameters**:

- `file_path` (Path): Path to document file
- `is_native_pdf` (bool): Whether PDF is native (text-based) vs scanned
- `force_high_quality` (bool): Skip to Tier 3 OCR

**Returns**: Tuple of:

- `extracted_text` (Optional[str]): Extracted text, None if failed
- `confidence` (float): 0.0-100.0 confidence score
- `tier_used` (OCRTier): Which OCR tier was used
- `processing_time_ms` (int): Processing time in milliseconds
- `cost` (float): Cost in USD (0.0 for Tier 1/2, >0 for Tier 3)

**Example**:

```python
ocr_service = OCRService()
text, confidence, tier, time_ms, cost = ocr_service.extract_text(
    file_path=Path("document.pdf"),
    is_native_pdf=True,
    force_high_quality=False
)
```

---

#### OCRService.extract_with_attempts()

**Location**: `document_service/ocr/service.py`

```python
def extract_with_attempts(
    file_path: Path,
    is_native_pdf: bool = False,
    force_high_quality: bool = False,
) -> Tuple[List[ExtractionAttempt], Optional[ExtractionAttempt]]
```

**Parameters**:

- `file_path` (Path): Path to document file
- `is_native_pdf` (bool): Whether PDF is native vs scanned
- `force_high_quality` (bool): Skip to Tier 3 OCR

**Returns**: Tuple of:

- `extraction_attempts` (List[ExtractionAttempt]): All OCR attempts made
- `best_attempt` (Optional[ExtractionAttempt]): Best result, None if all failed

**Note**: This method tries Tier 1 → Tier 2 → Tier 3 if confidence < 60%

---

### API Endpoints

#### POST /api/v1/claims/{tracking_number}/decision

**Location**: `decision_service/routes/claims.py`

**Path Parameters**:

- `tracking_number` (str): Claim tracking number

**Request Body** (optional):

```json
{
  "override_max_benefit": 5000.0 // Optional, float
}
```

**Headers**:

- `X-Request-ID` (optional): Request ID for tracing
- `X-Idempotency-Key` (optional): Idempotency key

**Response**: `DecisionResponse` (200 OK) with:

- `decision_id` (int)
- `claim_id` (int)
- `tracking_number` (str)
- `decision_type` (str)
- `proposed_status` (str): "approve" or "deny"
- `proposed_benefit_amount` (float)
- `eligible_total` (float)
- `invoice_total` (float)
- `cap_amount` (float, optional)
- `approved_line_items` (List[LineItem])
- `ineligible_line_items` (List[LineItem])
- `flags` (Flags)
- `missing_data` (MissingData)
- `reasoning` (dict)
- `confidence_score` (float)
- `engine_version` (str)
- `processing_time_ms` (int, optional)
- `decided_at` (datetime)

**Errors**:

- `400`: Bad request (missing tracking number)
- `404`: Claim not found
- `500`: Internal server error

---

#### POST /api/v1/documents/process

**Location**: `document_service/routes/documents.py`

**Form Data**:

- `file` (UploadFile): Document file (PDF, image, etc.)
- `claim_id` (int): Associated claim ID (required)
- `processing_priority` (int): Processing priority, default 0
- `force_high_quality` (bool): Force Tier 3 OCR, default false

**Response**: `DocumentProcessingResult` as JSON (200 OK) - see `DocumentProcessor.process_document()` return type

**Errors**:

- `400`: Bad request (missing claim_id)
- `500`: Processing error

---

#### GET /api/v1/claims/{tracking_number}/documents

**Location**: `decision_service/routes/claims.py`

**Path Parameters**:

- `tracking_number` (str): Claim tracking number

**Response**: List[dict] (200 OK) with document records:

- `document_id` (int)
- `claim_id` (int)
- `file_path` (str)
- `original_filename` (str)
- `file_hash` (str)
- `file_size_bytes` (int)
- `mime_type` (str)
- `document_type` (str)
- `classification_confidence` (float)
- `page_count` (int)
- `processing_status` (str)
- `created_at` (str, ISO datetime)

**Errors**:

- `404`: Claim not found

---

## Development Guidelines

### Code Style

- **No non-human comments**: Only add comments that are critical for human understanding
- **Production-ready code**: All code must be complete, no TODOs or placeholders
- **Type hints**: Use type hints for all function parameters and returns
- **Async/await**: Use async/await for I/O operations

### Testing

- **Location**: `tests/` directory
- **Run tests**: `pytest tests/ -v`
- **Coverage**: `pytest tests/ --cov=. --cov-report=html`
- **Test files**: Mirror source structure (e.g., `test_document_processor.py`)

### Environment Variables

Key environment variables (see `shared/config.py`):

```bash
# OCR Configuration
OCR_TIER1_ENABLED=true
OCR_TIER2_ENABLED=true
OCR_TIER3_ENABLED=false
OCR_CONFIDENCE_THRESHOLD=60

# Classification
CLASSIFICATION_CONFIDENCE_THRESHOLD=0.75

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/corgi

# Redis
REDIS_URL=redis://localhost:6379/0

# Tier 3 OCR
TIER3_PROVIDER=gemini  # or mistral
GEMINI_API_KEY=your_key
MISTRAL_API_KEY=your_key

# Concurrency & Queue
MAX_CONCURRENT_WORKERS=10
MAX_QUEUE_DEPTH=1000
QUEUE_WARNING_THRESHOLD=800
RATE_LIMIT_PER_CLAIM=10
RATE_LIMIT_PER_USER=100

# SLA Configuration
SLA_TARGET_AVG_MS=5000
SLA_TARGET_P95_MS=15000
SLA_TARGET_P99_MS=30000
SLA_TARGET_MAX_MS=60000
SLA_ALERT_THRESHOLD=0.05

# PII Detection
PII_DETECTION_ENABLED=true
PII_REDACTION_MODE=REDACT  # REDACT, TAG, MASK, NONE
PII_USE_ML_MODEL=false

# Error Budget
OCR_ERROR_BUDGET_PERCENTAGE=0.05
OCR_LOW_CONFIDENCE_THRESHOLD=50.0
ERROR_BUDGET_WINDOW_HOURS=24
ERROR_BUDGET_ALERT_THRESHOLD=0.80

# Language Detection
LANGUAGE_DETECTION_ENABLED=true
RTL_LANGUAGE_SUPPORT=true
```

### Running Services Locally

```bash
# Decision Service
uvicorn decision_service.main:app --reload --port 8000

# Document Service
uvicorn document_service.main:app --reload --port 8001

# Celery Worker
celery -A tasks.celery_app worker --loglevel=info

# Docker Compose (all services)
docker-compose up
```

### Database Migrations

- **Location**: `migrations/versions/`
- **Tool**: Alembic
- **Key migrations**:
  - `001_initial_schema.py` - Initial schema
  - `002_soft_delete_utc_encryption.py` - Soft delete, UTC, encryption metadata

---

## Quick Reference

### Common Tasks

**Add a new API endpoint**

1. Add route in `decision_service/routes/claims.py` or `document_service/routes/documents.py`
2. Add schema in `decision_service/schemas/request.py` or `response.py`
3. Implement business logic in appropriate engine/service
4. Add tests in `tests/`

**Add a new business rule**

1. Modify `decision_service/engine/rule_evaluator.py`
2. Update version number in `rule_evaluator.py`
3. Add tests

**Add a new document type**

1. Add enum value to `DocumentType` in `shared/models.py`
2. Update classifier in `document_service/classifier.py`
3. Update database enum in `database/schema.sql`

**Process a document**

```python
from document_service.processor import DocumentProcessor
from pathlib import Path

processor = DocumentProcessor()
result = await processor.process_document(
    file_path=Path("document.pdf"),
    claim_id=123,
    processing_priority=0,
    force_high_quality=False
)
```

**Evaluate a claim**

```python
from decision_service.engine.decision_engine import DecisionEngine

engine = DecisionEngine()
decision = await engine.evaluate_claim(claim_id=123)
```

### Important Gotchas

1. **Soft Delete**: Never use `DELETE`, always soft delete
2. **UTC Timestamps**: Always use UTC, never local time
3. **Query Filtering**: Always filter `deleted_at IS NULL`
4. **Encryption**: Encrypt PII before storing (application-level)
5. **Foreign Keys**: RESTRICT prevents cascading deletes
6. **Repository Pattern**: Currently returns mock data if `DATABASE_URL` not set
7. **OCR Tiers**: Automatically escalates if confidence < 60%
8. **Classification**: Uses ML first, falls back to rules if confidence < 0.75
9. **PII Detection**: Automatically enabled, redacts PII if detected
10. **Error Budget**: Auto-escalates to Tier 3 when budget exhausted
11. **Queue Limits**: Requests rejected if queue depth exceeds limit
12. **SLA Tracking**: Processing times tracked automatically, violations logged
13. **RTL Languages**: Language detected automatically, RTL flag set in metadata

### Key Constants

- **OCR Confidence Threshold**: 60% (escalates to next tier if below)
- **Classification Confidence Threshold**: 0.75 (auto-classify if above)
- **Deduplication TTL**: 90 days
- **Max File Size**: 50 MB
- **Processing Timeout**: 60 seconds
- **Tier 1 Timeout**: 100ms
- **Tier 2 Timeout**: 3000ms
- **Tier 3 Timeout**: 5000ms
- **SLA Targets**: Avg < 5s, P95 < 15s, P99 < 30s, Max < 60s
- **Error Budget**: < 5% low OCR confidence (24h window)
- **Max Concurrent Workers**: 10 (configurable)
- **Max Queue Depth**: 1000 (configurable)
- **Rate Limit**: 10 docs/min per claim, 100 docs/min per user

### Useful Commands

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Start services
docker-compose up

# Check database schema
psql $DATABASE_URL -c "\d claims.claims"

# View logs
docker-compose logs -f decision-service
```

---

## Additional Resources

- **Architecture Docs**: `docs/architecture/README.md`
- **Critical Requirements**: `docs/CRITICAL_REQUIREMENTS.md`
- **Data Dictionary**: `docs/DATA_DICTIONARY.md`
- **API Spec**: `docs/architecture/openapi.yaml`
- **Main README**: `README.md`
- **Enhancement Plan**: `docs/ENHANCEMENT_PLAN.md`

---

## Enhancement Features (Production Resilience)

### New Services

1. **Queue Manager** (`shared/queue_manager.py`)

   - Maximum parallelism control (semaphore-based)
   - Queue depth limits with warnings
   - Rate limiting per claim and per user (token bucket algorithm)
   - Metrics tracking (depth, wait times, rejections)
   - Usage: `await queue_manager.acquire(claim_id=123, user_id="user_001")`

2. **SLA Tracker** (`shared/sla_tracker.py`)

   - Real-time SLA tracking (avg, P95, P99, max)
   - Per-document-type metrics
   - Violation detection and alerting
   - Compliance percentage calculation
   - Usage: `sla_tracker.record_processing_time(processing_time_ms=4500, document_type="invoice")`

3. **PII Detection & Redaction** (`shared/pii_detector.py`)

   - Pattern-based detection (SSN, phone, email, credit card, bank account)
   - ML-based detection (spaCy NER for names) - optional
   - Multiple redaction modes (REDACT, TAG, MASK, NONE)
   - Automatic detection after OCR extraction
   - Usage: `pii_detector.detect(text)` → `pii_redactor.redact(text, detections)`

4. **Error Budget Tracker** (`shared/error_budget_tracker.py`)

   - Tracks low OCR confidence cases (< 50%)
   - 24-hour rolling window
   - Per-tier tracking
   - Auto-escalation to Tier 3 when budget exhausted
   - Usage: `error_budget_tracker.record_document(confidence=45.0, tier="tier2")`

5. **Language Detector** (`shared/language_detector.py`)
   - Automatic language detection (langdetect)
   - RTL language identification (Arabic, Hebrew, Urdu, Persian, Yiddish)
   - Language metadata in FileMetadata
   - Usage: `language_detector.detect_language(text)` → `(language_code, confidence, is_rtl)`

### Integration

All enhancement features are automatically integrated into `DocumentProcessor`:

- PII detection runs after OCR extraction
- Language detection runs after OCR extraction
- SLA tracking records processing time automatically
- Error budget tracking records OCR confidence automatically
- Error budget exhaustion triggers Tier 3 escalation

### Configuration

All features are configurable via environment variables (see `shared/config.py`):

- Queue limits: `MAX_CONCURRENT_WORKERS`, `MAX_QUEUE_DEPTH`, `RATE_LIMIT_PER_CLAIM`
- SLA targets: `SLA_TARGET_AVG_MS`, `SLA_TARGET_P95_MS`, etc.
- PII: `PII_DETECTION_ENABLED`, `PII_REDACTION_MODE`, `PII_USE_ML_MODEL`
- Error budget: `OCR_ERROR_BUDGET_PERCENTAGE`, `OCR_LOW_CONFIDENCE_THRESHOLD`
- Language: `LANGUAGE_DETECTION_ENABLED`, `RTL_LANGUAGE_SUPPORT`

---

**Last Updated**: 2024-01-20  
**Version**: 2.0.0
