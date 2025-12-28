import logging
import re
import time
from decimal import Decimal
from typing import List, Optional, Dict
from decision_service.engine.invoice_models import (
    LineItem, InvoiceParseResult, InvoiceMetadata, ParsingQualityMetrics,
    LineItemConfidence, TableStructure
)
from decision_service.engine.amount_extractor import AmountExtractor
from decision_service.engine.table_detector import TableDetector
from decision_service.engine.reconciliation import ReconciliationEngine

logger = logging.getLogger(__name__)


class InvoiceParseException(Exception):
    pass


class AdvancedInvoiceParser:
    def __init__(self):
        self.amount_extractor = AmountExtractor()
        self.table_detector = TableDetector()
        self.reconciliation_engine = ReconciliationEngine()
    
    def parse_invoice(
        self,
        extracted_text: str,
        document_id: Optional[int] = None,
        claim_context: Optional[Dict] = None
    ) -> InvoiceParseResult:
        start_time = time.time()
        
        try:
            structure = self._pass1_structure_detection(extracted_text)
            line_items = self._pass2_line_item_extraction(extracted_text, structure)
            line_items = self._pass3_amount_parsing(line_items)
            reconciliation = self._pass4_total_reconciliation(extracted_text, line_items)
            result = self._pass5_validation_quality_checks(
                extracted_text, line_items, reconciliation, start_time
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Invoice parsing failed: {e}", exc_info=True)
            return self._fallback_parse(extracted_text, start_time, str(e))
    
    def _pass1_structure_detection(self, text: str) -> TableStructure:
        structure = self.table_detector.detect_structure(text)
        logger.debug(f"Structure detected: header={structure.header_row_index}, "
                    f"footer={structure.footer_start_index}, "
                    f"amount_col={structure.amount_column_position}")
        return structure
    
    def _pass2_line_item_extraction(
        self,
        text: str,
        structure: TableStructure
    ) -> List[LineItem]:
        line_items = []
        
        if structure.detected_table:
            table_rows = self.table_detector.extract_table_rows(structure)
            idx = 0
            
            while idx < len(table_rows):
                row = table_rows[idx]
                desc, amount_text = self.table_detector.split_line_into_columns(
                    row, structure
                )
                
                if not desc and not amount_text:
                    idx += 1
                    continue
                
                if not amount_text:
                    merged_desc, next_idx = self.table_detector.merge_multiline_description(
                        table_rows, idx, structure.amount_column_position
                    )
                    if next_idx < len(table_rows):
                        _, amount_text = self.table_detector.split_line_into_columns(
                            table_rows[next_idx], structure
                        )
                    desc = merged_desc
                    idx = next_idx
                
                if desc or amount_text:
                    line_items.append(LineItem(
                        description=desc or "Unknown charge",
                        amount=Decimal("0"),
                        line_number=idx + 1,
                        confidence=LineItemConfidence.MEDIUM,
                        ambiguity_score=50.0,
                        notes=[],
                        original_text=row
                    ))
                
                idx += 1
        else:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            for i, line in enumerate(lines):
                if self._looks_like_line_item(line):
                    line_items.append(LineItem(
                        description=line,
                        amount=Decimal("0"),
                        line_number=i + 1,
                        confidence=LineItemConfidence.LOW,
                        ambiguity_score=70.0,
                        notes=["No table structure detected"],
                        original_text=line
                    ))
        
        return line_items
    
    def _pass3_amount_parsing(self, line_items: List[LineItem]) -> List[LineItem]:
        parsed_items = []
        
        for item in line_items:
            amount_result = self.amount_extractor.parse_amount(item.original_text)
            
            if amount_result:
                item.amount = amount_result.amount
                item.is_credit = amount_result.is_negative
                item.notes.append(f"Parsed via {amount_result.parse_method}")
                
                if amount_result.confidence >= 0.8:
                    item.confidence = LineItemConfidence.HIGH
                elif amount_result.confidence >= 0.5:
                    item.confidence = LineItemConfidence.MEDIUM
                else:
                    item.confidence = LineItemConfidence.LOW
            else:
                amount_result = self.amount_extractor.parse_amount(item.description)
                if amount_result:
                    item.amount = amount_result.amount
                    item.is_credit = amount_result.is_negative
                    item.notes.append("Amount found in description")
                else:
                    item.notes.append("Amount not found - manual review needed")
            
            item.ambiguity_score = self._calculate_ambiguity_score(item)
            
            if self.table_detector.is_tax_line(item.description):
                item.is_tax = True
                item.notes.append("Identified as tax")
            
            if self.table_detector.is_fee_line(item.description):
                item.is_fee = True
                item.notes.append("Identified as fee")
            
            parsed_items.append(item)
        
        return parsed_items
    
    def _pass4_total_reconciliation(
        self,
        text: str,
        line_items: List[LineItem]
    ) -> tuple:
        stated_total = self._extract_stated_total(text)
        
        credits = [item for item in line_items if item.is_credit]
        taxes = [item for item in line_items if item.is_tax]
        fees = [item for item in line_items if item.is_fee]
        regular_items = [
            item for item in line_items
            if not item.is_credit and not item.is_tax and not item.is_fee
        ]
        
        reconciliation = self.reconciliation_engine.reconcile_totals(
            regular_items, stated_total, credits, taxes, fees
        )
        
        return reconciliation, stated_total, credits, taxes, fees, regular_items
    
    def _pass5_validation_quality_checks(
        self,
        text: str,
        line_items: List[LineItem],
        reconciliation_data: tuple,
        start_time: float
    ) -> InvoiceParseResult:
        reconciliation, stated_total, credits, taxes, fees, regular_items = reconciliation_data
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        flags = []
        manual_review_reasons = []
        requires_manual_review = False
        
        if not line_items:
            flags.append("No line items found")
            manual_review_reasons.append("No line items could be extracted from invoice")
            requires_manual_review = True
        
        duplicates = self.reconciliation_engine.detect_duplicate_items(line_items)
        if duplicates:
            flags.append(f"Found {len(duplicates)} potential duplicate items")
            manual_review_reasons.append("Duplicate line items detected")
        
        calculated_total = sum(item.amount for item in line_items)
        suspicious = self.reconciliation_engine.detect_suspicious_items(
            line_items, calculated_total if calculated_total > 0 else Decimal("1")
        )
        if suspicious:
            flags.append(f"Found {len(suspicious)} suspicious items")
            for item in suspicious:
                if item.amount > Decimal("10000"):
                    manual_review_reasons.append(f"Item exceeds $10,000: {item.description}")
                elif not item.description or len(item.description.strip()) < 3:
                    manual_review_reasons.append("Item has missing or very short description")
        
        if not reconciliation.success:
            flags.append("Reconciliation failed")
            manual_review_reasons.append(f"Total mismatch: ${reconciliation.difference}")
            requires_manual_review = True
        
        ambiguous_items = [item for item in line_items if item.ambiguity_score >= 70]
        items_ambiguous = len(ambiguous_items)
        avg_ambiguity = sum(item.ambiguity_score for item in line_items) / len(line_items) if line_items else 100.0
        
        if avg_ambiguity > 60:
            requires_manual_review = True
            manual_review_reasons.append("High average ambiguity score")
        
        overall_confidence = max(0, 100 - avg_ambiguity)
        
        metadata = self._extract_metadata(text)
        
        quality_metrics = ParsingQualityMetrics(
            overall_confidence=overall_confidence,
            items_parsed=len(line_items),
            items_ambiguous=items_ambiguous,
            avg_ambiguity_score=avg_ambiguity,
            reconciliation_success=reconciliation.success,
            processing_time_ms=processing_time_ms
        )
        
        # Calculate total: regular items + taxes + fees - credits
        # Credits are stored as negative amounts (from amount_extractor), so we sum all items
        # This ensures correct math: if credit is -$50, it's already negative in the amount
        all_items_for_total = regular_items + taxes + fees + credits
        calculated_total = sum(item.amount for item in all_items_for_total)
        
        return InvoiceParseResult(
            line_items=regular_items,
            invoice_total_stated=stated_total,
            invoice_total_calculated=calculated_total,
            reconciliation_difference=reconciliation.difference,
            credits=credits,
            taxes=taxes,
            fees=fees,
            metadata=metadata,
            quality_metrics=quality_metrics,
            flags=flags,
            requires_manual_review=requires_manual_review,
            manual_review_reasons=manual_review_reasons
        )
    
    def _extract_stated_total(self, text: str) -> Optional[Decimal]:
        lines = text.split('\n')
        footer_keywords = ["total", "amount due", "balance", "grand total"]
        
        for line in reversed(lines):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in footer_keywords):
                amount_result = self.amount_extractor.parse_amount(line)
                if amount_result and amount_result.confidence > 0.7:
                    return abs(amount_result.amount)
        
        return None
    
    def _extract_metadata(self, text: str) -> InvoiceMetadata:
        metadata = InvoiceMetadata()
        
        invoice_num_match = re.search(r'invoice\s*#?\s*:?\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
        if invoice_num_match:
            metadata.invoice_number = invoice_num_match.group(1).strip()
        
        date_patterns = [
            r'date\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            r'invoice\s+date\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata.invoice_date = match.group(1).strip()
                break
        
        due_date_patterns = [
            r'due\s+date\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            r'payment\s+due\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        ]
        for pattern in due_date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata.due_date = match.group(1).strip()
                break
        
        return metadata
    
    def _calculate_ambiguity_score(self, item: LineItem) -> float:
        score = 0.0
        
        if not item.description or len(item.description.strip()) < 3:
            score += 40
        elif len(item.description.strip()) < 10:
            score += 20
        
        if item.amount == 0:
            score += 50
        elif item.confidence == LineItemConfidence.LOW:
            score += 30
        elif item.confidence == LineItemConfidence.MEDIUM:
            score += 15
        
        if "unknown" in item.description.lower():
            score += 30
        
        if any(note.startswith("Amount not found") for note in item.notes):
            score += 40
        
        return min(100.0, score)
    
    def _looks_like_line_item(self, line: str) -> bool:
        if not line or len(line.strip()) < 5:
            return False
        
        has_amount = bool(re.search(r'\$?\s*[\d,]+\.?\d*', line))
        has_text = len([c for c in line if c.isalpha()]) > 3
        
        return has_amount and has_text
    
    def _fallback_parse(
        self,
        text: str,
        start_time: float,
        error_message: str
    ) -> InvoiceParseResult:
        logger.warning(f"Using fallback parsing due to: {error_message}")
        
        amounts = self.amount_extractor.extract_all_amounts(text)
        line_items = []
        
        for i, amount_result in enumerate(amounts[:50]):
            if amount_result.confidence > 0.5:
                line_items.append(LineItem(
                    description=f"Unknown charge {i+1}",
                    amount=amount_result.amount,
                    line_number=i + 1,
                    confidence=LineItemConfidence.LOW,
                    ambiguity_score=90.0,
                    notes=["Fallback parsing", error_message],
                    original_text=amount_result.original_text
                ))
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        total = sum(item.amount for item in line_items)
        
        return InvoiceParseResult(
            line_items=line_items,
            invoice_total_stated=None,
            invoice_total_calculated=total,
            reconciliation_difference=Decimal("0"),
            credits=[],
            taxes=[],
            fees=[],
            metadata=InvoiceMetadata(),
            quality_metrics=ParsingQualityMetrics(
                overall_confidence=20.0,
                items_parsed=len(line_items),
                items_ambiguous=len(line_items),
                avg_ambiguity_score=90.0,
                reconciliation_success=False,
                processing_time_ms=processing_time_ms
            ),
            flags=["Fallback parsing used", error_message],
            requires_manual_review=True,
            manual_review_reasons=["Primary parsing failed", error_message]
        )

