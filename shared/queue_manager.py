"""Queue management with parallelism and depth limits."""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from shared.config import Config

logger = logging.getLogger(__name__)


@dataclass
class QueueMetrics:
    """Queue metrics."""
    
    current_depth: int = 0
    max_depth: int = 0
    active_workers: int = 0
    total_processed: int = 0
    total_rejected: int = 0
    avg_wait_time_ms: float = 0.0


class QueueManager:
    """Manages document processing queue with concurrency and depth limits."""
    
    def __init__(self):
        """Initialize queue manager."""
        self._semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_WORKERS)
        self._queue_depth = 0
        self._active_workers = 0
        self._total_processed = 0
        self._total_rejected = 0
        self._wait_times = []
        self._rate_limiters = defaultdict(lambda: {"tokens": Config.RATE_LIMIT_PER_CLAIM, "last_refill": time.time()})
        self._user_rate_limiters = defaultdict(lambda: {"tokens": Config.RATE_LIMIT_PER_USER, "last_refill": time.time()})
    
    async def acquire(self, claim_id: Optional[int] = None, user_id: Optional[str] = None) -> bool:
        """
        Acquire a processing slot.
        
        Args:
            claim_id: Optional claim ID for rate limiting
            user_id: Optional user ID for rate limiting
        
        Returns:
            True if slot acquired, False if rejected
        """
        if self._queue_depth >= Config.MAX_QUEUE_DEPTH:
            self._total_rejected += 1
            logger.warning(f"Queue depth limit reached: {self._queue_depth}/{Config.MAX_QUEUE_DEPTH}")
            return False
        
        if claim_id and not self._check_rate_limit(claim_id, is_user=False):
            self._total_rejected += 1
            logger.warning(f"Rate limit exceeded for claim {claim_id}")
            return False
        
        if user_id and not self._check_rate_limit(user_id, is_user=True):
            self._total_rejected += 1
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False
        
        if self._queue_depth >= Config.QUEUE_WARNING_THRESHOLD:
            logger.warning(f"Queue depth approaching limit: {self._queue_depth}/{Config.MAX_QUEUE_DEPTH}")
        
        self._queue_depth += 1
        wait_start = time.time()
        
        try:
            await self._semaphore.acquire()
            wait_time = (time.time() - wait_start) * 1000
            self._wait_times.append(wait_time)
            if len(self._wait_times) > 1000:
                self._wait_times = self._wait_times[-1000:]
            
            self._active_workers += 1
            self._queue_depth -= 1
            return True
        except Exception as e:
            logger.error(f"Error acquiring queue slot: {e}")
            self._queue_depth -= 1
            return False
    
    def release(self) -> None:
        """Release a processing slot."""
        self._active_workers = max(0, self._active_workers - 1)
        self._total_processed += 1
        self._semaphore.release()
    
    def _check_rate_limit(self, identifier: str, is_user: bool = False) -> bool:
        """Check rate limit using token bucket algorithm."""
        limit = Config.RATE_LIMIT_PER_USER if is_user else Config.RATE_LIMIT_PER_CLAIM
        limiter = self._user_rate_limiters[identifier] if is_user else self._rate_limiters[identifier]
        
        now = time.time()
        elapsed = now - limiter["last_refill"]
        
        tokens_to_add = int(elapsed * (limit / 60.0))
        limiter["tokens"] = min(limit, limiter["tokens"] + tokens_to_add)
        limiter["last_refill"] = now
        
        if limiter["tokens"] >= 1:
            limiter["tokens"] -= 1
            return True
        
        return False
    
    def get_metrics(self) -> QueueMetrics:
        """Get current queue metrics."""
        avg_wait = sum(self._wait_times) / len(self._wait_times) if self._wait_times else 0.0
        
        return QueueMetrics(
            current_depth=self._queue_depth,
            max_depth=Config.MAX_QUEUE_DEPTH,
            active_workers=self._active_workers,
            total_processed=self._total_processed,
            total_rejected=self._total_rejected,
            avg_wait_time_ms=avg_wait,
        )
    
    def reset_rate_limits(self) -> None:
        """Reset all rate limiters (for testing)."""
        self._rate_limiters.clear()
        self._user_rate_limiters.clear()


















