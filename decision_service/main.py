import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from decision_service.routes import claims, health, batch

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


@app.get("/")
async def root():
    return {
        "service": "decision-service",
        "version": "1.0.0",
        "status": "running"
    }

