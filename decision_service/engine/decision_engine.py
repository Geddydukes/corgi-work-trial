import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict
from decimal import Decimal

from shared.config import Config

from decision_service.engine.eligibility import EligibilityEngine
from decision_service.engine.invoice_parser import InvoiceParser
from decision_service.engine.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)

_claim_locks: Dict[int, asyncio.Lock] = {}
_claim_locks_guard = asyncio.Lock()


@asynccontextmanager
async def claim_processing_lock(claim_id: int):
    """
    Serialize claim evaluation to avoid race conditions when reusing cached analysis.
    """
    async with _claim_locks_guard:
        lock = _claim_locks.get(claim_id)
        if lock is None:
            lock = asyncio.Lock()
            _claim_locks[claim_id] = lock
    async with lock:
        yield


class Decision:
    def __init__(
        self,
        claim_id: int,
        proposed_status: str,
        proposed_benefit_amount: Decimal,
        eligible_total: Decimal,
        invoice_total: Decimal,
        cap_amount: Optional[Decimal],
        approved_line_items: list,
        ineligible_line_items: list,
        flags: dict,
        missing_data: dict,
        reasoning: dict,
        confidence_score: float,
        engine_version: str,
        claim_amount: Decimal,
        max_benefit: Optional[Decimal],
        document_count: int,
        line_item_count: int,
    ):
        self.claim_id = claim_id
        self.proposed_status = proposed_status
        self.proposed_benefit_amount = proposed_benefit_amount
        self.eligible_total = eligible_total
        self.invoice_total = invoice_total
        self.cap_amount = cap_amount
        self.approved_line_items = approved_line_items
        self.ineligible_line_items = ineligible_line_items
        self.flags = flags
        self.missing_data = missing_data
        self.reasoning = reasoning
        self.confidence_score = confidence_score
        self.engine_version = engine_version
        self.claim_amount = claim_amount
        self.max_benefit = max_benefit
        self.document_count = document_count
        self.line_item_count = line_item_count


