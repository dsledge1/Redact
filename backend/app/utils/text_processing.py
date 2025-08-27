"""
Text processing utilities for the text extraction and matching services.

This module provides comprehensive text processing functionality including
normalization, preprocessing, quality assessment, comparison, and optimization
utilities used across the text extraction and matching pipeline.
"""

import re
import unicodedata
import hashlib
import logging
from typing import List, Dict, Tuple, Optional, Union, Any
from collections import Counter
from functools import lru_cache
import time

try:
    import nltk
    from nltk.stem import PorterStemmer, WordNetLemmatizer
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize, sent_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    import jellyfish
    PHONETIC_AVAILABLE = True
except ImportError:
    PHONETIC_AVAILABLE = False

logger = logging.getLogger(__name__)


class TextNormalizer:
    """Handles text normalization and cleanup operations."""
    
    def __init__(self):
        self.whitespace_pattern = re.compile(r'\s+')
        self.punctuation_pattern = re.compile(r'[^\w\s]')
        self.special_chars_pattern = re.compile(r'[^\x20-\x7E]')
        
    def normalize_unicode(self, text: str, form: str = 'NFKC') -> str:
        """Normalize Unicode characters in text.
        
        Args:
            text: Input text to normalize
            form: Unicode normalization form (NFC, NFD, NFKC, NFKD)
            
        Returns:
            Normalized text
        """
        try:
            return unicodedata.normalize(form, text)
        except Exception as e:
            logger.warning(f"Unicode normalization failed: {e}")
            return text
    
    def normalize_whitespace(self, text: str, preserve_lines: bool = False) -> str:
        """Normalize whitespace in text.
        
        Args:
            text: Input text to normalize
            preserve_lines: Whether to preserve line breaks
            
        Returns:
            Text with normalized whitespace
        """
        if preserve_lines:
            lines = text.split('\n')
            return '\n'.join(self.whitespace_pattern.sub(' ', line.strip()) for line in lines)
        else:
            return self.whitespace_pattern.sub(' ', text).strip()
    
    def normalize_case(self, text: str, method: str = 'lower') -> str:
        """Normalize case in text.
        
        Args:
            text: Input text to normalize
            method: Case normalization method ('lower', 'upper', 'title')
            
        Returns:
            Case-normalized text
        """
        if method == 'lower':
            return text.lower()
        elif method == 'upper':
            return text.upper()
        elif method == 'title':
            return text.title()
        else:
            return text
    
    def remove_punctuation(self, text: str, keep_chars: Optional[str] = None) -> str:
        """Remove or selectively keep punctuation from text.
        
        Args:
            text: Input text to process
            keep_chars: Characters to preserve (e.g., "-.")
            
        Returns:
            Text with punctuation removed/filtered
        """
        if keep_chars:
            pattern = re.compile(f'[^\w\s{re.escape(keep_chars)}]')
            return pattern.sub('', text)
        else:
            return self.punctuation_pattern.sub('', text)
    
    def remove_special_chars(self, text: str, replacement: str = '') -> str:
        """Remove non-ASCII special characters from text.
        
        Args:
            text: Input text to process
            replacement: Replacement string for special characters
            
        Returns:
            Text with special characters removed
        """
        return self.special_chars_pattern.sub(replacement, text)


