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
        
        invoice_docs = [
            doc for doc in documents 
            if doc.get("document_type") == DocumentType.INVOICE.value
        ]
        
        if not invoice_docs:
            logger.warning("No invoice documents found")
            return {
                "line_items": [],
                "total_amount": Decimal("0"),
                "document_count": 0
            }
        
        all_line_items = []
        all_parse_results = []
        
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
        
        total_amount = sum(
            Decimal(str(item["amount"])) for item in all_line_items
        )
        
        return {
            "line_items": all_line_items,
            "total_amount": total_amount,
            "document_count": len(invoice_docs),
            "parse_results": [pr.to_dict() for pr in all_parse_results]
        }

