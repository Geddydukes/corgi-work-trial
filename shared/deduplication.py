import logging
from typing import Optional
from datetime import datetime, timedelta

import redis

from shared.config import Config
from shared.models import DocumentProcessingResult

logger = logging.getLogger(__name__)


class DeduplicationService:
    def __init__(self):
        try:
            self.redis_client = redis.from_url(Config.REDIS_URL) if Config.REDIS_URL else None
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            self.redis_client = None
    
    def get_cached_result(self, file_hash: str) -> Optional[dict]:
        if not self.redis_client:
            return None
        
        try:
            cache_key = f"doc_result:{file_hash}"
            cached = self.redis_client.get(cache_key)
            
            if cached:
                import json
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
        
        return None
    
    def cache_result(self, file_hash: str, result: DocumentProcessingResult) -> None:
        if not self.redis_client:
            return
        
        try:
            cache_key = f"doc_result:{file_hash}"
            ttl_seconds = Config.DEDUP_CACHE_TTL_DAYS * 24 * 60 * 60
            
            import json
            self.redis_client.setex(
                cache_key,
                ttl_seconds,
                json.dumps(result.to_dict(), default=str),
            )
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")
    
    def check_duplicate(self, file_hash: str) -> bool:
        return self.get_cached_result(file_hash) is not None

