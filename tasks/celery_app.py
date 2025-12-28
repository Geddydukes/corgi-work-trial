import asyncio
import logging
from pathlib import Path
from typing import Optional

from celery import Celery
from celery.exceptions import Retry

from shared.config import Config
from document_service.processor import DocumentProcessor
from shared.models import DocumentProcessingResult

logger = logging.getLogger(__name__)

app = Celery('document_processor', broker=Config.REDIS_URL)
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(
    self,
    file_path: str,
    claim_id: int,
    processing_priority: int = 0,
    force_high_quality: bool = False,
) -> dict:
    try:
        processor = DocumentProcessor()
        result = asyncio.run(processor.process_document(
            Path(file_path),
            claim_id=claim_id,
            processing_priority=processing_priority,
            force_high_quality=force_high_quality,
        ))
        
        return result.to_dict()
        
    except Exception as e:
        logger.error(f"Task failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@app.task
def process_document_batch(
    file_paths: list[str],
    claim_id: int,
    processing_priority: int = 0,
) -> list[dict]:
    tasks = []
    for file_path in file_paths:
        task = process_document_task.delay(
            file_path, claim_id, processing_priority
        )
        tasks.append(task)
    
    results = []
    for task in tasks:
        try:
            result = task.get(timeout=300)
            results.append(result)
        except Exception as e:
            logger.error(f"Batch task failed: {e}")
            results.append({"error": str(e)})
    
    return results


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def evaluate_claim_task(self, claim_id: int, batch_id: str) -> dict:
    """
    Process a single claim in a batch.
    
    This task is called by the batch processing system to evaluate a claim
    asynchronously. It updates the batch status after completion.
    """
    from decision_service.repositories.batch_repository import BatchRepository
    from decision_service.engine.decision_engine import DecisionEngine
    from decision_service.repositories.claim_repository import ClaimRepository
    
    batch_repo = BatchRepository()
    claim_repo = ClaimRepository()
    
    try:
        asyncio.run(batch_repo.update_batch_status(batch_id, claim_id, 'processing'))
        
        engine = DecisionEngine()
        decision = asyncio.run(engine.evaluate_claim(claim_id=claim_id))
        
        decision_record = asyncio.run(claim_repo.create_decision(decision, user_id="system"))
        
        asyncio.run(batch_repo.update_batch_status(batch_id, claim_id, 'completed'))
        
        batch_status = asyncio.run(batch_repo.get_batch_job(batch_id))
        
        if batch_status and batch_status["status"] == "completed":
            logger.info(f"Batch {batch_id} completed. All claims processed.")
        
        return {
            "claim_id": claim_id,
            "batch_id": batch_id,
            "status": "completed",
            "decision_id": decision_record["id"] if decision_record else None
        }
        
    except Exception as e:
        logger.error(f"Error processing claim {claim_id} in batch {batch_id}: {e}", exc_info=True)
        
        asyncio.run(batch_repo.update_batch_status(
            batch_id,
            claim_id,
            'failed',
            error_message=str(e)
        ))
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        else:
            return {
                "claim_id": claim_id,
                "batch_id": batch_id,
                "status": "failed",
                "error": str(e)
            }

