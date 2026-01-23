# Security Deposit Claims Decision Engine

**Last Updated**: December 30, 2025  
**Status**: Production-ready system processing security deposit claims with automated decision-making

## System Overview

Enterprise-grade security deposit claims processing system that:

- **Processes claim documents** (PDFs, images) using multi-tier OCR (PyPDF2 → Tesseract → Gemini Flash)
- **Classifies documents** (lease, invoice, addendum, move-out statement) using ML + rule-based classification
- **Extracts line items** from invoices using Google Gemini 2.5 Flash/Pro with deterministic rule validation
- **Evaluates eligibility** using deterministic business rules (rent, contractual fees, prior balances, etc.)
- **Generates automated decisions** (approve/deny) with benefit amounts, confidence scores, and detailed reasoning
- **Handles batch processing** with concurrency control and Redis/Celery support
- **Provides web UI** for manual review, override, and variance analysis
- **Integrates with Google Drive** for automated document retrieval and processing

## Architecture

### Services

1. **Decision Service** (`decision_service/`)

   - FastAPI service on port 8000
   - Main entry: `decision_service/main.py`
   - Routes: `decision_service/routes/claims.py`, `decision_service/routes/batch.py`
   - Core engine: `decision_service/engine/decision_engine.py`
   - **Key Components**:
     - `DecisionEngine`: Main orchestrator
     - `DocumentAnalyzer`: Gemini-based document and line item analysis
     - `RuleEvaluator`: Business rule application and cap calculation
     - `EligibilityEngine`: Line item eligibility classification
     - `DeterministicRules`: Phrase-based category detection (rent, cleaning, repairs, etc.)

2. **Document Service** (`document_service/`)

   - FastAPI service on port 8001
   - Multi-tier OCR processing (Tier 1: PyPDF2, Tier 2: Tesseract, Tier 3: Gemini Flash)
   - Document classification (ML + rules)
   - Parallel processing support

3. **Frontend** (`frontend/`)

   - Next.js 14+ with TypeScript
   - React components for decision review and override
   - Real-time total calculation
   - Batch processing UI
   - Google Drive integration

4. **Shared Code** (`shared/`)
   - Models: `shared/models.py`
   - Config: `shared/config.py` (all environment variables)
   - Google Drive integration: `shared/google_drive.py` (thread-safe, batch metadata fetching)

### Technology Stack

- **Backend**: Python 3.11+, FastAPI (async)
- **Frontend**: Next.js 16.1, React 19.2, TypeScript 5+
- **Database**: PostgreSQL 14+ (with connection pooling)
- **Cache/Queue**: Redis + Celery (optional, falls back to BackgroundTasks)
- **OCR**: Multi-tier (PyPDF2 → Tesseract → Gemini Flash)
- **ML**: scikit-learn (TF-IDF + Logistic Regression) for document classification
- **AI**: Google Gemini 2.5 Flash/Pro for document analysis and line item extraction
- **Storage**: Google Drive API for document retrieval

## Key Features

### Decision Engine

- **Deterministic Rule Engine**: Phrase-based categorization prevents LLM variability
- **Caching**: Reuses LLM analysis when rerunning with updated rules (cost optimization)
- **Cap Management**: Handles `claim_amount`, `max_benefit`, and `invoice_total` caps correctly
- **NULL `claim_amount` Handling**: Uses `max_benefit` as cap when `claim_amount` is NULL (not $0)
- **Concurrency Control**: Global semaphore for Gemini API calls (configurable limit)
- **Error Handling**: Graceful degradation, retry logic, comprehensive error tracking

### Document Processing

- **Multi-tier OCR**: Automatically escalates based on confidence thresholds
- **Parallel Processing**: Concurrent Google Drive downloads and Gemini API calls
- **Batch Metadata Fetching**: Reduces API calls for better performance
- **Document Filtering**: Skips irrelevant documents (ledgers, applications, leases) based on keywords

### Batch Processing

- **Unlimited Batch Size**: Processes any number of claims
- **Concurrent Processing**: Configurable concurrency (default: 5 claims)
- **Status Tracking**: Real-time progress updates via `/batch/{batch_id}/status`
- **Redis Optional**: Falls back to synchronous processing if Redis unavailable

## Installation

### Prerequisites

```bash
# Python 3.11+
python3 --version

# PostgreSQL 14+
psql --version

# Redis (optional, for async processing)
redis-cli --version

# System dependencies (Ubuntu/Debian)
sudo apt-get install tesseract-ocr libmagic1 libheif-dev

# System dependencies (macOS)
brew install tesseract libmagic libheif
```

