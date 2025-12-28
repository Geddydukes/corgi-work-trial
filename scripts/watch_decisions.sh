#!/bin/bash
# Watch decisions being made in real-time

LOG_FILE="/Users/geddydukes/Desktop/Corgi/workflow_output.log"

echo "=========================================="
echo "LIVE DECISION MONITOR"
echo "=========================================="
echo "Watching for approve/deny decisions..."
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Show recent decisions first
echo "Recent Decisions:"
echo "----------------------------------------"
grep "→ Decision:" "$LOG_FILE" 2>/dev/null | tail -15 | while read line; do
    DECISION=$(echo "$line" | sed 's/.*Decision: //')
    TIME=$(echo "$line" | grep -o '[0-9][0-9]:[0-9][0-9]:[0-9][0-9]' | head -1)
    
    if echo "$DECISION" | grep -q "approve"; then
        echo "  ✅ [$TIME] $DECISION"
    elif echo "$DECISION" | grep -q "deny"; then
        echo "  ❌ [$TIME] $DECISION"
    else
        echo "  ⚠️  [$TIME] $DECISION"
    fi
done

echo ""
echo "----------------------------------------"
echo "Waiting for new decisions..."
echo "----------------------------------------"
echo ""

# Watch for new decisions
tail -f "$LOG_FILE" 2>/dev/null | while read line; do
    if echo "$line" | grep -q "→ Decision:"; then
        DECISION=$(echo "$line" | sed 's/.*Decision: //')
        TIME=$(date '+%H:%M:%S')
        
        if echo "$DECISION" | grep -q "approve"; then
            echo "✅ [$TIME] $DECISION"
        elif echo "$DECISION" | grep -q "deny"; then
            echo "❌ [$TIME] $DECISION"
        else
            echo "⚠️  [$TIME] $DECISION"
        fi
    fi
done
