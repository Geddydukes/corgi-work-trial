#!/usr/bin/env python3
"""
Process exactly 42 claims from Google Drive to reach 100 total claims with decisions.
Then run batch evaluation and generate variance report.
"""
import requests
import time
import psycopg2
import json
from datetime import datetime

API_URL = "http://localhost:8000/api/v1"
DRIVE_FOLDER_ID = "1-sEEs61X3q7AG8MV6y6wlX637KLOnMs4"

def get_db_connection():
    return psycopg2.connect("postgresql://postgres:postgres@localhost:5432/corgi_dev")

def check_server():
    try:
        resp = requests.get("http://localhost:8000/health", timeout=5)
        return resp.status_code == 200
    except:
        return False

def get_claims_to_process():
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET search_path TO claims")
    
    # Count current
    cur.execute("""
        SELECT COUNT(DISTINCT c.id) 
        FROM claims c
        JOIN decisions d ON c.id = d.claim_id AND d.is_active = true
        JOIN decision_validation dv ON c.id = dv.claim_id
    """)
    current = cur.fetchone()[0]
    needed = 100 - current
    print(f"Current claims with decisions: {current}")
    print(f"Need: {needed} more to reach 100")
    
    if needed <= 0:
        print("Already have 100+ claims!")
        cur.close()
        conn.close()
        return []
    
    # Get exactly needed claims, excluding tracking number 13 (claim_id 2501) which freezes
    cur.execute("""
        SELECT c.id, c.claim_tracking_number
        FROM claims c
        JOIN decision_validation dv ON c.id = dv.claim_id
        LEFT JOIN decisions d ON c.id = d.claim_id AND d.is_active = true
        WHERE d.id IS NULL
        AND c.claim_tracking_number ~ '^[0-9]+$'
        AND c.claim_tracking_number != '13'
        ORDER BY c.claim_tracking_number::int
        LIMIT %s
    """, (needed,))
    claims = cur.fetchall()
    
    cur.close()
    conn.close()
    return claims

def process_from_drive(tracking_number):
    try:
        resp = requests.post(
            f"{API_URL}/claims/process-from-drive",
            json={"tracking_number": tracking_number, "drive_folder_id": DRIVE_FOLDER_ID},
            timeout=180
        )
        if resp.status_code == 200:
            return True, None
        else:
            error = resp.json().get('detail', resp.text[:100])
            return False, str(error)
    except Exception as e:
        return False, str(e)

def submit_batch(claim_ids):
    resp = requests.post(
        f"{API_URL}/batch/evaluate",
        json={"claim_ids": claim_ids},
        timeout=60
    )
    if resp.status_code in [200, 202]:
        return resp.json().get("batch_id")
    return None

def wait_for_batch(batch_id, max_wait=900):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(f"{API_URL}/batch/{batch_id}/status", timeout=30)
            state = resp.json().get("status")
            if state == "completed":
                return True, time.time() - start
            elif state == "failed":
                return False, time.time() - start
        except:
            pass
        time.sleep(5)
    return None, max_wait

def main():
    if not check_server():
        print("❌ Server is not responding. Please start the server first.")
        return
    
    claims = get_claims_to_process()
    if not claims:
        return
    
    print(f"\n{'='*60}")
    print(f"STEP 1: Loading documents from Google Drive ({len(claims)} claims)")
    print(f"{'='*60}")
    
    successful_claims = []
    failed_claims = []
    
    for i, (claim_id, tracking) in enumerate(claims):
        success, error = process_from_drive(tracking)
        if success:
            successful_claims.append(claim_id)
            print(f"✅ [{i+1}/{len(claims)}] Claim {tracking}")
        else:
            failed_claims.append((tracking, error))
            print(f"❌ [{i+1}/{len(claims)}] Claim {tracking} - {error[:50]}")
        
        # Small delay to avoid overwhelming server
        if (i + 1) % 5 == 0:
            time.sleep(2)
        else:
            time.sleep(0.5)
    
    print(f"\n✅ Successfully loaded docs for {len(successful_claims)}/{len(claims)} claims")
    if failed_claims:
        print(f"❌ Failed: {len(failed_claims)} claims")
    
    if not successful_claims:
        print("\n❌ No claims successfully processed. Cannot continue.")
        return
    
    print(f"\n{'='*60}")
    print(f"STEP 2: Running batch evaluation ({len(successful_claims)} claims)")
    print(f"{'='*60}")
    
    batch_id = submit_batch(successful_claims)
    if not batch_id:
        print("❌ Failed to submit batch")
        return
    
    print(f"Batch {batch_id} submitted, waiting for completion...")
    success, elapsed = wait_for_batch(batch_id)
    
    if success:
        print(f"✅ Batch completed in {elapsed:.0f}s")
    elif success is False:
        print(f"❌ Batch failed after {elapsed:.0f}s")
    else:
        print(f"⏰ Batch timed out after {elapsed:.0f}s")
    
    print(f"\n{'='*60}")
    print("STEP 3: Generating variance report")
    print(f"{'='*60}")
    
    # Count final total
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET search_path TO claims")
    
    cur.execute("""
        SELECT COUNT(DISTINCT c.id) 
        FROM claims c
        JOIN decisions d ON c.id = d.claim_id AND d.is_active = true
        JOIN decision_validation dv ON c.id = dv.claim_id
    """)
    final_count = cur.fetchone()[0]
    print(f"Total claims with decisions: {final_count}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()

