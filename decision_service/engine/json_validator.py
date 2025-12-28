"""
JSON validation utilities for Gemini responses.
"""

import json
import logging
from typing import Dict, List, Any, Tuple, Optional, Callable
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class LineItemAnalysis:
    """Validated line item analysis structure."""
    line_item_number: int
    should_be_included: bool
    is_normal_wear_tear: bool
    is_covered_by_addendum: bool
    is_covered_by_other_insurance: bool
    confidence: float
    reasoning: str
    addendum_reference: str


def extract_json_from_response(response_text: str) -> Tuple[Optional[str], List[str]]:
    """
    Extract JSON from Gemini response, handling markdown code blocks.
    
    Returns:
        (extracted_json_text, list_of_errors)
    """
    errors = []
    original_text = response_text.strip()
    
    # Try to extract from markdown code blocks
    if '```json' in original_text:
        json_start = original_text.find('```json') + 7
        json_end = original_text.find('```', json_start)
        if json_end == -1:
            json_end = len(original_text)
        extracted = original_text[json_start:json_end].strip()
    elif '```' in original_text:
        json_start = original_text.find('```') + 3
        json_end = original_text.find('```', json_start)
        if json_end == -1:
            json_end = len(original_text)
        extracted = original_text[json_start:json_end].strip()
    else:
        extracted = original_text
    
    if not extracted:
        errors.append("No JSON content found in response")
        return None, errors
    
    return extracted, errors


def validate_line_item_analysis_response(
    response: Dict[str, Any],
    expected_count: int
) -> Tuple[bool, List[str], Optional[List[LineItemAnalysis]]]:
    """
    Validate the line item analysis JSON response structure.
    
    Args:
        response: Parsed JSON response
        expected_count: Expected number of line item analyses
    
    Returns:
        (is_valid, list_of_errors, validated_analyses)
    """
    errors = []
    
    # Check root structure
    if 'line_item_analyses' not in response:
        return False, ["Missing 'line_item_analyses' field"], None
    
    analyses = response['line_item_analyses']
    
    # Check it's a list
    if not isinstance(analyses, list):
        return False, [f"'line_item_analyses' must be an array, got {type(analyses).__name__}"], None
    
    # Check array length
    if len(analyses) != expected_count:
        errors.append(f"Expected {expected_count} analyses, got {len(analyses)}")
    
    validated_analyses = []
    
    # Validate each analysis
    for i, analysis in enumerate(analyses):
        prefix = f"Analysis {i+1}:"
        
        if not isinstance(analysis, dict):
            errors.append(f"{prefix} Must be an object, got {type(analysis).__name__}")
            continue
        
        # Check required fields
        required_fields = {
            'line_item_number': int,
            'should_be_included': bool,
            'is_normal_wear_tear': bool,
            'is_covered_by_addendum': bool,
            'is_covered_by_other_insurance': bool,
            'confidence': (int, float),
            'reasoning': str,
            'addendum_reference': str
        }
        
        analysis_dict = {}
        has_errors = False
        
        for field, expected_type in required_fields.items():
            if field not in analysis:
                errors.append(f"{prefix} Missing required field '{field}'")
                has_errors = True
                continue
            
            value = analysis[field]
            
            # Type validation
            if field == 'line_item_number':
                if not isinstance(value, int):
                    errors.append(f"{prefix} 'line_item_number' must be integer, got {type(value).__name__}")
                    has_errors = True
                elif value != i + 1:
                    errors.append(f"{prefix} 'line_item_number' should be {i+1}, got {value}")
                else:
                    analysis_dict['line_item_number'] = value
            
            elif field in ['should_be_included', 'is_normal_wear_tear', 'is_covered_by_addendum', 'is_covered_by_other_insurance']:
                # Handle string booleans
                if isinstance(value, str):
                    if value.lower() in ['true', '1', 'yes']:
                        value = True
                    elif value.lower() in ['false', '0', 'no']:
                        value = False
                    else:
                        errors.append(f"{prefix} '{field}' must be boolean, got string '{value}'")
                        has_errors = True
                        continue
                
                if not isinstance(value, bool):
                    errors.append(f"{prefix} '{field}' must be boolean, got {type(value).__name__}")
                    has_errors = True
                else:
                    analysis_dict[field] = value
            
            elif field == 'confidence':
                # Handle string numbers
                if isinstance(value, str):
                    try:
                        value = float(value)
                    except ValueError:
                        errors.append(f"{prefix} 'confidence' must be number, got string '{value}'")
                        has_errors = True
                        continue
                
                if not isinstance(value, (int, float)):
                    errors.append(f"{prefix} 'confidence' must be number, got {type(value).__name__}")
                    has_errors = True
                elif not (0.0 <= float(value) <= 1.0):
                    errors.append(f"{prefix} 'confidence' must be between 0.0 and 1.0, got {value}")
                    has_errors = True
                else:
                    analysis_dict['confidence'] = float(value)
            
            elif field in ['reasoning', 'addendum_reference']:
                if not isinstance(value, str):
                    errors.append(f"{prefix} '{field}' must be string, got {type(value).__name__}")
                    has_errors = True
                elif field == 'reasoning' and not value.strip():
                    errors.append(f"{prefix} 'reasoning' must be non-empty string")
                    has_errors = True
                else:
                    analysis_dict[field] = value
        
        if not has_errors:
            try:
                validated = LineItemAnalysis(**analysis_dict)
                validated_analyses.append(validated)
            except TypeError as e:
                errors.append(f"{prefix} Failed to create LineItemAnalysis: {e}")
    
    is_valid = len(errors) == 0
    return is_valid, errors, validated_analyses if is_valid else None


