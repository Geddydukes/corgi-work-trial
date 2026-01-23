from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from datetime import datetime


class LineItemConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class LineItem:
    description: str
    amount: Decimal
    line_number: int
    confidence: LineItemConfidence
    ambiguity_score: float
    notes: List[str] = field(default_factory=list)
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    is_credit: bool = False
    is_tax: bool = False
    is_fee: bool = False
    original_text: str = ""
    
    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "amount": float(self.amount),
            "line_number": self.line_number,
            "confidence": self.confidence.value,
            "ambiguity_score": self.ambiguity_score,
            "notes": self.notes,
            "quantity": self.quantity,
            "unit_price": float(self.unit_price) if self.unit_price else None,
            "is_credit": self.is_credit,
            "is_tax": self.is_tax,
            "is_fee": self.is_fee,
            "original_text": self.original_text,
        }


@dataclass
class InvoiceMetadata:
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    vendor: Optional[str] = None
    property_address: Optional[str] = None
    tenant_name: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "due_date": self.due_date,
            "vendor": self.vendor,
            "property_address": self.property_address,
            "tenant_name": self.tenant_name,
        }


@dataclass
class ParsingQualityMetrics:
    overall_confidence: float
    items_parsed: int
    items_ambiguous: int
    avg_ambiguity_score: float
    reconciliation_success: bool
    processing_time_ms: int
    
    def to_dict(self) -> dict:
        return {
            "overall_confidence": self.overall_confidence,
            "items_parsed": self.items_parsed,
            "items_ambiguous": self.items_ambiguous,
            "avg_ambiguity_score": self.avg_ambiguity_score,
            "reconciliation_success": self.reconciliation_success,
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass
class InvoiceParseResult:
    line_items: List[LineItem]
    invoice_total_stated: Optional[Decimal]
    invoice_total_calculated: Decimal
    reconciliation_difference: Decimal
    credits: List[LineItem]
    taxes: List[LineItem]
    fees: List[LineItem]
    metadata: InvoiceMetadata
    quality_metrics: ParsingQualityMetrics
    flags: List[str]
    requires_manual_review: bool
    manual_review_reasons: List[str]
    
    def to_dict(self) -> dict:
        return {
            "line_items": [item.to_dict() for item in self.line_items],
            "invoice_total_stated": float(self.invoice_total_stated) if self.invoice_total_stated else None,
            "invoice_total_calculated": float(self.invoice_total_calculated),
            "reconciliation_difference": float(self.reconciliation_difference),
            "credits": [item.to_dict() for item in self.credits],
            "taxes": [item.to_dict() for item in self.taxes],
            "fees": [item.to_dict() for item in self.fees],
            "metadata": self.metadata.to_dict(),
            "quality_metrics": self.quality_metrics.to_dict(),
            "flags": self.flags,
            "requires_manual_review": self.requires_manual_review,
            "manual_review_reasons": self.manual_review_reasons,
        }
    
    def to_legacy_format(self) -> dict:
        return {
            "line_items": [
                {
                    "description": item.description,
                    "amount": float(item.amount),
                }
                for item in self.line_items
            ],
            "total_amount": self.invoice_total_stated or self.invoice_total_calculated,
            "document_count": 1,
        }


@dataclass
class TableStructure:
    header_row_index: Optional[int] = None
    footer_start_index: Optional[int] = None
    amount_column_position: Optional[int] = None
    description_column_start: Optional[int] = None
    description_column_end: Optional[int] = None
    rows: List[str] = field(default_factory=list)
    detected_table: bool = False


@dataclass
class AmountParseResult:
    amount: Decimal
    confidence: float
    is_negative: bool
    original_text: str
    parse_method: str


@dataclass
class ReconciliationResult:
    difference: Decimal
    success: bool
    missing_items_detected: bool
    negative_amounts_found: bool
    notes: List[str] = field(default_factory=list)


















