# Code Review Overview - Security Deposit Claims Decision Engine

## System Purpose

**Security Deposit Claims Decision Engine** - An enterprise-grade system that:

- Processes security deposit claim documents (PDFs, images) using multi-tier OCR
- Classifies documents (lease, invoice, addendum, etc.) using ML + rules
- Parses invoices to extract line items and amounts using Gemini 2.5 Pro/Flash
- Evaluates claim eligibility based on business rules
- Generates automated decisions (approve/deny) with confidence scores
- Handles high-volume processing (target: 5,000 claims/hour)
- Provides web-based UI for manual review and override of decisions
- Integrates with Google Drive for document processing

## Architecture

### Services

1. **Decision Service** (`decision_service/`)

   - FastAPI service on port 8000
   - Main entry: `decision_service/main.py`
   - Routes: `decision_service/routes/claims.py`, `decision_service/routes/batch.py`
   - Core engine: `decision_service/engine/decision_engine.py`
   - Database connection pooling for optimized performance

2. **Document Service** (`document_service/`)

   - FastAPI service on port 8001
   - OCR processing with multi-tier strategy
   - Document classification
   - Parallel processing support

3. **Frontend** (`frontend/`)

   - Next.js 14+ with TypeScript
   - React components for decision review and override
   - Real-time total calculation
   - Cap management UI
   - Status override functionality
   - Automatic Google Drive processing integration

4. **Shared Code** (`shared/`)
   - Models: `shared/models.py`
   - Config: `shared/config.py`
   - Utilities: deduplication, PII detection, error tracking
   - Google Drive integration: `shared/google_drive.py`

### Technology Stack

- **Language**: Python 3.11 (backend), TypeScript (frontend)
- **Framework**: FastAPI (async backend), Next.js 14+ (frontend)
- **Database**: PostgreSQL 14+ (with connection pooling)
- **Cache/Queue**: Redis + Celery
- **OCR**: Multi-tier (PyPDF2 → Tesseract → Gemini/Mistral)
- **ML**: scikit-learn (TF-IDF + Logistic Regression)
- **AI**: Google Gemini 2.5 Pro/Flash for document analysis
- **Storage**: Google Drive API for document retrieval

## Key API Endpoints

### Decision Service

#### Claim Decision Endpoints

- `POST /api/v1/claims/{tracking_number}/decision` - Generate new decision for a claim (re-runs decision engine)
- `GET /api/v1/claims/{tracking_number}/decision` - Get latest decision for a claim (fast, no re-processing)
- `PATCH /api/v1/claims/{tracking_number}/decision/{decision_id}` - Update decision with user overrides
  - Supports line item overrides (approve/ineligible)
  - Supports cap amount override
  - Supports status override (deny → approve)
  - Saves overrides to `user_line_item_overrides` table for rule refinement

#### Document Processing Endpoints

- `POST /api/v1/claims/process-from-drive` - Process claim from Google Drive

  - Automatically creates claim if it doesn't exist
  - Downloads and processes documents in parallel (up to 3 concurrent)
  - Runs decision engine and returns result
  - Optimized with parallel Gemini API calls

- `GET /api/v1/claims/{tracking_number}/documents` - Get claim documents (with optional type filter)

#### Batch Processing Endpoints

- `POST /api/v1/batch/evaluate` - Submit batch evaluation job (async, returns batch_id)
- `GET /api/v1/batch/{batch_id}/status` - Get batch job status and progress

#### Health Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness check

### Document Service

- `POST /api/v1/documents/process` - Process document (OCR + classification)
- `GET /health` - Health check

## Core Decision Flow

```
1. API receives claim request
   ↓
2. DecisionEngine.evaluate_claim(claim_id)
   ↓
3. Fetch claim data and documents from database
   ↓
4. DocumentAnalyzer.analyze_all_documents() - Batch analyze with Gemini
   ↓
5. DocumentAnalyzer.extract_line_items_from_invoice() - Extract line items
   ↓
6. DocumentAnalyzer.analyze_line_items_batch() - Analyze eligibility with Gemini
   ↓
7. EligibilityEngine.calculate() - Calculate eligible totals
   ↓
8. RuleEvaluator.evaluate() - Apply business rules and caps
   ↓
9. Create Decision object and save to database
```