def create_default_include_analyses(
    expected_count: int
) -> List[LineItemAnalysis]:
    """
    Create default-include analyses for JSON validation failures.
    
    This prevents silent denials when LLM output is invalid.
    Deterministic rules will filter these appropriately.
    
    Args:
        expected_count: Number of analyses to create
    
    Returns:
        List of LineItemAnalysis with should_be_included=True
    """
    analyses = []
    for i in range(expected_count):
        analysis = LineItemAnalysis(
            line_item_number=i + 1,
            should_be_included=True,
            is_normal_wear_tear=False,
            is_covered_by_addendum=True,
            is_covered_by_other_insurance=False,
            confidence=0.3,
            reasoning="JSON validation failed, defaulting to include (deterministic rules will filter)",
            addendum_reference="N/A"
        )
        analyses.append(analysis)
    return analyses


def parse_and_validate_line_item_analysis(
    response_text: str,
    expected_count: int,
    max_retries: int = 2,
    default_on_failure: bool = True
) -> Tuple[Optional[List[LineItemAnalysis]], List[str], bool]:
    """
    Parse JSON from response and validate structure.
    
    Args:
        response_text: Raw response text from Gemini
        expected_count: Expected number of line item analyses
        max_retries: Maximum retry attempts if parsing fails
        default_on_failure: If True, return default-include analyses on failure
    
    Returns:
        (validated_analyses, list_of_errors, json_validation_failed_flag)
    """
    errors = []
    json_validation_failed = False
    
    # Extract JSON
    extracted_json, extract_errors = extract_json_from_response(response_text)
    if extract_errors:
        errors.extend(extract_errors)
        if not extracted_json:
            logger.error(f"Failed to extract JSON: {errors}")
            logger.error(f"Response preview: {response_text[:500]}")
            if default_on_failure:
                logger.warning("Returning default-include analyses due to JSON extraction failure")
                return create_default_include_analyses(expected_count), errors, True
            return None, errors, True
    
    # Try to parse JSON
    for attempt in range(max_retries):
        try:
            result = json.loads(extracted_json)
            break
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                # Try to fix common issues
                extracted_json = extracted_json.replace("'", '"')  # Replace single quotes
                continue
            else:
                errors.append(f"Invalid JSON (attempt {attempt + 1}): {str(e)}")
                errors.append(f"JSON preview: {extracted_json[:200]}")
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Full response: {response_text[:1000]}")
                if default_on_failure:
                    logger.warning("Returning default-include analyses due to JSON parse failure")
                    return create_default_include_analyses(expected_count), errors, True
                return None, errors, True
    else:
        errors.append("Failed to parse JSON after retries")
        if default_on_failure:
            logger.warning("Returning default-include analyses due to JSON parse failure")
            return create_default_include_analyses(expected_count), errors, True
        return None, errors, True
    
    # Validate structure
    is_valid, validation_errors, validated_analyses = validate_line_item_analysis_response(result, expected_count)
    
    if validation_errors:
        errors.extend(validation_errors)
        logger.warning(f"Validation errors: {validation_errors}")
        logger.debug(f"Response was: {response_text[:1000]}")
    
    if not is_valid:
        json_validation_failed = True
        if default_on_failure:
            logger.warning("Returning default-include analyses due to validation failure")
            return create_default_include_analyses(expected_count), errors, True
        return None, errors, True
    
    return validated_analyses, [], False


