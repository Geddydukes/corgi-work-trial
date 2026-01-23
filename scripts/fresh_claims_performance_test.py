#!/usr/bin/env python3
"""
Fresh Claims Performance Test - No Caching
Uploads new documents and processes claims to measure true LLM performance.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from sqlalchemy import create_engine, text

# Configuration
API_URL = "http://localhost:8000/api/v1"
DB_URL = "postgresql://postgres:postgres@localhost:5432/app_dev"
LOCAL_PATH = Path(os.getenv("LOCAL_FILES_PATH", "./local_files"))
OUTPUT_DIR = Path(__file__).parent / "performance_test_results"
OUTPUT_DIR.mkdir(exist_ok=True)

engine = create_engine(DB_URL)


def get_fresh_claims(count=30):
    """Get claims with no documents in DB but local files available."""
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        result = conn.execute(
            text("""
                SELECT c.id, c.claim_tracking_number::int as tracking
                FROM claims c
                LEFT JOIN claim_documents cd ON c.id = cd.claim_id
                WHERE c.claim_tracking_number ~ '^[0-9]+$'
                  AND c.claim_tracking_number::int BETWEEN 500 AND 650
                GROUP BY c.id, c.claim_tracking_number
                HAVING COUNT(cd.id) = 0
                ORDER BY c.claim_tracking_number::int
            """)
        ).fetchall()
        
        # Filter to those with local PDFs
        available = []
        for claim_id, tracking in result:
            folder = LOCAL_PATH / str(tracking)
            if folder.exists():
                pdfs = list(folder.glob("*.pdf"))
                if pdfs:
                    available.append((claim_id, tracking, pdfs))
        
        return available[:count]


def process_documents_locally(claims_data, max_concurrent=5):
    """Process documents locally and insert into database."""
    print(f"\n📤 Processing documents for {len(claims_data)} claims (max {max_concurrent} concurrent)...")
    
    # Import the document processor
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from document_service.processor import DocumentProcessor
    
    upload_times = []
    results = []
    
    def process_single(claim_id, tracking, pdfs):
        start = time.time()
        processed = 0
        try:
            processor = DocumentProcessor()
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                for pdf_path in pdfs:
                    try:
                        # Process document
                        result = processor.process_file(str(pdf_path))
                        
                        if result.errors:
                            continue
                        
                        # Calculate file hash
                        import hashlib
                        with open(pdf_path, 'rb') as f:
                            file_hash = hashlib.sha256(f.read()).hexdigest()
                        
                        # Insert into database
                        conn.execute(
                            text("""
                                INSERT INTO claim_documents (
                                    claim_id, file_path, original_filename, file_hash,
                                    file_size_bytes, mime_type, document_type,
                                    classification_confidence, extracted_text, ocr_confidence,
                                    page_count, processing_status, processed_at
                                ) VALUES (
                                    :claim_id, :file_path, :filename, :file_hash,
                                    :size, :mime_type, CAST(:doc_type AS document_type_enum),
                                    :class_conf, :text, :ocr_conf,
                                    :pages, 'completed', NOW()
                                )
                                ON CONFLICT (claim_id, file_hash) DO UPDATE SET
                                    extracted_text = EXCLUDED.extracted_text,
                                    document_type = EXCLUDED.document_type,
                                    processing_status = 'completed',
                                    processed_at = NOW()
                            """),
                            {
                                'claim_id': claim_id,
                                'file_path': str(pdf_path),
                                'filename': pdf_path.name,
                                'file_hash': file_hash,
                                'size': pdf_path.stat().st_size,
                                'mime_type': 'application/pdf',
                                'doc_type': result.document_type.value if result.document_type else 'unknown',
                                'class_conf': result.classification_confidence or 0.0,
                                'text': result.extracted_text or '',
                                'ocr_conf': result.ocr_confidence or 0.0,
                                'pages': result.page_count or 1
                            }
                        )
                        conn.commit()
                        processed += 1
                    except Exception as e:
                        print(f"      Error processing {pdf_path.name}: {e}")
            
            elapsed = time.time() - start
            return (tracking, processed > 0, elapsed, f"{processed}/{len(pdfs)} docs")
        except Exception as e:
            return (tracking, False, time.time() - start, str(e))
    
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(process_single, claim_id, tracking, pdfs): tracking 
            for claim_id, tracking, pdfs in claims_data
        }
        
        for future in as_completed(futures):
            tracking, success, elapsed, detail = future.result()
            upload_times.append(elapsed)
            status = "✅" if success else "❌"
            print(f"   {status} Claim {tracking}: {elapsed:.1f}s - {detail}")
            results.append({
                "tracking": tracking,
                "success": success,
                "upload_time": elapsed,
                "detail": detail
            })
    
    return results, upload_times


def run_batch_evaluation(claim_ids):
    """Run batch evaluation and track performance."""
    print(f"\n🚀 Running batch evaluation for {len(claim_ids)} claims (10 concurrent)...")
    
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
    last_processed = 0
    while time.time() - start_time < 1800:
        try:
            status = requests.get(f"{API_URL}/batch/{batch_id}/status", timeout=60).json()
            
            elapsed = int(time.time() - start_time)
            processed = status.get("processed_count", 0)
            total = status.get("claim_count", 0)
            successful = status.get("successful_count", 0)
            failed = status.get("failed_count", 0)
            
            # Only print when something changes
            if processed != last_processed:
                print(f"   [{elapsed}s] {processed}/{total} processed | {successful} ✅ | {failed} ❌")
                last_processed = processed
            
            if status.get("status") in ["completed", "failed"]:
                break
                
        except Exception as e:
            print(f"   [{int(time.time() - start_time)}s] Poll error: {e}")
        
        time.sleep(2)
    
    total_time = time.time() - start_time
    
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
        "avg_time_per_claim": total_time / len(claim_ids) if claim_ids else 0
    }


def extract_results(claim_ids):
    """Extract decision results."""
    results = []
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for claim_id in claim_ids:
            decision = conn.execute(
                text("""
                    SELECT 
                        d.proposed_status, d.proposed_benefit_amount, d.eligible_total,
                        d.invoice_total, d.confidence_score,
                        jsonb_array_length(d.approved_line_items::jsonb) as approved_count,
                        c.claim_tracking_number
                    FROM decisions d
                    JOIN claims c ON d.claim_id = c.id
                    WHERE d.claim_id = :claim_id AND d.is_active = true
                    ORDER BY d.decided_at DESC
                    LIMIT 1
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
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
                    "tracking": decision[6],
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
                    result["amount_diff"] = abs(result["proposed_amount"] - result["actual_amount"])
                
                results.append(result)
    
    return results


