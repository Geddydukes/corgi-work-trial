from pydantic import BaseModel, Field
from typing import Optional


class DecisionRequest(BaseModel):
    override_max_benefit: Optional[float] = Field(
        None,
        ge=0,
        le=999999.99,
        description="Override maximum benefit amount (optional)"
    )

