import logging
from typing import Optional
from decimal import Decimal

from decision_service.engine.eligibility import EligibilityEngine
from decision_service.engine.invoice_parser import InvoiceParser
from decision_service.engine.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)


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
        
        # Analyze all documents for denial reasons using Gemini (batch processing)
        logger.info(f"Batch analyzing {len(documents)} documents for denial reasons with Gemini 2.5 Pro...")
        document_analysis = self.document_analyzer.analyze_all_documents(documents)
        
        # Check for critical denial reasons
        if document_analysis.get('should_deny'):
            logger.warning(f"Document analysis suggests denial: {document_analysis.get('denial_reasons', [])}")
        
        if document_analysis.get('charges_covered_by_addendum'):
            logger.info(f"Document analysis indicates charges are covered by addendum protections")
        
        # Extract line items using Gemini for invoice/statement documents
        # Only extract from actual invoices/move-out statements, not all documents
        all_line_items = []
        invoice_total = Decimal("0")
        
        for doc in documents:
            doc_type = doc.get('document_type', 'unknown')
            filename = doc.get('original_filename', '')
            text = doc.get('extracted_text', '')
            
            # Only extract from move-out invoices/statements, NOT authorization forms or other documents
            filename_lower = filename.lower()
            is_authorization_form = (
                'authorization' in filename_lower or
                'authorization form' in filename_lower
            )
            
            is_move_out_invoice = (
                (doc_type == DocumentType.INVOICE.value or
                 'move-out-statement' in filename_lower or
                 'move out statement' in filename_lower or
                 ('statement' in filename_lower and 'move' in filename_lower)) and
                not is_authorization_form
            )
            
            is_invoice_or_statement = is_move_out_invoice
            
            if is_invoice_or_statement and text:
                logger.info(f"Extracting line items from {filename}...")
                extracted_items = []
                try:
                    extracted_items = self.document_analyzer.extract_line_items_from_invoice(text, filename)
                except Exception as e:
                    logger.warning(f"Gemini line item extraction failed for {filename}: {e}, falling back to InvoiceParser")
                    # Fallback to InvoiceParser if Gemini fails
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
                    # Calculate invoice_total as sum of POSITIVE charges only (exclude payments/credits and prior balances)
                    # Payments/credits are negative amounts and should not reduce the invoice total
                    # Initial/beginning balances are prior balances, not new charges on this invoice
                    for item in extracted_items:
                        amount = Decimal(str(item.get('amount', 0)))
                        description = str(item.get('description', '')).lower()
                        # Exclude initial/beginning balances (prior balances, not new charges)
                        is_prior_balance = any(phrase in description for phrase in [
                            'balance as of', 'beginning balance', 'initial balance', 
                            'prior balance', 'opening balance', 'balance forward'
                        ])
                        # Only add positive amounts (charges), not negative amounts (payments/credits) or prior balances
                        if amount > 0 and not is_prior_balance:
                            invoice_total += amount
        
        invoice_data = {
            "line_items": all_line_items,
            "total_amount": invoice_total,
            "document_count": len([d for d in documents if d.get('document_type') == DocumentType.INVOICE.value]),
            "flags": {"critical": [], "warnings": [], "info": []}
        }
        
        logger.info(f"Extracted {len(all_line_items)} line items from invoices/statements")
        
        # Get addendum text and lease text for line item analysis
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
        
        # Analyze all line items in batch with Gemini
        line_items_with_flags = []
        json_validation_failed_count = 0
        if invoice_data.get("line_items"):
            logger.info(f"Batch analyzing {len(invoice_data['line_items'])} line items with Gemini 2.5 Pro...")
            line_items_with_flags = self.document_analyzer.analyze_line_items_batch(
                invoice_data["line_items"],
                addendum_text,
                claim_context
            )
            
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
            
            # Calculate eligible_total from line_items_with_flags (only count once!)
            raw_eligible_total = sum(Decimal(str(item.get('amount', 0))) for item in line_items_with_flags if item.get('should_be_included', False))
            
            # Sanity check: eligible_total should not exceed invoice_total by more than 50%
            # This catches data corruption (e.g., Claim 901 with billions)
            if raw_eligible_total > invoice_total * Decimal("1.5") and invoice_total > 0:
                logger.warning(f"Eligible total ${raw_eligible_total} exceeds invoice_total ${invoice_total} by >50%, applying sanity cap")
                eligible_total = invoice_total * Decimal("1.5")
                invoice_data["flags"]["warnings"].append(f"eligible_total_sanity_check_applied: capped to ${eligible_total}")
            else:
                eligible_total = raw_eligible_total
            
            # Build approved/ineligible item lists (don't recalculate eligible_total here!)
            for item in line_items_with_flags:
                amount = Decimal(str(item.get('amount', 0)))
                should_include = item.get('should_be_included', False)
                
                # Create item dict with analysis (preserve all deterministic rule info)
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
                        'is_covered_by_addendum': item.get('is_covered_by_addendum', False),
                        'confidence': item.get('analysis_confidence', item.get('llm_confidence', 0.5)),
                        'reasoning': item.get('analysis_reasoning', item.get('llm_reasoning', '')),
                        'addendum_reference': item.get('addendum_reference', item.get('llm_addendum_reference', 'N/A'))
                    },
                    # Preserve deterministic rule information for logging and future rule improvement
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
                    # DON'T add to eligible_total here - already calculated above!
                else:
                    ineligible_items.append(item_with_analysis)
            
            # Update eligibility_result with recalculated values
            eligibility_result["approved_items"] = approved_items
            eligibility_result["ineligible_items"] = ineligible_items
            eligibility_result["eligible_total"] = eligible_total
                    
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
        
        claim_amount = Decimal(str(claim.get("claim_amount", 0)))
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