## User Override System

### Frontend Features

- **Line Item Toggle**: Users can include/exclude individual line items
- **Live Total Calculation**: Real-time approved amount updates as items are toggled
- **Cap Management**:
  - Toggle cap on/off
  - Override cap amount with custom value
  - Display cap reason (claim_amount, max_benefit, invoice_total)
- **Status Override**: Override denied decisions to approved
- **Change Tracking**: Visual indicators for modified items
- **Notes**: Optional notes for each line item override

### Backend Override Storage

- **`user_line_item_overrides` table**: Stores detailed override information
  - Line item index and description
  - System vs user decision
  - User reasoning
  - Timestamp
- **Decision updates**: Updates `decisions` table with new line items and totals
- **Decision type**: Set to `'reconsideration'` for manual overrides

## Google Drive Integration

### Features

- **Automatic Processing**: Frontend automatically processes from Google Drive if claim not found
- **Parallel Downloads**: Downloads up to 3 documents concurrently
- **Parallel Processing**: Processes documents in parallel with Gemini API
- **Subfolder Detection**: Automatically finds subfolder matching tracking number
- **Document Deduplication**: Uses file hash to prevent duplicate processing

### Configuration

- Service account credentials: `google-drive-credentials.json`
- Default folder ID configured in frontend
- Supports both folder URLs and folder IDs

## Key Components

### Decision Engine (`decision_service/engine/decision_engine.py`)

- Main orchestrator for claim evaluation
- Coordinates: DocumentAnalyzer, EligibilityEngine, RuleEvaluator
- Handles document analysis, line item extraction, and final decision creation
- Fallback to invoice parser if Gemini extraction fails

### Document Analyzer (`decision_service/engine/document_analyzer.py`)

- **Critical**: Contains Gemini prompts that define approval/denial logic
- Batch analyzes documents for denial reasons
- Extracts line items from invoices/statements
- Analyzes line items for eligibility flags
- Key flags: `should_be_included`, `is_normal_wear_tear`, `is_covered_by_addendum`

### JSON Validator (`decision_service/engine/json_validator.py`)

- Validates Gemini's JSON responses
- Handles markdown-wrapped responses
- Retry logic for invalid responses
- Type and range validation

### Rule Evaluator (`decision_service/engine/rule_evaluator.py`)

- Applies business rules from PRD
- Calculates caps (claim_amount, max_benefit, invoice_total)
- Determines approve/deny status
- Monotonicity requirement: increasing max_benefit must never decrease proposed_benefit

### Eligibility Engine (`decision_service/engine/eligibility.py`)

- Processes approved/ineligible line items
- Calculates eligible_total
- Handles credits and adjustments

### Repositories

- **ClaimRepository** (`decision_service/repositories/claim_repository.py`)

  - Connection pooling for database queries
  - Cached engine instance for performance
  - Methods: `get_claim`, `get_claim_by_tracking_number`, `get_latest_decision_by_tracking_number`, `create_claim`, `create_decision`

- **OverrideRepository** (`decision_service/repositories/override_repository.py`)

  - Saves user line item overrides
  - Retrieves override history for analysis

- **DocumentRepository** (`decision_service/repositories/document_repository.py`)

  - Document retrieval with type filtering

- **BatchRepository** (`decision_service/repositories/batch_repository.py`)
  - Batch job management
  - Status tracking

## Business Rules (from PRD)

### Decision Rules

- Missing addendum → DENY, benefit = 0
- Missing invoice → DENY, benefit = 0
- Missing max_benefit → DENY, benefit = 0
- Claim amount = 0 → APPROVE, benefit = 0
- Eligible total = 0 → DENY
- Otherwise → APPROVE, compute benefit

### Benefit Calculation

```
cap_amount = min(claim_amount, max_benefit, invoice_total)
proposed_benefit = min(eligible_total, cap_amount)
```

### Cap Reason Logic