def enforce_claim_amount_constraint(
    line_items: List[Dict],
    analyses: List[LineItemAnalysis],
    claim_amount: Decimal,
    max_benefit: Optional[Decimal]
) -> Tuple[List[Dict], Decimal, List[str]]:
    """
    Enforce claim_amount and max_benefit constraints.
    
    Never approve more than min(claim_amount, max_benefit).
    If eligible_total exceeds claim_amount, prioritize items and reduce.
    
    Args:
        line_items: Original line items
        analyses: Validated analyses
        claim_amount: Maximum claim amount (hard limit)
        max_benefit: Maximum benefit (secondary cap)
    
    Returns:
        (updated_line_items_with_flags, final_eligible_total, constraint_applied_messages)
    """
    messages = []
    
    # Calculate cap
    if max_benefit is not None:
        cap = min(claim_amount, max_benefit)
        messages.append(f"Cap applied: min(claim_amount=${claim_amount:.2f}, max_benefit=${max_benefit:.2f}) = ${cap:.2f}")
    else:
        cap = claim_amount
        messages.append(f"Cap applied: claim_amount=${claim_amount:.2f}")
    
    # Calculate current eligible total
    eligible_items = []
    for i, (item, analysis) in enumerate(zip(line_items, analyses)):
        if analysis.should_be_included:
            amount = Decimal(str(item.get('amount', 0)))
            eligible_items.append({
                'index': i,
                'item': item,
                'analysis': analysis,
                'amount': amount,
                'confidence': analysis.confidence
            })
    
    eligible_total = sum(item['amount'] for item in eligible_items)
    
    # If eligible total exceeds cap, prioritize and reduce
    if eligible_total > cap:
        messages.append(f"Eligible total ${eligible_total:.2f} exceeds cap ${cap:.2f}, prioritizing items")
        
        # Sort by confidence (highest first), then by amount (largest first)
        eligible_items.sort(key=lambda x: (-x['confidence'], -x['amount']))
        
        # Keep items until we hit the cap
        approved_items = []
        running_total = Decimal("0")
        
        for item_data in eligible_items:
            amount = item_data['amount']
            if running_total + amount <= cap:
                approved_items.append(item_data['index'])
                running_total += amount
            else:
                # Can't fit this item, mark as excluded
                messages.append(f"Excluded ${amount:.2f} '{item_data['item'].get('description', 'N/A')[:50]}' to stay within cap")
        
        # Update analyses to reflect constraint
        for i, analysis in enumerate(analyses):
            if i not in approved_items and analysis.should_be_included:
                # Create new analysis with should_be_included=False
                updated_analysis = LineItemAnalysis(
                    line_item_number=analysis.line_item_number,
                    should_be_included=False,
                    is_normal_wear_tear=analysis.is_normal_wear_tear,
                    is_covered_by_addendum=analysis.is_covered_by_addendum,
                    is_covered_by_other_insurance=analysis.is_covered_by_other_insurance,
                    confidence=analysis.confidence,
                    reasoning=f"{analysis.reasoning} [Excluded due to claim_amount constraint]",
                    addendum_reference=analysis.addendum_reference
                )
                analyses[i] = updated_analysis
        
        eligible_total = running_total
        messages.append(f"Final eligible total after constraint: ${eligible_total:.2f}")
    
    # Convert analyses back to dict format for compatibility
    # Preserve all existing flags from deterministic rules
    updated_items = []
    for i, (item, analysis) in enumerate(zip(line_items, analyses)):
        updated_item = {
            **item,  # Preserve all existing fields including deterministic flags
            'should_be_included': analysis.should_be_included,
            'is_normal_wear_tear': analysis.is_normal_wear_tear,
            'is_covered_by_addendum': analysis.is_covered_by_addendum,
            'is_covered_by_other_insurance': analysis.is_covered_by_other_insurance,
            'analysis_confidence': analysis.confidence,
            'analysis_reasoning': analysis.reasoning,
            'addendum_reference': analysis.addendum_reference
        }
        updated_items.append(updated_item)
    
    return updated_items, eligible_total, messages

