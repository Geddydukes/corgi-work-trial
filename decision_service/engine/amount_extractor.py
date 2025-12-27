import re
from decimal import Decimal, InvalidOperation
from typing import Tuple, Optional, List
from decision_service.engine.invoice_models import AmountParseResult


class AmountExtractor:
    AMOUNT_PATTERNS = [
        (r'\$\s*([\d,]+\.\d{2})\b', 1.0, "standard_dollar"),
        (r'\(\$\s*([\d,]+\.\d{2})\)', 0.95, "negative_parentheses"),
        (r'-\s*\$?\s*([\d,]+\.\d{2})\b', 0.95, "negative_minus"),
        (r'\$\s*([\d,]+)\b(?!\.)', 0.85, "dollar_no_cents"),
        (r'([\d,]+\.\d{2})\s*(?:USD|usd|\$)', 0.9, "amount_with_currency"),
        (r'([\d,]+\.\d{2})\b(?!%)', 0.8, "decimal_amount"),
        (r'([\d,]+)\b(?!\.\d)(?!%)', 0.7, "integer_amount"),
        (r'([\d,]+\.\d{1})\b', 0.75, "single_decimal"),
    ]
    
    PERCENTAGE_PATTERN = r'(\d+(?:\.\d+)?)\s*%'
    RANGE_PATTERN = r'\$?\s*([\d,]+\.?\d*)\s*[-–—]\s*\$?\s*([\d,]+\.?\d*)'
    FORMULA_PATTERN = r'(\d+(?:\.\d+)?)\s*[×xX*]\s*\$?\s*([\d,]+\.?\d*)'
    EURO_PATTERN = r'([\d.,]+)\s*€'
    TBD_PATTERNS = [
        r'\bTBD\b',
        r'\bPending\b',
        r'\bTBA\b',
        r'\bTo\s+be\s+determined\b',
        r'\bN/A\b',
    ]
    
    def parse_amount(self, text: str, base_amount: Optional[Decimal] = None) -> Optional[AmountParseResult]:
        text = text.strip()
        
        if not text:
            return None
        
        if self._is_tbd(text):
            return AmountParseResult(
                amount=Decimal("0"),
                confidence=0.0,
                is_negative=False,
                original_text=text,
                parse_method="tbd_flag"
            )
        
        result = self._try_percentage(text, base_amount)
        if result:
            return result
        
        result = self._try_range(text)
        if result:
            return result
        
        result = self._try_formula(text)
        if result:
            return result
        
        result = self._try_euro(text)
        if result:
            return result
        
        result = self._try_standard_patterns(text)
        if result:
            return result
        
        return None
    
    def _is_tbd(self, text: str) -> bool:
        text_upper = text.upper()
        for pattern in self.TBD_PATTERNS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                return True
        return False
    
    def _try_percentage(self, text: str, base_amount: Optional[Decimal]) -> Optional[AmountParseResult]:
        if base_amount is None:
            return None
        
        match = re.search(self.PERCENTAGE_PATTERN, text)
        if match:
            try:
                percentage = Decimal(match.group(1))
                amount = base_amount * (percentage / Decimal("100"))
                return AmountParseResult(
                    amount=amount,
                    confidence=0.85,
                    is_negative=False,
                    original_text=text,
                    parse_method="percentage_calculation"
                )
            except (InvalidOperation, ValueError):
                pass
        return None
    
    def _try_range(self, text: str) -> Optional[AmountParseResult]:
        match = re.search(self.RANGE_PATTERN, text)
        if match:
            try:
                low = self._parse_numeric(match.group(1))
                high = self._parse_numeric(match.group(2))
                if low and high and low <= high:
                    midpoint = (low + high) / Decimal("2")
                    return AmountParseResult(
                        amount=midpoint,
                        confidence=0.75,
                        is_negative=False,
                        original_text=text,
                        parse_method="range_midpoint"
                    )
            except (InvalidOperation, ValueError):
                pass
        return None
    
    def _try_formula(self, text: str) -> Optional[AmountParseResult]:
        match = re.search(self.FORMULA_PATTERN, text)
        if match:
            try:
                quantity = Decimal(match.group(1))
                unit_price = self._parse_numeric(match.group(2))
                if unit_price:
                    amount = quantity * unit_price
                    return AmountParseResult(
                        amount=amount,
                        confidence=0.9,
                        is_negative=False,
                        original_text=text,
                        parse_method="formula_calculation"
                    )
            except (InvalidOperation, ValueError):
                pass
        return None
    
    def _try_euro(self, text: str) -> Optional[AmountParseResult]:
        match = re.search(self.EURO_PATTERN, text)
        if match:
            try:
                euro_amount = match.group(1).replace('.', '').replace(',', '.')
                amount = Decimal(euro_amount)
                usd_amount = amount * Decimal("1.10")
                return AmountParseResult(
                    amount=usd_amount,
                    confidence=0.7,
                    is_negative=False,
                    original_text=text,
                    parse_method="euro_conversion"
                )
            except (InvalidOperation, ValueError):
                pass
        return None
    
    def _try_standard_patterns(self, text: str) -> Optional[AmountParseResult]:
        best_result = None
        best_confidence = 0.0
        
        for pattern, confidence, method in self.AMOUNT_PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    amount_str = match.group(1).replace(',', '')
                    amount = Decimal(amount_str)
                    
                    is_negative = (
                        '(' in text or
                        text.strip().startswith('-') or
                        method == "negative_parentheses" or
                        method == "negative_minus"
                    )
                    
                    if is_negative:
                        amount = -amount
                    
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_result = AmountParseResult(
                            amount=amount,
                            confidence=confidence,
                            is_negative=is_negative,
                            original_text=text,
                            parse_method=method
                        )
                except (InvalidOperation, ValueError):
                    continue
        
        return best_result
    
    def _parse_numeric(self, text: str) -> Optional[Decimal]:
        try:
            cleaned = text.replace(',', '').replace('$', '').strip()
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
    
    def extract_all_amounts(self, text: str) -> List[AmountParseResult]:
        results = []
        lines = text.split('\n')
        
        for line in lines:
            result = self.parse_amount(line)
            if result and result.confidence > 0.5:
                results.append(result)
        
        return results
    
    def validate_amount(self, amount: Decimal) -> Tuple[bool, Optional[str]]:
        if amount == 0:
            return False, "Amount is zero"
        
        abs_amount = abs(amount)
        if abs_amount > Decimal("10000"):
            return False, f"Amount exceeds maximum: ${abs_amount}"
        
        if abs_amount < Decimal("0.01"):
            return False, f"Amount below minimum: ${abs_amount}"
        
        return True, None

