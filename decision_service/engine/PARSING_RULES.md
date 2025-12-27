# Invoice Parsing Rules and Algorithm Documentation

## Overview

This document describes the production-grade invoice parser that handles extreme real-world variability in invoice formats, layouts, and content.

## Architecture

The parser uses a **5-pass algorithm** to extract and validate invoice data:

1. **Pass 1: Structure Detection** - Identifies table boundaries, headers, and footers
2. **Pass 2: Line Item Extraction** - Extracts individual line items from the invoice
3. **Pass 3: Amount Parsing** - Parses amounts using multiple pattern matching strategies
4. **Pass 4: Total Reconciliation** - Validates totals and identifies discrepancies
5. **Pass 5: Validation & Quality Checks** - Performs final validation and calculates confidence scores

## Module Structure

### Core Modules

- **`invoice_parser_advanced.py`** - Main parser implementing the 5-pass algorithm
- **`amount_extractor.py`** - Handles all amount parsing patterns and variations
- **`table_detector.py`** - Detects table structure and column positions
- **`reconciliation.py`** - Validates totals and detects discrepancies
- **`invoice_models.py`** - Data models for parsed invoice data

## Pass 1: Structure Detection

### Objectives
- Detect table boundaries using whitespace analysis
- Identify header row (keywords: "description", "charge", "amount")
- Detect column positions (amount column typically right-aligned)
- Identify footer section (keywords: "total", "balance", "amount due")

### Algorithm

1. Split text into lines
2. Search for header row by matching keywords in first 20 lines
3. Search for footer row by matching keywords in last 30 lines
4. Detect amount column position by finding most common dollar sign positions
5. Detect description column bounds based on amount column position

### Detection Criteria

**Header Detection:**
- Must contain at least 2 header keywords, OR
- Contains 1 header keyword AND has dollar signs or numbers

**Footer Detection:**
- Contains at least 1 footer keyword AND
- Contains dollar amounts or decimal numbers

**Column Detection:**
- Amount column: Most common position of dollar amounts (rounded to nearest 10)
- Description column: Average start position of text before amount column

## Pass 2: Line Item Extraction

### Objectives
- Extract each row between header and footer
- Use column positions to split description from amount
- Merge multi-line descriptions (heuristic: next line has no amount)
- Handle bullet points and numbering

### Algorithm

1. Extract rows between header and footer
2. For each row:
   - Split into description and amount using column positions
   - If no amount found, attempt to merge with next line
   - Create LineItem with extracted data
3. Handle special cases:
   - Bullet points (•, -, *)
   - Numbered lists (1., 2., 3.)
   - Multi-line descriptions

### Multi-line Merging Heuristic

A description continues on the next line if:
- Next line has no amount in the amount column position
- Next line doesn't start with bullet/number markers
- Next line contains text (not just whitespace)

## Pass 3: Amount Parsing

### Objectives
- Parse amounts using multiple regex patterns in order of specificity
- Handle percentage calculations if base amount provided
- Convert ranges to midpoint
- Flag unparseable amounts for manual review

### Amount Patterns (in order of specificity)

1. **Standard dollar**: `$1,234.56` (confidence: 1.0)
2. **Negative parentheses**: `($50.00)` (confidence: 0.95)
3. **Negative minus**: `-$50.00` (confidence: 0.95)
4. **Dollar no cents**: `$1234` (confidence: 0.85)
5. **Amount with currency**: `1234.56 USD` (confidence: 0.9)
6. **Decimal amount**: `1234.56` (confidence: 0.8)
7. **Integer amount**: `1234` (confidence: 0.7)
8. **Single decimal**: `1234.5` (confidence: 0.75)

### Special Cases

**Percentage-based:**
- Pattern: `15%` or `15 percent`
- Requires base amount in context
- Calculation: `base_amount * (percentage / 100)`
- Confidence: 0.85

**Range amounts:**
- Pattern: `$50-$75` or `50-75`
- Uses midpoint: `(low + high) / 2`
- Confidence: 0.75

