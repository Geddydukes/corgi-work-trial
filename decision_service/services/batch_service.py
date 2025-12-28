import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)


class BatchService:
    def __init__(self):
        from decision_service.repositories.batch_repository import BatchRepository
        self.batch_repository = BatchRepository()
    
    async def submit_batch(
        self,
        claim_ids: List[int],
        webhook_url: Optional[str] = None,
        priority: int = 0
    ) -> Dict:
        from decision_service.repositories.claim_repository import ClaimRepository
        from tasks.celery_app import evaluate_claim_task
        
        claim_repo = ClaimRepository()
        
        valid_claim_ids = []
        for claim_id in claim_ids:
            claim = await claim_repo.get_claim(claim_id)
            if claim:
                valid_claim_ids.append(claim_id)
            else:
                logger.warning(f"Claim {claim_id} not found, skipping")
        
        if not valid_claim_ids:
            raise ValueError("No valid claim IDs provided")
        
        batch_id = await self.batch_repository.create_batch_job(
            claim_ids=valid_claim_ids,
            webhook_url=webhook_url,
            priority=priority
        )
        
        for claim_id in valid_claim_ids:
            evaluate_claim_task.delay(claim_id, batch_id)
        
        estimated_completion = datetime.utcnow() + timedelta(
            seconds=len(valid_claim_ids) * 3
        )
        
        return {
            "batch_id": batch_id,
            "estimated_completion": estimated_completion.isoformat(),
            "claim_count": len(valid_claim_ids),
            "status": "pending"
        }
    
    async def get_batch_status(self, batch_id: str) -> Optional[Dict]:
        batch_job = await self.batch_repository.get_batch_job(batch_id)
        
        if not batch_job:
            return None
        
        return batch_job

