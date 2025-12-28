from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from uuid import uuid4
from datetime import datetime

from decision_service.schemas.request import BatchEvaluationRequest
from decision_service.schemas.response import BatchEvaluationResponse, BatchStatusResponse
from decision_service.services.batch_service import BatchService

router = APIRouter()


@router.post("/batch/evaluate", response_model=BatchEvaluationResponse, status_code=202)
async def submit_batch_evaluation(
    request: BatchEvaluationRequest,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Submit batch evaluation job.
    
    Submits a batch of claims for asynchronous evaluation.
    Returns immediately with batch ID. Completion notification sent via webhook.
    """
    request_id = x_request_id or str(uuid4())
    
    try:
        batch_service = BatchService()
        
        result = await batch_service.submit_batch(
            claim_ids=request.claim_ids,
            webhook_url=request.webhook_url,
            priority=request.priority
        )
        
        return BatchEvaluationResponse(
            batch_id=result["batch_id"],
            estimated_completion=datetime.fromisoformat(result["estimated_completion"].replace('Z', '+00:00')) if isinstance(result["estimated_completion"], str) else result["estimated_completion"],
            claim_count=result["claim_count"],
            status=result["status"]
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: str,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
):
    """
    Get batch job status.
    
    Returns current status of a batch evaluation job.
    """
    request_id = x_request_id or str(uuid4())
    
    try:
        batch_service = BatchService()
        batch_status = await batch_service.get_batch_status(batch_id)
        
        if not batch_status:
            raise HTTPException(status_code=404, detail=f"Batch job {batch_id} not found")
        
        def parse_datetime(dt_str):
            if dt_str is None:
                return None
            if isinstance(dt_str, datetime):
                return dt_str
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        
        return BatchStatusResponse(
            batch_id=batch_status["batch_id"],
            status=batch_status["status"],
            claim_count=batch_status["claim_count"],
            processed_count=batch_status["processed_count"],
            successful_count=batch_status["successful_count"],
            failed_count=batch_status["failed_count"],
            started_at=parse_datetime(batch_status.get("started_at")),
            completed_at=parse_datetime(batch_status.get("completed_at")),
            error_message=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

