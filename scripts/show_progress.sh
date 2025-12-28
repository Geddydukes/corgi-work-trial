#!/bin/bash
# Show current progress and which file is being processed

LOG_FILE="/Users/geddydukes/Desktop/Corgi/workflow_output.log"

echo "=========================================="
echo "WORKFLOW PROGRESS MONITOR"
echo "=========================================="
echo ""

# Get current file being processed
CURRENT_FILE=$(tail -20 "$LOG_FILE" 2>/dev/null | grep "Processing:" | tail -1 | sed 's/.*Processing: //' | sed 's/$/.../')
CURRENT_CLAIM=$(tail -20 "$LOG_FILE" 2>/dev/null | grep "Processing claim" | tail -1 | sed 's/.*Processing claim //' | sed 's/\.\.\..*//')

# Count progress
DOCS_PROCESSED=$(grep -c "✓ Document saved" "$LOG_FILE" 2>/dev/null || echo "0")
DECISIONS_CREATED=$(grep -c "✓ Decision saved" "$LOG_FILE" 2>/dev/null || echo "0")
TOTAL_CLAIMS=21  # 900-920 inclusive

# Show current status
if [ -n "$CURRENT_CLAIM" ]; then
    echo "📋 Current Claim: $CURRENT_CLAIM"
fi

if [ -n "$CURRENT_FILE" ]; then
    echo "📄 Current File: $CURRENT_FILE"
else
    echo "📄 Current File: (checking...)"
fi

echo ""
echo "📊 Progress:"
echo "   Documents Processed: $DOCS_PROCESSED"
echo "   Decisions Created: $DECISIONS_CREATED"
echo "   Claims Range: 900-920 ($TOTAL_CLAIMS claims)"
echo ""

# Check which step we're in
if grep -q "STEP 2: Running Decision Engine" "$LOG_FILE" 2>/dev/null; then
    if grep -q "STEP 3: Running Evaluation" "$LOG_FILE" 2>/dev/null; then
        echo "✅ Status: Step 3 - Evaluation (almost done!)"
    else
        echo "✅ Status: Step 2 - Decision Engine"
    fi
elif grep -q "STEP 1: Processing Documents" "$LOG_FILE" 2>/dev/null; then
    echo "✅ Status: Step 1 - Document Processing"
else
    echo "⏳ Status: Starting..."
fi

echo ""
echo "=========================================="
echo "Last 5 log lines:"
echo "------------------------------------------"
tail -5 "$LOG_FILE" 2>/dev/null | sed 's/^/  /'
echo "=========================================="

