from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

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
        description="List of claim IDs to evaluate (unlimited size, ranges will be expanded)"
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


class LineItemOverride(BaseModel):
    line_item_index: int = Field(..., description="Index of the line item in the original list")
    user_should_be_included: bool = Field(..., description="User's decision on whether to include this item")
    user_reasoning: Optional[str] = Field(None, description="User's reason for the override")


class UpdateDecisionRequest(BaseModel):
    approved_line_items: List[LineItemOverride] = Field(
        default_factory=list,
        description="Line items that should be approved (with user overrides)"
    )
    ineligible_line_items: List[LineItemOverride] = Field(
        default_factory=list,
        description="Line items that should be ineligible (with user overrides)"
    )
    user_notes: Optional[str] = Field(None, description="General notes about the decision override")
    override_cap_amount: Optional[float] = Field(None, description="If provided, override the cap amount")
    cap_enabled: bool = Field(True, description="If false, ignore cap entirely")
    override_status: Optional[str] = Field(None, description="Override the decision status (e.g., 'approve' to override a 'deny')")


class ProcessFromDriveRequest(BaseModel):
    tracking_number: str = Field(..., description="Claim tracking number")
    drive_folder_id: str = Field(..., description="Google Drive folder ID (parent folder containing subfolders, or direct folder with documents)")
    override_max_benefit: Optional[float] = Field(None, description="Override max benefit for decision calculation")
