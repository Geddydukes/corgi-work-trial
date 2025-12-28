import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from decimal import Decimal
from sqlalchemy import create_engine, text
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class EvaluationMetrics:
    """Container for all evaluation metrics."""
    total_claims: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_absolute_percentage_error: float
    median_absolute_error: float
    
    avg_proposed_benefit: float
    avg_actual_benefit: float
    bias_direction: str
    bias_magnitude: float
    
    complete_data_rate: float
    manual_review_rate: float
    avg_confidence_score: float
    
    avg_processing_time_ms: float
    
    status_mismatches: int
    amount_over_by_50_plus: int
    amount_under_by_50_plus: int
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_markdown(self) -> str:
        """Generate markdown summary report."""
        return f"""
# Decision Engine Evaluation Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Overall Performance

| Metric | Value |
|--------|-------|
| Total Claims Evaluated | {self.total_claims} |
| **Accuracy** | **{self.accuracy:.2%}** |
| Precision | {self.precision:.2%} |
| Recall | {self.recall:.2%} |
| F1 Score | {self.f1_score:.3f} |

## Confusion Matrix

|  | Actual Approve | Actual Deny |
|---|---|---|
| **Proposed Approve** | {self.true_positives} ✓ | {self.false_positives} ✗ |
| **Proposed Deny** | {self.false_negatives} ✗ | {self.true_negatives} ✓ |

## Amount Accuracy (Approved Claims)

| Metric | Value |
|--------|-------|
| Mean Absolute Error | ${self.mean_absolute_error:.2f} |
| RMSE | ${self.root_mean_squared_error:.2f} |
| MAPE | {self.mean_absolute_percentage_error:.2%} |
| Median Absolute Error | ${self.median_absolute_error:.2f} |

## Bias Analysis

- **Average Proposed Benefit:** ${self.avg_proposed_benefit:.2f}
- **Average Actual Benefit:** ${self.avg_actual_benefit:.2f}
- **Bias Direction:** {self.bias_direction}
- **Bias Magnitude:** {self.bias_magnitude:.2%}

{self._interpret_bias()}

## Quality Metrics

- **Complete Data Rate:** {self.complete_data_rate:.1%}
- **Manual Review Rate:** {self.manual_review_rate:.1%}
- **Average Confidence:** {self.avg_confidence_score:.1f}%

## Mismatches

- **Status Disagreements:** {self.status_mismatches} claims
- **Amount Over by $50+:** {self.amount_over_by_50_plus} claims
- **Amount Under by $50+:** {self.amount_under_by_50_plus} claims

---

## Recommendations

{self._generate_recommendations()}
"""
    
    def _interpret_bias(self) -> str:
        if self.bias_direction == "neutral":
            return "✓ System is well-calibrated with minimal bias."
        elif self.bias_direction == "more_generous":
            return f"⚠️ System is {self.bias_magnitude:.1%} more generous than historical decisions. This aligns with approval-leaning policy."
        else:
            return f"⚠️ System is {self.bias_magnitude:.1%} less generous than historical decisions. Consider adjusting eligibility rules."
    
    def _generate_recommendations(self) -> str:
        recs = []
        
        if self.false_negatives > self.false_positives * 2:
            recs.append("- **High false negative rate:** Consider loosening eligibility criteria or improving document classification.")
        
        if self.false_positives > self.false_negatives * 2:
            recs.append("- **High false positive rate:** Review eligibility rules for items that should be ineligible.")
        
        if self.mean_absolute_error > 100:
            recs.append(f"- **High amount error (MAE=${self.mean_absolute_error:.0f}):** Investigate benefit cap logic and line item parsing.")
        
        if self.manual_review_rate > 0.3:
            recs.append(f"- **High manual review rate ({self.manual_review_rate:.0%}):** Improve classification confidence through better training data or rules.")
        
        if self.avg_confidence_score < 70:
            recs.append(f"- **Low average confidence ({self.avg_confidence_score:.0f}%):** Review OCR quality and classification patterns.")
        
        if not recs:
            recs.append("- ✓ No critical issues detected. System is performing well.")
        
        return "\n".join(recs)


