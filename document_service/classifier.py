"""Document classification with ML and rule-based fallback."""

import logging
import re
from typing import Dict, List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

import config
from models import (
    DocumentClassification,
    DocumentType,
    ExtractedText,
    FeatureScores,
)

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """Document classifier with ML and rule-based fallback."""
    
    def __init__(self):
        """Initialize classifier."""
        self.ml_model: Optional[Pipeline] = None
        self._train_model()
    
    def _train_model(self) -> None:
        """Train ML model with example documents."""
        training_data = self._get_training_data()
        
        if not training_data:
            logger.warning("No training data available, using rule-based only")
            return
        
        texts = [item["text"] for item in training_data]
        labels = [item["label"] for item in training_data]
        
        try:
            self.ml_model = Pipeline([
                ("tfidf", TfidfVectorizer(max_features=1000, ngram_range=(1, 2))),
                ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
            ])
            self.ml_model.fit(texts, labels)
            logger.info("ML model trained successfully")
        except Exception as e:
            logger.error(f"Failed to train ML model: {e}")
            self.ml_model = None
    
    def _get_training_data(self) -> List[Dict[str, str]]:
        """Get training data examples."""
        return [
            {"text": "LEASE AGREEMENT This lease agreement is entered into on TERM: 12 months MONTHLY RENT: $1500", "label": "lease"},
            {"text": "RESIDENTIAL LEASE TERM: January 1, 2023 to December 31, 2023 MONTHLY RENT: $2000 Security Deposit: $2000", "label": "lease"},
            {"text": "LEASE AGREEMENT Property Address: 123 Main St TERM: 24 months MONTHLY RENT: $1800", "label": "lease"},
            {"text": "INVOICE Invoice Number: INV-001 BALANCE DUE: $500.00 Itemized charges: Flooring $300, Paint $200", "label": "invoice"},
            {"text": "Invoice for Services Rendered Total Amount: $1,500.00 BALANCE DUE: $1,500.00", "label": "invoice"},
            {"text": "INVOICE #12345 Date: 2024-01-15 Itemized charges: Repair $800, Labor $200 Total: $1000.00", "label": "invoice"},
            {"text": "ADDENDUM TO LEASE AGREEMENT This addendum modifies the lease SECURITY DEPOSIT WAIVER: Yes", "label": "addendum"},
            {"text": "ADDENDUM ENROLLMENT: Confirmed This addendum is part of the lease agreement", "label": "addendum"},
            {"text": "Lease Addendum SECURITY DEPOSIT WAIVER granted ENROLLMENT: Active", "label": "addendum"},
        ]
    
    def classify(
        self,
        extracted_text: ExtractedText,
        page_count: int,
        ocr_confidence: float,
    ) -> DocumentClassification:
        """
        Classify document using ML with rule-based fallback.
        
        Args:
            extracted_text: Extracted text result
            page_count: Number of pages
            ocr_confidence: OCR confidence score
        
        Returns:
            DocumentClassification result
        """
        text = extracted_text.text.lower()
        
        feature_scores = self._extract_features(text, page_count)
        
        ml_result = None
        ml_probabilities = {}
        
        if self.ml_model:
            try:
                probabilities = self.ml_model.predict_proba([extracted_text.text])[0]
                classes = self.ml_model.classes_
                ml_probabilities = {cls: float(prob) for cls, prob in zip(classes, probabilities)}
                predicted_class = classes[np.argmax(probabilities)]
                ml_confidence = float(probabilities[np.argmax(probabilities)])
                
                ml_result = {
                    "type": DocumentType(predicted_class),
                    "confidence": ml_confidence,
                }
            except Exception as e:
                logger.warning(f"ML classification failed: {e}")
        
        ocr_quality_factor = min(1.0, ocr_confidence / 100.0)
        
        if ml_result:
            final_confidence = ml_result["confidence"] * ocr_quality_factor
            
            if final_confidence >= config.Config.CLASSIFICATION_CONFIDENCE_THRESHOLD:
                return DocumentClassification(
                    document_type=ml_result["type"],
                    confidence=final_confidence,
                    feature_scores=feature_scores,
                    fallback_used=False,
                    ml_probabilities=ml_probabilities,
                )
        
        rule_result = self._classify_with_rules(text, page_count, feature_scores)
        
        if rule_result["confidence"] >= config.Config.CLASSIFICATION_CONFIDENCE_THRESHOLD:
            return DocumentClassification(
                document_type=rule_result["type"],
                confidence=rule_result["confidence"],
                feature_scores=feature_scores,
                fallback_used=True,
                ml_probabilities=ml_probabilities,
            )
        
        return DocumentClassification(
            document_type=DocumentType.UNKNOWN,
            confidence=max(rule_result["confidence"], ml_result["confidence"] if ml_result else 0.0),
            feature_scores=feature_scores,
            fallback_used=True,
            ml_probabilities=ml_probabilities,
        )
    
    def _extract_features(self, text: str, page_count: int) -> FeatureScores:
        """Extract features for classification."""
        keyword_score = self._calculate_keyword_score(text)
        structure_score = self._calculate_structure_score(text)
        dollar_amount_score = self._calculate_dollar_amount_score(text)
        date_pattern_score = self._calculate_date_pattern_score(text)
        page_count_score = self._calculate_page_count_score(page_count)
        
        return FeatureScores(
            keyword_score=keyword_score,
            structure_score=structure_score,
            dollar_amount_score=dollar_amount_score,
            date_pattern_score=date_pattern_score,
            page_count_score=page_count_score,
        )
    
    def _calculate_keyword_score(self, text: str) -> float:
        """Calculate keyword presence score."""
        lease_keywords = ["lease agreement", "term:", "monthly rent", "tenant", "landlord"]
        invoice_keywords = ["invoice", "balance due", "total", "amount due", "itemized"]
        addendum_keywords = ["addendum", "security deposit waiver", "enrollment"]
        
        lease_matches = sum(1 for kw in lease_keywords if kw in text)
        invoice_matches = sum(1 for kw in invoice_keywords if kw in text)
        addendum_matches = sum(1 for kw in addendum_keywords if kw in text)
        
        max_matches = max(lease_matches, invoice_matches, addendum_matches)
        return min(1.0, max_matches / len(lease_keywords))
    
    def _calculate_structure_score(self, text: str) -> float:
        """Calculate document structure score."""
        lines = text.split("\n")
        line_count = len([l for l in lines if l.strip()])
        
        has_table_indicators = any(
            "|" in line or "\t" in line or re.search(r"\s{3,}", line)
            for line in lines[:20]
        )
        
        score = min(1.0, line_count / 50.0)
        if has_table_indicators:
            score += 0.2
        
        return min(1.0, score)
    
    def _calculate_dollar_amount_score(self, text: str) -> float:
        """Calculate dollar amount pattern score."""
        dollar_pattern = r'\$[\d,]+\.?\d*'
        matches = re.findall(dollar_pattern, text)
        
        if len(matches) >= 3:
            return 1.0
        elif len(matches) >= 2:
            return 0.7
        elif len(matches) >= 1:
            return 0.4
        
        return 0.0
    
    def _calculate_date_pattern_score(self, text: str) -> float:
        """Calculate date pattern score."""
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}',
        ]
        
        matches = sum(1 for pattern in date_patterns if re.search(pattern, text, re.IGNORECASE))
        
        if matches >= 2:
            return 1.0
        elif matches >= 1:
            return 0.5
        
        return 0.0
    
    def _calculate_page_count_score(self, page_count: int) -> float:
        """Calculate page count score."""
        if 5 <= page_count <= 15:
            return 1.0
        elif 3 <= page_count <= 20:
            return 0.7
        elif 1 <= page_count <= 25:
            return 0.4
        
        return 0.2
    
    def _classify_with_rules(self, text: str, page_count: int, feature_scores: FeatureScores) -> Dict:
        """Classify using rule-based approach."""
        lease_score = 0.0
        invoice_score = 0.0
        addendum_score = 0.0
        
        if "lease agreement" in text or "lease" in text:
            lease_score += 0.4
        if "term:" in text or "monthly rent" in text:
            lease_score += 0.3
        if 5 <= page_count <= 15:
            lease_score += 0.2
        if feature_scores.date_pattern_score > 0.5:
            lease_score += 0.1
        
        if "invoice" in text:
            invoice_score += 0.4
        if "balance due" in text or "total" in text.lower():
            invoice_score += 0.3
        if feature_scores.dollar_amount_score > 0.5:
            invoice_score += 0.2
        if 1 <= page_count <= 5:
            invoice_score += 0.1
        
        if "addendum" in text:
            addendum_score += 0.4
        if "security deposit waiver" in text:
            addendum_score += 0.3
        if "enrollment" in text:
            addendum_score += 0.2
        if page_count <= 3:
            addendum_score += 0.1
        
        scores = {
            DocumentType.LEASE: lease_score,
            DocumentType.INVOICE: invoice_score,
            DocumentType.ADDENDUM: addendum_score,
        }
        
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        return {
            "type": best_type,
            "confidence": min(1.0, best_score),
        }

