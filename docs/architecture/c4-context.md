# C4 Model - Context Diagram

## System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Users                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Analyst    │  │    Admin     │  │   Auditor    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼──────────────────┼──────────────────┼──────────────────┘
          │                  │                  │
          │                  │                  │
          │  HTTPS/TLS 1.3   │                  │
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼──────────────────┐
│                      API Gateway                                 │
│  • Rate Limiting (1000 req/min per user)                        │
│  • Authentication (OAuth 2.0 / JWT)                              │
│  • Request Routing                                               │
│  • Request ID Generation                                         │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            │ Internal Network
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│              Security Deposit Claims Decision Engine             │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Decision Service (FastAPI)                   │  │
│  │  • Core decision logic (stateless)                       │  │
│  │  • Eligibility engine                                     │  │
│  │  • Invoice parsing                                        │  │
│  │  • Rule evaluation                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Document Processing Service (FastAPI)              │  │
│  │  • OCR processing (Tesseract + Textract fallback)         │  │
│  │  • Document classification                                │  │
│  │  • Text extraction                                        │  │
│  │  • Quality validation                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Worker Services (Celery)                     │  │
│  │  • Async document processing                              │  │
│  │  • Batch evaluation jobs                                  │  │
│  │  • Retry logic with exponential backoff                   │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        │                   │                   │
┌───────▼────────┐  ┌───────▼────────┐  ┌───────▼────────┐
│  PostgreSQL    │  │     Redis      │  │   S3/MinIO     │
│  (Primary +    │  │  (Cache +      │  │  (Document     │
│   Read Replicas)│  │   Celery)     │  │   Storage)     │
└────────────────┘  └────────────────┘  └────────────────┘
        │                   │                   │
        │                   │                   │
┌───────▼───────────────────▼───────────────────▼────────┐
│              External Services                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│
│  │ AWS Textract │  │ PagerDuty    │  │ OAuth        ││
│  │ (OCR Tier 3) │  │ (Alerts)     │  │ Provider     ││
│  └──────────────┘  └──────────────┘  └──────────────┘│
└────────────────────────────────────────────────────────┘
```

## Actors

### Primary Actors
- **Analyst**: Reviews claims, overrides decisions, manages manual review queue
- **Admin**: System administration, rule management, user management
- **Auditor**: Access audit logs, compliance reporting, decision validation

### External Systems
- **OAuth Provider**: Authentication and authorization
- **AWS Textract**: Cloud OCR service (fallback tier)
- **PagerDuty**: Incident management and alerting

## Key Interactions

1. **Synchronous Decision Request**
   - User → API Gateway → Decision Service → Database → Response (< 5 sec)

2. **Asynchronous Batch Processing**
   - User → API Gateway → Decision Service → Message Queue → Worker → Webhook

3. **Document Upload & Processing**
   - User → API Gateway → Document Service → S3 → Worker → OCR → Classification → Database

4. **Manual Review Workflow**
   - System → Manual Review Queue → Analyst → Decision Override → Audit Log

## Non-Functional Requirements

- **Availability**: 99.9% uptime
- **Performance**: P95 response time < 3 seconds
- **Throughput**: 1000 decisions/minute peak
- **Security**: Encryption at rest (AES-256) and in transit (TLS 1.3)
- **Compliance**: 7-year data retention, audit logging

