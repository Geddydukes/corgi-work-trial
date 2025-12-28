from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional
from uuid import uuid4

from decision_service.schemas.request import DecisionRequest
from decision_service.schemas.response import DecisionResponse
from shared.models import DocumentType

router = APIRouter()


@router.post("/claims/{tracking_number}/decision", response_model=DecisionResponse)
async def create_decision(
    tracking_number: str,
    request: Optional[DecisionRequest] = None,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Generate decision for a claim.
    
    Synchronously generates a decision for a claim. Response time target: < 5 seconds.
    """
    if not tracking_number:
        raise HTTPException(status_code=400, detail="Tracking number is required")
    
    request_id = x_request_id or str(uuid4())
    
    try:
        from decision_service.engine.decision_engine import DecisionEngine
        from decision_service.repositories.claim_repository import ClaimRepository
        
        engine = DecisionEngine()
        repository = ClaimRepository()
        
        claim = await repository.get_claim_by_tracking_number(tracking_number)
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
        
        decision = await engine.evaluate_claim(
            claim_id=claim["id"],
            override_max_benefit=request.override_max_benefit if request else None
        )
        
        decision_record = await repository.create_decision(decision, user_id="system")
        
        return DecisionResponse.from_decision_record(decision_record)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/claims/{tracking_number}/documents")
async def get_claim_documents(
    tracking_number: str,
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type")
):
    """
    Get documents for a claim.
    
    Returns metadata for all documents associated with a claim.
    Optionally filter by document type.
    """
    from decision_service.repositories.document_repository import DocumentRepository
    
    repository = DocumentRepository()
    documents = await repository.get_documents_by_tracking_number(
        tracking_number,
        document_type=document_type.value if document_type else None
    )
    
    if not documents:
        raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
    
    return documents

