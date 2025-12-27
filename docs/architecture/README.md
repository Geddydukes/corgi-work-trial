# Security Deposit Claims Decision Engine - Architecture Documentation

This directory contains comprehensive architecture documentation for the production-ready Security Deposit Claims Decision Engine.

## Documentation Structure

### 1. C4 Architecture Diagrams

- **[Context Diagram](./c4-context.md)**: System context, actors, and key interactions
- **[Container Diagram](./c4-container.md)**: High-level containers and their responsibilities
- **[Component Diagram](./c4-component.md)**: Detailed component breakdown of Decision Service
- **[Code Diagram](./c4-code.md)**: Code-level structure and key implementations

### 2. API Documentation

- **[OpenAPI 3.0 Specification](./openapi.yaml)**: Complete API contract with request/response schemas

### 3. Requirements & Design

- **[Non-Functional Requirements](./non-functional-requirements.md)**: Performance, availability, security, scalability requirements

### 4. Architecture Decision Records (ADR)

- **[ADR Index](./adr/README.md)**: Overview of all architecture decisions
- **[ADR-001: Python 3.11 with FastAPI](./adr/001-python-fastapi.md)**: Language and framework choice
- **[ADR-002: PostgreSQL with Read Replicas](./adr/002-postgresql-with-read-replicas.md)**: Database architecture
- **[ADR-003: Celery with Redis](./adr/003-celery-redis-task-queue.md)**: Asynchronous processing
- **[ADR-004: Tiered OCR Approach](./adr/004-ocr-tiered-approach.md)**: OCR strategy
- **[ADR-005: Kubernetes Deployment](./adr/005-kubernetes-deployment.md)**: Container orchestration
- **[ADR-006: Terraform Infrastructure](./adr/006-terraform-infrastructure.md)**: Infrastructure as Code

### 5. Developer Resources

- **[Developer Setup Guide](./developer-setup.md)**: Local development environment setup
- **[Docker Compose](../docker-compose.yml)**: Local development stack

### 6. Diagrams & Models

- **[Sequence Diagrams](./sequence-diagrams.md)**: Critical flow diagrams (synchronous, async, error scenarios)
- **[Infrastructure Diagram & Security](./infrastructure-diagram.md)**: Network architecture and threat modeling

## Quick Start

1. **Understand the System**: Start with [Context Diagram](./c4-context.md)
2. **Review Architecture**: Read [Container Diagram](./c4-container.md) and [Component Diagram](./c4-component.md)
3. **Set Up Development**: Follow [Developer Setup Guide](./developer-setup.md)
4. **Explore API**: Check [OpenAPI Specification](./openapi.yaml)
5. **Understand Decisions**: Review [Architecture Decision Records](./adr/)

## System Overview

### Architecture Principles

1. **Stateless Services**: All application services are stateless for horizontal scaling
2. **Separation of Concerns**: Clear separation between API, business logic, and data layers
3. **Fault Tolerance**: Circuit breakers, retries, graceful degradation
4. **Security First**: Encryption at rest and in transit, RBAC, audit logging
5. **Observability**: Comprehensive logging, metrics, and tracing

### Key Components

- **API Gateway**: Rate limiting, authentication, request routing
- **Decision Service**: Core decision logic (stateless, horizontally scalable)
- **Document Processing Service**: OCR, classification, text extraction
- **Celery Workers**: Asynchronous processing for long-running tasks
- **PostgreSQL**: Primary database with read replicas
- **Redis**: Cache and message broker
- **S3/MinIO**: Object storage for documents
- **Observability Stack**: Prometheus, Grafana, ELK

### Processing Modes

1. **Synchronous**: `/api/v1/claims/{id}/decision` (< 5 sec response)
2. **Asynchronous Batch**: `/api/v1/batch/evaluate` (webhook on completion)
3. **Manual Review**: Claims flagged for human review

## Performance Targets

| Metric | Target |
|--------|--------|
| Availability | 99.9% uptime |
| P95 Response Time | < 3 seconds |
| Throughput | 1000 decisions/minute peak |
| Database Lookup | < 10ms |
| Cache Hit Rate | > 80% |

## Security

- **Authentication**: OAuth 2.0 / JWT
- **Authorization**: RBAC (Analyst, Admin, Auditor)
- **Encryption**: AES-256 at rest, TLS 1.3 in transit
- **Audit Logging**: Immutable logs, 7-year retention
- **PII Protection**: Tokenization, data masking

See [Infrastructure Diagram & Security](./infrastructure-diagram.md) for detailed threat modeling.

## Technology Stack

- **Language**: Python 3.11
- **Framework**: FastAPI
- **Database**: PostgreSQL 14+ (with read replicas)
- **Cache/Queue**: Redis
- **Task Queue**: Celery
- **Object Storage**: S3/MinIO
- **Containerization**: Docker
- **Orchestration**: Kubernetes
- **Infrastructure**: Terraform
- **CI/CD**: GitHub Actions → ArgoCD

## Data Flow

```
Document Upload → OCR Service → Text Extraction → Classification → 
Invoice Parsing → Eligibility Engine → Decision Engine → 
Validation → Storage → API Response
```

See [Sequence Diagrams](./sequence-diagrams.md) for detailed flows.

## Scalability

- **Horizontal Scaling**: Stateless services scale to 10-50 pods
- **Database Scaling**: Read replicas for read operations
- **Worker Scaling**: Auto-scale based on queue depth
- **Storage Scaling**: Unlimited object storage (S3)

## Fault Tolerance

- **Circuit Breakers**: External services (OCR, S3)
- **Retry Logic**: Exponential backoff (3 attempts)
- **Dead Letter Queue**: Failed processing after max retries
- **Graceful Degradation**: Manual review if automation fails

## Observability

- **Logging**: Structured JSON logs (ELK Stack)
- **Metrics**: Prometheus (RED method: Rate, Errors, Duration)
- **Tracing**: OpenTelemetry (distributed tracing)
- **Alerting**: PagerDuty integration
- **Dashboards**: Grafana (claim volume, processing time, error rate)

## Compliance

- **Data Retention**: 7 years (compliance requirement)
- **Audit Logging**: All data access logged
- **Encryption**: At rest and in transit
- **Access Control**: RBAC with least privilege

## Getting Help

- **Documentation Issues**: Create GitHub issue
- **Architecture Questions**: Contact architecture team
- **Security Concerns**: security@example.com

## Document Maintenance

- **Last Updated**: 2024-01-15
- **Maintainer**: Architecture Team
- **Review Cycle**: Quarterly architecture reviews
- **Version**: 1.0.0

## Related Documentation

- [Main README](../README.md): Project overview
- [Data Dictionary](../DATA_DICTIONARY.md): Database schema documentation
- [API Documentation](./openapi.yaml): OpenAPI 3.0 specification

