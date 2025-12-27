# Eligibility Classification Rules Guide

This guide explains how to modify and maintain the eligibility classification rules without requiring code changes.

## Overview

The eligibility classification system uses externalized YAML rules that can be modified and hot-reloaded without deploying new code. This allows rapid iteration and A/B testing of different rulesets.

## Rules File Structure

The rules file (`rules_v1.0.yaml`) contains:

1. **Metadata**: Version, effective date, approval bias
2. **Categories**: Classification categories with patterns and keywords
3. **Special Rules**: Override rules for edge cases
4. **Threshold Rules**: Confidence and amount thresholds

## Understanding Categories

Each category defines how to classify line items:

```yaml
- name: ELIGIBLE_CLEANING
  confidence: 90
  patterns:
    - '\b(clean|shampoo|sanitiz)\b'
  keywords:
    positive: [clean, cleaning, shampoo]
    negative: [routine, scheduled]
  examples:
    - "Professional carpet cleaning"
```

### Category Name Format

- Must start with `ELIGIBLE_`, `INELIGIBLE_`, or `AMBIGUOUS_`
- Use uppercase with underscores
- Examples: `ELIGIBLE_CLEANING`, `INELIGIBLE_NORMAL_WEAR`

### Confidence Score

- Range: 0-100
- Higher = more certain
- Used to determine if manual review is needed
- Typical values:
  - 95-100: Very certain (exact matches)
  - 85-94: High confidence (strong patterns)
  - 70-84: Medium confidence (keyword matches)
  - Below 70: Low confidence (requires review)

### Patterns

- Regular expressions (regex) for matching descriptions
- Case-insensitive matching
- Use word boundaries `\b` to avoid partial matches
- Examples:
  - `\b(clean|shampoo)\b` - matches "clean" or "shampoo" as whole words
  - `\b(carpet clean|deep clean)\b` - matches phrases

### Keywords

- **Positive keywords**: Increase score for this category
- **Negative keywords**: Decrease score (heavily penalize)
- Simple word matching (case-insensitive)
- More flexible than patterns but less precise

### Examples

- Provide example descriptions that should match this category
- Used for exact matching (Layer 1)
- Also used for fuzzy matching with typos

## Classification Layers

The system uses 5 layers (in order):

1. **Exact Match**: Matches examples exactly (highest confidence)
2. **Pattern Match**: Matches regex patterns
3. **Keyword Scoring**: Scores based on keyword presence
4. **ML Prediction**: Machine learning (if model available)
5. **Default**: Falls back to default (lowest confidence)

## Adding a New Category

1. Add a new category entry in the `categories` section:

```yaml
- name: ELIGIBLE_NEW_CATEGORY
  confidence: 85
  patterns:
    - '\b(keyword1|keyword2)\b'
  keywords:
    positive: [keyword1, keyword2, keyword3]
    negative: [exclude1, exclude2]
  examples:
    - "Example description 1"
    - "Example description 2"
  notes: "Brief explanation"
```

2. Test with sample descriptions
3. Adjust confidence and patterns as needed
4. Reload rules (hot-reload) to test

## Modifying Existing Categories

### To Increase Match Rate

- Add more patterns
- Add more positive keywords
- Add more examples
- Lower confidence threshold (if appropriate)

### To Decrease False Positives

- Add negative keywords
- Make patterns more specific
- Increase confidence threshold
- Add special rules

## Special Rules

Special rules override normal classification for edge cases:

```yaml
- rule_id: "AMBIGUOUS_CLEANING_DAMAGE"
  trigger:
    contains_all: ["clean", "damage"]
  action:
    status: AMBIGUOUS
    confidence: 50
    requires_review: true
    reason: "Description contains both cleaning and damage keywords"
```

### Trigger Types

- `contains_all`: All keywords must be present
- `amount_above` + `confidence_below`: High amount with low confidence
- `patterns`: All regex patterns must match

### Action Types

- `status`: Override status (eligible/ineligible/ambiguous)
- `confidence`: Set confidence level
- `requires_review`: Force manual review
- `flag`: Add a flag to the result
- `reason`: Explanation for the override

