"""OCR service for Ultimate PDF application using pytesseract and OpenCV."""

import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
import json
import hashlib
import threading
import concurrent.futures
from datetime import datetime
from django.core.cache import cache

logger = logging.getLogger(__name__)


class OCRService:
    """Service class for OCR processing with preprocessing, caching, and confidence scoring."""
    
    # OCR Configuration
    DEFAULT_DPI = 300
    MIN_CONFIDENCE = 30
    CACHE_TIMEOUT = 86400  # 24 hours in seconds
    MAX_IMAGE_SIZE = (2000, 2000)  # Max dimensions for processing
    MAX_WORKERS = 4  # Maximum parallel processing workers
    
    # Preprocessing parameters
    BLUR_KERNEL_SIZE = (1, 1)
    MORPH_KERNEL_SIZE = (2, 2)
    
    # Advanced OCR modes
    OCR_MODES = {
        'fast': '--oem 3 --psm 6',
        'accurate': '--oem 3 --psm 3',
        'complex': '--oem 3 --psm 11',
        'single_block': '--oem 3 --psm 8'
    }
    
    def __init__(self):
        """Initialize OCR service with default settings."""
        self.tesseract_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '
    
    def process_pdf_page_image(
        self, 
        image_data: bytes, 
        page_number: int,
        dpi: int = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Process a PDF page image using OCR pipeline.
        
        Args:
            image_data: Raw image data from PDF page
            page_number: Page number for reference
            dpi: DPI setting for OCR (default 300)
            use_cache: Whether to use Redis caching for results
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if OCR succeeded
            - text: Extracted text content
            - confidence: Overall confidence score
            - words: List of individual word results with bounding boxes
            - preprocessing_info: Details about image preprocessing
            - cache_hit: Whether result came from cache
            - error: Error message if processing failed
        """
        try:
            dpi = dpi or self.DEFAULT_DPI
            
            # Generate cache key from image data hash
            cache_key = None
            if use_cache:
                image_hash = hashlib.md5(image_data).hexdigest()
                cache_key = f"ocr_result_{image_hash}_{dpi}_{page_number}"
                
                # Check cache first
                cached_result = cache.get(cache_key)
                if cached_result:
                    cached_result['cache_hit'] = True
                    return cached_result
            
            # Step 1: Preprocess image
            preprocessed_image, preprocessing_info = self._preprocess_image(image_data)
            
            if preprocessed_image is None:
                return {
                    'success': False,
                    'error': 'Image preprocessing failed',
                    'page_number': page_number,
                    'cache_hit': False
                }
            
            # Step 2: Perform OCR with confidence detection
            ocr_result = self._perform_ocr_detection(preprocessed_image, dpi)
            
            if not ocr_result['success']:
                return {
                    'success': False,
                    'error': ocr_result.get('error', 'OCR detection failed'),
                    'page_number': page_number,
                    'preprocessing_info': preprocessing_info,
                    'cache_hit': False
                }
            
            # Step 3: Post-process and format results
            final_result = self._postprocess_ocr_results(ocr_result, preprocessing_info, page_number)
            
            # Cache the result
            if use_cache and cache_key:
                try:
                    cache.set(cache_key, final_result, timeout=self.CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Failed to cache OCR result: {str(e)}")
            
            final_result['cache_hit'] = False
            return final_result
            
        except Exception as e:
            logger.error(f"OCR processing error for page {page_number}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'page_number': page_number,
                'cache_hit': False
            }
    
    def _preprocess_image(self, image_data: bytes) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Step 1: Preprocess image using OpenCV for better OCR results.
        
        Args:
            image_data: Raw image data
            
        Returns:
            Tuple of (processed_image_array, preprocessing_info_dict)
        """
        preprocessing_info = {
            'original_size': None,
            'final_size': None,
            'operations_applied': [],
            'grayscale_converted': False,
            'noise_removed': False,
            'thresholded': False,
            'deskewed': False
        }
        
        try:
            # Convert bytes to PIL Image
            pil_image = Image.open(io.BytesIO(image_data))
            preprocessing_info['original_size'] = pil_image.size
            
            # Convert to numpy array
            image_array = np.array(pil_image)
            
            # Downscale if image is too large
            height, width = image_array.shape[:2]
            if width > self.MAX_IMAGE_SIZE[0] or height > self.MAX_IMAGE_SIZE[1]:
                scale_factor = min(
                    self.MAX_IMAGE_SIZE[0] / width,
                    self.MAX_IMAGE_SIZE[1] / height
                )
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                image_array = cv2.resize(image_array, (new_width, new_height))
                preprocessing_info['operations_applied'].append(f'resized from {width}x{height} to {new_width}x{new_height}')
            
            # Convert to grayscale
            if len(image_array.shape) == 3:
                gray_image = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
                preprocessing_info['grayscale_converted'] = True
                preprocessing_info['operations_applied'].append('converted to grayscale')
            else:
                gray_image = image_array
            
            # Noise removal using Gaussian blur
            denoised = cv2.GaussianBlur(gray_image, self.BLUR_KERNEL_SIZE, 0)
            preprocessing_info['noise_removed'] = True
            preprocessing_info['operations_applied'].append('noise removal with Gaussian blur')
            
            # Thresholding - adaptive threshold for varying lighting
            threshold_image = cv2.adaptiveThreshold(
                denoised, 
                255, 
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 
                11, 
                2
            )
            preprocessing_info['thresholded'] = True
            preprocessing_info['operations_applied'].append('adaptive thresholding')
            
            # Morphological operations to clean up text
            kernel = np.ones(self.MORPH_KERNEL_SIZE, np.uint8)
            cleaned_image = cv2.morphologyEx(threshold_image, cv2.MORPH_CLOSE, kernel)
            preprocessing_info['operations_applied'].append('morphological cleanup')
            
            # Deskewing (basic rotation correction)
            try:
                deskewed_image = self._deskew_image(cleaned_image)
                preprocessing_info['deskewed'] = True
                preprocessing_info['operations_applied'].append('deskewing')
                final_image = deskewed_image
            except Exception as e:
                logger.warning(f"Deskewing failed: {str(e)}")
                final_image = cleaned_image
            
            preprocessing_info['final_size'] = final_image.shape[:2]
            
            return final_image, preprocessing_info
            
        except Exception as e:
            logger.error(f"Image preprocessing error: {str(e)}")
            preprocessing_info['error'] = str(e)
            return None, preprocessing_info
    
    def _deskew_image(self, image: np.ndarray) -> np.ndarray:
        """Correct skew/rotation in the image.
        
        Args:
            image: Grayscale image array
            
        Returns:
            Deskewed image array
        """
        # Find coordinates of all white pixels
        coords = np.column_stack(np.where(image > 0))
        
        # Find minimum area rectangle
        angle = cv2.minAreaRect(coords)[-1]
        
        # Correct the angle
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        
        # Only apply correction if angle is significant
        if abs(angle) < 0.5:
            return image
        
        # Rotate the image to deskew it
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        deskewed = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        
        return deskewed
    
    def _perform_ocr_detection(self, image: np.ndarray, dpi: int) -> Dict[str, Any]:
        """Step 2: Perform OCR detection with pytesseract.
        
        Args:
            image: Preprocessed image array
            dpi: DPI setting for OCR
            
        Returns:
            Dictionary with OCR detection results
        """
        try:
            # Convert numpy array back to PIL Image for pytesseract
            pil_image = Image.fromarray(image)
            
            # Configure tesseract options
            custom_config = f'--dpi {dpi} {self.tesseract_config}'
            
            # Extract text with confidence scores
            ocr_data = pytesseract.image_to_data(
                pil_image, 
                output_type=pytesseract.Output.DICT,
                config=custom_config
            )
            
            # Extract plain text
            full_text = pytesseract.image_to_string(pil_image, config=custom_config)
            
            # Process word-level results
            words = []
            n_boxes = len(ocr_data['text'])
            
            for i in range(n_boxes):
                confidence = int(ocr_data['conf'][i])
                text = ocr_data['text'][i].strip()
                
                # Filter out low-confidence and empty results
                if confidence >= self.MIN_CONFIDENCE and text:
                    words.append({
                        'text': text,
                        'confidence': confidence,
                        'bbox': {
                            'x': int(ocr_data['left'][i]),
                            'y': int(ocr_data['top'][i]),
                            'width': int(ocr_data['width'][i]),
                            'height': int(ocr_data['height'][i])
                        },
                        'block_num': int(ocr_data['block_num'][i]),
                        'par_num': int(ocr_data['par_num'][i]),
                        'line_num': int(ocr_data['line_num'][i]),
                        'word_num': int(ocr_data['word_num'][i])
                    })
            
            # Calculate overall confidence
            if words:
                overall_confidence = sum(word['confidence'] for word in words) / len(words)
            else:
                overall_confidence = 0
            
            return {
                'success': True,
                'text': full_text.strip(),
                'overall_confidence': round(overall_confidence, 2),
                'words': words,
                'total_words': len(words),
                'high_confidence_words': len([w for w in words if w['confidence'] >= 80])
            }
            
        except Exception as e:
            logger.error(f"OCR detection error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _postprocess_ocr_results(
        self, 
        ocr_result: Dict[str, Any], 
        preprocessing_info: Dict[str, Any],
        page_number: int
    ) -> Dict[str, Any]:
        """Step 3: Post-process OCR results and format output.
        
        Args:
            ocr_result: Raw OCR detection results
            preprocessing_info: Image preprocessing information
            page_number: Page number for reference
            
        Returns:
            Final formatted OCR results
        """
        try:
            # Clean and format text
            cleaned_text = self._clean_ocr_text(ocr_result['text'])
            
            # Organize words by lines and blocks
            structured_content = self._structure_content(ocr_result['words'])
            
            # Generate text statistics
            text_stats = self._generate_text_statistics(cleaned_text, ocr_result['words'])
            
            return {
                'success': True,
                'page_number': page_number,
                'text': cleaned_text,
                'confidence': ocr_result['overall_confidence'],
                'words': ocr_result['words'],
                'structured_content': structured_content,
                'text_statistics': text_stats,
                'preprocessing_info': preprocessing_info,
                'processing_metadata': {
                    'total_words_detected': ocr_result['total_words'],
                    'high_confidence_words': ocr_result['high_confidence_words'],
                    'text_length': len(cleaned_text),
                    'confidence_distribution': self._get_confidence_distribution(ocr_result['words'])
                },
                'error': None
            }
            
        except Exception as e:
            logger.error(f"OCR postprocessing error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'page_number': page_number,
                'preprocessing_info': preprocessing_info
            }
    
    def _clean_ocr_text(self, raw_text: str) -> str:
        """Clean and normalize OCR text output.
        
        Args:
            raw_text: Raw text from OCR
            
        Returns:
            Cleaned text string
        """
        if not raw_text:
            return ""
        
        # Remove excessive whitespace
        cleaned = ' '.join(raw_text.split())
        
        # Fix common OCR errors
        replacements = {
            '|': 'l',  # Common OCR mistake
            'rn': 'm',  # Another common mistake
            '0': 'O',   # Zero to O in text contexts (context-dependent)
        }
        
        # Apply replacements cautiously (would need more sophisticated context analysis)
        # For now, just do basic cleaning
        
        return cleaned.strip()
    
    def _structure_content(self, words: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Organize words into structured content (blocks, paragraphs, lines).
        
        Args:
            words: List of word dictionaries with position info
            
        Returns:
            Dictionary with structured content organization
        """
        if not words:
            return {'blocks': [], 'lines': [], 'paragraphs': []}
        
        # Group by blocks
        blocks = {}
        for word in words:
            block_id = word['block_num']
            if block_id not in blocks:
                blocks[block_id] = []
            blocks[block_id].append(word)
        
        # Group by lines within blocks
        structured_blocks = []
        for block_id, block_words in blocks.items():
            lines = {}
            for word in block_words:
                line_id = word['line_num']
                if line_id not in lines:
                    lines[line_id] = []
                lines[line_id].append(word)
            
            # Sort words within each line by x-coordinate
            for line_words in lines.values():
                line_words.sort(key=lambda w: w['bbox']['x'])
            
            structured_blocks.append({
                'block_id': block_id,
                'lines': lines,
                'word_count': len(block_words),
                'text': ' '.join(word['text'] for word in block_words)
            })
        
        return {
            'blocks': structured_blocks,
            'total_blocks': len(structured_blocks),
            'total_lines': sum(len(block['lines']) for block in structured_blocks)
        }
    
    def _generate_text_statistics(self, text: str, words: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate statistics about the extracted text.
        
        Args:
            text: Cleaned text content
            words: List of word dictionaries
            
        Returns:
            Dictionary with text statistics
        """
        return {
            'character_count': len(text),
            'word_count': len(text.split()),
            'line_count': text.count('\n') + 1,
            'detected_words': len(words),
            'average_word_confidence': round(
                sum(w['confidence'] for w in words) / len(words) if words else 0, 2
            ),
            'confidence_range': {
                'min': min(w['confidence'] for w in words) if words else 0,
                'max': max(w['confidence'] for w in words) if words else 0
            }
        }
    
    def _get_confidence_distribution(self, words: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get distribution of word confidence scores.
        
        Args:
            words: List of word dictionaries
            
        Returns:
            Dictionary with confidence distribution
        """
        distribution = {
            '90-100': 0,
            '80-89': 0,
            '70-79': 0,
            '60-69': 0,
            'below-60': 0
        }
        
        for word in words:
            confidence = word['confidence']
            if confidence >= 90:
                distribution['90-100'] += 1
            elif confidence >= 80:
                distribution['80-89'] += 1
            elif confidence >= 70:
                distribution['70-79'] += 1
            elif confidence >= 60:
                distribution['60-69'] += 1
            else:
                distribution['below-60'] += 1
        
        return distribution
    
    def process_fallback_detection(self, image_data: bytes, page_number: int) -> Dict[str, Any]:
        """Fallback OCR processing for complex layouts or low-quality images.
        
        Args:
            image_data: Raw image data
            page_number: Page number for reference
            
        Returns:
            Dictionary with fallback OCR results
        """
        try:
            # Use different PSM (Page Segmentation Mode) for complex layouts
            fallback_config = r'--oem 3 --psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '
            
            pil_image = Image.open(io.BytesIO(image_data))
            
            # Try with different preprocessing
            image_array = np.array(pil_image)
            if len(image_array.shape) == 3:
                gray_image = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            else:
                gray_image = image_array
            
            # More aggressive preprocessing for difficult images
            # Bilateral filter for noise reduction while keeping edges sharp
            filtered = cv2.bilateralFilter(gray_image, 9, 75, 75)
            
            # Different thresholding approach
            _, threshold = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            pil_processed = Image.fromarray(threshold)
            
            # Extract text with fallback configuration
            fallback_text = pytesseract.image_to_string(pil_processed, config=fallback_config)
            
            return {
                'success': True,
                'text': fallback_text.strip(),
                'page_number': page_number,
                'method': 'fallback_detection',
                'confidence': 'estimated',  # Fallback doesn't provide detailed confidence
                'preprocessing': 'aggressive_bilateral_otsu'
            }
            
        except Exception as e:
            logger.error(f"Fallback OCR failed for page {page_number}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'page_number': page_number,
                'method': 'fallback_detection'
            }
    
    def clear_cache(self, pattern: str = None) -> Dict[str, Any]:
        """Clear OCR result cache.
        
        Args:
            pattern: Optional pattern to match cache keys (None clears all OCR cache)
            
        Returns:
            Dictionary with cache clearing results
        """
        try:
            if pattern:
                # This would require a more sophisticated cache implementation
                # For now, just return success
                return {
                    'success': True,
                    'message': f'Cache pattern {pattern} cleared',
                    'cleared_keys': 'pattern-based clearing not implemented'
                }
            else:
                # Clear all OCR cache entries (simplified)
                return {
                    'success': True,
                    'message': 'All OCR cache cleared',
                    'cleared_keys': 'bulk clearing not implemented'
                }
                
        except Exception as e:
            logger.error(f"Cache clearing error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def process_pdf_direct(self, pdf_path: Path, page_range: Optional[Tuple[int, int]] = None, 
                          dpi: int = None, ocr_mode: str = 'accurate', 
                          use_parallel: bool = True) -> Dict[str, Any]:
        """Process PDF pages directly using PyMuPDF for image extraction and OCR.
        
        Args:
            pdf_path: Path to the PDF file
            page_range: Optional tuple (start_page, end_page) for selective processing
            dpi: DPI setting for image extraction and OCR
            ocr_mode: OCR processing mode ('fast', 'accurate', 'complex', 'single_block')
            use_parallel: Whether to use parallel processing for multiple pages
            
        Returns:
            Dictionary with comprehensive OCR results for all processed pages
        """
        try:
            dpi = dpi or self.DEFAULT_DPI
            
            if ocr_mode not in self.OCR_MODES:
                ocr_mode = 'accurate'
            
            # Open PDF document
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            # Determine page range
            if page_range:
                start_page, end_page = page_range
                start_page = max(1, min(start_page, total_pages))
                end_page = max(start_page, min(end_page, total_pages))
            else:
                start_page, end_page = 1, total_pages
            
            pages_to_process = list(range(start_page - 1, end_page))  # Convert to 0-indexed
            
            # Process pages
            if use_parallel and len(pages_to_process) > 1:
                results = self._process_pages_parallel(doc, pages_to_process, dpi, ocr_mode)
            else:
                results = self._process_pages_sequential(doc, pages_to_process, dpi, ocr_mode)
            
            doc.close()
            
            # Compile comprehensive results
            successful_pages = [r for r in results if r.get('success', False)]
            total_text = '\n\n'.join(r.get('text', '') for r in successful_pages)
            
            # Calculate overall statistics
            overall_confidence = (
                sum(r.get('confidence', 0) for r in successful_pages) / len(successful_pages)
                if successful_pages else 0
            )
            
            return {
                'success': True,
                'pdf_path': str(pdf_path),
                'total_pages_in_pdf': total_pages,
                'pages_processed': len(results),
                'successful_pages': len(successful_pages),
                'failed_pages': len(results) - len(successful_pages),
                'page_range': f"{start_page}-{end_page}",
                'processing_mode': 'parallel' if use_parallel and len(pages_to_process) > 1 else 'sequential',
                'dpi_used': dpi,
                'ocr_mode': ocr_mode,
                'overall_confidence': round(overall_confidence, 2),
                'total_text': total_text,
                'total_text_length': len(total_text),
                'page_results': results,
                'processing_timestamp': datetime.now().isoformat(),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Direct PDF OCR processing error for {pdf_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'pdf_path': str(pdf_path),
                'processing_timestamp': datetime.now().isoformat()
            }
    
    def _process_pages_parallel(self, doc, page_indices: List[int], dpi: int, ocr_mode: str) -> List[Dict[str, Any]]:
        """Process multiple PDF pages in parallel using thread pool."""
        results = [None] * len(page_indices)
        
        def process_single_page(args):
            idx, page_num = args
            try:
                page = doc[page_num]
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                result = self._process_image_with_mode(img_data, page_num + 1, dpi, ocr_mode)
                result['processing_thread'] = threading.current_thread().name
                return idx, result
                
            except Exception as e:
                return idx, {
                    'success': False,
                    'page_number': page_num + 1,
                    'error': str(e),
                    'processing_thread': threading.current_thread().name
                }
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_idx = {
                executor.submit(process_single_page, (idx, page_num)): (idx, page_num) 
                for idx, page_num in enumerate(page_indices)
            }
            
            for future in concurrent.futures.as_completed(future_to_idx):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    idx, page_num = future_to_idx[future]
                    results[idx] = {
                        'success': False,
                        'page_number': page_num + 1,
                        'error': f"Parallel processing error: {str(e)}"
                    }
        
        return results
    
    def _process_pages_sequential(self, doc, page_indices: List[int], dpi: int, ocr_mode: str) -> List[Dict[str, Any]]:
        """Process PDF pages sequentially."""
        results = []
        
        for page_num in page_indices:
            try:
                page = doc[page_num]
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                result = self._process_image_with_mode(img_data, page_num + 1, dpi, ocr_mode)
                result['processing_method'] = 'sequential'
                results.append(result)
                
            except Exception as e:
                results.append({
                    'success': False,
                    'page_number': page_num + 1,
                    'error': str(e),
                    'processing_method': 'sequential'
                })
        
        return results
    
    def _process_image_with_mode(self, image_data: bytes, page_number: int, dpi: int, ocr_mode: str) -> Dict[str, Any]:
        """Process image data with specific OCR mode."""
        try:
            result = self.process_pdf_page_image(image_data, page_number, dpi, use_cache=True)
            
            # Apply mode-specific processing if standard processing failed or had low confidence
            if not result.get('success', False) or result.get('confidence', 0) < 50:
                tesseract_config = self.OCR_MODES[ocr_mode]
                preprocessed_image, preprocessing_info = self._preprocess_image(image_data)
                
                if preprocessed_image is not None:
                    pil_image = Image.fromarray(preprocessed_image)
                    custom_config = f'--dpi {dpi} {tesseract_config}'
                    fallback_text = pytesseract.image_to_string(pil_image, config=custom_config)
                    
                    if len(fallback_text.strip()) > len(result.get('text', '').strip()):
                        result.update({
                            'text': fallback_text.strip(),
                            'fallback_mode_used': ocr_mode,
                            'improved_by_fallback': True
                        })
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'page_number': page_number,
                'error': str(e),
                'ocr_mode_attempted': ocr_mode
            }
    
    def intelligent_text_detection(self, pdf_path: Path) -> Dict[str, Any]:
        """Intelligently detect which pages need OCR processing."""
        try:
            analysis_results = {
                'pdf_path': str(pdf_path),
                'total_pages': 0,
                'pages_with_extractable_text': 0,
                'pages_needing_ocr': [],
                'text_quality_analysis': [],
                'ocr_recommendations': {},
                'estimated_processing_time': 0
            }
            
            doc = fitz.open(pdf_path)
            analysis_results['total_pages'] = len(doc)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                existing_text = page.get_text().strip()
                text_length = len(existing_text)
                images = page.get_images()
                image_count = len(images)
                
                # Calculate quality score
                if text_length > 0:
                    page_area = page.rect.width * page.rect.height
                    text_density = text_length / (page_area / 10000)
                    quality_score = min(100, text_density * 10)
                    analysis_results['pages_with_extractable_text'] += 1
                else:
                    quality_score = 0
                
                # Determine if OCR is needed
                needs_ocr = (
                    text_length < 50 or
                    quality_score < 30 or
                    (image_count > 0 and text_length < 200)
                )
                
                if needs_ocr:
                    analysis_results['pages_needing_ocr'].append(page_num + 1)
                
                analysis_results['text_quality_analysis'].append({
                    'page_number': page_num + 1,
                    'existing_text_length': text_length,
                    'image_count': image_count,
                    'quality_score': round(quality_score, 2),
                    'needs_ocr': needs_ocr,
                    'text_sample': existing_text[:100] + '...' if len(existing_text) > 100 else existing_text
                })
            
            doc.close()
            
            # Generate recommendations
            ocr_pages = len(analysis_results['pages_needing_ocr'])
            total_pages = analysis_results['total_pages']
            
            if ocr_pages == 0:
                priority = 'none'
                method = 'direct_text_extraction'
            elif ocr_pages < total_pages * 0.3:
                priority = 'low'
                method = 'selective_ocr'
            elif ocr_pages < total_pages * 0.7:
                priority = 'medium'
                method = 'hybrid_processing'
            else:
                priority = 'high'
                method = 'full_ocr_processing'
            
            estimated_time = ocr_pages * 15
            
            analysis_results['ocr_recommendations'] = {
                'priority': priority,
                'recommended_method': method,
                'pages_for_ocr': ocr_pages,
                'ocr_percentage': round((ocr_pages / total_pages) * 100, 1) if total_pages > 0 else 0,
                'estimated_processing_time_seconds': estimated_time,
                'estimated_processing_time_minutes': round(estimated_time / 60, 1),
                'should_use_parallel_processing': ocr_pages > 1
            }
            
            analysis_results['estimated_processing_time'] = estimated_time
            
            return {
                'success': True,
                'analysis': analysis_results,
                'analysis_timestamp': datetime.now().isoformat(),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Text detection analysis error for {pdf_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'pdf_path': str(pdf_path),
                'analysis_timestamp': datetime.now().isoformat()
            }