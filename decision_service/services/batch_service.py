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
        priority: int = 0,
        background_tasks = None
    ) -> Dict:
        # Note: No limit on batch size - can process unlimited claims
        # Frontend should expand ranges like "904-940" before sending
        logger.info(f"Processing batch with {len(claim_ids)} claim IDs")
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.engine.decision_engine import DecisionEngine
        from shared.config import Config
        
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
        
        # Try to use Celery if Redis is available, otherwise process synchronously
        redis_available = False
        try:
            import redis
            if Config.REDIS_URL:
                redis_client = redis.from_url(Config.REDIS_URL, socket_connect_timeout=1)
                redis_client.ping()
                redis_available = True
        except Exception as e:
            logger.warning(f"Redis not available, processing batch synchronously: {e}")
        
        if redis_available:
            # Use Celery for asynchronous processing
            try:
                from tasks.celery_app import evaluate_claim_task
                for claim_id in valid_claim_ids:
                    evaluate_claim_task.delay(claim_id, batch_id)
                logger.info(f"Batch {batch_id} submitted to Celery queue")
            except Exception as e:
                logger.warning(f"Failed to submit to Celery, falling back to sync processing: {e}")
                redis_available = False
        
        if not redis_available:
            # Process synchronously using FastAPI BackgroundTasks
            if background_tasks is None:
                # Fallback to asyncio if BackgroundTasks not provided
                import asyncio
                task = asyncio.create_task(self._process_batch_sync(batch_id, valid_claim_ids))
                # Add done callback to log any unhandled exceptions
                def log_task_error(task):
                    try:
                        task.result()  # This will raise if task had an exception
                    except Exception as e:
                        logger.error(f"Unhandled exception in background task for batch {batch_id}: {e}", exc_info=True)
                task.add_done_callback(log_task_error)
                logger.warning(f"BackgroundTasks not provided, using asyncio.create_task for batch {batch_id}")
            else:
                # Use FastAPI BackgroundTasks - BackgroundTasks can handle async functions
                # Wrap to ensure exceptions don't crash the server
                async def safe_process():
                    try:
                        await self._process_batch_sync(batch_id, valid_claim_ids)
                    except Exception as e:
                        logger.error(f"Unhandled exception in background task for batch {batch_id}: {e}", exc_info=True)
                background_tasks.add_task(safe_process)
            logger.info(f"Batch {batch_id} processing synchronously (Redis unavailable)")
        
        estimated_completion = datetime.utcnow() + timedelta(
            seconds=len(valid_claim_ids) * 3
        )
        
        return {
            "batch_id": batch_id,
            "estimated_completion": estimated_completion.isoformat(),
            "claim_count": len(valid_claim_ids),
            "status": "pending"
        }
    
    async def _process_batch_sync(self, batch_id: str, claim_ids: List[int]):
        """Process batch claims synchronously when Redis/Celery is not available.
        
        Processes claims in chunks to avoid overwhelming the server.
        """
        try:
            from decision_service.repositories.claim_repository import ClaimRepository
            from decision_service.engine.decision_engine import DecisionEngine
            import asyncio
            
            claim_repo = ClaimRepository()
            engine = DecisionEngine()
            
            logger.info(f"Starting batch processing for batch {batch_id} with {len(claim_ids)} claims")
            
            # Process claims with controlled concurrency to avoid overwhelming the server
            # Use semaphore to limit concurrent evaluations (each can be CPU/API intensive)
            # Using 2 concurrent to balance speed with stability (avoiding connection pool issues)
            MAX_CONCURRENT = 2  # Process up to 2 claims concurrently for stability
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            async def process_single_claim(claim_id: int):
                """Process a single claim with semaphore limiting concurrency."""
                async with semaphore:
                    try:
                        # Update status to processing
                        await self.batch_repository.update_batch_status(batch_id, claim_id, 'processing')
                        
                        # Always evaluate the claim - the decision creation will handle duplicates
                        # (Removed existence check to avoid connection pool double-free issues in concurrent code)
                        logger.info(f"Evaluating claim {claim_id}")
                        
                        # Check if claim has documents before processing
                        from decision_service.repositories.document_repository import DocumentRepository
                        doc_repo = DocumentRepository()
                        documents = await doc_repo.get_documents(claim_id)
                        
                        if not documents:
                            logger.warning(f"Claim {claim_id} has no documents - will result in $0 decision. Skipping evaluation.")
                            # Mark as failed since we can't evaluate without documents
                            await self.batch_repository.update_batch_status(
                                batch_id,
                                claim_id,
                                'failed',
                                error_message="Claim has no documents - cannot evaluate"
                            )
                            return  # Skip this claim
                        
                        logger.info(f"Claim {claim_id} has {len(documents)} documents, proceeding with evaluation")
                        decision = await engine.evaluate_claim(claim_id=claim_id)
                        
                        # Log decision details for debugging
                        logger.info(f"Claim {claim_id} decision: status={decision.proposed_status}, amount=${decision.proposed_benefit_amount}, line_items={decision.line_item_count}")
                        
                        await claim_repo.create_decision(decision, user_id="system")
                        
                        # Update status to completed
                        await self.batch_repository.update_batch_status(batch_id, claim_id, 'completed')
                        
                        logger.info(f"Processed claim {claim_id} in batch {batch_id}")
                    except Exception as e:
                        logger.error(f"Error processing claim {claim_id} in batch {batch_id}: {e}", exc_info=True)
                        try:
                            await self.batch_repository.update_batch_status(
                                batch_id, 
                                claim_id, 
                                'failed',
                                error_message=str(e)
                            )
                        except Exception as update_error:
                            logger.error(f"Failed to update batch status to failed: {update_error}", exc_info=True)
            
            # Process all claims with controlled concurrency
            tasks = [process_single_claim(claim_id) for claim_id in claim_ids]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            logger.info(f"Completed batch processing for batch {batch_id}")
        except Exception as e:
            logger.error(f"Critical error in batch processing for batch {batch_id}: {e}", exc_info=True)
            # Don't re-raise - log and continue to prevent server crash
    
    async def get_batch_status(self, batch_id: str) -> Optional[Dict]:
        batch_job = await self.batch_repository.get_batch_job(batch_id)
        
        if not batch_job:
            return None
        
        return batch_job












