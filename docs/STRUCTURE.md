# Project Structure

This document describes the reorganized project structure for the Security Deposit Claims Decision Engine.

## Directory Structure

```
Corgi/
├── architecture/              # Architecture documentation
│   ├── adr/                   # Architecture Decision Records
│   ├── c4-*.md                # C4 architecture diagrams
│   ├── openapi.yaml           # API specification
│   └── ...
│
├── shared/                     # Shared code across services
│   ├── __init__.py
│   ├── models.py              # Pydantic models (moved from root)
│   ├── config.py              # Configuration (moved from root)
│   └── deduplication.py       # Deduplication service (moved from root)
│
├── decision_service/           # Decision API Service
│   ├── __init__.py
│   ├── main.py                # FastAPI application
│   ├── routes/                 # API routes
│   │   ├── __init__.py
│   │   ├── claims.py          # Claim decision endpoints
│   │   └── health.py           # Health check endpoints
│   ├── schemas/                # Request/response schemas
│   │   ├── __init__.py
│   │   ├── request.py
│   │   └── response.py
│   ├── engine/                 # Decision engine
│   │   ├── __init__.py
│   │   ├── decision_engine.py  # Main orchestrator
│   │   ├── eligibility.py      # Eligibility engine
│   │   ├── invoice_parser.py   # Invoice parser
│   │   └── rule_evaluator.py  # Rule evaluator
│   └── repositories/          # Data access layer
│       ├── __init__.py
│       ├── claim_repository.py
│       └── document_repository.py
│
├── document_service/           # Document Processing Service
│   ├── __init__.py
│   ├── main.py                # FastAPI application
│   ├── routes/                 # API routes
│   │   ├── __init__.py
│   │   ├── documents.py        # Document processing endpoints
│   │   └── health.py           # Health check endpoints
│   ├── classifier.py           # Document classifier (moved from root)
│   ├── processor.py            # Document processor (moved from root)
│   └── ocr/                    # OCR service
│       ├── __init__.py
│       └── service.py          # OCR service (moved from root)
│
├── tasks/                      # Celery tasks
│   ├── __init__.py
│   └── celery_app.py          # Celery configuration and tasks (moved from celery_tasks.py)
│
├── tests/                      # Test suite
├── migrations/                 # Database migrations
├── docker-compose.yml          # Local development setup
├── requirements.txt           # Python dependencies
└── README.md                   # Project documentation
```

## File Movements

### Moved to `shared/`
- `models.py` → `shared/models.py`
- `config.py` → `shared/config.py`
- `deduplication.py` → `shared/deduplication.py`

### Moved to `document_service/`
- `classifier.py` → `document_service/classifier.py`
- `document_processor.py` → `document_service/processor.py`
- `ocr_service.py` → `document_service/ocr/service.py`

### Moved to `tasks/`
- `celery_tasks.py` → `tasks/celery_app.py`

## New Files Created

### Decision Service
- `decision_service/main.py` - FastAPI application
- `decision_service/routes/claims.py` - Claim decision endpoints
- `decision_service/routes/health.py` - Health check endpoints
- `decision_service/schemas/request.py` - Request schemas
- `decision_service/schemas/response.py` - Response schemas
- `decision_service/engine/decision_engine.py` - Main decision orchestrator
- `decision_service/engine/eligibility.py` - Eligibility engine
- `decision_service/engine/invoice_parser.py` - Invoice parser
- `decision_service/engine/rule_evaluator.py` - Rule evaluator
- `decision_service/repositories/claim_repository.py` - Claim data access
- `decision_service/repositories/document_repository.py` - Document data access

### Document Service
- `document_service/main.py` - FastAPI application
- `document_service/routes/documents.py` - Document processing endpoints
- `document_service/routes/health.py` - Health check endpoints

## Import Updates

All imports have been updated to use the new structure:
- `from models import ...` → `from shared.models import ...`
- `from config import Config` → `from shared.config import Config`
- `from classifier import ...` → `from document_service.classifier import ...`
- `from document_processor import ...` → `from document_service.processor import ...`
- `from ocr_service import ...` → `from document_service.ocr.service import ...`

## Running the Services

### Decision Service
```bash
uvicorn decision_service.main:app --reload --port 8000
```

### Document Service
```bash
uvicorn document_service.main:app --reload --port 8001
```

### Using Docker Compose
```bash
docker-compose up
```

## Next Steps

1. **Database Integration**: Connect repositories to actual PostgreSQL database
2. **Authentication**: Add OAuth 2.0 / JWT authentication middleware
3. **Caching**: Implement Redis caching in repositories
4. **S3 Integration**: Add S3 client for document storage
5. **Batch Processing**: Implement batch evaluation endpoints
6. **Testing**: Add integration tests for new services

## Notes

- The repositories currently return mock data when `DATABASE_URL` is not configured
- All services are stateless and can be horizontally scaled
- The architecture follows the C4 model documented in `/architecture`

