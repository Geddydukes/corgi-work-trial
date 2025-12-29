# Root Cause Summary: Claims 900-904

## Quick Reference

| Claim | Proposed | Actual | Variance | Root Cause(s) | File(s) | Line(s) |
|-------|----------|--------|----------|---------------|---------|---------|
| 900 | APPROVE $200 | DENY $0 | $200 | Cleaning-only invoice rule missing | `document_analyzer.py` | 282-292 |
| 901 | APPROVE $1500 | APPROVE $770 | $730 | Invoice parsing corruption, no sanity checks | `document_analyzer.py`, `decision_engine.py` | 122-189, 181-210 |
| 902 | APPROVE $50 | APPROVE $100 | $50 | Missing cleaning charges in extraction | `document_analyzer.py` | 122-189 |
| 903 | APPROVE $190 | APPROVE $190 | $0 | ✅ Perfect match | - | - |
| 904 | DENY $0 | APPROVE $1500 | $1500 | Normal wear/tear override too aggressive | `decision_engine.py` | 278-295 |

---

## Root Cause Categories

### a) Invoice Parsing Failure
- **Claim 901**: Line items extracted as $0.00 with "N/A" descriptions
- **Location**: `document_analyzer.py:122-189` (`extract_line_items_from_invoice`)
- **Fix**: Add sanity checks, reject if >50% items have $0 amounts

### b) Eligibility Classification Mismatch
- **Claim 900**: "Excessive cleaning" approved but should be denied
- **Claim 904**: Normal wear/tear flag denying valid charges
- **Location**: `document_analyzer.py:281-312` (prompt), `decision_engine.py:278-295` (override)
- **Fix**: Move coverage decisions to deterministic rules, LLM only tags categories

### c) Rent and Month-to-Month Rule Mismatch
- **Claim 902**: Rent charges approved when only cleaning should be covered
- **Claim 904**: Future rent and reletting fees approved
- **Location**: `document_analyzer.py:393-400` (rent denial), missing "future months rent"
- **Fix**: Expand rent phrase list, add contractual fee detection

### d) Cleaning-Only Invoice Behavior
- **Claim 900**: Single cleaning charge approved but historical policy denies
- **Location**: Missing rule in `rule_evaluator.py`
- **Fix**: Add rule: `if len(line_items) == 1 and is_cleaning_only: deny`

### e) Missing max_benefit Auto-Denial
- **Not observed in 900-904**, but code exists
- **Location**: `rule_evaluator.py:101-121`
- **Fix**: Add backtest mode that returns PENDING instead of DENY

### f) has_addendum / has_invoice Misclassification
- **Not observed in 900-904**, but risk exists
- **Location**: `decision_engine.py:79-86`
- **Fix**: Cross-check with enrollment data, don't rely solely on classification

### g) JSON Validation Failure Causing Fallback
- **Not explicitly observed**, but code path exists
- **Location**: `document_analyzer.py:361-364`, `json_validator.py:191-249`
- **Fix**: Default-include on validation failure, tag with flag

### h) Cap Logic Mismatch
- **Claim 901**: Corrupted invoice_total used in cap calculation
- **Location**: `rule_evaluator.py:140-145`
- **Fix**: Sanity check invoice_total before using in cap

---

## File-by-File Issues

### document_analyzer.py
- **Line 282**: Prompt says "excessive cleaning = APPROVE" but should deny cleaning-only
- **Line 306-312**: LLM directly decides `should_be_included` (should be rules)
- **Line 393-400**: Rent denial works but missing "future months rent"
- **Line 361-364**: JSON failure → implicit deny (should default-include)

### decision_engine.py
- **Line 79-86**: `has_addendum`/`has_invoice` only from classification (no enrollment check)
- **Line 278-295**: Document analysis override too aggressive (denies valid charges)
- **Line 181-210**: No sanity check on eligible_total (accepts billions)

### rule_evaluator.py
- **Line 101-121**: Missing max_benefit → hard deny (no backtest mode)
- **Line 140-145**: Cap calculation doesn't sanity-check invoice_total
- **Missing**: Cleaning-only invoice rule

### json_validator.py
- **Line 191-249**: Validation failure returns None → implicit deny
- **Missing**: Default-include fallback with flag

---

## Deterministic Design Principles

1. **LLM Role**: Extract text, segment items, suggest categories (ADVISORY)
2. **Rule Engine**: Phrase matching → coverage flags (DETERMINISTIC)
3. **RuleEvaluator**: Cap calculation, final status (DETERMINISTIC, MONOTONIC)

**Trusted Inputs:**
- `claim_amount`, `max_benefit`, `lease_end_date` (database)
- `invoice_total` (with sanity checks)
- `has_addendum`, `has_invoice` (classification OR enrollment)

**Advisory Inputs:**
- `line_item.description`, `line_item.amount` (LLM extracted)
- `line_item.category_suggestion` (LLM suggests, rules decide)

---

## Implementation Checklist

- [ ] Add sanity checks for invoice_total corruption
- [ ] Fix JSON validation fallback (default-include)
- [ ] Add cleaning-only invoice denial rule
- [ ] Expand rent phrase list
- [ ] Create deterministic rule engine
- [ ] Move coverage decisions from LLM to rules
- [ ] Add backtest mode (missing max_benefit → PENDING)
- [ ] Add structured logging
- [ ] Implement regression tests
- [ ] Add monotonicity tests


