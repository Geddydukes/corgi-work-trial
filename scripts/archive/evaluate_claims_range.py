#!/usr/bin/env python3
"""
Evaluate specific claim range and generate variance report.

This script:
1. Evaluates decisions for claims in a specific range
2. Generates detailed results file
3. Creates variance analysis report with suggestions
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict
import json
from datetime import datetime
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np

from evaluation import DecisionEvaluator, EvaluationMetrics, MismatchRecord


def generate_variance_report(
    metrics: EvaluationMetrics,
    mismatches: List[MismatchRecord],
    output_file: str
):
    """Generate detailed variance report with suggestions."""
    
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("VARIANCE ANALYSIS REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    
    report_lines.append("## EXECUTIVE SUMMARY")
    report_lines.append("-" * 80)
    report_lines.append(f"Total Claims Evaluated: {metrics.total_claims}")
    report_lines.append(f"Overall Accuracy: {metrics.accuracy:.2%}")
    report_lines.append(f"Mean Absolute Error: ${metrics.mean_absolute_error:.2f}")
    report_lines.append(f"Mean Absolute Percentage Error: {metrics.mean_absolute_percentage_error:.2%}")
    report_lines.append("")
    
    report_lines.append("## VARIANCE BREAKDOWN")
    report_lines.append("-" * 80)
    
    status_mismatches = [m for m in mismatches if m.mismatch_type in ['status_only', 'both']]
    amount_mismatches = [m for m in mismatches if m.mismatch_type in ['amount_only', 'both']]
    
    report_lines.append(f"\n### Status Disagreements: {len(status_mismatches)}")
    if status_mismatches:
        false_positives = [m for m in status_mismatches if m.proposed_status == 'approve' and m.actual_status == 'deny']
        false_negatives = [m for m in status_mismatches if m.proposed_status == 'deny' and m.actual_status == 'approve']
        
        report_lines.append(f"  - False Positives (approved, should deny): {len(false_positives)}")
        report_lines.append(f"  - False Negatives (denied, should approve): {len(false_negatives)}")
        
        if false_positives:
            report_lines.append("\n  Top False Positive Causes:")
            fp_causes = {}
            for m in false_positives:
                cause = m.likely_cause
                fp_causes[cause] = fp_causes.get(cause, 0) + 1
            for cause, count in sorted(fp_causes.items(), key=lambda x: x[1], reverse=True)[:5]:
                report_lines.append(f"    • {cause}: {count} occurrences")
        
        if false_negatives:
            report_lines.append("\n  Top False Negative Causes:")
            fn_causes = {}
            for m in false_negatives:
                cause = m.likely_cause
                fn_causes[cause] = fn_causes.get(cause, 0) + 1
            for cause, count in sorted(fn_causes.items(), key=lambda x: x[1], reverse=True)[:5]:
                report_lines.append(f"    • {cause}: {count} occurrences")
    
    report_lines.append(f"\n### Amount Disagreements: {len(amount_mismatches)}")
    if amount_mismatches:
        over_estimates = [m for m in amount_mismatches if m.difference > 0]
        under_estimates = [m for m in amount_mismatches if m.difference < 0]
        
        avg_over = np.mean([m.difference for m in over_estimates]) if over_estimates else 0
        avg_under = np.mean([abs(m.difference) for m in under_estimates]) if under_estimates else 0
        
        report_lines.append(f"  - Over-estimates: {len(over_estimates)} (avg: ${avg_over:.2f})")
        report_lines.append(f"  - Under-estimates: {len(under_estimates)} (avg: ${avg_under:.2f})")
        
        large_errors = [m for m in amount_mismatches if abs(m.difference) > 100]
        report_lines.append(f"  - Large errors (>$100): {len(large_errors)}")
    
    report_lines.append("\n## DETAILED VARIANCE ANALYSIS")
    report_lines.append("-" * 80)
    
    if mismatches:
        report_lines.append("\n### High-Priority Mismatches (Status or >$100 difference)")
        high_priority = [m for m in mismatches if m.needs_review]
        for i, m in enumerate(high_priority[:20], 1):
            report_lines.append(f"\n{i}. Claim {m.claim_tracking_number} (ID: {m.claim_id})")
            report_lines.append(f"   Proposed: {m.proposed_status.upper()} ${m.proposed_benefit:.2f}")
            report_lines.append(f"   Actual:   {m.actual_status.upper()} ${m.actual_benefit:.2f}")
            report_lines.append(f"   Difference: ${m.difference:.2f}")
            report_lines.append(f"   Cause: {m.likely_cause}")
            report_lines.append(f"   Confidence: {m.confidence:.1f}%")
            if m.flags:
                report_lines.append(f"   Flags: {', '.join(m.flags[:3])}")
    
    report_lines.append("\n## RECOMMENDATIONS TO MINIMIZE VARIANCE")
    report_lines.append("-" * 80)
    
    recommendations = []
    
    if metrics.false_positives > metrics.false_negatives * 1.5:
        recommendations.append({
            'priority': 'HIGH',
            'issue': 'High False Positive Rate',
            'description': f'System is approving {metrics.false_positives} claims that should be denied',
            'suggestions': [
                'Review eligibility rules for items that should be ineligible',
                'Strengthen document classification to better identify ineligible charges',
                'Add validation checks for common false positive patterns',
                'Review cap enforcement logic',
                'Consider adding negative patterns to eligibility classifier'
            ]
        })
    
    if metrics.false_negatives > metrics.false_positives * 1.5:
        recommendations.append({
            'priority': 'HIGH',
            'issue': 'High False Negative Rate',
            'description': f'System is denying {metrics.false_negatives} claims that should be approved',
            'suggestions': [
                'Review eligibility rules - may be too restrictive',
                'Expand eligible item categories based on false negative patterns',
                'Improve document classification to catch more eligible items',
                'Review missing data handling - may be rejecting valid claims',
                'Consider adjusting confidence thresholds for approval'
            ]
        })
    
    if metrics.mean_absolute_error > 100:
        recommendations.append({
            'priority': 'HIGH',
            'issue': 'High Amount Variance',
            'description': f'Average amount error is ${metrics.mean_absolute_error:.2f}',
            'suggestions': [
                'Review benefit cap calculation logic',
                'Improve line item parsing accuracy',
                'Verify invoice total extraction',
                'Check for systematic rounding errors',
                'Review eligible vs ineligible item classification',
                'Validate cap amount against max_benefit field'
            ]
        })
    
    if metrics.mean_absolute_percentage_error > 0.10:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': 'High Percentage Error',
            'description': f'Average percentage error is {metrics.mean_absolute_percentage_error:.2%}',
            'suggestions': [
                'Review proportional benefit calculations',
                'Check for systematic over/under-estimation patterns',
                'Validate cap percentage calculations',
                'Review partial approval logic'
            ]
        })
    
    if metrics.bias_direction != 'neutral' and metrics.bias_magnitude > 0.05:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': f'System Bias: {metrics.bias_direction}',
            'description': f'System is {metrics.bias_magnitude:.1%} {metrics.bias_direction} than historical',
            'suggestions': [
                'Calibrate benefit calculations to match historical averages',
                'Review eligibility thresholds',
                'Adjust cap enforcement if systematically different',
                'Consider policy alignment - bias may be intentional'
            ]
        })
    
    if metrics.avg_confidence_score < 70:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': 'Low Confidence Scores',
            'description': f'Average confidence is {metrics.avg_confidence_score:.1f}%',
            'suggestions': [
                'Improve OCR quality for better text extraction',
                'Enhance document classification training data',
                'Review low-confidence patterns and improve rules',
                'Consider manual review threshold adjustments'
            ]
        })
    
    if metrics.manual_review_rate > 0.3:
        recommendations.append({
            'priority': 'LOW',
            'issue': 'High Manual Review Rate',
            'description': f'{metrics.manual_review_rate:.1%} of claims require manual review',
            'suggestions': [
                'Improve classification confidence through better training',
                'Add more specific rules for common patterns',
                'Review flags that trigger manual review',
                'Consider automating some manual review triggers'
            ]
        })
    
    if not recommendations:
        recommendations.append({
            'priority': 'INFO',
            'issue': 'System Performing Well',
            'description': 'No critical variance issues detected',
            'suggestions': [
                'Continue monitoring for trends',
                'Review edge cases for further optimization',
                'Consider expanding test coverage'
            ]
        })
    
    for i, rec in enumerate(recommendations, 1):
        report_lines.append(f"\n### {i}. [{rec['priority']}] {rec['issue']}")
        report_lines.append(f"\n{rec['description']}")
        report_lines.append("\nSuggested Actions:")
        for suggestion in rec['suggestions']:
            report_lines.append(f"  • {suggestion}")
    
    report_lines.append("\n## SPECIFIC PATTERN ANALYSIS")
    report_lines.append("-" * 80)
    
    if mismatches:
        pattern_analysis = {}
        for m in mismatches:
            pattern = m.likely_cause
            if pattern not in pattern_analysis:
                pattern_analysis[pattern] = {
                    'count': 0,
                    'total_variance': 0,
                    'claims': []
                }
            pattern_analysis[pattern]['count'] += 1
            pattern_analysis[pattern]['total_variance'] += abs(m.difference)
            pattern_analysis[pattern]['claims'].append(m.claim_tracking_number)
        
        report_lines.append("\n### Variance by Pattern:")
        for pattern, data in sorted(pattern_analysis.items(), key=lambda x: x[1]['count'], reverse=True):
            avg_variance = data['total_variance'] / data['count'] if data['count'] > 0 else 0
            report_lines.append(f"\n{pattern}:")
            report_lines.append(f"  Occurrences: {data['count']}")
            report_lines.append(f"  Average Variance: ${avg_variance:.2f}")
            report_lines.append(f"  Sample Claims: {', '.join(data['claims'][:5])}")
    
    report_lines.append("\n" + "=" * 80)
    report_lines.append("END OF VARIANCE REPORT")
    report_lines.append("=" * 80)
    
    with open(output_file, 'w') as f:
        f.write('\n'.join(report_lines))
    
    print(f"\n✓ Variance report saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate specific claim range and generate variance report")
    parser.add_argument('--db', required=True, help='PostgreSQL connection string')
    parser.add_argument('--start-claim', type=int, default=900, help='Start claim ID')
    parser.add_argument('--end-claim', type=int, default=920, help='End claim ID')
    parser.add_argument('--output-dir', default='./evaluation_results', help='Output directory')
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    evaluator = DecisionEvaluator(args.db)
    
    print("=" * 80)
    print(f"Evaluating Claims {args.start_claim} to {args.end_claim}")
    print("=" * 80)
    
    tracking_numbers = [str(i) for i in range(args.start_claim, args.end_claim + 1)]
    tracking_list = "', '".join(tracking_numbers)
    
    query = f"""
    SELECT 
        d.claim_id,
        c.claim_tracking_number,
        d.proposed_status,
        d.proposed_benefit_amount,
        d.eligible_total,
        d.invoice_total,
        d.flags,
        d.missing_data,
        d.confidence_score,
        d.engine_version,
        d.decided_at,
        d.processing_time_ms,
        v.actual_status,
        v.actual_paid_amount,
        v.actual_decision_date,
        v.adjudication_notes
    FROM claims.decisions d
    INNER JOIN claims.claims c ON d.claim_id = c.id
    INNER JOIN claims.decision_validation v ON d.claim_id = v.claim_id
    WHERE d.is_active = true
    AND c.claim_tracking_number IN ('{tracking_list}')
    ORDER BY CAST(c.claim_tracking_number AS INTEGER)
    """
    
    engine = create_engine(args.db)
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    
    if len(df) == 0:
        print(f"\n⚠ No decisions found for tracking numbers {args.start_claim} to {args.end_claim}")
        print("Checking if claims exist...")
        
        with engine.connect() as conn:
            check_query = f"""
            SELECT COUNT(*) FROM claims.claims 
            WHERE claim_tracking_number IN ('{tracking_list}')
            """
            result = conn.execute(text(check_query))
            claim_count = result.scalar()
            print(f"Found {claim_count} claims with tracking numbers in range")
            
            check_validations = f"""
            SELECT COUNT(*) FROM claims.claims c
            INNER JOIN claims.decision_validation v ON c.id = v.claim_id
            WHERE c.claim_tracking_number IN ('{tracking_list}')
            """
            result = conn.execute(text(check_validations))
            validation_count = result.scalar()
            print(f"Found {validation_count} claims with validation data")
            
            check_decisions = f"""
            SELECT COUNT(*) FROM claims.claims c
            INNER JOIN claims.decisions d ON c.id = d.claim_id
            WHERE c.claim_tracking_number IN ('{tracking_list}')
            AND d.is_active = true
            """
            result = conn.execute(text(check_decisions))
            decision_count = result.scalar()
            print(f"Found {decision_count} active decisions")
        
        if claim_count > 0 and decision_count == 0:
            print("\n⚠ Claims exist but no decisions found.")
            print("You may need to create decisions for these claims first.")
        elif claim_count == 0:
            print(f"\n⚠ No claims found with tracking numbers {args.start_claim} to {args.end_claim}")
            print("These tracking numbers may not exist in the database.")
        return
    
    print(f"\nFound {len(df)} decisions to evaluate")
    
    metrics = evaluator.calculate_metrics(df)
    mismatches = evaluator.identify_mismatches(df)
    
    results_file = output_dir / f"results_claims_{args.start_claim}_to_{args.end_claim}.json"
    variance_file = output_dir / f"variance_report_claims_{args.start_claim}_to_{args.end_claim}.txt"
    
    with open(results_file, 'w') as f:
        json.dump({
            'evaluation_range': {
                'start_claim': args.start_claim,
                'end_claim': args.end_claim
            },
            'metrics': metrics.to_dict(),
            'mismatches': [m.__dict__ for m in mismatches],
            'summary': {
                'total_claims': metrics.total_claims,
                'accuracy': metrics.accuracy,
                'mae': metrics.mean_absolute_error,
                'mape': metrics.mean_absolute_percentage_error,
                'status_mismatches': metrics.status_mismatches,
                'amount_over_50': metrics.amount_over_by_50_plus,
                'amount_under_50': metrics.amount_under_by_50_plus
            }
        }, f, indent=2)
    
    print(f"\n✓ Results saved to: {results_file}")
    
    generate_variance_report(metrics, mismatches, str(variance_file))
    
    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"Accuracy: {metrics.accuracy:.2%}")
    print(f"Mean Absolute Error: ${metrics.mean_absolute_error:.2f}")
    print(f"Status Mismatches: {metrics.status_mismatches}")
    print(f"Amount Errors >$50: {metrics.amount_over_by_50_plus + metrics.amount_under_by_50_plus}")
    print("=" * 80)


if __name__ == "__main__":
    main()