- `claim_amount`: Limited by claim amount
- `max_benefit`: Limited by max benefit
- `invoice_total`: Limited by invoice total
- `claim_amount_and_max_benefit`: Limited by both claim amount and max benefit
- `user_override`: User-specified cap amount

### Eligibility Policy

**Eligible**: cleaning, trash removal, damage beyond normal wear, fixture repair
**Ineligible**: normal wear and tear, upgrades, routine maintenance, utilities (unless unpaid), late fees (unless covered), rent charges

## Performance Optimizations

### Database

- **Connection Pooling**: Cached engine with pool_size=5, max_overflow=10
- **Pool Pre-ping**: Ensures connections are alive
- **Pool Recycle**: Recycles connections after 1 hour
- **Query Performance**: Optimized SELECT queries, removed unnecessary columns

### Google Drive & Gemini

- **Parallel Downloads**: Up to 3 concurrent document downloads
- **Parallel Processing**: Up to 3 concurrent document processing tasks
- **Batch API Calls**: Gemini calls happen concurrently across documents
- **Expected Speedup**: 2-3x faster than sequential processing

### Frontend

- **Fast Decision Retrieval**: GET endpoint for existing decisions (no re-processing)
- **Automatic Fallback**: Auto-processes from Google Drive if claim not found
- **Loading States**: Clear feedback during processing

## Data Models

### Key Models (`shared/models.py`)

- `DocumentType` enum: ADDENDUM, INVOICE, LEASE, UNKNOWN, SUPPORTING_DOC
- `EligibilityStatus` enum
- `ExtractedText` - OCR results
- `DocumentProcessingResult` - Processing results

### Database Tables

- `claims` - Claim data (claim_amount, max_benefit, claim_date, etc.)
- `claim_documents` - Document metadata and extracted text
- `decisions` - Proposed decisions
  - Columns: id, claim_id, decision_type, proposed_status, proposed_benefit_amount, eligible_total, invoice_total, cap_amount, approved_line_items, ineligible_line_items, flags, missing_data, reasoning, confidence_score, engine_version, processing_time_ms, decided_by, decided_at, is_active
  - Decision type enum: 'initial', 'appeal', 'reconsideration'
  - Decision status enum: 'approve', 'deny'
- `user_line_item_overrides` - User override history for rule refinement
- `decision_validation` - Actual decisions (for evaluation)
- `processing_queue` - Batch processing queue

### Frontend Types (`frontend/lib/api.ts`)

- `DecisionResponse` - Complete decision data with line items
- `LineItem` - Individual line item with description, amount, reason
- `LineItemOverride` - Override specification
- `UpdateDecisionRequest` - Request for updating decision
- `ProcessFromDriveRequest` - Request for Google Drive processing

## Configuration

### Environment Variables (see `env.example`)

- `GEMINI_API_KEY` - Required for document analysis
- `GEMINI_MODEL` - gemini-2.5-flash or gemini-2.5-pro
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection for Celery
- `GOOGLE_DRIVE_CREDENTIALS` - Path to service account credentials JSON
- OCR tier configuration (TIER1_ENABLED, TIER2_ENABLED, TIER3_ENABLED)

### Frontend Configuration

