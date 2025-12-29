"""
Deterministic rule engine for line item coverage decisions.

This module enforces coverage rules using phrase matching and date comparisons.
LLM output is advisory only - final coverage decisions are made here.
"""

import logging
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


# Deterministic phrase lists for category detection
RENT_PHRASES = [
    "residential rent",
    "garage rent",
    "rent",
    "monthly rent",
    "future months rent",
    "future month rent"
]

MONTH_TO_MONTH_PHRASES = [
    "month to month",
    "month-to-month",
    "m2m"
]

CLEANING_PHRASES = [
    "cleaning",
    "carpet cleaning",
    "carpet",
    "stain",
    "stains",
    "filth",
    "excessive cleaning",
    "deep cleaning"
]

REPAIR_PHRASES = [
    "repair",
    "repairs",
    "drywall",
    "paint",
    "painting",
    "broken",
    "drip pan",
    "drip pans",
    "fixture"
]

DAMAGE_PHRASES = [
    "damage",
    "damages",
    "hole",
    "holes",
    "scratch",
    "scratches"
]

IMPROPER_NOTICE_PHRASES = [
    "improper notice",
    "improper",
    "notice charge"
]

OTHER_INSURANCE_PHRASES = [
    "flea",
    "pet",
    "dog",
    "cat",
    "animal",
    "pest control",
    "pest treatment",
    "pet deposit",
    "pet damage",
    "pet cleaning",
    "fire",
    "smoke",
    "burn",
    "flame",
    "water damage",
    "flood",
    "leak",
    "overflow",
    "sewer",
    "drain",
    "sump"
]

CONTRACTUAL_FEE_PHRASES = [
    "reletting fee",
    "reletting",
    "late charge",
    "late fee",
    "utility revenue",
    "security deposit protection",
    "renters insurance"
]


class LineItemCategory:
    """Deterministic category tags for a line item."""
    
    def __init__(
        self,
        is_rent: bool = False,
        is_month_to_month: bool = False,
        is_cleaning: bool = False,
        is_repair: bool = False,
        is_damage: bool = False,
        is_improper_notice: bool = False,
        is_other_insurance: bool = False,
        is_contractual_fee: bool = False,
        is_after_lease_end: bool = False
    ):
        self.is_rent = is_rent
        self.is_month_to_month = is_month_to_month
        self.is_cleaning = is_cleaning
        self.is_repair = is_repair
        self.is_damage = is_damage
        self.is_improper_notice = is_improper_notice
        self.is_other_insurance = is_other_insurance
        self.is_contractual_fee = is_contractual_fee
        self.is_after_lease_end = is_after_lease_end


def categorize_line_item(
    description: str,
    amount: Decimal,
    lease_end_date: Optional[str] = None,
    charge_date: Optional[str] = None
) -> LineItemCategory:
    """
    Deterministically categorize a line item using phrase matching.
    
    Args:
        description: Line item description
        amount: Line item amount
        lease_end_date: Lease end date (ISO format string)
        charge_date: Charge date (ISO format string, optional)
    
    Returns:
        LineItemCategory with boolean flags
    """
    description_lower = str(description).lower()
    
    is_rent = any(phrase in description_lower for phrase in RENT_PHRASES)
    is_month_to_month = any(phrase in description_lower for phrase in MONTH_TO_MONTH_PHRASES)
    is_cleaning = any(phrase in description_lower for phrase in CLEANING_PHRASES)
    is_repair = any(phrase in description_lower for phrase in REPAIR_PHRASES)
    is_damage = any(phrase in description_lower for phrase in DAMAGE_PHRASES)
    is_improper_notice = any(phrase in description_lower for phrase in IMPROPER_NOTICE_PHRASES)
    is_other_insurance = any(phrase in description_lower for phrase in OTHER_INSURANCE_PHRASES)
    is_contractual_fee = any(phrase in description_lower for phrase in CONTRACTUAL_FEE_PHRASES)
    
    is_after_lease_end = False
    if lease_end_date and charge_date:
        try:
            lease_end = datetime.fromisoformat(lease_end_date.replace('Z', '+00:00'))
            charge = datetime.fromisoformat(charge_date.replace('Z', '+00:00'))
            is_after_lease_end = charge > lease_end
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse dates: lease_end={lease_end_date}, charge={charge_date}")
    
    return LineItemCategory(
        is_rent=is_rent,
        is_month_to_month=is_month_to_month,
        is_cleaning=is_cleaning,
        is_repair=is_repair,
        is_damage=is_damage,
        is_improper_notice=is_improper_notice,
        is_other_insurance=is_other_insurance,
        is_contractual_fee=is_contractual_fee,
        is_after_lease_end=is_after_lease_end
    )


