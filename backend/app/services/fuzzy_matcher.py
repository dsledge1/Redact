"""Enhanced fuzzy text matching service for Ultimate PDF redaction.

This service provides comprehensive fuzzy text matching with multiple algorithms,
configurable thresholds, advanced preprocessing, and integration capabilities.
"""

import re
import time
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from enum import Enum
from dataclasses import dataclass
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from fuzzywuzzy import fuzz, process

try:
    import nltk
    from nltk.stem import PorterStemmer, SnowballStemmer
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    import jellyfish
    PHONETIC_AVAILABLE = True
except ImportError:
    PHONETIC_AVAILABLE = False

from ..utils.text_processing import (
    text_preprocessor, text_comparator, text_normalizer,
    measure_processing_time
)

logger = logging.getLogger(__name__)


class MatchingAlgorithm(Enum):
    """Available fuzzy matching algorithms."""
    RATIO = "ratio"
    PARTIAL_RATIO = "partial_ratio"
    TOKEN_SORT_RATIO = "token_sort_ratio"
    TOKEN_SET_RATIO = "token_set_ratio"
    WEIGHTED_RATIO = "weighted_ratio"


class MatchingStrategy(Enum):
    """Text matching strategies."""
    FUZZY_ONLY = "fuzzy_only"
    EXACT_ONLY = "exact_only"
    HYBRID = "hybrid"
    PHONETIC = "phonetic"
    SEMANTIC = "semantic"


class TextPreprocessingMode(Enum):
    """Text preprocessing modes."""
    NONE = "none"
    BASIC = "basic"
    ADVANCED = "advanced"
    LINGUISTIC = "linguistic"


@dataclass
class MatchingConfiguration:
    """Configuration for fuzzy matching operations."""
    algorithm: MatchingAlgorithm = MatchingAlgorithm.TOKEN_SORT_RATIO
    threshold: int = 80
    high_confidence_threshold: int = 95
    strategy: MatchingStrategy = MatchingStrategy.HYBRID
    preprocessing_mode: TextPreprocessingMode = TextPreprocessingMode.BASIC
    case_sensitive: bool = False
    enable_stemming: bool = False
    enable_phonetic: bool = False
    context_window: int = 100
    max_candidates: int = 1000
    enable_clustering: bool = True
    negative_patterns: List[str] = None
    custom_thresholds: Dict[str, int] = None
    language: str = 'english'
    enable_parallel_processing: bool = True
    max_workers: int = 4

    def __post_init__(self):
        if self.negative_patterns is None:
            self.negative_patterns = []
        if self.custom_thresholds is None:
            self.custom_thresholds = {}


@dataclass
class MatchResult:
    """Enhanced match result with detailed metadata."""
    search_term: str
    matched_text: str
    confidence_score: float
    page_number: int
    needs_approval: bool
    match_context: str
    position_info: Dict[str, int]
    algorithm_used: str
    preprocessing_applied: List[str]
    match_type: str
    similarity_scores: Dict[str, float]
    ocr_confidence: Optional[float] = None
    context_relevance: Optional[float] = None
    cluster_id: Optional[str] = None
    processing_time: Optional[float] = None


