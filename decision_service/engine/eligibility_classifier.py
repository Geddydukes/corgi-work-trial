"""Eligibility classification system with multi-layer decision tree and externalized rules."""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class EligibilityStatus(Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    AMBIGUOUS = "ambiguous"


@dataclass
class ClassificationResult:
    status: EligibilityStatus
    category: str
    confidence: float
    matched_patterns: List[str]
    matched_keywords: List[str]
    reasoning: str
    requires_manual_review: bool
    flags: List[str]
    rule_version: str
    classification_layers: Dict[str, any]


@dataclass
class ClassifiedLineItem:
    description: str
    amount: Decimal
    line_number: int
    classification: ClassificationResult
    original_text: str
    normalized_description: str


class EligibilityClassifier:
    """
    Production-grade eligibility classifier with externalized rules.
    
    Features:
    - Hot-reloadable rules from YAML
    - Multi-layer classification
    - Comprehensive audit trail
    - A/B testing support
    """
    
    def __init__(self, rules_path: str = "rules_v1.0.yaml"):
        self.rules = self._load_rules(rules_path)
        self.rule_version = self.rules['version']
        self.ml_model = None
        self._compile_patterns()
        self._build_exact_matches()
    
    def _load_rules(self, path: str) -> dict:
        """Load and validate rules configuration."""
        rules_file = Path(path)
        if not rules_file.is_absolute() and not rules_file.exists():
            rules_file = Path(__file__).parent.parent.parent / "rules" / path
            if not rules_file.exists():
                rules_file = Path(__file__).parent.parent.parent / path
                if not rules_file.exists():
                    raise FileNotFoundError(f"Rules file not found: {path}")
        
        with open(rules_file, 'r') as f:
            rules = yaml.safe_load(f)
        
        required_keys = ['version', 'categories', 'threshold_rules']
        for key in required_keys:
            if key not in rules:
                raise ValueError(f"Missing required key in rules: {key}")
        
        return rules
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        for category in self.rules['categories']:
            category['compiled_patterns'] = [
                re.compile(pattern, re.IGNORECASE) 
                for pattern in category.get('patterns', [])
            ]
    
    def _build_exact_matches(self):
        """Build exact match dictionary from category examples."""
        self.exact_matches = {}
        for category in self.rules['categories']:
            category_name = category['name']
            confidence = category.get('confidence', 90)
            for example in category.get('examples', []):
                normalized_example = self._normalize_description(example)
                self.exact_matches[normalized_example] = (category_name, confidence)
    
    def classify(self, line_item: dict) -> ClassifiedLineItem:
        """
        Classify a single line item.
        
        Args:
            line_item: Dict with 'description' and 'amount' keys
            
        Returns:
            ClassifiedLineItem with classification results
        """
        description = line_item.get('description', '')
        amount = line_item.get('amount', Decimal('0.00'))
        
        if not description:
            return self._build_default_result(line_item, "Empty description")
        
        normalized = self._normalize_description(description)
        layers = {}
        
        exact_result = self._exact_match(normalized)
        layers['exact_match'] = exact_result
        
        pattern_result = self._pattern_match(normalized)
        layers['pattern_match'] = pattern_result
        
        if exact_result:
            if not pattern_result or exact_result['confidence'] >= pattern_result['confidence'] - 5:
                result = self._apply_special_rules(exact_result, line_item)
                return self._build_result(line_item, result, layers)
        
        if pattern_result and pattern_result['confidence'] > 80:
            result = self._apply_special_rules(pattern_result, line_item)
            return self._build_result(line_item, result, layers)
        
        if exact_result:
            result = self._apply_special_rules(exact_result, line_item)
            return self._build_result(line_item, result, layers)
        
        keyword_result = self._keyword_score(normalized)
        layers['keyword_score'] = keyword_result
        if keyword_result and keyword_result['confidence'] > 50:
            result = self._apply_special_rules(keyword_result, line_item)
            return self._build_result(line_item, result, layers)
        
        if self.ml_model:
            ml_result = self._ml_predict(normalized)
            layers['ml_prediction'] = ml_result
            if ml_result and ml_result['confidence'] > 70:
                result = self._apply_special_rules(ml_result, line_item)
                return self._build_result(line_item, result, layers)
        
        default_result = {
            'status': EligibilityStatus.ELIGIBLE if self.rules.get('approval_bias', True) else EligibilityStatus.AMBIGUOUS,
            'category': 'DEFAULT_ELIGIBLE' if self.rules.get('approval_bias', True) else 'DEFAULT_AMBIGUOUS',
            'confidence': 30,
            'matched_patterns': [],
            'matched_keywords': [],
            'reasoning': 'No strong match found, defaulting per policy',
            'requires_manual_review': True,
            'flags': ['LOW_CONFIDENCE_DEFAULT']
        }
        layers['default'] = default_result
        
        return self._build_result(line_item, default_result, layers)
    
    def _normalize_description(self, desc: str) -> str:
        """Clean and normalize description for matching."""
        normalized = desc.lower()
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def _exact_match(self, normalized: str) -> Optional[dict]:
        """Check for exact phrase matches with fuzzy matching for typos."""
        best_match = None
        best_confidence = 0
        
        for phrase, (category, confidence) in self.exact_matches.items():
            if phrase in normalized:
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        'status': self._get_status_from_category(category),
                        'category': category,
                        'confidence': confidence,
                        'matched_patterns': [phrase],
                        'matched_keywords': phrase.split(),
                        'reasoning': f'Exact match: "{phrase}"',
                        'requires_manual_review': False,
                        'flags': []
                    }
        
        if best_match:
            return best_match
        
        for phrase, (category, confidence) in self.exact_matches.items():
            if self._fuzzy_match(normalized, phrase, max_distance=3):
                fuzzy_confidence = max(confidence - 5, 85)
                if fuzzy_confidence > best_confidence:
                    best_confidence = fuzzy_confidence
                    best_match = {
                        'status': self._get_status_from_category(category),
                        'category': category,
                        'confidence': fuzzy_confidence,
                        'matched_patterns': [phrase],
                        'matched_keywords': phrase.split(),
                        'reasoning': f'Fuzzy match: "{phrase}"',
                        'requires_manual_review': False,
                        'flags': ['FUZZY_MATCH']
                    }
        
        return best_match
    
    def _fuzzy_match(self, text: str, pattern: str, max_distance: int = 3) -> bool:
        """Check if text matches pattern within Levenshtein distance."""
        if pattern in text:
            return True
        
        words = text.split()
        pattern_words = pattern.split()
        
        if len(pattern_words) == 1:
            for word in words:
                if self._levenshtein_distance(word, pattern_words[0]) <= max_distance:
                    return True
        else:
            for i in range(len(words) - len(pattern_words) + 1):
                window = ' '.join(words[i:i+len(pattern_words)])
                if self._levenshtein_distance(window, pattern) <= max_distance:
                    return True
        
        return False
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _pattern_match(self, normalized: str) -> Optional[dict]:
        """Match against regex patterns."""
        best_match = None
        highest_confidence = 0
        
        for category in self.rules['categories']:
            for pattern in category.get('compiled_patterns', []):
                match = pattern.search(normalized)
                if match:
                    confidence = category.get('confidence', 85)
                    
                    negative_keywords = category.get('keywords', {}).get('negative', [])
                    if not any(kw.lower() in normalized for kw in negative_keywords):
                        confidence = min(confidence + 5, 99)
                    
                    if confidence > highest_confidence:
                        highest_confidence = confidence
                        best_match = {
                            'status': self._get_status_from_category(category['name']),
                            'category': category['name'],
                            'confidence': confidence,
                            'matched_patterns': [pattern.pattern],
                            'matched_keywords': self._extract_matched_keywords(
                                normalized, category.get('keywords', {}).get('positive', [])
                            ),
                            'reasoning': f'Pattern match: {category["name"]}',
                            'requires_manual_review': confidence < self.rules['threshold_rules'].get('low_confidence_review', 60),
                            'flags': []
                        }
        
        return best_match
    
    def _keyword_score(self, normalized: str) -> Optional[dict]:
        """Score based on keyword presence."""
        category_scores = {}
        
        for category in self.rules['categories']:
            score = 0
            matched_pos = []
            matched_neg = []
            
            positive_keywords = category.get('keywords', {}).get('positive', [])
            negative_keywords = category.get('keywords', {}).get('negative', [])
            
            for keyword in positive_keywords:
                if keyword.lower() in normalized:
                    score += 1
                    matched_pos.append(keyword)
            
            for keyword in negative_keywords:
                if keyword.lower() in normalized:
                    score -= 2
                    matched_neg.append(keyword)
            
            if score > 0:
                max_possible_score = len(positive_keywords) if positive_keywords else 1
                score_ratio = score / max_possible_score
                base_confidence = category.get('confidence', 75)
                confidence = min(base_confidence * score_ratio, 85)
                
                category_scores[category['name']] = {
                    'score': score,
                    'matched_pos': matched_pos,
                    'matched_neg': matched_neg,
                    'confidence': confidence
                }
        
        if not category_scores:
            return None
        
        best_category = max(category_scores.items(), key=lambda x: x[1]['score'])
        category_name = best_category[0]
        score_data = best_category[1]
        
        return {
            'status': self._get_status_from_category(category_name),
            'category': category_name,
            'confidence': score_data['confidence'],
            'matched_patterns': [],
            'matched_keywords': score_data['matched_pos'],
            'reasoning': f'Keyword score: {score_data["score"]} ({", ".join(score_data["matched_pos"])})',
            'requires_manual_review': score_data['confidence'] < self.rules['threshold_rules'].get('low_confidence_review', 60),
            'flags': ['KEYWORD_BASED'] if score_data['matched_neg'] else []
        }
    
    def _ml_predict(self, normalized: str) -> Optional[dict]:
        """ML prediction using trained model."""
        if not self.ml_model:
            return None
        
        try:
            probabilities = self.ml_model.predict_proba([normalized])[0]
            classes = self.ml_model.classes_
            max_idx = probabilities.argmax()
            confidence = float(probabilities[max_idx]) * 100
            predicted_class = classes[max_idx]
            
            if confidence > 70:
                return {
                    'status': EligibilityStatus.ELIGIBLE if 'ELIGIBLE' in predicted_class else EligibilityStatus.INELIGIBLE,
                    'category': predicted_class,
                    'confidence': confidence,
                    'matched_patterns': [],
                    'matched_keywords': [],
                    'reasoning': f'ML prediction: {predicted_class}',
                    'requires_manual_review': confidence < 85,
                    'flags': ['ML_BASED']
                }
        except Exception as e:
            logger.warning(f"ML prediction failed: {e}")
        
        return None
    
    def _apply_special_rules(self, result: dict, line_item: dict) -> dict:
        """Apply special case rules that override normal classification."""
        description = line_item.get('description', '').lower()
        amount = line_item.get('amount', Decimal('0.00'))
        
        for special_rule in self.rules.get('special_rules', []):
            trigger = special_rule.get('trigger', {})
            triggered = False
            
            if 'contains_all' in trigger:
                keywords = trigger['contains_all']
                if all(kw.lower() in description for kw in keywords):
                    triggered = True
            
            if 'amount_above' in trigger and 'confidence_below' in trigger:
                if amount > Decimal(str(trigger['amount_above'])) and result['confidence'] < trigger['confidence_below']:
                    triggered = True
            
            if 'patterns' in trigger:
                patterns = trigger['patterns']
                if all(re.search(pattern, description, re.IGNORECASE) for pattern in patterns):
                    triggered = True
            
            if triggered:
                action = special_rule.get('action', {})
                result = result.copy()
                
                if 'status' in action:
                    status_value = action['status'].lower()
                    result['status'] = EligibilityStatus(status_value)
                if 'category' in action:
                    result['category'] = action['category']
                if 'confidence' in action:
                    result['confidence'] = action['confidence']
                if 'requires_review' in action:
                    result['requires_manual_review'] = action['requires_review']
                if 'flag' in action:
                    result['flags'].append(action['flag'])
                if 'reason' in action:
                    result['reasoning'] = f"{result['reasoning']}; {action['reason']}"
                
                result['flags'].append(f"SPECIAL_RULE_{special_rule.get('rule_id', 'UNKNOWN')}")
        
        for category in self.rules['categories']:
            if category['name'] == result['category']:
                amount_threshold = category.get('amount_threshold')
                if amount_threshold and 'above' in amount_threshold:
                    if amount > Decimal(str(amount_threshold['above'])):
                        boost = amount_threshold.get('confidence_boost', 0)
                        result['confidence'] = min(result['confidence'] + boost, 99)
                        result['flags'].append('AMOUNT_THRESHOLD_MET')
        
        if amount > Decimal(str(self.rules['threshold_rules'].get('high_value_review', 500))):
            if result['confidence'] < 60:
                result['requires_manual_review'] = True
                result['flags'].append('HIGH_VALUE_UNCERTAIN')
        
        if result['confidence'] < self.rules['threshold_rules'].get('manual_review_required', 40):
            result['requires_manual_review'] = True
        
        return result
    
    def _get_status_from_category(self, category_name: str) -> EligibilityStatus:
        """Determine eligibility status from category name."""
        if category_name.startswith('ELIGIBLE'):
            return EligibilityStatus.ELIGIBLE
        elif category_name.startswith('INELIGIBLE'):
            return EligibilityStatus.INELIGIBLE
        else:
            return EligibilityStatus.AMBIGUOUS
    
    def _extract_matched_keywords(self, text: str, keywords: List[str]) -> List[str]:
        """Extract which keywords were actually found in text."""
        return [kw for kw in keywords if kw.lower() in text]
    
    def _build_result(self, line_item: dict, classification: dict, layers: dict) -> ClassifiedLineItem:
        """Build final ClassifiedLineItem object."""
        return ClassifiedLineItem(
            description=line_item.get('description', ''),
            amount=Decimal(str(line_item.get('amount', 0))),
            line_number=line_item.get('line_number', 0),
            classification=ClassificationResult(
                status=classification['status'],
                category=classification['category'],
                confidence=classification['confidence'],
                matched_patterns=classification['matched_patterns'],
                matched_keywords=classification['matched_keywords'],
                reasoning=classification['reasoning'],
                requires_manual_review=classification['requires_manual_review'],
                flags=classification['flags'],
                rule_version=self.rule_version,
                classification_layers=layers
            ),
            original_text=line_item.get('description', ''),
            normalized_description=self._normalize_description(line_item.get('description', ''))
        )
    
    def _build_default_result(self, line_item: dict, reason: str) -> ClassifiedLineItem:
        """Build default result for edge cases."""
        default_result = {
            'status': EligibilityStatus.AMBIGUOUS,
            'category': 'DEFAULT_AMBIGUOUS',
            'confidence': 30,
            'matched_patterns': [],
            'matched_keywords': [],
            'reasoning': reason,
            'requires_manual_review': True,
            'flags': ['EDGE_CASE']
        }
        return self._build_result(line_item, default_result, {'default': default_result})
    
    def classify_batch(self, line_items: List[dict]) -> List[ClassifiedLineItem]:
        """Classify multiple line items efficiently."""
        return [self.classify(item) for item in line_items]
    
    def get_rule_version(self) -> str:
        """Get current rules version."""
        return self.rule_version
    
    def reload_rules(self, rules_path: str):
        """Hot-reload rules without restarting service."""
        self.rules = self._load_rules(rules_path)
        self.rule_version = self.rules['version']
        self._compile_patterns()
        self._build_exact_matches()
        logger.info(f"Rules reloaded: version {self.rule_version}")
    
    def set_ml_model(self, model):
        """Set ML model for Layer 4 classification."""
        self.ml_model = model
        logger.info("ML model set for classification")

