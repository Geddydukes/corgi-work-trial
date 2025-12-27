# Developer Setup Guide

This guide will help you set up a local development environment for the Security Deposit Claims Decision Engine.

## Prerequisites

- **Docker**: 20.10+ and Docker Compose 2.0+
- **Python**: 3.11+ (for local development without Docker)
- **Git**: 2.30+
- **Make**: (optional, for convenience commands)

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/your-org/corgi.git
cd corgi
```

### 2. Start Services with Docker Compose

```bash
docker-compose up -d
```

This will start:
- PostgreSQL (port 5432)
- Redis (port 6379)
- MinIO (S3-compatible storage, port 9000)
- Prometheus (port 9090)
- Grafana (port 3000)

### 3. Initialize Database

```bash
# Run migrations
docker-compose exec app alembic upgrade head

# Load sample data (optional)
docker-compose exec app python scripts/load_sample_data.py
```

### 4. Start Application Services

```bash
# Start Decision Service
docker-compose up decision-service

# Start Document Processing Service (separate terminal)
docker-compose up document-service

# Start Celery Workers (separate terminal)
docker-compose up celery-worker
```

### 5. Verify Setup

```bash
# Health check
curl http://localhost:8000/health

# API documentation
open http://localhost:8000/docs
```

## Local Development (Without Docker)

### 1. Install Python Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Start Local Services

You still need Docker for databases and Redis:

```bash
docker-compose up postgres redis minio -d
```

### 3. Set Environment Variables

Create `.env` file:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/corgi_dev
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=corgi-documents
LOG_LEVEL=DEBUG
```

### 4. Run Services Locally

```bash
# Decision Service
uvicorn decision_service.main:app --reload --port 8000

# Document Processing Service
uvicorn document_service.main:app --reload --port 8001

# Celery Worker
celery -A tasks.celery_app worker --loglevel=info
```

## Project Structure

```
corgi/
├── decision_service/          # Decision API service
│   ├── main.py
│   ├── routes/
│   ├── engine/
│   ├── repositories/
│   └── schemas/
├── document_service/          # Document processing service
│   ├── main.py
│   ├── routes/
│   ├── ocr/
│   └── classifier/
├── tasks/                     # Celery tasks
│   ├── celery_app.py
│   ├── batch_tasks.py
│   └── ocr_tasks.py
├── shared/                    # Shared code
│   ├── models.py
│   ├── config.py
│   └── database.py
├── tests/                     # Test suite
├── migrations/               # Alembic migrations
├── docker-compose.yml         # Local development setup
├── Dockerfile                # Application container
└── requirements.txt          # Python dependencies
```

## Database Setup

### Create Database

```bash
# Using Docker
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE corgi_dev;"

# Or locally
createdb corgi_dev
```

### Run Migrations

```bash
# Using Docker
docker-compose exec app alembic upgrade head

# Or locally
alembic upgrade head
```

### Load Sample Data

```bash
# Using Docker
docker-compose exec app python scripts/load_sample_data.py

# Or locally
python scripts/load_sample_data.py
```

## Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=decision_service --cov=document_service

# Specific test file
pytest tests/test_decision_engine.py

# With verbose output
pytest -v
```

### Test Database

Tests use a separate test database. Set in `.env.test`:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/corgi_test
```

## API Testing

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# Create decision (requires authentication)
curl -X POST http://localhost:8000/api/v1/claims/CLM-2024-001234/decision \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"override_max_benefit": 5000.00}'
```

### Using OpenAPI Docs

1. Start the service: `docker-compose up decision-service`
2. Open browser: http://localhost:8000/docs
3. Click "Authorize" and enter your JWT token
4. Test endpoints interactively

## Common Tasks

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f decision-service

# Last 100 lines
docker-compose logs --tail=100 decision-service
```

### Database Access

```bash
# PostgreSQL shell
docker-compose exec postgres psql -U postgres -d corgi_dev

# Run SQL file
docker-compose exec -T postgres psql -U postgres -d corgi_dev < script.sql
```

### Redis Access

```bash
# Redis CLI
docker-compose exec redis redis-cli

# Monitor commands
docker-compose exec redis redis-cli MONITOR
```

### MinIO (S3) Access

1. Open browser: http://localhost:9000
2. Login: minioadmin / minioadmin
3. Create bucket: `corgi-documents`

## Environment Variables

### Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `S3_ENDPOINT_URL` | S3 endpoint (MinIO for local) | `http://localhost:9000` |
| `S3_ACCESS_KEY_ID` | S3 access key | - |
| `S3_SECRET_ACCESS_KEY` | S3 secret key | - |
| `S3_BUCKET_NAME` | S3 bucket name | `corgi-documents` |
| `JWT_SECRET_KEY` | JWT signing key | - |
| `LOG_LEVEL` | Logging level | `INFO` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OCR_TIER1_ENABLED` | Enable Tier 1 OCR | `true` |
| `OCR_TIER2_ENABLED` | Enable Tier 2 OCR (Tesseract) | `true` |
| `OCR_TIER3_ENABLED` | Enable Tier 3 OCR (Textract) | `false` |
| `AWS_REGION` | AWS region for Textract | `us-east-1` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |

## Troubleshooting

### Port Already in Use

```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

### Database Connection Error

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check connection
docker-compose exec postgres psql -U postgres -c "SELECT 1;"
```

### Redis Connection Error

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli PING
```

### Migration Errors

```bash
# Reset database (WARNING: deletes all data)
docker-compose exec postgres psql -U postgres -c "DROP DATABASE corgi_dev;"
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE corgi_dev;"
alembic upgrade head
```

## IDE Setup

### VS Code

Recommended extensions:
- Python
- Pylance
- Docker
- SQLTools

Settings (`.vscode/settings.json`):
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true
}
```

### PyCharm

1. Configure Python interpreter: `venv/bin/python`
2. Enable Docker integration
3. Configure database connection (PostgreSQL)
4. Set up pytest as test runner

## Next Steps

1. Read [Architecture Documentation](../architecture/)
2. Review [API Documentation](http://localhost:8000/docs)
3. Check [Non-Functional Requirements](../architecture/non-functional-requirements.md)
4. Review [Architecture Decision Records](../architecture/adr/)

## Getting Help

- **Documentation**: Check `/architecture` directory
- **Issues**: Create GitHub issue
- **Slack**: #corgi-dev channel
- **Email**: dev-team@example.com

