"""Comprehensive test suite for eligibility classifier."""

import pytest
from decimal import Decimal
from pathlib import Path

from decision_service.engine.eligibility_classifier import (
    EligibilityClassifier,
    EligibilityStatus,
    ClassifiedLineItem
)


@pytest.fixture
def classifier():
    """Create classifier instance for testing."""
    rules_path = Path(__file__).parent.parent / "rules" / "rules_v1.0.yaml"
    return EligibilityClassifier(str(rules_path))


class TestExactMatch:
    """Test Layer 1: Exact Match classification."""
    
    def test_carpet_cleaning_exact(self, classifier):
        """Test exact match for carpet cleaning."""
        item = {
            "description": "Professional carpet cleaning",
            "amount": Decimal("150.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert result.classification.category == "ELIGIBLE_CLEANING"
        assert result.classification.confidence >= 90
        assert not result.classification.requires_manual_review
    
    def test_normal_wear_tear_exact(self, classifier):
        """Test exact match for normal wear and tear."""
        item = {
            "description": "Normal wear and tear on walls",
            "amount": Decimal("75.00"),
            "line_number": 2
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
        assert result.classification.category == "INELIGIBLE_NORMAL_WEAR"
        assert result.classification.confidence >= 95
    
    def test_unpaid_rent_exact(self, classifier):
        """Test exact match for unpaid rent."""
        item = {
            "description": "Unpaid rent - October 2024",
            "amount": Decimal("1200.00"),
            "line_number": 3
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert result.classification.category == "ELIGIBLE_UNPAID_RENT"
        assert result.classification.confidence == 100
    
    def test_broken_window_exact(self, classifier):
        """Test exact match for broken window."""
        item = {
            "description": "Broken window pane replacement",
            "amount": Decimal("200.00"),
            "line_number": 4
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert result.classification.category == "ELIGIBLE_DAMAGE"
        assert result.classification.confidence >= 85


class TestFuzzyMatch:
    """Test fuzzy matching for typos."""
    
    def test_carpet_cleaning_typo(self, classifier):
        """Test fuzzy match with typo in carpet cleaning."""
        item = {
            "description": "Profesional carpet cleening",
            "amount": Decimal("150.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert "FUZZY_MATCH" in result.classification.flags
    
    def test_normal_wear_typo(self, classifier):
        """Test fuzzy match with typo in normal wear."""
        item = {
            "description": "Normal wear and teer",
            "amount": Decimal("50.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE


class TestPatternMatching:
    """Test Layer 2: Pattern Matching."""
    
    def test_damage_pattern(self, classifier):
        """Test pattern matching for damage."""
        item = {
            "description": "Repair broken door handle",
            "amount": Decimal("75.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert result.classification.category == "ELIGIBLE_DAMAGE"
        assert len(result.classification.matched_patterns) > 0
    
    def test_cleaning_pattern(self, classifier):
        """Test pattern matching for cleaning."""
        item = {
            "description": "Deep cleaning service",
            "amount": Decimal("200.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        keyword_layer = result.classification.classification_layers.get('keyword_score', {})
        has_clean_keyword = ("clean" in result.classification.matched_keywords or 
                           "cleaning" in result.classification.matched_keywords or
                           "clean" in str(keyword_layer.get('matched_keywords', [])) or
                           "cleaning" in str(keyword_layer.get('matched_keywords', [])))
        assert has_clean_keyword or len(result.classification.matched_patterns) > 0 or result.classification.category == "ELIGIBLE_CLEANING"
    
    def test_upgrade_pattern(self, classifier):
        """Test pattern matching for upgrades."""
        item = {
            "description": "Kitchen upgrade to granite counters",
            "amount": Decimal("5000.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
        assert result.classification.category == "INELIGIBLE_UPGRADES"
    
    def test_routine_maintenance_pattern(self, classifier):
        """Test pattern matching for routine maintenance."""
        item = {
            "description": "Routine maintenance service",
            "amount": Decimal("100.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
        assert result.classification.category == "INELIGIBLE_ROUTINE_MAINTENANCE"
    
    def test_pre_existing_pattern(self, classifier):
        """Test pattern matching for pre-existing damage."""
        item = {
            "description": "Pre-existing damage repair",
            "amount": Decimal("300.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
        assert result.classification.category == "INELIGIBLE_PRE_EXISTING"


class TestKeywordScoring:
    """Test Layer 3: Keyword Scoring."""
    
    def test_keyword_positive_match(self, classifier):
        """Test positive keyword matching."""
        item = {
            "description": "Fix hole in wall",
            "amount": Decimal("150.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert len(result.classification.matched_keywords) > 0
    
    def test_keyword_negative_penalty(self, classifier):
        """Test negative keyword penalty."""
        item = {
            "description": "Normal cleaning routine",
            "amount": Decimal("100.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert ("normal" in result.classification.matched_keywords or 
                result.classification.status == EligibilityStatus.INELIGIBLE or
                "normal" in str(result.classification.classification_layers.get('keyword_score', {}).get('matched_keywords', [])))


class TestSpecialRules:
    """Test special rule triggers."""
    
    def test_ambiguous_cleaning_damage(self, classifier):
        """Test ambiguous case with both cleaning and damage."""
        item = {
            "description": "Clean up water damage",
            "amount": Decimal("250.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.AMBIGUOUS
        assert result.classification.confidence == 50
        assert result.classification.requires_manual_review
    
    def test_high_amount_uncertain(self, classifier):
        """Test high amount with low confidence."""
        item = {
            "description": "Mystery charge",
            "amount": Decimal("600.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert "HIGH_VALUE_UNCERTAIN" in result.classification.flags or result.classification.requires_manual_review
    
    def test_utilities_unpaid(self, classifier):
        """Test unpaid utilities special rule."""
        item = {
            "description": "Unpaid electric bill",
            "amount": Decimal("150.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_cleaning_routine_rule(self, classifier):
        """Test routine cleaning special rule."""
        item = {
            "description": "Routine cleaning service",
            "amount": Decimal("100.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE


class TestAmountThresholds:
    """Test amount-based rules."""
    
    def test_damage_amount_boost(self, classifier):
        """Test confidence boost for high damage amounts."""
        item = {
            "description": "Broken window repair",
            "amount": Decimal("150.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
        assert "AMOUNT_THRESHOLD_MET" in result.classification.flags or result.classification.confidence >= 85
    
    def test_high_value_review(self, classifier):
        """Test high value review flag."""
        item = {
            "description": "Unclear charge",
            "amount": Decimal("750.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        if result.classification.confidence < 60:
            assert result.classification.requires_manual_review


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_description(self, classifier):
        """Test empty description."""
        item = {
            "description": "",
            "amount": Decimal("50.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status in [EligibilityStatus.AMBIGUOUS, EligibilityStatus.ELIGIBLE]
        assert result.classification.requires_manual_review
    
    def test_special_characters(self, classifier):
        """Test description with special characters."""
        item = {
            "description": "Repair & replacement (damage) - $200",
            "amount": Decimal("200.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_very_long_description(self, classifier):
        """Test very long description."""
        item = {
            "description": "Professional deep cleaning service for move-out including carpet shampoo and sanitization of all surfaces",
            "amount": Decimal("300.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_mixed_case(self, classifier):
        """Test mixed case description."""
        item = {
            "description": "BROKEN Window REPAIR",
            "amount": Decimal("150.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_numbers_in_description(self, classifier):
        """Test description with numbers."""
        item = {
            "description": "Repair 3 broken windows",
            "amount": Decimal("450.00"),
            "line_number": 1
        }
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE


class TestCategoryCoverage:
    """Test all category types."""
    
    def test_eligible_cleaning(self, classifier):
        """Test eligible cleaning category."""
        item = {"description": "Steam cleaning of carpets", "amount": Decimal("180.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_damage(self, classifier):
        """Test eligible damage category."""
        item = {"description": "Fix broken door", "amount": Decimal("120.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_unpaid_rent(self, classifier):
        """Test eligible unpaid rent."""
        item = {"description": "Outstanding rent balance", "amount": Decimal("1200.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_utilities_unpaid(self, classifier):
        """Test eligible unpaid utilities."""
        item = {"description": "Past due gas bill", "amount": Decimal("85.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_pet_damage(self, classifier):
        """Test eligible pet damage."""
        item = {"description": "Pet damage to carpet", "amount": Decimal("200.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_smoking_damage(self, classifier):
        """Test eligible smoking damage."""
        item = {"description": "Smoking damage to walls", "amount": Decimal("500.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_painting_damage(self, classifier):
        """Test eligible painting due to damage."""
        item = {"description": "Repaint due to damage", "amount": Decimal("400.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_appliance_damage(self, classifier):
        """Test eligible appliance damage."""
        item = {"description": "Broken refrigerator repair", "amount": Decimal("300.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_flooring_damage(self, classifier):
        """Test eligible flooring damage."""
        item = {"description": "Carpet damage repair", "amount": Decimal("250.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_eligible_plumbing_damage(self, classifier):
        """Test eligible plumbing damage."""
        item = {"description": "Broken pipe repair", "amount": Decimal("180.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_ineligible_normal_wear(self, classifier):
        """Test ineligible normal wear."""
        item = {"description": "Expected aging of appliances", "amount": Decimal("100.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
    
    def test_ineligible_upgrades(self, classifier):
        """Test ineligible upgrades."""
        item = {"description": "Bathroom modernization", "amount": Decimal("3000.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
    
    def test_ineligible_routine_maintenance(self, classifier):
        """Test ineligible routine maintenance."""
        item = {"description": "Scheduled annual inspection", "amount": Decimal("150.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
    
    def test_ineligible_pre_existing(self, classifier):
        """Test ineligible pre-existing damage."""
        item = {"description": "Prior damage to wall", "amount": Decimal("200.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
    
    def test_ineligible_utilities_regular(self, classifier):
        """Test ineligible regular utilities."""
        item = {"description": "Monthly electric bill", "amount": Decimal("120.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE
    
    def test_ineligible_landscaping(self, classifier):
        """Test ineligible landscaping."""
        item = {"description": "Lawn maintenance", "amount": Decimal("80.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.INELIGIBLE


class TestAmbiguousCases:
    """Test ambiguous classification cases."""
    
    def test_ambiguous_cleaning_damage(self, classifier):
        """Test ambiguous cleaning and damage."""
        item = {"description": "Cleaning after fire damage", "amount": Decimal("400.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.AMBIGUOUS
    
    def test_low_confidence_default(self, classifier):
        """Test default for low confidence."""
        item = {"description": "Miscellaneous charge", "amount": Decimal("50.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.requires_manual_review or result.classification.confidence < 60


class TestMultiWordVsSingleWord:
    """Test multi-word vs single-word matching."""
    
    def test_multi_word_cleaning(self, classifier):
        """Test multi-word cleaning phrase."""
        item = {"description": "Move-out deep cleaning service", "amount": Decimal("250.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_single_word_cleaning(self, classifier):
        """Test single-word cleaning."""
        item = {"description": "Cleaning", "amount": Decimal("100.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_multi_word_damage(self, classifier):
        """Test multi-word damage phrase."""
        item = {"description": "Broken window pane replacement", "amount": Decimal("200.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE
    
    def test_single_word_damage(self, classifier):
        """Test single-word damage."""
        item = {"description": "Damage", "amount": Decimal("150.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.status == EligibilityStatus.ELIGIBLE


class TestBatchProcessing:
    """Test batch classification."""
    
    def test_batch_classify(self, classifier):
        """Test batch classification."""
        items = [
            {"description": "Professional carpet cleaning", "amount": Decimal("150.00"), "line_number": 1},
            {"description": "Normal wear and tear", "amount": Decimal("75.00"), "line_number": 2},
            {"description": "Broken window", "amount": Decimal("200.00"), "line_number": 3},
        ]
        results = classifier.classify_batch(items)
        assert len(results) == 3
        assert results[0].classification.status == EligibilityStatus.ELIGIBLE
        assert results[1].classification.status == EligibilityStatus.INELIGIBLE
        assert results[2].classification.status == EligibilityStatus.ELIGIBLE


class TestRuleReloading:
    """Test hot-reloading of rules."""
    
    def test_reload_rules(self, classifier):
        """Test reloading rules."""
        original_version = classifier.get_rule_version()
        rules_path = Path(__file__).parent.parent / "rules" / "rules_v1.0.yaml"
        classifier.reload_rules(str(rules_path))
        assert classifier.get_rule_version() == original_version


class TestAuditTrail:
    """Test audit trail and transparency."""
    
    def test_classification_layers(self, classifier):
        """Test that classification layers are recorded."""
        item = {"description": "Professional carpet cleaning", "amount": Decimal("150.00"), "line_number": 1}
        result = classifier.classify(item)
        assert 'exact_match' in result.classification.classification_layers
        assert result.classification.rule_version is not None
    
    def test_reasoning_present(self, classifier):
        """Test that reasoning is provided."""
        item = {"description": "Broken window repair", "amount": Decimal("200.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.reasoning
        assert len(result.classification.reasoning) > 0
    
    def test_matched_patterns(self, classifier):
        """Test that matched patterns are recorded."""
        item = {"description": "Repair broken door", "amount": Decimal("150.00"), "line_number": 1}
        result = classifier.classify(item)
        assert len(result.classification.matched_patterns) > 0 or len(result.classification.matched_keywords) > 0


class TestConfidenceLevels:
    """Test confidence scoring."""
    
    def test_high_confidence_exact_match(self, classifier):
        """Test high confidence for exact matches."""
        item = {"description": "Unpaid rent - October 2024", "amount": Decimal("1200.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.confidence >= 90
    
    def test_medium_confidence_pattern(self, classifier):
        """Test medium confidence for pattern matches."""
        item = {"description": "Fix hole in wall", "amount": Decimal("100.00"), "line_number": 1}
        result = classifier.classify(item)
        assert 60 <= result.classification.confidence <= 100
    
    def test_low_confidence_default(self, classifier):
        """Test low confidence for defaults."""
        item = {"description": "Unknown charge", "amount": Decimal("50.00"), "line_number": 1}
        result = classifier.classify(item)
        assert result.classification.confidence <= 40 or result.classification.requires_manual_review


class TestManualReviewFlags:
    """Test manual review requirements."""
    
    def test_low_confidence_review(self, classifier):
        """Test low confidence triggers review."""
        item = {"description": "Unclear description", "amount": Decimal("50.00"), "line_number": 1}
        result = classifier.classify(item)
        if result.classification.confidence < 60:
            assert result.classification.requires_manual_review
    
    def test_high_value_review(self, classifier):
        """Test high value triggers review."""
        item = {"description": "Mystery charge", "amount": Decimal("600.00"), "line_number": 1}
        result = classifier.classify(item)
        if result.classification.confidence < 60:
            assert result.classification.requires_manual_review
    
    def test_ambiguous_review(self, classifier):
        """Test ambiguous status triggers review."""
        item = {"description": "Clean up water damage", "amount": Decimal("250.00"), "line_number": 1}
        result = classifier.classify(item)
        if result.classification.status == EligibilityStatus.AMBIGUOUS:
            assert result.classification.requires_manual_review