class FuzzyMatcher:
    """Enhanced service class for fuzzy text matching with advanced capabilities.
    
    Features:
    - Multiple matching algorithms (ratio, partial, token-based)
    - Advanced text preprocessing (stemming, lemmatization, phonetic)
    - Configurable confidence thresholds per search term
    - Multi-language support
    - Match clustering and deduplication
    - OCR confidence integration
    - Parallel processing for large documents
    - Negative pattern filtering
    """
    
    DEFAULT_THRESHOLD = 80
    HIGH_CONFIDENCE_THRESHOLD = 95
    MIN_MATCH_LENGTH = 3
    
    def __init__(self, config: Optional[MatchingConfiguration] = None):
        """Initialize enhanced fuzzy matcher with comprehensive configuration.
        
        Args:
            config: Matching configuration object. If None, uses defaults.
        """
        self.config = config or MatchingConfiguration()
        
        # Validate configuration
        if not 0 <= self.config.threshold <= 100:
            raise ValueError("Threshold must be between 0 and 100")
        if not 0 <= self.config.high_confidence_threshold <= 100:
            raise ValueError("High confidence threshold must be between 0 and 100")
        
        # Initialize preprocessing tools
        self.preprocessor = text_preprocessor
        self.normalizer = text_normalizer
        self.comparator = text_comparator
        
        # Initialize NLTK components if available
        if NLTK_AVAILABLE and self.config.enable_stemming:
            try:
                self.stemmer = SnowballStemmer(self.config.language)
                self.english_stemmer = PorterStemmer()
            except:
                logger.warning("Failed to initialize stemmer")
                self.stemmer = None
                self.english_stemmer = None
        else:
            self.stemmer = None
            self.english_stemmer = None
        
        # Match clustering support
        self.match_clusters: Dict[str, List] = {}
        
        # Algorithm mapping
        self.algorithm_map = {
            MatchingAlgorithm.RATIO: fuzz.ratio,
            MatchingAlgorithm.PARTIAL_RATIO: fuzz.partial_ratio,
            MatchingAlgorithm.TOKEN_SORT_RATIO: fuzz.token_sort_ratio,
            MatchingAlgorithm.TOKEN_SET_RATIO: fuzz.token_set_ratio,
            MatchingAlgorithm.WEIGHTED_RATIO: fuzz.WRatio
        }
        
        logger.info(f"Enhanced FuzzyMatcher initialized with algorithm: {self.config.algorithm.value}, "
                   f"threshold: {self.config.threshold}, strategy: {self.config.strategy.value}")
    
    @measure_processing_time
    def find_matches(
        self, 
        search_terms: List[str], 
        text_pages: List[Dict[str, Any]],
        custom_config: Optional[MatchingConfiguration] = None,
        ocr_confidence_data: Optional[Dict[int, float]] = None
    ) -> List[MatchResult]:
        """Find enhanced fuzzy matches for search terms across PDF pages.
        
        Args:
            search_terms: List of terms to search for
            text_pages: List of page dictionaries with 'page_number' and 'text' keys
            custom_config: Optional custom configuration for this search
            ocr_confidence_data: Optional OCR confidence scores by page number
            
        Returns:
            List of enhanced MatchResult objects with detailed metadata
        """
        # Use custom config if provided
        config = custom_config or self.config
        all_matches = []
        start_time = time.time()
        
        try:
            # Validate and filter search terms
            valid_terms = self._validate_search_terms(search_terms)
            if not valid_terms:
                logger.warning("No valid search terms provided")
                return []
            
            # Apply negative pattern filtering
            filtered_terms = self._apply_negative_patterns(valid_terms, config.negative_patterns)
            
            # Preprocess pages for better matching
            preprocessed_pages = self._preprocess_pages(text_pages, config)
            
            if config.enable_parallel_processing and len(filtered_terms) > 1:
                all_matches = self._find_matches_parallel(
                    filtered_terms, preprocessed_pages, config, ocr_confidence_data
                )
            else:
                all_matches = self._find_matches_sequential(
                    filtered_terms, preprocessed_pages, config, ocr_confidence_data
                )
            
            # Post-process matches
            all_matches = self._post_process_matches(all_matches, config)
            
            # Apply match clustering if enabled
            if config.enable_clustering:
                all_matches = self._cluster_matches(all_matches)
            
            # Sort by confidence score (highest first) then by page number
            all_matches.sort(key=lambda x: (-x.confidence_score, x.page_number))
            
            total_time = time.time() - start_time
            logger.info(f"Found {len(all_matches)} matches in {total_time:.3f} seconds")
            
            return all_matches
            
        except Exception as e:
            logger.error(f"Error finding matches: {str(e)}")
            return []
    
    def _validate_search_terms(self, search_terms: List[str]) -> List[str]:
        """Validate and filter search terms.
        
        Args:
            search_terms: List of search terms
            
        Returns:
            List of valid search terms
        """
        valid_terms = []
        for term in search_terms:
            cleaned_term = term.strip()
            if len(cleaned_term) >= self.MIN_MATCH_LENGTH:
                valid_terms.append(cleaned_term)
            else:
                logger.warning(f"Skipping search term too short: '{term}'")
        return valid_terms
    
    def _apply_negative_patterns(self, search_terms: List[str], negative_patterns: List[str]) -> List[str]:
        """Apply negative patterns to filter out unwanted terms.
        
        Args:
            search_terms: List of search terms
            negative_patterns: List of patterns to exclude
            
        Returns:
            Filtered list of search terms
        """
        if not negative_patterns:
            return search_terms
        
        filtered_terms = []
        for term in search_terms:
            should_include = True
            for pattern in negative_patterns:
                try:
                    if re.search(pattern, term, re.IGNORECASE):
                        should_include = False
                        logger.debug(f"Excluding term '{term}' due to negative pattern '{pattern}'")
                        break
                except re.error:
                    logger.warning(f"Invalid negative pattern: {pattern}")
            
            if should_include:
                filtered_terms.append(term)
        
        return filtered_terms
    
    def _preprocess_pages(self, text_pages: List[Dict[str, Any]], config: MatchingConfiguration) -> List[Dict[str, Any]]:
        """Preprocess pages for enhanced matching.
        
        Args:
            text_pages: List of page dictionaries
            config: Matching configuration
            
        Returns:
            List of preprocessed page dictionaries
        """
        preprocessed_pages = []
        
        for page in text_pages:
            page_text = page.get('text', '')
            if not page_text.strip():
                preprocessed_pages.append(page)
                continue
            
            processed_text = self._preprocess_text(page_text, config)
            
            preprocessed_page = page.copy()
            preprocessed_page['processed_text'] = processed_text
            preprocessed_page['original_text'] = page_text
            preprocessed_pages.append(preprocessed_page)
        
        return preprocessed_pages
    
    def _preprocess_text(self, text: str, config: MatchingConfiguration) -> str:
        """Preprocess text based on configuration.
        
        Args:
            text: Input text
            config: Matching configuration
            
        Returns:
            Preprocessed text
        """
        if config.preprocessing_mode == TextPreprocessingMode.NONE:
            return text
        
        # Basic preprocessing
        processed = self.normalizer.normalize_unicode(text)
        processed = self.normalizer.normalize_whitespace(processed)
        
        if config.preprocessing_mode == TextPreprocessingMode.BASIC:
            return processed
        
        # Advanced preprocessing
        if not config.case_sensitive:
            processed = processed.lower()
        
        if config.preprocessing_mode == TextPreprocessingMode.LINGUISTIC and NLTK_AVAILABLE:
            # Tokenize and process linguistically
            tokens = self.preprocessor.tokenize_words(processed)
            
            # Apply stemming if enabled
            if config.enable_stemming and self.stemmer:
                tokens = [self.stemmer.stem(token) for token in tokens]
            
            # Remove stopwords
            tokens = self.preprocessor.remove_stop_words(tokens, config.language)
            
            processed = ' '.join(tokens)
        
        return processed
    
    def _find_matches_parallel(
        self, 
        search_terms: List[str], 
        text_pages: List[Dict[str, Any]],
        config: MatchingConfiguration,
        ocr_confidence_data: Optional[Dict[int, float]]
    ) -> List[MatchResult]:
        """Find matches using parallel processing.
        
        Args:
            search_terms: List of search terms
            text_pages: List of preprocessed page dictionaries
            config: Matching configuration
            ocr_confidence_data: OCR confidence data by page
            
        Returns:
            List of match results
        """
        all_matches = []
        
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            future_to_term = {
                executor.submit(self._find_term_matches, term, text_pages, config, ocr_confidence_data): term
                for term in search_terms
            }
            
            for future in as_completed(future_to_term):
                try:
                    term_matches = future.result()
                    all_matches.extend(term_matches)
                except Exception as e:
                    term = future_to_term[future]
                    logger.error(f"Error processing term '{term}': {e}")
        
        return all_matches
    
    def _find_matches_sequential(
        self, 
        search_terms: List[str], 
        text_pages: List[Dict[str, Any]],
        config: MatchingConfiguration,
        ocr_confidence_data: Optional[Dict[int, float]]
    ) -> List[MatchResult]:
        """Find matches using sequential processing.
        
        Args:
            search_terms: List of search terms
            text_pages: List of preprocessed page dictionaries
            config: Matching configuration
            ocr_confidence_data: OCR confidence data by page
            
        Returns:
            List of match results
        """
        all_matches = []
        
        for search_term in search_terms:
            try:
                term_matches = self._find_term_matches(
                    search_term, text_pages, config, ocr_confidence_data
                )
                all_matches.extend(term_matches)
            except Exception as e:
                logger.error(f"Error processing term '{search_term}': {e}")
        
        return all_matches
    
    def _find_term_matches(
        self, 
        search_term: str, 
        text_pages: List[Dict[str, Any]],
        config: MatchingConfiguration,
        ocr_confidence_data: Optional[Dict[int, float]] = None
    ) -> List[MatchResult]:
        """Find enhanced matches for a single search term across all pages.
        
        Args:
            search_term: Single term to search for
            text_pages: List of preprocessed page dictionaries
            config: Matching configuration
            ocr_confidence_data: OCR confidence data by page
            
        Returns:
            List of enhanced match results for this term
        """
        matches = []
        start_time = time.time()
        
        # Get custom threshold for this term if configured
        threshold = config.custom_thresholds.get(search_term, config.threshold)
        
        # Preprocess search term
        processed_term = self._preprocess_text(search_term, config)
        
        for page_data in text_pages:
            page_number = page_data.get('page_number', 1)
            page_text = page_data.get('processed_text') or page_data.get('text', '')
            original_text = page_data.get('original_text') or page_data.get('text', '')
            
            if not page_text.strip():
                continue
            
            # Get OCR confidence for this page
            page_ocr_confidence = None
            if ocr_confidence_data:
                page_ocr_confidence = ocr_confidence_data.get(page_number)
            
            page_matches = self._find_page_matches_enhanced(
                search_term,
                processed_term,
                page_text,
                original_text,
                page_number,
                config,
                threshold,
                page_ocr_confidence
            )
            matches.extend(page_matches)
        
        # Add processing time to matches
        processing_time = time.time() - start_time
        for match in matches:
            match.processing_time = processing_time / len(matches) if matches else processing_time
        
        return matches
    
    def _find_page_matches_enhanced(
        self,
        search_term: str,
        processed_term: str,
        page_text: str,
        original_text: str,
        page_number: int,
        config: MatchingConfiguration,
        threshold: int,
        ocr_confidence: Optional[float] = None
    ) -> List[MatchResult]:
        """Find enhanced matches for a search term within a single page.
        
        Args:
            search_term: Original search term
            processed_term: Preprocessed search term
            page_text: Preprocessed page text
            original_text: Original page text
            page_number: Page number for reference
            config: Matching configuration
            threshold: Threshold for this specific term
            ocr_confidence: OCR confidence for this page
            
        Returns:
            List of enhanced match results for this page
        """
        matches = []
        
        try:
            # Extract candidates for matching
            candidates = self._extract_candidates(
                page_text, len(processed_term.split())
            )
            
            if not candidates:
                return matches
            
            # Apply different matching strategies
            if config.strategy in [MatchingStrategy.FUZZY_ONLY, MatchingStrategy.HYBRID]:
                fuzzy_matches = self._find_fuzzy_matches(
                    processed_term, candidates, threshold, config
                )
                
                # Process fuzzy matches
                for matched_text, confidence_score, algorithm_scores in fuzzy_matches:
                    original_match = self._find_original_text(
                        matched_text, original_text, config.case_sensitive
                    )
                    
                    if original_match:
                        match_result = self._create_match_result(
                            search_term, original_match, confidence_score,
                            page_number, original_text, config, algorithm_scores,
                            ocr_confidence, "fuzzy"
                        )
                        matches.append(match_result)
            
            if config.strategy in [MatchingStrategy.EXACT_ONLY, MatchingStrategy.HYBRID]:
                exact_matches = self._find_exact_matches_enhanced(
                    search_term, original_text, page_number, config, ocr_confidence
                )
                matches.extend(exact_matches)
            
            if config.strategy == MatchingStrategy.PHONETIC and PHONETIC_AVAILABLE:
                phonetic_matches = self._find_phonetic_matches(
                    search_term, page_text, original_text, page_number, config, ocr_confidence
                )
                matches.extend(phonetic_matches)
            
            # Remove duplicates
            matches = self._remove_duplicate_matches_enhanced(matches)
            
        except Exception as e:
            logger.error(f"Error finding enhanced matches on page {page_number}: {str(e)}")
        
        return matches
    
    def _extract_candidates(self, text: str, term_word_count: int) -> List[str]:
        """Extract potential matching candidates from text.
        
        Args:
            text: Source text to extract from
            term_word_count: Number of words in search term
            
        Returns:
            List of candidate phrases for matching
        """
        candidates = []
        
        # Split into sentences and clean
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            # Clean sentence
            clean_sentence = re.sub(r'\s+', ' ', sentence.strip())
            if len(clean_sentence) < self.MIN_MATCH_LENGTH:
                continue
            
            # Extract n-grams based on search term length
            words = clean_sentence.split()
            
            # Single words
            candidates.extend(words)
            
            # Phrases of varying lengths around the search term length
            for n in range(max(1, term_word_count - 2), min(len(words) + 1, term_word_count + 3)):
                for i in range(len(words) - n + 1):
                    phrase = ' '.join(words[i:i + n])
                    if len(phrase) >= self.MIN_MATCH_LENGTH:
                        candidates.append(phrase)
        
        return list(set(candidates))  # Remove duplicates
    
    def _find_original_text(self, matched_text: str, page_text: str, case_sensitive: bool) -> Optional[str]:
        """Find the original text in the page that corresponds to the matched text.
        
        Args:
            matched_text: The matched text (potentially lowercased)
            page_text: Original page text
            case_sensitive: Whether matching was case-sensitive
            
        Returns:
            Original text from page, or None if not found
        """
        if case_sensitive:
            return matched_text if matched_text in page_text else None
        
        # Case-insensitive search to find original
        lower_page_text = page_text.lower()
        lower_matched_text = matched_text.lower()
        
        start_idx = lower_page_text.find(lower_matched_text)
        if start_idx != -1:
            return page_text[start_idx:start_idx + len(matched_text)]
        
        return None
    
    def _get_match_context(self, matched_text: str, page_text: str, context_chars: int = 100) -> str:
        """Get surrounding context for a match.
        
        Args:
            matched_text: The matched text
            page_text: Full page text
            context_chars: Number of characters to include on each side
            
        Returns:
            Context string with match highlighted
        """
        try:
            match_start = page_text.find(matched_text)
            if match_start == -1:
                return matched_text
            
            start_idx = max(0, match_start - context_chars)
            end_idx = min(len(page_text), match_start + len(matched_text) + context_chars)
            
            context = page_text[start_idx:end_idx]
            
            # Add ellipsis if truncated
            if start_idx > 0:
                context = '...' + context
            if end_idx < len(page_text):
                context = context + '...'
            
            return context
            
        except Exception as e:
            logger.warning(f"Error getting context: {str(e)}")
            return matched_text
    
    def _get_position_info(self, matched_text: str, page_text: str) -> Dict[str, int]:
        """Get position information for a match within the page.
        
        Args:
            matched_text: The matched text
            page_text: Full page text
            
        Returns:
            Dictionary with position information
        """
        try:
            start_pos = page_text.find(matched_text)
            if start_pos == -1:
                return {'start': 0, 'end': 0, 'length': len(matched_text)}
            
            return {
                'start': start_pos,
                'end': start_pos + len(matched_text),
                'length': len(matched_text)
            }
            
        except Exception as e:
            logger.warning(f"Error getting position info: {str(e)}")
            return {'start': 0, 'end': 0, 'length': len(matched_text)}
    
    def _find_exact_matches(
        self,
        search_term: str,
        page_text: str,
        page_number: int,
        case_sensitive: bool
    ) -> List[Dict[str, Any]]:
        """Find exact matches using regex patterns.
        
        Args:
            search_term: Term to search for
            page_text: Page text content
            page_number: Page number
            case_sensitive: Whether to match case-sensitively
            
        Returns:
            List of exact match dictionaries
        """
        matches = []
        
        try:
            # Create regex pattern
            pattern = re.escape(search_term)
            flags = 0 if case_sensitive else re.IGNORECASE
            
            for match in re.finditer(pattern, page_text, flags=flags):
                matched_text = match.group(0)
                match_context = self._get_match_context(matched_text, page_text)
                position_info = {
                    'start': match.start(),
                    'end': match.end(),
                    'length': len(matched_text)
                }
                
                matches.append({
                    'search_term': search_term,
                    'matched_text': matched_text,
                    'confidence_score': 100.0,  # Exact matches have 100% confidence
                    'page_number': page_number,
                    'needs_approval': False,  # Exact matches don't need approval
                    'match_context': match_context,
                    'position_info': position_info,
                    'case_sensitive_match': case_sensitive,
                    'match_type': 'exact'
                })
                
        except Exception as e:
            logger.error(f"Error finding exact matches: {str(e)}")
        
        return matches
    
    def _remove_duplicate_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate matches based on text content and position.
        
        Args:
            matches: List of match dictionaries
            
        Returns:
            List with duplicates removed
        """
        seen = set()
        unique_matches = []
        
        for match in matches:
            # Create key based on matched text and position
            key = (
                match['matched_text'].lower(),
                match['page_number'],
                match['position_info']['start']
            )
            
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)
            else:
                # Keep match with higher confidence if duplicate found
                existing_match = next(
                    (m for m in unique_matches 
                     if (m['matched_text'].lower(), m['page_number'], m['position_info']['start']) == key),
                    None
                )
                if existing_match and match['confidence_score'] > existing_match['confidence_score']:
                    unique_matches.remove(existing_match)
                    unique_matches.append(match)
        
        return unique_matches
    
    def approve_match(self, match_id: str, approved: bool) -> Dict[str, Any]:
        """Approve or reject a fuzzy match for redaction.
        
        Args:
            match_id: Unique identifier for the match
            approved: Whether the match is approved for redaction
            
        Returns:
            Dictionary with approval status and updated match info
        """
        try:
            # This would typically update the database
            # For now, return a mock response
            return {
                'success': True,
                'match_id': match_id,
                'approved': approved,
                'status': 'approved' if approved else 'rejected',
                'message': f"Match {'approved' if approved else 'rejected'} for redaction"
            }
            
        except Exception as e:
            logger.error(f"Error approving match: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'match_id': match_id
            }
    
    def get_match_statistics(self, matches: List[Union[Dict[str, Any], MatchResult]]) -> Dict[str, Any]:
        """Generate statistics for a set of matches.
        
        Args:
            matches: List of match dictionaries or MatchResult objects
            
        Returns:
            Dictionary with match statistics
        """
        if not matches:
            return {
                'total_matches': 0,
                'high_confidence_matches': 0,
                'needs_approval_matches': 0,
                'average_confidence': 0,
                'pages_with_matches': 0,
                'unique_search_terms': 0
            }
        
        try:
            total_matches = len(matches)
            
            # Handle both dict and MatchResult objects
            if isinstance(matches[0], MatchResult):
                high_confidence_matches = len([m for m in matches if m.confidence_score >= self.config.high_confidence_threshold])
                needs_approval_matches = len([m for m in matches if m.needs_approval])
                average_confidence = sum(m.confidence_score for m in matches) / total_matches
                pages_with_matches = len(set(m.page_number for m in matches))
                unique_search_terms = len(set(m.search_term for m in matches))
            else:
                high_confidence_matches = len([m for m in matches if m['confidence_score'] >= self.config.high_confidence_threshold])
                needs_approval_matches = len([m for m in matches if m.get('needs_approval', False)])
                average_confidence = sum(m['confidence_score'] for m in matches) / total_matches
                pages_with_matches = len(set(m['page_number'] for m in matches))
                unique_search_terms = len(set(m['search_term'] for m in matches))
            
            return {
                'total_matches': total_matches,
                'high_confidence_matches': high_confidence_matches,
                'needs_approval_matches': needs_approval_matches,
                'average_confidence': round(average_confidence, 2),
                'pages_with_matches': pages_with_matches,
                'unique_search_terms': unique_search_terms,
                'confidence_distribution': self._get_confidence_distribution(matches)
            }
            
        except Exception as e:
            logger.error(f"Error calculating statistics: {str(e)}")
            return {
                'total_matches': len(matches),
                'error': str(e)
            }
    
    def _get_confidence_distribution(self, matches: List[Union[Dict[str, Any], MatchResult]]) -> Dict[str, int]:
        """Get distribution of matches by confidence ranges.
        
        Args:
            matches: List of match dictionaries or MatchResult objects
            
        Returns:
            Dictionary with confidence range counts
        """
        distribution = {
            '95-100': 0,
            '90-94': 0,
            '85-89': 0,
            '80-84': 0,
            'below-80': 0
        }
        
        for match in matches:
            if isinstance(match, MatchResult):
                confidence = match.confidence_score
            else:
                confidence = match['confidence_score']
                
            if confidence >= 95:
                distribution['95-100'] += 1
            elif confidence >= 90:
                distribution['90-94'] += 1
            elif confidence >= 85:
                distribution['85-89'] += 1
            elif confidence >= 80:
                distribution['80-84'] += 1
            else:
                distribution['below-80'] += 1
        
        return distribution

    def _find_fuzzy_matches(
        self, 
        search_term: str, 
        candidates: List[str], 
        threshold: int, 
        config: MatchingConfiguration
    ) -> List[Tuple[str, float, Dict[str, float]]]:
        """Find fuzzy matches among candidates.
        
        Args:
            search_term: Term to search for
            candidates: List of candidate text strings
            threshold: Minimum threshold for matches
            config: Matching configuration
            
        Returns:
            List of tuples (matched_text, confidence_score, algorithm_scores)
        """
        matches = []
        algorithm_func = self.algorithm_map[config.algorithm]
        
        try:
            for candidate in candidates:
                if len(candidate.strip()) < self.MIN_MATCH_LENGTH:
                    continue
                
                # Calculate primary score
                primary_score = algorithm_func(search_term, candidate)
                
                if primary_score >= threshold:
                    # Calculate additional algorithm scores for comparison
                    algorithm_scores = {}
                    for alg, func in self.algorithm_map.items():
                        try:
                            algorithm_scores[alg.value] = func(search_term, candidate)
                        except:
                            algorithm_scores[alg.value] = 0.0
                    
                    matches.append((candidate, primary_score, algorithm_scores))
        
        except Exception as e:
            logger.error(f"Error in fuzzy matching: {str(e)}")
        
        return matches

    def _find_exact_matches_enhanced(
        self,
        search_term: str,
        page_text: str,
        page_number: int,
        config: MatchingConfiguration,
        ocr_confidence: Optional[float] = None
    ) -> List[MatchResult]:
        """Find exact matches and return MatchResult objects.
        
        Args:
            search_term: Term to search for
            page_text: Page text content
            page_number: Page number
            config: Matching configuration
            ocr_confidence: OCR confidence for this page
            
        Returns:
            List of MatchResult objects
        """
        matches = []
        
        try:
            pattern = re.escape(search_term)
            flags = 0 if config.case_sensitive else re.IGNORECASE
            
            for match in re.finditer(pattern, page_text, flags=flags):
                matched_text = match.group(0)
                match_context = self._get_match_context(matched_text, page_text, config.context_window)
                position_info = {
                    'start': match.start(),
                    'end': match.end(),
                    'length': len(matched_text)
                }
                
                match_result = MatchResult(
                    search_term=search_term,
                    matched_text=matched_text,
                    confidence_score=100.0,
                    page_number=page_number,
                    needs_approval=False,
                    match_context=match_context,
                    position_info=position_info,
                    algorithm_used="exact",
                    preprocessing_applied=[],
                    match_type="exact",
                    similarity_scores={"exact": 100.0},
                    ocr_confidence=ocr_confidence,
                    context_relevance=1.0,
                    cluster_id=None,
                    processing_time=None
                )
                matches.append(match_result)
                
        except Exception as e:
            logger.error(f"Error finding exact matches: {str(e)}")
        
        return matches

    def _remove_duplicate_matches_enhanced(self, matches: List[MatchResult]) -> List[MatchResult]:
        """Remove duplicate MatchResult objects based on text content and position.
        
        Args:
            matches: List of MatchResult objects
            
        Returns:
            List with duplicates removed
        """
        seen = set()
        unique_matches = []
        
        for match in matches:
            key = (
                match.matched_text.lower(),
                match.page_number,
                match.position_info['start']
            )
            
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)
            else:
                # Keep match with higher confidence if duplicate found
                existing_match = next(
                    (m for m in unique_matches 
                     if (m.matched_text.lower(), m.page_number, m.position_info['start']) == key),
                    None
                )
                if existing_match and match.confidence_score > existing_match.confidence_score:
                    unique_matches.remove(existing_match)
                    unique_matches.append(match)
        
        return unique_matches

    def _create_match_result(
        self,
        search_term: str,
        matched_text: str,
        confidence_score: float,
        page_number: int,
        page_text: str,
        config: MatchingConfiguration,
        algorithm_scores: Dict[str, float],
        ocr_confidence: Optional[float] = None,
        match_type: str = "fuzzy"
    ) -> MatchResult:
        """Create a MatchResult object from match data.
        
        Args:
            search_term: Original search term
            matched_text: The matched text
            confidence_score: Confidence score for the match
            page_number: Page number where match was found
            page_text: Full page text for context
            config: Matching configuration
            algorithm_scores: Scores from different algorithms
            ocr_confidence: OCR confidence for this page
            match_type: Type of match (fuzzy, exact, etc.)
            
        Returns:
            MatchResult object
        """
        match_context = self._get_match_context(matched_text, page_text, config.context_window)
        position_info = self._get_position_info(matched_text, page_text)
        
        # Determine if approval is needed
        needs_approval = (
            match_type == "fuzzy" and 
            confidence_score < config.high_confidence_threshold
        )
        
        # Determine preprocessing applied
        preprocessing_applied = []
        if config.preprocessing_mode != TextPreprocessingMode.NONE:
            preprocessing_applied.append(config.preprocessing_mode.value)
        if config.enable_stemming:
            preprocessing_applied.append("stemming")
        if not config.case_sensitive:
            preprocessing_applied.append("case_insensitive")
        
        return MatchResult(
            search_term=search_term,
            matched_text=matched_text,
            confidence_score=confidence_score,
            page_number=page_number,
            needs_approval=needs_approval,
            match_context=match_context,
            position_info=position_info,
            algorithm_used=config.algorithm.value,
            preprocessing_applied=preprocessing_applied,
            match_type=match_type,
            similarity_scores=algorithm_scores,
            ocr_confidence=ocr_confidence,
            context_relevance=None,
            cluster_id=None,
            processing_time=None
        )

    def _find_phonetic_matches(
        self,
        search_term: str,
        page_text: str,
        original_text: str,
        page_number: int,
        config: MatchingConfiguration,
        ocr_confidence: Optional[float] = None
    ) -> List[MatchResult]:
        """Find phonetic matches using phonetic algorithms.
        
        Args:
            search_term: Term to search for
            page_text: Preprocessed page text
            original_text: Original page text
            page_number: Page number
            config: Matching configuration
            ocr_confidence: OCR confidence for this page
            
        Returns:
            List of phonetic match results
        """
        matches = []
        
        if not PHONETIC_AVAILABLE:
            return matches
        
        try:
            import jellyfish
            
            # Get phonetic representation of search term
            search_soundex = jellyfish.soundex(search_term)
            search_metaphone = jellyfish.metaphone(search_term)
            
            # Extract candidates
            candidates = self._extract_candidates(page_text, len(search_term.split()))
            
            for candidate in candidates:
                if len(candidate.strip()) < self.MIN_MATCH_LENGTH:
                    continue
                
                # Calculate phonetic similarity
                candidate_soundex = jellyfish.soundex(candidate)
                candidate_metaphone = jellyfish.metaphone(candidate)
                
                soundex_match = search_soundex == candidate_soundex
                metaphone_match = search_metaphone == candidate_metaphone
                
                if soundex_match or metaphone_match:
                    # Calculate confidence based on phonetic matches
                    confidence = 85.0  # Base phonetic confidence
                    if soundex_match and metaphone_match:
                        confidence = 95.0
                    elif soundex_match or metaphone_match:
                        confidence = 85.0
                    
                    # Find original text
                    original_match = self._find_original_text(
                        candidate, original_text, config.case_sensitive
                    )
                    
                    if original_match:
                        algorithm_scores = {
                            "soundex": 100.0 if soundex_match else 0.0,
                            "metaphone": 100.0 if metaphone_match else 0.0
                        }
                        
                        match_result = self._create_match_result(
                            search_term, original_match, confidence,
                            page_number, original_text, config, algorithm_scores,
                            ocr_confidence, "phonetic"
                        )
                        matches.append(match_result)
        
        except Exception as e:
            logger.error(f"Error in phonetic matching: {str(e)}")
        
        return matches

    def _post_process_matches(self, matches: List[MatchResult], config: MatchingConfiguration) -> List[MatchResult]:
        """Post-process matches to apply additional filtering or enhancements.
        
        Args:
            matches: List of MatchResult objects
            config: Matching configuration
            
        Returns:
            List of post-processed MatchResult objects
        """
        if not matches:
            return matches
        
        processed_matches = []
        
        for match in matches:
            # Apply additional validation or filtering here
            # For now, just pass through all matches
            processed_matches.append(match)
        
        return processed_matches

    def _cluster_matches(self, matches: List[MatchResult]) -> List[MatchResult]:
        """Cluster similar matches to reduce redundancy.
        
        Args:
            matches: List of MatchResult objects
            
        Returns:
            List of clustered MatchResult objects
        """
        if not matches:
            return matches
        
        # Simple clustering by search term and page
        clusters = {}
        clustered_matches = []
        
        for match in matches:
            cluster_key = f"{match.search_term}_{match.page_number}"
            
            if cluster_key not in clusters:
                clusters[cluster_key] = []
            clusters[cluster_key].append(match)
        
        # Process each cluster
        cluster_id = 0
        for cluster_key, cluster_matches in clusters.items():
            cluster_id += 1
            
            # Sort by confidence and keep the best matches
            cluster_matches.sort(key=lambda x: x.confidence_score, reverse=True)
            
            # Add cluster ID to all matches in this cluster
            for i, match in enumerate(cluster_matches):
                match.cluster_id = f"cluster_{cluster_id}"
                clustered_matches.append(match)
        
        return clustered_matches