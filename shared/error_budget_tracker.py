"""Error budget tracking for low OCR confidence cases."""

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from shared.config import Config

logger = logging.getLogger(__name__)


@dataclass
class ErrorBudgetMetrics:
    """Error budget metrics."""
    
    total_documents: int = 0
    low_confidence_count: int = 0
    error_rate: float = 0.0
    budget_consumed: float = 0.0
    budget_remaining: float = 1.0
    by_tier: Dict[str, Dict[str, int]] = None


class ErrorBudgetTracker:
    """Tracks error budget for low OCR confidence cases."""
    
    def __init__(self, window_hours: int = None):
        """Initialize error budget tracker."""
        self.window_hours = window_hours or Config.ERROR_BUDGET_WINDOW_HOURS
        self.window_seconds = self.window_hours * 3600
        
        self._documents = deque()
        self._low_confidence = deque()
        self._by_tier: Dict[str, Dict[str, int]] = {
            "tier1": {"total": 0, "low_conf": 0},
            "tier2": {"total": 0, "low_conf": 0},
            "tier3": {"total": 0, "low_conf": 0},
        }
    
    def record_document(
        self,
        confidence: float,
        tier: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> bool:
        """
        Record a document processing result.
        
        Args:
            confidence: OCR confidence score (0-100)
            tier: OCR tier used
            timestamp: Processing timestamp (defaults to now)
        
        Returns:
            True if budget exceeded, False otherwise
        """
        now = timestamp or time.time()
        
        self._documents.append(now)
        self._clean_old_records(now)
        
        is_low_confidence = confidence < Config.OCR_LOW_CONFIDENCE_THRESHOLD
        
        if is_low_confidence:
            self._low_confidence.append(now)
        
        if tier:
            tier_key = tier.lower().replace("tier", "tier")
            if tier_key in self._by_tier:
                self._by_tier[tier_key]["total"] += 1
                if is_low_confidence:
                    self._by_tier[tier_key]["low_conf"] += 1
        
        metrics = self._calculate_metrics()
        
        if metrics.budget_consumed >= Config.ERROR_BUDGET_ALERT_THRESHOLD:
            logger.warning(
                f"Error budget {metrics.budget_consumed:.2%} consumed "
                f"(threshold: {Config.ERROR_BUDGET_ALERT_THRESHOLD:.2%})"
            )
        
        if metrics.budget_consumed >= 1.0:
            logger.error(
                f"Error budget exhausted: {metrics.error_rate:.2%} error rate "
                f"(budget: {Config.OCR_ERROR_BUDGET_PERCENTAGE:.2%})"
            )
            return True
        
        return False
    
    def _clean_old_records(self, now: float) -> None:
        """Remove records outside the time window."""
        cutoff = now - self.window_seconds
        
        while self._documents and self._documents[0] < cutoff:
            self._documents.popleft()
        
        while self._low_confidence and self._low_confidence[0] < cutoff:
            self._low_confidence.popleft()
    
    def _calculate_metrics(self) -> ErrorBudgetMetrics:
        """Calculate current error budget metrics."""
        total = len(self._documents)
        low_conf = len(self._low_confidence)
        
        error_rate = (low_conf / total) if total > 0 else 0.0
        budget_consumed = error_rate / Config.OCR_ERROR_BUDGET_PERCENTAGE if Config.OCR_ERROR_BUDGET_PERCENTAGE > 0 else 0.0
        budget_remaining = max(0.0, 1.0 - budget_consumed)
        
        return ErrorBudgetMetrics(
            total_documents=total,
            low_confidence_count=low_conf,
            error_rate=error_rate,
            budget_consumed=budget_consumed,
            budget_remaining=budget_remaining,
            by_tier=self._by_tier.copy(),
        )
    
    def get_metrics(self) -> ErrorBudgetMetrics:
        """Get current error budget metrics."""
        return self._calculate_metrics()
    
    def should_escalate(self) -> bool:
        """
        Determine if processing should escalate to Tier 3.
        
        Returns:
            True if error budget exhausted
        """
        metrics = self.get_metrics()
        return metrics.budget_consumed >= 1.0
















