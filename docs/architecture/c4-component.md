# C4 Model - Component Diagram (Decision Service)

## Decision Service Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      Decision Service                            │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              API Layer (FastAPI Routes)                  │   │
│  │  • POST /api/v1/claims/{id}/decision                    │   │
│  │  • GET /api/v1/claims/{id}/documents                    │   │
│  │  • POST /api/v1/batch/evaluate                          │   │
│  │  • GET /api/v1/claims/{id}/decision/history            │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │            Request Validation Layer                      │   │
│  │  • Input validation (Pydantic models)                    │   │
│  │  • Authentication/authorization checks                   │   │
│  │  • Idempotency key handling                              │   │
│  │  • Rate limiting enforcement                             │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │            Decision Engine Core                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ Eligibility  │  │   Invoice    │  │    Rule      │   │   │
│  │  │   Engine     │  │    Parser    │  │  Evaluator   │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │            Data Access Layer                              │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   Claim      │  │  Document    │  │  Decision    │   │   │
│  │  │  Repository   │  │  Repository  │  │  Repository  │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │            External Service Clients                       │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   Cache      │  │   Message    │  │  Object      │   │   │
│  │  │   Client     │  │   Queue      │  │  Storage     │   │   │
│  │  │  (Redis)     │  │   Client     │  │  Client (S3) │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Observability Layer                            │   │
│  │  • Structured logging (JSON)                             │   │
│  │  • Metrics collection (Prometheus)                       │   │
│  │  • Distributed tracing (OpenTelemetry)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Layer
**Components**:
- `routes/claims.py`: Claim decision endpoints
- `routes/documents.py`: Document retrieval endpoints
- `routes/batch.py`: Batch processing endpoints
- `middleware/auth.py`: Authentication middleware
- `middleware/rate_limit.py`: Rate limiting middleware
- `middleware/tracing.py`: Request tracing middleware

**Responsibilities**:
- HTTP request/response handling
- Route registration and routing
- Middleware execution
- Error handling and response formatting

### 2. Request Validation Layer
**Components**:
- `schemas/request.py`: Pydantic request models
- `schemas/response.py`: Pydantic response models
- `validators/claim_validator.py`: Claim validation logic
- `validators/idempotency.py`: Idempotency key validation

**Responsibilities**:
- Input validation and sanitization
- Authentication token validation
- Authorization checks (RBAC)
- Idempotency key management
- Request deduplication

### 3. Decision Engine Core

#### Eligibility Engine
**Components**:
- `engine/eligibility.py`: Eligibility calculation
- `engine/line_item_analyzer.py`: Line item eligibility analysis
- `engine/cap_calculator.py`: Maximum benefit cap calculation

**Responsibilities**:
- Determine eligible amounts per line item
- Apply policy rules (e.g., normal wear and tear)
- Calculate maximum benefit caps
- Flag ineligible items

#### Invoice Parser
**Components**:
- `parser/invoice_parser.py`: Invoice text parsing
- `parser/line_item_extractor.py`: Line item extraction
- `parser/amount_extractor.py`: Amount extraction with validation

**Responsibilities**:
- Extract line items from invoice text
- Parse amounts, descriptions, dates
- Validate invoice structure
- Handle multiple invoice formats

#### Rule Evaluator
**Components**:
- `rules/rule_engine.py`: Rule execution engine
- `rules/rule_loader.py`: Rule loading and versioning
- `rules/rule_validator.py`: Rule validation

**Responsibilities**:
- Execute business rules
- Version management for rules
- Rule conflict resolution
- Decision confidence scoring

### 4. Data Access Layer

#### Claim Repository
**Components**:
- `repositories/claim_repository.py`: Claim data access
- `repositories/claim_cache.py`: Claim caching layer

**Responsibilities**:
- CRUD operations for claims
- Cache management (Redis)
- Query optimization
- Transaction management

#### Document Repository
**Components**:
- `repositories/document_repository.py`: Document metadata access
- `repositories/document_storage.py`: S3 document access

**Responsibilities**:
- Document metadata CRUD
- S3 document retrieval
- Document versioning
- Access control

#### Decision Repository
**Components**:
- `repositories/decision_repository.py`: Decision data access
- `repositories/audit_repository.py`: Audit log access

**Responsibilities**:
- Decision CRUD operations
- Decision history retrieval
- Audit log creation
- Decision superseding logic

### 5. External Service Clients

#### Cache Client (Redis)
**Components**:
- `clients/redis_client.py`: Redis connection and operations
- `clients/cache_manager.py`: Cache strategy implementation

**Responsibilities**:
- Cache get/set operations
- Cache invalidation
- Connection pooling
- Circuit breaker for Redis failures

#### Message Queue Client
**Components**:
- `clients/celery_client.py`: Celery task client
- `tasks/batch_tasks.py`: Batch processing tasks
- `tasks/notification_tasks.py`: Webhook notification tasks

**Responsibilities**:
- Task enqueueing
- Task status tracking
- Retry logic
- Dead letter queue handling

#### Object Storage Client (S3)
**Components**:
- `clients/s3_client.py`: S3 operations
- `clients/storage_manager.py`: Storage abstraction

**Responsibilities**:
- Document upload/download
- Version management
- Encryption/decryption
- Lifecycle policy management

### 6. Observability Layer
**Components**:
- `observability/logger.py`: Structured logging
- `observability/metrics.py`: Prometheus metrics
- `observability/tracing.py`: OpenTelemetry tracing

**Responsibilities**:
- JSON structured logging
- RED metrics (Rate, Errors, Duration)
- Distributed tracing correlation
- Error tracking and alerting

## Component Interactions

### Synchronous Decision Flow
```
API Route → Validation → Cache Check → 
Decision Engine → Eligibility Engine → Invoice Parser → Rule Evaluator → 
Decision Repository → Cache Update → Response
```

### Batch Processing Flow
```
API Route → Validation → Batch Service → 
Message Queue → Worker → Decision Engine → 
Decision Repository → Webhook Notification
```

### Document Retrieval Flow
```
API Route → Validation → Document Repository → 
Cache Check → S3 Client → Response
```

## Error Handling Strategy

- **Validation Errors**: Return 400 with detailed error messages
- **Not Found**: Return 404 with resource identifier
- **Rate Limit**: Return 429 with retry-after header
- **Service Unavailable**: Return 503 with circuit breaker status
- **Internal Errors**: Log with trace ID, return 500 with generic message

## Performance Optimizations

- **Caching**: Frequently accessed claims cached in Redis (1-hour TTL)
- **Connection Pooling**: Database and Redis connections pooled
- **Async Operations**: Non-blocking I/O for external service calls
- **Batch Queries**: N+1 query prevention with eager loading
- **Read Replicas**: Read operations routed to replicas

