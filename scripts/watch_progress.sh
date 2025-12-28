#!/bin/bash
# Continuously watch progress with file names

LOG_FILE="/Users/geddydukes/Desktop/Corgi/workflow_output.log"

# Clear screen and show header
clear
echo "=========================================="
echo "WORKFLOW PROGRESS - LIVE MONITOR"
echo "=========================================="
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Function to show current status
show_status() {
    # Get current file
    CURRENT_FILE=$(tail -30 "$LOG_FILE" 2>/dev/null | grep "Processing:" | tail -1 | sed 's/.*Processing: //')
    CURRENT_CLAIM=$(tail -30 "$LOG_FILE" 2>/dev/null | grep "Processing claim" | tail -1 | sed 's/.*Processing claim //' | sed 's/\.\.\..*//')
    
    # Count progress
    DOCS_PROCESSED=$(grep -c "✓ Document saved" "$LOG_FILE" 2>/dev/null || echo "0")
    DECISIONS_CREATED=$(grep -c "✓ Decision saved" "$LOG_FILE" 2>/dev/null || echo "0")
    
    # Clear and show status
    clear
    echo "=========================================="
    echo "WORKFLOW PROGRESS - LIVE MONITOR"
    echo "=========================================="
    echo ""
    
    if [ -n "$CURRENT_CLAIM" ]; then
        echo "📋 Current Claim: $CURRENT_CLAIM"
    fi
    
    if [ -n "$CURRENT_FILE" ]; then
        echo "📄 Current File: $CURRENT_FILE"
    else
        echo "📄 Current File: (waiting...)"
    fi
    
    echo ""
    echo "📊 Progress:"
    echo "   Documents: $DOCS_PROCESSED processed"
    echo "   Decisions: $DECISIONS_CREATED created"
    echo ""
    
    # Check step
    if grep -q "WORKFLOW COMPLETE" "$LOG_FILE" 2>/dev/null; then
        echo "🎉 WORKFLOW COMPLETE!"
        echo ""
        tail -10 "$LOG_FILE" | grep -E "WORKFLOW COMPLETE|Documents processed|Decisions created|Evaluation accuracy|Results saved"
        return 1
    elif grep -q "STEP 3: Running Evaluation" "$LOG_FILE" 2>/dev/null; then
        echo "✅ Step 3: Evaluation"
    elif grep -q "STEP 2: Running Decision Engine" "$LOG_FILE" 2>/dev/null; then
        echo "✅ Step 2: Decision Engine"
    else
        echo "✅ Step 1: Document Processing"
    fi
    
    echo ""
    echo "----------------------------------------"
    echo "Recent Activity:"
    echo "----------------------------------------"
    tail -8 "$LOG_FILE" 2>/dev/null | sed 's/^/  /'
    echo ""
    echo "=========================================="
    echo "Updated: $(date '+%H:%M:%S')"
}

# Watch loop
while true; do
    show_status
    if [ $? -eq 1 ]; then
        # Workflow complete, exit
        break
    fi
    sleep 2
done

