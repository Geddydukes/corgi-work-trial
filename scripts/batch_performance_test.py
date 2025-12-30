#!/usr/bin/env python3
"""
Batch Performance Test: Mixed Local Files + Database Claims
Tests processing of 30 claims with performance and variance reporting.
"""

import os
import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from sqlalchemy import create_engine, text

# Configuration
API_URL = "http://localhost:8000/api/v1"
DB_URL = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
LOCAL_FILES_PATH = Path("/Users/geddydukes/Downloads/drive-download-20251230T010322Z-1-001")
OUTPUT_DIR = Path(__file__).parent / "performance_test_results"
OUTPUT_DIR.mkdir(exist_ok=True)

engine = create_engine(DB_URL)


def check_server():
    """Check if server is running."""
    try:
        requests.get(f"{API_URL}/health", timeout=5)
        return True
    except:
        return False


def get_claim_ids_for_tracking_numbers(tracking_numbers):
    """Get claim IDs for tracking numbers."""
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        placeholders = ", ".join([f"'{t}'" for t in tracking_numbers])
        result = conn.execute(
            text(f"""
                SELECT id, claim_tracking_number 
                FROM claims 
                WHERE claim_tracking_number IN ({placeholders})
            """)
        ).fetchall()
        return {r[1]: r[0] for r in result}


def process_local_files(tracking_numbers):
    """Process local files by uploading them via API."""
    print(f"\n📁 Processing {len(tracking_numbers)} local file folders...")
    processed = []
    failed = []
    
    for tracking in tracking_numbers:
        folder_path = LOCAL_FILES_PATH / str(tracking)
        if not folder_path.exists():
            print(f"   ⚠️  Folder {tracking} not found, skipping")
            failed.append(tracking)
            continue
        
        # Get all PDF files in folder
        pdf_files = list(folder_path.glob("*.pdf"))
        if not pdf_files:
            print(f"   ⚠️  No PDFs in folder {tracking}, skipping")
            failed.append(tracking)
            continue
        
        print(f"   📄 {tracking}: {len(pdf_files)} PDF files")
        
        # Upload files via the claims/upload endpoint
        try:
            files = []
            for pdf_path in pdf_files:
                files.append(('files', (pdf_path.name, open(pdf_path, 'rb'), 'application/pdf')))
            
            response = requests.post(
                f"{API_URL}/claims/upload",
                files=files,
                data={'tracking_number': str(tracking)},
                timeout=120
            )
            
            # Close file handles
            for _, (_, f, _) in files:
                f.close()
            
            if response.status_code == 200:
                processed.append(tracking)
            else:
                print(f"   ❌ Upload failed for {tracking}: {response.status_code}")
                failed.append(tracking)
        except Exception as e:
            print(f"   ❌ Error uploading {tracking}: {e}")
            failed.append(tracking)
    
    return processed, failed


def run_batch_evaluation(claim_ids, batch_name="test"):
    """Run batch evaluation and track performance."""
    print(f"\n🚀 Running batch evaluation for {len(claim_ids)} claims...")
    
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{API_URL}/batch/evaluate",
            json={"claim_ids": claim_ids},
            timeout=300
        )
        response.raise_for_status()
        batch_id = response.json()["batch_id"]
        print(f"   ✅ Batch submitted: {batch_id}")
    except Exception as e:
        print(f"   ❌ Failed to submit batch: {e}")
        return None
    
    # Poll for completion
    poll_times = []
    while time.time() - start_time < 1800:  # 30 min max
        poll_start = time.time()
        try:
            status_response = requests.get(
                f"{API_URL}/batch/{batch_id}/status",
                timeout=60
            )
            status_response.raise_for_status()
            status = status_response.json()
            
            poll_times.append(time.time() - poll_start)
            
            elapsed = int(time.time() - start_time)
            processed = status.get("processed_count", 0)
            total = status.get("claim_count", 0)
            successful = status.get("successful_count", 0)
            failed = status.get("failed_count", 0)
            
            print(f"   [{elapsed}s] {processed}/{total} processed | {successful} success | {failed} failed")
            
            if status.get("status") in ["completed", "failed"]:
                break
                
        except requests.exceptions.Timeout:
            print(f"   [{int(time.time() - start_time)}s] Status check timeout...")
        except Exception as e:
            print(f"   [{int(time.time() - start_time)}s] Error: {e}")
        
        time.sleep(3)
    
    total_time = time.time() - start_time
    
    # Get final status
    try:
        final_status = requests.get(f"{API_URL}/batch/{batch_id}/status", timeout=30).json()
    except:
        final_status = {}
    
    return {
        "batch_id": batch_id,
        "total_time": total_time,
        "claim_count": len(claim_ids),
        "successful_count": final_status.get("successful_count", 0),
        "failed_count": final_status.get("failed_count", 0),
        "avg_time_per_claim": total_time / len(claim_ids) if claim_ids else 0,
        "poll_times": poll_times
    }