class TextPreprocessor:
    """Handles text preprocessing operations."""
    
    def __init__(self):
        self.normalizer = TextNormalizer()
        if NLTK_AVAILABLE:
            try:
                self.stemmer = PorterStemmer()
                self.lemmatizer = WordNetLemmatizer()
                nltk.data.find('tokenizers/punkt')
                nltk.data.find('corpora/stopwords')
                nltk.data.find('corpora/wordnet')
            except LookupError:
                logger.warning("NLTK data not found. Some preprocessing features may not work.")
        
    def tokenize_words(self, text: str) -> List[str]:
        """Tokenize text into words.
        
        Args:
            text: Input text to tokenize
            
        Returns:
            List of word tokens
        """
        if NLTK_AVAILABLE:
            try:
                return word_tokenize(text)
            except:
                pass
        
        # Fallback to simple regex tokenization
        return re.findall(r'\b\w+\b', text)
    
    def tokenize_sentences(self, text: str) -> List[str]:
        """Tokenize text into sentences.
        
        Args:
            text: Input text to tokenize
            
        Returns:
            List of sentence tokens
        """
        if NLTK_AVAILABLE:
            try:
                return sent_tokenize(text)
            except:
                pass
        
        # Fallback to simple sentence splitting
        return re.split(r'[.!?]+', text)
    
    def remove_stop_words(self, tokens: List[str], language: str = 'english') -> List[str]:
        """Remove stop words from token list.
        
        Args:
            tokens: List of word tokens
            language: Language for stop words
            
        Returns:
            Filtered token list
        """
        if NLTK_AVAILABLE:
            try:
                stop_words = set(stopwords.words(language))
                return [token for token in tokens if token.lower() not in stop_words]
            except:
                pass
        
        # Fallback stop words list
        basic_stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
        return [token for token in tokens if token.lower() not in basic_stop_words]
    
    def stem_words(self, tokens: List[str]) -> List[str]:
        """Apply stemming to word tokens.
        
        Args:
            tokens: List of word tokens
            
        Returns:
            List of stemmed tokens
        """
        if NLTK_AVAILABLE and hasattr(self, 'stemmer'):
            return [self.stemmer.stem(token) for token in tokens]
        else:
            # Simple suffix removal fallback
            return [self._simple_stem(token) for token in tokens]
    
    def lemmatize_words(self, tokens: List[str], pos: str = 'n') -> List[str]:
        """Apply lemmatization to word tokens.
        
        Args:
            tokens: List of word tokens
            pos: Part of speech tag
            
        Returns:
            List of lemmatized tokens
        """
        if NLTK_AVAILABLE and hasattr(self, 'lemmatizer'):
            return [self.lemmatizer.lemmatize(token, pos) for token in tokens]
        else:
            return tokens
    
    def _simple_stem(self, word: str) -> str:
        """Simple stemming fallback."""
        word = word.lower()
        if word.endswith('ing'):
            return word[:-3]
        elif word.endswith('ed'):
            return word[:-2]
        elif word.endswith('s'):
            return word[:-1]
        return word


