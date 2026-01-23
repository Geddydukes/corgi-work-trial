#!/usr/bin/env python3.11
"""
Generate enhanced variance report with graphs and historical analysis.
Compares proposed decisions to actual decisions and tracks variance over time.
"""

import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from decimal import Decimal
from datetime import datetime
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

def load_historical_reports():
    """Load historical variance reports from text files."""
    historical_data = []
    report_files = [
        'variance_report_900_904.txt',
        'variance_report_900_904_v2.txt',
        'variance_report_900_904_v3.txt',
        'variance_report_905_909.txt',
        'variance_report_905_909_fixed.txt',
        'variance_report_deterministic.txt',
    ]
    
    base_path = Path(__file__).parent.parent
    
    for report_file in report_files:
        file_path = base_path / report_file
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    # Extract summary statistics if available
                    if 'SUMMARY STATISTICS' in content:
                        historical_data.append({
                            'file': report_file,
                            'date': file_path.stat().st_mtime,
                            'content': content
                        })
            except Exception as e:
                print(f"Warning: Could not load {report_file}: {e}")
    
    return historical_data

def generate_variance_report(start_tracking: int = 900, end_tracking: int = 904, generate_graphs: bool = True):
    """Generate variance report for specified claims with graphs."""
    
    from shared.config import Config
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = Config.DATABASE_URL or "postgresql://postgres:postgres@localhost:5432/app_dev"
    engine = create_engine(db_url)
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    print("=" * 100)
    print("ENHANCED VARIANCE REPORT: Proposed vs Actual Decisions")
    print(f"Claims {start_tracking} to {end_tracking}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    print()
    
    results = []
    historical_data = load_historical_reports()
    
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
                        flags, reasoning, engine_version, decided_at
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
            decided_at = decision_result[11] if decision_result[11] else None
            
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
            if cap_amount:
                print(f"  Cap Amount:      ${cap_amount:>12,.2f}")
            print(f"  Confidence:        {confidence:>6.1f}%")
            print(f"  Engine Version:   {engine_version}")
            if decided_at:
                print(f"  Decided At:      {decided_at}")
            
            if approved_items:
                print(f"  Approved Line Items ({len(approved_items)}):")
                for item in approved_items[:5]:
                    if isinstance(item, dict):
                        line_item = item.get('line_item', item)
                        amount = line_item.get('amount', 0)
                        desc = line_item.get('description', 'N/A')
                        print(f"    - ${amount:>10,.2f}  {desc[:60]}")
                if len(approved_items) > 5:
                    print(f"    ... and {len(approved_items) - 5} more")
            
            if ineligible_items:
                print(f"  Ineligible Line Items ({len(ineligible_items)}):")
                for item in ineligible_items[:5]:
                    if isinstance(item, dict):
                        line_item = item.get('line_item', item)
                        amount = line_item.get('amount', 0)
                        desc = line_item.get('description', 'N/A')
                        print(f"    - ${amount:>10,.2f}  {desc[:60]}")
                if len(ineligible_items) > 5:
                    print(f"    ... and {len(ineligible_items) - 5} more")
            
            if notes:
                print(f"  Notes: {notes[:200]}")
            
            if actual_status:
                results.append({
                    'tracking': tracking_num,
                    'proposed_status': proposed_status,
                    'proposed_amount': proposed_amount,
                    'actual_status': actual_status,
                    'actual_amount': actual_amount,
                    'difference': abs(proposed_amount - actual_amount),
                    'status_match': proposed_status.lower() == actual_status.lower(),
                    'eligible_total': eligible_total,
                    'invoice_total': invoice_total,
                    'cap_amount': cap_amount,
                    'confidence': confidence,
                    'engine_version': engine_version,
                    'decided_at': decided_at
                })
            
            print()
    
    # Summary statistics
    if results:
        print("=" * 100)
        print("SUMMARY STATISTICS")
        print("=" * 100)
        print(f"Total Claims Analyzed: {len(results)}")
        
        status_matches = sum(1 for r in results if r['status_match'])
        status_accuracy = status_matches/len(results)*100 if results else 0
        print(f"Status Accuracy: {status_matches}/{len(results)} ({status_accuracy:.1f}%)")
        
        total_proposed = sum(r['proposed_amount'] for r in results)
        total_actual = sum(r['actual_amount'] for r in results)
        total_variance = sum(r['difference'] for r in results)
        avg_variance = total_variance/len(results) if results else 0
        
        print(f"Total Proposed Amount: ${total_proposed:,.2f}")
        print(f"Total Actual Amount: ${total_actual:,.2f}")
        print(f"Total Variance: ${total_variance:,.2f}")
        print(f"Average Variance per Claim: ${avg_variance:,.2f}")
        
        # Calculate MAE (Mean Absolute Error)
        mae = np.mean([r['difference'] for r in results])
        print(f"Mean Absolute Error (MAE): ${mae:,.2f}")
        
        # Calculate percentage errors
        percentage_errors = []
        for r in results:
            if r['actual_amount'] > 0:
                pct_error = abs(r['proposed_amount'] - r['actual_amount']) / r['actual_amount'] * 100
                percentage_errors.append(pct_error)
        if percentage_errors:
            avg_pct_error = np.mean(percentage_errors)
            print(f"Average Percentage Error: {avg_pct_error:.1f}%")
        
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
        
        # Generate graphs if requested
        if generate_graphs:
            try:
                generate_graphs_for_report(results, historical_data, start_tracking, end_tracking)
            except Exception as e:
                print(f"Warning: Could not generate graphs: {e}")
        
        # Mitigation efforts discussion
        print("=" * 100)
        print("ONGOING EFFORTS TO MITIGATE VARIANCE")
        print("=" * 100)
        print()
        print("1. **Deterministic Rule Engine**: Implemented phrase-based category detection")
        print("   to reduce LLM variability in line item classification.")
        print()
        print("2. **Connection Pooling**: Optimized database queries with connection pooling")
        print("   to ensure consistent and fast decision retrieval.")
        print()
        print("3. **User Override System**: Frontend allows manual review and override of")
        print("   decisions, with overrides stored for rule refinement.")
        print()
        print("4. **Cap Management**: Improved cap calculation logic with clear reason tracking")
        print("   (claim_amount, max_benefit, invoice_total).")
        print()
        print("5. **Parallel Processing**: Optimized Google Drive document processing with")
        print("   parallel downloads and Gemini API calls for faster, more consistent results.")
        print()
        print("6. **Status Override**: Added ability to override denied decisions to approved")
        print("   when appropriate, with full audit trail.")
        print()
        print("7. **Historical Analysis**: Tracking variance over time to identify patterns")
        print("   and systematic biases.")
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
            print(f"   Consider refining Gemini prompts for better line item extraction")
        
        if status_accuracy < 80:
            print(f"⚠️  Status accuracy below 80% ({status_accuracy:.1f}%)")
            print(f"   Review business rules and denial logic")
        
        print()

def generate_graphs_for_report(results, historical_data, start_tracking, end_tracking):
    """Generate visualization graphs for variance analysis."""
    
    output_dir = Path(__file__).parent.parent / 'variance'
    output_dir.mkdir(exist_ok=True)
    
    # Graph 1: Status Accuracy
    fig, ax = plt.subplots(figsize=(10, 6))
    tracking_nums = [r['tracking'] for r in results]
    status_matches = [1 if r['status_match'] else 0 for r in results]
    
    ax.bar(tracking_nums, status_matches, color=['green' if m else 'red' for m in status_matches])
    ax.set_xlabel('Claim Tracking Number')
    ax.set_ylabel('Status Match (1=Match, 0=Mismatch)')
    ax.set_title('Status Accuracy by Claim')
    ax.set_ylim([0, 1.2])
    ax.grid(axis='y', alpha=0.3)
    
    accuracy = sum(status_matches) / len(status_matches) * 100 if status_matches else 0
    ax.text(0.5, 0.95, f'Overall Accuracy: {accuracy:.1f}%', 
            transform=ax.transAxes, ha='center', fontsize=12, 
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(output_dir / f'variance_status_accuracy_{start_tracking}_{end_tracking}.png', dpi=150)
    print(f"✓ Saved status accuracy graph: variance_status_accuracy_{start_tracking}_{end_tracking}.png")
    plt.close()
    
    # Graph 2: Amount Variance
    fig, ax = plt.subplots(figsize=(12, 6))
    tracking_nums = [r['tracking'] for r in results]
    proposed_amounts = [r['proposed_amount'] for r in results]
    actual_amounts = [r['actual_amount'] for r in results]
    
    x = np.arange(len(tracking_nums))
    width = 0.35
    
    ax.bar(x - width/2, proposed_amounts, width, label='Proposed', color='blue', alpha=0.7)
    ax.bar(x + width/2, actual_amounts, width, label='Actual', color='orange', alpha=0.7)
    
    ax.set_xlabel('Claim Tracking Number')
    ax.set_ylabel('Amount ($)')
    ax.set_title('Proposed vs Actual Amounts by Claim')
    ax.set_xticks(x)
    ax.set_xticklabels(tracking_nums)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / f'variance_amounts_{start_tracking}_{end_tracking}.png', dpi=150)
    print(f"✓ Saved amounts comparison graph: variance_amounts_{start_tracking}_{end_tracking}.png")
    plt.close()
    
    # Graph 3: Variance Distribution
    fig, ax = plt.subplots(figsize=(10, 6))
    variances = [r['difference'] for r in results]
    
    ax.hist(variances, bins=min(10, len(variances)), edgecolor='black', alpha=0.7)
    ax.set_xlabel('Variance ($)')
    ax.set_ylabel('Number of Claims')
    ax.set_title('Distribution of Amount Variances')
    ax.grid(axis='y', alpha=0.3)
    
    if variances:
        mean_var = np.mean(variances)
        median_var = np.median(variances)
        ax.axvline(mean_var, color='red', linestyle='--', label=f'Mean: ${mean_var:,.2f}')
        ax.axvline(median_var, color='green', linestyle='--', label=f'Median: ${median_var:,.2f}')
        ax.legend()
    
    plt.tight_layout()
    plt.savefig(output_dir / f'variance_distribution_{start_tracking}_{end_tracking}.png', dpi=150)
    print(f"✓ Saved variance distribution graph: variance_distribution_{start_tracking}_{end_tracking}.png")
    plt.close()
    
    # Graph 4: Confidence vs Accuracy
    fig, ax = plt.subplots(figsize=(10, 6))
    confidences = [r['confidence'] for r in results]
    accuracies = [1 if r['status_match'] else 0 for r in results]
    
    ax.scatter(confidences, accuracies, alpha=0.6, s=100)
    ax.set_xlabel('Confidence Score (%)')
    ax.set_ylabel('Status Match (1=Match, 0=Mismatch)')
    ax.set_title('Confidence Score vs Status Accuracy')
    ax.set_ylim([-0.1, 1.1])
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / f'variance_confidence_{start_tracking}_{end_tracking}.png', dpi=150)
    print(f"✓ Saved confidence analysis graph: variance_confidence_{start_tracking}_{end_tracking}.png")
    plt.close()
    
    print()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate enhanced variance report with graphs")
    parser.add_argument('--start', type=int, default=900, help='Start tracking number')
    parser.add_argument('--end', type=int, default=904, help='End tracking number')
    parser.add_argument('--no-graphs', action='store_true', help='Skip graph generation')
    
    args = parser.parse_args()
    
    generate_variance_report(args.start, args.end, generate_graphs=not args.no_graphs)

