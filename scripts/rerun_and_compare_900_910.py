#!/usr/bin/env python3.11
"""
Rerun claims 900-910 with the new lenient system and compare with previous runs.
"""

import sys
import asyncio
import json
import time
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine, text
from typing import Dict, List, Optional
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
API_URL = "http://localhost:8000/api/v1"
DB_URL = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
START_TRACKING = 900
END_TRACKING = 920
PREVIOUS_RESULTS_DIR = Path(__file__).parent / "archive" / "claims_900_920_results"
OUTPUT_DIR = Path(__file__).parent / "claims_900_920_lenient_results"
OUTPUT_DIR.mkdir(exist_ok=True)


def get_claim_ids_from_tracking_numbers(tracking_numbers: List[str]) -> Dict[str, int]:
    """Get claim IDs for tracking numbers."""
    engine = create_engine(DB_URL)
    claim_ids = {}
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for tracking in tracking_numbers:
            result = conn.execute(
                text("SELECT id FROM claims WHERE claim_tracking_number = :tracking"),
                {"tracking": tracking}
            ).fetchone()
            
            if result:
                claim_ids[tracking] = result[0]
            else:
                print(f"⚠️  Warning: Claim {tracking} not found in database")
    
    return claim_ids


def submit_batch(claim_ids: List[int]) -> str:
    """Submit batch evaluation and return batch_id."""
    url = f"{API_URL}/batch/evaluate"
    payload = {"claim_ids": claim_ids}
    
    print(f"📤 Submitting batch with {len(claim_ids)} claims...")
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"❌ Cannot connect to server at {API_URL}. "
            "Please make sure the server is running: "
            "uvicorn decision_service.main:app --host 0.0.0.0 --port 8000 --reload"
        )
    
    data = response.json()
    batch_id = data["batch_id"]
    print(f"✅ Batch submitted: {batch_id}")
    
    return batch_id


def wait_for_batch_completion(batch_id: str, poll_interval: int = 5, max_wait: int = 1800) -> Dict:
    """Wait for batch to complete and return final status."""
    url = f"{API_URL}/batch/{batch_id}/status"
    start_time = time.time()
    last_processed = 0
    
    print(f"⏳ Waiting for batch {batch_id} to complete...")
    print(f"   (This may take several minutes for {END_TRACKING - START_TRACKING + 1} claims with Gemini processing)")
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            status = response.json()
            processed = status.get("processed_count", 0)
            total = status.get("claim_count", 0)
            batch_status = status.get("status", "unknown")
            successful = status.get("successful_count", 0)
            failed = status.get("failed_count", 0)
            
            # Only print if status changed
            if processed != last_processed:
                elapsed = int(time.time() - start_time)
                print(f"   [{elapsed}s] Status: {batch_status} | Processed: {processed}/{total} | Success: {successful} | Failed: {failed}")
                last_processed = processed
            
            if batch_status in ["completed", "failed"]:
                print()  # New line after status updates
                return status
            
            time.sleep(poll_interval)
        except requests.exceptions.Timeout:
            # Continue polling even if one request times out
            elapsed = int(time.time() - start_time)
            print(f"   [{elapsed}s] Status check timeout, continuing to poll...")
            time.sleep(poll_interval)
        except requests.exceptions.RequestException as e:
            elapsed = int(time.time() - start_time)
            print(f"   [{elapsed}s] Error checking status: {e}, retrying...")
            time.sleep(poll_interval)
    
    raise TimeoutError(f"Batch {batch_id} did not complete within {max_wait} seconds")


