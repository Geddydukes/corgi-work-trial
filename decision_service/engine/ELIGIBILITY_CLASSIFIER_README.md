# Eligibility Classification System

A transparent, auditable eligibility classification system optimized for rapid iteration.

## Features

- **Externalized Rules**: YAML-based configuration, no code changes needed
- **Hot Reloading**: Update rules without deployment
- **Multi-Layer Classification**: 5-layer decision tree for maximum accuracy
- **A/B Testing**: Compare different rulesets
- **Comprehensive Audit Trail**: Full transparency on classification decisions
- **Performance Optimized**: <1ms per item, <50ms rules reload

## Quick Start

```python
from decision_service.engine.eligibility_classifier import EligibilityClassifier
from decimal import Decimal

classifier = EligibilityClassifier("rules/rules_v1.0.yaml")

item = {
    "description": "Professional carpet cleaning",
    "amount": Decimal("150.00"),
    "line_number": 1
}

result = classifier.classify(item)
print(f"Status: {result.classification.status.value}")
print(f"Category: {result.classification.category}")
print(f"Confidence: {result.classification.confidence}%")
print(f"Reasoning: {result.classification.reasoning}")
```

## Classification Layers

1. **Exact Match** (confidence: 90-100%)
   - Matches example descriptions exactly
   - Includes fuzzy matching for typos (Levenshtein distance < 3)

2. **Pattern Matching** (confidence: 80-95%)
   - Regex pattern matching
   - Case-insensitive with word boundaries

3. **Keyword Scoring** (confidence: 60-85%)
   - Weighted scoring based on keyword presence
   - Positive keywords increase score
   - Negative keywords heavily penalize

4. **Machine Learning** (confidence: 70-95%)
   - TF-IDF + Logistic Regression
   - Only used if model available and accuracy > 85%

5. **Default** (confidence: 30%)
   - Falls back to eligible (if approval_bias=true)
   - Requires manual review

## Files

- `eligibility_classifier.py` - Main classifier class
- `ab_testing.py` - A/B testing framework
- `../rules/rules_v1.0.yaml` - Rules configuration
- `../rules/rules_schema.json` - JSON schema for validation
- `../rules/RULES_GUIDE.md` - Guide for modifying rules

## Testing

Run comprehensive test suite:

```bash
pytest tests/test_eligibility_classifier.py -v
```

Run performance benchmarks:

```bash
pytest tests/test_eligibility_performance.py -v
```

## A/B Testing

Compare two rulesets:

```python
from decision_service.engine.ab_testing import RulesABTest

test = RulesABTest("rules/rules_v1.0.yaml", "rules/rules_v1.1.yaml")
results = test.compare_on_dataset(test_claims)
print(test.generate_report(results))
```

## Hot Reloading

Update rules without restarting:

```python
classifier.reload_rules("rules/rules_v1.1.yaml")
```

## Performance Targets

- ✅ Classify 100 items: < 100ms (< 1ms per item)
- ✅ Rules reload: < 50ms
- ✅ Memory footprint: < 50MB

## Integration

The classifier can be integrated into the existing `EligibilityEngine`:

```python
from decision_service.engine.eligibility_classifier import EligibilityClassifier

class EligibilityEngine:
    def __init__(self):
        self.classifier = EligibilityClassifier("rules/rules_v1.0.yaml")
    
    async def calculate(self, claim: dict, invoice_data: dict) -> dict:
        approved_items = []
        ineligible_items = []
        
        for line_item in invoice_data.get("line_items", []):
            classified = self.classifier.classify({
                "description": line_item.get("description", ""),
                "amount": line_item.get("amount", 0.0),
                "line_number": line_item.get("line_number", 0)
            })
            
            if classified.classification.status.value == "eligible":
                approved_items.append({
                    "description": classified.description,
                    "amount": classified.amount,
                    "reason": classified.classification.reasoning
                })
            else:
                ineligible_items.append({
                    "description": classified.description,
                    "amount": classified.amount,
                    "reason": classified.classification.reasoning
                })
        
        eligible_total = sum(item["amount"] for item in approved_items)
        
        return {
            "approved_items": approved_items,
            "ineligible_items": ineligible_items,
            "eligible_total": Decimal(str(eligible_total))
        }
```

## Documentation

See `rules/RULES_GUIDE.md` for detailed instructions on modifying rules.