- `NEXT_PUBLIC_API_URL` - Backend API URL (default: http://localhost:8000/api/v1)
- Default Google Drive folder ID configured in `DecisionViewer.tsx`

## Testing

### Test Files (`tests/`)

- `test_integration.py` - Integration tests
- `test_eligibility_classifier.py` - Eligibility tests
- `test_document_processor.py` - Document processing tests
- `test_invoice_parser_advanced.py` - Invoice parsing tests
- Phase tests: `test_phase1_phase2.py`, `test_phase3.py`, `test_phase4.py`, `test_phase5_integration.py`

### Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html
```

## Performance Requirements

- **Latency**: Target < 3 seconds per claim, hard timeout 10 seconds
- **Throughput**: 5,000 claims per hour on typical instance
- **Determinism**: Identical input and engine version must produce identical output
- **Retry**: Two retries on OCR/parsing errors
- **Database Queries**: < 10ms for existing decisions (with connection pooling)

## Security & Compliance

- PII detection and redaction (names, phone numbers, addresses, SSN)
- Document retention policy (configurable by days)
- Hashed file deduplication
- Role-based access control (planned)
- Full audit trail of overrides and reviews
- Google Drive service account authentication

## Key Files for Code Review

### Critical Files

1. **`decision_service/engine/document_analyzer.py`** (Lines 250-350)

   - Contains Gemini prompts that define approval/denial logic
   - Auto-denial logic (rent, improper notice, other insurance)
   - Normal wear/tear detection

2. **`decision_service/engine/decision_engine.py`** (Lines 88-280)

   - Document analysis override logic
   - Line item extraction and analysis
   - Final decision creation

3. **`decision_service/routes/claims.py`**

   - `update_decision`: User override handling
   - `process_claim_from_drive`: Google Drive integration with parallel processing
   - `get_decision`: Fast decision retrieval

4. **`decision_service/engine/rule_evaluator.py`**

   - Cap calculation (claim_amount, max_benefit, invoice_total)
   - Final benefit amount calculation
   - Business rule enforcement

5. **`decision_service/repositories/claim_repository.py`**

   - Connection pooling implementation
   - Optimized query methods

6. **`frontend/app/components/DecisionViewer.tsx`**

   - Main UI component
   - Line item toggle logic
   - Cap management
   - Status override
   - Google Drive auto-processing

7. **`shared/google_drive.py`**

   - Google Drive API integration
   - File download and folder traversal

### Documentation Files

- `README.md` - Main entry point
- `docs/PRD.md` - Product requirements
- `docs/STRUCTURE.md` - Architecture overview
- `docs/DECISION_PROCESS_FILES.md` - Decision flow explanation
- `docs/ISSUE_ANALYSIS.md` - Known issues analysis
- `docs/AGENT_ONBOARDING.md` - Comprehensive onboarding guide
- `docs/USER_OVERRIDE_SYSTEM.md` - User override system documentation
- `rules/RULES_GUIDE.md` - Business rules documentation
- `docs/architecture/` - Architecture Decision Records (ADRs) and C4 diagrams
- `frontend/README.md` - Frontend setup and usage

## Running the System

### Local Development

#### Backend

```bash
# Decision Service
cd /Users/geddydukes/Desktop/Corgi
python3.11 -m uvicorn decision_service.main:app --host 0.0.0.0 --port 8000 --reload

# Document Service
uvicorn document_service.main:app --reload --port 8001
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:3000
```

#### Using Docker Compose

```bash
docker-compose up
```

### Scripts

- `scripts/run_decisions_first_5.py` - Run decisions on claims 900-904
- `scripts/generate_variance_report.py` - Generate variance reports
- `scripts/clear_decisions.py` - Clear decisions for a range of claims

## Frontend Usage

1. **Search for Claim**: Enter tracking number and click "Search"
2. **Auto-Processing**: If claim not found, automatically processes from Google Drive
3. **Review Decision**: View decision summary, line items, and flags
4. **Toggle Line Items**: Click to include/exclude items, see live total update
5. **Manage Cap**: Toggle cap on/off, override cap amount
6. **Override Status**: Click "Override to Approve" for denied claims
7. **Add Notes**: Optional notes for each line item change
8. **Save Changes**: Submit all overrides to database

## Evaluation Metrics

- Status accuracy (approve/deny)
- Mean Absolute Error (MAE) for amounts
- False denial rate
- Systematic bias direction
- Cap-driven vs eligibility-driven changes
- User override patterns (for rule refinement)

## Versioning

- Semantic versioning: `rules_vMAJOR.MINOR.PATCH`
- Every decision stamped with ruleset version
- Ability to rerun decisions under newer rules for comparison

## Recent Updates

- Added frontend UI for decision review and override
- Implemented Google Drive integration with parallel processing
- Added status override functionality (deny → approve)
- Optimized database queries with connection pooling
- Added cap management (toggle, override amount, reason display)
- Implemented user override storage for rule refinement
- Added automatic fallback to Google Drive processing
- Performance optimizations for existing decision retrieval
