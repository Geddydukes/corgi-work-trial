#!/usr/bin/env python3
"""
Full Pipeline Performance Test - Including Google Drive
Tests the complete flow: Drive fetch → OCR → Decision Engine
with fresh claims that haven't been cached.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from sqlalchemy import create_engine, text

# Configuration
API_URL = "http://localhost:8000/api/v1"
DB_URL = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "1-sEEs61X3q7AG8MV6y6wlX637KLOnMs4")
OUTPUT_DIR = Path(__file__).parent / "performance_test_results"
OUTPUT_DIR.mkdir(exist_ok=True)

engine = create_engine(DB_URL)


def check_server():
    """Check if server is running."""
    try:
        requests.get(f"{API_URL}/batch/1/status", timeout=5)
        return True
    except:
        try:
            requests.get("http://localhost:8000/api/v1/batch/1/status", timeout=5)
            return True
        except:
            return False


def get_fresh_tracking_numbers(count=30):
    """Get tracking numbers that exist in Drive but have no documents in DB."""
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        # Find claims with NO documents (fresh for processing)
        result = conn.execute(
            text("""
                SELECT c.claim_tracking_number::int as tracking
                FROM claims c
                LEFT JOIN claim_documents cd ON c.id = cd.claim_id
                WHERE c.claim_tracking_number ~ '^[0-9]+$'
                  AND c.claim_tracking_number::int BETWEEN 500 AND 700
                GROUP BY c.claim_tracking_number
                HAVING COUNT(cd.id) = 0
                ORDER BY c.claim_tracking_number::int
                LIMIT :count
            """),
            {"count": count}
        ).fetchall()
        
        return [r[0] for r in result]


def process_claim_from_drive(tracking_number, timeout=180):
    """Process a single claim from Google Drive."""
    start = time.time()
    try:
        response = requests.post(
            f"{API_URL}/claims/process-from-drive",
            json={
                "tracking_number": str(tracking_number),
                "drive_folder_id": DRIVE_FOLDER_ID
            },
            timeout=timeout
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            return {
                "tracking": tracking_number,
                "success": True,
                "time": elapsed,
                "status": data.get("proposed_status"),
                "amount": data.get("proposed_benefit_amount"),
                "line_items": data.get("line_item_count", 0)
            }
        else:
            return {
                "tracking": tracking_number,
                "success": False,
                "time": elapsed,
                "error": f"HTTP {response.status_code}: {response.text[:100]}"
            }
    except requests.exceptions.Timeout:
        return {
            "tracking": tracking_number,
            "success": False,
            "time": time.time() - start,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "tracking": tracking_number,
            "success": False,
            "time": time.time() - start,
            "error": str(e)
        }


def run_parallel_processing(tracking_numbers, max_concurrent=10):
    """Process multiple claims in parallel via Drive endpoint."""
    print(f"\n🚀 Processing {len(tracking_numbers)} claims from Google Drive")
    print(f"   Concurrency: {max_concurrent} claims in parallel")
    print(f"   (Each claim: 4 concurrent document downloads)")
    print("")
    
    results = []
    start_time = time.time()
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(process_claim_from_drive, t): t 
            for t in tracking_numbers
        }
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            
            elapsed = time.time() - start_time
            status = "✅" if result["success"] else "❌"
            
            if result["success"]:
                print(f"   {status} [{completed}/{len(tracking_numbers)}] Claim {result['tracking']}: "
                      f"{result['time']:.1f}s - {result['status']} ${result.get('amount', 0)}")
            else:
                print(f"   {status} [{completed}/{len(tracking_numbers)}] Claim {result['tracking']}: "
                      f"{result['time']:.1f}s - {result.get('error', 'Unknown error')[:50]}")
    
    total_time = time.time() - start_time
    return results, total_time


def get_validation_data(tracking_numbers):
    """Get validation data for claims."""
    validation = {}
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for tracking in tracking_numbers:
            result = conn.execute(
                text("""
                    SELECT dv.actual_status, dv.actual_paid_amount
                    FROM decision_validation dv
                    JOIN claims c ON dv.claim_id = c.id
                    WHERE c.claim_tracking_number = :tracking
                    ORDER BY dv.actual_decision_date DESC
                    LIMIT 1
                """),
                {"tracking": str(tracking)}
            ).fetchone()
            
            if result:
                validation[tracking] = {
                    "actual_status": result[0],
                    "actual_amount": float(result[1]) if result[1] else 0
                }
    
    return validation


def generate_reports(results, total_time, validation):
    """Generate performance and variance reports."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    # Calculate metrics
    if successful:
        avg_time = sum(r["time"] for r in successful) / len(successful)
        min_time = min(r["time"] for r in successful)
        max_time = max(r["time"] for r in successful)
    else:
        avg_time = min_time = max_time = 0
    
    throughput = len(results) / total_time * 60 if total_time > 0 else 0
    
    # Build report
    report = []
    report.append("=" * 80)
    report.append("FULL PIPELINE PERFORMANCE REPORT")
    report.append("Google Drive → OCR → Document Classification → Decision Engine")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("CONFIGURATION")
    report.append("-" * 40)
    report.append("Batch concurrency: 10 claims in parallel")
    report.append("Document download concurrency: 4 per claim")
    report.append("LLM: Gemini 2.5 Flash")
    report.append("")
    report.append("PERFORMANCE METRICS")
    report.append("-" * 40)
    report.append(f"Total Claims: {len(results)}")
    report.append(f"Successful: {len(successful)}")
    report.append(f"Failed: {len(failed)}")
    report.append(f"Success Rate: {len(successful) / len(results) * 100:.1f}%")
    report.append("")
    report.append(f"Total Wall Clock Time: {total_time:.1f}s ({total_time/60:.1f} min)")
    report.append(f"Average Time per Claim: {avg_time:.1f}s")
    report.append(f"Min/Max Time: {min_time:.1f}s / {max_time:.1f}s")
    report.append(f"Throughput: {throughput:.1f} claims/min")
    
    # Variance analysis
    if validation:
        report.append("")
        report.append("DECISION ACCURACY")
        report.append("-" * 40)
        
        validated = []
        for r in successful:
            if r["tracking"] in validation:
                v = validation[r["tracking"]]
                match = r.get("status", "").lower() == v["actual_status"].lower()
                diff = abs(float(r.get("amount", 0)) - v["actual_amount"])
                validated.append({
                    "tracking": r["tracking"],
                    "proposed_status": r.get("status"),
                    "actual_status": v["actual_status"],
                    "proposed_amount": r.get("amount", 0),
                    "actual_amount": v["actual_amount"],
                    "status_match": match,
                    "amount_diff": diff
                })
        
        if validated:
            correct = sum(1 for v in validated if v["status_match"])
            report.append(f"Claims with validation: {len(validated)}")
            report.append(f"Status accuracy: {correct / len(validated) * 100:.1f}%")
            mae = sum(v["amount_diff"] for v in validated) / len(validated)
            report.append(f"Mean Absolute Error: ${mae:,.2f}")
    
    # Comparison section
    report.append("")
    report.append("OPTIMIZATION COMPARISON")
    report.append("-" * 40)
    report.append("Before optimizations:")
    report.append("  - Batch concurrency: 2")
    report.append("  - Doc downloads: 2 concurrent")
    report.append("  - Avg time: ~53s per claim")
    report.append("  - Throughput: ~1.1 claims/min")
    report.append("")
    report.append("After optimizations:")
    report.append("  - Batch concurrency: 10")
    report.append("  - Doc downloads: 4 concurrent")
    report.append(f"  - Avg time: {avg_time:.1f}s per claim")
    report.append(f"  - Throughput: {throughput:.1f} claims/min")
    
    if avg_time > 0:
        speedup = 53.0 / avg_time
        report.append(f"\n🚀 SPEEDUP: {speedup:.1f}x faster!")
    
    # Failures
    if failed:
        report.append("")
        report.append("FAILURES")
        report.append("-" * 40)
        for f in failed[:10]:
            report.append(f"  Claim {f['tracking']}: {f.get('error', 'Unknown')[:60]}")
    
    report_text = "\n".join(report)
    
    # Save files
    perf_path = OUTPUT_DIR / f"full_pipeline_{timestamp}.txt"
    with open(perf_path, "w") as f:
        f.write(report_text)
    
    data_path = OUTPUT_DIR / f"full_pipeline_raw_{timestamp}.json"
    with open(data_path, "w") as f:
        json.dump({
            "config": {
                "batch_concurrency": 10,
                "doc_concurrency": 4,
                "total_claims": len(results)
            },
            "performance": {
                "total_time": total_time,
                "avg_time": avg_time,
                "throughput": throughput
            },
            "results": results
        }, f, indent=2, default=str)
    
    return report_text, perf_path, data_path