### Setup

```bash
# Clone repository
git clone <repository-url>
cd <project-directory>

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..

# Copy environment template
cp env.example .env

# Edit .env with your configuration
# Required: GEMINI_API_KEY, DATABASE_URL
# Optional: GOOGLE_DRIVE_CREDENTIALS, REDIS_URL
```

## Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/app_dev

# Gemini API (required for document analysis)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash  # or gemini-2.5-pro

# Google Drive (optional, for process-from-drive endpoint)
GOOGLE_DRIVE_CREDENTIALS=credentials/google-drive-credentials.json
GOOGLE_DRIVE_USE_SERVICE_ACCOUNT=true
```

### Optional Environment Variables

```bash
# OCR Configuration
OCR_TIER1_ENABLED=true
OCR_TIER2_ENABLED=true
OCR_TIER3_ENABLED=false  # Enable for high-quality processing
OCR_CONFIDENCE_THRESHOLD=60

# Classification
CLASSIFICATION_CONFIDENCE_THRESHOLD=0.75

# Redis (for async batch processing)
REDIS_URL=redis://localhost:6379/0

# Concurrency
MAX_CONCURRENT_WORKERS=10
GEMINI_CONCURRENCY_LIMIT=3  # Max concurrent Gemini API calls

# File Processing
MAX_FILE_SIZE_MB=50
PROCESSING_TIMEOUT_SEC=60
```

See `env.example` for complete configuration options.

## Usage

### Starting Services

```bash
# Start decision service
cd <project-directory>
uvicorn decision_service.main:app --host 0.0.0.0 --port 8000 --reload

# Start document service (separate terminal)
uvicorn document_service.main:app --host 0.0.0.0 --port 8001 --reload

# Start frontend (separate terminal)
cd frontend
npm run dev
```

### API Endpoints

#### Decision Endpoints

- `POST /api/v1/claims/{tracking_number}/decision` - Generate new decision
- `GET /api/v1/claims/{tracking_number}/decision` - Get latest decision
- `PATCH /api/v1/claims/{tracking_number}/decision/{decision_id}` - Update decision with overrides

#### Document Processing

- `POST /api/v1/claims/process-from-drive` - Process claim from Google Drive
  - Requires: `tracking_number`, `drive_folder_id`
  - Downloads documents, runs OCR, generates decision

#### Batch Processing

- `POST /api/v1/batch/evaluate` - Submit batch evaluation
  - Body: `{"claim_ids": [1, 2, 3, ...]}`
  - Returns: `{"batch_id": "uuid"}`
- `GET /api/v1/batch/{batch_id}/status` - Get batch status
  - Returns: `{"status": "completed", "processed_count": 10, "claim_count": 10}`

#### Health Checks

- `GET /health` - Health check
- `GET /ready` - Readiness check

### Example: Process Single Claim

```python
import requests

# Process claim from Google Drive
response = requests.post(
    "http://localhost:8000/api/v1/claims/process-from-drive",
    json={
        "tracking_number": "123",
        "drive_folder_id": "YOUR_DRIVE_FOLDER_ID_HERE"
    }
)
decision = response.json()
print(f"Status: {decision['proposed_status']}")
print(f"Amount: ${decision['proposed_benefit_amount']}")
```

### Example: Batch Processing

```python
import requests

# Submit batch
response = requests.post(
    "http://localhost:8000/api/v1/batch/evaluate",
    json={"claim_ids": [1, 2, 3, 4, 5]}
)
batch_id = response.json()["batch_id"]