class TextQualityAssessor:
    """Assesses text quality and provides recommendations."""
    
    def __init__(self):
        self.common_ocr_errors = {
            'rn': 'm', 'cl': 'd', 'll': 'u', '0': 'o', '1': 'l', '5': 's'
        }
        
    def assess_character_confidence(self, text: str) -> float:
        """Assess character recognition confidence.
        
        Args:
            text: Input text to assess
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        if not text:
            return 0.0
            
        total_chars = len(text)
        suspicious_chars = 0
        
        # Check for common OCR error patterns
        for error_pattern in self.common_ocr_errors.keys():
            suspicious_chars += text.count(error_pattern)
        
        # Check for unusual character sequences
        suspicious_chars += len(re.findall(r'[^\w\s]{3,}', text))
        
        # Check for excessive special characters
        special_char_ratio = len(re.findall(r'[^\w\s]', text)) / total_chars
        if special_char_ratio > 0.3:
            suspicious_chars += int(total_chars * 0.1)
        
        confidence = max(0.0, 1.0 - (suspicious_chars / total_chars))
        return min(1.0, confidence)
    
    def assess_coherence(self, text: str) -> float:
        """Assess text coherence and readability.
        
        Args:
            text: Input text to assess
            
        Returns:
            Coherence score (0.0 to 1.0)
        """
        if not text:
            return 0.0
            
        words = text.split()
        if len(words) < 5:
            return 0.5
        
        # Calculate average word length
        avg_word_length = sum(len(word) for word in words) / len(words)
        word_length_score = min(1.0, avg_word_length / 6.0)  # Normalize around 6 chars
        
        # Calculate sentence structure score
        sentences = re.split(r'[.!?]+', text)
        avg_sentence_length = len(words) / max(1, len(sentences))
        sentence_score = min(1.0, avg_sentence_length / 15.0)  # Normalize around 15 words
        
        # Calculate vocabulary diversity
        unique_words = set(word.lower() for word in words)
        diversity_score = len(unique_words) / len(words)
        
        # Combine scores
        coherence_score = (word_length_score + sentence_score + diversity_score) / 3.0
        return coherence_score
    
    def detect_ocr_errors(self, text: str) -> List[Tuple[str, str, int]]:
        """Detect potential OCR errors in text.
        
        Args:
            text: Input text to analyze
            
        Returns:
            List of (error_pattern, suggested_correction, position) tuples
        """
        errors = []
        
        for error_pattern, correction in self.common_ocr_errors.items():
            for match in re.finditer(error_pattern, text, re.IGNORECASE):
                errors.append((error_pattern, correction, match.start()))
        
        return errors
    
    def assess_completeness(self, text: str) -> float:
        """Assess text completeness.
        
        Args:
            text: Input text to assess
            
        Returns:
            Completeness score (0.0 to 1.0)
        """
        if not text:
            return 0.0
        
        # Check for terminal punctuation in original text before splitting
        terminal_punctuation_pattern = r'[.!?]+\s*$'
        has_terminal_punctuation = bool(re.search(terminal_punctuation_pattern, text.strip()))
        
        # Count sentences that end properly with terminal punctuation
        # Use word boundary and lookahead to avoid splitting on abbreviations
        sentence_pattern = r'[.!?]+(?=\s+[A-Z]|\s*$)'
        terminal_sentences = len(re.findall(sentence_pattern, text))
        
        # Count all potential sentences (including incomplete ones)
        all_sentence_breaks = len(re.findall(r'[.!?]+', text))
        
        # Calculate completeness based on terminal punctuation
        if all_sentence_breaks == 0:
            # No sentence breaks found - check if it's a complete fragment
            word_count = len(text.split())
            if word_count >= 3 and has_terminal_punctuation:
                completeness_score = 0.8  # Single complete sentence
            elif word_count >= 3:
                completeness_score = 0.6  # Single incomplete sentence
            else:
                completeness_score = 0.3  # Fragment
        else:
            completeness_score = terminal_sentences / max(1, all_sentence_breaks)
        
        # Additional checks for text quality indicators
        
        # Check for missing words (indicated by excessive spaces)
        excessive_spaces = len(re.findall(r'\s{3,}', text))
        space_penalty = min(0.3, excessive_spaces / max(1, len(text.split())))
        
        # Check for incomplete words (common OCR issue)
        incomplete_words = len(re.findall(r'\b\w{1,2}\s+\w{1,2}\b', text))
        incomplete_penalty = min(0.2, incomplete_words / max(1, len(text.split())))
        
        # Check for missing capitals at sentence starts
        sentences_after_split = re.split(r'[.!?]+', text)
        sentences_with_capitals = sum(1 for s in sentences_after_split 
                                    if s.strip() and s.strip()[0].isupper())
        capital_bonus = 0.1 if sentences_with_capitals > 0 and len(sentences_after_split) > 1 else 0
        
        # Combine all factors
        final_score = completeness_score - space_penalty - incomplete_penalty + capital_bonus
        
        return max(0.0, min(1.0, final_score))


class TextComparator:
    """Handles text comparison and similarity calculations."""
    
    def __init__(self):
        self.preprocessor = TextPreprocessor()
        
    def calculate_similarity(self, text1: str, text2: str, method: str = 'jaccard') -> float:
        """Calculate similarity between two texts.
        
        Args:
            text1: First text for comparison
            text2: Second text for comparison
            method: Similarity calculation method
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if method == 'jaccard':
            return self._jaccard_similarity(text1, text2)
        elif method == 'cosine':
            return self._cosine_similarity(text1, text2)
        elif method == 'levenshtein':
            return self._levenshtein_similarity(text1, text2)
        else:
            return self._jaccard_similarity(text1, text2)
    
    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity."""
        words1 = set(self.preprocessor.tokenize_words(text1.lower()))
        words2 = set(self.preprocessor.tokenize_words(text2.lower()))
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def _cosine_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity."""
        words1 = self.preprocessor.tokenize_words(text1.lower())
        words2 = self.preprocessor.tokenize_words(text2.lower())
        
        counter1 = Counter(words1)
        counter2 = Counter(words2)
        
        # Get all unique words
        all_words = set(counter1.keys()).union(set(counter2.keys()))
        
        # Create vectors
        vector1 = [counter1.get(word, 0) for word in all_words]
        vector2 = [counter2.get(word, 0) for word in all_words]
        
        # Calculate dot product and magnitudes
        dot_product = sum(a * b for a, b in zip(vector1, vector2))
        magnitude1 = sum(a * a for a in vector1) ** 0.5
        magnitude2 = sum(a * a for a in vector2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def _levenshtein_similarity(self, text1: str, text2: str) -> float:
        """Calculate Levenshtein similarity."""
        distance = self.levenshtein_distance(text1, text2)
        max_length = max(len(text1), len(text2))
        
        if max_length == 0:
            return 1.0
        
        return 1.0 - (distance / max_length)
    
    def levenshtein_distance(self, text1: str, text2: str) -> int:
        """Calculate Levenshtein distance between two texts."""
        if len(text1) < len(text2):
            return self.levenshtein_distance(text2, text1)
        
        if len(text2) == 0:
            return len(text1)
        
        previous_row = range(len(text2) + 1)
        for i, char1 in enumerate(text1):
            current_row = [i + 1]
            for j, char2 in enumerate(text2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (char1 != char2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def phonetic_similarity(self, text1: str, text2: str, algorithm: str = 'soundex') -> float:
        """Calculate phonetic similarity between texts.
        
        Args:
            text1: First text for comparison
            text2: Second text for comparison
            algorithm: Phonetic algorithm ('soundex', 'metaphone', 'nysiis')
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not PHONETIC_AVAILABLE:
            return 0.0
        
        words1 = self.preprocessor.tokenize_words(text1)
        words2 = self.preprocessor.tokenize_words(text2)
        
        if algorithm == 'soundex':
            codes1 = [jellyfish.soundex(word) for word in words1]
            codes2 = [jellyfish.soundex(word) for word in words2]
        elif algorithm == 'metaphone':
            codes1 = [jellyfish.metaphone(word) for word in words1]
            codes2 = [jellyfish.metaphone(word) for word in words2]
        elif algorithm == 'nysiis':
            codes1 = [jellyfish.nysiis(word) for word in words1]
            codes2 = [jellyfish.nysiis(word) for word in words2]
        else:
            return 0.0
        
        # Calculate Jaccard similarity of phonetic codes
        set1 = set(codes1)
        set2 = set(codes2)
        intersection = set1.intersection(set2)
        union = set1.union(set2)
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)


class TextExtractionHelper:
    """Helper utilities for text extraction operations."""
    
    def __init__(self):
        self.normalizer = TextNormalizer()
        
    def clean_extracted_text(self, text: str) -> str:
        """Clean and sanitize extracted text.
        
        Args:
            text: Raw extracted text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Normalize unicode and whitespace
        text = self.normalizer.normalize_unicode(text)
        text = self.normalizer.normalize_whitespace(text, preserve_lines=True)
        
        # Remove null bytes and control characters
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Fix common OCR spacing issues
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between lowercase and uppercase
        text = re.sub(r'(\d)([A-Za-z])', r'\1 \2', text)  # Add space between digit and letter
        text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)  # Add space between letter and digit
        
        return text.strip()
    
    def extract_table_text(self, text: str) -> List[List[str]]:
        """Extract table-like structures from text.
        
        Args:
            text: Input text containing table data
            
        Returns:
            List of table rows, each row is a list of cells
        """
        tables = []
        lines = text.split('\n')
        current_table = []
        
        for line in lines:
            # Detect potential table rows (multiple whitespace-separated columns)
            columns = re.split(r'\s{2,}', line.strip())
            if len(columns) > 1:
                current_table.append(columns)
            else:
                if current_table:
                    tables.append(current_table)
                    current_table = []
        
        if current_table:
            tables.append(current_table)
        
        return tables
    
    def extract_list_items(self, text: str) -> List[str]:
        """Extract list items from text.
        
        Args:
            text: Input text containing list items
            
        Returns:
            List of extracted items
        """
        items = []
        
        # Match bullet points, numbers, letters
        patterns = [
            r'^\s*[•·▪▫‣⁃]\s*(.+)$',  # Bullet points
            r'^\s*\d+[\.\)]\s*(.+)$',  # Numbered lists
            r'^\s*[a-zA-Z][\.\)]\s*(.+)$',  # Lettered lists
            r'^\s*[-*+]\s*(.+)$',  # Dash/asterisk bullets
        ]
        
        lines = text.split('\n')
        for line in lines:
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    items.append(match.group(1).strip())
                    break
        
        return items
    
    def extract_headers(self, text: str) -> List[Tuple[str, int]]:
        """Extract headers and their levels from text.
        
        Args:
            text: Input text containing headers
            
        Returns:
            List of (header_text, level) tuples
        """
        headers = []
        lines = text.split('\n')
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            # Check for markdown-style headers
            if stripped.startswith('#'):
                level = len(stripped) - len(stripped.lstrip('#'))
                header_text = stripped.lstrip('#').strip()
                if header_text:
                    headers.append((header_text, level))
            
            # Check for underlined headers
            elif len(stripped) > 0 and all(c in '=-_' for c in stripped):
                # Look for previous line as potential header
                prev_line_idx = lines.index(line) - 1
                if prev_line_idx >= 0:
                    prev_line = lines[prev_line_idx].strip()
                    if prev_line and not all(c in '=-_' for c in prev_line):
                        level = 1 if '=' in stripped else 2
                        headers.append((prev_line, level))
        
        return headers
    
    def track_text_coordinates(self, text: str, page_width: int, page_height: int) -> Dict[str, Any]:
        """Track text coordinates and positioning information.
        
        Args:
            text: Input text
            page_width: Page width for coordinate calculation
            page_height: Page height for coordinate calculation
            
        Returns:
            Dictionary containing coordinate and positioning metadata
        """
        lines = text.split('\n')
        line_height = page_height / max(1, len(lines))
        
        coordinates = {
            'page_width': page_width,
            'page_height': page_height,
            'line_count': len(lines),
            'line_height': line_height,
            'lines': []
        }
        
        for i, line in enumerate(lines):
            line_data = {
                'line_number': i + 1,
                'text': line,
                'y_position': i * line_height,
                'character_count': len(line),
                'word_count': len(line.split())
            }
            coordinates['lines'].append(line_data)
        
        return coordinates
    
    def extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract metadata from text.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary containing text metadata
        """
        words = text.split()
        sentences = re.split(r'[.!?]+', text)
        paragraphs = text.split('\n\n')
        
        metadata = {
            'character_count': len(text),
            'word_count': len(words),
            'sentence_count': len([s for s in sentences if s.strip()]),
            'paragraph_count': len([p for p in paragraphs if p.strip()]),
            'line_count': len(text.split('\n')),
            'average_word_length': sum(len(word) for word in words) / max(1, len(words)),
            'unique_word_count': len(set(word.lower() for word in words)),
            'language_hints': self._detect_language_hints(text)
        }
        
        return metadata
    
    def _detect_language_hints(self, text: str) -> List[str]:
        """Detect potential languages based on character patterns."""
        hints = []
        
        if re.search(r'[àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]', text, re.IGNORECASE):
            hints.append('romance_language')
        
        if re.search(r'[äöüß]', text, re.IGNORECASE):
            hints.append('german')
        
        if re.search(r'[ąćęłńóśźż]', text, re.IGNORECASE):
            hints.append('polish')
        
        if re.search(r'[а-я]', text, re.IGNORECASE):
            hints.append('cyrillic')
        
        if re.search(r'[\u4e00-\u9fff]', text):
            hints.append('chinese')
        
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            hints.append('japanese')
        
        return hints


class TextProcessingCache:
    """Cache for text processing operations to improve performance."""
    
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
        self.access_times = {}
        
    def get(self, key: str) -> Optional[Any]:
        """Get cached value."""
        if key in self.cache:
            self.access_times[key] = time.time()
            return self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set cached value."""
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = value
        self.access_times[key] = time.time()
    
    def _evict_oldest(self):
        """Evict least recently accessed item."""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times, key=self.access_times.get)
        del self.cache[oldest_key]
        del self.access_times[oldest_key]
    
    def clear(self):
        """Clear all cached values."""
        self.cache.clear()
        self.access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_ratio': len(self.access_times) / max(1, len(self.cache))
        }