def main():
    print("=" * 80)
    print("FULL PIPELINE PERFORMANCE TEST")
    print("Google Drive → OCR → Classification → LLM → Decision")
    print("=" * 80)
    print("")
    
    # Check server
    if not check_server():
        print("❌ Server not running! Start with:")
        print("   uvicorn decision_service.main:app --host 0.0.0.0 --port 8000 --reload")
        return
    
    print("✅ Server is running")
    
    # Get fresh claims
    print("\n📋 Finding fresh claims (no documents in DB)...")
    tracking_numbers = get_fresh_tracking_numbers(30)
    
    if len(tracking_numbers) < 10:
        print(f"⚠️  Only found {len(tracking_numbers)} fresh claims")
        if not tracking_numbers:
            print("❌ No fresh claims available for testing")
            return
    
    print(f"   Found {len(tracking_numbers)} claims: {tracking_numbers}")
    
    # Get validation data
    print("\n📊 Loading validation data...")
    validation = get_validation_data(tracking_numbers)
    print(f"   Found validation for {len(validation)} claims")
    
    # Process claims
    results, total_time = run_parallel_processing(tracking_numbers, max_concurrent=10)
    
    # Summary
    successful = [r for r in results if r["success"]]
    print(f"\n✅ Completed: {len(successful)}/{len(results)} successful")
    print(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    
    if successful:
        avg = sum(r["time"] for r in successful) / len(successful)
        print(f"   Average: {avg:.1f}s per claim")
        print(f"   Throughput: {len(results) / total_time * 60:.1f} claims/min")
    
    # Generate reports
    report_text, perf_path, data_path = generate_reports(results, total_time, validation)
    
    print(f"\n💾 Reports saved:")
    print(f"   {perf_path}")
    print(f"   {data_path}")
    
    print("\n" + report_text)


if __name__ == "__main__":
    main()

