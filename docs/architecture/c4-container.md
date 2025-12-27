# C4 Model - Container Diagram

## Container Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Security Deposit Claims System                    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    API Gateway                               │  │
│  │  • Kong / AWS API Gateway / Traefik                          │  │
│  │  • Rate limiting: 1000 req/min per user                      │  │
│  │  • Authentication: OAuth 2.0 / JWT validation                │  │
│  │  • Request ID generation (X-Request-ID)                       │  │
│  │  • Idempotency key handling (X-Idempotency-Key)              │  │
│  │  • TLS termination                                           │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          │                                          │
│        ┌─────────────────┼─────────────────┐                       │
│        │                 │                 │                       │
│  ┌─────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐               │
│  │  Decision  │   │  Document   │   │  Batch      │               │
│  │  Service   │   │  Processing │   │  Service    │               │
│  │  (FastAPI) │   │  Service    │   │  (FastAPI)   │               │
│  │            │   │  (FastAPI)  │   │              │               │
│  │ Stateless  │   │ Stateless   │   │ Stateless    │               │
│  │ Pods       │   │ Pods        │   │ Pods         │               │
│  └─────┬──────┘   └──────┬──────┘   └──────┬──────┘               │
│        │                 │                 │                       │
│        └─────────────────┼─────────────────┘                       │
│                          │                                          │
│  ┌───────────────────────▼──────────────────────────────────────┐  │
│  │              Celery Workers (Async Processing)                │  │
│  │  • Document OCR workers (scale by queue depth)               │  │
│  │  • Batch evaluation workers                                   │  │
│  │  • Retry workers (dead letter queue)                         │  │
│  │  • Manual review notification workers                        │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          │                                          │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐  ┌──────▼────────┐  ┌──────▼────────┐
│  PostgreSQL    │  │     Redis      │  │   S3/MinIO     │
│  Primary DB    │  │  • Cache       │  │  • Documents   │
│  + Read        │  │  • Celery      │  │  • Encrypted   │
│  Replicas (3)  │  │    Broker      │  │  • Versioned    │
└────────────────┘  └────────────────┘  └────────────────┘
        │                  │                  │
        │                  │                  │
┌───────▼──────────────────▼──────────────────▼────────┐
│              Observability Stack                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│
│  │ Prometheus   │  │   Grafana    │  │   ELK Stack  ││
│  │ (Metrics)    │  │  (Dashboards)│  │  (Logging)   ││
│  └──────────────┘  └──────────────┘  └──────────────┘│
└────────────────────────────────────────────────────────┘
```

## Container Details

### 1. API Gateway
**Technology**: Kong / AWS API Gateway / Traefik  
**Responsibilities**:
- Request routing to backend services
- Rate limiting (1000 requests/minute per user)
- Authentication and authorization (OAuth 2.0 / JWT)
- Request/response transformation
- Idempotency key management
- Request ID propagation
- TLS termination

**Scaling**: Horizontal (3+ instances behind load balancer)

### 2. Decision Service
**Technology**: FastAPI (Python 3.11)  
**Responsibilities**:
- Core decision logic execution
- Eligibility engine
- Invoice parsing and line item extraction
- Rule evaluation
- Decision validation
- Synchronous API endpoints (`/api/v1/claims/{id}/decision`)

**Scaling**: Stateless pods, horizontal scaling (10-50 pods based on load)  
**Health Checks**: `/health`, `/ready`

### 3. Document Processing Service
**Technology**: FastAPI (Python 3.11)  
**Responsibilities**:
- Document upload handling
- OCR orchestration (Tesseract → Textract fallback)
- Document classification
- Text extraction quality validation
- Document metadata management

**Scaling**: Stateless pods, horizontal scaling (5-20 pods)  
**Health Checks**: `/health`, `/ready`

### 4. Batch Service
**Technology**: FastAPI (Python 3.11)  
**Responsibilities**:
- Batch job creation and management
- Webhook notification handling
- Batch status tracking
- Job scheduling

**Scaling**: Stateless pods (2-5 pods)  
**Health Checks**: `/health`, `/ready`

### 5. Celery Workers
**Technology**: Celery + Redis  
**Responsibilities**:
- Async document processing
- Batch evaluation jobs
- Retry logic with exponential backoff
- Dead letter queue processing
- Manual review notifications

**Scaling**: Worker pools scale based on queue depth:
- OCR Workers: 10-50 workers
- Batch Workers: 5-20 workers
- Retry Workers: 2-5 workers

### 6. PostgreSQL Database
**Technology**: PostgreSQL 14+  
**Responsibilities**:
- Primary data store (claims, decisions, documents)
- Transaction management
- Data integrity constraints
- Partitioned tables (yearly for claims, monthly for audit logs)

**Configuration**:
- Primary: 1 instance (write operations)
- Read Replicas: 3 instances (read operations)
- Connection Pool: Max 100 connections per service
- Backup: Continuous WAL archiving, daily full backups

### 7. Redis
**Technology**: Redis 7+  
**Responsibilities**:
- Celery message broker
- Cache layer (frequently accessed claims)
- Rate limiting counters
- Session storage

**Configuration**:
- Primary: 1 instance (with persistence)
- Replica: 1 instance (read-only)
- Cache TTL: 1 hour for claims, 5 minutes for decisions

### 8. Object Storage (S3/MinIO)
**Technology**: AWS S3 / MinIO (on-prem)  
**Responsibilities**:
- Document storage (encrypted at rest)
- Versioning for document history
- Lifecycle policies (7-year retention)

**Configuration**:
- Encryption: AES-256
- Versioning: Enabled
- Lifecycle: Move to Glacier after 1 year, delete after 7 years

### 9. Observability Stack
**Technology**: Prometheus, Grafana, ELK Stack  
**Responsibilities**:
- Metrics collection (Prometheus)
- Dashboards (Grafana)
- Log aggregation (ELK)
- Distributed tracing (OpenTelemetry)

## Container Communication

### Synchronous Communication
- **API Gateway → Services**: HTTP/REST (internal network)
- **Services → Database**: SQLAlchemy connection pool
- **Services → Redis**: Redis client with connection pooling
- **Services → S3**: boto3 SDK

### Asynchronous Communication
- **Services → Workers**: Celery tasks via Redis broker
- **Workers → Services**: HTTP callbacks for webhooks

### Service Discovery
- Kubernetes DNS for service-to-service communication
- Environment variables for external service endpoints

## Data Flow Between Containers

1. **Synchronous Decision Flow**:
   ```
   API Gateway → Decision Service → PostgreSQL (read) → Redis (cache check) → Response
   ```

2. **Document Processing Flow**:
   ```
   API Gateway → Document Service → S3 (upload) → Celery Queue → 
   Worker → OCR Service → S3 (store result) → PostgreSQL (metadata) → 
   Webhook (if async)
   ```

3. **Batch Processing Flow**:
   ```
   API Gateway → Batch Service → Celery Queue → Workers → 
   Decision Service → PostgreSQL → Batch Service → Webhook
   ```

## Security Boundaries

- **External Boundary**: API Gateway (TLS 1.3, authentication)
- **Internal Network**: Private VPC/subnet (no public access)
- **Database**: Private subnet, accessible only from application services
- **Object Storage**: Private bucket, IAM-based access control

