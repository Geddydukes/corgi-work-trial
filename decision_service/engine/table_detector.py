import re
from typing import List, Optional, Tuple
from decision_service.engine.invoice_models import TableStructure


class TableDetector:
    HEADER_KEYWORDS = [
        "description", "item", "charge", "amount", "price", "cost",
        "service", "fee", "line", "detail", "particulars"
    ]
    
    FOOTER_KEYWORDS = [
        "total", "subtotal", "sum", "balance", "amount due", "due",
        "grand total", "invoice total", "final total", "payable",
        "previous balance", "payment", "credit", "adjustment"
    ]
    
    TAX_KEYWORDS = [
        "tax", "gst", "vat", "sales tax", "use tax", "hst"
    ]
    
    FEE_KEYWORDS = [
        "fee", "processing", "service charge", "convenience",
        "late fee", "administrative"
    ]
    
    def detect_structure(self, text: str) -> TableStructure:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            return TableStructure()
        
        header_idx = self._find_header_row(lines)
        footer_idx = self._find_footer_row(lines)
        amount_col_pos = self._detect_amount_column(lines, header_idx, footer_idx)
        desc_col_bounds = self._detect_description_column(lines, header_idx, footer_idx, amount_col_pos)
        
        detected = (
            header_idx is not None or
            footer_idx is not None or
            amount_col_pos is not None
        )
        
        return TableStructure(
            header_row_index=header_idx,
            footer_start_index=footer_idx,
            amount_column_position=amount_col_pos,
            description_column_start=desc_col_bounds[0] if desc_col_bounds else None,
            description_column_end=desc_col_bounds[1] if desc_col_bounds else None,
            rows=lines,
            detected_table=detected
        )
    
    def _find_header_row(self, lines: List[str]) -> Optional[int]:
        for i, line in enumerate(lines[:20]):
            line_lower = line.lower()
            keyword_count = sum(1 for keyword in self.HEADER_KEYWORDS if keyword in line_lower)
            
            if keyword_count >= 2:
                return i
            
            if keyword_count == 1 and ('$' in line or re.search(r'\d+', line)):
                return i
        
        return None
    
    def _find_footer_row(self, lines: List[str]) -> Optional[int]:
        for i in range(len(lines) - 1, max(0, len(lines) - 30), -1):
            line_lower = lines[i].lower()
            keyword_count = sum(1 for keyword in self.FOOTER_KEYWORDS if keyword in line_lower)
            
            if keyword_count >= 1:
                if '$' in lines[i] or re.search(r'\d+\.\d{2}', lines[i]):
                    return i
        
        return None
    
    def _detect_amount_column(self, lines: List[str], header_idx: Optional[int], footer_idx: Optional[int]) -> Optional[int]:
        start = header_idx if header_idx is not None else 0
        end = footer_idx if footer_idx is not None else len(lines)
        sample_lines = lines[start:min(start + 20, end)]
        
        if not sample_lines:
            return None
        
        dollar_positions = []
        for line in sample_lines:
            matches = list(re.finditer(r'\$?\s*[\d,]+\.\d{2}', line))
            for match in matches:
                dollar_positions.append(match.start())
        
        if not dollar_positions:
            return None
        
        position_counts = {}
        for pos in dollar_positions:
            rounded_pos = (pos // 10) * 10
            position_counts[rounded_pos] = position_counts.get(rounded_pos, 0) + 1
        
        if position_counts:
            most_common_pos = max(position_counts.items(), key=lambda x: x[1])
            if most_common_pos[1] >= 3:
                return most_common_pos[0]
        
        return max(dollar_positions) if dollar_positions else None
    
    def _detect_description_column(self, lines: List[str], header_idx: Optional[int], footer_idx: Optional[int], amount_col_pos: Optional[int]) -> Optional[Tuple[int, int]]:
        if amount_col_pos is None:
            return None
        
        start = header_idx if header_idx is not None else 0
        end = footer_idx if footer_idx is not None else len(lines)
        sample_lines = lines[start:min(start + 20, end)]
        
        if not sample_lines:
            return None
        
        desc_starts = []
        for line in sample_lines:
            if len(line) > amount_col_pos:
                desc_part = line[:amount_col_pos].rstrip()
                if desc_part:
                    desc_starts.append(len(line) - len(desc_part.lstrip()))
        
        if not desc_starts:
            return (0, amount_col_pos)
        
        avg_start = sum(desc_starts) // len(desc_starts)
        return (avg_start, amount_col_pos)
    
    def extract_table_rows(self, structure: TableStructure) -> List[str]:
        if not structure.rows:
            return []
        
        start = structure.header_row_index + 1 if structure.header_row_index is not None else 0
        end = structure.footer_start_index if structure.footer_start_index is not None else len(structure.rows)
        
        return structure.rows[start:end]
    
    def split_line_into_columns(self, line: str, structure: TableStructure) -> Tuple[str, Optional[str]]:
        if structure.amount_column_position is None:
            return line, None
        
        if len(line) <= structure.amount_column_position:
            return line, None
        
        description = line[:structure.amount_column_position].strip()
        amount_text = line[structure.amount_column_position:].strip()
        
        return description, amount_text
    
    def is_tax_line(self, text: str) -> bool:
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.TAX_KEYWORDS)
    
    def is_fee_line(self, text: str) -> bool:
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.FEE_KEYWORDS)
    
    def is_subtotal_line(self, text: str) -> bool:
        text_lower = text.lower()
        subtotal_keywords = ["subtotal", "sub-total", "sub total"]
        return any(keyword in text_lower for keyword in subtotal_keywords)
    
    def merge_multiline_description(self, lines: List[str], start_idx: int, amount_col_pos: Optional[int]) -> Tuple[str, int]:
        if start_idx >= len(lines):
            return "", start_idx
        
        merged = [lines[start_idx]]
        current_idx = start_idx + 1
        
        while current_idx < len(lines):
            line = lines[current_idx]
            
            if amount_col_pos and len(line) > amount_col_pos:
                potential_amount = line[amount_col_pos:].strip()
                if re.search(r'\$?\s*[\d,]+\.?\d*', potential_amount):
                    break
            
            if line.strip() and not line.strip().startswith(('•', '-', '*', '1.', '2.', '3.')):
                merged.append(line)
                current_idx += 1
            else:
                break
        
        return ' '.join(merged), current_idx


















