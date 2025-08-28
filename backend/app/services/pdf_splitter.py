import re
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from fuzzywuzzy import fuzz
from PyPDF2 import PdfReader, PdfWriter

from .text_extraction_service import TextExtractionService
from .temp_file_manager import TempFileManager
from ..utils.validators import validate_file_exists, validate_page_numbers
from ..utils.pdf_utils import validate_pdf_structure, preserve_pdf_metadata

logger = logging.getLogger(__name__)


class PDFSplitter:
    """
    Specialized service for PDF splitting operations with support for both
    page-range and pattern-based splitting.
    """
    
    def __init__(self, session_id: str):
        """
        Initialize PDFSplitter with session-specific file management.
        
        Args:
            session_id: Session identifier for file management
        """
        self.session_id = session_id
        self.text_extractor = TextExtractionService()
        
    def split_by_pages(
        self,
        file_path: Path,
        split_pages: List[int],
        preserve_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Split PDF by explicit page ranges with enhanced metadata preservation.
        
        Args:
            file_path: Path to source PDF file
            split_pages: List of page numbers to split on
            preserve_metadata: Whether to preserve document metadata
            
        Returns:
            Dictionary with split results, file paths, and statistics
        """
        try:
            # Validate input parameters
            validate_file_exists(file_path)
            
            # Optional PDF structure validation
            pdf_validation = validate_pdf_structure(file_path)
            if not pdf_validation.get('valid', True):
                logger.warning(f"PDF structure validation warning: {pdf_validation.get('error', 'Unknown issue')}")
                
            # Read source PDF
            reader = PdfReader(str(file_path))
            total_pages = len(reader.pages)
            
            # Validate split parameters
            self._validate_split_parameters(file_path, split_pages, total_pages)
            
            # Calculate page ranges for splits
            page_ranges = self._calculate_page_ranges(split_pages, total_pages)
            
            # Generate output filenames
            base_name = file_path.stem
            output_files = self._generate_split_filenames(
                base_name, 'pages', page_ranges
            )
            
            # Perform splits
            split_results = []
            for i, (start_page, end_page) in enumerate(page_ranges):
                output_path = TempFileManager.get_session_path(self.session_id, 'downloads') / output_files[i]
                
                # Create writer and copy pages
                writer = PdfWriter()
                for page_num in range(start_page - 1, end_page):
                    writer.add_page(reader.pages[page_num])
                
                # Preserve metadata if requested
                if preserve_metadata:
                    preserve_pdf_metadata(reader, writer, 'comprehensive')
                
                # Write output file
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)
                
                # Calculate file hash for integrity
                file_hash = self._calculate_file_hash(output_path)
                
                split_results.append({
                    'filename': output_files[i],
                    'path': str(output_path),
                    'page_range': f"{start_page}-{end_page}",
                    'page_count': end_page - start_page + 1,
                    'file_size': output_path.stat().st_size,
                    'sha256_hash': file_hash
                })
            
            # Calculate overall statistics
            total_output_size = sum(result['file_size'] for result in split_results)
            original_size = file_path.stat().st_size
            
            result = {
                'success': True,
                'split_type': 'pages',
                'source_file': str(file_path),
                'source_pages': total_pages,
                'source_size': original_size,
                'output_files': split_results,
                'total_output_size': total_output_size,
                'metadata_preserved': preserve_metadata,
                'processing_time': None  # Set by caller if needed
            }
            
            logger.info(
                f"Successfully split PDF by pages: {file_path.name} -> "
                f"{len(split_results)} files"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error splitting PDF by pages: {str(e)}")
            raise
    
    def split_by_pattern(
        self,
        file_path: Path,
        pattern: str,
        pattern_type: str = 'regex',
        fuzzy_threshold: int = 80,
        split_position: str = 'before'
    ) -> Dict[str, Any]:
        """
        Split PDF based on text pattern matching.
        
        Args:
            file_path: Path to source PDF file
            pattern: Text pattern to search for
            pattern_type: Type of pattern matching ('regex', 'fuzzy', 'exact')
            fuzzy_threshold: Threshold for fuzzy matching (1-100)
            split_position: Position to split ('before' or 'after' pattern)
            
        Returns:
            Dictionary with split results, file paths, and statistics
        """
        try:
            # Validate input parameters
            validate_file_exists(file_path)
            
            # Optional PDF structure validation
            pdf_validation = validate_pdf_structure(file_path)
            if not pdf_validation.get('valid', True):
                logger.warning(f"PDF structure validation warning: {pdf_validation.get('error', 'Unknown issue')}")
                
            # Read source PDF
            reader = PdfReader(str(file_path))
            total_pages = len(reader.pages)
            
            # Detect pattern matches
            pattern_matches = self._detect_pattern_pages(
                file_path, pattern, pattern_type, fuzzy_threshold
            )
            
            if not pattern_matches:
                logger.warning(f"No pattern matches found for: {pattern}")
                return {
                    'success': False,
                    'error': 'No pattern matches found',
                    'pattern': pattern,
                    'pattern_type': pattern_type
                }
            
            # Calculate split points based on matches and position
            split_pages = self._calculate_split_points(
                pattern_matches, split_position, total_pages
            )
            
            # Calculate page ranges for splits
            page_ranges = self._calculate_page_ranges(split_pages, total_pages)
            
            # Generate output filenames
            base_name = file_path.stem
            match_labels = [match['text'][:20] for match in pattern_matches]
            output_files = self._generate_split_filenames(
                base_name, 'pattern', page_ranges, match_labels
            )
            
            # Perform splits
            split_results = []
            for i, (start_page, end_page) in enumerate(page_ranges):
                output_path = TempFileManager.get_session_path(self.session_id, 'downloads') / output_files[i]
                
                # Create writer and copy pages
                writer = PdfWriter()
                for page_num in range(start_page - 1, end_page):
                    writer.add_page(reader.pages[page_num])
                
                # Preserve metadata
                preserve_pdf_metadata(reader, writer, 'comprehensive')
                
                # Write output file
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)
                
                # Calculate file hash for integrity
                file_hash = self._calculate_file_hash(output_path)
                
                split_results.append({
                    'filename': output_files[i],
                    'path': str(output_path),
                    'page_range': f"{start_page}-{end_page}",
                    'page_count': end_page - start_page + 1,
                    'file_size': output_path.stat().st_size,
                    'sha256_hash': file_hash,
                    'pattern_match': match_labels[i] if i < len(match_labels) else None
                })
            
            # Calculate overall statistics
            total_output_size = sum(result['file_size'] for result in split_results)
            original_size = file_path.stat().st_size
            
            result = {
                'success': True,
                'split_type': 'pattern',
                'pattern': pattern,
                'pattern_type': pattern_type,
                'pattern_matches_found': len(pattern_matches),
                'source_file': str(file_path),
                'source_pages': total_pages,
                'source_size': original_size,
                'output_files': split_results,
                'total_output_size': total_output_size,
                'metadata_preserved': True,
                'processing_time': None  # Set by caller if needed
            }
            
            logger.info(
                f"Successfully split PDF by pattern: {file_path.name} -> "
                f"{len(split_results)} files, {len(pattern_matches)} matches"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error splitting PDF by pattern: {str(e)}")
            raise
    
    def _detect_pattern_pages(
        self,
        file_path: Path,
        pattern: str,
        pattern_type: str,
        fuzzy_threshold: int
    ) -> List[Dict[str, Any]]:
        """
        Detect pages containing the specified pattern using text extraction.
        
        Args:
            file_path: Path to PDF file
            pattern: Pattern to search for
            pattern_type: Type of pattern matching
            fuzzy_threshold: Threshold for fuzzy matching
            
        Returns:
            List of pattern matches with page numbers and text
        """
        try:
            # Extract text from all pages
            extraction_result = self.text_extractor.extract_text_unified(
                str(file_path), {'method': 'text_layer'}
            )
            
            if not extraction_result['success']:
                raise Exception("Failed to extract text for pattern matching")
            
            matches = []
            
            for page in extraction_result['pages']:
                page_text = page.get('text', '')
                page_number = page.get('page_number')
                
                if not page_text.strip():
                    continue
                
                match_info = self._match_pattern(
                    page_text, pattern, pattern_type, fuzzy_threshold
                )
                
                if match_info['found']:
                    matches.append({
                        'page': page_number,
                        'text': match_info['matched_text'],
                        'confidence': match_info['confidence'],
                        'position': match_info.get('position', 0)
                    })
            
            return matches
            
        except Exception as e:
            logger.error(f"Error detecting pattern pages: {str(e)}")
            raise
    
    def _match_pattern(
        self,
        text: str,
        pattern: str,
        pattern_type: str,
        fuzzy_threshold: int
    ) -> Dict[str, Any]:
        """
        Match pattern in text using specified matching method.
        
        Args:
            text: Text to search in
            pattern: Pattern to search for
            pattern_type: Type of pattern matching
            fuzzy_threshold: Threshold for fuzzy matching
            
        Returns:
            Dictionary with match information
        """
        try:
            if pattern_type == 'exact':
                if pattern in text:
                    return {
                        'found': True,
                        'matched_text': pattern,
                        'confidence': 100,
                        'position': text.find(pattern)
                    }
                    
            elif pattern_type == 'regex':
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    return {
                        'found': True,
                        'matched_text': match.group(0),
                        'confidence': 100,
                        'position': match.start()
                    }
                    
            elif pattern_type == 'fuzzy':
                # Split text into words and check fuzzy match
                words = text.split()
                best_match = None
                best_ratio = 0
                best_position = 0
                
                for i, word in enumerate(words):
                    ratio = fuzz.ratio(pattern.lower(), word.lower())
                    if ratio > best_ratio and ratio >= fuzzy_threshold:
                        best_ratio = ratio
                        best_match = word
                        best_position = text.find(word)
                
                if best_match:
                    return {
                        'found': True,
                        'matched_text': best_match,
                        'confidence': best_ratio,
                        'position': best_position
                    }
            
            return {'found': False, 'confidence': 0}
            
        except Exception as e:
            logger.error(f"Error matching pattern: {str(e)}")
            return {'found': False, 'confidence': 0, 'error': str(e)}
    
    def _calculate_split_points(
        self,
        pattern_matches: List[Dict[str, Any]],
        split_position: str,
        total_pages: int
    ) -> List[int]:
        """
        Calculate split points based on pattern matches and split position.
        
        Args:
            pattern_matches: List of pattern matches with page numbers
            split_position: Position to split ('before' or 'after')
            total_pages: Total number of pages
            
        Returns:
            List of page numbers to split on
        """
        split_pages = []
        
        for match in pattern_matches:
            page_num = match['page']
            
            if split_position == 'before':
                if page_num > 1:  # Can't split before page 1
                    split_pages.append(page_num)
            elif split_position == 'after':
                if page_num < total_pages:  # Can't split after last page
                    split_pages.append(page_num + 1)
        
        # Remove duplicates and sort
        split_pages = sorted(list(set(split_pages)))
        
        return split_pages
    
    def _calculate_page_ranges(
        self,
        split_pages: List[int],
        total_pages: int
    ) -> List[Tuple[int, int]]:
        """
        Calculate page ranges based on split points.
        
        Args:
            split_pages: List of page numbers to split on
            total_pages: Total number of pages
            
        Returns:
            List of (start_page, end_page) tuples
        """
        if not split_pages:
            return [(1, total_pages)]
        
        ranges = []
        start_page = 1
        
        for split_page in sorted(split_pages):
            if start_page < split_page:
                ranges.append((start_page, split_page - 1))
            start_page = split_page
        
        # Add final range if needed
        if start_page <= total_pages:
            ranges.append((start_page, total_pages))
        
        return ranges
    
    def _validate_split_parameters(
        self,
        file_path: Path,
        split_pages: List[int],
        total_pages: int
    ) -> None:
        """
        Validate split parameters for comprehensive validation.
        
        Args:
            file_path: Path to PDF file
            split_pages: List of page numbers to split on
            total_pages: Total number of pages in PDF
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Explicit guard to reject page 1
        if 1 in split_pages:
            raise ValueError("Cannot split on page 1 (would create empty first section)")
        
        # Validate page numbers with strict requirements for split operations
        page_validation = validate_page_numbers(
            split_pages, 
            total_pages, 
            allow_duplicates=False, 
            require_ascending=True
        )
        if not page_validation['valid']:
            raise ValueError(f"Invalid page numbers: {page_validation['error']}")
        
        # Check for reasonable split limits
        if len(split_pages) > 100:
            raise ValueError("Too many split points (maximum 100)")
        
        # Validate file is readable
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"File not found or not readable: {file_path}")
    
    def _generate_split_filenames(
        self,
        base_name: str,
        split_strategy: str,
        page_ranges: List[Tuple[int, int]],
        pattern_matches: Optional[List[str]] = None
    ) -> List[str]:
        """
        Generate intelligent filenames for split files.
        
        Args:
            base_name: Base filename without extension
            split_strategy: Strategy used for splitting
            page_ranges: List of page ranges for each split
            pattern_matches: List of pattern matches (for pattern splits)
            
        Returns:
            List of generated filenames
        """
        filenames = []
        
        for i, (start, end) in enumerate(page_ranges):
            if split_strategy == 'pages':
                if start == end:
                    filename = f"{base_name}_page_{start}.pdf"
                else:
                    filename = f"{base_name}_pages_{start}-{end}.pdf"
            elif split_strategy == 'pattern':
                if pattern_matches and i < len(pattern_matches):
                    # Sanitize pattern match for filename
                    match_text = re.sub(r'[^\w\s-]', '', pattern_matches[i])
                    match_text = re.sub(r'\s+', '_', match_text)[:15]
                    filename = f"{base_name}_match_{i+1}_{match_text}.pdf"
                else:
                    filename = f"{base_name}_section_{i+1}_pages_{start}-{end}.pdf"
            else:
                filename = f"{base_name}_part_{i+1}.pdf"
            
            filenames.append(filename)
        
        return filenames
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA-256 hash of file for integrity verification.
        
        Args:
            file_path: Path to file
            
        Returns:
            SHA-256 hash as hex string
        """
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating file hash: {str(e)}")
            return ""