# Implementation Summary: Deterministic Decision Engine

## Changes Implemented

### 1. New Module: `deterministic_rules.py`

**File**: `decision_service/engine/deterministic_rules.py`

**Purpose**: Deterministic rule engine that makes coverage decisions using phrase matching, independent of LLM output.

**Key Features**:

- Phrase-based category detection (rent, cleaning, repair, etc.)
- Date-based exclusion rules (post-lease-end charges)
- Cleaning-only invoice denial rule
- Sanity checks for corrupted amounts

**Functions**:

- `categorize_line_item()`: Phrase matching to tag categories
- `should_be_included_deterministic()`: Coverage decision logic
- `is_cleaning_only_invoice()`: Special rule for cleaning-only invoices
- `apply_deterministic_rules()`: Main entry point

---

### 2. Updated: `json_validator.py`

**File**: `decision_service/engine/json_validator.py`

**Changes**:

- Added `create_default_include_analyses()`: Creates default-include analyses on validation failure
- Updated `parse_and_validate_line_item_analysis()`:
  - New parameter: `default_on_failure=True`
  - Returns tuple: `(analyses, errors, json_validation_failed_flag)`
  - On failure: Returns default-include analyses instead of None

**Impact**: Prevents silent denials when LLM JSON is invalid. Deterministic rules will filter appropriately.

---

### 3. Updated: `document_analyzer.py`

**File**: `decision_service/engine/document_analyzer.py`

**Changes**:

- Imported `deterministic_rules` module
- Updated `analyze_line_items_batch()`:
  - Uses new JSON validator signature (handles `json_validation_failed` flag)
  - Removed auto-denial rules (moved to deterministic rules)
  - Calls `apply_deterministic_rules()` to make coverage decisions
  - Preserves LLM metadata for audit trail
- Updated constraint enforcement to work with new format

**Impact**: LLM output is now advisory only. Final coverage decisions made by deterministic rules.

---

### 4. Updated: `rule_evaluator.py`

**File**: `decision_service/engine/rule_evaluator.py`

**Changes**:

- Added `mode` parameter: `"production"` (default) or `"backtest"`
- Backtest mode: Missing `max_benefit` → returns `"pending"` instead of `"deny"`
- Added sanity check: `invoice_total` capped to `claim_amount * 1.5` if exceeds
- Added explicit comments for deterministic cap calculation (monotonicity)

**Impact**:

- Backtest mode prevents false denials when `max_benefit` is missing
- Sanity checks catch data corruption (e.g., Claim 901)

---

### 5. Updated: `decision_engine.py`

**File**: `decision_service/engine/decision_engine.py`

**Changes**:

- Added `lease_end_date` to `claim_context` (for date-based rules)
- Added sanity check: `eligible_total` capped to `invoice_total * 1.5` if exceeds
- Removed aggressive document analysis override (lines 278-295)
- Document analysis now advisory only (warnings, not blocking)
- Computes `document_confidence` and passes to `RuleEvaluator`

**Impact**:

- Deterministic rules control coverage, not document analysis
- Sanity checks prevent corrupted eligible totals
- Document analysis provides warnings but doesn't block approvals

---

## Architecture Changes

### Before (PROBLEMATIC):

```
LLM → should_be_included (FINAL DECISION)
     ↓
Auto-denial rules (too late)
     ↓
RuleEvaluator (uses LLM decision)
```

### After (DETERMINISTIC):

```
LLM → category suggestions (ADVISORY)
     ↓
Deterministic Rules → should_be_included (FINAL DECISION)
     ↓
RuleEvaluator (uses rule decision)
```

---

## Root Cause Fixes

| Claim | Issue                                    | Fix                                                                      |
| ----- | ---------------------------------------- | ------------------------------------------------------------------------ |
| 900   | Cleaning-only invoice approved           | Added `is_cleaning_only_invoice()` rule                                  |
| 901   | Invoice parsing corruption               | Added sanity checks in `rule_evaluator` and `decision_engine`            |
| 902   | Missing cleaning charges                 | Improved extraction (no code change, but deterministic rules will catch) |
| 904   | Normal wear/tear override too aggressive | Removed document analysis override                                       |

---

## Testing Status

### Unit Tests Needed:

- [ ] `test_deterministic_rules.py`: Phrase matching, coverage decisions
- [ ] `test_json_validator_fallback.py`: Default-include on validation failure
- [ ] `test_rule_evaluator_backtest.py`: Backtest mode behavior
- [ ] `test_monotonicity.py`: Increasing max_benefit never decreases benefit

### Regression Tests Needed:

- [ ] Claim 900: Cleaning-only invoice → DENY
- [ ] Claim 901: Corrupted invoice_total → Sanity check applied
- [ ] Claim 902: Rent excluded, cleaning included → APPROVE $100
- [ ] Claim 904: Normal wear/tear doesn't block → APPROVE

---

## Remaining Work

### High Priority:

1. Update `run_decisions_first_5.py` to add structured logging
2. Add regression tests for Claims 900-904
3. Add property-based tests for monotonicity
4. Update prompts in `document_analyzer.py` to remove "never approve rent" (LLM should only tag)

### Medium Priority:

5. Cross-check `has_addendum` with enrollment data (not just classification)
6. Add fuzzy matching for phrase lists (handle misspellings)
7. Improve date extraction from line item descriptions

### Low Priority:

8. Add monitoring for JSON validation failures
9. Create runbook for phrase list updates
10. Add alerts for sanity check triggers

---

## Breaking Changes

### API Changes:

- `parse_and_validate_line_item_analysis()` now returns 3-tuple instead of 2-tuple
- `RuleEvaluator.evaluate()` now accepts `mode` parameter

### Behavior Changes:

- JSON validation failures now default-include (was implicit deny)
- Missing `max_benefit` in backtest mode returns `"pending"` (was `"deny"`)
- Document analysis no longer overrides line item decisions

---

## Migration Guide

### For Callers of `parse_and_validate_line_item_analysis()`:

```python
# Old:
analyses, errors = parse_and_validate_line_item_analysis(...)

# New:
analyses, errors, json_failed = parse_and_validate_line_item_analysis(...)
if json_failed:
    logger.warning("JSON validation failed, using default-include")
```

### For Callers of `RuleEvaluator.evaluate()`:

```python
# Old:
result = await rule_evaluator.evaluate(claim, eligibility_result, ...)

# New (backtest mode):
result = await rule_evaluator.evaluate(
    claim, eligibility_result, ..., mode="backtest"
)
```

---

## Performance Impact

**Minimal**: Deterministic rules use simple string matching (O(n\*m) where n=items, m=phrases), which is fast.

**LLM Calls**: Unchanged - still one call per batch of line items.

**Database Queries**: Unchanged.

---

## Security Considerations

**None**: All changes are internal logic improvements. No external API changes.

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-XX  
**Status**: Implementation Complete, Testing Pending

