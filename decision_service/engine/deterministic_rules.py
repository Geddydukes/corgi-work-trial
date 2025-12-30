"""
Deterministic rule engine for line item coverage decisions.

This module enforces coverage rules using phrase matching and date comparisons.
LLM output is advisory only - final coverage decisions are made here.
"""

import logging
import re
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


def _match_word_boundary(phrase: str, text: str) -> bool:
    """
    Check if phrase matches as a whole word in text.
    Prevents 'pet' from matching 'carpet'.
    """
    # Use word boundary regex for short phrases that might be substrings
    if len(phrase) <= 4:
        # For short phrases like 'pet', 'cat', 'dog', use word boundary matching
        pattern = r'\b' + re.escape(phrase) + r'\b'
        return bool(re.search(pattern, text))
    else:
        # For longer phrases, substring matching is usually fine
        return phrase in text


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
    # Removed "pet cleaning" - it matches "carpet cleaning" incorrectly
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

# Prior balances are ledger entries, not damage charges
PRIOR_BALANCE_PHRASES = [
    "balance as of",
    "beginning balance",
    "initial balance",
    "prior balance",
    "opening balance",
    "balance forward",
    "carryover balance",
    "previous balance",
    "outstanding balance",
    "amount due",
    "total amount due",
    "past due",
    "amount owed"
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
        is_after_lease_end: bool = False,
        is_prior_balance: bool = False
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
        self.is_prior_balance = is_prior_balance


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
    # Use word boundary matching for OTHER_INSURANCE_PHRASES to avoid false positives
    # e.g., "pet" should not match "carpet"
    is_other_insurance = any(_match_word_boundary(phrase, description_lower) for phrase in OTHER_INSURANCE_PHRASES)
    is_contractual_fee = any(phrase in description_lower for phrase in CONTRACTUAL_FEE_PHRASES)
    # Prior balances are ledger entries, not actual damage charges
    is_prior_balance = any(phrase in description_lower for phrase in PRIOR_BALANCE_PHRASES)
    
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
        is_after_lease_end=is_after_lease_end,
        is_prior_balance=is_prior_balance
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
    
    # Auto-deny ineligible categories
    if category.is_rent:
        return False
    
    if category.is_month_to_month:
        return False
    
    if category.is_improper_notice:
        return False
    
    if category.is_other_insurance:
        return False
    
    # Prior balances are ledger entries, not damage charges
    if category.is_prior_balance:
        return False
    
    # Contractual fees (late fees, utility fees, etc.) are not damage charges
    if category.is_contractual_fee:
        return False
    
    # Only deny normal wear/tear if explicitly flagged (be more lenient)
    if is_normal_wear_tear:
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
    if (not category.is_rent and 
        not category.is_month_to_month and 
        not category.is_improper_notice and 
        not category.is_other_insurance and
        not category.is_prior_balance and
        not category.is_contractual_fee):
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
        # Approval-leaning default: assume addendum coverage unless we have explicit evidence otherwise
        is_covered_by_addendum = True  # Default to True
        has_llm_suggestion = llm_suggestions and i < len(llm_suggestions)
        if has_llm_suggestion:
            is_normal_wear_tear = llm_suggestions[i].get('is_normal_wear_tear', False)
            is_covered_by_addendum = llm_suggestions[i].get('is_covered_by_addendum', True)
        elif 'is_covered_by_addendum' in item:
            # Only fall back to item-level flags when no fresh LLM suggestions are provided
            is_covered_by_addendum = item.get('is_covered_by_addendum', True)
        
        should_include = should_be_included_deterministic(
            category=category,
            is_normal_wear_tear=is_normal_wear_tear,
            amount=amount,
            is_covered_by_addendum=is_covered_by_addendum
        )
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
            'is_prior_balance': category.is_prior_balance,
            'is_normal_wear_tear': is_normal_wear_tear,
            'is_covered_by_addendum': is_covered_by_addendum,  # Preserve LLM's determination
            'deterministic_rule_applied': True
        }
        
        flagged_items.append(flagged_item)
    
    return flagged_items
