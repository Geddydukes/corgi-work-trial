"""Language detection with RTL support."""

import logging
from typing import Optional, Tuple

from shared.config import Config

logger = logging.getLogger(__name__)

RTL_LANGUAGES = {"ar", "he", "ur", "fa", "yi"}


class LanguageDetector:
    """Detects document language and RTL support."""
    
    def __init__(self):
        """Initialize language detector."""
        self._detector = None
        self._load_detector()
    
    def _load_detector(self) -> None:
        """Load language detection library."""
        if not Config.LANGUAGE_DETECTION_ENABLED:
            return
        
        try:
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 0
            self._detector = detect
            logger.info("Language detector loaded")
        except ImportError:
            logger.warning("langdetect not available, language detection disabled")
            self._detector = None
        except Exception as e:
            logger.error(f"Failed to load language detector: {e}")
            self._detector = None
    
    def detect_language(self, text: str) -> Tuple[Optional[str], float, bool]:
        """
        Detect language of text.
        
        Args:
            text: Text to analyze
        
        Returns:
            Tuple of (language_code, confidence, is_rtl)
        """
        if not Config.LANGUAGE_DETECTION_ENABLED or not self._detector:
            return None, 0.0, False
        
        if not text or len(text.strip()) < 10:
            return None, 0.0, False
        
        try:
            language = self._detector(text)
            confidence = 0.85
            
            is_rtl = language in RTL_LANGUAGES if language else False
            
            return language, confidence, is_rtl
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None, 0.0, False
    
    def is_rtl_language(self, language_code: Optional[str]) -> bool:
        """
        Check if language code is RTL.
        
        Args:
            language_code: ISO 639-1 language code
        
        Returns:
            True if RTL language
        """
        if not language_code:
            return False
        return language_code.lower() in RTL_LANGUAGES
