**Formula-based:**
- Pattern: `3 × $25` or `3 x $25` or `3 * $25`
- Calculation: `quantity * unit_price`
- Confidence: 0.9

**European format:**
- Pattern: `1.234,56€` or `1,234.56€`
- Converts to USD using exchange rate (1.10)
- Confidence: 0.7

**TBD/Pending:**
- Patterns: `TBD`, `Pending`, `TBA`, `To be determined`, `N/A`
- Returns amount 0 with confidence 0.0
- Flagged for manual review

### Amount Validation

- Amount must be non-zero (except for credits)
- Maximum amount: $10,000 per item
- Minimum amount: $0.01
- Negative amounts are flagged as credits

## Pass 4: Total Reconciliation

### Objectives
- Extract stated total from footer
- Calculate sum of parsed line items
- If difference > $1.00, flag reconciliation error
- Use stated total as authoritative if found

### Algorithm

1. Extract stated total from footer section
2. Calculate total from all items (line_items + credits + taxes + fees)
3. Calculate difference: `abs(calculated - stated)`
4. Success if difference <= $1.00
5. Generate reconciliation notes

### Reconciliation Logic

**Net Amount Calculation:**
```
net = sum(positive_items) + sum(taxes) + sum(fees) - sum(abs(credits))
```

**Difference Analysis:**
- If calculated < stated: Possible missing items
- If calculated > stated: Possible duplicate items or calculation error
- If difference > $10.00: Critical error

### Credit Detection

Negative amounts are automatically classified as credits if:
- Amount is negative (from parentheses or minus sign)
- Description contains credit-related keywords

## Pass 5: Validation & Quality Checks

### Objectives
- Verify at least one line item found
- Check for duplicate descriptions (case-insensitive)
- Flag if any single item > 50% of total (likely error)
- Ensure all amounts are reasonable (< $10,000 per item)
- Calculate overall parsing confidence

### Quality Checks

1. **Line Item Validation:**
   - At least one line item must be found
   - Each item must have description and amount

2. **Duplicate Detection:**
   - Case-insensitive description matching
   - Same amount (within $0.01 tolerance)
   - Flagged for manual review

3. **Suspicious Item Detection:**
   - Item > 50% of total amount
   - Item > $10,000
   - Description missing or < 3 characters
   - All flagged for manual review

4. **Ambiguity Scoring:**
   Each line item gets ambiguity_score (0-100):
   - Clear desc + clean amount = 10
   - Multi-line desc + clean amount = 30
   - Unclear desc + clean amount = 50
   - Unclear desc + estimated amount = 80
   - No desc or amount = 100 (manual review required)

5. **Overall Confidence:**
   ```
   overall_confidence = max(0, 100 - avg_ambiguity_score)
   ```

### Manual Review Triggers

An invoice requires manual review if:
- No line items found
- Average ambiguity score > 60
- Reconciliation difference > $1.00
- Duplicate items detected
- Suspicious items detected
- Any item > $10,000
- Any item missing description

## Advanced Features

### Context-Aware Parsing

- **Quantity Detection:** If description contains "per day/month/unit", extract quantity
- **Formula Detection:** If formula detected (e.g., "3 × $25"), calculate result
- **Multi-page Detection:** If reference to "page 2", flag multi-page invoice
- **Property Type:** Cross-reference with property type (studio vs 4-bedroom)

### Negative Amount Handling

- Negative = credit/refund
- Separated into `credits` list
- Net amount = sum(positive) - sum(abs(negative))
- Flagged if credits > charges (likely data error)

### Tax and Fee Detection

**Tax Keywords:**
- "tax", "gst", "vat", "sales tax", "use tax", "hst"

**Fee Keywords:**
- "fee", "processing", "service charge", "convenience", "late fee", "administrative"

**Handling:**
- Stored separately for eligibility rules
- Don't double-count in total
- Calculate pre-tax vs. post-tax amounts

### Industry-Specific Rules

**Property Management:**
- Expect "move-out charges"
- Room-by-room breakdowns
- Damage assessment items

