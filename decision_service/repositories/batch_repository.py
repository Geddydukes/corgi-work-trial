import logging
from typing import Optional, Dict, List
from datetime import datetime
from uuid import UUID

logger = logging.getLogger(__name__)


class BatchRepository:
    async def create_batch_job(
        self,
        claim_ids: List[int],
        webhook_url: Optional[str] = None,
        priority: int = 0
    ) -> str:
        from shared.config import Config
        from sqlalchemy import create_engine, text
        from uuid import uuid4
        
        batch_id = str(uuid4())
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock batch_id")
            return batch_id
        
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                for claim_id in claim_ids:
                    conn.execute(
                        text("""
                            INSERT INTO processing_queue (
                                batch_id, claim_id, priority, status, scheduled_at
                            ) VALUES (
                                :batch_id, :claim_id, :priority, 'pending', NOW()
                            )
                        """),
                        {
                            'batch_id': batch_id,
                            'claim_id': claim_id,
                            'priority': priority
                        }
                    )
                
                conn.commit()
                return batch_id
        except Exception as e:
            logger.error(f"Error creating batch job: {e}", exc_info=True)
            raise
    
    async def get_batch_job(self, batch_id: str) -> Optional[Dict]:
        from shared.config import Config
        from sqlalchemy import create_engine, text
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock batch status")
            return {
                "batch_id": batch_id,
                "status": "processing",
                "claim_count": 10,
                "processed_count": 5,
                "successful_count": 4,
                "failed_count": 1,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
            }
        
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                result = conn.execute(
                    text("""
                        SELECT 
                            COUNT(*) as claim_count,
                            COUNT(CASE WHEN status IN ('completed', 'failed') THEN 1 END) as processed_count,
                            COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_count,
                            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count,
                            MIN(scheduled_at) as started_at,
                            MAX(completed_at) as completed_at,
                            CASE 
                                WHEN COUNT(*) = 0 THEN 'pending'
                                WHEN COUNT(CASE WHEN status IN ('completed', 'failed') THEN 1 END) = COUNT(*) 
                                    AND COUNT(CASE WHEN status = 'failed' THEN 1 END) = COUNT(*)
                                THEN 'failed'
                                WHEN COUNT(CASE WHEN status IN ('completed', 'failed') THEN 1 END) = COUNT(*)
                                THEN 'completed'
                                WHEN COUNT(CASE WHEN status = 'processing' THEN 1 END) > 0
                                THEN 'processing'
                                ELSE 'pending'
                            END as status
                        FROM processing_queue
                        WHERE batch_id = :batch_id
                    """),
                    {"batch_id": batch_id}
                ).fetchone()
                
                if not result or result[0] == 0:
                    return None
                
                return {
                    "batch_id": batch_id,
                    "status": result[6],
                    "claim_count": result[0],
                    "processed_count": result[1],
                    "successful_count": result[2],
                    "failed_count": result[3],
                    "started_at": result[4].isoformat() if result[4] else None,
                    "completed_at": result[5].isoformat() if result[5] else None,
                }
        except Exception as e:
            logger.error(f"Error fetching batch job {batch_id}: {e}", exc_info=True)
            return None
    
    async def update_batch_status(
        self,
        batch_id: str,
        claim_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        from shared.config import Config
        from sqlalchemy import create_engine, text
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, skipping update")
            return True
        
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                update_data = {
                    'batch_id': batch_id,
                    'claim_id': claim_id,
                    'status': status
                }
                
                if status == 'processing':
                    conn.execute(
                        text("""
                            UPDATE processing_queue
                            SET status = :status, started_at = NOW()
                            WHERE batch_id = :batch_id AND claim_id = :claim_id
                        """),
                        {**update_data}
                    )
                elif status in ('completed', 'failed'):
                    update_sql = """
                        UPDATE processing_queue
                        SET status = :status, completed_at = NOW()
                    """
                    if error_message:
                        update_sql = update_sql.replace("completed_at = NOW()", "completed_at = NOW(), error_message = :error_message")
                        update_data['error_message'] = error_message
                    update_sql += " WHERE batch_id = :batch_id AND claim_id = :claim_id"
                    
                    conn.execute(text(update_sql), update_data)
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating batch status: {e}", exc_info=True)
            return False
    
    async def get_batch_claims(self, batch_id: str) -> List[int]:
        from shared.config import Config
        from sqlalchemy import create_engine, text
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning empty list")
            return []
        
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                result = conn.execute(
                    text("""
                        SELECT DISTINCT claim_id
                        FROM processing_queue
                        WHERE batch_id = :batch_id
                        ORDER BY claim_id
                    """),
                    {"batch_id": batch_id}
                ).fetchall()
                
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error fetching batch claims: {e}", exc_info=True)
            return []

