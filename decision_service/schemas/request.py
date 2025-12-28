from pydantic import BaseModel, Field
from typing import Optional, List


class DecisionRequest(BaseModel):
    override_max_benefit: Optional[float] = Field(
        None,
        ge=0,
        le=999999.99,
        description="Override maximum benefit amount (optional)"
    )


class BatchEvaluationRequest(BaseModel):
    claim_ids: List[int] = Field(
        ...,
        min_items=1,
        max_items=1000,
        description="List of claim IDs to evaluate"
    )
    webhook_url: Optional[str] = Field(
        None,
        description="Webhook URL for completion notification"
    )
    priority: int = Field(
        0,
        ge=0,
        description="Processing priority (higher = more urgent)"
    )

