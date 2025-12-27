"""PII Detection and Redaction Service."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class PIIType(str, Enum):
    """PII type enumeration."""
    
    NAME = "name"
    SSN = "ssn"
    PHONE = "phone"
    EMAIL = "email"
    BANK_ACCOUNT = "bank_account"
    CREDIT_CARD = "credit_card"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    DRIVER_LICENSE = "driver_license"


@dataclass
class PIIDetection:
    """PII detection result."""
    
    pii_type: PIIType
    start_pos: int
    end_pos: int
    value: str
    confidence: float
    detection_method: str


class PIIDetector:
    """PII detection service using pattern matching and ML models."""
    
    def __init__(self, use_ml_model: bool = False):
        """Initialize PII detector."""
        self.use_ml_model = use_ml_model
        self._ml_model = None
        
        if use_ml_model:
            self._load_ml_model()
    
    def _load_ml_model(self) -> None:
        """Load ML model for PII detection."""
        try:
            import spacy
            self._ml_model = spacy.load("en_core_web_lg")
            logger.info("ML model loaded for PII detection")
        except ImportError:
            logger.warning("spaCy not available, using pattern-based detection only")
            self.use_ml_model = False
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            self.use_ml_model = False
    
    def detect(self, text: str) -> List[PIIDetection]:
        """
        Detect PII in text.
        
        Args:
            text: Text to analyze
        
        Returns:
            List of PII detections
        """
        detections = []
        
        detections.extend(self._detect_patterns(text))
        
        if self.use_ml_model and self._ml_model:
            detections.extend(self._detect_with_ml(text))
        
        detections = self._deduplicate_detections(detections)
        
        return sorted(detections, key=lambda x: x.start_pos)
    
    def _detect_patterns(self, text: str) -> List[PIIDetection]:
        """Detect PII using regex patterns."""
        detections = []
        
        ssn_pattern = r'\b\d{3}-?\d{2}-?\d{4}\b'
        for match in re.finditer(ssn_pattern, text):
            if self._is_valid_ssn(match.group()):
                detections.append(PIIDetection(
                    pii_type=PIIType.SSN,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    value=match.group(),
                    confidence=0.95,
                    detection_method="pattern"
                ))
        
        phone_pattern = r'\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b'
        for match in re.finditer(phone_pattern, text):
            detections.append(PIIDetection(
                pii_type=PIIType.PHONE,
                start_pos=match.start(),
                end_pos=match.end(),
                value=match.group(),
                confidence=0.90,
                detection_method="pattern"
            ))
        
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, text):
            detections.append(PIIDetection(
                pii_type=PIIType.EMAIL,
                start_pos=match.start(),
                end_pos=match.end(),
                value=match.group(),
                confidence=0.95,
                detection_method="pattern"
            ))
        
        credit_card_pattern = r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
        for match in re.finditer(credit_card_pattern, text):
            card_number = re.sub(r'[-\s]', '', match.group())
            if self._is_valid_credit_card(card_number):
                detections.append(PIIDetection(
                    pii_type=PIIType.CREDIT_CARD,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    value=match.group(),
                    confidence=0.90,
                    detection_method="pattern"
                ))
        
        bank_account_pattern = r'\b\d{8,17}\b'
        for match in re.finditer(bank_account_pattern, text):
            if self._looks_like_bank_account(match.group()):
                detections.append(PIIDetection(
                    pii_type=PIIType.BANK_ACCOUNT,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    value=match.group(),
                    confidence=0.70,
                    detection_method="pattern"
                ))
        
        return detections
    
    def _detect_with_ml(self, text: str) -> List[PIIDetection]:
        """Detect PII using ML model."""
        detections = []
        
        if not self._ml_model:
            return detections
        
        doc = self._ml_model(text)
        
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG"]:
                detections.append(PIIDetection(
                    pii_type=PIIType.NAME,
                    start_pos=ent.start_char,
                    end_pos=ent.end_char,
                    value=ent.text,
                    confidence=ent.score if hasattr(ent, 'score') else 0.85,
                    detection_method="model"
                ))
        
        return detections
    
    def _is_valid_ssn(self, ssn: str) -> bool:
        """Validate SSN format."""
        ssn_clean = re.sub(r'[-\s]', '', ssn)
        if len(ssn_clean) != 9:
            return False
        if ssn_clean.startswith('000') or ssn_clean.startswith('666'):
            return False
        if ssn_clean[3:5] == '00' or ssn_clean[5:] == '0000':
            return False
        return True
    
    def _is_valid_credit_card(self, card_number: str) -> bool:
        """Validate credit card using Luhn algorithm."""
        def luhn_check(card_num):
            def digits_of(n):
                return [int(d) for d in str(n)]
            digits = digits_of(card_num)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d * 2))
            return checksum % 10 == 0
        
        if len(card_number) < 13 or len(card_number) > 19:
            return False
        return luhn_check(card_number)
    
    def _looks_like_bank_account(self, text: str) -> bool:
        """Heuristic to identify bank account numbers."""
        if len(text) < 8 or len(text) > 17:
            return False
        if re.match(r'^0+$', text):
            return False
        return True
    
    def _deduplicate_detections(self, detections: List[PIIDetection]) -> List[PIIDetection]:
        """Remove overlapping detections, keeping highest confidence."""
        if not detections:
            return []
        
        sorted_detections = sorted(detections, key=lambda x: (x.start_pos, -x.confidence))
        result = []
        
        for detection in sorted_detections:
            overlaps = False
            for existing in result:
                if (detection.start_pos < existing.end_pos and 
                    detection.end_pos > existing.start_pos):
                    overlaps = True
                    if detection.confidence > existing.confidence:
                        result.remove(existing)
                        result.append(detection)
                    break
            
            if not overlaps:
                result.append(detection)
        
        return sorted(result, key=lambda x: x.start_pos)


class PIIRedactor:
    """PII redaction service."""
    
    REDACTION_MODES = {
        "REDACT": "[REDACTED]",
        "TAG": "[PII_TYPE: REDACTED]",
        "MASK": "***",
        "NONE": None,
    }
    
    def __init__(self, mode: str = "REDACT"):
        """Initialize redactor."""
        self.mode = mode.upper()
        if self.mode not in self.REDACTION_MODES:
            raise ValueError(f"Invalid redaction mode: {mode}")
    
    def redact(self, text: str, detections: List[PIIDetection]) -> Tuple[str, bool]:
        """
        Redact PII from text.
        
        Args:
            text: Original text
            detections: List of PII detections
        
        Returns:
            Tuple of (redacted_text, redaction_applied)
        """
        if not detections or self.mode == "NONE":
            return text, False
        
        if self.mode == "TAG":
            redacted = self._redact_with_tags(text, detections)
        elif self.mode == "MASK":
            redacted = self._redact_with_mask(text, detections)
        else:
            redacted = self._redact_standard(text, detections)
        
        return redacted, True
    
    def _redact_standard(self, text: str, detections: List[PIIDetection]) -> str:
        """Standard redaction: replace with [REDACTED]."""
        result = text
        offset = 0
        
        for detection in sorted(detections, key=lambda x: x.start_pos):
            start = detection.start_pos + offset
            end = detection.end_pos + offset
            replacement = self.REDACTION_MODES["REDACT"]
            result = result[:start] + replacement + result[end:]
            offset += len(replacement) - (end - start)
        
        return result
    
    def _redact_with_tags(self, text: str, detections: List[PIIDetection]) -> str:
        """Redact with PII type tags."""
        result = text
        offset = 0
        
        for detection in sorted(detections, key=lambda x: x.start_pos):
            start = detection.start_pos + offset
            end = detection.end_pos + offset
            replacement = f"[{detection.pii_type.value.upper()}: REDACTED]"
            result = result[:start] + replacement + result[end:]
            offset += len(replacement) - (end - start)
        
        return result
    
    def _redact_with_mask(self, text: str, detections: List[PIIDetection]) -> str:
        """Redact with mask preserving length."""
        result = text
        offset = 0
        
        for detection in sorted(detections, key=lambda x: x.start_pos):
            start = detection.start_pos + offset
            end = detection.end_pos + offset
            length = end - start
            replacement = "*" * min(length, 20)
            result = result[:start] + replacement + result[end:]
            offset += len(replacement) - (end - start)
        
        return result