## Threshold Rules

Control when items require manual review:

```yaml
threshold_rules:
  low_confidence_review: 60      # Below this confidence, flag for review
  high_value_review: 500          # Amounts above this with low confidence
  manual_review_required: 40      # Below this, mandatory human review
```

## Testing Rules

### Before Deploying

1. Test with historical claims
2. Use A/B testing framework to compare versions
3. Check for:
   - False positives (wrongly classified as eligible)
   - False negatives (wrongly classified as ineligible)
   - Low confidence scores (may need better patterns)

### A/B Testing

Use the A/B testing framework to compare rule versions:

```python
from decision_service.engine.ab_testing import RulesABTest

test = RulesABTest("rules_v1.0.yaml", "rules_v1.1.yaml")
results = test.compare_on_dataset(test_claims)
print(test.generate_report(results))
```

## Common Patterns

### Matching Phrases

```yaml
patterns:
  - '\b(carpet clean|deep clean)\b'  # Matches either phrase
```

### Matching with Context

```yaml
patterns:
  - '\b(repair|fix).{0,20}\b(damage|broken)\b'  # "repair" within 20 chars of "damage"
```

### Excluding False Positives

```yaml
keywords:
  positive: [clean, cleaning]
  negative: [routine, scheduled, normal]  # Excludes routine cleaning
```

### Amount-Based Rules

```yaml
amount_threshold:
  above: 50              # Amount must be above $50
  confidence_boost: 10   # Boost confidence by 10 points
```

## Version Control

- Use semantic versioning: `1.0`, `1.1`, `2.0`
- Include `effective_date` for tracking
- Document changes in commit messages
- Keep old versions for rollback

## Hot Reloading

Rules can be reloaded without restarting the service:

```python
classifier.reload_rules("rules_v1.1.yaml")
```

This allows:
- Rapid iteration
- Testing in production (with monitoring)
- Quick rollback if issues found

## Best Practices

1. **Start Specific**: Begin with specific patterns, then generalize
2. **Test Thoroughly**: Test with real historical data
3. **Monitor Results**: Track classification accuracy over time
4. **Document Changes**: Explain why rules were added/modified
5. **Use Examples**: Provide clear examples for each category
6. **Balance Confidence**: Don't set confidence too high (causes false positives) or too low (requires too much review)
7. **Negative Keywords**: Use negative keywords to reduce false positives
8. **Special Rules**: Use special rules for edge cases, not for common patterns

## Troubleshooting

### Too Many False Positives

- Add negative keywords
- Make patterns more specific
- Increase confidence threshold
- Add special rules to override

### Too Many False Negatives

- Add more patterns
- Add more positive keywords
- Add more examples
- Lower confidence threshold (carefully)

### Low Confidence Scores

- Improve patterns to be more specific
- Add more examples for exact matching
- Adjust keyword weights
- Consider adding ML model

### Performance Issues

- Reduce number of patterns per category
- Simplify regex patterns
- Cache compiled patterns (already done)
- Consider indexing for large datasets

## Examples

### Example 1: Adding Pet Damage Category

```yaml
- name: ELIGIBLE_PET_DAMAGE
  confidence: 85
  patterns:
    - '\b(pet.{0,15}damage|damage.{0,15}pet)\b'
    - '\b(urine|stain|odor).{0,15}\b(pet|animal)\b'
  keywords:
    positive: [pet, animal, urine, stain, odor, damage]
    negative: [normal, wear]
  examples:
    - "Pet damage to carpet"
    - "Urine stain removal from pet"
  notes: "Damage caused by pets is eligible"
```

### Example 2: Special Rule for Ambiguous Cases

```yaml
- rule_id: "CLEANING_ROUTINE"
  trigger:
    contains_all: ["clean", "routine"]
  action:
    status: INELIGIBLE_ROUTINE_MAINTENANCE
    confidence: 85
    requires_review: false
    reason: "Routine cleaning is not eligible"
```

## Support

For questions or issues:
1. Check this guide first
2. Review existing categories for patterns
3. Test changes with A/B testing framework
4. Monitor production metrics after changes

