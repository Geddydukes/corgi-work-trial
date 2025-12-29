#!/usr/bin/env python3
"""
Test script for batch endpoint with tracking numbers.
Tests the batch processing with mixed DB and Drive claims.
"""

import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from decision_service.repositories.claim_repository import ClaimRepository
from decision_service.services.batch_service import BatchService

async def test_batch_with_tracking_numbers():
    """Test batch processing with tracking numbers: 901, 555, 603, 724, 1"""
    
    tracking_numbers = ['901', '555', '603', '724', '1']
    
    print("=" * 80)
    print("Testing Batch Endpoint with Tracking Numbers")
    print("=" * 80)
    print(f"Tracking Numbers: {', '.join(tracking_numbers)}")
    print()
    
    claim_repo = ClaimRepository()
    batch_service = BatchService()
    
    claim_ids = []
    db_claims = []
    drive_claims = []
    
    print("Step 1: Checking which claims exist in database...")
    print("-" * 80)
    
    for tracking_number in tracking_numbers:
        claim = await claim_repo.get_claim_by_tracking_number(tracking_number)
        if claim:
            claim_id = claim['id']
            claim_ids.append(claim_id)
            db_claims.append((tracking_number, claim_id))
            print(f"  ✓ {tracking_number} -> Found in DB (Claim ID: {claim_id})")
        else:
            drive_claims.append(tracking_number)
            print(f"  ✗ {tracking_number} -> Not in DB (will use Drive processing)")
    
    print()
    print(f"Summary:")
    print(f"  - DB claims: {len(db_claims)} ({', '.join([f'{tn}({cid})' for tn, cid in db_claims])})")
    print(f"  - Drive claims: {len(drive_claims)} ({', '.join(drive_claims)})")
    print()
    
    if claim_ids:
        print("Step 2: Submitting batch evaluation for DB claims...")
        print("-" * 80)
        
        try:
            batch_request = BatchEvaluationRequest(claim_ids=claim_ids)
            result = await batch_service.submit_batch(
                claim_ids=claim_ids,
                webhook_url=None,
                priority=0
            )
            
            print(f"  ✓ Batch submitted successfully")
            print(f"    Batch ID: {result['batch_id']}")
            print(f"    Claim Count: {result['claim_count']}")
            print(f"    Status: {result['status']}")
            print(f"    Estimated Completion: {result['estimated_completion']}")
            print()
            
            print("Step 3: Polling batch status...")
            print("-" * 80)
            
            batch_id = result['batch_id']
            max_polls = 10
            poll_count = 0
            
            while poll_count < max_polls:
                status = await batch_service.get_batch_status(batch_id)
                if status:
                    print(f"  Poll {poll_count + 1}: Status={status['status']}, "
                          f"Processed={status['processed_count']}/{status['claim_count']}, "
                          f"Success={status['successful_count']}, Failed={status['failed_count']}")
                    
                    if status['status'] in ['completed', 'failed']:
                        print()
                        print(f"  Final Status: {status['status']}")
                        print(f"    Processed: {status['processed_count']}/{status['claim_count']}")
                        print(f"    Successful: {status['successful_count']}")
                        print(f"    Failed: {status['failed_count']}")
                        if status.get('error_message'):
                            print(f"    Error: {status['error_message']}")
                        break
                    
                    await asyncio.sleep(2)
                    poll_count += 1
                else:
                    print(f"  ✗ Could not get batch status")
                    break
            
            print()
            print("=" * 80)
            print("Batch Processing Test Complete")
            print("=" * 80)
            print()
            print("Note: Drive claims (555, 603, 724, 1) would need to be processed")
            print("      separately via the process-from-drive endpoint.")
            print()
            
        except Exception as e:
            print(f"  ✗ Error submitting batch: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("No DB claims found. All claims would need Drive processing.")
        print()

if __name__ == "__main__":
    asyncio.run(test_batch_with_tracking_numbers())

