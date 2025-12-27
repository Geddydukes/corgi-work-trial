"""A/B testing framework for eligibility classification rules."""

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from decision_service.engine.eligibility_classifier import EligibilityClassifier, ClassifiedLineItem

logger = logging.getLogger(__name__)


class RulesABTest:
    """Test different rulesets to optimize accuracy."""
    
    def __init__(self, control_rules: str, treatment_rules: str):
        """
        Initialize A/B test with control and treatment rulesets.
        
        Args:
            control_rules: Path to control rules YAML file
            treatment_rules: Path to treatment rules YAML file
        """
        self.control = EligibilityClassifier(control_rules)
        self.treatment = EligibilityClassifier(treatment_rules)
        logger.info(f"A/B test initialized: control={control_rules}, treatment={treatment_rules}")
    
    def compare_on_dataset(self, test_claims: List[dict]) -> dict:
        """
        Compare two rulesets on historical claims.
        
        Args:
            test_claims: List of dicts with 'description', 'amount', and optionally 'expected_status'
            
        Returns:
            Dictionary with comparison metrics
        """
        results = {
            'agreement_count': 0,
            'disagreement_count': 0,
            'status_flips': [],
            'confidence_improvements': [],
            'confidence_degradations': [],
            'control_stats': {
                'total': 0,
                'eligible': 0,
                'ineligible': 0,
                'ambiguous': 0,
                'avg_confidence': 0.0,
                'manual_review_count': 0
            },
            'treatment_stats': {
                'total': 0,
                'eligible': 0,
                'ineligible': 0,
                'ambiguous': 0,
                'avg_confidence': 0.0,
                'manual_review_count': 0
            },
            'accuracy_comparison': {
                'control_correct': 0,
                'treatment_correct': 0,
                'both_correct': 0,
                'both_wrong': 0,
                'control_only_correct': 0,
                'treatment_only_correct': 0
            }
        }
        
        total_control_confidence = 0.0
        total_treatment_confidence = 0.0
        
        for claim in test_claims:
            control_result = self.control.classify(claim)
            treatment_result = self.treatment.classify(claim)
            
            control_status = control_result.classification.status.value
            treatment_status = treatment_result.classification.status.value
            
            results['control_stats']['total'] += 1
            results['treatment_stats']['total'] += 1
            
            if control_status == 'eligible':
                results['control_stats']['eligible'] += 1
            elif control_status == 'ineligible':
                results['control_stats']['ineligible'] += 1
            else:
                results['control_stats']['ambiguous'] += 1
            
            if treatment_status == 'eligible':
                results['treatment_stats']['eligible'] += 1
            elif treatment_status == 'ineligible':
                results['treatment_stats']['ineligible'] += 1
            else:
                results['treatment_stats']['ambiguous'] += 1
            
            if control_result.classification.requires_manual_review:
                results['control_stats']['manual_review_count'] += 1
            if treatment_result.classification.requires_manual_review:
                results['treatment_stats']['manual_review_count'] += 1
            
            total_control_confidence += control_result.classification.confidence
            total_treatment_confidence += treatment_result.classification.confidence
            
            if control_status == treatment_status:
                results['agreement_count'] += 1
            else:
                results['disagreement_count'] += 1
                results['status_flips'].append({
                    'claim': claim,
                    'control': {
                        'status': control_status,
                        'category': control_result.classification.category,
                        'confidence': control_result.classification.confidence,
                        'reasoning': control_result.classification.reasoning
                    },
                    'treatment': {
                        'status': treatment_status,
                        'category': treatment_result.classification.category,
                        'confidence': treatment_result.classification.confidence,
                        'reasoning': treatment_result.classification.reasoning
                    }
                })
            
            conf_delta = treatment_result.classification.confidence - control_result.classification.confidence
            if conf_delta > 5:
                results['confidence_improvements'].append({
                    'description': claim.get('description', ''),
                    'delta': conf_delta,
                    'control_conf': control_result.classification.confidence,
                    'treatment_conf': treatment_result.classification.confidence
                })
            elif conf_delta < -5:
                results['confidence_degradations'].append({
                    'description': claim.get('description', ''),
                    'delta': conf_delta,
                    'control_conf': control_result.classification.confidence,
                    'treatment_conf': treatment_result.classification.confidence
                })
            
            if 'expected_status' in claim:
                expected = claim['expected_status'].lower()
                control_correct = control_status == expected
                treatment_correct = treatment_status == expected
                
                if control_correct and treatment_correct:
                    results['accuracy_comparison']['both_correct'] += 1
                elif not control_correct and not treatment_correct:
                    results['accuracy_comparison']['both_wrong'] += 1
                elif control_correct:
                    results['accuracy_comparison']['control_only_correct'] += 1
                elif treatment_correct:
                    results['accuracy_comparison']['treatment_only_correct'] += 1
                
                if control_correct:
                    results['accuracy_comparison']['control_correct'] += 1
                if treatment_correct:
                    results['accuracy_comparison']['treatment_correct'] += 1
        
        if results['control_stats']['total'] > 0:
            results['control_stats']['avg_confidence'] = total_control_confidence / results['control_stats']['total']
        if results['treatment_stats']['total'] > 0:
            results['treatment_stats']['avg_confidence'] = total_treatment_confidence / results['treatment_stats']['total']
        
        total = results['control_stats']['total']
        if total > 0:
            results['agreement_rate'] = results['agreement_count'] / total
            results['disagreement_rate'] = results['disagreement_count'] / total
        
        return results
    
    def generate_report(self, comparison_results: dict) -> str:
        """
        Generate human-readable A/B test report.
        
        Args:
            comparison_results: Results from compare_on_dataset()
            
        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append("ELIGIBILITY CLASSIFICATION A/B TEST REPORT")
        report.append("=" * 80)
        report.append("")
        
        report.append("SUMMARY")
        report.append("-" * 80)
        total = comparison_results['control_stats']['total']
        report.append(f"Total test cases: {total}")
        report.append(f"Agreement rate: {comparison_results.get('agreement_rate', 0):.2%}")
        report.append(f"Disagreement rate: {comparison_results.get('disagreement_rate', 0):.2%}")
        report.append("")
        
        report.append("CONTROL RULESET STATISTICS")
        report.append("-" * 80)
        c_stats = comparison_results['control_stats']
        report.append(f"  Eligible: {c_stats['eligible']} ({c_stats['eligible']/total*100:.1f}%)")
        report.append(f"  Ineligible: {c_stats['ineligible']} ({c_stats['ineligible']/total*100:.1f}%)")
        report.append(f"  Ambiguous: {c_stats['ambiguous']} ({c_stats['ambiguous']/total*100:.1f}%)")
        report.append(f"  Average confidence: {c_stats['avg_confidence']:.1f}%")
        report.append(f"  Requiring manual review: {c_stats['manual_review_count']} ({c_stats['manual_review_count']/total*100:.1f}%)")
        report.append("")
        
        report.append("TREATMENT RULESET STATISTICS")
        report.append("-" * 80)
        t_stats = comparison_results['treatment_stats']
        report.append(f"  Eligible: {t_stats['eligible']} ({t_stats['eligible']/total*100:.1f}%)")
        report.append(f"  Ineligible: {t_stats['ineligible']} ({t_stats['ineligible']/total*100:.1f}%)")
        report.append(f"  Ambiguous: {t_stats['ambiguous']} ({t_stats['ambiguous']/total*100:.1f}%)")
        report.append(f"  Average confidence: {t_stats['avg_confidence']:.1f}%")
        report.append(f"  Requiring manual review: {t_stats['manual_review_count']} ({t_stats['manual_review_count']/total*100:.1f}%)")
        report.append("")
        
        if comparison_results['status_flips']:
            report.append("STATUS CHANGES")
            report.append("-" * 80)
            for i, flip in enumerate(comparison_results['status_flips'][:10], 1):
                report.append(f"{i}. {flip['claim'].get('description', 'N/A')}")
                report.append(f"   Control: {flip['control']['status']} ({flip['control']['category']}, {flip['control']['confidence']:.1f}%)")
                report.append(f"   Treatment: {flip['treatment']['status']} ({flip['treatment']['category']}, {flip['treatment']['confidence']:.1f}%)")
                report.append("")
            if len(comparison_results['status_flips']) > 10:
                report.append(f"... and {len(comparison_results['status_flips']) - 10} more")
            report.append("")
        
        if comparison_results['confidence_improvements']:
            report.append("CONFIDENCE IMPROVEMENTS (>5%)")
            report.append("-" * 80)
            for i, imp in enumerate(comparison_results['confidence_improvements'][:10], 1):
                report.append(f"{i}. {imp['description']}")
                report.append(f"   Improvement: +{imp['delta']:.1f}% ({imp['control_conf']:.1f}% → {imp['treatment_conf']:.1f}%)")
                report.append("")
            if len(comparison_results['confidence_improvements']) > 10:
                report.append(f"... and {len(comparison_results['confidence_improvements']) - 10} more")
            report.append("")
        
        if comparison_results['confidence_degradations']:
            report.append("CONFIDENCE DEGRADATIONS (<-5%)")
            report.append("-" * 80)
            for i, deg in enumerate(comparison_results['confidence_degradations'][:10], 1):
                report.append(f"{i}. {deg['description']}")
                report.append(f"   Degradation: {deg['delta']:.1f}% ({deg['control_conf']:.1f}% → {deg['treatment_conf']:.1f}%)")
                report.append("")
            if len(comparison_results['confidence_degradations']) > 10:
                report.append(f"... and {len(comparison_results['confidence_degradations']) - 10} more")
            report.append("")
        
        if comparison_results['accuracy_comparison']['control_correct'] > 0 or comparison_results['accuracy_comparison']['treatment_correct'] > 0:
            report.append("ACCURACY COMPARISON (if expected_status provided)")
            report.append("-" * 80)
            acc = comparison_results['accuracy_comparison']
            report.append(f"  Control accuracy: {acc['control_correct']}/{total} ({acc['control_correct']/total*100:.1f}%)")
            report.append(f"  Treatment accuracy: {acc['treatment_correct']}/{total} ({acc['treatment_correct']/total*100:.1f}%)")
            report.append(f"  Both correct: {acc['both_correct']}")
            report.append(f"  Both wrong: {acc['both_wrong']}")
            report.append(f"  Control only correct: {acc['control_only_correct']}")
            report.append(f"  Treatment only correct: {acc['treatment_only_correct']}")
            report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)

