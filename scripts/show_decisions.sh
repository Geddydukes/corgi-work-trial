#!/bin/bash
# Show all decisions made so far with summary

LOG_FILE="/Users/geddydukes/Desktop/Corgi/workflow_output.log"

echo "=========================================="
echo "DECISION SUMMARY"
echo "=========================================="
echo ""

# Extract decisions with better parsing
echo "All Decisions Made:"
echo "----------------------------------------"

# Get decisions with claim context
grep "→ Decision:" "$LOG_FILE" 2>/dev/null | while read line; do
    DECISION=$(echo "$line" | sed 's/.*Decision: //')
    
    # Try to get claim number from context (look back a few lines)
    LINE_NUM=$(grep -n "→ Decision:" "$LOG_FILE" 2>/dev/null | grep -F "$line" | cut -d: -f1)
    if [ -n "$LINE_NUM" ]; then
        CLAIM=$(sed -n "$((LINE_NUM-5)),${LINE_NUM}p" "$LOG_FILE" 2>/dev/null | grep "Processing claim" | tail -1 | sed 's/.*Processing claim //' | sed 's/\.\.\..*//')
    fi
    
    if [ -z "$CLAIM" ]; then
        CLAIM="?"
    fi
    
    if echo "$DECISION" | grep -q "approve"; then
        printf "  ✅ Claim %-5s: %s\n" "$CLAIM" "$DECISION"
    elif echo "$DECISION" | grep -q "deny"; then
        printf "  ❌ Claim %-5s: %s\n" "$CLAIM" "$DECISION"
    else
        printf "  ⚠️  Claim %-5s: %s\n" "$CLAIM" "$DECISION"
    fi
done

echo ""
echo "----------------------------------------"
echo "Summary:"
echo "----------------------------------------"

APPROVALS=$(grep "→ Decision:" "$LOG_FILE" 2>/dev/null | grep -c "approve" || echo "0")
DENIALS=$(grep "→ Decision:" "$LOG_FILE" 2>/dev/null | grep -c "deny" || echo "0")
TOTAL=$((APPROVALS + DENIALS))

echo "  Total Decisions: $TOTAL"
echo "  ✅ Approvals: $APPROVALS"
echo "  ❌ Denials: $DENIALS"

if [ "$TOTAL" -gt 0 ] && command -v bc >/dev/null 2>&1; then
    APPROVAL_PCT=$(echo "scale=1; $APPROVALS * 100 / $TOTAL" | bc 2>/dev/null || echo "0")
    DENIAL_PCT=$(echo "scale=1; $DENIALS * 100 / $TOTAL" | bc 2>/dev/null || echo "0")
    echo "  Approval Rate: ${APPROVAL_PCT}%"
    echo "  Denial Rate: ${DENIAL_PCT}%"
fi

echo ""
echo "=========================================="