class BatchTextProcessor:
    """Handles batch text processing operations."""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.normalizer = TextNormalizer()
        self.preprocessor = TextPreprocessor()
        self.quality_assessor = TextQualityAssessor()
        self.cache = TextProcessingCache()
        
    def process_batch(self, texts: List[str], operations: List[str]) -> List[Dict[str, Any]]:
        """Process a batch of texts with specified operations.
        
        Args:
            texts: List of texts to process
            operations: List of operations to perform
            
        Returns:
            List of processing results for each text
        """
        results = []
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_results = []
            
            for text in batch:
                text_result = {'original_text': text}
                
                if 'normalize' in operations:
                    text_result['normalized'] = self.normalizer.normalize_unicode(text)
                
                if 'tokenize' in operations:
                    text_result['tokens'] = self.preprocessor.tokenize_words(text)
                
                if 'quality' in operations:
                    text_result['quality_score'] = self.quality_assessor.assess_character_confidence(text)
                
                if 'clean' in operations:
                    helper = TextExtractionHelper()
                    text_result['cleaned'] = helper.clean_extracted_text(text)
                
                batch_results.append(text_result)
            
            results.extend(batch_results)
        
        return results
    
    def monitor_memory_usage(self) -> Dict[str, Any]:
        """Monitor memory usage during batch processing."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss,
            'vms': memory_info.vms,
            'percent': process.memory_percent(),
            'cache_stats': self.cache.get_stats()
        }


# Global instances for common use
text_normalizer = TextNormalizer()
text_preprocessor = TextPreprocessor()
text_quality_assessor = TextQualityAssessor()
text_comparator = TextComparator()
text_extraction_helper = TextExtractionHelper()
batch_processor = BatchTextProcessor()


def get_text_fingerprint(text: str) -> str:
    """Generate a fingerprint hash for text content.
    
    Args:
        text: Input text
        
    Returns:
        SHA-256 hash of the text
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def measure_processing_time(func):
    """Decorator to measure text processing time."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        logger.debug(f"{func.__name__} took {end_time - start_time:.4f} seconds")
        return result
    return wrapper