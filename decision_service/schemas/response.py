from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional
from decimal import Decimal


class LineItem(BaseModel):
    description: str
    amount: float
    reason: Optional[str] = None


class Flags(BaseModel):
    critical: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    info: List[str] = Field(default_factory=list)


class MissingData(BaseModel):
    fields: List[str] = Field(default_factory=list)
    needs_user_input: bool = False


class DecisionResponse(BaseModel):
    decision_id: int
    claim_id: int
    tracking_number: str
    decision_type: str
    proposed_status: str
    proposed_benefit_amount: float
    eligible_total: float
    invoice_total: float
    cap_amount: Optional[float] = None
    claim_amount: float
    max_benefit: Optional[float] = None
    document_count: int
    line_item_count: int
    approved_line_items: List[LineItem] = Field(default_factory=list)
    ineligible_line_items: List[LineItem] = Field(default_factory=list)
    flags: Flags = Field(default_factory=Flags)
    missing_data: MissingData = Field(default_factory=MissingData)
    reasoning: Dict = Field(default_factory=dict)
    confidence_score: float
    engine_version: str
    processing_time_ms: Optional[int] = None
    decided_at: datetime
    
    @classmethod
    def _normalize_line_items(cls, items: list) -> List[LineItem]:
        """Convert line items from complex format to simple LineItem format."""
        normalized = []
        for item in items:
            if isinstance(item, dict):
                if "line_item" in item:
                    line_item_data = item["line_item"]
                    analysis = item.get("analysis", {})
                    normalized.append(LineItem(
                        description=line_item_data.get("description", ""),
                        amount=float(line_item_data.get("amount", 0)),
                        reason=analysis.get("reasoning") or analysis.get("reason") or None
                    ))
                elif "description" in item and "amount" in item:
                    normalized.append(LineItem(
                        description=item.get("description", ""),
                        amount=float(item.get("amount", 0)),
                        reason=item.get("reason")
                    ))
        return normalized
    
    @classmethod
    def from_decision_record(cls, record: dict) -> "DecisionResponse":
        approved_items = cls._normalize_line_items(record.get("approved_line_items", []))
        ineligible_items = cls._normalize_line_items(record.get("ineligible_line_items", []))
        
        return cls(
            decision_id=record["id"],
            claim_id=record["claim_id"],
            tracking_number=record.get("tracking_number", ""),
            decision_type=record["decision_type"],
            proposed_status=record["proposed_status"],
            proposed_benefit_amount=float(record["proposed_benefit_amount"]),
            eligible_total=float(record["eligible_total"]),
            invoice_total=float(record["invoice_total"]),
            cap_amount=float(record["cap_amount"]) if record.get("cap_amount") else None,
            claim_amount=float(record.get("claim_amount", 0.0)),
            max_benefit=float(record["max_benefit"]) if record.get("max_benefit") else None,
            document_count=record.get("document_count", 0),
            line_item_count=record.get("line_item_count", 0),
            approved_line_items=approved_items,
            ineligible_line_items=ineligible_items,
            flags=Flags(**record.get("flags", {})),
            missing_data=MissingData(**record.get("missing_data", {})),
            reasoning=record.get("reasoning", {}),
            confidence_score=float(record.get("confidence_score", 0.0)),
            engine_version=record["engine_version"],
            processing_time_ms=record.get("processing_time_ms"),
            decided_at=record["decided_at"],
        )


class BatchEvaluationResponse(BaseModel):
    batch_id: str
    estimated_completion: datetime
    claim_count: int
    status: str


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: str
    claim_count: int
    processed_count: int
    successful_count: int
    failed_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