@dataclass
class MismatchRecord:
    """Record of a single mismatch between proposed and actual."""
    claim_id: int
    claim_tracking_number: str
    proposed_status: str
    actual_status: str
    proposed_benefit: float
    actual_benefit: float
    difference: float
    mismatch_type: str
    likely_cause: str
    flags: List[str]
    confidence: float
    needs_review: bool


class DecisionEvaluator:
    """
    Evaluate decision engine performance against historical actuals.
    
    This is the key deliverable for proving system accuracy.
    """
    
    def __init__(self, db_connection_string: str):
        """
        Args:
            db_connection_string: PostgreSQL connection string
        """
        self.engine = create_engine(db_connection_string)
        logger.info("DecisionEvaluator initialized")
    
    def load_data(
        self, 
        engine_version: str = None,
        date_range: Tuple[str, str] = None
    ) -> pd.DataFrame:
        """
        Load decisions and validations from database.
        
        Args:
            engine_version: Filter by specific engine version (e.g., "rules_v1.0.0")
            date_range: Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
            
        Returns:
            DataFrame with joined decision and validation data
        """
        query = """
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
        FROM decisions d
        INNER JOIN claims c ON d.claim_id = c.id
        INNER JOIN decision_validation v ON d.claim_id = v.claim_id
        WHERE d.is_active = true
        """
        
        params = {}
        
        if engine_version:
            query += " AND d.engine_version = :version"
            params['version'] = engine_version
        
        if date_range:
            query += " AND d.decided_at BETWEEN :start_date AND :end_date"
            params['start_date'] = date_range[0]
            params['end_date'] = date_range[1]
        
        query += " ORDER BY d.decided_at DESC"
        
        logger.info(f"Loading evaluation data (version={engine_version}, date_range={date_range})")
        df = pd.read_sql(text(query), self.engine, params=params)
        logger.info(f"Loaded {len(df)} claim decisions for evaluation")
        
        return df
    
    def calculate_metrics(self, df: pd.DataFrame) -> EvaluationMetrics:
        """Calculate comprehensive evaluation metrics."""
        
        df['proposed_approve'] = df['proposed_status'] == 'approve'
        df['actual_approve'] = df['actual_status'] == 'approve'
        
        tn = len(df[(~df['proposed_approve']) & (~df['actual_approve'])])
        tp = len(df[df['proposed_approve'] & df['actual_approve']])
        fp = len(df[df['proposed_approve'] & (~df['actual_approve'])])
        fn = len(df[(~df['proposed_approve']) & df['actual_approve']])
        
        accuracy = (tp + tn) / len(df) if len(df) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        approved_both = df[df['proposed_approve'] & df['actual_approve']].copy()
        
        if len(approved_both) > 0:
            approved_both['abs_error'] = abs(approved_both['proposed_benefit_amount'] - approved_both['actual_paid_amount'])
            approved_both['squared_error'] = (approved_both['proposed_benefit_amount'] - approved_both['actual_paid_amount']) ** 2
            approved_both['pct_error'] = abs(
                (approved_both['proposed_benefit_amount'] - approved_both['actual_paid_amount']) / approved_both['actual_paid_amount']
            )
            
            mae = approved_both['abs_error'].mean()
            rmse = np.sqrt(approved_both['squared_error'].mean())
            mape = approved_both['pct_error'].mean()
            median_ae = approved_both['abs_error'].median()
        else:
            mae = rmse = mape = median_ae = 0.0
        
        avg_proposed = df[df['proposed_approve']]['proposed_benefit_amount'].mean() if any(df['proposed_approve']) else 0
        avg_actual = df[df['actual_approve']]['actual_paid_amount'].mean() if any(df['actual_approve']) else 0
        
        if avg_actual > 0:
            bias_magnitude = abs(avg_proposed - avg_actual) / avg_actual
            if abs(avg_proposed - avg_actual) < avg_actual * 0.05:
                bias_direction = "neutral"
            elif avg_proposed > avg_actual:
                bias_direction = "more_generous"
            else:
                bias_direction = "less_generous"
        else:
            bias_magnitude = 0
            bias_direction = "neutral"
        
        def has_missing_data_fields(missing_data_json):
            try:
                if isinstance(missing_data_json, str):
                    data = json.loads(missing_data_json)
                    return len(data.get('fields', [])) > 0
                elif isinstance(missing_data_json, dict):
                    return len(missing_data_json.get('fields', [])) > 0
                return False
            except (json.JSONDecodeError, TypeError, AttributeError):
                return False
        
        df['has_missing_data'] = df['missing_data'].apply(has_missing_data_fields)
        complete_data_rate = 1 - df['has_missing_data'].mean()
        
        def needs_manual_review(flags_json):
            try:
                if isinstance(flags_json, str):
                    flags = json.loads(flags_json)
                elif isinstance(flags_json, dict):
                    flags = flags_json
                else:
                    return False
                all_flags = flags.get('warnings', []) + flags.get('info', []) + flags.get('critical', [])
                return any('manual_review' in str(flag).lower() or 'manual' in str(flag).lower() 
                          for flag in all_flags)
            except (json.JSONDecodeError, TypeError, AttributeError):
                return False
        
        df['needs_manual_review'] = df['flags'].apply(needs_manual_review)
        manual_review_rate = df['needs_manual_review'].mean()
        
        avg_confidence = df['confidence_score'].mean() if 'confidence_score' in df.columns else 0.0
        avg_processing_time = df['processing_time_ms'].mean() if 'processing_time_ms' in df.columns else 0.0
        
        status_mismatches = len(df[df['proposed_status'] != df['actual_status']])
        amount_over_50 = len(approved_both[approved_both['proposed_benefit_amount'] - approved_both['actual_paid_amount'] > 50]) if len(approved_both) > 0 else 0
        amount_under_50 = len(approved_both[approved_both['actual_paid_amount'] - approved_both['proposed_benefit_amount'] > 50]) if len(approved_both) > 0 else 0
        
        return EvaluationMetrics(
            total_claims=len(df),
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
            mean_absolute_error=mae,
            root_mean_squared_error=rmse,
            mean_absolute_percentage_error=mape,
            median_absolute_error=median_ae,
            avg_proposed_benefit=avg_proposed,
            avg_actual_benefit=avg_actual,
            bias_direction=bias_direction,
            bias_magnitude=bias_magnitude,
            complete_data_rate=complete_data_rate,
            manual_review_rate=manual_review_rate,
            avg_confidence_score=avg_confidence,
            avg_processing_time_ms=avg_processing_time,
            status_mismatches=status_mismatches,
            amount_over_by_50_plus=amount_over_50,
            amount_under_by_50_plus=amount_under_50
        )
    
    def identify_mismatches(self, df: pd.DataFrame) -> List[MismatchRecord]:
        """Identify and analyze mismatches."""
        
        mismatches = []
        
        for _, row in df.iterrows():
            status_match = row['proposed_status'] == row['actual_status']
            
            if row['proposed_status'] == 'approve' and row['actual_status'] == 'approve':
                amount_diff = row['proposed_benefit_amount'] - row['actual_paid_amount']
                amount_match = abs(amount_diff) < 50
            else:
                amount_diff = 0
                amount_match = True
            
            if not status_match or not amount_match:
                if not status_match and not amount_match:
                    mismatch_type = "both"
                elif not status_match:
                    mismatch_type = "status_only"
                else:
                    mismatch_type = "amount_only"
                
                likely_cause = self._infer_cause(row, status_match, amount_diff)
                
                flags_list = []
                try:
                    if isinstance(row['flags'], str):
                        flags = json.loads(row['flags'])
                    elif isinstance(row['flags'], dict):
                        flags = row['flags']
                    else:
                        flags = {}
                    for severity in ['critical', 'warnings', 'info']:
                        flag_list = flags.get(severity, [])
                        if isinstance(flag_list, list):
                            flags_list.extend([str(f) for f in flag_list])
                except (json.JSONDecodeError, TypeError, AttributeError):
                    flags_list = []
                
                mismatches.append(MismatchRecord(
                    claim_id=row['claim_id'],
                    claim_tracking_number=row['claim_tracking_number'],
                    proposed_status=row['proposed_status'],
                    actual_status=row['actual_status'],
                    proposed_benefit=float(row['proposed_benefit_amount']),
                    actual_benefit=float(row['actual_paid_amount']) if pd.notna(row['actual_paid_amount']) else 0.0,
                    difference=float(amount_diff),
                    mismatch_type=mismatch_type,
                    likely_cause=likely_cause,
                    flags=flags_list,
                    confidence=float(row['confidence_score']) if pd.notna(row.get('confidence_score')) else 0.0,
                    needs_review=abs(amount_diff) > 100 or not status_match
                ))
        
        logger.info(f"Identified {len(mismatches)} mismatches")
        return mismatches
    
    def _infer_cause(self, row, status_match: bool, amount_diff: float) -> str:
        """Infer likely cause of mismatch."""
        
        if not status_match:
            if row['proposed_status'] == 'deny' and row['actual_status'] == 'approve':
                return "False negative: System too restrictive or missing eligible items"
            else:
                return "False positive: System approved ineligible charges"
        
        if amount_diff > 100:
            return "Amount too high: Possible eligibility over-classification or cap miscalculation"
        elif amount_diff < -100:
            return "Amount too low: Missing eligible items or incorrect cap"
        elif abs(amount_diff) > 0:
            return "Minor amount difference: Likely due to rounding or line item interpretation"
        
        return "Unknown"
    
    def generate_visualizations(self, df: pd.DataFrame, metrics: EvaluationMetrics, output_dir: str = "./evaluation_output"):
        """Generate visualization charts."""
        
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        sns.set_style("whitegrid")
        
        cm = np.array([[metrics.true_positives, metrics.false_positives],
                       [metrics.false_negatives, metrics.true_negatives]])
        
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                    xticklabels=['Actual Approve', 'Actual Deny'],
                    yticklabels=['Proposed Approve', 'Proposed Deny'])
        plt.title('Confusion Matrix')
        plt.ylabel('Proposed Decision')
        plt.xlabel('Actual Decision')
        plt.tight_layout()
        plt.savefig(f'{output_dir}/confusion_matrix.png', dpi=300)
        plt.close()
        
        approved_both = df[(df['proposed_status'] == 'approve') & (df['actual_status'] == 'approve')]
        
        if len(approved_both) > 0:
            plt.figure(figsize=(10, 6))
            plt.scatter(approved_both['actual_paid_amount'], approved_both['proposed_benefit_amount'], alpha=0.6)
            
            max_val = max(approved_both['actual_paid_amount'].max(), approved_both['proposed_benefit_amount'].max())
            plt.plot([0, max_val], [0, max_val], 'r--', label='Perfect Agreement')
            
            plt.xlabel('Actual Paid Amount ($)')
            plt.ylabel('Proposed Benefit Amount ($)')
            plt.title('Proposed vs. Actual Benefit Amounts')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(f'{output_dir}/amount_scatter.png', dpi=300)
            plt.close()
            
            approved_both['error'] = approved_both['proposed_benefit_amount'] - approved_both['actual_paid_amount']
            
            plt.figure(figsize=(10, 6))
            plt.hist(approved_both['error'], bins=30, edgecolor='black', alpha=0.7)
            plt.axvline(x=0, color='r', linestyle='--', label='Zero Error')
            plt.xlabel('Error (Proposed - Actual) ($)')
            plt.ylabel('Frequency')
            plt.title('Distribution of Benefit Amount Errors')
            plt.legend()
            plt.tight_layout()
            plt.savefig(f'{output_dir}/error_distribution.png', dpi=300)
            plt.close()
        
        if 'confidence_score' in df.columns and df['confidence_score'].notna().any():
            plt.figure(figsize=(10, 6))
            plt.hist(df['confidence_score'].dropna(), bins=20, edgecolor='black', alpha=0.7, color='skyblue')
            mean_conf = df['confidence_score'].mean()
            plt.axvline(x=mean_conf, color='r', linestyle='--', label=f'Mean: {mean_conf:.1f}%')
            plt.xlabel('Overall Confidence Score (%)')
            plt.ylabel('Frequency')
            plt.title('Distribution of Decision Confidence Scores')
            plt.legend()
            plt.tight_layout()
            plt.savefig(f'{output_dir}/confidence_distribution.png', dpi=300)
            plt.close()
        
        logger.info(f"Visualizations saved to {output_dir}/")
    
    def export_results(
        self, 
        metrics: EvaluationMetrics, 
        mismatches: List[MismatchRecord],
        output_dir: str = "./evaluation_output"
    ):
        """Export results to files."""
        
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        with open(f'{output_dir}/metrics.json', 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)
        
        with open(f'{output_dir}/EVALUATION_REPORT.md', 'w') as f:
            f.write(metrics.to_markdown())
        
        mismatches_df = pd.DataFrame([asdict(m) for m in mismatches])
        mismatches_df.to_csv(f'{output_dir}/mismatches.csv', index=False)
        
        high_priority = mismatches_df[mismatches_df['needs_review'] == True]
        high_priority.to_csv(f'{output_dir}/high_priority_mismatches.csv', index=False)
        
        logger.info(f"Results exported to {output_dir}/")
        logger.info(f"  - metrics.json")
        logger.info(f"  - EVALUATION_REPORT.md")
        logger.info(f"  - mismatches.csv ({len(mismatches)} total)")
        logger.info(f"  - high_priority_mismatches.csv ({len(high_priority)} high priority)")
    
    def run_full_evaluation(
        self,
        engine_version: str = None,
        date_range: Tuple[str, str] = None,
        output_dir: str = "./evaluation_output"
    ) -> EvaluationMetrics:
        """
        Run complete evaluation pipeline.
        
        This is the main entry point for the trial project demo.
        """
        logger.info("=" * 60)
        logger.info("Starting full evaluation pipeline")
        logger.info("=" * 60)
        
        df = self.load_data(engine_version, date_range)
        
        logger.info("Calculating metrics...")
        metrics = self.calculate_metrics(df)
        
        logger.info("Identifying mismatches...")
        mismatches = self.identify_mismatches(df)
        
        logger.info("Generating visualizations...")
        self.generate_visualizations(df, metrics, output_dir)
        
        logger.info("Exporting results...")
        self.export_results(metrics, mismatches, output_dir)
        
        logger.info("=" * 60)
        logger.info("Evaluation complete!")
        logger.info(f"Results saved to: {output_dir}/")
        logger.info(f"Overall Accuracy: {metrics.accuracy:.2%}")
        logger.info(f"Mean Absolute Error: ${metrics.mean_absolute_error:.2f}")
        logger.info("=" * 60)
        
        return metrics


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate decision engine performance")
    parser.add_argument('--db', required=True, help='Database connection string')
    parser.add_argument('--version', help='Filter by engine version')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default='./evaluation_output', help='Output directory')
    
    args = parser.parse_args()
    
    date_range = None
    if args.start_date and args.end_date:
        date_range = (args.start_date, args.end_date)
    
    evaluator = DecisionEvaluator(args.db)
    metrics = evaluator.run_full_evaluation(
        engine_version=args.version,
        date_range=date_range,
        output_dir=args.output
    )
    
    print("\n" + metrics.to_markdown())

