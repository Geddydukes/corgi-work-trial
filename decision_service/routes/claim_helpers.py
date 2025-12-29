"""
Helper functions for claim route operations.

These functions extract complex logic from route handlers to improve readability
and maintainability.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


def safe_json_load(value: Any, default: Any = None) -> Any:
    """
    Safely load JSON from a value that may be a string, already parsed, or None.
    
    Args:
        value: Value that may be a JSON string, already parsed dict/list, or None
        default: Default value to return if value is None or empty
    
    Returns:
        Parsed JSON value or default
    """
    if value is None:
        return default if default is not None else []
    
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else []
    
    return value if value else (default if default is not None else [])


def normalize_line_item(item: Any) -> Tuple[Dict, Dict]:
    """
    Normalize line item from various formats to standard format.
    
    Handles:
    - Items with 'line_item' and 'analysis' keys (complex format)
    - Simple dict items
    - Non-dict items (converts to dict)
    
    Args:
        item: Line item in any format
    
    Returns:
        Tuple of (line_item_data, analysis_data)
    """
    if isinstance(item, dict):
        if 'line_item' in item:
            line_item_data = item['line_item']
            analysis = item.get('analysis', {})
        else:
            line_item_data = item
            analysis = {}
    else:
        line_item_data = {'description': str(item), 'amount': 0}
        analysis = {}
    
    return line_item_data, analysis


def extract_reason(override: Optional[Dict], analysis: Dict, item: Dict) -> Optional[str]:
    """
    Extract reason from override, analysis, or item in priority order.
    
    Priority:
    1. Override reasoning (user input)
    2. Analysis reasoning/reason (system analysis)
    3. Item reason (fallback)
    
    Args:
        override: User override dict with optional 'reasoning' key
        analysis: Analysis dict with optional 'reasoning' or 'reason' key
        item: Item dict with optional 'reason' key
    
    Returns:
        Reason string or None
    """
    if override and override.get('reasoning'):
        return override['reasoning']
    
    if analysis:
        return analysis.get('reasoning') or analysis.get('reason')
    
    return item.get('reason') if isinstance(item, dict) else None


def build_simple_line_item(
    line_item_data: Dict,
    amount: float,
    reason: Optional[str]
) -> Dict:
    """
    Build a simple line item dict for response.
    
    Args:
        line_item_data: Line item data dict
        amount: Item amount
        reason: Item reason
    
    Returns:
        Simple line item dict
    """
    return {
        'description': line_item_data.get('description', ''),
        'amount': amount,
        'reason': reason
    }


def process_line_item_overrides(
    all_items: List[Dict],
    override_map: Dict[int, Dict],
    original_included_map: Dict[int, bool]
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Process line items based on user overrides.
    
    Args:
        all_items: All line items (approved + ineligible)
        override_map: Map of index -> override dict
        original_included_map: Map of index -> original included status
    
    Returns:
        Tuple of (new_approved_items, new_ineligible_items, overrides_to_save)
    """
    new_approved = []
    new_ineligible = []
    overrides_to_save = []
    
    for index, item in enumerate(all_items):
        original_included = original_included_map.get(index, False)
        override = override_map.get(index)
        
        should_be_included = (
            override['should_be_included'] 
            if override is not None 
            else original_included
        )
        
        line_item_data, analysis = normalize_line_item(item)
        reason = extract_reason(override, analysis, item)
        amount = float(line_item_data.get('amount', 0))
        simple_item = build_simple_line_item(line_item_data, amount, reason)
        
        if should_be_included:
            new_approved.append(simple_item)
        else:
            new_ineligible.append(simple_item)
        
        if override and override['should_be_included'] != original_included:
            overrides_to_save.append({
                'line_item_index': index,
                'line_item_description': line_item_data.get('description', ''),
                'line_item_amount': amount,
                'system_should_be_included': original_included,
                'system_categories': json.dumps({
                    'is_rent': item.get('is_rent', False) if isinstance(item, dict) else False,
                    'is_cleaning': item.get('is_cleaning', False) if isinstance(item, dict) else False,
                    'is_repair': item.get('is_repair', False) if isinstance(item, dict) else False,
                    'is_damage': item.get('is_damage', False) if isinstance(item, dict) else False,
                }),
                'system_reasoning': analysis.get('reasoning') or analysis.get('reason') if analysis else None,
                'system_confidence': float(analysis.get('confidence', 0.5)) if analysis and analysis.get('confidence') else None,
                'user_should_be_included': override['should_be_included'],
                'user_reasoning': override.get('reasoning')
            })
    
    return new_approved, new_ineligible, overrides_to_save