# Check status
status = requests.get(f"http://localhost:8000/api/v1/batch/{batch_id}/status").json()
print(f"Processed: {status['processed_count']}/{status['claim_count']}")
```

## Decision Engine Logic

### Processing Flow

1. **Document Loading**: Fetches documents from database or Google Drive
2. **OCR Processing**: Multi-tier OCR extraction (cached by file hash)
3. **Document Analysis**: Gemini analyzes documents for addendum coverage, denial reasons
4. **Line Item Extraction**: Gemini extracts line items from invoices
5. **Deterministic Categorization**: Phrase-based rules categorize items (rent, cleaning, repairs, etc.)
6. **Eligibility Evaluation**: Deterministic rules determine `should_be_included`
7. **Cap Calculation**: Applies `min(claim_amount, max_benefit, invoice_total)` caps
8. **Decision Generation**: Creates decision with status, amounts, reasoning

### Key Business Rules

- **Rent**: Always denied
- **Contractual Fees**: Denied (late fees, admin fees, etc.)
- **Prior Balances**: Denied (balance forward, opening balance, etc.)
- **Cleaning/Repairs/Damage**: Approved if not explicitly denied
- **Normal Wear/Tear**: Denied if explicitly flagged
- **Other Insurance**: Denied (pet damage, fire, water damage, etc.)
- **Utility Charges**: Denied (no coverage)

### Cap Logic

- If `claim_amount` is NULL: Use `max_benefit` as cap (not $0)
- If `claim_amount` is 0: Approve $0 only if no `max_benefit`
- Final cap: `min(claim_amount or max_benefit, max_benefit, invoice_total)`
- Benefit amount: `min(eligible_total, cap_amount)`

## Performance

- **Single Claim**: 5-30 seconds (depending on document count and OCR tier)
- **Batch Processing**: 5-10 claims/minute (with concurrency)
- **Gemini API**: Global semaphore limits concurrent calls (default: 3)
- **Database**: Connection pooling for optimized queries
- **Caching**: LLM results cached for reruns (significant cost savings)

## Security

- **No Hardcoded Secrets**: All API keys via environment variables
- **Credential Storage**: Google Drive credentials in `credentials/` folder (gitignored)
- **File Validation**: Magic bytes verification, size limits
- **Error Handling**: Comprehensive error tracking without exposing internals
- **Audit Trail**: All decisions and overrides tracked in database

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test
pytest tests/test_decision_engine.py -v
```

## Monitoring

Structured JSON logs are emitted for all operations:

```json
{
  "timestamp": "2025-12-30T00:23:05",
  "level": "INFO",
  "service": "decision-service",
  "message": "Decision created: approve $2023.35"
}
```

## Variance Analysis

Current performance metrics (as of December 30, 2025):

- **Total Claims Analyzed**: 83
- **Status Accuracy**: 92.7% (76/83 correct)
- **Status Mismatches**: 6 (3 false negatives, 3 false positives)
- **Average Variance**: $1,287.32 per claim

See `variance/README.md` for detailed variance analysis and `variance_report_20251230_002305.md` for full report.

## Code Review Notes

### Critical Fixes (December 2025)

1. **NULL `claim_amount` Handling**: Fixed issue where NULL `claim_amount` defaulted to $0, causing incorrect $0 approvals. Now uses `max_benefit` as cap when `claim_amount` is NULL.

2. **Deterministic Rules**: Implemented phrase-based categorization to prevent LLM variability in line item classification.

3. **Caching**: Added LLM result caching to reduce costs when rerunning claims with updated rules.

4. **Concurrency Control**: Added global semaphore for Gemini API calls to prevent rate limiting.

### Architecture Decisions

- **Deterministic Rules First**: LLM provides suggestions, deterministic rules make final decisions
- **Caching Strategy**: Cache LLM analysis but always reapply deterministic rules
- **Error Handling**: Graceful degradation, never crash on individual claim failures
- **Batch Processing**: Redis optional, falls back to synchronous processing

## Production Readiness Improvements for Future Development

### 1. Monitoring & Observability

**Current State**: Structured JSON logs, basic health checks

**Recommended Improvements**:

- **APM Integration**: Integrate with Datadog, New Relic, or similar for distributed tracing
- **Metrics Dashboard**: Prometheus + Grafana for real-time performance metrics
- **Alerting**: Set up alerts for error rates, latency spikes, and throughput drops
- **Log Aggregation**: Centralized logging with ELK stack or CloudWatch Logs
- **Business Metrics**: Track decision accuracy, variance trends, cost per claim

### 2. Scaling & Performance

**Current State**: 3,351 claims/hour (33% below 5,000 target)

**Recommended Improvements**:

- **Horizontal Scaling**: Deploy multiple worker instances behind load balancer
- **Increase Concurrency**: Scale to 7-8 concurrent claims (from current 5)
- **Gemini API Optimization**: Increase semaphore to 4-5 concurrent calls (from 3)
- **Database Read Replicas**: Offload read queries to replicas for better throughput
- **Redis Clustering**: Use Redis Cluster for distributed caching and queue management
- **CDN for Documents**: Cache frequently accessed documents at edge locations

### 3. Security Hardening

**Current State**: Environment variables, gitignored credentials

**Recommended Improvements**:

- **Secrets Management**: Integrate with AWS Secrets Manager, HashiCorp Vault, or similar
- **API Authentication**: Implement JWT tokens with refresh token rotation
- **Rate Limiting**: Per-user and per-IP rate limiting with Redis
- **Input Validation**: Enhanced Pydantic validators for all API inputs
- **SQL Injection Prevention**: Use parameterized queries exclusively (already implemented)
- **HTTPS Only**: Enforce TLS 1.3+ with certificate pinning
- **Audit Logging**: Comprehensive audit trail for all decision changes and overrides
- **PII Encryption**: Encrypt sensitive data at rest (SSN, account numbers)

