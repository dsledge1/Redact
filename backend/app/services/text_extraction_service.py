"""Comprehensive text extraction service for Ultimate PDF redaction."""

from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
import logging
from datetime import datetime
from enum import Enum
import hashlib
import json

from django.core.cache import cache

from .ocr_service import OCRService
from app.utils.temp_file_manager import TempFileManager

logger = logging.getLogger(__name__)


class ExtractionMethod(Enum):
    """Text extraction methods."""
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    HYBRID = "hybrid"
    AUTO = "auto"


class TextQuality(Enum):
    """Text quality levels."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class TextExtractionService:
    """Comprehensive service for unified text extraction from PDFs.
    
    This service intelligently combines text layer extraction and OCR results,
    providing unified text extraction with source attribution and confidence scoring.
    """
    
    # Quality thresholds (0.0 - 1.0 scale)
    HIGH_QUALITY_THRESHOLD = 0.8
    MEDIUM_QUALITY_THRESHOLD = 0.5
    LOW_QUALITY_THRESHOLD = 0.2
    
    # Text layer quality assessment
    MIN_TEXT_DENSITY = 0.5  # Characters per 1000 square units
    MIN_PAGE_TEXT_LENGTH = 50
    
    # Caching configuration
    CACHE_TIMEOUT = 3600  # 1 hour
    CACHE_PREFIX = "text_extraction"
    
    def __init__(self, session_id: str, pdf_processor: Optional[Any] = None, ocr_service: Optional[OCRService] = None):
        """Initialize text extraction service.
        
        Args:
            session_id: Session identifier for file management
            pdf_processor: Optional PDF processor instance for dependency injection
            ocr_service: Optional OCRService instance for dependency injection
        """
        self.session_id = session_id
        if pdf_processor:
            self.pdf_processor = pdf_processor
        else:
            # Import here to avoid circular dependency
            from .pdf_processor import PDFProcessor
            self.pdf_processor = PDFProcessor(session_id)
        self.ocr_service = ocr_service or OCRService()
        self.temp_file_manager = TempFileManager(session_id)
        
        # Statistics tracking
        self.extraction_stats = {
            'pages_processed': 0,
            'text_layer_used': 0,
            'ocr_used': 0,
            'hybrid_used': 0,
            'total_processing_time': 0,
            'cache_hits': 0
        }
    
    def extract_text_unified(
        self, 
        pdf_path: Union[Path, str],
        method: ExtractionMethod = ExtractionMethod.AUTO,
        page_range: Optional[Tuple[int, int]] = None,
        include_confidence: bool = True,
        use_cache: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Extract text from PDF using unified approach.
        
        Args:
            pdf_path: Path to PDF file (str or Path object)
            method: Extraction method to use
            page_range: Optional page range (start, end)
            include_confidence: Whether to include confidence scoring
            use_cache: Whether to use caching
            progress_callback: Optional callback function for progress reporting
            
        Returns:
            Dictionary with unified extraction results
        """
        try:
            # Ensure pdf_path is a Path object
            pdf_path = Path(pdf_path)
            start_time = datetime.now()
            
            # Generate cache key if caching is enabled
            cache_key = None
            if use_cache:
                cache_key = self._generate_cache_key(pdf_path, method, page_range)
                cached_result = cache.get(cache_key)
                if cached_result:
                    cached_result['cache_hit'] = True
                    self.extraction_stats['cache_hits'] += 1
                    return cached_result
            
            # Validate PDF and get metadata
            validation_result = self.pdf_processor.validate_pdf(pdf_path)
            if not validation_result['is_valid']:
                return {
                    'success': False,
                    'error': f"Invalid PDF: {validation_result['error']}",
                    'extraction_method': None,
                    'pages': [],
                    'cache_hit': False
                }
            
            total_pages = validation_result['page_count']
            has_text_layer = validation_result['has_text_layer']
            
            # Determine page range
            if page_range:
                start_page, end_page = page_range
                start_page = max(1, min(start_page, total_pages))
                end_page = max(start_page, min(end_page, total_pages))
            else:
                start_page, end_page = 1, total_pages
            
            # Determine extraction method
            extraction_method = self._determine_extraction_method(
                method, pdf_path, has_text_layer, (start_page, end_page)
            )
            
            # Extract text using determined method
            if extraction_method == ExtractionMethod.TEXT_LAYER:
                result = self._extract_text_layer(pdf_path, (start_page, end_page), progress_callback)
            elif extraction_method == ExtractionMethod.OCR:
                result = self._extract_ocr_only(pdf_path, (start_page, end_page), progress_callback)
            elif extraction_method == ExtractionMethod.HYBRID:
                result = self._extract_hybrid(pdf_path, (start_page, end_page), progress_callback)
            else:
                return {
                    'success': False,
                    'error': f"Unsupported extraction method: {extraction_method}",
                    'extraction_method': extraction_method.value,
                    'pages': [],
                    'cache_hit': False
                }
            
            if not result['success']:
                return result
            
            # Add confidence scoring if requested
            if include_confidence:
                result = self._add_confidence_scoring(result)
            
            # Add metadata and statistics
            processing_time = (datetime.now() - start_time).total_seconds()
            result.update({
                'extraction_method': extraction_method.value,
                'pdf_metadata': {
                    'total_pages': total_pages,
                    'has_text_layer': has_text_layer,
                    'page_range': f"{start_page}-{end_page}",
                    'file_size': pdf_path.stat().st_size if pdf_path.exists() else 0
                },
                'processing_metadata': {
                    'processing_time_seconds': processing_time,
                    'pages_processed': end_page - start_page + 1,
                    'extraction_timestamp': datetime.now().isoformat(),
                    'cache_used': use_cache,
                    'confidence_included': include_confidence
                },
                'cache_hit': False
            })
            
            # Update statistics
            self.extraction_stats['pages_processed'] += end_page - start_page + 1
            self.extraction_stats['total_processing_time'] += processing_time
            
            if extraction_method == ExtractionMethod.TEXT_LAYER:
                self.extraction_stats['text_layer_used'] += 1
            elif extraction_method == ExtractionMethod.OCR:
                self.extraction_stats['ocr_used'] += 1
            else:
                self.extraction_stats['hybrid_used'] += 1
            
            # Cache result if caching is enabled
            if use_cache and cache_key:
                try:
                    cache.set(cache_key, result, timeout=self.CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Failed to cache extraction result: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Text extraction error for {pdf_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'extraction_method': method.value if isinstance(method, ExtractionMethod) else str(method),
                'pages': [],
                'cache_hit': False
            }
    
    def _determine_extraction_method(
        self, 
        requested_method: ExtractionMethod,
        pdf_path: Path,
        has_text_layer: bool,
        page_range: Tuple[int, int]
    ) -> ExtractionMethod:
        """Intelligently determine the best extraction method.
        
        Args:
            requested_method: Method requested by user
            pdf_path: Path to PDF file
            has_text_layer: Whether PDF has text layer
            page_range: Page range to process
            
        Returns:
            Optimal extraction method
        """
        if requested_method != ExtractionMethod.AUTO:
            return requested_method
        
        # If no text layer, must use OCR
        if not has_text_layer:
            return ExtractionMethod.OCR
        
        # Analyze text layer quality for a subset of pages
        try:
            quality_analysis = self.pdf_processor.detect_text_layer_quality(pdf_path)
            
            if quality_analysis['success']:
                analysis = quality_analysis['analysis']
                
                # Check overall text coverage
                overall_coverage = analysis.get('overall_text_coverage', 0)
                ocr_pages = len(analysis.get('recommended_ocr_pages', []))
                total_pages = page_range[1] - page_range[0] + 1
                
                # Decision logic
                if overall_coverage >= 70 and ocr_pages == 0:
                    return ExtractionMethod.TEXT_LAYER
                elif overall_coverage < 30 or ocr_pages >= total_pages * 0.8:
                    return ExtractionMethod.OCR
                else:
                    return ExtractionMethod.HYBRID
            
            # Fallback if analysis fails
            return ExtractionMethod.TEXT_LAYER if has_text_layer else ExtractionMethod.OCR
            
        except Exception as e:
            logger.warning(f"Quality analysis failed: {str(e)}")
            return ExtractionMethod.TEXT_LAYER if has_text_layer else ExtractionMethod.OCR
    
    def _extract_text_layer(self, pdf_path: Path, page_range: Tuple[int, int], progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Extract text from PDF text layer.
        
        Args:
            pdf_path: Path to PDF file
            page_range: Page range (start, end)
            progress_callback: Optional callback for progress reporting
            
        Returns:
            Text layer extraction results
        """
        try:
            extraction_result = self.pdf_processor.extract_text(pdf_path)
            
            if not extraction_result['success']:
                return {
                    'success': False,
                    'error': f"Text layer extraction failed: {extraction_result['error']}",
                    'pages': [],
                    'extraction_source': 'text_layer'
                }
            
            # Filter pages by range
            start_page, end_page = page_range
            filtered_pages = [
                page for page in extraction_result['pages']
                if start_page <= page['page_number'] <= end_page
            ]
            
            # Process pages and add metadata
            processed_pages = []
            total_text_length = 0
            total_pages = len(filtered_pages)
            
            for idx, page in enumerate(filtered_pages, 1):
                # Report progress if callback provided
                if progress_callback:
                    try:
                        progress_callback(idx, total_pages)
                    except Exception as e:
                        logger.warning(f"Progress callback error: {e}")
                        
                text = page.get('text', '')
                text_length = len(text.strip())
                total_text_length += text_length
                
                # Assess text quality
                quality = self._assess_text_quality(text, page.get('char_count', text_length))
                
                processed_pages.append({
                    'page_number': page['page_number'],
                    'text': text,
                    'text_length': text_length,
                    'extraction_source': 'text_layer',
                    'extraction_confidence': 1.0,  # Text layer is always 100% confident
                    'text_quality': quality.value,
                    'has_content': text_length > 0,
                    'processing_metadata': {
                        'extraction_method': 'text_layer',
                        'original_char_count': page.get('char_count', text_length),
                        'error': page.get('error')
                    }
                })
            
            return {
                'success': True,
                'pages': processed_pages,
                'extraction_source': 'text_layer',
                'summary': {
                    'total_pages': len(processed_pages),
                    'pages_with_text': len([p for p in processed_pages if p['has_content']]),
                    'total_text_length': total_text_length,
                    'average_text_per_page': total_text_length / len(processed_pages) if processed_pages else 0,
                    'average_confidence': 1.0,  # Text layer always has 1.0 confidence (0.0-1.0 scale)
                    'extraction_method': 'text_layer',
                    'confidence_scale': '0.0-1.0'  # Document confidence scale used
                }
            }
            
        except Exception as e:
            logger.error(f"Text layer extraction error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'pages': [],
                'extraction_source': 'text_layer'
            }
    
    def _extract_ocr_only(self, pdf_path: Path, page_range: Tuple[int, int], progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Extract text using OCR only.
        
        Args:
            pdf_path: Path to PDF file
            page_range: Page range (start, end)
            progress_callback: Optional callback for progress reporting
            
        Returns:
            OCR extraction results
        """
        try:
            # Extract page images first
            image_result = self.pdf_processor.extract_pages_as_images(
                pdf_path, 
                dpi=300,
                page_range=page_range
            )
            
            if not image_result['success']:
                return {
                    'success': False,
                    'error': f"Image extraction failed: {image_result['error']}",
                    'pages': [],
                    'extraction_source': 'ocr'
                }
            
            processed_pages = []
            total_text_length = 0
            total_pages = len(image_result['images'])
            
            # Process each page image with OCR
            for idx, image_data in enumerate(image_result['images'], 1):
                # Report progress if callback provided
                if progress_callback:
                    try:
                        progress_callback(idx, total_pages)
                    except Exception as e:
                        logger.warning(f"Progress callback error: {e}")
                        
                if 'error' in image_data or not image_data.get('image_data'):
                    processed_pages.append({
                        'page_number': image_data['page_number'],
                        'text': '',
                        'text_length': 0,
                        'extraction_source': 'ocr',
                        'extraction_confidence': 0.0,
                        'text_quality': TextQuality.VERY_LOW.value,
                        'has_content': False,
                        'processing_metadata': {
                            'extraction_method': 'ocr',
                            'error': image_data.get('error', 'No image data available')
                        }
                    })
                    continue
                
                # Perform OCR on the image
                ocr_result = self.ocr_service.process_pdf_page_image(
                    image_data['image_data'],
                    image_data['page_number'],
                    dpi=300,
                    use_cache=True
                )
                
                if ocr_result['success']:
                    text = ocr_result.get('text', '')
                    text_length = len(text.strip())
                    total_text_length += text_length
                    confidence = ocr_result.get('confidence', 0.0)
                    # Convert confidence from 0-100 scale to 0-1 scale
                    if confidence > 1.0:
                        confidence = confidence / 100.0
                    
                    # Assess text quality based on OCR confidence and content
                    quality = self._assess_ocr_quality(text, confidence)
                    
                    processed_pages.append({
                        'page_number': image_data['page_number'],
                        'text': text,
                        'text_length': text_length,
                        'extraction_source': 'ocr',
                        'extraction_confidence': confidence,
                        'text_quality': quality.value,
                        'has_content': text_length > 0,
                        'processing_metadata': {
                            'extraction_method': 'ocr',
                            'ocr_confidence': confidence,
                            'words_detected': len(ocr_result.get('words', [])),
                            'preprocessing_info': ocr_result.get('preprocessing_info', {}),
                            'dpi_used': 300
                        }
                    })
                else:
                    processed_pages.append({
                        'page_number': image_data['page_number'],
                        'text': '',
                        'text_length': 0,
                        'extraction_source': 'ocr',
                        'extraction_confidence': 0.0,
                        'text_quality': TextQuality.VERY_LOW.value,
                        'has_content': False,
                        'processing_metadata': {
                            'extraction_method': 'ocr',
                            'error': ocr_result.get('error', 'OCR processing failed')
                        }
                    })
            
            return {
                'success': True,
                'pages': processed_pages,
                'extraction_source': 'ocr',
                'summary': {
                    'total_pages': len(processed_pages),
                    'pages_with_text': len([p for p in processed_pages if p['has_content']]),
                    'total_text_length': total_text_length,
                    'average_text_per_page': total_text_length / len(processed_pages) if processed_pages else 0,
                    'average_confidence': sum(p['extraction_confidence'] for p in processed_pages) / len(processed_pages) if processed_pages else 0,  # 0.0-1.0 scale
                    'extraction_method': 'ocr',
                    'confidence_scale': '0.0-1.0'  # Document confidence scale used
                }
            }
            
        except Exception as e:
            logger.error(f"OCR extraction error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'pages': [],
                'extraction_source': 'ocr'
            }
    
    def _extract_hybrid(self, pdf_path: Path, page_range: Tuple[int, int], progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Extract text using hybrid approach (text layer + OCR as needed).
        
        Args:
            pdf_path: Path to PDF file
            page_range: Page range (start, end)
            progress_callback: Optional callback for progress reporting
            
        Returns:
            Hybrid extraction results
        """
        try:
            # First, extract text layer
            text_result = self._extract_text_layer(pdf_path, page_range)
            if not text_result['success']:
                # Fall back to OCR only
                return self._extract_ocr_only(pdf_path, page_range)
            
            # Analyze which pages need OCR enhancement
            pages_needing_ocr = []
            for page in text_result['pages']:
                needs_ocr = (
                    page['text_length'] < self.MIN_PAGE_TEXT_LENGTH or
                    page['text_quality'] in [TextQuality.LOW.value, TextQuality.VERY_LOW.value]
                )
                if needs_ocr:
                    pages_needing_ocr.append(page['page_number'])
            
            if not pages_needing_ocr:
                # No OCR needed, return text layer results
                result = text_result
                result['extraction_source'] = 'hybrid'
                result['summary']['extraction_method'] = 'hybrid'
                # Ensure confidence scale is documented
                if 'confidence_scale' not in result['summary']:
                    result['summary']['confidence_scale'] = '0.0-1.0'
                for page in result['pages']:
                    page['extraction_source'] = 'hybrid'
                    page['processing_metadata']['extraction_method'] = 'hybrid'
                return result
            
            # Extract images for pages needing OCR - handle non-contiguous pages
            if len(pages_needing_ocr) == 1:
                # Single page
                image_result = self.pdf_processor.extract_pages_as_images(
                    pdf_path,
                    dpi=300,
                    page_range=(pages_needing_ocr[0], pages_needing_ocr[0])
                )
            elif len(set(pages_needing_ocr)) == len(pages_needing_ocr) and pages_needing_ocr == list(range(min(pages_needing_ocr), max(pages_needing_ocr) + 1)):
                # Contiguous pages
                image_result = self.pdf_processor.extract_pages_as_images(
                    pdf_path,
                    dpi=300,
                    page_range=(min(pages_needing_ocr), max(pages_needing_ocr))
                )
            else:
                # Non-contiguous pages - extract each page separately and combine
                image_result = {'success': True, 'images': []}
                for page_num in sorted(pages_needing_ocr):
                    page_result = self.pdf_processor.extract_pages_as_images(
                        pdf_path,
                        dpi=300,
                        page_range=(page_num, page_num)
                    )
                    if page_result['success'] and page_result.get('images'):
                        image_result['images'].extend(page_result['images'])
                    else:
                        # Add error entry for this page
                        image_result['images'].append({
                            'page_number': page_num,
                            'error': page_result.get('error', 'Failed to extract image'),
                            'image_data': None
                        })
                
                if not image_result['images']:
                    image_result['success'] = False
                    image_result['error'] = 'No pages could be extracted as images'
            
            if not image_result['success']:
                # Return text layer results if image extraction fails
                logger.warning(f"Image extraction failed for OCR enhancement: {image_result['error']}")
                result = text_result
                result['extraction_source'] = 'hybrid'
                result['summary']['extraction_method'] = 'hybrid'
                # Ensure confidence scale is documented
                if 'confidence_scale' not in result['summary']:
                    result['summary']['confidence_scale'] = '0.0-1.0'
                return result
            
            # Process OCR for needed pages
            ocr_results = {}
            for image_data in image_result['images']:
                if image_data['page_number'] in pages_needing_ocr and image_data.get('image_data'):
                    ocr_result = self.ocr_service.process_pdf_page_image(
                        image_data['image_data'],
                        image_data['page_number'],
                        dpi=300,
                        use_cache=True
                    )
                    
                    if ocr_result['success']:
                        # Convert confidence from 0-100 scale to 0-1 scale
                        if 'confidence' in ocr_result and ocr_result['confidence'] > 1.0:
                            ocr_result['confidence'] = ocr_result['confidence'] / 100.0
                        ocr_results[image_data['page_number']] = ocr_result
            
            # Combine text layer and OCR results
            processed_pages = []
            total_text_length = 0
            
            for page in text_result['pages']:
                page_num = page['page_number']
                
                if page_num in ocr_results:
                    # Combine text layer and OCR
                    ocr_data = ocr_results[page_num]
                    combined_text = self._combine_texts(
                        page['text'], 
                        ocr_data.get('text', ''),
                        page['extraction_confidence'],
                        ocr_data.get('confidence', 0.0)
                    )
                    
                    text_length = len(combined_text['text'].strip())
                    total_text_length += text_length
                    quality = self._assess_combined_quality(
                        combined_text['text'], 
                        combined_text['confidence'],
                        text_length
                    )
                    
                    processed_pages.append({
                        'page_number': page_num,
                        'text': combined_text['text'],
                        'text_length': text_length,
                        'extraction_source': 'hybrid',
                        'extraction_confidence': combined_text['confidence'],
                        'text_quality': quality.value,
                        'has_content': text_length > 0,
                        'processing_metadata': {
                            'extraction_method': 'hybrid',
                            'text_layer_length': page['text_length'],
                            'ocr_length': len(ocr_data.get('text', '').strip()),
                            'ocr_confidence': ocr_data.get('confidence', 0.0),
                            'combination_strategy': combined_text['strategy'],
                            'sources_used': combined_text['sources_used']
                        }
                    })
                else:
                    # Use text layer result
                    total_text_length += page['text_length']
                    page['extraction_source'] = 'hybrid'
                    page['processing_metadata']['extraction_method'] = 'hybrid'
                    processed_pages.append(page)
            
            return {
                'success': True,
                'pages': processed_pages,
                'extraction_source': 'hybrid',
                'summary': {
                    'total_pages': len(processed_pages),
                    'pages_with_text': len([p for p in processed_pages if p['has_content']]),
                    'total_text_length': total_text_length,
                    'average_text_per_page': total_text_length / len(processed_pages) if processed_pages else 0,
                    'average_confidence': sum(p['extraction_confidence'] for p in processed_pages) / len(processed_pages) if processed_pages else 0,  # 0.0-1.0 scale
                    'pages_enhanced_with_ocr': len(ocr_results),
                    'extraction_method': 'hybrid',
                    'confidence_scale': '0.0-1.0'  # Document confidence scale used
                }
            }
            
        except Exception as e:
            logger.error(f"Hybrid extraction error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'pages': [],
                'extraction_source': 'hybrid'
            }
    
    def _combine_texts(
        self, 
        text_layer_text: str, 
        ocr_text: str,
        text_layer_confidence: float,
        ocr_confidence: float
    ) -> Dict[str, Any]:
        """Intelligently combine text from different sources.
        
        Args:
            text_layer_text: Text from PDF text layer
            ocr_text: Text from OCR
            text_layer_confidence: Confidence of text layer extraction
            ocr_confidence: Confidence of OCR extraction
            
        Returns:
            Dictionary with combined text and metadata
        """
        text_layer_len = len(text_layer_text.strip())
        ocr_len = len(ocr_text.strip())
        
        # Strategy 1: Use longer text if one is significantly longer
        length_ratio = max(text_layer_len, ocr_len) / max(min(text_layer_len, ocr_len), 1)
        
        if length_ratio > 3:
            if text_layer_len > ocr_len:
                return {
                    'text': text_layer_text,
                    'confidence': text_layer_confidence,
                    'strategy': 'text_layer_preferred_by_length',
                    'sources_used': ['text_layer']
                }
            else:
                return {
                    'text': ocr_text,
                    'confidence': ocr_confidence,
                    'strategy': 'ocr_preferred_by_length',
                    'sources_used': ['ocr']
                }
        
        # Strategy 2: Use higher confidence if confidence gap is significant (0.0-1.0 scale)
        confidence_difference = abs(text_layer_confidence - ocr_confidence)
        if confidence_difference > 0.3:
            if text_layer_confidence > ocr_confidence:
                return {
                    'text': text_layer_text,
                    'confidence': text_layer_confidence,
                    'strategy': 'text_layer_preferred_by_confidence',
                    'sources_used': ['text_layer']
                }
            else:
                return {
                    'text': ocr_text,
                    'confidence': ocr_confidence,
                    'strategy': 'ocr_preferred_by_confidence',
                    'sources_used': ['ocr']
                }
        
        # Strategy 3: Merge both sources with confidence weighting
        if text_layer_len > 0 and ocr_len > 0:
            # Simple merge by appending (could be enhanced with NLP techniques)
            merged_text = f"{text_layer_text}\n\n--- OCR ENHANCEMENT ---\n\n{ocr_text}"
            weighted_confidence = (
                (text_layer_confidence * text_layer_len + ocr_confidence * ocr_len) /
                (text_layer_len + ocr_len)
            )
            
            return {
                'text': merged_text,
                'confidence': weighted_confidence,
                'strategy': 'weighted_merge',
                'sources_used': ['text_layer', 'ocr']
            }
        
        # Strategy 4: Use whichever has content
        if text_layer_len > 0:
            return {
                'text': text_layer_text,
                'confidence': text_layer_confidence,
                'strategy': 'text_layer_only_available',
                'sources_used': ['text_layer']
            }
        elif ocr_len > 0:
            return {
                'text': ocr_text,
                'confidence': ocr_confidence,
                'strategy': 'ocr_only_available',
                'sources_used': ['ocr']
            }
        else:
            return {
                'text': '',
                'confidence': 0.0,
                'strategy': 'no_text_available',
                'sources_used': []
            }
    
    def _assess_text_quality(self, text: str, char_count: int) -> TextQuality:
        """Assess quality of extracted text.
        
        Args:
            text: Extracted text content
            char_count: Character count
            
        Returns:
            Text quality assessment
        """
        if not text or char_count == 0:
            return TextQuality.VERY_LOW
        
        text_len = len(text.strip())
        
        # Basic length-based assessment
        if text_len >= 500:
            return TextQuality.HIGH
        elif text_len >= 100:
            return TextQuality.MEDIUM
        elif text_len >= 20:
            return TextQuality.LOW
        else:
            return TextQuality.VERY_LOW
    
    def _assess_ocr_quality(self, text: str, confidence: float) -> TextQuality:
        """Assess quality of OCR-extracted text.
        
        Args:
            text: OCR-extracted text
            confidence: OCR confidence score
            
        Returns:
            Text quality assessment
        """
        if confidence >= self.HIGH_QUALITY_THRESHOLD and len(text.strip()) > 100:
            return TextQuality.HIGH
        elif confidence >= self.MEDIUM_QUALITY_THRESHOLD and len(text.strip()) > 50:
            return TextQuality.MEDIUM
        elif confidence >= self.LOW_QUALITY_THRESHOLD and len(text.strip()) > 10:
            return TextQuality.LOW
        else:
            return TextQuality.VERY_LOW
    
    def _assess_combined_quality(self, text: str, confidence: float, text_length: int) -> TextQuality:
        """Assess quality of combined text from multiple sources.
        
        Args:
            text: Combined text content
            confidence: Combined confidence score
            text_length: Length of combined text
            
        Returns:
            Text quality assessment
        """
        # Combined assessment considers both confidence and length
        quality_score = confidence * 0.7 + min(text_length / 1000, 1.0) * 0.3
        
        if quality_score >= 0.8:
            return TextQuality.HIGH
        elif quality_score >= 0.6:
            return TextQuality.MEDIUM
        elif quality_score >= 0.3:
            return TextQuality.LOW
        else:
            return TextQuality.VERY_LOW
    
    def _add_confidence_scoring(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Add detailed confidence scoring to extraction results.
        
        Args:
            result: Extraction result dictionary
            
        Returns:
            Result with added confidence scoring
        """
        if not result.get('success') or not result.get('pages'):
            return result
        
        # Calculate overall confidence metrics
        pages = result['pages']
        confidences = [p['extraction_confidence'] for p in pages]
        text_lengths = [p['text_length'] for p in pages]
        
        confidence_stats = {
            'min_confidence': min(confidences) if confidences else 0,  # 0.0-1.0 scale
            'max_confidence': max(confidences) if confidences else 0,  # 0.0-1.0 scale
            'average_confidence': sum(confidences) / len(confidences) if confidences else 0,  # 0.0-1.0 scale
            'weighted_confidence': (  # Text-length weighted confidence (0.0-1.0 scale)
                sum(c * l for c, l in zip(confidences, text_lengths)) /
                sum(text_lengths) if sum(text_lengths) > 0 else 0
            ),
            'confidence_distribution': self._get_confidence_distribution(confidences),
            'quality_distribution': self._get_quality_distribution(pages),
            'confidence_scale': '0.0-1.0'  # Document confidence scale used throughout
        }
        
        result['confidence_analysis'] = confidence_stats
        return result
    
    def _get_confidence_distribution(self, confidences: List[float]) -> Dict[str, int]:
        """Get distribution of confidence scores (0.0-1.0 scale).
        
        Args:
            confidences: List of confidence scores (0.0-1.0)
            
        Returns:
            Distribution dictionary with 0-1 scale bins
        """
        distribution = {
            '0.9-1.0': 0,
            '0.8-0.89': 0,
            '0.7-0.79': 0,
            '0.6-0.69': 0,
            '0.5-0.59': 0,
            'below-0.5': 0
        }
        
        for confidence in confidences:
            if confidence >= 0.9:
                distribution['0.9-1.0'] += 1
            elif confidence >= 0.8:
                distribution['0.8-0.89'] += 1
            elif confidence >= 0.7:
                distribution['0.7-0.79'] += 1
            elif confidence >= 0.6:
                distribution['0.6-0.69'] += 1
            elif confidence >= 0.5:
                distribution['0.5-0.59'] += 1
            else:
                distribution['below-0.5'] += 1
        
        return distribution
    
    def _get_quality_distribution(self, pages: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get distribution of text quality levels.
        
        Args:
            pages: List of page dictionaries
            
        Returns:
            Quality distribution dictionary
        """
        distribution = {
            'high': 0,
            'medium': 0,
            'low': 0,
            'very_low': 0
        }
        
        for page in pages:
            quality = page.get('text_quality', 'very_low')
            distribution[quality] += 1
        
        return distribution
    
    def _generate_cache_key(
        self, 
        pdf_path: Path, 
        method: ExtractionMethod,
        page_range: Optional[Tuple[int, int]]
    ) -> str:
        """Generate cache key for extraction results.
        
        Args:
            pdf_path: Path to PDF file
            method: Extraction method
            page_range: Page range
            
        Returns:
            Cache key string
        """
        try:
            # Use file hash and modification time for cache key
            file_stat = pdf_path.stat()
            content_hash = hashlib.md5(
                f"{pdf_path}{file_stat.st_mtime}{file_stat.st_size}".encode()
            ).hexdigest()
            
            range_str = f"{page_range[0]}-{page_range[1]}" if page_range else "all"
            
            return f"{self.CACHE_PREFIX}_{content_hash}_{method.value}_{range_str}"
        except Exception as e:
            logger.warning(f"Cache key generation failed: {str(e)}")
            return f"{self.CACHE_PREFIX}_{hash(str(pdf_path))}_{method.value}"
    
    def get_extraction_statistics(self) -> Dict[str, Any]:
        """Get current extraction statistics.
        
        Returns:
            Statistics dictionary
        """
        stats = self.extraction_stats.copy()
        
        # Calculate additional metrics
        total_extractions = (
            stats['text_layer_used'] + 
            stats['ocr_used'] + 
            stats['hybrid_used']
        )
        
        if total_extractions > 0:
            stats['method_distribution'] = {
                'text_layer_percentage': (stats['text_layer_used'] / total_extractions) * 100,
                'ocr_percentage': (stats['ocr_used'] / total_extractions) * 100,
                'hybrid_percentage': (stats['hybrid_used'] / total_extractions) * 100
            }
            
            stats['average_processing_time'] = (
                stats['total_processing_time'] / total_extractions
            )
            
            stats['cache_hit_rate'] = (
                (stats['cache_hits'] / total_extractions) * 100
            )
        else:
            stats['method_distribution'] = {
                'text_layer_percentage': 0,
                'ocr_percentage': 0,
                'hybrid_percentage': 0
            }
            stats['average_processing_time'] = 0
            stats['cache_hit_rate'] = 0
        
        stats['total_extractions'] = total_extractions
        return stats
    
    def clear_cache(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """Clear extraction cache.
        
        Args:
            pattern: Optional pattern to match cache keys
            
        Returns:
            Cache clearing results
        """
        try:
            if pattern:
                # Pattern-based clearing - find all keys with the pattern
                try:
                    # Try to get all cache keys (this may not be supported by all backends)
                    from django.core.cache.backends.base import InvalidCacheBackendError
                    cleared_count = 0
                    
                    # Since Django cache doesn't provide key iteration, we'll just clear by prefix
                    if pattern.startswith(self.CACHE_PREFIX):
                        # For specific prefix clearing, we'd need to maintain a key registry
                        logger.info(f"Pattern-based cache clearing requested for: {pattern}")
                        return {
                            'success': True,
                            'message': f'Pattern-based clearing attempted for {pattern}',
                            'cleared_keys': 0
                        }
                    else:
                        return {
                            'success': False,
                            'message': f'Invalid pattern: {pattern}. Must start with {self.CACHE_PREFIX}',
                            'cleared_keys': 0
                        }
                        
                except Exception as e:
                    logger.warning(f"Pattern-based cache clearing failed: {e}")
                    return {
                        'success': False,
                        'error': str(e),
                        'cleared_keys': 0
                    }
            else:
                # Clear all cache - this clears the entire Django cache
                # In production, you might want to be more selective
                cache.clear()
                return {
                    'success': True,
                    'message': 'All extraction cache cleared',
                    'cleared_keys': 'global cache cleared'
                }
                
        except Exception as e:
            logger.error(f"Cache clearing error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'cleared_keys': 0
            }
    
    def extract_structured_text(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None,
        output_format: str = 'json',
        include_formatting: bool = False,
        export_to_files: bool = True
    ) -> Dict[str, Any]:
        """Extract text with structured output and multiple format support.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional tuple of (start_page, end_page) (1-indexed)
            output_format: Output format ('json', 'txt', 'structured')
            include_formatting: Whether to preserve formatting information
            export_to_files: Whether to export results to files
            
        Returns:
            Dictionary containing structured extraction results
        """
        try:
            logger.info(f"Starting structured text extraction from {file_path}")
            
            # Use existing unified extraction as base
            base_result = self.extract_text_unified(
                file_path,
                method=ExtractionMethod.AUTO,
                page_range=page_range,
                include_confidence=True
            )
            
            if not base_result['success']:
                return base_result
            
            # Extract structured text with formatting if requested
            if include_formatting:
                formatting_result = self._extract_text_with_formatting(file_path, page_range)
                if formatting_result['success']:
                    # Merge formatting data with base result
                    for page in base_result['pages']:
                        page_num = page['page_number']
                        formatting_page = next(
                            (p for p in formatting_result['pages'] if p['page_number'] == page_num),
                            None
                        )
                        if formatting_page:
                            page['formatting_data'] = formatting_page.get('formatting_data', {})
            
            # Organize text by structure
            structured_data = self._organize_text_by_structure(base_result['pages'])
            
            # Calculate text statistics
            text_stats = self._calculate_text_statistics(structured_data)
            
            # Detect language
            language = self._detect_text_language_enhanced(structured_data.get('full_text', ''))
            
            # Prepare structured result
            structured_result = {
                'success': True,
                'structured_data': structured_data,
                'text_statistics': text_stats,
                'language_info': language,
                'extraction_metadata': {
                    'include_formatting': include_formatting,
                    'output_format': output_format,
                    'extraction_method': base_result.get('extraction_method', 'auto'),
                    'pages_processed': len(base_result['pages']),
                    'page_range': page_range
                },
                'files': []
            }
            
            # Export to files if requested
            if export_to_files:
                export_result = self._export_text_to_formats(
                    structured_data,
                    [output_format]
                )
                if export_result:
                    structured_result['files'] = export_result
            
            logger.info("Structured text extraction completed successfully")
            return structured_result
            
        except Exception as e:
            logger.error(f"Structured text extraction error: {e}")
            return {
                'success': False,
                'error': str(e),
                'structured_data': {},
                'files': []
            }
    
    def _extract_text_with_formatting(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None
    ) -> Dict[str, Any]:
        """Extract text with formatting and layout information.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional page range
            
        Returns:
            Dictionary containing text with formatting data
        """
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            
            # Determine pages to process
            if page_range:
                start, end = page_range
                start = max(1, start) - 1  # Convert to 0-indexed
                end = min(total_pages, end)
                pages_to_process = list(range(start, end))
            else:
                pages_to_process = list(range(total_pages))
            
            formatted_pages = []
            
            for page_num in pages_to_process:
                page = doc.load_page(page_num)
                
                # Extract text with detailed formatting
                text_dict = page.get_text("dict")
                
                # Process text blocks with formatting
                text_blocks = []
                fonts_used = set()
                
                for block in text_dict.get("blocks", []):
                    if "lines" in block:  # Text block
                        block_data = {
                            'bbox': block.get('bbox', []),
                            'lines': []
                        }
                        
                        for line in block["lines"]:
                            line_data = {
                                'bbox': line.get('bbox', []),
                                'spans': []
                            }
                            
                            for span in line["spans"]:
                                font_info = f"{span.get('font', '')}_{span.get('size', 0)}_{span.get('flags', 0)}"
                                fonts_used.add(font_info)
                                
                                span_data = {
                                    'text': span.get('text', ''),
                                    'font': span.get('font', ''),
                                    'size': span.get('size', 0),
                                    'flags': span.get('flags', 0),
                                    'color': span.get('color', 0),
                                    'bbox': span.get('bbox', []),
                                    'is_bold': bool(span.get('flags', 0) & 2**4),
                                    'is_italic': bool(span.get('flags', 0) & 2**1),
                                }
                                
                                line_data['spans'].append(span_data)
                            
                            block_data['lines'].append(line_data)
                        
                        text_blocks.append(block_data)
                
                # Combine all text for the page
                page_text = page.get_text()
                
                formatting_data = {
                    'text_blocks': text_blocks,
                    'fonts_used': list(fonts_used),
                    'page_dimensions': {
                        'width': page.rect.width,
                        'height': page.rect.height
                    },
                    'text_coverage': len(page_text.strip()) / (page.rect.width * page.rect.height) if page.rect.width * page.rect.height > 0 else 0
                }
                
                formatted_pages.append({
                    'page_number': page_num + 1,
                    'text': page_text,
                    'formatting_data': formatting_data
                })
            
            doc.close()
            
            return {
                'success': True,
                'pages': formatted_pages
            }
            
        except Exception as e:
            logger.error(f"Error extracting text with formatting: {e}")
            return {
                'success': False,
                'error': str(e),
                'pages': []
            }
    
    def _organize_text_by_structure(self, text_data: List[Dict]) -> Dict[str, Any]:
        """Organize extracted text by structural elements.
        
        Args:
            text_data: List of page text data
            
        Returns:
            Dictionary with organized text structure
        """
        full_text = ""
        pages_data = []
        paragraphs = []
        headers = []
        
        for page in text_data:
            page_text = page.get('text', '')
            full_text += page_text + "\n"
            
            # Simple paragraph detection by double line breaks
            page_paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
            
            # Simple header detection (lines that are short and followed by longer text)
            lines = page_text.split('\n')
            page_headers = []
            
            for i, line in enumerate(lines):
                line = line.strip()
                if (len(line) < 100 and len(line) > 5 and 
                    i < len(lines) - 1 and len(lines[i + 1].strip()) > len(line)):
                    # Potential header
                    page_headers.append({
                        'text': line,
                        'page': page['page_number'],
                        'line_number': i + 1
                    })
            
            paragraphs.extend(page_paragraphs)
            headers.extend(page_headers)
            
            pages_data.append({
                'page_number': page['page_number'],
                'text': page_text,
                'paragraphs': page_paragraphs,
                'headers': page_headers,
                'text_length': len(page_text),
                'extraction_source': page.get('extraction_source', 'unknown'),
                'confidence': page.get('extraction_confidence', 0.0)
            })
        
        return {
            'full_text': full_text.strip(),
            'pages': pages_data,
            'paragraphs': paragraphs,
            'headers': headers,
            'total_pages': len(pages_data),
            'total_paragraphs': len(paragraphs),
            'total_headers': len(headers)
        }
    
    def _export_text_to_formats(
        self,
        text_data: Dict[str, Any],
        formats: List[str]
    ) -> List[Dict[str, Any]]:
        """Export text data to multiple formats.
        
        Args:
            text_data: Structured text data
            formats: List of output formats ('json', 'txt', 'structured')
            
        Returns:
            List of exported file information
        """
        exported_files = []
        downloads_dir = self.temp_file_manager.downloads_dir
        
        for format_type in formats:
            try:
                if format_type.lower() == 'json':
                    # Export as JSON
                    filename = f'text_structured_{self.session_id[:8]}.json'
                    file_path = downloads_dir / filename
                    
                    export_data = {
                        'extraction_info': {
                            'timestamp': datetime.now().isoformat(),
                            'format': 'structured_json',
                            'session_id': self.session_id
                        },
                        'text_data': text_data
                    }
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)
                    
                elif format_type.lower() == 'txt':
                    # Export as plain text
                    filename = f'text_extracted_{self.session_id[:8]}.txt'
                    file_path = downloads_dir / filename
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(text_data.get('full_text', ''))
                
                elif format_type.lower() == 'structured':
                    # Export as structured text with sections
                    filename = f'text_structured_{self.session_id[:8]}.txt'
                    file_path = downloads_dir / filename
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write("=== DOCUMENT STRUCTURE ===\n\n")
                        
                        # Write headers
                        if text_data.get('headers'):
                            f.write("HEADERS:\n")
                            for header in text_data['headers']:
                                f.write(f"- {header['text']} (Page {header['page']})\n")
                            f.write("\n")
                        
                        # Write full text by pages
                        f.write("=== FULL TEXT BY PAGES ===\n\n")
                        for page in text_data.get('pages', []):
                            f.write(f"--- Page {page['page_number']} ---\n")
                            f.write(page['text'])
                            f.write("\n\n")
                
                else:
                    logger.warning(f"Unsupported export format: {format_type}")
                    continue
                
                file_info = {
                    'filename': filename,
                    'file_path': str(file_path),
                    'file_size': file_path.stat().st_size,
                    'format': format_type.lower(),
                    'type': 'structured_text'
                }
                
                exported_files.append(file_info)
                logger.info(f"Exported structured text to {filename}")
                
            except Exception as e:
                logger.error(f"Error exporting to {format_type}: {e}")
                continue
        
        return exported_files
    
    def _detect_text_language_enhanced(self, text: str) -> Dict[str, Any]:
        """Enhanced language detection for extracted text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with language detection results
        """
        if not text or len(text.strip()) < 50:
            return {
                'primary_language': 'unknown',
                'confidence': 0.0,
                'languages_detected': [],
                'text_sample_length': len(text.strip())
            }
        
        # Simple language detection based on character patterns and common words
        text_lower = text.lower()
        
        # English indicators
        english_words = ['the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'a', 'an', 'is', 'are', 'was', 'were']
        english_score = sum(1 for word in english_words if f' {word} ' in f' {text_lower} ')
        
        # Spanish indicators
        spanish_words = ['el', 'la', 'de', 'en', 'y', 'es', 'un', 'una', 'con', 'por', 'para', 'que', 'del', 'los', 'las']
        spanish_score = sum(1 for word in spanish_words if f' {word} ' in f' {text_lower} ')
        
        # French indicators
        french_words = ['le', 'de', 'et', 'à', 'un', 'une', 'ce', 'que', 'qui', 'dans', 'avec', 'sur', 'pour', 'du', 'des']
        french_score = sum(1 for word in french_words if f' {word} ' in f' {text_lower} ')
        
        # German indicators
        german_words = ['der', 'die', 'und', 'in', 'den', 'von', 'zu', 'das', 'mit', 'ist', 'im', 'für', 'auf', 'eine', 'einen']
        german_score = sum(1 for word in german_words if f' {word} ' in f' {text_lower} ')
        
        scores = {
            'english': english_score,
            'spanish': spanish_score,
            'french': french_score,
            'german': german_score
        }
        
        # Determine primary language
        max_score = max(scores.values())
        if max_score >= 3:
            primary_language = max(scores, key=scores.get)
            confidence = min(max_score / 20.0, 1.0)  # Normalize to 0-1
        else:
            primary_language = 'unknown'
            confidence = 0.0
        
        # Languages detected (those with significant scores)
        detected_languages = [lang for lang, score in scores.items() if score >= 2]
        
        return {
            'primary_language': primary_language,
            'confidence': confidence,
            'languages_detected': detected_languages,
            'language_scores': scores,
            'text_sample_length': len(text.strip())
        }
    
    def _calculate_text_statistics(self, text_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate comprehensive text statistics.
        
        Args:
            text_data: Structured text data
            
        Returns:
            Dictionary with text statistics
        """
        full_text = text_data.get('full_text', '')
        
        if not full_text:
            return {
                'total_characters': 0,
                'total_words': 0,
                'total_sentences': 0,
                'average_words_per_sentence': 0,
                'average_characters_per_word': 0,
                'reading_time_minutes': 0,
                'complexity_score': 0.0
            }
        
        # Basic counts
        total_chars = len(full_text)
        total_chars_no_spaces = len(full_text.replace(' ', ''))
        words = full_text.split()
        total_words = len(words)
        
        # Sentence count (simple approximation)
        sentences = [s.strip() for s in full_text.replace('!', '.').replace('?', '.').split('.') if s.strip()]
        total_sentences = len(sentences)
        
        # Calculate averages
        avg_words_per_sentence = total_words / max(total_sentences, 1)
        avg_chars_per_word = total_chars_no_spaces / max(total_words, 1)
        
        # Reading time (average 250 words per minute)
        reading_time = max(1, round(total_words / 250))
        
        # Simple complexity score based on sentence length and word length
        complexity_factors = []
        if avg_words_per_sentence > 20:
            complexity_factors.append(0.3)  # Long sentences
        if avg_chars_per_word > 6:
            complexity_factors.append(0.2)  # Long words
        if total_words > 5000:
            complexity_factors.append(0.2)  # Long document
        
        complexity_score = sum(complexity_factors)
        
        # Page-level statistics
        page_stats = []
        for page in text_data.get('pages', []):
            page_text = page.get('text', '')
            page_words = len(page_text.split())
            
            page_stats.append({
                'page_number': page['page_number'],
                'characters': len(page_text),
                'words': page_words,
                'confidence': page.get('confidence', 0.0)
            })
        
        return {
            'total_characters': total_chars,
            'total_characters_no_spaces': total_chars_no_spaces,
            'total_words': total_words,
            'total_sentences': total_sentences,
            'average_words_per_sentence': round(avg_words_per_sentence, 1),
            'average_characters_per_word': round(avg_chars_per_word, 1),
            'reading_time_minutes': reading_time,
            'complexity_score': round(complexity_score, 2),
            'page_statistics': page_stats,
            'total_pages': len(text_data.get('pages', [])),
            'total_paragraphs': text_data.get('total_paragraphs', 0),
            'total_headers': text_data.get('total_headers', 0)
        }
    
    def _validate_text_quality(self, text: str, confidence_threshold: float = 0.8) -> Dict[str, Any]:
        """Validate text extraction quality.
        
        Args:
            text: Extracted text to validate
            confidence_threshold: Minimum confidence threshold
            
        Returns:
            Dictionary with quality validation results
        """
        if not text:
            return {
                'is_valid': False,
                'quality_score': 0.0,
                'issues': ['No text content'],
                'recommendations': ['Check if PDF contains readable text or try OCR']
            }
        
        issues = []
        recommendations = []
        quality_factors = []
        
        # Check text length
        if len(text.strip()) < 50:
            issues.append('Very short text content')
            recommendations.append('Verify PDF contains readable text')
            quality_factors.append(0.2)
        else:
            quality_factors.append(0.8)
        
        # Check for garbled text (high ratio of special characters)
        text_chars = len([c for c in text if c.isalnum() or c.isspace()])
        total_chars = len(text)
        if total_chars > 0:
            text_ratio = text_chars / total_chars
            if text_ratio < 0.7:
                issues.append('High ratio of non-text characters')
                recommendations.append('Consider using OCR for better text extraction')
                quality_factors.append(0.3)
            else:
                quality_factors.append(0.9)
        
        # Check for repeated patterns (possible OCR errors)
        words = text.split()
        if len(words) > 10:
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.5:
                issues.append('High repetition in text')
                recommendations.append('Review extraction quality and consider alternative methods')
                quality_factors.append(0.4)
            else:
                quality_factors.append(0.8)
        
        quality_score = sum(quality_factors) / len(quality_factors) if quality_factors else 0.0
        is_valid = quality_score >= confidence_threshold and len(issues) == 0
        
        return {
            'is_valid': is_valid,
            'quality_score': quality_score,
            'issues': issues,
            'recommendations': recommendations,
            'text_length': len(text),
            'word_count': len(words) if 'words' in locals() else 0
        }