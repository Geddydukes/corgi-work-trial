from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "document-service"
    }


@router.get("/ready")
async def readiness_check():
    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "document-service"
    }