### 4. Reliability & Resilience

**Current State**: Global exception handler, retry logic, graceful degradation

**Recommended Improvements**:

- **Circuit Breakers**: Implement circuit breakers for external services (Gemini API, Google Drive)
- **Health Checks**: Enhanced health checks with dependency verification (DB, Redis, Gemini API)
- **Graceful Shutdown**: Proper cleanup of in-flight requests on shutdown
- **Database Connection Pooling**: Tune pool size based on load (currently using defaults)
- **Idempotency**: Ensure batch processing is idempotent (retry-safe)
- **Dead Letter Queue**: Failed claims should be queued for manual review
- **Backup & Recovery**: Automated database backups with point-in-time recovery

### 5. Testing & Quality Assurance

**Current State**: Unit tests, integration tests

**Recommended Improvements**:

- **Test Coverage**: Increase coverage to 80%+ (currently partial)
- **Load Testing**: Simulate 5,000 claims/hour load to verify performance
- **Chaos Engineering**: Test system resilience under failure conditions
- **Contract Testing**: API contract tests to prevent breaking changes
- **End-to-End Tests**: Automated E2E tests for critical user flows
- **Performance Regression Tests**: Automated benchmarks to catch performance degradation

### 6. CI/CD Pipeline

**Current State**: Manual deployment

**Recommended Improvements**:

- **Automated Testing**: Run tests on every PR (GitHub Actions, GitLab CI)
- **Automated Deployment**: Deploy to staging/production via CI/CD pipeline
- **Blue-Green Deployments**: Zero-downtime deployments
- **Database Migrations**: Automated migration testing and rollback procedures
- **Container Registry**: Use Docker Hub or ECR for container images
- **Infrastructure as Code**: Terraform/CloudFormation for infrastructure provisioning

### 7. Cost Optimization

**Current State**: LLM caching, document filtering

**Recommended Improvements**:

- **LLM Cost Tracking**: Real-time cost monitoring per claim/document
- **Tier 3 OCR Optimization**: Only escalate to Tier 3 when absolutely necessary
- **Batch API Calls**: Batch multiple Gemini requests where possible
- **Document Caching**: Cache OCR results longer (currently 90 days)
- **Auto-scaling**: Scale down during low-traffic periods
- **Reserved Instances**: Use reserved instances for predictable workloads

### 8. Data Quality & Validation

**Current State**: Basic validation, variance tracking

**Recommended Improvements**:

- **Automated Variance Monitoring**: Alert on high variance cases automatically
- **Data Quality Checks**: Validate claim data completeness before processing
- **Anomaly Detection**: ML-based anomaly detection for unusual claim patterns
- **A/B Testing Framework**: Test rule changes on subset of claims before full rollout
- **Feedback Loop**: Automated collection of user override patterns for rule refinement

### 9. Compliance & Governance

**Current State**: Basic audit trail

**Recommended Improvements**:

- **GDPR Compliance**: Right to deletion, data portability, consent management
- **SOC 2 Compliance**: Security controls, access management, change management
- **Data Retention Policies**: Automated data archival and deletion
- **Access Controls**: Role-based access control (RBAC) for different user types
- **Change Management**: Formal process for rule changes with approval workflow

### 10. Developer Experience

**Current State**: Good documentation, clear structure

**Recommended Improvements**:

- **API Documentation**: Interactive Swagger/OpenAPI docs with examples
- **Local Development**: Docker Compose setup for full local environment
- **Debugging Tools**: Enhanced logging with correlation IDs, request tracing
- **Performance Profiling**: Built-in profiling tools for identifying bottlenecks
- **Code Quality**: Pre-commit hooks, automated linting, type checking

### Priority Recommendations

**High Priority** (Immediate production needs):

1. Secrets management integration
2. Enhanced monitoring and alerting
3. Horizontal scaling setup
4. Automated testing pipeline

**Medium Priority** (Next 3-6 months): 5. Circuit breakers and resilience patterns 6. Cost optimization and tracking 7. Performance optimization (increase concurrency) 8. Enhanced security (rate limiting, audit logging)

**Low Priority** (Future enhancements): 9. A/B testing framework 10. Advanced analytics and ML-based anomaly detection 11. Compliance certifications (SOC 2, GDPR)

## License

Proprietary - All rights reserved
