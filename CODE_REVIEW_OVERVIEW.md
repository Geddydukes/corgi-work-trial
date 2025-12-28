# Code Review Overview - Security Deposit Claims Decision Engine

## System Purpose

**Security Deposit Claims Decision Engine** - An enterprise-grade system that:

- Processes security deposit claim documents (PDFs, images) using multi-tier OCR
- Classifies documents (lease, invoice, addendum, etc.) using ML + rules
- Parses invoices to extract line items and amounts using Gemini 2.5 Pro/Flash
- Evaluates claim eligibility based on business rules
- Generates automated decisions (approve/deny) with confidence scores
- Handles high-volume processing (target: 5,000 claims/hour)

## Architecture

### Services

1. **Decision Service** (`decision_service/`)

   - FastAPI service on port 8000
   - Main entry: `decision_service/main.py`
   - Routes: `decision_service/routes/claims.py`
   - Core engine: `decision_service/engine/decision_engine.py`

2. **Document Service** (`document_service/`)

   - FastAPI service on port 8001
   - OCR processing with multi-tier strategy
   - Document classification

3. **Shared Code** (`shared/`)
   - Models: `shared/models.py`
   - Config: `shared/config.py`
   - Utilities: deduplication, PII detection, error tracking

### Technology Stack

- **Language**: Python 3.11
- **Framework**: FastAPI (async)
- **Database**: PostgreSQL 14+ (with read replicas)
- **Cache/Queue**: Redis + Celery
- **OCR**: Multi-tier (PyPDF2 → Tesseract → Gemini/Mistral)
- **ML**: scikit-learn (TF-IDF + Logistic Regression)
- **AI**: Google Gemini 2.5 Pro/Flash for document analysis

## Key API Endpoints

### Decision Service

- `POST /api/v1/claims/{tracking_number}/decision` - Generate decision for a claim
- `GET /api/v1/claims/{tracking_number}/documents` - Get claim documents
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

## Key Components

### Decision Engine (`decision_service/engine/decision_engine.py`)

- Main orchestrator for claim evaluation
- Coordinates: DocumentAnalyzer, EligibilityEngine, RuleEvaluator
- Handles document analysis, line item extraction, and final decision creation

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
- Calculates caps (claim_amount, max_benefit)
- Determines approve/deny status
- Monotonicity requirement: increasing max_benefit must never decrease proposed_benefit

### Eligibility Engine (`decision_service/engine/eligibility.py`)

- Processes approved/ineligible line items
- Calculates eligible_total
- Handles credits and adjustments

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
cap_amount = min(max_benefit, invoice_total)
proposed_benefit = min(eligible_total, cap_amount)
```

### Eligibility Policy

**Eligible**: cleaning, trash removal, damage beyond normal wear, fixture repair
**Ineligible**: normal wear and tear, upgrades, routine maintenance, utilities (unless unpaid), late fees (unless covered)

## Known Issues (from Variance Reports)

### Issue #1: Rent Charges Being Approved

- **Problem**: System approves rent, garage rent, utility revenue
- **Root Cause**: Gemini not excluding rent charges
- **Status**: Needs fix in `document_analyzer.py` prompts

### Issue #2: Post-Lease-End Charges

- **Problem**: Charges after lease end date are approved
- **Root Cause**: No lease end date check
- **Status**: Needs implementation

### Issue #3: Normal Wear/Tear Detection Too Aggressive

- **Problem**: Valid charges denied as normal wear/tear
- **Root Cause**: Document analysis flags too broadly
- **Status**: Needs refinement

### Issue #4: "Excessive" Cleaning Charges

- **Problem**: "Excessive" cleaning approved but should be denied
- **Root Cause**: No special handling for "excessive" keyword
- **Status**: Needs clarification

## Data Models

### Key Models (`shared/models.py`)

- `DocumentType` enum: ADDENDUM, INVOICE, LEASE, UNKNOWN
- `EligibilityStatus` enum
- `ExtractedText` - OCR results
- `DocumentProcessingResult` - Processing results

### Database Tables

- `claims` - Claim data (claim_amount, max_benefit, etc.)
- `claim_documents` - Document metadata and extracted text
- `decisions` - Proposed decisions
- `decision_validation` - Actual decisions (for evaluation)

## Configuration

### Environment Variables (see `env.example`)

- `GEMINI_API_KEY` - Required for document analysis
- `GEMINI_MODEL` - gemini-2.5-flash or gemini-2.5-pro
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection for Celery
- OCR tier configuration (TIER1_ENABLED, TIER2_ENABLED, TIER3_ENABLED)

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

## Security & Compliance

- PII detection and redaction (names, phone numbers, addresses, SSN)
- Document retention policy (configurable by days)
- Hashed file deduplication
- Role-based access control (planned)
- Full audit trail of overrides and reviews

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

3. **`decision_service/engine/rule_evaluator.py`**

   - Cap calculation (claim_amount, max_benefit)
   - Final benefit amount calculation
   - Business rule enforcement

4. **`decision_service/engine/json_validator.py`**
   - Ensures Gemini responses are valid
   - May cause fallback to defaults if validation fails

### Documentation Files

- `README.md` - Main entry point
- `docs/PRD.md` - Product requirements
- `docs/STRUCTURE.md` - Architecture overview
- `docs/DECISION_PROCESS_FILES.md` - Decision flow explanation
- `docs/ISSUE_ANALYSIS.md` - Known issues analysis
- `docs/AGENT_ONBOARDING.md` - Comprehensive onboarding guide
- `rules/RULES_GUIDE.md` - Business rules documentation
- `docs/architecture/` - Architecture Decision Records (ADRs) and C4 diagrams

## Running the System

### Local Development

```bash
# Decision Service
uvicorn decision_service.main:app --reload --port 8000

# Document Service
uvicorn document_service.main:app --reload --port 8001

# Using Docker Compose
docker-compose up
```

### Scripts

- `scripts/run_decisions_first_5.py` - Run decisions on claims 900-904
- `scripts/generate_variance_report.py` - Generate variance reports

## Evaluation Metrics

- Status accuracy (approve/deny)
- Mean Absolute Error (MAE) for amounts
- False denial rate
- Systematic bias direction
- Cap-driven vs eligibility-driven changes

## Versioning

- Semantic versioning: `rules_vMAJOR.MINOR.PATCH`
- Every decision stamped with ruleset version
- Ability to rerun decisions under newer rules for comparison
