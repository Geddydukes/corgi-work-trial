#!/usr/bin/env python3.11
"""
Generate variance report comparing proposed decisions to actual decisions.
"""

import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from decimal import Decimal
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

def generate_variance_report(start_tracking: int = 900, end_tracking: int = 904):
    """Generate variance report for specified claims."""
    import os
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/app_dev")
    engine = create_engine(db_url)
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    print("=" * 100)
    print("VARIANCE REPORT: Proposed vs Actual Decisions")
    print(f"Claims {start_tracking} to {end_tracking}")
    print("=" * 100)
    print()
    
    results = []
    
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO claims, public"))
        
        for tracking_num in tracking_numbers:
            # Get claim ID
            claim_result = conn.execute(
                text("SELECT id FROM claims WHERE claim_tracking_number = :tracking"),
                {"tracking": tracking_num}
            ).fetchone()
            
            if not claim_result:
                print(f"Claim {tracking_num}: Not found")
                continue
            
            claim_id = claim_result[0]
            
            # Get latest proposed decision
            decision_result = conn.execute(
                text("""
                    SELECT 
                        proposed_status, proposed_benefit_amount, eligible_total, invoice_total,
                        cap_amount, confidence_score, approved_line_items, ineligible_line_items,
                        flags, reasoning, engine_version
                    FROM decisions
                    WHERE claim_id = :claim_id AND is_active = true
                    ORDER BY decided_at DESC
                    LIMIT 1
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
            if not decision_result:
                print(f"Claim {tracking_num}: No proposed decision found")
                continue
            
            proposed_status = decision_result[0]
            proposed_amount = float(decision_result[1]) if decision_result[1] else 0.0
            eligible_total = float(decision_result[2]) if decision_result[2] else 0.0
            invoice_total = float(decision_result[3]) if decision_result[3] else 0.0
            cap_amount = float(decision_result[4]) if decision_result[4] else None
            confidence = float(decision_result[5]) if decision_result[5] else 0.0
            approved_items = decision_result[6] if decision_result[6] else []
            ineligible_items = decision_result[7] if decision_result[7] else []
            flags = decision_result[8] if decision_result[8] else {}
            reasoning = decision_result[9] if decision_result[9] else {}
            engine_version = decision_result[10] if decision_result[10] else "unknown"
            
            # Get actual decision from decision_validation
            actual_result = conn.execute(
                text("""
                    SELECT actual_status, actual_paid_amount, adjudication_notes
                    FROM decision_validation
                    WHERE claim_id = :claim_id
                    ORDER BY actual_decision_date DESC
                    LIMIT 1
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
            if actual_result:
                actual_status = actual_result[0]
                actual_amount = float(actual_result[1]) if actual_result[1] else 0.0
                notes = actual_result[2] if actual_result[2] else ""
            else:
                # Try to get from variance report data if available
                actual_status = None
                actual_amount = None
                notes = ""
            
            # Print claim details
            print("-" * 100)
            print(f"Claim {tracking_num}")
            print("-" * 100)
            
            if actual_status:
                status_match = "✅" if proposed_status.lower() == actual_status.lower() else "❌"
                print(f"  Proposed Status: {proposed_status.upper():<10} | Actual Status: {actual_status.upper():<10} {status_match}")
                print(f"  Proposed Amount: ${proposed_amount:>12,.2f} | Actual Amount: ${actual_amount:>12,.2f} | Difference: ${abs(proposed_amount - actual_amount):>12,.2f}")
            else:
                print(f"  Proposed Status: {proposed_status.upper():<10} | Actual Status: {'N/A':<10}")
                print(f"  Proposed Amount: ${proposed_amount:>12,.2f} | Actual Amount: {'N/A':>12} | Difference: {'N/A':>12}")
            
            print(f"  Eligible Total:  ${eligible_total:>12,.2f} | Invoice Total: ${invoice_total:>12,.2f}")
            print(f"  Confidence:        {confidence:>6.1f}%")
            print(f"  Engine Version:   {engine_version}")
            
            if approved_items:
                print(f"  Approved Line Items ({len(approved_items)}):")
                for item in approved_items[:10]:  # Show first 10
                    if isinstance(item, dict):
                        line_item = item.get('line_item', item)
                        amount = line_item.get('amount', 0)
                        desc = line_item.get('description', 'N/A')
                        analysis = item.get('analysis', {})
                        reasoning = analysis.get('reasoning', '')[:80] if analysis.get('reasoning') else ''
                        print(f"    - ${amount:>10,.2f}  {desc[:50]}")
                        if reasoning:
                            print(f"      Reason: {reasoning}")
                if len(approved_items) > 10:
                    print(f"    ... and {len(approved_items) - 10} more")
            
            if ineligible_items:
                print(f"  Ineligible Line Items ({len(ineligible_items)}):")
                for item in ineligible_items[:10]:  # Show first 10
                    if isinstance(item, dict):
                        line_item = item.get('line_item', item)
                        amount = line_item.get('amount', 0)
                        desc = line_item.get('description', 'N/A')
                        analysis = item.get('analysis', {})
                        reasoning = analysis.get('reasoning', '')[:80] if analysis.get('reasoning') else ''
                        # Get category tags if available
                        categories = []
                        if item.get('is_rent'):
                            categories.append('RENT')
                        if item.get('is_month_to_month'):
                            categories.append('MONTH_TO_MONTH')
                        if item.get('is_cleaning'):
                            categories.append('CLEANING')
                        if item.get('is_repair'):
                            categories.append('REPAIR')
                        if item.get('is_contractual_fee'):
                            categories.append('CONTRACTUAL_FEE')
                        if item.get('is_improper_notice'):
                            categories.append('IMPROPER_NOTICE')
                        if item.get('is_other_insurance'):
                            categories.append('OTHER_INSURANCE')
                        if item.get('is_normal_wear_tear'):
                            categories.append('NORMAL_WEAR_TEAR')
                        category_str = f" [{', '.join(categories)}]" if categories else ""
                        print(f"    - ${amount:>10,.2f}  {desc[:50]}{category_str}")
                        if reasoning:
                            print(f"      Reason: {reasoning}")
                if len(ineligible_items) > 10:
                    print(f"    ... and {len(ineligible_items) - 10} more")
            
            if notes:
                print(f"  Notes: {notes}")
            
            if actual_status:
                results.append({
                    'tracking': tracking_num,
                    'proposed_status': proposed_status,
                    'proposed_amount': proposed_amount,
                    'actual_status': actual_status,
                    'actual_amount': actual_amount,
                    'difference': abs(proposed_amount - actual_amount),
                    'status_match': proposed_status.lower() == actual_status.lower()
                })
            
            print()
    
    # Summary statistics
    if results:
        print("=" * 100)
        print("SUMMARY STATISTICS")
        print("=" * 100)
        print(f"Total Claims Analyzed: {len(results)}")
        
        status_matches = sum(1 for r in results if r['status_match'])
        print(f"Status Accuracy: {status_matches}/{len(results)} ({status_matches/len(results)*100:.1f}%)")
        
        total_proposed = sum(r['proposed_amount'] for r in results)
        total_actual = sum(r['actual_amount'] for r in results)
        total_variance = sum(r['difference'] for r in results)
        
        print(f"Total Proposed Amount: ${total_proposed:,.2f}")
        print(f"Total Actual Amount: ${total_actual:,.2f}")
        print(f"Total Variance: ${total_variance:,.2f}")
        print(f"Average Variance per Claim: ${total_variance/len(results):,.2f}")
        print()
        
        # Status mismatches
        mismatches = [r for r in results if not r['status_match']]
        if mismatches:
            print("=" * 100)
            print("STATUS MISMATCHES")
            print("=" * 100)
            for r in mismatches:
                print(f"Claim {r['tracking']}:")
                print(f"  Proposed: {r['proposed_status'].upper()} ${r['proposed_amount']:,.2f}")
                print(f"  Actual:   {r['actual_status'].upper()} ${r['actual_amount']:,.2f}")
            print()
        
        # Amount variances
        amount_variances = [r for r in results if r['difference'] > 0.01]
        if amount_variances:
            print("=" * 100)
            print("AMOUNT VARIANCES (> $0.01)")
            print("=" * 100)
            for r in amount_variances:
                print(f"Claim {r['tracking']}:")
                print(f"  Proposed: ${r['proposed_amount']:,.2f}")
                print(f"  Actual:   ${r['actual_amount']:,.2f}")
                print(f"  Difference: ${r['difference']:,.2f}")
            print()
        
        # Recommendations
        print("=" * 100)
        print("RECOMMENDATIONS")
        print("=" * 100)
        if mismatches:
            print(f"⚠️  {len(mismatches)} status mismatch(es) detected:")
            for r in mismatches:
                if r['proposed_status'].lower() == 'approve' and r['actual_status'].lower() == 'deny':
                    print(f"   - Claim {r['tracking']}: False positive (approved but should be denied)")
                elif r['proposed_status'].lower() == 'deny' and r['actual_status'].lower() == 'approve':
                    print(f"   - Claim {r['tracking']}: False negative (denied but should be approved)")
        
        if amount_variances:
            avg_variance = sum(r['difference'] for r in amount_variances) / len(amount_variances)
            print(f"⚠️  {len(amount_variances)} amount variance(es) detected (avg: ${avg_variance:,.2f})")
            print(f"   Review line item analysis logic and coverage rules")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate variance report")
    parser.add_argument('--start', type=int, default=900, help='Start tracking number')
    parser.add_argument('--end', type=int, default=904, help='End tracking number')
    
    args = parser.parse_args()
    
    generate_variance_report(args.start, args.end)
