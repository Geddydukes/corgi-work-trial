from decimal import Decimal
from typing import List, Optional, Tuple
from decision_service.engine.invoice_models import LineItem, ReconciliationResult


class ReconciliationEngine:
    RECONCILIATION_TOLERANCE = Decimal("1.00")
    
    def reconcile_totals(
        self,
        line_items: List[LineItem],
        stated_total: Optional[Decimal],
        credits: List[LineItem],
        taxes: List[LineItem],
        fees: List[LineItem]
    ) -> ReconciliationResult:
        all_items = line_items + credits + taxes + fees
        calculated_total = sum(item.amount for item in all_items)
        
        if stated_total is None:
            return ReconciliationResult(
                difference=Decimal("0"),
                success=True,
                missing_items_detected=False,
                negative_amounts_found=any(item.amount < 0 for item in all_items),
                notes=["No stated total found, using calculated total"]
            )
        
        difference = abs(calculated_total - stated_total)
        success = difference <= self.RECONCILIATION_TOLERANCE
        
        notes = []
        if not success:
            notes.append(f"Reconciliation difference: ${difference}")
            if calculated_total < stated_total:
                notes.append("Calculated total is less than stated total - possible missing items")
            else:
                notes.append("Calculated total exceeds stated total - possible duplicate items or calculation error")
        
        negative_amounts = [item for item in all_items if item.amount < 0]
        if negative_amounts and not credits:
            notes.append(f"Found {len(negative_amounts)} negative amounts not classified as credits")
        
        missing_items_detected = (
            not success and
            calculated_total < stated_total and
            difference > self.RECONCILIATION_TOLERANCE
        )
        
        return ReconciliationResult(
            difference=difference,
            success=success,
            missing_items_detected=missing_items_detected,
            negative_amounts_found=len(negative_amounts) > 0,
            notes=notes
        )
    
    def detect_duplicate_items(self, line_items: List[LineItem]) -> List[Tuple[LineItem, LineItem]]:
        duplicates = []
        seen = {}
        
        for item in line_items:
            desc_key = item.description.lower().strip()
            if desc_key in seen:
                existing = seen[desc_key]
                if abs(existing.amount - item.amount) <= Decimal("0.01"):
                    duplicates.append((existing, item))
            else:
                seen[desc_key] = item
        
        return duplicates
    
    def detect_suspicious_items(self, line_items: List[LineItem], total: Decimal) -> List[LineItem]:
        suspicious = []
        
        for item in line_items:
            if item.amount <= 0:
                continue
            
            percentage = (item.amount / total * 100) if total > 0 else 0
            
            if percentage > 50:
                suspicious.append(item)
            elif item.amount > Decimal("10000"):
                suspicious.append(item)
            elif not item.description or len(item.description.strip()) < 3:
                suspicious.append(item)
        
        return suspicious
    
    def validate_reconciliation(
        self,
        result: ReconciliationResult,
        line_items: List[LineItem],
        stated_total: Optional[Decimal]
    ) -> Tuple[bool, List[str]]:
        errors = []
        
        if not line_items and stated_total and stated_total > 0:
            errors.append("No line items found but stated total is non-zero")
        
        if result.missing_items_detected:
            errors.append("Possible missing line items detected")
        
        if result.difference > Decimal("10.00"):
            errors.append(f"Large reconciliation difference: ${result.difference}")
        
        return len(errors) == 0, errors

