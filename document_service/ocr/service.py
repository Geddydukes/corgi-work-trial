"""Multi-tier OCR service with fallback chain."""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, List

import pdfplumber
import PyPDF2
from PIL import Image
from pypdf import PdfReader

from shared import config
from shared.models import (
    ExtractionAttempt,
    OCRTier,
    ProcessingError,
    ProcessingErrorType,
)

logger = logging.getLogger(__name__)


class OCRService:
    """Multi-tier OCR service with automatic fallback."""
    
    def __init__(self):
        """Initialize OCR service."""
        self._tesseract_available = self._check_tesseract()
        self._tier3_available = self._check_tier3_provider()
        self._tier3_provider = config.Config.TIER3_PROVIDER
    
    def _check_tesseract(self) -> bool:
        """Check if Tesseract is available."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            logger.warning("Tesseract not available")
            return False
    
    def _check_tier3_provider(self) -> bool:
        """Check if Tier 3 OCR provider is available."""
        provider = config.Config.TIER3_PROVIDER.lower()
        
        if provider == "gemini":
            try:
                if config.Config.GEMINI_API_KEY:
                    return True
            except Exception:
                pass
        
        elif provider == "mistral":
            try:
                if config.Config.MISTRAL_API_KEY:
                    return True
            except Exception:
                pass
        
        return False
    
    def extract_text(
        self,
        file_path: Path,
        is_native_pdf: bool = False,
        force_high_quality: bool = False,
    ) -> Tuple[Optional[str], float, OCRTier, int, float]:
        """
        Extract text using multi-tier approach.
        
        Returns:
            Tuple of (extracted_text, confidence, tier_used, processing_time_ms, cost)
        """
        start_time = time.time()
        
        if force_high_quality and config.Config.OCR_TIER3_ENABLED and self._tier3_available:
            logger.info(f"Force high quality: using {self._tier3_provider} for {file_path}")
            return self._extract_tier3(file_path)
        
        if is_native_pdf and config.Config.OCR_TIER1_ENABLED:
            text, confidence, tier, time_ms, cost = self._extract_tier1(file_path)
            if confidence >= config.Config.OCR_CONFIDENCE_THRESHOLD:
                return text, confidence, tier, time_ms, cost
        
        if config.Config.OCR_TIER2_ENABLED and self._tesseract_available:
            text, confidence, tier, time_ms, cost = self._extract_tier2_tesseract(file_path)
            if confidence >= config.Config.OCR_CONFIDENCE_THRESHOLD:
                return text, confidence, tier, time_ms, cost
        
        if config.Config.OCR_TIER3_ENABLED and self._tier3_available:
            return self._extract_tier3(file_path)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        return None, 0.0, OCRTier.TIER2_TESSERACT, elapsed_ms, 0.0
    
    def _extract_tier1(self, file_path: Path) -> Tuple[Optional[str], float, OCRTier, int, float]:
        """Extract text using Tier 1 (PyPDF2/pdfplumber)."""
        start_time = time.time()
        
        try:
            text_pypdf2 = None
            text_pdfplumber = None
            
            try:
                with open(file_path, "rb") as f:
                    reader = PdfReader(f)
                    text_pypdf2 = ""
                    for page in reader.pages:
                        text_pypdf2 += page.extract_text() + "\n"
            except Exception as e:
                logger.debug(f"PyPDF2 extraction failed: {e}")
            
            try:
                with pdfplumber.open(file_path) as pdf:
                    text_pdfplumber = ""
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_pdfplumber += page_text + "\n"
            except Exception as e:
                logger.debug(f"pdfplumber extraction failed: {e}")
            
            texts = [t for t in [text_pypdf2, text_pdfplumber] if t and len(t.strip()) > 0]
            
            if not texts:
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, 0.0, OCRTier.TIER1_PYPDF2, elapsed_ms, 0.0
            
            best_text = max(texts, key=len)
            confidence = self._calculate_confidence(best_text)
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            tier = OCRTier.TIER1_PDFPLUMBER if text_pdfplumber and len(text_pdfplumber) >= len(text_pypdf2) else OCRTier.TIER1_PYPDF2
            
            logger.info(f"Tier 1 extraction: {len(best_text)} chars, confidence {confidence:.1f}%")
            return best_text, confidence, tier, elapsed_ms, 0.0
            
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tier 1 extraction error: {e}")
            return None, 0.0, OCRTier.TIER1_PYPDF2, elapsed_ms, 0.0
    
    def _extract_tier2_tesseract(self, file_path: Path) -> Tuple[Optional[str], float, OCRTier, int, float]:
        """Extract text using Tier 2 (Tesseract OCR)."""
        start_time = time.time()
        
        try:
            import pytesseract
            from pdf2image import convert_from_path
            
            images = []
            if file_path.suffix.lower() == ".pdf":
                images = convert_from_path(str(file_path), dpi=300)
            else:
                img = Image.open(file_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images = [img]
            
            extracted_text = ""
            total_confidence = 0.0
            page_count = 0
            
            for img in images:
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                page_text = ""
                page_confidences = []
                
                for i, text in enumerate(data["text"]):
                    if text.strip():
                        page_text += text + " "
                        conf = float(data["conf"][i])
                        if conf > 0:
                            page_confidences.append(conf)
                
                if page_text:
                    extracted_text += page_text + "\n\n"
                    if page_confidences:
                        total_confidence += sum(page_confidences) / len(page_confidences)
                    page_count += 1
            
            if not extracted_text.strip():
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, 0.0, OCRTier.TIER2_TESSERACT, elapsed_ms, 0.0
            
            avg_confidence = total_confidence / page_count if page_count > 0 else 0.0
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Tier 2 extraction: {len(extracted_text)} chars, confidence {avg_confidence:.1f}%")
            return extracted_text.strip(), avg_confidence, OCRTier.TIER2_TESSERACT, elapsed_ms, 0.0
            
        except ImportError:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("Tesseract dependencies not installed")
            return None, 0.0, OCRTier.TIER2_TESSERACT, elapsed_ms, 0.0
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tier 2 extraction error: {e}")
            return None, 0.0, OCRTier.TIER2_TESSERACT, elapsed_ms, 0.0
    
    def _extract_tier3(self, file_path: Path) -> Tuple[Optional[str], float, OCRTier, int, float]:
        """Extract text using Tier 3 (Gemini Flash or Mistral)."""
        provider = config.Config.TIER3_PROVIDER.lower()
        
        if provider == "gemini":
            return self._extract_tier3_gemini(file_path)
        elif provider == "mistral":
            return self._extract_tier3_mistral(file_path)
        else:
            logger.error(f"Unknown Tier 3 provider: {provider}")
            return None, 0.0, OCRTier.TIER3_GEMINI_FLASH, 0, 0.0
    
    def _extract_tier3_gemini(self, file_path: Path) -> Tuple[Optional[str], float, OCRTier, int, float]:
        """Extract text using Tier 3 (Google Gemini Flash)."""
        start_time = time.time()
        
        try:
            import google.generativeai as genai
            import base64
            
            genai.configure(api_key=config.Config.GEMINI_API_KEY)
            model = genai.GenerativeModel(config.Config.GEMINI_MODEL)
            
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            if file_path.suffix.lower() == ".pdf":
                file_part = {
                    "mime_type": "application/pdf",
                    "data": file_bytes
                }
            else:
                mime_type_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".tiff": "image/tiff",
                    ".tif": "image/tiff",
                }
                mime_type = mime_type_map.get(file_path.suffix.lower(), "image/jpeg")
                file_part = {
                    "mime_type": mime_type,
                    "data": file_bytes
                }
            
            prompt = """Extract all text from this document. Preserve the structure, including:
