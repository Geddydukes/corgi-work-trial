import logging
from decimal import Decimal
from typing import Dict, List

from decision_service.engine.invoice_parser_advanced import AdvancedInvoiceParser

logger = logging.getLogger(__name__)


class InvoiceParser:
    def __init__(self):
        self.advanced_parser = AdvancedInvoiceParser()
    
    async def parse_documents(
        self,
        documents: List[dict]
    ) -> dict:
        from shared.models import DocumentType
        
        # First, try to find explicitly classified invoices
        invoice_docs = [
            doc for doc in documents 
            if doc.get("document_type") == DocumentType.INVOICE.value
        ]
        
        # If no invoices found, try to find documents that might be invoices
        # (e.g., SDI, Move Out Statement, Ledger, etc.)
        if not invoice_docs:
            logger.info("No explicitly classified invoices found, checking other documents...")
            # Look for documents with invoice-like content
            # Include "move-out-statement", "move out statement", etc. as invoice indicators
            invoice_keywords = [
                'invoice', 'statement', 'ledger', 'sdi', 'charge', 'total', 'amount due', 'balance',
                'move-out-statement', 'move out statement', 'move-out statement', 'moveout statement',
                'move-out-stmt', 'move out stmt', 'move-out stmt'
            ]
            for doc in documents:
                text = doc.get("extracted_text", "").lower()
                filename = doc.get("original_filename", "").lower()
                # Check if document might be an invoice
                # Prioritize filename patterns for move-out statements
                is_move_out_statement = any(pattern in filename for pattern in [
                    'move-out-statement', 'move out statement', 'move-out statement', 
                    'moveout statement', 'move-out-stmt', 'move out stmt'
                ])
                has_invoice_keyword = any(keyword in text or keyword in filename for keyword in invoice_keywords)
                if is_move_out_statement or has_invoice_keyword:
                    if doc.get("document_type") != DocumentType.ADDENDUM.value:  # Don't treat addendums as invoices
                        invoice_docs.append(doc)
                        logger.info(f"Treating document '{doc.get('original_filename')}' as potential invoice")
        
        if not invoice_docs:
            logger.warning("No invoice documents found")
            return {
                "line_items": [],
                "total_amount": Decimal("0"),
                "document_count": 0
            }
        
        all_line_items = []
        all_parse_results = []
        all_flags = {"critical": [], "warnings": [], "info": []}
        
        for doc in invoice_docs:
            text = doc.get("extracted_text", "")
            if not text:
                logger.warning(f"Document {doc.get('id')} has no extracted text")
                continue
            
            parse_result = self.advanced_parser.parse_invoice(
                extracted_text=text,
                document_id=doc.get("id"),
                claim_context={}
            )
            
            all_parse_results.append(parse_result)
            
            legacy_format = parse_result.to_legacy_format()
            all_line_items.extend(legacy_format["line_items"])
            
            if parse_result.flags:
                for flag in parse_result.flags:
                    if "Reconciliation failed" in flag or "mismatch" in flag.lower():
                        all_flags["critical"].append(flag)
                    elif "duplicate" in flag.lower() or "suspicious" in flag.lower():
                        all_flags["warnings"].append(flag)
                    else:
                        all_flags["info"].append(flag)
            
            if not parse_result.quality_metrics.reconciliation_success:
                diff = abs(parse_result.reconciliation_difference)
                if diff > Decimal("0.05") * (parse_result.invoice_total_stated or parse_result.invoice_total_calculated):
                    all_flags["critical"].append(
                        f"invoice_total_mismatch: ${diff} difference (>{5}% threshold)"
                    )
                else:
                    all_flags["warnings"].append(
                        f"invoice_total_mismatch: ${diff} difference"
                    )
        
        total_amount = sum(
            Decimal(str(item["amount"])) for item in all_line_items
        )
        
        result = {
            "line_items": all_line_items,
            "total_amount": total_amount,
            "document_count": len(invoice_docs),
            "parse_results": [pr.to_dict() for pr in all_parse_results]
        }
        
        if any(all_flags.values()):
            result["flags"] = all_flags
        
        return result

