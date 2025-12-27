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
    def from_decision_record(cls, record: dict) -> "DecisionResponse":
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
            approved_line_items=record.get("approved_line_items", []),
            ineligible_line_items=record.get("ineligible_line_items", []),
            flags=Flags(**record.get("flags", {})),
            missing_data=MissingData(**record.get("missing_data", {})),
            reasoning=record.get("reasoning", {}),
            confidence_score=float(record.get("confidence_score", 0.0)),
            engine_version=record["engine_version"],
            processing_time_ms=record.get("processing_time_ms"),
            decided_at=record["decided_at"],
        )

