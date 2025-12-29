#!/bin/bash
# Test batch endpoint with tracking numbers: 901, 555, 603, 724, 1
# This script tests the actual API endpoints

API_URL="${API_URL:-http://localhost:8000/api/v1}"

echo "=================================================================================="
echo "Testing Batch Endpoint with Tracking Numbers: 901, 555, 603, 724, 1"
echo "=================================================================================="
echo "API URL: $API_URL"
echo ""

echo "Step 1: Check which claims exist in database"
echo "----------------------------------------------------------------------------------"
for tn in 901 555 603 724 1; do
    echo -n "Checking tracking number $tn: "
    response=$(curl -s -w "\n%{http_code}" "$API_URL/claims/$tn/decision" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    if [ "$http_code" = "200" ]; then
        claim_id=$(echo "$response" | head -n-1 | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('claim_id', 'N/A'))" 2>/dev/null || echo "N/A")
        echo "✓ Found in DB (Claim ID: $claim_id)"
    else
        echo "✗ Not in DB (will use Drive processing)"
    fi
done

echo ""
echo "Step 2: Submit batch evaluation (for DB claims)"
echo "----------------------------------------------------------------------------------"
echo "Note: This would require claim IDs. For tracking numbers, we need to:"
echo "  1. Check each tracking number to get claim ID"
echo "  2. Submit batch with claim IDs"
echo "  3. For non-existent claims, use process-from-drive endpoint"
echo ""

echo "Step 3: Expected API calls"
echo "----------------------------------------------------------------------------------"
echo "For DB claims (if they exist):"
echo "  POST $API_URL/batch/evaluate"
echo "    Body: {\"claim_ids\": [<claim_ids>]}"
echo ""
echo "For Drive claims (if they don't exist in DB):"
echo "  POST $API_URL/claims/process-from-drive"
echo "    Body: {\"tracking_number\": \"<tn>\", \"drive_folder_id\": \"1-sEEs61X3q7AG8MV6y6wlX637KLOnMs4\"}"
echo ""

echo "=================================================================================="
echo "Test script complete. Check console output above for results."
echo "=================================================================================="