class DecisionEngine:
    def __init__(self):
        self.eligibility_engine = EligibilityEngine()
        self.invoice_parser = InvoiceParser()
        self.rule_evaluator = RuleEvaluator()
        from decision_service.engine.document_analyzer import DocumentAnalyzer
        self.document_analyzer = DocumentAnalyzer()
    
    async def evaluate_claim(
        self,
        claim_id: int,
        override_max_benefit: Optional[Decimal] = None
    ) -> Decision:
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        repository = ClaimRepository()
        doc_repository = DocumentRepository()
        
        claim = await repository.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        
        documents = await doc_repository.get_documents(claim_id)
        
        from shared.models import DocumentType
        
        has_addendum = any(
            doc.get("document_type") == DocumentType.ADDENDUM.value 
            for doc in documents
        )
        has_invoice = any(
            doc.get("document_type") == DocumentType.INVOICE.value 
            for doc in documents
        )
        
        # Check if we have existing document analysis from a previous decision
        # This allows us to skip LLM calls when rerunning with updated rules
        document_analysis = None
        try:
            # Get latest decision for this claim to check for existing analysis
            with repository.get_connection() as conn:
                from sqlalchemy import text
                result = conn.execute(
                    text("""
                        SELECT reasoning
                        FROM decisions
                        WHERE claim_id = :claim_id
                            AND is_active = TRUE
                        ORDER BY decided_at DESC
                        LIMIT 1
                    """),
                    {"claim_id": claim_id}
                ).fetchone()
                
                if result and result[0]:
                    import json
                    reasoning = result[0] if isinstance(result[0], dict) else json.loads(result[0]) if isinstance(result[0], str) else {}
                    if isinstance(reasoning, dict) and 'document_analysis' in reasoning:
                        doc_analysis = reasoning['document_analysis']
                        # Check if it's a valid analysis structure
                        if isinstance(doc_analysis, dict) and any(key in doc_analysis for key in ['denial_reasons', 'is_normal_wear_tear', 'has_eligible_charges']):
                            logger.info(f"Using existing document analysis from previous decision (skipping LLM call)")
                            document_analysis = {
                                'denial_reasons': doc_analysis.get('denial_reasons', []),
                                'is_normal_wear_tear': doc_analysis.get('is_normal_wear_tear', False),
                                'charges_covered_by_addendum': doc_analysis.get('charges_covered_by_addendum', False),
                                'has_eligible_charges': doc_analysis.get('has_eligible_charges', False),
                                'addendum_protections': doc_analysis.get('addendum_protections', []),
                                'missing_information': [],
                                'charges_found': [],
                                'document_specific_findings': {},
                                'analysis': doc_analysis.get('analysis', ''),
                                'critical_flags': [],
                                'warnings': [],
                                'should_deny': doc_analysis.get('is_normal_wear_tear', False) and not doc_analysis.get('has_eligible_charges', False)
                            }
        except Exception as e:
            logger.warning(f"Could not retrieve existing document analysis: {e}, will analyze with LLM")
        
        # If no existing analysis, analyze with LLM
        if document_analysis is None:
            logger.info(f"Batch analyzing {len(documents)} documents for denial reasons with Gemini 2.5 Pro...")
            document_analysis = self.document_analyzer.analyze_all_documents(documents)
        
        if document_analysis.get('should_deny'):
            logger.warning(f"Document analysis suggests denial: {document_analysis.get('denial_reasons', [])}")
        
        if document_analysis.get('charges_covered_by_addendum'):
            logger.info(f"Document analysis indicates charges are covered by addendum protections")
        
        # ============================================================
        # OPTIMIZATION: Check for cached line items FIRST to avoid LLM calls
        # If we have line items from a previous decision, use them directly
        # This saves money by skipping both extraction AND analysis LLM calls
        # ============================================================
        all_line_items = []
        invoice_total = Decimal("0")
        cached_line_items_used = False
        
        try:
            with repository.get_connection() as conn:
                from sqlalchemy import text as sql_text
                result = conn.execute(
                    sql_text("""
                        SELECT approved_line_items, ineligible_line_items
                        FROM decisions
                        WHERE claim_id = :claim_id
                            AND is_active = TRUE
                        ORDER BY decided_at DESC
                        LIMIT 1
                    """),
                    {"claim_id": claim_id}
                ).fetchone()
                
                if result and (result[0] or result[1]):
                    import json
                    approved_items = result[0] if isinstance(result[0], list) else (json.loads(result[0]) if isinstance(result[0], str) else [])
                    ineligible_items = result[1] if isinstance(result[1], list) else (json.loads(result[1]) if isinstance(result[1], str) else [])
                    all_cached_items = approved_items + ineligible_items
                    
                    if all_cached_items:
                        logger.info(f"Found {len(all_cached_items)} cached line items from previous decision - SKIPPING LLM extraction")
                        
                        # Extract line item data from cached items (they have nested structure)
                        for cached_item in all_cached_items:
                            line_item_data = cached_item.get('line_item', {})
                            if line_item_data:
                                # Reconstruct the line item in extraction format
                                all_line_items.append({
                                    'description': line_item_data.get('description', ''),
                                    'amount': line_item_data.get('amount', 0),
                                    'quantity': line_item_data.get('quantity', 1),
                                    'unit_price': line_item_data.get('unit_price', line_item_data.get('amount', 0)),
                                    'line_number': line_item_data.get('line_number', 0),
                                    # Preserve LLM analysis flags for reuse
                                    '_cached_analysis': cached_item.get('analysis', {}),
                                    '_cached_flags': {
                                        'is_normal_wear_tear': cached_item.get('is_normal_wear_tear', False),
                                        'is_cleaning': cached_item.get('is_cleaning', False),
                                        'is_repair': cached_item.get('is_repair', False),
                                        'is_damage': cached_item.get('is_damage', False),
                                    }
                                })
                                
                                # Calculate invoice total from cached items (only actual charges)
                                amount = Decimal(str(line_item_data.get('amount', 0)))
                                description = str(line_item_data.get('description', '')).lower()
                                
                                is_prior_balance = any(phrase in description for phrase in [
                                    'balance as of', 'beginning balance', 'initial balance', 
                                    'prior balance', 'opening balance', 'balance forward',
                                    'carryover balance', 'carry over balance', 'previous balance',
                                    'balance brought forward', 'balance b/f', 'balance bf'
                                ])
                                is_rent = any(phrase in description for phrase in ['rent', 'monthly rent', 'residential rent'])
                                is_fee = any(phrase in description for phrase in [
                                    'late charge', 'late fee', 'utility revenue', 'security deposit protection',
                                    'renters insurance', 'renter insurance', 'reletting'
                                ])
                                is_payment = amount < 0
                                
                                # Only count actual damage/cleaning charges
                                if not is_prior_balance and not is_rent and not is_fee and not is_payment:
                                    invoice_total += amount
                        
                        cached_line_items_used = True
                        logger.info(f"Using {len(all_line_items)} cached line items, invoice_total=${invoice_total}")
        except Exception as e:
            logger.warning(f"Could not retrieve cached line items: {e}, will extract from documents")
        
        # Only extract from documents if we don't have cached line items
        if not cached_line_items_used:
            logger.info("No cached line items found - extracting from documents (LLM call)")
            for doc in documents:
                doc_type = doc.get('document_type', 'unknown')
                doc_type_lower = str(doc_type).lower()
                filename = doc.get('original_filename', '')
                text = doc.get('extracted_text', '')
                
                filename_lower = filename.lower()
                is_authorization_form = (
                    'authorization' in filename_lower or
                    'authorization form' in filename_lower
                )
                
                is_move_out_invoice = (
                    not is_authorization_form and (
                        doc_type_lower == DocumentType.INVOICE.value or
                        doc_type_lower == DocumentType.UNKNOWN.value or
                        'invoice' in filename_lower or
                        'move-out-statement' in filename_lower or
                        'move out statement' in filename_lower or
                        ('statement' in filename_lower and 'move' in filename_lower) or
                        ('deposit' in filename_lower and 'disposition' in filename_lower)
                    )
                )
                
                # Extract from short deposit disposition documents only (under 2000 chars to keep costs low)
                # These are typically short, focused documents with specific charges
                is_short_deposit_disposition = (
                    'deposit' in filename_lower and 
                    ('disposition' in filename_lower or 'amount due' in filename_lower) and
                    'ledger' not in filename_lower and  # Exclude tenant ledgers
                    len(text) > 0 and len(text) < 2000  # Only short documents
                )
                
                is_invoice_or_statement = is_move_out_invoice or is_short_deposit_disposition
                
                # Initialize extracted_items for this document
                extracted_items = []
                
                if is_invoice_or_statement and text:
                    logger.info(f"Extracting line items from {filename}...")
                    try:
                        extracted_items = self.document_analyzer.extract_line_items_from_invoice(text, filename)
                    except Exception as e:
                        logger.warning(f"Gemini line item extraction failed for {filename}: {e}, falling back to InvoiceParser")
                        try:
                            from decision_service.engine.invoice_parser import InvoiceParser
                            parser = InvoiceParser()
                            parse_result = await parser.parse_documents([doc])
                            if parse_result.get("line_items"):
                                extracted_items = parse_result["line_items"]
                        except Exception as fallback_error:
                            logger.error(f"InvoiceParser fallback also failed for {filename}: {fallback_error}")
                
                if extracted_items:
                    all_line_items.extend(extracted_items)
                    for item in extracted_items:
                        amount = Decimal(str(item.get('amount', 0)))
                        description = str(item.get('description', '')).lower()
                        
                        # Exclude non-eligible charges from invoice_total
                        is_prior_balance = any(phrase in description for phrase in [
                            'balance as of', 'beginning balance', 'initial balance', 
                            'prior balance', 'opening balance', 'balance forward',
                            'carryover balance', 'carry over balance', 'previous balance',
                            'balance brought forward', 'balance b/f', 'balance bf'
                        ])
                        is_rent = any(phrase in description for phrase in ['rent', 'monthly rent', 'residential rent'])
                        is_fee = any(phrase in description for phrase in [
                            'late charge', 'late fee', 'utility revenue', 'security deposit protection',
                            'renters insurance', 'renter insurance', 'reletting'
                        ])
                        is_payment = amount < 0  # Payments/credits are negative
                        
                        # Only count actual damage/cleaning charges in invoice_total
                        if not is_prior_balance and not is_rent and not is_fee and not is_payment:
                            invoice_total += amount
        
        invoice_data = {
            "line_items": all_line_items,
            "total_amount": invoice_total,
            "document_count": len([d for d in documents if d.get('document_type') == DocumentType.INVOICE.value]),
            "flags": {"critical": [], "warnings": [], "info": []}
        }
        
        logger.info(f"Extracted {len(all_line_items)} line items from invoices/statements")
        
        addendum_text = None
        lease_text = None
        for doc in documents:
            if doc.get('document_type') == DocumentType.ADDENDUM.value:
                addendum_text = doc.get('extracted_text', '')
            elif doc.get('document_type') == DocumentType.LEASE.value:
                lease_text = doc.get('extracted_text', '')
        
        lease_end_date = claim.get('lease_end_date')
        # lease_end_date may already be a string (ISO format) or a date object
        if lease_end_date:
            if isinstance(lease_end_date, str):
                lease_end_date_str = lease_end_date
            else:
                lease_end_date_str = lease_end_date.isoformat()
        else:
            lease_end_date_str = None
        
        claim_context = {
            'max_benefit': float(claim.get('max_benefit', 0)) if claim.get('max_benefit') else None,
            'security_deposit': float(claim.get('security_deposit_amount', 0)) if claim.get('security_deposit_amount') else None,
            'claim_amount': float(claim.get('claim_amount', 0)) if claim.get('claim_amount') else None,
            'lease_text': lease_text[:2000] if lease_text else None,
            'lease_end_date': lease_end_date_str
        }
        
        # ============================================================
        # Apply deterministic rules to line items
        # If we used cached line items, we already have the LLM analysis
        # Just apply fresh deterministic rules (no LLM call needed)
        # ============================================================
        line_items_with_flags = []
        json_validation_failed_count = 0
        if invoice_data.get("line_items"):
            async with claim_processing_lock(claim_id):
                # Check if line items have cached analysis (from earlier in this function)
                has_cached_analysis = cached_line_items_used and all(
                    item.get('_cached_analysis') for item in invoice_data["line_items"]
                )
                
                if has_cached_analysis:
                    # Use cached LLM analysis - just apply deterministic rules
                    logger.info(f"Using cached LLM analysis for {len(invoice_data['line_items'])} items - SKIPPING LLM analysis call")
                    
                    # Build LLM suggestions from cached analysis
                    llm_suggestions = []
                    clean_line_items = []
                    for item in invoice_data["line_items"]:
                        cached_analysis = item.get('_cached_analysis', {})
                        llm_suggestions.append({
                            'is_normal_wear_tear': cached_analysis.get('is_normal_wear_tear', False),
                            'is_covered_by_addendum': cached_analysis.get('is_covered_by_addendum', True),
                            'confidence': cached_analysis.get('confidence', 0.5),
                            'reasoning': cached_analysis.get('reasoning', '')
                        })
                        
                        # Remove internal cached fields before processing
                        clean_item = {k: v for k, v in item.items() if not k.startswith('_cached')}
                        clean_line_items.append(clean_item)
                    
                    # Apply deterministic rules with cached LLM suggestions
                    from decision_service.engine.deterministic_rules import apply_deterministic_rules
                    line_items_with_flags = apply_deterministic_rules(
                        line_items=clean_line_items,
                        lease_end_date=lease_end_date_str,
                        llm_suggestions=llm_suggestions
                    )
                    logger.info(f"Applied deterministic rules to {len(line_items_with_flags)} cached items (NO LLM calls made)")
                
                else:
                    # No cached analysis - need to call LLM for fresh line items
                    logger.info(f"Batch analyzing {len(invoice_data['line_items'])} line items with Gemini 2.5 Pro...")
                    llm_analyzed_items = self.document_analyzer.analyze_line_items_batch(
                        invoice_data["line_items"],
                        addendum_text,
                        claim_context
                    )
                    
                    # CRITICAL: Apply deterministic rules to LLM-analyzed items
                    # The LLM's should_be_included is advisory - deterministic rules have final say
                    from decision_service.engine.deterministic_rules import apply_deterministic_rules
                    
                    # Build LLM suggestions from analyzed items
                    llm_suggestions = []
                    for item in llm_analyzed_items:
                        llm_suggestions.append({
                            'is_normal_wear_tear': item.get('is_normal_wear_tear', False),
                            'is_covered_by_addendum': item.get('is_covered_by_addendum', True),  # Default to True (lenient)
                            'confidence': item.get('llm_confidence', item.get('analysis_confidence', 0.5)),
                            'reasoning': item.get('llm_reasoning', item.get('analysis_reasoning', ''))
                        })
                    
                    # Apply deterministic rules (this ensures lenient rules override LLM denials)
                    line_items_with_flags = apply_deterministic_rules(
                        line_items=llm_analyzed_items,
                        lease_end_date=lease_end_date_str,
                        llm_suggestions=llm_suggestions
                    )
                    logger.info(f"Applied deterministic rules to {len(line_items_with_flags)} LLM-analyzed items")
                
                # Check for JSON validation failures and flag in decision
                json_validation_failed_count = sum(1 for item in line_items_with_flags if item.get('json_validation_failed', False))
                if json_validation_failed_count > 0:
                    logger.warning(f"JSON validation failed for {json_validation_failed_count} out of {len(line_items_with_flags)} line items")
                    invoice_data["flags"]["warnings"].append(f"json_validation_failed_for_{json_validation_failed_count}_line_items")
                    invoice_data["flags"]["critical"].append("llm_json_validation_failure")
                
                # Update invoice_data with flagged line items
                invoice_data["line_items"] = line_items_with_flags
        
        try:
            eligibility_result = await self.eligibility_engine.calculate(
                claim=claim,
                invoice_data=invoice_data
            )
            
            # Recalculate approved/ineligible items based on deterministic rules
            approved_items = []
            ineligible_items = []
            
            # Calculate eligible totals, explicitly separating charges and credits/payments
            eligible_total = Decimal("0")
            approved_charge_total = Decimal("0")
            approved_credit_total = Decimal("0")
            approved_count = 0
            for item in line_items_with_flags:
                if item.get('should_be_included', False):
                    amount = Decimal(str(item.get('amount', 0)))
                    if amount >= 0:
                        approved_charge_total += amount
                    else:
                        approved_credit_total += amount
                    eligible_total += amount
                    approved_count += 1
            
            # Sanity check: cap eligible_total relative to invoice_total using configurable multiplier
            sanity_multiplier = Decimal(str(Config.ELIGIBLE_TO_INVOICE_SANITY_MULTIPLIER))
            if invoice_total > 0 and eligible_total > invoice_total * sanity_multiplier:
                logger.warning(
                    f"Eligible total ${eligible_total} exceeds invoice_total ${invoice_total} by multiplier>{sanity_multiplier}, applying sanity cap"
                )
                eligible_total = invoice_total * sanity_multiplier
                invoice_data["flags"]["warnings"].append(f"eligible_total_sanity_check_applied: capped to ${eligible_total}")
            
            # Log summary for debugging - this will help diagnose the $0 issue
            logger.info(
                f"Claim {claim_id}: {approved_count} approved items "
                f"(charges=${approved_charge_total}, credits=${approved_credit_total}) "
                f"with eligible_total=${eligible_total}, invoice_total=${invoice_total}"
            )
            
            for item in line_items_with_flags:
                amount = Decimal(str(item.get('amount', 0)))
                should_include = item.get('should_be_included', False)
                
                item_with_analysis = {
                    'line_item': {
                        'description': item.get('description', ''),
                        'amount': float(amount),
                        'quantity': item.get('quantity', 1),
                        'unit_price': item.get('unit_price', float(amount))
                    },
                    'analysis': {
                        'should_be_included': should_include,
                        'is_normal_wear_tear': item.get('is_normal_wear_tear', False),
                        'is_covered_by_addendum': item.get('is_covered_by_addendum', True),
                        'confidence': item.get('analysis_confidence', item.get('llm_confidence', 0.5)),
                        'reasoning': item.get('analysis_reasoning', item.get('llm_reasoning', '')),
                        'addendum_reference': item.get('addendum_reference', item.get('llm_addendum_reference', 'N/A'))
                    },
                    'deterministic_rule': item.get('deterministic_rule', ''),
                    'is_rent': item.get('is_rent', False),
                    'is_month_to_month': item.get('is_month_to_month', False),
                    'is_cleaning': item.get('is_cleaning', False),
                    'is_repair': item.get('is_repair', False),
                    'is_damage': item.get('is_damage', False),
                    'is_improper_notice': item.get('is_improper_notice', False),
                    'is_other_insurance': item.get('is_other_insurance', False),
                    'is_contractual_fee': item.get('is_contractual_fee', False),
                    'is_after_lease_end': item.get('is_after_lease_end', False),
                    'llm_suggested_included': item.get('llm_suggested_included', None),
                    'json_validation_failed': item.get('json_validation_failed', False)
                }
                
                if should_include:
                    approved_items.append(item_with_analysis)
                else:
                    ineligible_items.append(item_with_analysis)
            
            eligibility_result["approved_items"] = approved_items
            eligibility_result["ineligible_items"] = ineligible_items
            eligibility_result["eligible_total"] = eligible_total
            eligibility_result["eligible_charge_total"] = approved_charge_total
            eligibility_result["eligible_credit_total"] = approved_credit_total
                    
        except Exception as e:
            logger.error(f"Eligibility calculation failed for claim {claim_id}: {e}", exc_info=True)
            eligibility_result = {
                "approved_items": [],
                "ineligible_items": [],
                "eligible_total": Decimal("0"),
                "credits": []
            }
        
        low_confidence_docs = [
            doc for doc in documents 
            if doc.get("ocr_confidence") is not None and doc.get("ocr_confidence", 100) < 50
        ]
        
        invoice_flags = invoice_data.get("flags", {})
        if invoice_flags:
            eligibility_result.setdefault("flags", {})
            for severity in ["critical", "warnings", "info"]:
                if severity in invoice_flags:
                    eligibility_result["flags"].setdefault(severity, []).extend(invoice_flags[severity])
        
        if low_confidence_docs:
            eligibility_result.setdefault("flags", {}).setdefault("warnings", []).append(
                f"low_ocr_confidence: {len(low_confidence_docs)} document(s) with OCR confidence < 50%"
            )
        
        # Incorporate document analysis as warnings only (not blocking)
        # Deterministic rules have already decided coverage - document analysis is advisory
        if document_analysis.get('is_normal_wear_tear') and not document_analysis.get('has_eligible_charges'):
            # Only warn if ALL charges are normal wear/tear AND we have no eligible items
            if eligibility_result.get("eligible_total", 0) == 0:
                eligibility_result.setdefault("flags", {}).setdefault("warnings", []).append(
                    "document_analysis_suggests_all_normal_wear_tear"
                )
        elif document_analysis.get('is_normal_wear_tear') and document_analysis.get('has_eligible_charges'):
            eligibility_result.setdefault("flags", {}).setdefault("warnings", []).append(
                "document_analysis_suggests_some_normal_wear_tear"
            )
        
        if document_analysis.get('denial_reasons'):
            for reason in document_analysis['denial_reasons']:
                eligibility_result.setdefault("flags", {}).setdefault("warnings", []).append(
                    f"document_analysis_advisory: {reason[:100]}"
                )
        
        # Compute aggregate document confidence for RuleEvaluator
        document_confidence = None
        if documents:
            confidences = [
                doc.get('classification_confidence', 100) or 100
                for doc in documents
                if doc.get('classification_confidence') is not None
            ]
            if confidences:
                document_confidence = min(confidences)
        
        rule_result = await self.rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result,
            override_max_benefit=override_max_benefit,
            has_addendum=has_addendum,
            has_invoice=has_invoice,
            invoice_total=invoice_data["total_amount"],
            document_confidence=document_confidence
        )
        
        # REMOVED: Aggressive document analysis override
        # Deterministic rules have already decided coverage based on line items
        # Document analysis is advisory only - don't override rule decisions
        
        if invoice_flags:
            for severity in ["critical", "warnings", "info"]:
                if severity in invoice_flags:
                    rule_result["flags"][severity].extend(invoice_flags[severity])
        
        eligibility_flags = eligibility_result.get("flags", {})
        if eligibility_flags:
            for severity in ["critical", "warnings", "info"]:
                if severity in eligibility_flags:
                    rule_result["flags"][severity].extend(eligibility_flags[severity])
        
        if low_confidence_docs:
            rule_result["flags"]["warnings"].append(
                f"low_ocr_confidence: {len(low_confidence_docs)} document(s) with OCR confidence < 50%"
            )
        
        claim_amount_raw = claim.get("claim_amount")
        claim_amount = Decimal(str(claim_amount_raw)) if claim_amount_raw is not None else None
        max_benefit_raw = claim.get("max_benefit")
        max_benefit = Decimal(str(max_benefit_raw)) if max_benefit_raw is not None and max_benefit_raw != "" else None
        
        line_item_count = len(invoice_data.get("line_items", []))
        
        decision = Decision(
            claim_id=claim_id,
            proposed_status=rule_result["status"],
            proposed_benefit_amount=rule_result["benefit_amount"],
            eligible_total=eligibility_result["eligible_total"],
            invoice_total=invoice_data["total_amount"],
            cap_amount=rule_result.get("cap_amount"),
            approved_line_items=eligibility_result["approved_items"],
            ineligible_line_items=eligibility_result["ineligible_items"],
            flags=rule_result["flags"],
            missing_data=rule_result["missing_data"],
            reasoning={
                **rule_result["reasoning"],
                "document_analysis": {
                    "denial_reasons": document_analysis.get('denial_reasons', []),
                    "is_normal_wear_tear": document_analysis.get('is_normal_wear_tear', False),
                    "charges_covered_by_addendum": document_analysis.get('charges_covered_by_addendum', False),
                    "has_eligible_charges": document_analysis.get('has_eligible_charges', False),
                    "addendum_protections": document_analysis.get('addendum_protections', [])
                }
            },
            confidence_score=rule_result["confidence"],
            engine_version=self.rule_evaluator.version,
            claim_amount=claim_amount,
            max_benefit=max_benefit,
            document_count=len(documents),
            line_item_count=line_item_count
        )
        
        return decision
