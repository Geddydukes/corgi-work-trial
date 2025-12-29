# User Line Item Override System

## Overview

This system allows users to override line item decisions through a frontend interface. These overrides are logged and can be used in batches to improve deterministic rules.

## Database Schema

**Table**: `claims.user_line_item_overrides`

Stores:
- Original system decision (should_be_included, categories, reasoning)
- User override (should_be_included, reasoning, user_id)
- Batch ID for grouping overrides
- Flag indicating if override has been applied to rules

## Workflow

### 1. User Reviews Decision
- Frontend displays all line items with:
  - Description
  - Amount
  - System decision (approved/denied)
  - Reasoning (deterministic rule + LLM reasoning)
  - Category tags (rent, cleaning, repair, etc.)

### 2. User Toggles Line Item
- User clicks toggle to change approval status
- Frontend sends override to API:
  ```json
  {
    "decision_id": 123,
    "line_item_index": 0,
    "user_should_be_included": true,
    "user_reasoning": "This cleaning charge should be approved despite being excessive"
  }
  ```

### 3. Override Stored
- API stores override in `user_line_item_overrides` table
- Original system decision preserved for comparison
- Batch ID assigned (e.g., "batch_2025_01_28")

### 4. Batch Processing
- Periodically (e.g., weekly), process overrides in batches
- Analyze patterns:
  - Which deterministic rules are frequently overridden?
  - What categories are being misclassified?
  - What reasoning patterns indicate rule gaps?

### 5. Rule Improvement
- Update phrase lists based on overrides
- Adjust deterministic rules based on patterns
- Test improved rules on validation set
- Deploy improved rules

## API Endpoints (Future)

### POST /api/decisions/{decision_id}/line-items/{index}/override
```json
{
  "user_should_be_included": true,
  "user_reasoning": "Reason for override"
}
```

### GET /api/decisions/{decision_id}/line-items
Returns all line items with current system decisions

### GET /api/overrides/batches/{batch_id}
Returns all overrides in a batch for analysis

## Logging Format

Current logging includes:
- Line item description and amount
- System decision (approved/denied)
- Category tags (rent, cleaning, repair, etc.)
- Deterministic rule applied
- LLM reasoning
- Confidence score

All logged in both human-readable and JSON format for parsing.

## Example Log Output

```
Line Item #1: Cleaning Charges - Excessive
  Amount: $200.00
  Decision: ❌ DENIED
  Confidence: 100.0%
  Reasoning: Deterministic Rule: cleaning_only_invoice_denied | Categories: CLEANING | LLM: Excessive cleaning charges
  Category Tags: CLEANING
```

## Rule Improvement Process

1. **Collect Overrides**: Query `user_line_item_overrides` where `is_applied_to_rules = FALSE`
2. **Group by Pattern**: 
   - Overrides where system denied but user approved
   - Overrides where system approved but user denied
   - Category mismatches
3. **Analyze Patterns**:
   - If "cleaning" items frequently overridden → adjust cleaning rules
   - If specific phrases frequently misclassified → add to phrase lists
4. **Update Rules**: Modify `deterministic_rules.py` phrase lists and logic
5. **Test**: Run on validation set
6. **Deploy**: Mark overrides as `is_applied_to_rules = TRUE`

## Future Enhancements

- Machine learning model to predict overrides
- Automatic rule suggestions based on override patterns
- A/B testing of rule improvements
- Confidence scoring based on override frequency