def calculate_cap_amount(
    cap_enabled: bool,
    override_cap_amount: Optional[float],
    original_cap_amount: Optional[float]
) -> Optional[float]:
    """
    Calculate the effective cap amount.
    
    Args:
        cap_enabled: Whether cap is enabled
        override_cap_amount: User override cap amount
        original_cap_amount: Original cap amount from decision
    
    Returns:
        Effective cap amount or None
    """
    if not cap_enabled:
        return None
    
    if override_cap_amount is not None:
        return float(override_cap_amount)
    
    return float(original_cap_amount) if original_cap_amount else None


def determine_new_status(
    original_status: str,
    override_status: Optional[str],
    new_proposed_benefit: float,
    new_approved_count: int
) -> str:
    """
    Determine the new decision status.
    
    Args:
        original_status: Original decision status
        override_status: User override status
        new_proposed_benefit: New proposed benefit amount
        new_approved_count: Number of approved items
    
    Returns:
        New status string
    """
    new_status = original_status
    
    if override_status:
        if override_status.lower() in ['approve', 'deny', 'pending']:
            new_status = override_status.lower()
        else:
            logger.warning(f"Invalid status override: {override_status}, keeping original status")
    
    if new_proposed_benefit > 0 and new_status == 'deny':
        if override_status and override_status.lower() == 'approve':
            new_status = 'approve'
        elif new_approved_count > 0:
            new_status = 'approve'
    
    return new_status


def build_decision_record_dict(
    updated_dict: Dict,
    tracking_number: Optional[str],
    claim: Dict,
    new_approved: List[Dict],
    new_ineligible: List[Dict]
) -> Dict:
    """
    Build decision record dictionary for response.
    
    Args:
        updated_dict: Dictionary from updated decision query
        tracking_number: Claim tracking number
        claim: Claim dictionary
        new_approved: New approved line items
        new_ineligible: New ineligible line items
    
    Returns:
        Decision record dictionary
    """
    return {
        "id": updated_dict['id'],
        "claim_id": updated_dict['claim_id'],
        "tracking_number": tracking_number,
        "decision_type": updated_dict['decision_type'],
        "proposed_status": updated_dict['proposed_status'],
        "proposed_benefit_amount": float(updated_dict['proposed_benefit_amount']),
        "eligible_total": float(updated_dict['eligible_total']),
        "invoice_total": float(updated_dict['invoice_total']),
        "cap_amount": float(updated_dict['cap_amount']) if updated_dict['cap_amount'] else None,
        "claim_amount": float(claim.get('claim_amount', 0)),
        "max_benefit": float(claim.get('max_benefit', 0)) if claim.get('max_benefit') else None,
        "document_count": 0,
        "line_item_count": len(new_approved) + len(new_ineligible),
        "approved_line_items": new_approved,
        "ineligible_line_items": new_ineligible,
        "flags": safe_json_load(updated_dict['flags'], default={}),
        "missing_data": safe_json_load(updated_dict['missing_data'], default={}),
        "reasoning": safe_json_load(updated_dict['reasoning'], default={}),
        "confidence_score": float(updated_dict['confidence_score']) if updated_dict['confidence_score'] else 0.0,
        "engine_version": updated_dict['engine_version'],
        "processing_time_ms": updated_dict['processing_time_ms'],
        "decided_at": updated_dict['decided_at'],
    }

