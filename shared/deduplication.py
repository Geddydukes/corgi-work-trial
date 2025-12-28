import logging
from typing import Optional
from datetime import datetime, timedelta

import redis

from shared.config import Config
from shared.models import DocumentProcessingResult

logger = logging.getLogger(__name__)


class DeduplicationService:
    def __init__(self):
        self.redis_client = None
        self.redis_available = False
        
        if not Config.REDIS_URL:
            logger.debug("Redis URL not configured, caching disabled")
            return
        
        try:
            self.redis_client = redis.from_url(Config.REDIS_URL, socket_connect_timeout=1)
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            logger.debug("Redis cache connected")
        except Exception as e:
            logger.debug(f"Redis not available (caching disabled): {e}")
            self.redis_client = None
    
    def get_cached_result(self, file_hash: str) -> Optional[dict]:
        if not self.redis_available or not self.redis_client:
            return None
        
        try:
            cache_key = f"doc_result:{file_hash}"
            cached = self.redis_client.get(cache_key)
            
            if cached:
                import json
                return json.loads(cached)
        except Exception as e:
            # Redis connection lost, disable caching for this session
            self.redis_available = False
            logger.debug(f"Cache retrieval error (caching disabled): {e}")
        
        return None
    
    def cache_result(self, file_hash: str, result: DocumentProcessingResult) -> None:
        if not self.redis_available or not self.redis_client:
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
            # Redis connection lost, disable caching for this session
            self.redis_available = False
            logger.debug(f"Cache storage error (caching disabled): {e}")
    
    def check_duplicate(self, file_hash: str) -> bool:
        return self.get_cached_result(file_hash) is not None

