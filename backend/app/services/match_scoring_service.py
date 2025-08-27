"""
Match Scoring Service - Advanced confidence scoring and match evaluation.

This service provides sophisticated confidence scoring for text matches by combining
multiple factors including fuzzy matching confidence, OCR confidence, context
relevance, pattern validation, and text quality assessment.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import Enum
from dataclasses import dataclass, field
import statistics
from collections import defaultdict

from ..utils.text_processing import (
    text_quality_assessor, text_comparator, text_normalizer,
    measure_processing_time
)

logger = logging.getLogger(__name__)


class ScoringFactor(Enum):
    """Factors that contribute to confidence scoring."""
    FUZZY_CONFIDENCE = "fuzzy_confidence"
    OCR_CONFIDENCE = "ocr_confidence"
    PATTERN_VALIDATION = "pattern_validation"
    CONTEXT_RELEVANCE = "context_relevance"
    TEXT_QUALITY = "text_quality"
    POSITION_CONSISTENCY = "position_consistency"
    LENGTH_APPROPRIATENESS = "length_appropriateness"
    FREQUENCY_ANALYSIS = "frequency_analysis"


class ConfidenceLevel(Enum):
    """Confidence levels for matches."""
    VERY_HIGH = "very_high"      # 0.95 - 1.0
    HIGH = "high"                # 0.85 - 0.94
    MEDIUM = "medium"            # 0.70 - 0.84
    LOW = "low"                  # 0.50 - 0.69
    VERY_LOW = "very_low"        # 0.0 - 0.49


@dataclass
class ScoringWeights:
    """Weights for different scoring factors."""
    fuzzy_confidence: float = 0.35
    ocr_confidence: float = 0.20
    pattern_validation: float = 0.15
    context_relevance: float = 0.10
    text_quality: float = 0.10
    position_consistency: float = 0.05
    length_appropriateness: float = 0.03
    frequency_analysis: float = 0.02
    
    def __post_init__(self):
        """Validate that weights sum to 1.0."""
        total = sum(vars(self).values())
        if abs(total - 1.0) > 0.001:
            logger.warning(f"Scoring weights sum to {total:.3f}, not 1.0. Normalizing...")
            # Normalize weights
            for attr_name in vars(self):
                setattr(self, attr_name, getattr(self, attr_name) / total)


@dataclass
class ConfidenceBreakdown:
    """Detailed breakdown of confidence scoring components."""
    fuzzy_confidence: float = 0.0
    ocr_confidence: float = 0.0
    pattern_validation_score: float = 0.0
    context_relevance_score: float = 0.0
    text_quality_score: float = 0.0
    position_consistency_score: float = 0.0
    length_appropriateness_score: float = 0.0
    frequency_analysis_score: float = 0.0
    raw_weighted_score: float = 0.0
    calibrated_score: float = 0.0
    final_confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.VERY_LOW
    factors_used: List[str] = field(default_factory=list)
    scoring_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class MatchForScoring:
    """Match data structure for scoring analysis."""
    search_term: str
    matched_text: str
    page_number: int
    position_start: int
    position_end: int
    context: str
    match_type: str  # 'fuzzy', 'exact', 'pattern'
    fuzzy_confidence: Optional[float] = None
    ocr_confidence: Optional[float] = None
    pattern_validation: Optional[bool] = None
    algorithm_scores: Optional[Dict[str, float]] = None
    extraction_metadata: Optional[Dict[str, Any]] = None


class MatchScoringService:
    """Advanced confidence scoring service for text matches.
    
    This service evaluates match quality using multiple factors and provides
    detailed confidence scoring with calibration, threshold management, and
    statistical analysis capabilities.
    """
    
    def __init__(self, 
                 default_weights: Optional[ScoringWeights] = None,
                 enable_calibration: bool = True,
                 calibration_samples: int = 100):
        """Initialize the match scoring service.
        
        Args:
            default_weights: Default scoring weights. If None, uses standard weights.
            enable_calibration: Whether to enable confidence calibration
            calibration_samples: Number of samples to use for calibration
        """
        self.default_weights = default_weights or ScoringWeights()
        self.enable_calibration = enable_calibration
        self.calibration_samples = calibration_samples
        
        # Calibration data storage
        self.calibration_data: List[Dict[str, Any]] = []
        self.calibration_curve: Optional[Dict[str, Any]] = None
        
        # Document type specific weights
        self.document_type_weights: Dict[str, ScoringWeights] = {}
        
        # Confidence thresholds for different use cases
        self.confidence_thresholds = {
            'auto_approve': 0.95,
            'manual_review': 0.70,
            'low_confidence': 0.50
        }
        
        # Statistics tracking
        self.scoring_stats = {
            'total_scores_calculated': 0,
            'confidence_distribution': defaultdict(int),
            'factor_importance': defaultdict(list),
            'calibration_accuracy': 0.0,
            'average_processing_time': 0.0
        }
        
        logger.info(f"MatchScoringService initialized with calibration enabled: {enable_calibration}")
    
    @measure_processing_time
    def calculate_confidence_score(self,
                                 match_data: MatchForScoring,
                                 custom_weights: Optional[ScoringWeights] = None,
                                 document_type: Optional[str] = None) -> ConfidenceBreakdown:
        """Calculate comprehensive confidence score for a match.
        
        Args:
            match_data: Match data for scoring
            custom_weights: Optional custom weights for this calculation
            document_type: Optional document type for specialized scoring
            
        Returns:
            Detailed confidence breakdown
        """
        start_time = time.time()
        
        try:
            # Determine weights to use
            weights = self._get_scoring_weights(custom_weights, document_type)
            
            # Initialize confidence breakdown
            breakdown = ConfidenceBreakdown()
            
            # Calculate individual factor scores
            breakdown = self._calculate_fuzzy_confidence_factor(match_data, breakdown)
            breakdown = self._calculate_ocr_confidence_factor(match_data, breakdown)
            breakdown = self._calculate_pattern_validation_factor(match_data, breakdown)
            breakdown = self._calculate_context_relevance_factor(match_data, breakdown)
            breakdown = self._calculate_text_quality_factor(match_data, breakdown)
            breakdown = self._calculate_position_consistency_factor(match_data, breakdown)
            breakdown = self._calculate_length_appropriateness_factor(match_data, breakdown)
            breakdown = self._calculate_frequency_analysis_factor(match_data, breakdown)
            
            # Calculate weighted score
            breakdown.raw_weighted_score = (
                breakdown.fuzzy_confidence * weights.fuzzy_confidence +
                breakdown.ocr_confidence * weights.ocr_confidence +
                breakdown.pattern_validation_score * weights.pattern_validation +
                breakdown.context_relevance_score * weights.context_relevance +
                breakdown.text_quality_score * weights.text_quality +
                breakdown.position_consistency_score * weights.position_consistency +
                breakdown.length_appropriateness_score * weights.length_appropriateness +
                breakdown.frequency_analysis_score * weights.frequency_analysis
            )
            
            # Apply calibration if enabled
            if self.enable_calibration and self.calibration_curve:
                breakdown.calibrated_score = self._apply_calibration(breakdown.raw_weighted_score)
            else:
                breakdown.calibrated_score = breakdown.raw_weighted_score
            
            # Final confidence is the calibrated score
            breakdown.final_confidence = max(0.0, min(1.0, breakdown.calibrated_score))
            
            # Determine confidence level
            breakdown.confidence_level = self._determine_confidence_level(breakdown.final_confidence)
            
            # Add metadata
            processing_time = time.time() - start_time
            breakdown.scoring_metadata = {
                'processing_time': processing_time,
                'weights_used': vars(weights),
                'document_type': document_type,
                'calibration_applied': self.enable_calibration and self.calibration_curve is not None,
                'match_type': match_data.match_type,
                'factors_considered': len(breakdown.factors_used)
            }
            
            # Update statistics
            self._update_scoring_statistics(breakdown, processing_time)
            
            return breakdown
            
        except Exception as e:
            logger.error(f"Error calculating confidence score: {e}")
            # Return minimum confidence breakdown
            return ConfidenceBreakdown(
                final_confidence=0.0,
                confidence_level=ConfidenceLevel.VERY_LOW,
                scoring_metadata={'error': str(e)}
            )
    
    def _get_scoring_weights(self, custom_weights: Optional[ScoringWeights], document_type: Optional[str]) -> ScoringWeights:
        """Get appropriate scoring weights.
        
        Args:
            custom_weights: Custom weights provided for this calculation
            document_type: Document type for specialized weights
            
        Returns:
            Scoring weights to use
        """
        if custom_weights:
            return custom_weights
        elif document_type and document_type in self.document_type_weights:
            return self.document_type_weights[document_type]
        else:
            return self.default_weights\n    \n    def _calculate_fuzzy_confidence_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate fuzzy matching confidence factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            if match_data.fuzzy_confidence is not None:\n                # Convert percentage to decimal if needed\n                confidence = match_data.fuzzy_confidence\n                if confidence > 1.0:\n                    confidence = confidence / 100.0\n                \n                breakdown.fuzzy_confidence = confidence\n                breakdown.factors_used.append(ScoringFactor.FUZZY_CONFIDENCE.value)\n                \n                # Additional analysis if algorithm scores available\n                if match_data.algorithm_scores:\n                    # Use weighted average of different algorithms\n                    algorithm_weights = {\n                        'ratio': 0.3,\n                        'partial_ratio': 0.2,\n                        'token_sort_ratio': 0.3,\n                        'token_set_ratio': 0.2\n                    }\n                    \n                    weighted_score = 0.0\n                    total_weight = 0.0\n                    \n                    for alg, score in match_data.algorithm_scores.items():\n                        if alg in algorithm_weights:\n                            weight = algorithm_weights[alg]\n                            weighted_score += (score / 100.0) * weight\n                            total_weight += weight\n                    \n                    if total_weight > 0:\n                        breakdown.fuzzy_confidence = weighted_score / total_weight\n            else:\n                # No fuzzy confidence available\n                breakdown.fuzzy_confidence = 0.5  # Neutral score\n                \n        except Exception as e:\n            logger.debug(f\"Error calculating fuzzy confidence factor: {e}\")\n            breakdown.fuzzy_confidence = 0.5\n        \n        return breakdown\n    \n    def _calculate_ocr_confidence_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate OCR confidence factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            if match_data.ocr_confidence is not None:\n                # Convert percentage to decimal if needed\n                confidence = match_data.ocr_confidence\n                if confidence > 1.0:\n                    confidence = confidence / 100.0\n                \n                breakdown.ocr_confidence = confidence\n                breakdown.factors_used.append(ScoringFactor.OCR_CONFIDENCE.value)\n            else:\n                # No OCR confidence - assume text layer extraction\n                breakdown.ocr_confidence = 1.0  # Text layer is fully confident\n                \n        except Exception as e:\n            logger.debug(f\"Error calculating OCR confidence factor: {e}\")\n            breakdown.ocr_confidence = 0.8  # Default high confidence for text layer\n        \n        return breakdown\n    \n    def _calculate_pattern_validation_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate pattern validation factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            if match_data.match_type == 'pattern':\n                if match_data.pattern_validation is not None:\n                    breakdown.pattern_validation_score = 1.0 if match_data.pattern_validation else 0.2\n                    breakdown.factors_used.append(ScoringFactor.PATTERN_VALIDATION.value)\n                else:\n                    breakdown.pattern_validation_score = 0.7  # Assume basic validation passed\n            else:\n                # Not a pattern match - neutral score\n                breakdown.pattern_validation_score = 0.8\n                \n        except Exception as e:\n            logger.debug(f\"Error calculating pattern validation factor: {e}\")\n            breakdown.pattern_validation_score = 0.5\n        \n        return breakdown\n    \n    def _calculate_context_relevance_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate context relevance factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            context_score = 0.5  # Default neutral score\n            \n            if match_data.context:\n                # Analyze context for relevance\n                context_score = self._analyze_context_quality(match_data.context, match_data.search_term, match_data.matched_text)\n            \n            breakdown.context_relevance_score = context_score\n            breakdown.factors_used.append(ScoringFactor.CONTEXT_RELEVANCE.value)\n            \n        except Exception as e:\n            logger.debug(f\"Error calculating context relevance factor: {e}\")\n            breakdown.context_relevance_score = 0.5\n        \n        return breakdown\n    \n    def _analyze_context_quality(self, context: str, search_term: str, matched_text: str) -> float:\n        \"\"\"Analyze the quality and relevance of match context.\n        \n        Args:\n            context: Context around the match\n            search_term: Original search term\n            matched_text: Matched text\n            \n        Returns:\n            Context relevance score (0.0 to 1.0)\n        \"\"\"\n        try:\n            base_score = 0.5\n            \n            # Check context length (reasonable context is good)\n            if len(context.strip()) >= 20:\n                base_score += 0.1\n            \n            # Check for meaningful surrounding words\n            context_words = context.lower().split()\n            search_words = search_term.lower().split()\n            \n            # Look for related terms\n            related_terms_found = 0\n            for search_word in search_words:\n                if any(abs(len(word) - len(search_word)) <= 2 and \n                      text_comparator.calculate_similarity(word, search_word, 'levenshtein') > 0.7\n                      for word in context_words):\n                    related_terms_found += 1\n            \n            if related_terms_found > 0:\n                base_score += min(0.2, related_terms_found * 0.1)\n            \n            # Check for formatting context (headers, labels, etc.)\n            formatting_indicators = [':', '=', '->', '=>', '|', '#']\n            if any(indicator in context for indicator in formatting_indicators):\n                base_score += 0.1\n            \n            # Penalty for very repetitive context\n            if len(set(context_words)) < len(context_words) * 0.3:\n                base_score -= 0.1\n            \n            return max(0.0, min(1.0, base_score))\n            \n        except Exception as e:\n            logger.debug(f\"Error analyzing context quality: {e}\")\n            return 0.5\n    \n    def _calculate_text_quality_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate text quality factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            # Assess quality of the matched text\n            text_quality = text_quality_assessor.assess_character_confidence(match_data.matched_text)\n            \n            # Additional quality checks\n            coherence = text_quality_assessor.assess_coherence(match_data.matched_text)\n            completeness = text_quality_assessor.assess_completeness(match_data.matched_text)\n            \n            # Combine quality measures\n            breakdown.text_quality_score = (text_quality + coherence + completeness) / 3.0\n            breakdown.factors_used.append(ScoringFactor.TEXT_QUALITY.value)\n            \n        except Exception as e:\n            logger.debug(f\"Error calculating text quality factor: {e}\")\n            breakdown.text_quality_score = 0.7  # Default reasonable quality\n        \n        return breakdown\n    \n    def _calculate_position_consistency_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate position consistency factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            # Check if position makes sense\n            position_score = 0.8  # Default good score\n            \n            # Check for reasonable position values\n            if match_data.position_start < 0 or match_data.position_end <= match_data.position_start:\n                position_score = 0.2\n            else:\n                # Check text length consistency\n                expected_length = match_data.position_end - match_data.position_start\n                actual_length = len(match_data.matched_text)\n                \n                if abs(expected_length - actual_length) <= 2:\n                    position_score = 0.9\n                elif abs(expected_length - actual_length) <= 5:\n                    position_score = 0.7\n                else:\n                    position_score = 0.5\n            \n            breakdown.position_consistency_score = position_score\n            breakdown.factors_used.append(ScoringFactor.POSITION_CONSISTENCY.value)\n            \n        except Exception as e:\n            logger.debug(f\"Error calculating position consistency factor: {e}\")\n            breakdown.position_consistency_score = 0.7\n        \n        return breakdown\n    \n    def _calculate_length_appropriateness_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate length appropriateness factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            search_length = len(match_data.search_term)\n            match_length = len(match_data.matched_text)\n            \n            # Calculate length ratio\n            if search_length > 0:\n                length_ratio = match_length / search_length\n                \n                # Optimal ratio is around 0.8 to 1.5\n                if 0.8 <= length_ratio <= 1.5:\n                    length_score = 0.9\n                elif 0.5 <= length_ratio <= 2.0:\n                    length_score = 0.7\n                elif 0.3 <= length_ratio <= 3.0:\n                    length_score = 0.5\n                else:\n                    length_score = 0.3\n            else:\n                length_score = 0.5\n            \n            breakdown.length_appropriateness_score = length_score\n            breakdown.factors_used.append(ScoringFactor.LENGTH_APPROPRIATENESS.value)\n            \n        except Exception as e:\n            logger.debug(f\"Error calculating length appropriateness factor: {e}\")\n            breakdown.length_appropriateness_score = 0.7\n        \n        return breakdown\n    \n    def _calculate_frequency_analysis_factor(self, match_data: MatchForScoring, breakdown: ConfidenceBreakdown) -> ConfidenceBreakdown:\n        \"\"\"Calculate frequency analysis factor.\n        \n        Args:\n            match_data: Match data\n            breakdown: Confidence breakdown to update\n            \n        Returns:\n            Updated confidence breakdown\n        \"\"\"\n        try:\n            # This would typically analyze frequency patterns across the document\n            # For now, use a simple heuristic based on match characteristics\n            frequency_score = 0.6  # Default score\n            \n            # Boost for exact matches\n            if match_data.match_type == 'exact':\n                frequency_score = 0.8\n            \n            # Consider if this looks like a common pattern\n            text_lower = match_data.matched_text.lower()\n            \n            # Penalty for very common words that might be false positives\n            common_words = {'the', 'and', 'or', 'of', 'to', 'in', 'a', 'an', 'is', 'are', 'was', 'were'}\n            if text_lower in common_words:\n                frequency_score = 0.2\n            \n            breakdown.frequency_analysis_score = frequency_score\n            breakdown.factors_used.append(ScoringFactor.FREQUENCY_ANALYSIS.value)\n            \n        except Exception as e:\n            logger.debug(f\"Error calculating frequency analysis factor: {e}\")\n            breakdown.frequency_analysis_score = 0.6\n        \n        return breakdown\n    \n    def _apply_calibration(self, raw_score: float) -> float:\n        \"\"\"Apply confidence calibration to raw score.\n        \n        Args:\n            raw_score: Raw confidence score\n            \n        Returns:\n            Calibrated confidence score\n        \"\"\"\n        try:\n            if not self.calibration_curve:\n                return raw_score\n            \n            # Simple linear calibration (could be enhanced with more sophisticated methods)\n            slope = self.calibration_curve.get('slope', 1.0)\n            intercept = self.calibration_curve.get('intercept', 0.0)\n            \n            calibrated = raw_score * slope + intercept\n            return max(0.0, min(1.0, calibrated))\n            \n        except Exception as e:\n            logger.debug(f\"Error applying calibration: {e}\")\n            return raw_score\n    \n    def _determine_confidence_level(self, confidence: float) -> ConfidenceLevel:\n        \"\"\"Determine confidence level based on score.\n        \n        Args:\n            confidence: Confidence score (0.0 to 1.0)\n            \n        Returns:\n            Confidence level enum\n        \"\"\"\n        if confidence >= 0.95:\n            return ConfidenceLevel.VERY_HIGH\n        elif confidence >= 0.85:\n            return ConfidenceLevel.HIGH\n        elif confidence >= 0.70:\n            return ConfidenceLevel.MEDIUM\n        elif confidence >= 0.50:\n            return ConfidenceLevel.LOW\n        else:\n            return ConfidenceLevel.VERY_LOW\n    \n    def _update_scoring_statistics(self, breakdown: ConfidenceBreakdown, processing_time: float):\n        \"\"\"Update scoring statistics.\n        \n        Args:\n            breakdown: Confidence breakdown\n            processing_time: Time taken for scoring\n        \"\"\"\n        try:\n            self.scoring_stats['total_scores_calculated'] += 1\n            self.scoring_stats['confidence_distribution'][breakdown.confidence_level.value] += 1\n            \n            # Update average processing time\n            total_scores = self.scoring_stats['total_scores_calculated']\n            current_avg = self.scoring_stats['average_processing_time']\n            self.scoring_stats['average_processing_time'] = (\n                (current_avg * (total_scores - 1) + processing_time) / total_scores\n            )\n            \n            # Track factor importance\n            for factor in breakdown.factors_used:\n                self.scoring_stats['factor_importance'][factor].append(breakdown.final_confidence)\n            \n        except Exception as e:\n            logger.debug(f\"Error updating scoring statistics: {e}\")\n    \n    def calibrate_confidence_scoring(self, validation_data: List[Dict[str, Any]]) -> Dict[str, Any]:\n        \"\"\"Calibrate confidence scoring using validation data.\n        \n        Args:\n            validation_data: List of validation samples with 'match_data', 'expected_confidence'\n            \n        Returns:\n            Calibration results\n        \"\"\"\n        try:\n            if len(validation_data) < 10:\n                logger.warning(\"Insufficient validation data for calibration\")\n                return {'success': False, 'error': 'Insufficient validation data'}\n            \n            predicted_scores = []\n            actual_scores = []\n            \n            for sample in validation_data:\n                match_data = sample['match_data']\n                expected_confidence = sample['expected_confidence']\n                \n                # Calculate predicted confidence\n                breakdown = self.calculate_confidence_score(match_data)\n                predicted_scores.append(breakdown.raw_weighted_score)\n                actual_scores.append(expected_confidence)\n            \n            # Calculate calibration curve (simple linear regression)\n            if len(predicted_scores) >= 2:\n                # Simple linear calibration\n                from statistics import linear_regression\n                slope, intercept = linear_regression(predicted_scores, actual_scores)\n                \n                self.calibration_curve = {\n                    'slope': slope,\n                    'intercept': intercept,\n                    'samples_used': len(predicted_scores)\n                }\n                \n                # Calculate calibration accuracy\n                calibrated_scores = [score * slope + intercept for score in predicted_scores]\n                mae = sum(abs(pred - actual) for pred, actual in zip(calibrated_scores, actual_scores)) / len(actual_scores)\n                \n                self.scoring_stats['calibration_accuracy'] = 1.0 - mae\n                \n                return {\n                    'success': True,\n                    'slope': slope,\n                    'intercept': intercept,\n                    'mean_absolute_error': mae,\n                    'samples_used': len(predicted_scores),\n                    'calibration_accuracy': self.scoring_stats['calibration_accuracy']\n                }\n            else:\n                return {'success': False, 'error': 'Unable to calculate calibration curve'}\n                \n        except ImportError:\n            logger.error(\"statistics.linear_regression not available. Using simple calibration.\")\n            # Fallback to simple mean adjustment\n            if len(validation_data) > 0:\n                predicted_mean = statistics.mean([self.calculate_confidence_score(s['match_data']).raw_weighted_score for s in validation_data])\n                actual_mean = statistics.mean([s['expected_confidence'] for s in validation_data])\n                \n                self.calibration_curve = {\n                    'slope': 1.0,\n                    'intercept': actual_mean - predicted_mean,\n                    'samples_used': len(validation_data)\n                }\n                \n                return {\n                    'success': True,\n                    'method': 'mean_adjustment',\n                    'adjustment': actual_mean - predicted_mean,\n                    'samples_used': len(validation_data)\n                }\n            \n            return {'success': False, 'error': 'Calibration failed'}\n        except Exception as e:\n            logger.error(f\"Error during confidence calibration: {e}\")\n            return {'success': False, 'error': str(e)}\n    \n    def set_document_type_weights(self, document_type: str, weights: ScoringWeights):\n        \"\"\"Set custom weights for a specific document type.\n        \n        Args:\n            document_type: Document type identifier\n            weights: Scoring weights for this document type\n        \"\"\"\n        self.document_type_weights[document_type] = weights\n        logger.info(f\"Set custom weights for document type: {document_type}\")\n    \n    def update_confidence_thresholds(self, thresholds: Dict[str, float]):\n        \"\"\"Update confidence thresholds for different use cases.\n        \n        Args:\n            thresholds: Dictionary of threshold names and values\n        \"\"\"\n        self.confidence_thresholds.update(thresholds)\n        logger.info(f\"Updated confidence thresholds: {thresholds}\")\n    \n    def get_scoring_statistics(self) -> Dict[str, Any]:\n        \"\"\"Get comprehensive scoring statistics.\n        \n        Returns:\n            Dictionary with scoring statistics\n        \"\"\"\n        stats = self.scoring_stats.copy()\n        \n        # Calculate factor importance scores\n        factor_importance = {}\n        for factor, scores in stats['factor_importance'].items():\n            if scores:\n                factor_importance[factor] = {\n                    'average_contribution': statistics.mean(scores),\n                    'usage_count': len(scores),\n                    'min_contribution': min(scores),\n                    'max_contribution': max(scores)\n                }\n        \n        stats['factor_importance_analysis'] = factor_importance\n        \n        # Add calibration status\n        stats['calibration_enabled'] = self.enable_calibration\n        stats['calibration_active'] = self.calibration_curve is not None\n        \n        if self.calibration_curve:\n            stats['calibration_parameters'] = self.calibration_curve\n        \n        # Add threshold information\n        stats['confidence_thresholds'] = self.confidence_thresholds\n        stats['document_type_weights_configured'] = len(self.document_type_weights)\n        \n        return stats\n    \n    def analyze_confidence_trends(self, match_results: List[ConfidenceBreakdown]) -> Dict[str, Any]:\n        \"\"\"Analyze confidence scoring trends across multiple matches.\n        \n        Args:\n            match_results: List of confidence breakdowns to analyze\n            \n        Returns:\n            Dictionary with trend analysis\n        \"\"\"\n        try:\n            if not match_results:\n                return {'error': 'No match results provided'}\n            \n            confidences = [result.final_confidence for result in match_results]\n            \n            analysis = {\n                'total_matches': len(match_results),\n                'confidence_statistics': {\n                    'mean': statistics.mean(confidences),\n                    'median': statistics.median(confidences),\n                    'std_dev': statistics.stdev(confidences) if len(confidences) > 1 else 0,\n                    'min': min(confidences),\n                    'max': max(confidences)\n                },\n                'confidence_level_distribution': {\n                    level.value: sum(1 for result in match_results if result.confidence_level == level)\n                    for level in ConfidenceLevel\n                },\n                'factor_usage_frequency': {},\n                'processing_time_statistics': {}\n            }\n            \n            # Analyze factor usage\n            all_factors = []\n            processing_times = []\n            \n            for result in match_results:\n                all_factors.extend(result.factors_used)\n                if 'processing_time' in result.scoring_metadata:\n                    processing_times.append(result.scoring_metadata['processing_time'])\n            \n            factor_counts = defaultdict(int)\n            for factor in all_factors:\n                factor_counts[factor] += 1\n            \n            analysis['factor_usage_frequency'] = dict(factor_counts)\n            \n            if processing_times:\n                analysis['processing_time_statistics'] = {\n                    'mean': statistics.mean(processing_times),\n                    'median': statistics.median(processing_times),\n                    'min': min(processing_times),\n                    'max': max(processing_times)\n                }\n            \n            # Threshold analysis\n            analysis['threshold_analysis'] = {\n                'above_auto_approve': sum(1 for c in confidences if c >= self.confidence_thresholds['auto_approve']),\n                'needs_manual_review': sum(1 for c in confidences if self.confidence_thresholds['low_confidence'] <= c < self.confidence_thresholds['auto_approve']),\n                'low_confidence': sum(1 for c in confidences if c < self.confidence_thresholds['low_confidence'])\n            }\n            \n            return analysis\n            \n        except Exception as e:\n            logger.error(f\"Error analyzing confidence trends: {e}\")\n            return {'error': str(e)}\n    \n    def export_calibration_data(self) -> Dict[str, Any]:\n        \"\"\"Export calibration data for analysis or backup.\n        \n        Returns:\n            Dictionary with calibration data\n        \"\"\"\n        return {\n            'calibration_enabled': self.enable_calibration,\n            'calibration_curve': self.calibration_curve,\n            'calibration_samples': len(self.calibration_data),\n            'calibration_data': self.calibration_data[:100],  # Limit export size\n            'scoring_statistics': self.get_scoring_statistics()\n        }\n    \n    def import_calibration_data(self, calibration_data: Dict[str, Any]) -> bool:\n        \"\"\"Import calibration data from backup or external source.\n        \n        Args:\n            calibration_data: Calibration data dictionary\n            \n        Returns:\n            True if import was successful\n        \"\"\"\n        try:\n            if 'calibration_curve' in calibration_data:\n                self.calibration_curve = calibration_data['calibration_curve']\n            \n            if 'calibration_data' in calibration_data:\n                self.calibration_data.extend(calibration_data['calibration_data'])\n            \n            logger.info(\"Successfully imported calibration data\")\n            return True\n            \n        except Exception as e:\n            logger.error(f\"Error importing calibration data: {e}\")\n            return False