def extract_results(claim_ids):
    """Extract decision results for claims."""
    results = []
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for claim_id in claim_ids:
            # Get latest decision
            decision = conn.execute(
                text("""
                    SELECT 
                        d.proposed_status, d.proposed_benefit_amount, d.eligible_total,
                        d.invoice_total, d.confidence_score,
                        CASE WHEN d.approved_line_items IS NULL THEN 0 
                             ELSE jsonb_array_length(d.approved_line_items::jsonb) END as approved_count,
                        c.claim_tracking_number
                    FROM decisions d
                    JOIN claims c ON d.claim_id = c.id
                    WHERE d.claim_id = :claim_id AND d.is_active = true
                    ORDER BY d.decided_at DESC
                    LIMIT 1
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
            # Get validation data
            validation = conn.execute(
                text("""
                    SELECT actual_status, actual_paid_amount
                    FROM decision_validation
                    WHERE claim_id = :claim_id
                    ORDER BY actual_decision_date DESC
                    LIMIT 1
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
            if decision:
                result = {
                    "claim_id": claim_id,
                    "tracking_number": decision[6],
                    "proposed_status": decision[0],
                    "proposed_amount": float(decision[1]) if decision[1] else 0,
                    "eligible_total": float(decision[2]) if decision[2] else 0,
                    "invoice_total": float(decision[3]) if decision[3] else 0,
                    "confidence": float(decision[4]) if decision[4] else 0,
                    "approved_count": decision[5] or 0,
                }
                
                if validation:
                    result["actual_status"] = validation[0]
                    result["actual_amount"] = float(validation[1]) if validation[1] else 0
                    result["status_match"] = result["proposed_status"].lower() == result["actual_status"].lower()
                    result["amount_difference"] = abs(result["proposed_amount"] - result["actual_amount"])
                else:
                    result["actual_status"] = None
                    result["actual_amount"] = None
                    result["status_match"] = None
                    result["amount_difference"] = None
                
                results.append(result)
    
    return results


def generate_variance_report(results):
    """Generate variance report."""
    report = []
    report.append("=" * 80)
    report.append("VARIANCE REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Filter results with validation data
    validated = [r for r in results if r.get("actual_status")]
    
    if validated:
        correct = sum(1 for r in validated if r.get("status_match"))
        accuracy = correct / len(validated) * 100
        
        report.append(f"Total Claims: {len(results)}")
        report.append(f"With Validation Data: {len(validated)}")
        report.append(f"Status Accuracy: {accuracy:.1f}% ({correct}/{len(validated)})")
        
        amounts_with_validation = [r for r in validated if r.get("actual_amount") is not None]
        if amounts_with_validation:
            avg_proposed = sum(r["proposed_amount"] for r in amounts_with_validation) / len(amounts_with_validation)
            avg_actual = sum(r["actual_amount"] for r in amounts_with_validation) / len(amounts_with_validation)
            mae = sum(r["amount_difference"] for r in amounts_with_validation) / len(amounts_with_validation)
            
            report.append(f"Average Proposed Amount: ${avg_proposed:,.2f}")
            report.append(f"Average Actual Amount: ${avg_actual:,.2f}")
            report.append(f"Mean Absolute Error: ${mae:,.2f}")
        
        report.append("")
        report.append("-" * 80)
        report.append("DETAILED RESULTS")
        report.append("-" * 80)
        
        for r in sorted(results, key=lambda x: int(x.get("tracking_number", 0))):
            tracking = r.get("tracking_number", "?")
            status = r["proposed_status"].upper()
            amount = r["proposed_amount"]
            
            if r.get("actual_status"):
                actual = r["actual_status"].upper()
                actual_amt = r.get("actual_amount", 0)
                match = "✅" if r.get("status_match") else "❌"
                diff = r.get("amount_difference", 0)
                report.append(f"Claim {tracking}: {status} ${amount:,.2f} vs {actual} ${actual_amt:,.2f} {match} (diff: ${diff:,.2f})")
            else:
                report.append(f"Claim {tracking}: {status} ${amount:,.2f} (no validation)")
    else:
        report.append("No validation data available for these claims.")
    
    return "\n".join(report)


def generate_performance_report(perf_data, results):
    """Generate performance report."""
    report = []
    report.append("=" * 80)
    report.append("PERFORMANCE REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    report.append("BATCH PROCESSING METRICS")
    report.append("-" * 40)
    report.append(f"Total Claims: {perf_data['claim_count']}")
    report.append(f"Successful: {perf_data['successful_count']}")
    report.append(f"Failed: {perf_data['failed_count']}")
    report.append(f"Success Rate: {perf_data['successful_count'] / perf_data['claim_count'] * 100:.1f}%")
    report.append("")
    report.append(f"Total Processing Time: {perf_data['total_time']:.1f}s ({perf_data['total_time']/60:.1f} min)")
    report.append(f"Average Time per Claim: {perf_data['avg_time_per_claim']:.1f}s")
    report.append(f"Throughput: {perf_data['claim_count'] / perf_data['total_time'] * 60:.1f} claims/min")
    
    report.append("")
    report.append("DECISION QUALITY METRICS")
    report.append("-" * 40)
    
    validated = [r for r in results if r.get("actual_status")]
    if validated:
        correct = sum(1 for r in validated if r.get("status_match"))
        report.append(f"Status Accuracy: {correct / len(validated) * 100:.1f}%")
        
        amounts = [r for r in validated if r.get("actual_amount") is not None]
        if amounts:
            mae = sum(r["amount_difference"] for r in amounts) / len(amounts)
            report.append(f"Mean Absolute Error: ${mae:,.2f}")
    
    report.append("")
    report.append("RECOMMENDATIONS FOR OPTIMIZATION")
    report.append("-" * 40)
    
    avg_time = perf_data['avg_time_per_claim']
    if avg_time > 30:
        report.append("⚠️  Average time > 30s per claim - consider:")
        report.append("   - Increase batch concurrency (currently 5)")
        report.append("   - Check for slow database queries")
        report.append("   - Verify LLM caching is working")
    elif avg_time > 10:
        report.append("⚡ Good performance, but could be faster:")
        report.append("   - Try increasing concurrency to 8-10")
        report.append("   - Consider parallel document processing")
    else:
        report.append("✅ Excellent performance!")
        report.append("   - Current settings are optimal")
    
    return "\n".join(report)


def get_claims_with_documents(count=30, exclude_ranges=None):
    """Get claims that have documents."""
    exclude_ranges = exclude_ranges or []
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        # Build exclusion clause
        exclude_clauses = []
        for start, end in exclude_ranges:
            exclude_clauses.append(f"c.claim_tracking_number::int NOT BETWEEN {start} AND {end}")
        
        exclude_sql = " AND ".join(exclude_clauses) if exclude_clauses else "1=1"
        
        result = conn.execute(
            text(f"""
                SELECT DISTINCT c.id, c.claim_tracking_number::int as tracking
                FROM claims c
                JOIN claim_documents cd ON c.id = cd.claim_id
                WHERE c.claim_tracking_number ~ '^[0-9]+$'
                  AND c.claim_tracking_number::int BETWEEN 1 AND 1000
                  AND {exclude_sql}
                ORDER BY c.claim_tracking_number::int
            """)
        ).fetchall()
        
        return [(r[0], r[1]) for r in result]


def main():
    print("=" * 80)
    print("BATCH PERFORMANCE TEST: 30 Claims with Documents")
    print("=" * 80)
    
    # Check server
    if not check_server():
        print("❌ Server is not running!")
        print("   Start with: uvicorn decision_service.main:app --host 0.0.0.0 --port 8000 --reload")
        return
    
    # Get claims with documents, excluding 899-920 (already tested)
    claims_data = get_claims_with_documents(count=30, exclude_ranges=[(899, 920)])
    
    if len(claims_data) < 30:
        print(f"⚠️  Only found {len(claims_data)} claims with documents")
    
    # Take up to 30
    claims_data = claims_data[:30]
    claim_ids = [c[0] for c in claims_data]
    tracking_numbers = [c[1] for c in claims_data]
    
    print(f"\n📋 Test Configuration:")
    print(f"   Claims with documents: {len(claims_data)}")
    print(f"   Tracking numbers: {tracking_numbers}")
    
    if not claim_ids:
        print("❌ No claims found with documents!")
        return
    
    print(f"\n📊 Processing {len(claim_ids)} claims...")
    
    # Run batch evaluation
    perf_data = run_batch_evaluation(claim_ids, "mixed_test")
    
    if not perf_data:
        print("❌ Batch processing failed!")
        return
    
    print(f"\n✅ Batch completed!")
    print(f"   Total time: {perf_data['total_time']:.1f}s")
    print(f"   Successful: {perf_data['successful_count']}/{perf_data['claim_count']}")
    
    # Extract results
    print("\n📊 Extracting results...")
    results = extract_results(claim_ids)
    
    # Generate reports
    print("\n📝 Generating reports...")
    
    variance_report = generate_variance_report(results)
    perf_report = generate_performance_report(perf_data, results)
    
    # Save reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    variance_path = OUTPUT_DIR / f"variance_report_{timestamp}.txt"
    with open(variance_path, "w") as f:
        f.write(variance_report)
    print(f"   💾 Variance report: {variance_path}")
    
    perf_path = OUTPUT_DIR / f"performance_report_{timestamp}.txt"
    with open(perf_path, "w") as f:
        f.write(perf_report)
    print(f"   💾 Performance report: {perf_path}")
    
    # Save raw data
    data_path = OUTPUT_DIR / f"raw_results_{timestamp}.json"
    with open(data_path, "w") as f:
        json.dump({
            "performance": perf_data,
            "results": results
        }, f, indent=2, default=str)
    print(f"   💾 Raw data: {data_path}")
    
    # Print summaries
    print("\n" + "=" * 80)
    print(variance_report)
    print("\n" + "=" * 80)
    print(perf_report)


if __name__ == "__main__":
    main()