**Utility Bills:**
- Expect "water", "electric", "gas"
- Service period dates
- Usage-based charges

**Cleaning Invoices:**
- Room-by-room breakdown
- Service type classification
- Square footage considerations

**Maintenance:**
- Labor + parts split
- Hourly rates
- Material costs

## Error Recovery (Graceful Degradation)

If parsing completely fails:

1. **Fallback Strategy:**
   - Try simpler line-by-line regex scan
   - Extract any dollar amounts found
   - Return as "unknown charges" with low confidence
   - Flag entire invoice for manual review
   - Provide OCR text dump for human review

2. **Fallback Parsing:**
   - Extract all amounts using basic regex
   - Create line items with "Unknown charge N" descriptions
   - Set confidence to LOW
   - Set ambiguity score to 90
   - Require manual review

## Performance Requirements

- **Parse typical invoice (20 items):** < 500ms
- **Handle up to 200 line items:** ✓
- **Memory efficient:** Stream large documents
- **Concurrent processing:** Thread-safe design

## Output Validation

All output must satisfy:

- All amounts are `Decimal` (not `float`)
- All amounts non-negative (except credits flagged)
- Sum of items within $1 of stated total (if reconciled)
- At least one line item OR manual review flagged
- Confidence scores rational (0-100 range)
- Processing time recorded

## Data Models

### LineItem

```python
@dataclass
class LineItem:
    description: str
    amount: Decimal
    line_number: int
    confidence: LineItemConfidence  # HIGH, MEDIUM, LOW
    ambiguity_score: float  # 0-100
    notes: List[str]
    quantity: Optional[int]
    unit_price: Optional[Decimal]
    is_credit: bool
    is_tax: bool
    is_fee: bool
    original_text: str
```

### InvoiceParseResult

```python
@dataclass
class InvoiceParseResult:
    line_items: List[LineItem]
    invoice_total_stated: Optional[Decimal]
    invoice_total_calculated: Decimal
    reconciliation_difference: Decimal
    credits: List[LineItem]
    taxes: List[LineItem]
    fees: List[LineItem]
    metadata: InvoiceMetadata
    quality_metrics: ParsingQualityMetrics
    flags: List[str]
    requires_manual_review: bool
    manual_review_reasons: List[str]
```

## Testing

Comprehensive test suite covers 30+ scenarios:

1. Perfect invoice (clean table, all amounts parse)
2. Handwritten additions
3. Multi-page with page break mid-item
4. Missing total (use calculated)
5. Negative amounts (credits)
6. Percentage-based charges
7. Formula charges (3 × $25)
8. Foreign currency (flag for conversion)
9. Ambiguous descriptions
10. Duplicate line items
11. Single item > invoice total (error)
12. Sum ≠ stated total (reconciliation)
13. No line items found (empty invoice)
14. Tax separate from charges
15. Sub-totals throughout
... (30+ total scenarios)

## Usage

```python
from decision_service.engine.invoice_parser_advanced import AdvancedInvoiceParser

parser = AdvancedInvoiceParser()
result = parser.parse_invoice(
    extracted_text=ocr_text,
    document_id=123,
    claim_context={"property_type": "2-bedroom"}
)

# Access results
for item in result.line_items:
    print(f"{item.description}: ${item.amount}")

print(f"Total: ${result.invoice_total_calculated}")
print(f"Requires review: {result.requires_manual_review}")
```

## Maintenance

### Adding New Amount Patterns

1. Add pattern to `AMOUNT_PATTERNS` in `amount_extractor.py`
2. Include regex pattern, confidence score, and method name
3. Test with edge cases
4. Update documentation

### Adding New Industry Rules

1. Add keywords to appropriate detector in `table_detector.py`
2. Add validation logic in Pass 5
3. Create test cases
4. Update documentation

### Performance Optimization

- Profile with `performance_benchmark.py`
- Optimize regex patterns (compile if used frequently)
- Cache structure detection results
- Consider parallel processing for large invoices

