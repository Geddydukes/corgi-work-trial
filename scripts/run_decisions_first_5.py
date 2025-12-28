#!/usr/bin/env python3.11
"""
Run decision engine on first 5 claims (900-904)
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
import logging
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from decision_service.engine.decision_engine import DecisionEngine
from decision_service.repositories.claim_repository import ClaimRepository
from decision_service.repositories.document_repository import DocumentRepository
from shared.models import DocumentType

async def run_decisions(start_tracking: int = 900, end_tracking: int = 904):
    """Run decision engine on specified claims."""
    
    db_url = "postgresql://postgres:postgres@localhost:5432/corgi_dev"
    engine = create_engine(db_url)
    decision_engine = DecisionEngine()
    repository = ClaimRepository()
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    logger.info("=" * 80)
    logger.info(f"Running Decision Engine on Claims {start_tracking} to {end_tracking}")
    logger.info("=" * 80)
    
    results = []
    
    for tracking_num in tracking_numbers:
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing Claim {tracking_num}")
        logger.info(f"{'='*80}")
        
        try:
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                result = conn.execute(
                    text("SELECT id FROM claims WHERE claim_tracking_number = :tracking"),
                    {"tracking": tracking_num}
                ).fetchone()
                
                if not result:
                    logger.warning(f"  ✗ Claim {tracking_num} not found, skipping")
                    continue
                
                claim_id = result[0]
            
            # Get documents for structured logging
            doc_repository = DocumentRepository()
            documents = await doc_repository.get_documents(claim_id)
            
            has_addendum = any(
                doc.get("document_type") == DocumentType.ADDENDUM.value 
                for doc in documents
            )
            has_invoice = any(
                doc.get("document_type") == DocumentType.INVOICE.value 
                for doc in documents
            )
            
            # Get claim for max_benefit logging
            claim_repo = ClaimRepository()
            claim = await claim_repo.get_claim(claim_id)
            max_benefit = claim.get('max_benefit') if claim else None
            claim_amount = claim.get('claim_amount', 0) if claim else 0
            
            # Run decision engine
            logger.info(f"  → Running decision engine...")
            decision = await decision_engine.evaluate_claim(claim_id)
            
            # Determine rule branch
            rule_branch = _determine_rule_branch(decision, has_addendum, has_invoice, max_benefit)
            
            # Structured logging
            logger.info(f"  📊 Decision Metrics:")
            logger.info(f"     has_addendum: {has_addendum}")
            logger.info(f"     has_invoice: {has_invoice}")
            logger.info(f"     max_benefit: ${max_benefit:.2f}" if max_benefit else "     max_benefit: None")
            logger.info(f"     claim_amount: ${claim_amount:.2f}")
            logger.info(f"     eligible_total: ${float(decision.eligible_total):.2f}")
            logger.info(f"     invoice_total: ${float(decision.invoice_total):.2f}")
            logger.info(f"     cap_amount: ${float(decision.cap_amount):.2f}" if decision.cap_amount else "     cap_amount: None")
            logger.info(f"     proposed_benefit: ${float(decision.proposed_benefit_amount):.2f}")
            logger.info(f"     rule_branch: {rule_branch}")
            
            # Save decision
            decision_record = await repository.create_decision(decision, user_id="system")
            
            logger.info(f"  ✅ Decision: {decision.proposed_status.upper()}")
            logger.info(f"  ✅ Amount: ${decision.proposed_benefit_amount}")
            logger.info(f"  ✅ Confidence: {decision.confidence_score:.1f}%")
            
            # Print all line items with detailed reasoning
            print(f"\n{'='*100}")
            print(f"LINE ITEMS WITH DETAILED REASONING - Claim {tracking_num}")
            print(f"{'='*100}")
            
            all_items = decision.approved_line_items + decision.ineligible_line_items
            total_included = 0
            total_excluded = 0
            
            for i, item in enumerate(all_items, 1):
                # Handle nested structure: item may have 'line_item' and 'analysis' keys
                if isinstance(item, dict) and 'line_item' in item:
                    line_item = item['line_item']
                    analysis = item.get('analysis', {})
                else:
                    line_item = item
                    analysis = item
                
                # Handle Decimal conversion
                from decimal import Decimal
                amount_raw = line_item.get('amount', 0)
                amount = float(amount_raw) if isinstance(amount_raw, (Decimal, int, float)) else float(str(amount_raw))
                
                desc = line_item.get('description', 'N/A')
                should_include = analysis.get('should_be_included', item.get('should_be_included', False))
                is_normal = analysis.get('is_normal_wear_tear', item.get('is_normal_wear_tear', False))
                is_covered = analysis.get('is_covered_by_addendum', item.get('is_covered_by_addendum', False))
                confidence = analysis.get('confidence', item.get('analysis_confidence', 0))
                if isinstance(confidence, (Decimal, int, float)):
                    confidence = float(confidence)
                
                # Get reasoning
                llm_reasoning = analysis.get('reasoning', item.get('analysis_reasoning', item.get('llm_reasoning', '')))
                deterministic_rule = item.get('deterministic_rule', '')
                
                # Get deterministic category tags
                category_tags = []
                if item.get('is_rent', False):
                    category_tags.append('RENT')
                if item.get('is_month_to_month', False):
                    category_tags.append('MONTH_TO_MONTH')
                if item.get('is_cleaning', False):
                    category_tags.append('CLEANING')
                if item.get('is_repair', False):
                    category_tags.append('REPAIR')
                if item.get('is_damage', False):
                    category_tags.append('DAMAGE')
                if item.get('is_improper_notice', False):
                    category_tags.append('IMPROPER_NOTICE')
                if item.get('is_other_insurance', False):
                    category_tags.append('OTHER_INSURANCE')
                if item.get('is_contractual_fee', False):
                    category_tags.append('CONTRACTUAL_FEE')
                if item.get('is_after_lease_end', False):
                    category_tags.append('AFTER_LEASE_END')
                
                # Build comprehensive reasoning
                reasoning_parts = []
                if deterministic_rule:
                    reasoning_parts.append(f"Deterministic Rule: {deterministic_rule}")
                if category_tags:
                    reasoning_parts.append(f"Categories: {', '.join(category_tags)}")
                if is_normal:
                    reasoning_parts.append("Normal wear/tear")
                if llm_reasoning:
                    reasoning_parts.append(f"LLM: {llm_reasoning}")
                if not reasoning_parts:
                    reasoning_parts.append("No specific reasoning provided")
                
                full_reasoning = " | ".join(reasoning_parts)
                
                include_flag = "✅ APPROVED" if should_include else "❌ DENIED"
                
                if should_include:
                    total_included += amount
                else:
                    total_excluded += amount
                
                # Print detailed line item info
                print(f"\n{'─'*100}")
                print(f"Line Item #{i}: {desc}")
                print(f"  Amount: ${amount:,.2f}")
                print(f"  Decision: {include_flag}")
                print(f"  Confidence: {confidence*100:.1f}%")
                print(f"  Reasoning: {full_reasoning}")
                if category_tags:
                    print(f"  Category Tags: {', '.join(category_tags)}")
                if is_normal:
                    print(f"  Normal Wear/Tear: YES")
                if is_covered:
                    print(f"  Covered by Addendum: YES")
            
            print(f"\n{'='*100}")
            print(f"SUMMARY - Claim {tracking_num}")
            print(f"{'='*100}")
            print(f"  Total Included: ${total_included:,.2f}")
            print(f"  Total Excluded: ${total_excluded:,.2f}")
            print(f"  Invoice Total: ${float(decision.invoice_total):,.2f}")
            print(f"  Eligible Total: ${float(decision.eligible_total):,.2f}")
            if decision.cap_amount:
                print(f"  Cap Amount: ${float(decision.cap_amount):,.2f}")
            print(f"  Proposed Amount: ${float(decision.proposed_benefit_amount):,.2f}")
            print(f"{'='*100}\n")
            
            # Also log in structured format for parsing
            logger.info(f"  📋 Line Items Detail (Claim {tracking_num}):")
            for i, item in enumerate(all_items, 1):
                if isinstance(item, dict) and 'line_item' in item:
                    line_item = item['line_item']
                    analysis = item.get('analysis', {})
                else:
                    line_item = item
                    analysis = item
                
                from decimal import Decimal
                amount_raw = line_item.get('amount', 0)
                amount = float(amount_raw) if isinstance(amount_raw, (Decimal, int, float)) else float(str(amount_raw))
                
                desc = line_item.get('description', 'N/A')
                should_include = analysis.get('should_be_included', item.get('should_be_included', False))
                
                # Get all reasoning components
                llm_reasoning = analysis.get('reasoning', item.get('analysis_reasoning', item.get('llm_reasoning', '')))
                deterministic_rule = item.get('deterministic_rule', '')
                
                category_tags = []
                for tag in ['is_rent', 'is_month_to_month', 'is_cleaning', 'is_repair', 'is_damage', 
                           'is_improper_notice', 'is_other_insurance', 'is_contractual_fee', 'is_after_lease_end']:
                    if item.get(tag, False):
                        category_tags.append(tag.upper().replace('IS_', ''))
                
                logger.info(f"    Item {i}: {desc} | Amount: ${amount:.2f} | Included: {should_include} | "
                          f"Categories: {','.join(category_tags) if category_tags else 'none'} | "
                          f"Rule: {deterministic_rule if deterministic_rule else 'standard'} | "
                          f"Reasoning: {llm_reasoning[:100] if llm_reasoning else 'N/A'}")
            
            # Show calculation method
            print(f"{'='*80}")
            print(f"CALCULATION METHOD - Claim {tracking_num}")
            print(f"{'='*80}")
            print(f"1. Extracted {len(all_items)} line items from invoices/statements")
            print(f"2. Analyzed each line item with Gemini 2.5 Pro:")
            print(f"   - Checked if covered by addendum protections")
            print(f"   - Checked if normal wear and tear")
            print(f"   - Determined should_be_included flag")
            print(f"3. Sum of items with should_be_included=True: ${total_included:.2f}")
            print(f"4. Eligible Total: ${float(decision.eligible_total):.2f}")
            if decision.cap_amount:
                print(f"5. Applied cap: min(${float(decision.eligible_total):.2f}, ${float(decision.cap_amount):.2f}) = ${float(decision.proposed_benefit_amount):.2f}")
            else:
                print(f"5. No cap applied: Proposed Amount = ${float(decision.proposed_benefit_amount):.2f}")
            print(f"6. Final Decision: {decision.proposed_status.upper()} ${float(decision.proposed_benefit_amount):.2f}")
            print(f"{'='*80}\n")
            
            # Show document analysis results
            doc_analysis = decision.reasoning.get('document_analysis', {})
            if doc_analysis:
                if doc_analysis.get('denial_reasons'):
                    logger.info(f"  📋 Denial reasons: {', '.join(doc_analysis['denial_reasons'][:3])}")
            
            # Show flags
            if decision.flags.get('critical'):
                logger.warning(f"  ⚠️  Critical flags: {decision.flags['critical']}")
            if decision.flags.get('warnings'):
                logger.info(f"  ⚠️  Warnings: {len(decision.flags['warnings'])}")
            
            # Export line items in JSON format for rule improvement
            import json
            line_items_export = []
            for item in all_items:
                if isinstance(item, dict) and 'line_item' in item:
                    line_item = item['line_item']
                    analysis = item.get('analysis', {})
                else:
                    line_item = item
                    analysis = item
                
                from decimal import Decimal
                amount_raw = line_item.get('amount', 0)
                amount = float(amount_raw) if isinstance(amount_raw, (Decimal, int, float)) else float(str(amount_raw))
                
                line_items_export.append({
                    'description': line_item.get('description', ''),
                    'amount': amount,
                    'should_be_included': analysis.get('should_be_included', item.get('should_be_included', False)),
                    'is_rent': item.get('is_rent', False),
                    'is_month_to_month': item.get('is_month_to_month', False),
                    'is_cleaning': item.get('is_cleaning', False),
                    'is_repair': item.get('is_repair', False),
                    'is_damage': item.get('is_damage', False),
                    'is_improper_notice': item.get('is_improper_notice', False),
                    'is_other_insurance': item.get('is_other_insurance', False),
                    'is_contractual_fee': item.get('is_contractual_fee', False),
                    'is_after_lease_end': item.get('is_after_lease_end', False),
                    'is_normal_wear_tear': analysis.get('is_normal_wear_tear', False),
                    'deterministic_rule': item.get('deterministic_rule', ''),
                    'llm_reasoning': analysis.get('reasoning', item.get('analysis_reasoning', item.get('llm_reasoning', ''))),
                    'confidence': float(analysis.get('confidence', item.get('analysis_confidence', 0.5)))
                })
            
            # Log JSON export for rule improvement
            export_data = {
                'claim_tracking_number': tracking_num,
                'claim_id': claim_id,
                'decision_status': decision.proposed_status,
                'proposed_amount': float(decision.proposed_benefit_amount),
                'line_items': line_items_export,
                'timestamp': datetime.now().isoformat()
            }
            logger.info(f"  📄 Line Items JSON Export (for rule improvement):")
            logger.info(f"     {json.dumps(export_data, indent=2)}")
            
            results.append({
                'tracking': tracking_num,
                'status': decision.proposed_status,
                'amount': float(decision.proposed_benefit_amount),
                'confidence': decision.confidence_score
            })
            
        except Exception as e:
            logger.error(f"  ✗ Error processing claim {tracking_num}: {e}", exc_info=True)
            results.append({
                'tracking': tracking_num,
                'status': 'error',
                'amount': 0,
                'confidence': 0
            })
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total Claims: {len(results)}")
    
    approvals = sum(1 for r in results if r['status'] == 'approve')
    denials = sum(1 for r in results if r['status'] == 'deny')
    errors = sum(1 for r in results if r['status'] == 'error')
    
    logger.info(f"✅ Approvals: {approvals}")
    logger.info(f"❌ Denials: {denials}")
    if errors > 0:
        logger.info(f"⚠️  Errors: {errors}")
    
    total_amount = sum(r['amount'] for r in results if r['status'] == 'approve')
    logger.info(f"💰 Total Approved Amount: ${total_amount:.2f}")
    
    avg_confidence = sum(r['confidence'] for r in results) / len(results) if results else 0
    logger.info(f"📊 Average Confidence: {avg_confidence:.1f}%")
    
    logger.info(f"{'='*80}")


def _determine_rule_branch(decision, has_addendum: bool, has_invoice: bool, max_benefit) -> str:
    """Determine which rule branch was taken."""
    if not has_addendum:
        return "missing_waiver_addendum"
    if not has_invoice:
        return "missing_invoice"
    if max_benefit is None or max_benefit == 0:
        return "missing_max_benefit"
    if decision.eligible_total == 0:
        return "no_eligible_charges"
    if decision.proposed_benefit_amount > 0:
        return "normal_approve"
    return "deny_other"


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run decision engine on claims")
    parser.add_argument('--start', type=int, default=900, help='Start tracking number')
    parser.add_argument('--end', type=int, default=904, help='End tracking number')
    
    args = parser.parse_args()
    
    asyncio.run(run_decisions(args.start, args.end))