def generate_reports(perf_data, upload_times, results):
    """Generate performance and variance reports."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Performance Report
    report = []
    report.append("=" * 80)
    report.append("FRESH CLAIMS PERFORMANCE REPORT (No Caching)")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("UPLOAD METRICS")
    report.append("-" * 40)
    report.append(f"Claims uploaded: {len(upload_times)}")
    report.append(f"Total upload time: {sum(upload_times):.1f}s")
    report.append(f"Avg upload time: {sum(upload_times)/len(upload_times):.1f}s per claim")
    report.append("")
    report.append("BATCH PROCESSING METRICS (True LLM Performance)")
    report.append("-" * 40)
    report.append(f"Claims processed: {perf_data['claim_count']}")
    report.append(f"Successful: {perf_data['successful_count']}")
    report.append(f"Failed: {perf_data['failed_count']}")
    report.append(f"Success Rate: {perf_data['successful_count'] / perf_data['claim_count'] * 100:.1f}%")
    report.append("")
    report.append(f"Total Processing Time: {perf_data['total_time']:.1f}s ({perf_data['total_time']/60:.1f} min)")
    report.append(f"Average Time per Claim: {perf_data['avg_time_per_claim']:.1f}s")
    report.append(f"Throughput: {perf_data['claim_count'] / perf_data['total_time'] * 60:.1f} claims/min")
    report.append("")
    report.append("CONCURRENCY SETTINGS")
    report.append("-" * 40)
    report.append("Batch concurrency: 10 claims")
    report.append("Document download concurrency: 4")
    
    # Variance section
    validated = [r for r in results if r.get("actual_status")]
    if validated:
        correct = sum(1 for r in validated if r.get("status_match"))
        report.append("")
        report.append("DECISION ACCURACY")
        report.append("-" * 40)
        report.append(f"With validation data: {len(validated)}")
        report.append(f"Status accuracy: {correct / len(validated) * 100:.1f}%")
        
        amounts = [r for r in validated if r.get("actual_amount") is not None]
        if amounts:
            mae = sum(r["amount_diff"] for r in amounts) / len(amounts)
            report.append(f"Mean Absolute Error: ${mae:,.2f}")
    
    report_text = "\n".join(report)
    
    # Save
    perf_path = OUTPUT_DIR / f"fresh_performance_{timestamp}.txt"
    with open(perf_path, "w") as f:
        f.write(report_text)
    
    data_path = OUTPUT_DIR / f"fresh_raw_{timestamp}.json"
    with open(data_path, "w") as f:
        json.dump({
            "performance": perf_data,
            "upload_times": upload_times,
            "results": results
        }, f, indent=2, default=str)
    
    return report_text, perf_path, data_path


def main():
    print("=" * 80)
    print("FRESH CLAIMS PERFORMANCE TEST (No Caching)")
    print("=" * 80)
    print("This test uploads NEW documents and processes claims with real LLM calls.")
    print("")
    
    # Check server
    try:
        requests.get(f"{API_URL}/health", timeout=5)
    except:
        print("❌ Server not running!")
        return
    
    # Get fresh claims
    claims_data = get_fresh_claims(30)
    print(f"📋 Found {len(claims_data)} fresh claims (no documents in DB)")
    
    if len(claims_data) < 10:
        print("⚠️  Not enough fresh claims for meaningful test")
        return
    
    trackings = [t for _, t, _ in claims_data]
    print(f"   Tracking numbers: {trackings}")
    
    # Upload documents
    upload_results, upload_times = upload_documents_batch(claims_data, max_concurrent=5)
    successful_uploads = [r for r in upload_results if r["success"]]
    print(f"\n✅ Uploaded: {len(successful_uploads)}/{len(claims_data)}")
    
    if not successful_uploads:
        print("❌ No documents uploaded successfully")
        return
    
    # Get claim IDs for successful uploads
    claim_ids = [cid for cid, tracking, _ in claims_data 
                 if any(r["tracking"] == tracking and r["success"] for r in upload_results)]
    
    # Run batch evaluation
    perf_data = run_batch_evaluation(claim_ids)
    
    if not perf_data:
        print("❌ Batch processing failed")
        return
    
    print(f"\n✅ Batch completed!")
    print(f"   Total time: {perf_data['total_time']:.1f}s")
    print(f"   Average: {perf_data['avg_time_per_claim']:.1f}s per claim")
    print(f"   Throughput: {perf_data['claim_count'] / perf_data['total_time'] * 60:.1f} claims/min")
    
    # Extract results
    results = extract_results(claim_ids)
    
    # Generate reports
    report_text, perf_path, data_path = generate_reports(perf_data, upload_times, results)
    
    print(f"\n💾 Reports saved:")
    print(f"   {perf_path}")
    print(f"   {data_path}")
    
    print("\n" + report_text)


if __name__ == "__main__":
    main()

