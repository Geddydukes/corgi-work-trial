import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from decision_service.routes import claims, health, batch

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "service": "decision-service", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Decision Service")
    yield
    logger.info("Shutting down Decision Service")


app = FastAPI(
    title="Security Deposit Claims Decision Engine API",
    version="1.0.0",
    description="Production-ready API for security deposit claims decision processing",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(claims.router, prefix="/api/v1", tags=["Claims"])
app.include_router(batch.router, prefix="/api/v1", tags=["Batch"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to prevent server crashes from unhandled exceptions."""
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": f"Internal server error: {str(exc)}",
            "path": str(request.url.path),
            "method": request.method
        }
    )


@app.get("/")
async def root():
    return {
        "service": "decision-service",
        "version": "1.0.0",
        "status": "running"
    }