def extract_results(tracking_numbers: List[str], claim_ids: Dict[str, int]) -> Dict:
    """Extract decision results from database."""
    engine = create_engine(DB_URL)
    results = {}
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for tracking in tracking_numbers:
            if tracking not in claim_ids:
                continue
            
            claim_id = claim_ids[tracking]
            
            # Get latest decision
            decision_result = conn.execute(
                text("""
                    SELECT 
                        proposed_status, proposed_benefit_amount, eligible_total, invoice_total,
                        confidence_score, engine_version, decided_at, approved_line_items
                    FROM decisions
                    WHERE claim_id = :claim_id AND is_active = true
                    ORDER BY decided_at DESC
                    LIMIT 1
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
            if decision_result:
                # Get actual validation if available
                validation_result = conn.execute(
                    text("""
                        SELECT actual_status, actual_paid_amount
                        FROM decision_validation
                        WHERE claim_id = :claim_id
                        ORDER BY actual_decision_date DESC
                        LIMIT 1
                    """),
                    {"claim_id": claim_id}
                ).fetchone()
                
                results[tracking] = {
                    "claim_id": claim_id,
                    "proposed_status": decision_result[0],
                    "proposed_amount": float(decision_result[1]) if decision_result[1] else 0.0,
                    "eligible_total": float(decision_result[2]) if decision_result[2] else 0.0,
                    "invoice_total": float(decision_result[3]) if decision_result[3] else 0.0,
                    "confidence": float(decision_result[4]) if decision_result[4] else 0.0,
                    "engine_version": decision_result[5] or "unknown",
                    "decided_at": decision_result[6].isoformat() if decision_result[6] else None,
                    "approved_items_count": len(decision_result[7]) if decision_result[7] else 0,
                    "actual_status": validation_result[0] if validation_result else None,
                    "actual_amount": float(validation_result[1]) if validation_result and validation_result[1] else None,
                }
    
    return results


def load_previous_results() -> Optional[Dict]:
    """Load previous results from archive."""
    metrics_file = PREVIOUS_RESULTS_DIR / "metrics.json"
    results_file = PREVIOUS_RESULTS_DIR / "results_claims_900_to_920.json"
    
    previous = {}
    
    if metrics_file.exists():
        with open(metrics_file) as f:
            previous["metrics"] = json.load(f)
    
    if results_file.exists():
        with open(results_file) as f:
            previous["results"] = json.load(f)
    
    return previous if previous else None


def calculate_metrics(results: Dict) -> Dict:
    """Calculate metrics from results."""
    if not results:
        return {}
    
    total_claims = len(results)
    status_matches = 0
    amount_differences = []
    total_proposed = 0.0
    total_actual = 0.0
    
    for tracking, data in results.items():
        proposed_amount = data.get("proposed_amount", 0.0)
        actual_amount = data.get("actual_amount")
        proposed_status = data.get("proposed_status", "").lower()
        actual_status = data.get("actual_status", "").lower() if data.get("actual_status") else None
        
        total_proposed += proposed_amount
        
        if actual_status:
            if proposed_status == actual_status:
                status_matches += 1
            total_actual += actual_amount or 0.0
            if actual_amount is not None:
                amount_differences.append(abs(proposed_amount - actual_amount))
    
    metrics = {
        "total_claims": total_claims,
        "status_accuracy": status_matches / total_claims if total_claims > 0 else 0.0,
        "status_matches": status_matches,
        "total_proposed_amount": total_proposed,
        "total_actual_amount": total_actual,
        "total_variance": total_actual - total_proposed,
        "avg_proposed_amount": total_proposed / total_claims if total_claims > 0 else 0.0,
        "avg_actual_amount": total_actual / status_matches if status_matches > 0 else 0.0,
    }
    
    if amount_differences:
        metrics["mean_absolute_error"] = sum(amount_differences) / len(amount_differences)
        metrics["max_absolute_error"] = max(amount_differences)
        metrics["min_absolute_error"] = min(amount_differences)
    
    return metrics


def generate_comparison_report(new_results: Dict, new_metrics: Dict, previous: Optional[Dict]) -> str:
    """Generate comparison report."""
    report = []
    report.append("=" * 100)
    report.append("VARIANCE COMPARISON REPORT: Claims 900-920")
    report.append("=" * 100)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # New run summary
    report.append("=" * 100)
    report.append("NEW RUN (Lenient System) - Summary")
    report.append("=" * 100)
    report.append(f"Total Claims: {new_metrics.get('total_claims', 0)}")
    report.append(f"Status Accuracy: {new_metrics.get('status_accuracy', 0):.2%} ({new_metrics.get('status_matches', 0)}/{new_metrics.get('total_claims', 0)})")
    report.append(f"Average Proposed Amount: ${new_metrics.get('avg_proposed_amount', 0):,.2f}")
    if new_metrics.get('avg_actual_amount'):
        report.append(f"Average Actual Amount: ${new_metrics.get('avg_actual_amount', 0):,.2f}")
    if new_metrics.get('mean_absolute_error'):
        report.append(f"Mean Absolute Error: ${new_metrics.get('mean_absolute_error', 0):,.2f}")
    report.append("")
    
    # Previous run comparison
    if previous and "metrics" in previous:
        prev_metrics = previous["metrics"]
        report.append("=" * 100)
        report.append("PREVIOUS RUN - Summary")
        report.append("=" * 100)
        report.append(f"Total Claims: {prev_metrics.get('total_claims', 0)}")
        if 'accuracy' in prev_metrics:
            report.append(f"Status Accuracy: {prev_metrics.get('accuracy', 0):.2%}")
        report.append(f"Average Proposed Amount: ${prev_metrics.get('avg_proposed_benefit', 0):,.2f}")
        if prev_metrics.get('avg_actual_benefit'):
            report.append(f"Average Actual Amount: ${prev_metrics.get('avg_actual_benefit', 0):,.2f}")
        if prev_metrics.get('mean_absolute_error') is not None:
            report.append(f"Mean Absolute Error: ${prev_metrics.get('mean_absolute_error', 0):,.2f}")
        report.append("")
        
        # Comparison
        report.append("=" * 100)
        report.append("COMPARISON")
        report.append("=" * 100)
        
        new_acc = new_metrics.get('status_accuracy', 0)
        prev_acc = prev_metrics.get('accuracy', 0)
        acc_change = new_acc - prev_acc
        report.append(f"Status Accuracy Change: {acc_change:+.2%} ({new_acc:.2%} vs {prev_acc:.2%})")
        
        new_mae = new_metrics.get('mean_absolute_error', 0)
        prev_mae = prev_metrics.get('mean_absolute_error', 0)
        if new_mae and prev_mae:
            mae_change = new_mae - prev_mae
            report.append(f"Mean Absolute Error Change: ${mae_change:+,.2f} (${new_mae:,.2f} vs ${prev_mae:,.2f})")
        
        new_avg = new_metrics.get('avg_proposed_amount', 0)
        prev_avg = prev_metrics.get('avg_proposed_benefit', 0)
        avg_change = new_avg - prev_avg
        report.append(f"Average Proposed Amount Change: ${avg_change:+,.2f} (${new_avg:,.2f} vs ${prev_avg:,.2f})")
        report.append("")
    
    # Detailed results
    report.append("=" * 100)
    report.append("DETAILED RESULTS (New Run)")
    report.append("=" * 100)
    
    for tracking in sorted(new_results.keys(), key=int):
        data = new_results[tracking]
        report.append(f"\nClaim {tracking} (ID: {data['claim_id']}):")
        report.append(f"  Proposed: {data['proposed_status'].upper()} ${data['proposed_amount']:,.2f}")
        if data.get('actual_status'):
            status_match = "✅" if data['proposed_status'].lower() == data['actual_status'].lower() else "❌"
            actual_amount = data.get('actual_amount') or 0.0
            report.append(f"  Actual:   {data['actual_status'].upper()} ${actual_amount:,.2f} {status_match}")
            if data.get('actual_amount') is not None:
                diff = abs(data['proposed_amount'] - data['actual_amount'])
                report.append(f"  Difference: ${diff:,.2f}")
        else:
            report.append(f"  Actual:   N/A (no validation data)")
        report.append(f"  Confidence: {data['confidence']:.1f}%")
        report.append(f"  Approved Items: {data['approved_items_count']}")
    
    return "\n".join(report)


def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Rerun and compare claims 900-910")
    parser.add_argument('--extract-only', action='store_true', 
                       help='Only extract results without submitting a new batch')
    parser.add_argument('--batch-id', type=str, 
                       help='Check specific batch ID status and extract results')
    args = parser.parse_args()
    
    print("=" * 100)
    print("RERUN AND COMPARE: Claims 900-910 with Lenient System")
    print("=" * 100)
    print()
    
    # Step 1: Get claim IDs
    tracking_numbers = [str(i) for i in range(START_TRACKING, END_TRACKING + 1)]
    print(f"📋 Getting claim IDs for tracking numbers {START_TRACKING}-{END_TRACKING}...")
    claim_ids_map = get_claim_ids_from_tracking_numbers(tracking_numbers)
    
    if not claim_ids_map:
        print("❌ No claims found. Exiting.")
        return
    
    claim_ids = list(claim_ids_map.values())
    print(f"✅ Found {len(claim_ids)} claims")
    print()
    
    # If extract-only mode, skip batch submission
    if args.extract_only:
        print("📊 Extract-only mode: Skipping batch submission, extracting existing results...")
        print()
    elif args.batch_id:
        # Check specific batch status
        print(f"📊 Checking batch {args.batch_id}...")
        try:
            final_status = wait_for_batch_completion(args.batch_id)
            print(f"✅ Batch completed: {final_status.get('status')}")
            print(f"   Processed: {final_status.get('processed_count')}/{final_status.get('claim_count')}")
            print(f"   Successful: {final_status.get('successful_count')}")
            print(f"   Failed: {final_status.get('failed_count')}")
            print()
        except Exception as e:
            print(f"⚠️  Error checking batch: {e}")
            print("   Continuing to extract results anyway...")
            print()
    else:
        # Step 2: Submit batch
        try:
            batch_id = submit_batch(claim_ids)
        except ConnectionError as e:
            print(f"\n{e}")
            print("\nTo start the server, run:")
            print("  cd /Users/geddydukes/Desktop/Corgi")
            print("  uvicorn decision_service.main:app --host 0.0.0.0 --port 8000 --reload")
            return
        except Exception as e:
            print(f"❌ Error submitting batch: {e}")
            return
        
        # Step 3: Wait for completion
        try:
            final_status = wait_for_batch_completion(batch_id)
            print(f"✅ Batch completed: {final_status.get('status')}")
            print(f"   Processed: {final_status.get('processed_count')}/{final_status.get('claim_count')}")
            print(f"   Successful: {final_status.get('successful_count')}")
            print(f"   Failed: {final_status.get('failed_count')}")
        except Exception as e:
            print(f"⚠️  Batch still processing or error: {e}")
            print("   Continuing to extract results from completed claims...")
            print()
    
    print()
    
    # Step 4: Extract results
    print("📊 Extracting results from database...")
    results = extract_results(tracking_numbers, claim_ids_map)
    print(f"✅ Extracted {len(results)} results")
    print()
    
    # Step 5: Calculate metrics
    metrics = calculate_metrics(results)
    
    # Step 6: Load previous results
    previous = load_previous_results()
    
    # Step 7: Save new results
    results_file = OUTPUT_DIR / f"results_claims_{START_TRACKING}_to_{END_TRACKING}_lenient.json"
    with open(results_file, 'w') as f:
        json.dump({
            "run_date": datetime.now().isoformat(),
            "tracking_range": {"start": START_TRACKING, "end": END_TRACKING},
            "system": "lenient",
            "results": results,
            "metrics": metrics
        }, f, indent=2)
    print(f"💾 Saved results to: {results_file}")
    
    metrics_file = OUTPUT_DIR / f"metrics_claims_{START_TRACKING}_to_{END_TRACKING}_lenient.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"💾 Saved metrics to: {metrics_file}")
    
    # Step 8: Generate comparison report
    report = generate_comparison_report(results, metrics, previous)
    report_file = OUTPUT_DIR / f"variance_comparison_claims_{START_TRACKING}_to_{END_TRACKING}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"💾 Saved comparison report to: {report_file}")
    print()
    
    # Print report to console
    print(report)
    print()
    print("=" * 100)
    print("✅ COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()

