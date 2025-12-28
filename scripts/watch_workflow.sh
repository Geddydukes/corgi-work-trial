#!/bin/bash
# Continuous log watch for workflow progress

LOG_FILE="/Users/geddydukes/Desktop/Corgi/workflow_output.log"

echo "=========================================="
echo "Workflow Progress Monitor"
echo "=========================================="
echo "Watching: $LOG_FILE"
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Show last 20 lines, then follow
tail -n 20 "$LOG_FILE" && echo "" && echo "--- Following new lines ---" && tail -f "$LOG_FILE"