- Line breaks and paragraphs
- Tables and their structure
- Headers and sections
- Any numerical values and dollar amounts
- Dates and other important information

Return only the extracted text, no explanations or additional commentary."""
            
            response = model.generate_content([prompt, file_part])
            extracted_text = response.text if response.text else ""
            
            confidence = 95.0
            if extracted_text:
                confidence = min(100.0, 90.0 + (len(extracted_text.split()) / 100))
            
            page_count = 1
            if file_path.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    with open(file_path, "rb") as f:
                        reader = PdfReader(f)
                        page_count = len(reader.pages)
                except Exception:
                    pass
            
            cost = page_count * config.Config.GEMINI_COST_PER_PAGE
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Tier 3 Gemini extraction: {len(extracted_text)} chars, confidence {confidence:.1f}%")
            return extracted_text, confidence, OCRTier.TIER3_GEMINI_FLASH, elapsed_ms, cost
            
        except ImportError:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("google-generativeai not installed")
            return None, 0.0, OCRTier.TIER3_GEMINI_FLASH, elapsed_ms, 0.0
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tier 3 Gemini extraction error: {e}")
            return None, 0.0, OCRTier.TIER3_GEMINI_FLASH, elapsed_ms, 0.0
    
    def _extract_tier3_mistral(self, file_path: Path) -> Tuple[Optional[str], float, OCRTier, int, float]:
        """Extract text using Tier 3 (Mistral AI)."""
        start_time = time.time()
        
        try:
            from mistralai import Mistral
            import base64
            
            client = Mistral(api_key=config.Config.MISTRAL_API_KEY)
            
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            base64_image = base64.b64encode(file_bytes).decode("utf-8")
            
            if file_path.suffix.lower() == ".pdf":
                mime_type = "application/pdf"
            else:
                mime_type_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".tiff": "image/tiff",
                    ".tif": "image/tiff",
                }
                mime_type = mime_type_map.get(file_path.suffix.lower(), "image/jpeg")
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text from this document. Preserve the structure, including line breaks, paragraphs, tables, headers, numerical values, dollar amounts, and dates. Return only the extracted text, no explanations."
                        },
                        {
                            "type": "image_url",
                            "image_url": f"data:{mime_type};base64,{base64_image}"
                        }
                    ]
                }
            ]
            
            response = client.chat.complete(
                model=config.Config.MISTRAL_MODEL,
                messages=messages,
            )
            
            extracted_text = response.choices[0].message.content if response.choices else ""
            
            confidence = 95.0
            if extracted_text:
                confidence = min(100.0, 90.0 + (len(extracted_text.split()) / 100))
            
            page_count = 1
            if file_path.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    with open(file_path, "rb") as f:
                        reader = PdfReader(f)
                        page_count = len(reader.pages)
                except Exception:
                    pass
            
            cost = page_count * config.Config.MISTRAL_COST_PER_PAGE
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Tier 3 Mistral extraction: {len(extracted_text)} chars, confidence {confidence:.1f}%")
            return extracted_text, confidence, OCRTier.TIER3_MISTRAL, elapsed_ms, cost
            
        except ImportError:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("mistralai not installed")
            return None, 0.0, OCRTier.TIER3_MISTRAL, elapsed_ms, 0.0
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tier 3 Mistral extraction error: {e}")
            return None, 0.0, OCRTier.TIER3_MISTRAL, elapsed_ms, 0.0
    
    def _calculate_confidence(self, text: str) -> float:
        """
        Calculate confidence score for extracted text.
        
        Simple heuristic: based on text length, character diversity, word count.
        """
        if not text or len(text.strip()) < 10:
            return 0.0
        
        text = text.strip()
        word_count = len(text.split())
        char_diversity = len(set(text.lower())) / max(len(text), 1)
        
        if word_count < 10:
            return 30.0
        
        base_confidence = min(85.0, 50.0 + (word_count / 10) * 2)
        diversity_bonus = char_diversity * 10
        
        return min(100.0, base_confidence + diversity_bonus)
    
    def extract_with_attempts(
        self,
        file_path: Path,
        is_native_pdf: bool = False,
        force_high_quality: bool = False,
    ) -> Tuple[List[ExtractionAttempt], Optional[ExtractionAttempt]]:
        """
        Extract text with all attempts recorded.
        
        Returns:
            Tuple of (all_attempts, best_attempt)
        """
        attempts = []
        best_attempt = None
        best_confidence = -1.0
        
        if is_native_pdf and config.Config.OCR_TIER1_ENABLED:
            text, confidence, tier, time_ms, cost = self._extract_tier1(file_path)
            attempt = ExtractionAttempt(
                tier=tier,
                extracted_text=text or "",
                confidence=confidence,
                processing_time_ms=time_ms,
                cost=cost,
                page_count=1,
            )
            attempts.append(attempt)
            if confidence > best_confidence:
                best_confidence = confidence
                best_attempt = attempt
        
        if (best_confidence < config.Config.OCR_CONFIDENCE_THRESHOLD or force_high_quality) and config.Config.OCR_TIER2_ENABLED and self._tesseract_available:
            text, confidence, tier, time_ms, cost = self._extract_tier2_tesseract(file_path)
            attempt = ExtractionAttempt(
                tier=tier,
                extracted_text=text or "",
                confidence=confidence,
                processing_time_ms=time_ms,
                cost=cost,
                page_count=1,
            )
            attempts.append(attempt)
            if confidence > best_confidence:
                best_confidence = confidence
                best_attempt = attempt
        
        if (best_confidence < config.Config.OCR_CONFIDENCE_THRESHOLD or force_high_quality) and config.Config.OCR_TIER3_ENABLED and self._tier3_available:
            text, confidence, tier, time_ms, cost = self._extract_tier3(file_path)
            attempt = ExtractionAttempt(
                tier=tier,
                extracted_text=text or "",
                confidence=confidence,
                processing_time_ms=time_ms,
                cost=cost,
                page_count=1,
            )
            attempts.append(attempt)
            if confidence > best_confidence:
                best_confidence = confidence
                best_attempt = attempt
        
        return attempts, best_attempt

