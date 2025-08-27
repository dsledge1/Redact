"""PDF processing service for Ultimate PDF application."""

import io
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
import hashlib
from datetime import datetime

import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
from .temp_file_manager import TempFileManager

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Service class for PDF processing operations including validation, splitting, merging, and text extraction."""
    
    def __init__(self, session_id: str):
        """Initialize PDF processor for a specific session.
        
        Args:
            session_id: Unique session identifier for file management
        """
        self.session_id = session_id
        self.temp_manager = TempFileManager()
    
    def validate_pdf(self, file_path: Path) -> Dict[str, Any]:
        """Validate PDF file and extract basic metadata.
        
        Args:
            file_path: Path to the PDF file to validate
            
        Returns:
            Dictionary containing validation results and metadata:
            - is_valid: Boolean indicating if PDF is valid
            - page_count: Number of pages in the PDF
            - has_text_layer: Boolean indicating if PDF contains text
            - is_encrypted: Boolean indicating if PDF is password protected
            - metadata: Dictionary of PDF metadata
            - file_size: File size in bytes
            - error: Error message if validation failed
            
        Raises:
            FileNotFoundError: If the PDF file doesn't exist
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"PDF file not found: {file_path}")
            
            file_size = file_path.stat().st_size
            
            with open(file_path, 'rb') as file:
                try:
                    reader = PdfReader(file)
                    
                    # Check if PDF is encrypted
                    is_encrypted = reader.is_encrypted
                    if is_encrypted:
                        return {
                            'is_valid': False,
                            'error': 'PDF is password protected',
                            'file_size': file_size,
                            'is_encrypted': True
                        }
                    
                    page_count = len(reader.pages)
                    
                    # Check for text layer by trying to extract text from first few pages
                    has_text_layer = False
                    pages_to_check = min(3, page_count)
                    
                    for i in range(pages_to_check):
                        try:
                            text = reader.pages[i].extract_text()
                            if text is None:
                                text = ""
                            text = text.strip()
                            if text:
                                has_text_layer = True
                                break
                        except Exception:
                            continue
                    
                    # Extract metadata
                    metadata = {}
                    if reader.metadata:
                        metadata = {
                            'title': reader.metadata.get('/Title', ''),
                            'author': reader.metadata.get('/Author', ''),
                            'subject': reader.metadata.get('/Subject', ''),
                            'creator': reader.metadata.get('/Creator', ''),
                            'producer': reader.metadata.get('/Producer', ''),
                            'creation_date': str(reader.metadata.get('/CreationDate', '')),
                            'modification_date': str(reader.metadata.get('/ModDate', ''))
                        }
                    
                    return {
                        'is_valid': True,
                        'page_count': page_count,
                        'has_text_layer': has_text_layer,
                        'is_encrypted': False,
                        'metadata': metadata,
                        'file_size': file_size,
                        'error': None
                    }
                    
                except PyPDF2.errors.PdfReadError as e:
                    return {
                        'is_valid': False,
                        'error': f'Invalid PDF format: {str(e)}',
                        'file_size': file_size,
                        'is_encrypted': False
                    }
                    
        except Exception as e:
            logger.error(f"PDF validation error for {file_path}: {str(e)}")
            return {
                'is_valid': False,
                'error': f'Validation failed: {str(e)}',
                'file_size': 0,
                'is_encrypted': False
            }
    
    def extract_text(self, file_path: Path) -> Dict[str, Any]:
        """Extract text content from all pages of a PDF.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if extraction succeeded
            - pages: List of dictionaries with page_number and text
            - total_pages: Total number of pages processed
            - has_text: Boolean indicating if any text was found
            - error: Error message if extraction failed
        """
        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)
                
                if reader.is_encrypted:
                    return {
                        'success': False,
                        'error': 'Cannot extract text from encrypted PDF',
                        'pages': [],
                        'total_pages': 0,
                        'has_text': False
                    }
                
                pages = []
                total_text_length = 0
                
                for page_num, page in enumerate(reader.pages, 1):
                    try:
                        text = page.extract_text()
                        if text is None:
                            text = ""
                        pages.append({
                            'page_number': page_num,
                            'text': text,
                            'char_count': len(text)
                        })
                        total_text_length += len(text.strip())
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num}: {str(e)}")
                        pages.append({
                            'page_number': page_num,
                            'text': '',
                            'char_count': 0,
                            'error': str(e)
                        })
                
                return {
                    'success': True,
                    'pages': pages,
                    'total_pages': len(pages),
                    'has_text': total_text_length > 0,
                    'error': None
                }
                
        except Exception as e:
            logger.error(f"Text extraction error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'pages': [],
                'total_pages': 0,
                'has_text': False
            }
    
    def split_pdf(self, file_path: Path, split_pages: List[int]) -> Dict[str, Any]:
        """Split PDF into multiple files based on page ranges.
        
        Args:
            file_path: Path to the source PDF file
            split_pages: List of page numbers where to split (1-indexed)
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if split succeeded
            - output_files: List of created file paths
            - page_ranges: List of page ranges for each output file
            - error: Error message if split failed
        """
        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)
                total_pages = len(reader.pages)
                
                if reader.is_encrypted:
                    return {
                        'success': False,
                        'error': 'Cannot split encrypted PDF',
                        'output_files': [],
                        'page_ranges': []
                    }
                
                # Validate split points
                valid_splits = [p for p in split_pages if 1 <= p <= total_pages]
                valid_splits = sorted(list(set(valid_splits)))
                
                # Create page ranges
                ranges = []
                start = 1
                
                for split_point in valid_splits:
                    if split_point > start:
                        ranges.append((start, split_point - 1))
                        start = split_point
                
                # Add final range if needed
                if start <= total_pages:
                    ranges.append((start, total_pages))
                
                if not ranges:
                    ranges = [(1, total_pages)]
                
                # Create split files
                output_dir = self.temp_manager.get_session_path(self.session_id, 'downloads')
                output_files = []
                
                for i, (start_page, end_page) in enumerate(ranges, 1):
                    writer = PdfWriter()
                    
                    # Add pages to writer (convert to 0-indexed)
                    for page_num in range(start_page - 1, end_page):
                        writer.add_page(reader.pages[page_num])
                    
                    # Create output filename
                    base_name = file_path.stem
                    output_filename = f"{base_name}_part_{i}_pages_{start_page}-{end_page}.pdf"
                    output_path = output_dir / output_filename
                    
                    # Write the split PDF
                    with open(output_path, 'wb') as output_file:
                        writer.write(output_file)
                    
                    output_files.append(str(output_path))
                
                return {
                    'success': True,
                    'output_files': output_files,
                    'page_ranges': [f"{start}-{end}" for start, end in ranges],
                    'error': None
                }
                
        except Exception as e:
            logger.error(f"PDF split error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'output_files': [],
                'page_ranges': []
            }
    
    def merge_pdfs(self, file_paths: List[Path], output_filename: str = None) -> Dict[str, Any]:
        """Merge multiple PDF files into a single document.
        
        Args:
            file_paths: List of PDF file paths to merge
            output_filename: Custom name for merged file (optional)
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if merge succeeded
            - output_file: Path to the merged PDF file
            - total_pages: Total pages in merged document
            - source_info: Information about source files
            - error: Error message if merge failed
        """
        try:
            if len(file_paths) < 2:
                return {
                    'success': False,
                    'error': 'At least 2 PDF files required for merging',
                    'output_file': None,
                    'total_pages': 0,
                    'source_info': []
                }
            
            writer = PdfWriter()
            source_info = []
            total_pages = 0
            
            # Process each source file
            for file_path in file_paths:
                if not file_path.exists():
                    logger.warning(f"Skipping non-existent file: {file_path}")
                    continue
                
                try:
                    with open(file_path, 'rb') as file:
                        reader = PdfReader(file)
                        
                        if reader.is_encrypted:
                            logger.warning(f"Skipping encrypted file: {file_path}")
                            source_info.append({
                                'filename': file_path.name,
                                'pages': 0,
                                'status': 'skipped - encrypted'
                            })
                            continue
                        
                        page_count = len(reader.pages)
                        
                        # Add all pages to writer
                        for page in reader.pages:
                            writer.add_page(page)
                        
                        total_pages += page_count
                        source_info.append({
                            'filename': file_path.name,
                            'pages': page_count,
                            'status': 'merged'
                        })
                        
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
                    source_info.append({
                        'filename': file_path.name,
                        'pages': 0,
                        'status': f'error - {str(e)}'
                    })
            
            if total_pages == 0:
                return {
                    'success': False,
                    'error': 'No pages could be merged from source files',
                    'output_file': None,
                    'total_pages': 0,
                    'source_info': source_info
                }
            
            # Create output file
            output_dir = self.temp_manager.get_session_path(self.session_id, 'downloads')
            
            if not output_filename:
                output_filename = f"merged_document_{self.session_id[:8]}.pdf"
            
            if not output_filename.endswith('.pdf'):
                output_filename += '.pdf'
            
            output_path = output_dir / output_filename
            
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            return {
                'success': True,
                'output_file': str(output_path),
                'total_pages': total_pages,
                'source_info': source_info,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"PDF merge error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'output_file': None,
                'total_pages': 0,
                'source_info': []
            }
    
    def extract_pages_as_images(self, file_path: Path, dpi: int = 300, page_range: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """Extract PDF pages as high-quality images for OCR processing.
        
        Args:
            file_path: Path to the PDF file
            dpi: DPI setting for image extraction (default 300)
            page_range: Optional tuple (start_page, end_page) for selective extraction
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if extraction succeeded
            - images: List of dictionaries with page_number and image_data
            - total_pages: Total number of pages processed
            - dpi_used: Actual DPI used for extraction
            - error: Error message if extraction failed
        """
        try:
            doc = fitz.open(file_path)
            total_doc_pages = len(doc)
            
            # Determine page range
            if page_range:
                start_page, end_page = page_range
                start_page = max(1, start_page)
                end_page = min(total_doc_pages, end_page)
            else:
                start_page, end_page = 1, total_doc_pages
            
            images = []
            
            for page_num in range(start_page - 1, end_page):  # Convert to 0-indexed
                try:
                    page = doc[page_num]
                    
                    # Create transformation matrix for DPI scaling
                    mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 DPI is default
                    
                    # Render page to pixmap
                    pix = page.get_pixmap(matrix=mat)
                    
                    # Convert to bytes
                    img_data = pix.tobytes("png")
                    
                    images.append({
                        'page_number': page_num + 1,  # Convert back to 1-indexed
                        'image_data': img_data,
                        'image_size': len(img_data),
                        'dimensions': {
                            'width': pix.width,
                            'height': pix.height
                        },
                        'format': 'PNG'
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to extract page {page_num + 1}: {str(e)}")
                    images.append({
                        'page_number': page_num + 1,
                        'error': str(e),
                        'image_data': None
                    })
            
            doc.close()
            
            return {
                'success': True,
                'images': images,
                'total_pages': len(images),
                'pages_processed': len([img for img in images if 'error' not in img]),
                'dpi_used': dpi,
                'page_range': f"{start_page}-{end_page}",
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Page extraction error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'images': [],
                'total_pages': 0,
                'dpi_used': dpi
            }
    
    def extract_advanced_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract comprehensive metadata from PDF including advanced properties.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with extensive PDF metadata
        """
        try:
            metadata = {}
            
            # Extract metadata using PyMuPDF for more comprehensive data
            with fitz.open(file_path) as doc:
                # Basic document info
                metadata['document_info'] = {
                    'page_count': len(doc),
                    'is_encrypted': doc.needs_pass,
                    'pdf_version': doc.pdf_version,
                    'file_size': file_path.stat().st_size,
                    'creation_date': datetime.fromtimestamp(file_path.stat().st_ctime).isoformat(),
                    'modification_date': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                }
                
                # PDF metadata
                pdf_metadata = doc.metadata
                metadata['pdf_metadata'] = {
                    'title': pdf_metadata.get('title', ''),
                    'author': pdf_metadata.get('author', ''),
                    'subject': pdf_metadata.get('subject', ''),
                    'creator': pdf_metadata.get('creator', ''),
                    'producer': pdf_metadata.get('producer', ''),
                    'creation_date': pdf_metadata.get('creationDate', ''),
                    'modification_date': pdf_metadata.get('modDate', ''),
                    'keywords': pdf_metadata.get('keywords', '')
                }
                
                # Page analysis
                page_info = []
                total_text_length = 0
                has_images = False
                has_forms = False
                
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    
                    # Text analysis
                    text = page.get_text()
                    text_length = len(text.strip())
                    total_text_length += text_length
                    
                    # Image analysis
                    image_list = page.get_images()
                    page_has_images = len(image_list) > 0
                    if page_has_images:
                        has_images = True
                    
                    # Form field analysis
                    widgets = page.widgets()
                    page_has_forms = len(widgets) > 0
                    if page_has_forms:
                        has_forms = True
                    
                    # Links and annotations
                    links = page.get_links()
                    annotations = page.annots()
                    
                    page_info.append({
                        'page_number': page_num + 1,
                        'text_length': text_length,
                        'has_text': text_length > 0,
                        'image_count': len(image_list),
                        'has_images': page_has_images,
                        'form_field_count': len(widgets),
                        'has_forms': page_has_forms,
                        'link_count': len(links),
                        'annotation_count': len(list(annotations)),
                        'media_box': page.rect,
                        'rotation': page.rotation
                    })
                
                metadata['content_analysis'] = {
                    'total_text_length': total_text_length,
                    'has_text_content': total_text_length > 0,
                    'has_images': has_images,
                    'has_form_fields': has_forms,
                    'text_to_image_ratio': total_text_length / max(1, sum(p['image_count'] for p in page_info)),
                    'average_text_per_page': total_text_length / len(doc) if len(doc) > 0 else 0
                }
                
                metadata['page_details'] = page_info
                
                # Security analysis
                metadata['security_info'] = {
                    'is_encrypted': doc.needs_pass,
                    'permissions': doc.permissions if not doc.needs_pass else None,
                    'has_digital_signatures': self._check_digital_signatures(doc)
                }
            
            # File integrity
            metadata['file_integrity'] = {
                'sha256_hash': self._calculate_file_hash(file_path),
                'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2)
            }
            
            return {
                'success': True,
                'metadata': metadata,
                'extraction_timestamp': datetime.now().isoformat(),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Advanced metadata extraction error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'metadata': {},
                'extraction_timestamp': datetime.now().isoformat()
            }
    
    def _check_digital_signatures(self, doc) -> bool:
        """Check if PDF has digital signatures."""
        try:
            # Simple check for signature fields
            for page_num in range(len(doc)):
                page = doc[page_num]
                for widget in page.widgets():
                    if widget.field_type == 4:  # PDF_WIDGET_TYPE_SIGNATURE
                        return True
            return False
        except Exception:
            return False
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of the file."""
        try:
            return TempFileManager.calculate_file_hash(file_path)
        except Exception as e:
            logger.warning(f"Hash calculation failed: {str(e)}")
            return ""
    
    def detect_text_layer_quality(self, file_path: Path) -> Dict[str, Any]:
        """Analyze the quality and completeness of text layers in PDF.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with text layer analysis
        """
        try:
            with fitz.open(file_path) as doc:
                analysis = {
                    'total_pages': len(doc),
                    'pages_with_text': 0,
                    'pages_with_images': 0,
                    'text_quality_scores': [],
                    'recommended_ocr_pages': [],
                    'overall_text_coverage': 0
                }
                
                total_text_chars = 0
                total_possible_content = 0
                
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    
                    # Extract text
                    text = page.get_text()
                    text_length = len(text.strip())
                    
                    # Count images
                    images = page.get_images()
                    image_count = len(images)
                    
                    # Estimate content complexity
                    page_area = (page.rect.width * page.rect.height) / 10000  # Normalize
                    estimated_content = page_area + (image_count * 100)  # Rough heuristic
                    
                    # Calculate text quality score
                    if estimated_content > 0:
                        text_density = text_length / estimated_content
                        quality_score = min(100, text_density * 50)  # Scale to 0-100
                    else:
                        quality_score = 100 if text_length > 0 else 0
                    
                    # Track statistics
                    if text_length > 0:
                        analysis['pages_with_text'] += 1
                    
                    if image_count > 0:
                        analysis['pages_with_images'] += 1
                    
                    # Recommend OCR for low-quality text or image-heavy pages
                    if quality_score < 30 or (image_count > 0 and text_length < 50):
                        analysis['recommended_ocr_pages'].append(page_num + 1)
                    
                    analysis['text_quality_scores'].append({
                        'page_number': page_num + 1,
                        'text_length': text_length,
                        'image_count': image_count,
                        'quality_score': round(quality_score, 2),
                        'needs_ocr': quality_score < 30
                    })
                    
                    total_text_chars += text_length
                    total_possible_content += estimated_content
                
                # Overall coverage calculation
                if total_possible_content > 0:
                    analysis['overall_text_coverage'] = round(
                        (total_text_chars / total_possible_content) * 100, 2
                    )
                else:
                    analysis['overall_text_coverage'] = 100 if total_text_chars > 0 else 0
                
                # Recommendations
                analysis['recommendations'] = {
                    'needs_ocr': len(analysis['recommended_ocr_pages']) > 0,
                    'ocr_priority': 'high' if len(analysis['recommended_ocr_pages']) > len(doc) * 0.5 else 'medium' if analysis['recommended_ocr_pages'] else 'low',
                    'text_extraction_method': 'ocr' if analysis['overall_text_coverage'] < 50 else 'mixed' if analysis['recommended_ocr_pages'] else 'direct'
                }
                
                return {
                    'success': True,
                    'analysis': analysis,
                    'error': None
                }
                
        except Exception as e:
            logger.error(f"Text layer analysis error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'analysis': {}
            }
    
    def optimize_pdf(self, file_path: Path, optimization_level: str = 'standard') -> Dict[str, Any]:
        """Optimize PDF for size and performance.
        
        Args:
            file_path: Path to the PDF file
            optimization_level: 'light', 'standard', or 'aggressive'
            
        Returns:
            Dictionary with optimization results
        """
        try:
            output_dir = self.temp_manager.get_session_path(self.session_id, 'processing')
            output_filename = f"optimized_{file_path.stem}.pdf"
            output_path = output_dir / output_filename
            
            # Read original file
            with fitz.open(file_path) as doc:
                original_size = file_path.stat().st_size
                
                # Optimization settings based on level
                if optimization_level == 'light':
                    # Light optimization - just remove unused objects
                    doc.ez_save(output_path, garbage=4, deflate=True)
                
                elif optimization_level == 'standard':
                    # Standard optimization - compress images and remove unused objects
                    doc.save(output_path, garbage=4, deflate=True, clean=True, pretty=True)
                
                elif optimization_level == 'aggressive':
                    # Aggressive optimization - compress images more, subset fonts
                    doc.save(output_path, garbage=4, deflate=True, clean=True, 
                           ascii=True, expand=1, linear=True)
                else:
                    raise ValueError(f"Invalid optimization level: {optimization_level}")
            
            # Calculate optimization results
            optimized_size = output_path.stat().st_size
            size_reduction = original_size - optimized_size
            reduction_percent = (size_reduction / original_size) * 100 if original_size > 0 else 0
            
            return {
                'success': True,
                'output_file': str(output_path),
                'optimization_level': optimization_level,
                'original_size': original_size,
                'optimized_size': optimized_size,
                'size_reduction_bytes': size_reduction,
                'size_reduction_percent': round(reduction_percent, 2),
                'original_size_mb': round(original_size / (1024 * 1024), 2),
                'optimized_size_mb': round(optimized_size / (1024 * 1024), 2),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"PDF optimization error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'optimization_level': optimization_level
            }
    
    def extract_embedded_files(self, file_path: Path) -> Dict[str, Any]:
        """Extract embedded files and images from PDF.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with extracted files information
        """
        try:
            extracted_files = []
            extracted_images = []
            
            with fitz.open(file_path) as doc:
                # Extract embedded files
                embedded_files = doc.embfile_names()
                output_dir = self.temp_manager.get_session_path(self.session_id, 'processing')
                
                for file_name in embedded_files:
                    try:
                        file_data = doc.embfile_get(file_name)
                        output_path = output_dir / f"embedded_{file_name}"
                        
                        with open(output_path, 'wb') as f:
                            f.write(file_data)
                        
                        extracted_files.append({
                            'filename': file_name,
                            'output_path': str(output_path),
                            'size': len(file_data),
                            'extracted': True
                        })
                    except Exception as e:
                        extracted_files.append({
                            'filename': file_name,
                            'error': str(e),
                            'extracted': False
                        })
                
                # Extract images
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    image_list = page.get_images()
                    
                    for img_index, img in enumerate(image_list):
                        try:
                            xref = img[0]
                            pix = fitz.Pixmap(doc, xref)
                            
                            if pix.n - pix.alpha < 4:  # Only RGB/Gray images
                                img_filename = f"page_{page_num + 1}_img_{img_index + 1}.png"
                                img_path = output_dir / img_filename
                                
                                pix.save(str(img_path))
                                
                                extracted_images.append({
                                    'page_number': page_num + 1,
                                    'image_index': img_index + 1,
                                    'filename': img_filename,
                                    'output_path': str(img_path),
                                    'width': pix.width,
                                    'height': pix.height,
                                    'colorspace': pix.colorspace.name if pix.colorspace else 'unknown',
                                    'extracted': True
                                })
                            
                            pix = None  # Release memory
                            
                        except Exception as e:
                            extracted_images.append({
                                'page_number': page_num + 1,
                                'image_index': img_index + 1,
                                'error': str(e),
                                'extracted': False
                            })
            
            return {
                'success': True,
                'extracted_files': extracted_files,
                'extracted_images': extracted_images,
                'total_files': len(extracted_files),
                'total_images': len(extracted_images),
                'successful_files': len([f for f in extracted_files if f.get('extracted', False)]),
                'successful_images': len([i for i in extracted_images if i.get('extracted', False)]),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"File extraction error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'extracted_files': [],
                'extracted_images': []
            }
    
    def batch_process_pdfs(self, file_paths: List[Path], operation: str, **kwargs) -> Dict[str, Any]:
        """Process multiple PDF files in batch with the same operation.
        
        Args:
            file_paths: List of PDF file paths
            operation: Operation to perform ('validate', 'optimize', 'extract_metadata')
            **kwargs: Additional arguments for the operation
            
        Returns:
            Dictionary with batch processing results
        """
        try:
            results = []
            successful_operations = 0
            
            for i, file_path in enumerate(file_paths):
                try:
                    if operation == 'validate':
                        result = self.validate_pdf(file_path)
                    elif operation == 'optimize':
                        result = self.optimize_pdf(file_path, kwargs.get('optimization_level', 'standard'))
                    elif operation == 'extract_metadata':
                        result = self.extract_advanced_metadata(file_path)
                    else:
                        result = {'success': False, 'error': f'Unknown operation: {operation}'}
                    
                    result['file_path'] = str(file_path)
                    result['batch_index'] = i
                    results.append(result)
                    
                    if result.get('success', False):
                        successful_operations += 1
                        
                except Exception as e:
                    results.append({
                        'success': False,
                        'error': str(e),
                        'file_path': str(file_path),
                        'batch_index': i
                    })
            
            return {
                'success': True,
                'operation': operation,
                'total_files': len(file_paths),
                'successful_operations': successful_operations,
                'failed_operations': len(file_paths) - successful_operations,
                'success_rate': round((successful_operations / len(file_paths)) * 100, 2) if file_paths else 0,
                'results': results,
                'batch_completed_at': datetime.now().isoformat(),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Batch processing error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'operation': operation,
                'total_files': len(file_paths),
                'results': []
            }