def should_be_included_deterministic(
    category: LineItemCategory,
    is_normal_wear_tear: bool = False,
    amount: Optional[Decimal] = None,
    is_covered_by_addendum: bool = True  # Default to True (assume covered unless explicitly denied)
) -> bool:
    """
    Deterministically determine if a line item should be included.
    
    More lenient policy: Approve by default unless explicitly ineligible.
    
    Args:
        category: LineItemCategory from phrase matching
        is_normal_wear_tear: Whether item is normal wear/tear (from LLM suggestion or rules)
        amount: Line item amount (for sanity checks)
        is_covered_by_addendum: Whether LLM determined item is covered by addendum
    
    Returns:
        True if item should be included in approved benefit
    """
    if amount is not None:
        if amount > Decimal("100000") or amount < Decimal("0"):
            return False
    
    # Only auto-deny the most clear-cut ineligible categories
    # Removed: is_contractual_fee, is_after_lease_end (be more lenient)
    if category.is_rent:
        return False
    
    if category.is_month_to_month:
        return False
    
    if category.is_improper_notice:
        return False
    
    if category.is_other_insurance:
        return False
    
    # Only deny normal wear/tear if explicitly flagged (be more lenient)
    if is_normal_wear_tear and category.is_normal_wear_tear:
        return False
    
    # More lenient: Approve if it's any type of cleaning, repair, or damage
    # Even if not explicitly covered by addendum (assume it might be)
    if category.is_cleaning or category.is_repair or category.is_damage:
        return True
    
    # More lenient: If covered by addendum, approve everything except explicit denials
    if is_covered_by_addendum:
        return True
    
    # More lenient default: If not explicitly denied and not clearly ineligible, approve
    # This is a more approval-leaning policy
    if not category.is_rent and not category.is_month_to_month and not category.is_improper_notice and not category.is_other_insurance:
        return True
    
    # Only deny if explicitly in one of the denial categories
    return False


def is_cleaning_only_invoice(line_items: List[Dict]) -> bool:
    """
    Check if invoice contains only cleaning charges.
    
    Args:
        line_items: List of line item dicts
    
    Returns:
        True if invoice has only cleaning charges
    """
    if not line_items:
        return False
    
    if len(line_items) == 1:
        description = str(line_items[0].get('description', '')).lower()
        is_cleaning = any(phrase in description for phrase in CLEANING_PHRASES)
        return is_cleaning
    
    all_cleaning = all(
        any(phrase in str(item.get('description', '')).lower() for phrase in CLEANING_PHRASES)
        for item in line_items
    )
    
    return all_cleaning


def apply_deterministic_rules(
    line_items: List[Dict],
    lease_end_date: Optional[str] = None,
    llm_suggestions: Optional[List[Dict]] = None
) -> List[Dict]:
    """
    Apply deterministic rules to line items.
    
    Args:
        line_items: List of line item dicts with 'description', 'amount'
        lease_end_date: Lease end date (ISO format)
        llm_suggestions: Optional LLM suggestions (advisory only)
    
    Returns:
        List of line items with deterministic flags added
    """
    if not line_items:
        return []
    
    # Check for cleaning-only invoice AFTER excluding rent/contractual fees
    # Get items that would be eligible (not rent, not contractual fees)
    eligible_candidates = []
    for item in line_items:
        description = str(item.get('description', '')).lower()
        is_rent = any(phrase in description for phrase in RENT_PHRASES)
        is_contractual = any(phrase in description for phrase in CONTRACTUAL_FEE_PHRASES)
        is_payment = 'payment' in description or item.get('amount', 0) < 0
        if not is_rent and not is_contractual and not is_payment:
            eligible_candidates.append(item)
    
    # Check if this is a cleaning-only invoice (all eligible items are cleaning)
    cleaning_only_invoice = False
    if eligible_candidates:
        all_cleaning = all(
            any(phrase in str(item.get('description', '')).lower() for phrase in CLEANING_PHRASES)
            for item in eligible_candidates
        )
        if all_cleaning:
            cleaning_only_invoice = True
            logger.info(f"Cleaning-only invoice detected ({len(eligible_candidates)} cleaning items) - denying per policy")
    
    flagged_items = []
    for i, item in enumerate(line_items):
        description = item.get('description', '')
        amount = Decimal(str(item.get('amount', 0)))
        
        category = categorize_line_item(
            description=description,
            amount=amount,
            lease_end_date=lease_end_date
        )
        
        is_normal_wear_tear = False
        is_covered_by_addendum = True  # Default to True
        if llm_suggestions and i < len(llm_suggestions):
            is_normal_wear_tear = llm_suggestions[i].get('is_normal_wear_tear', False)
            is_covered_by_addendum = llm_suggestions[i].get('is_covered_by_addendum', True)
        
        # Also check if item already has is_covered_by_addendum flag (from LLM analysis)
        if 'is_covered_by_addendum' in item:
            is_covered_by_addendum = item.get('is_covered_by_addendum', True)
        
        should_include = should_be_included_deterministic(
            category=category,
            is_normal_wear_tear=is_normal_wear_tear,
            amount=amount,
            is_covered_by_addendum=is_covered_by_addendum
        )
        
        # Override: if cleaning-only invoice, deny all cleaning items
        if cleaning_only_invoice and category.is_cleaning:
            should_include = False
            deterministic_rule = 'cleaning_only_invoice_denied'
        else:
            deterministic_rule = item.get('deterministic_rule', '')
        
        flagged_item = {
            **item,
            'should_be_included': should_include,
            'deterministic_rule': deterministic_rule,
            'is_rent': category.is_rent,
            'is_month_to_month': category.is_month_to_month,
            'is_cleaning': category.is_cleaning,
            'is_repair': category.is_repair,
            'is_damage': category.is_damage,
            'is_improper_notice': category.is_improper_notice,
            'is_other_insurance': category.is_other_insurance,
            'is_contractual_fee': category.is_contractual_fee,
            'is_after_lease_end': category.is_after_lease_end,
            'is_normal_wear_tear': is_normal_wear_tear,
            'is_covered_by_addendum': is_covered_by_addendum,  # Preserve LLM's determination
            'deterministic_rule_applied': True
        }
        
        flagged_items.append(flagged_item)
    
    return flagged_items

