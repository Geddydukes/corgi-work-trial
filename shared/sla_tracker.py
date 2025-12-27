"""SLA tracking and violation detection."""

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from shared.config import Config

logger = logging.getLogger(__name__)


@dataclass
class SLAMetrics:
    """SLA metrics."""
    
    avg_time_ms: float = 0.0
    p95_time_ms: float = 0.0
    p99_time_ms: float = 0.0
    max_time_ms: float = 0.0
    violation_count: int = 0
    total_count: int = 0
    compliance_percentage: float = 100.0
    by_document_type: Dict[str, Dict[str, float]] = None


class SLATracker:
    """Tracks SLA compliance for document processing."""
    
    def __init__(self, window_size: int = 1000):
        """Initialize SLA tracker."""
        self.window_size = window_size
        self._processing_times = deque(maxlen=window_size)
        self._processing_times_by_type: Dict[str, deque] = {}
        self._violations = 0
        self._total = 0
    
    def record_processing_time(
        self,
        processing_time_ms: int,
        document_type: Optional[str] = None,
    ) -> bool:
        """
        Record a processing time.
        
        Args:
            processing_time_ms: Processing time in milliseconds
            document_type: Optional document type for per-type tracking
        
        Returns:
            True if SLA violated, False otherwise
        """
        self._processing_times.append(processing_time_ms)
        self._total += 1
        
        violated = False
        
        if processing_time_ms > Config.SLA_TARGET_MAX_MS:
            self._violations += 1
            violated = True
            logger.warning(f"SLA violation: {processing_time_ms}ms > {Config.SLA_TARGET_MAX_MS}ms max")
        
        if document_type:
            if document_type not in self._processing_times_by_type:
                self._processing_times_by_type[document_type] = deque(maxlen=self.window_size)
            self._processing_times_by_type[document_type].append(processing_time_ms)
        
        violation_rate = self._violations / self._total if self._total > 0 else 0.0
        
        if violation_rate > Config.SLA_ALERT_THRESHOLD:
            logger.error(
                f"SLA violation rate {violation_rate:.2%} exceeds threshold "
                f"{Config.SLA_ALERT_THRESHOLD:.2%}"
            )
        
        return violated
    
    def get_metrics(self) -> SLAMetrics:
        """Get current SLA metrics."""
        if not self._processing_times:
            return SLAMetrics()
        
        times = sorted(self._processing_times)
        count = len(times)
        
        avg = sum(times) / count
        p95_idx = int(count * 0.95)
        p99_idx = int(count * 0.99)
        
        p95 = times[p95_idx] if p95_idx < count else times[-1]
        p99 = times[p99_idx] if p99_idx < count else times[-1]
        max_time = times[-1]
        
        violations = sum(1 for t in times if t > Config.SLA_TARGET_MAX_MS)
        compliance = (1.0 - (violations / count)) * 100.0 if count > 0 else 100.0
        
        by_type = {}
        for doc_type, type_times in self._processing_times_by_type.items():
            if type_times:
                type_sorted = sorted(type_times)
                type_count = len(type_sorted)
                by_type[doc_type] = {
                    "avg": sum(type_sorted) / type_count,
                    "p95": type_sorted[int(type_count * 0.95)] if type_count > 0 else 0.0,
                    "p99": type_sorted[int(type_count * 0.99)] if type_count > 0 else 0.0,
                    "max": type_sorted[-1] if type_count > 0 else 0.0,
                    "count": type_count,
                }
        
        return SLAMetrics(
            avg_time_ms=avg,
            p95_time_ms=p95,
            p99_time_ms=p99,
            max_time_ms=max_time,
            violation_count=violations,
            total_count=count,
            compliance_percentage=compliance,
            by_document_type=by_type,
        )
    
    def check_sla_compliance(self) -> tuple[bool, Dict[str, bool]]:
        """
        Check SLA compliance against targets.
        
        Returns:
            Tuple of (overall_compliant, per_target_compliance)
        """
        metrics = self.get_metrics()
        
        if metrics.total_count == 0:
            return True, {}
        
        compliance = {
            "avg": metrics.avg_time_ms <= Config.SLA_TARGET_AVG_MS,
            "p95": metrics.p95_time_ms <= Config.SLA_TARGET_P95_MS,
            "p99": metrics.p99_time_ms <= Config.SLA_TARGET_P99_MS,
            "max": metrics.max_time_ms <= Config.SLA_TARGET_MAX_MS,
        }
        
        overall = all(compliance.values())
        
        return overall, compliance

