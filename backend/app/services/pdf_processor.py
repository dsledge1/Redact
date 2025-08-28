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
from .pdf_splitter import PDFSplitter
from .pdf_merger import PDFMerger
from ..utils.validators import validate_split_pattern
from .table_extraction_service import TableExtractionService
from .image_extraction_service import ImageExtractionService
from .metadata_extraction_service import MetadataExtractionService

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
    
    def validate_split_pattern(self, file_path: Path, pattern: str, pattern_type: str) -> Dict[str, Any]:
        """Validate pattern before processing for pattern-based splitting.
        
        Args:
            file_path: Path to PDF file
            pattern: Pattern to validate
            pattern_type: Type of pattern matching
            
        Returns:
            Dictionary with validation results
        """
        try:
            validation_result = validate_split_pattern(pattern, pattern_type)
            if not validation_result['valid']:
                return {
                    'valid': False,
                    'error': validation_result['error'],
                    'pattern': pattern,
                    'pattern_type': pattern_type
                }
            
            # Test pattern against PDF if it exists
            if file_path.exists():
                splitter = PDFSplitter(self.session_id)
                try:
                    # Quick test to see if pattern can be found
                    pattern_matches = splitter._detect_pattern_pages(
                        file_path, pattern, pattern_type, 80
                    )
                    
                    return {
                        'valid': True,
                        'pattern': pattern,
                        'pattern_type': pattern_type,
                        'test_matches': len(pattern_matches),
                        'preview_matches': pattern_matches[:3]  # First 3 matches
                    }
                except Exception as e:
                    return {
                        'valid': False,
                        'error': f"Pattern test failed: {str(e)}",
                        'pattern': pattern,
                        'pattern_type': pattern_type
                    }
            
            return {
                'valid': True,
                'pattern': pattern,
                'pattern_type': pattern_type,
                'note': 'Pattern syntax valid, but not tested against document'
            }
            
        except Exception as e:
            logger.error(f"Pattern validation error: {str(e)}")
            return {
                'valid': False,
                'error': str(e),
                'pattern': pattern,
                'pattern_type': pattern_type
            }
    
    def get_document_outline(self, file_path: Path) -> Dict[str, Any]:
        """Extract document structure information for merge planning.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Dictionary with document outline and structure info
        """
        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)
                
                outline_info = {
                    'has_outline': False,
                    'outline_items': [],
                    'total_pages': len(reader.pages),
                    'page_labels': [],
                    'bookmarks': []
                }
                
                # Extract outline/bookmarks if available
                if hasattr(reader, 'outline') and reader.outline:
                    outline_info['has_outline'] = True
                    
                    def extract_outline_items(outline_items, level=0):
                        items = []
                        for item in outline_items:
                            if isinstance(item, dict):
                                items.append({
                                    'title': item.get('/Title', 'Untitled'),
                                    'level': level,
                                    'page': None  # Would need more complex extraction
                                })
                            elif hasattr(item, '__iter__'):
                                items.extend(extract_outline_items(item, level + 1))
                        return items
                    
                    outline_info['outline_items'] = extract_outline_items(reader.outline)
                
                return {
                    'success': True,
                    'outline': outline_info,
                    'error': None
                }
                
        except Exception as e:
            logger.error(f"Document outline extraction error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'outline': {}
            }
    
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
                    
                    # Additional checks for splitting/merging compatibility
                    compatibility_info = {
                        'structural_integrity': True,
                        'splitting_compatible': not is_encrypted and page_count > 1,
                        'merging_compatible': not is_encrypted,
                        'has_forms': False,  # Would need deeper analysis
                        'has_annotations': False  # Would need deeper analysis
                    }
                    
                    return {
                        'is_valid': True,
                        'page_count': page_count,
                        'has_text_layer': has_text_layer,
                        'is_encrypted': False,
                        'metadata': metadata,
                        'file_size': file_size,
                        'compatibility': compatibility_info,
                        'file_hash': self._calculate_file_hash(file_path),
                        'error': None
                    }
                    
                except PyPDF2.errors.PdfReadError as e:
                    return {
                        'is_valid': False,
                        'error': f'Invalid PDF format: {str(e)}',
                        'file_size': file_size,
                        'is_encrypted': False,
                        'compatibility': {
                            'structural_integrity': False,
                            'splitting_compatible': False,
                            'merging_compatible': False
                        }
                    }
                    
        except Exception as e:
            logger.error(f"PDF validation error for {file_path}: {str(e)}")
            return {
                'is_valid': False,
                'error': f'Validation failed: {str(e)}',
                'file_size': 0,
                'is_encrypted': False,
                'compatibility': {
                    'structural_integrity': False,
                    'splitting_compatible': False,
                    'merging_compatible': False
                }
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
    
    def split_pdf(
        self,
        file_path: Path,
        split_pages: List[int] = None,
        pattern: str = None,
        pattern_type: str = 'regex',
        fuzzy_threshold: int = 80,
        split_position: str = 'before',
        preserve_metadata: bool = True
    ) -> Dict[str, Any]:
        """Split PDF into multiple files based on page ranges or patterns.
        
        Args:
            file_path: Path to the source PDF file
            split_pages: List of page numbers where to split (1-indexed)
            pattern: Text pattern to search for (for pattern-based splitting)
            pattern_type: Type of pattern matching ('regex', 'fuzzy', 'exact')
            fuzzy_threshold: Threshold for fuzzy matching (1-100)
            split_position: Position to split ('before' or 'after' pattern)
            preserve_metadata: Whether to preserve document metadata
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if split succeeded
            - output_files: List of created file paths
            - page_ranges: List of page ranges for each output file
            - split_type: Type of split performed ('pages' or 'pattern')
            - error: Error message if split failed
        """
        try:
            # Initialize splitter service
            splitter = PDFSplitter(self.session_id)
            
            # Determine split method and delegate to appropriate service
            if pattern is not None:
                # Pattern-based splitting
                if pattern_type == 'regex':
                    validation_result = validate_split_pattern(pattern, pattern_type)
                    if not validation_result['valid']:
                        return {
                            'success': False,
                            'error': f"Invalid pattern: {validation_result['error']}",
                            'split_type': 'pattern'
                        }
                
                result = splitter.split_by_pattern(
                    file_path, pattern, pattern_type, fuzzy_threshold, split_position
                )
                
                # Convert result format for backward compatibility
                if result['success']:
                    output_files = [output_file['path'] for output_file in result['output_files']]
                    page_ranges = [output_file['page_range'] for output_file in result['output_files']]
                    
                    return {
                        'success': True,
                        'split_type': 'pattern',
                        'pattern': pattern,
                        'pattern_matches_found': result.get('pattern_matches_found', 0),
                        'output_files': output_files,
                        'page_ranges': page_ranges,
                        'metadata_preserved': preserve_metadata,
                        'error': None
                    }
                else:
                    return {
                        'success': False,
                        'split_type': 'pattern',
                        'error': result.get('error', 'Pattern-based split failed'),
                        'output_files': [],
                        'page_ranges': []
                    }
                    
            elif split_pages is not None:
                # Page-based splitting
                result = splitter.split_by_pages(
                    file_path, split_pages, preserve_metadata
                )
                
                # Convert result format for backward compatibility
                if result['success']:
                    output_files = [output_file['path'] for output_file in result['output_files']]
                    page_ranges = [output_file['page_range'] for output_file in result['output_files']]
                    
                    return {
                        'success': True,
                        'split_type': 'pages',
                        'output_files': output_files,
                        'page_ranges': page_ranges,
                        'metadata_preserved': preserve_metadata,
                        'error': None
                    }
                else:
                    return {
                        'success': False,
                        'split_type': 'pages',
                        'error': result.get('error', 'Page-based split failed'),
                        'output_files': [],
                        'page_ranges': []
                    }
            else:
                # No split parameters provided
                return {
                    'success': False,
                    'error': 'Either split_pages or pattern must be provided',
                    'output_files': [],
                    'page_ranges': []
                }
                
        except Exception as e:
            logger.error(f"PDF split error for {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'output_files': [],
                'page_ranges': []
            }
    
    def merge_pdfs(
        self,
        file_paths: List[Path],
        output_filename: str = None,
        preserve_metadata: bool = True,
        merge_strategy: str = 'sequential'
    ) -> Dict[str, Any]:
        """Merge multiple PDF files into a single document.
        
        Args:
            file_paths: List of PDF file paths to merge
            output_filename: Custom name for merged file (optional)
            preserve_metadata: Whether to preserve and combine metadata
            merge_strategy: Strategy for merging ('sequential', 'aggregate')
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if merge succeeded
            - output_file: Path to the merged PDF file
            - total_pages: Total pages in merged document
            - source_info: Information about source files
            - merge_strategy: Strategy used for merging
            - metadata_preserved: Whether metadata was preserved
            - error: Error message if merge failed
        """
        try:
            # Initialize merger service
            merger = PDFMerger(self.session_id)
            
            # Delegate to merger service
            result = merger.merge_documents(
                file_paths, output_filename, preserve_metadata, merge_strategy
            )
            
            # Convert result format for backward compatibility
            if result['success']:
                # Convert source file info format
                source_info = []
                for i, file_path in enumerate(file_paths):
                    source_info.append({
                        'filename': file_path.name,
                        'pages': 0,  # Will be filled from analysis if available
                        'status': 'merged'
                    })
                
                return {
                    'success': True,
                    'output_file': result['output_file'],
                    'total_pages': result['total_pages'],
                    'source_info': source_info,
                    'merge_strategy': merge_strategy,
                    'metadata_preserved': preserve_metadata,
                    'statistics': result.get('statistics', {}),
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Merge operation failed'),
                    'output_file': None,
                    'total_pages': 0,
                    'source_info': [],
                    'merge_strategy': merge_strategy
                }
                
        except Exception as e:
            logger.error(f"PDF merge error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'output_file': None,
                'total_pages': 0,
                'source_info': [],
                'merge_strategy': merge_strategy
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
    
    def extract_tables(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None,
        csv_delimiter: str = ',',
        extraction_method: str = 'auto'
    ) -> Dict[str, Any]:
        """Extract tables from PDF file using TableExtractionService.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional tuple of (start_page, end_page) (1-indexed)
            csv_delimiter: Delimiter for CSV export
            extraction_method: Method to use ('auto', 'camelot', 'tabula')
            
        Returns:
            Dictionary containing table extraction results
        """
        try:
            logger.info(f"Starting table extraction from {file_path}")
            
            # Validate PDF first
            validation_result = self.validate_pdf(file_path)
            if not validation_result['is_valid']:
                return {
                    'success': False,
                    'error': f"Invalid PDF: {validation_result.get('error', 'Unknown error')}",
                    'tables': [],
                    'files': []
                }
            
            # Use TableExtractionService
            table_service = TableExtractionService(self.session_id)
            result = table_service.extract_tables(
                file_path=file_path,
                page_range=page_range,
                extraction_method=extraction_method,
                csv_delimiter=csv_delimiter
            )
            
            logger.info(f"Table extraction completed: {result.get('success', False)}")
            return result
            
        except Exception as e:
            logger.error(f"Table extraction error for {file_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'tables': [],
                'files': []
            }
    
    def extract_images_enhanced(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None,
        output_format: str = 'PNG',
        quality: int = 95,
        include_page_renders: bool = False
    ) -> Dict[str, Any]:
        """Extract images from PDF using enhanced ImageExtractionService.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional tuple of (start_page, end_page) (1-indexed)
            output_format: Target output format ('PNG', 'JPEG', 'TIFF', 'WEBP')
            quality: Output quality for JPEG (1-100)
            include_page_renders: Whether to also render pages as images
            
        Returns:
            Dictionary containing image extraction results
        """
        try:
            logger.info(f"Starting enhanced image extraction from {file_path}")
            
            # Validate PDF first
            validation_result = self.validate_pdf(file_path)
            if not validation_result['is_valid']:
                return {
                    'success': False,
                    'error': f"Invalid PDF: {validation_result.get('error', 'Unknown error')}",
                    'images': [],
                    'files': []
                }
            
            # Use ImageExtractionService
            image_service = ImageExtractionService(self.session_id)
            result = image_service.extract_images(
                file_path=file_path,
                page_range=page_range,
                output_format=output_format,
                quality=quality,
                include_page_renders=include_page_renders
            )
            
            logger.info(f"Enhanced image extraction completed: {result.get('success', False)}")
            return result
            
        except Exception as e:
            logger.error(f"Enhanced image extraction error for {file_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'images': [],
                'files': []
            }
    
    def extract_metadata_structured(
        self,
        file_path: Path,
        output_format: str = 'json',
        include_analysis: bool = True
    ) -> Dict[str, Any]:
        """Extract comprehensive metadata using MetadataExtractionService.
        
        Args:
            file_path: Path to the PDF file
            output_format: Output format ('json' only supported currently)
            include_analysis: Whether to include content analysis
            
        Returns:
            Dictionary containing metadata extraction results
        """
        try:
            logger.info(f"Starting structured metadata extraction from {file_path}")
            
            # Validate PDF first
            validation_result = self.validate_pdf(file_path)
            if not validation_result['is_valid']:
                return {
                    'success': False,
                    'error': f"Invalid PDF: {validation_result.get('error', 'Unknown error')}",
                    'metadata': {},
                    'files': []
                }
            
            # Use MetadataExtractionService
            metadata_service = MetadataExtractionService(self.session_id)
            result = metadata_service.extract_metadata(
                file_path=file_path,
                include_content_analysis=include_analysis,
                include_security_info=True,
                output_format=output_format
            )
            
            logger.info(f"Structured metadata extraction completed: {result.get('success', False)}")
            return result
            
        except Exception as e:
            logger.error(f"Structured metadata extraction error for {file_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'metadata': {},
                'files': []
            }
    
    def extract_comprehensive(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None,
        extraction_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract all content types from PDF using all extraction services.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional tuple of (start_page, end_page) (1-indexed)
            extraction_options: Optional dictionary of extraction parameters
            
        Returns:
            Dictionary containing comprehensive extraction results
        """
        try:
            logger.info(f"Starting comprehensive extraction from {file_path}")
            
            # Default options
            if extraction_options is None:
                extraction_options = {}
            
            # Validate PDF first
            validation_result = self.validate_pdf(file_path)
            if not validation_result['is_valid']:
                return {
                    'success': False,
                    'error': f"Invalid PDF: {validation_result.get('error', 'Unknown error')}",
                    'results': {}
                }
            
            comprehensive_results = {
                'success': True,
                'extraction_summary': {
                    'file_path': str(file_path),
                    'page_range': page_range,
                    'extraction_timestamp': datetime.now().isoformat(),
                    'services_used': [],
                    'total_files_created': 0
                },
                'results': {},
                'all_files': []
            }
            
            extraction_errors = []
            
            # Extract text (existing method)
            try:
                text_result = self.extract_text(file_path)
                if text_result['success']:
                    comprehensive_results['results']['text'] = text_result
                    comprehensive_results['extraction_summary']['services_used'].append('text_extraction')
                else:
                    comprehensive_results['results']['text'] = {
                        'success': False,
                        'error': text_result.get('error', 'Unknown error'),
                        'pages': [],
                        'total_pages': 0,
                        'has_text': False
                    }
                    extraction_errors.append(f"Text extraction: {text_result.get('error', 'Unknown error')}")
            except Exception as e:
                comprehensive_results['results']['text'] = {
                    'success': False,
                    'error': str(e),
                    'pages': [],
                    'total_pages': 0,
                    'has_text': False
                }
                extraction_errors.append(f"Text extraction failed: {e}")
            
            # Extract tables
            try:
                table_result = self.extract_tables(
                    file_path,
                    page_range=page_range,
                    csv_delimiter=extraction_options.get('csv_delimiter', ','),
                    extraction_method=extraction_options.get('table_extraction_method', 'auto')
                )
                if table_result['success']:
                    comprehensive_results['results']['tables'] = table_result
                    comprehensive_results['extraction_summary']['services_used'].append('table_extraction')
                    comprehensive_results['all_files'].extend(table_result.get('files', []))
                else:
                    comprehensive_results['results']['tables'] = {
                        'success': False,
                        'error': table_result.get('error', 'Unknown error'),
                        'tables': [],
                        'files': []
                    }
                    extraction_errors.append(f"Table extraction: {table_result.get('error', 'Unknown error')}")
            except Exception as e:
                comprehensive_results['results']['tables'] = {
                    'success': False,
                    'error': str(e),
                    'tables': [],
                    'files': []
                }
                extraction_errors.append(f"Table extraction failed: {e}")
            
            # Extract images
            try:
                image_result = self.extract_images_enhanced(
                    file_path,
                    page_range=page_range,
                    output_format=extraction_options.get('image_format', 'PNG'),
                    quality=extraction_options.get('image_quality', 95),
                    include_page_renders=extraction_options.get('include_page_renders', False)
                )
                if image_result['success']:
                    comprehensive_results['results']['images'] = image_result
                    comprehensive_results['extraction_summary']['services_used'].append('image_extraction')
                    comprehensive_results['all_files'].extend(image_result.get('files', []))
                else:
                    comprehensive_results['results']['images'] = {
                        'success': False,
                        'error': image_result.get('error', 'Unknown error'),
                        'images': [],
                        'files': []
                    }
                    extraction_errors.append(f"Image extraction: {image_result.get('error', 'Unknown error')}")
            except Exception as e:
                comprehensive_results['results']['images'] = {
                    'success': False,
                    'error': str(e),
                    'images': [],
                    'files': []
                }
                extraction_errors.append(f"Image extraction failed: {e}")
            
            # Extract metadata
            try:
                metadata_result = self.extract_metadata_structured(
                    file_path,
                    output_format=extraction_options.get('metadata_format', 'json'),
                    include_analysis=extraction_options.get('include_content_analysis', True)
                )
                if metadata_result['success']:
                    comprehensive_results['results']['metadata'] = metadata_result
                    comprehensive_results['extraction_summary']['services_used'].append('metadata_extraction')
                    comprehensive_results['all_files'].extend(metadata_result.get('files', []))
                else:
                    comprehensive_results['results']['metadata'] = {
                        'success': False,
                        'error': metadata_result.get('error', 'Unknown error'),
                        'metadata': {},
                        'files': []
                    }
                    extraction_errors.append(f"Metadata extraction: {metadata_result.get('error', 'Unknown error')}")
            except Exception as e:
                comprehensive_results['results']['metadata'] = {
                    'success': False,
                    'error': str(e),
                    'metadata': {},
                    'files': []
                }
                extraction_errors.append(f"Metadata extraction failed: {e}")
            
            # Update summary
            comprehensive_results['extraction_summary']['total_files_created'] = len(comprehensive_results['all_files'])
            comprehensive_results['extraction_summary']['extraction_errors'] = extraction_errors
            
            # Count successful vs failed services
            successful_services = sum(1 for result in comprehensive_results['results'].values() if result.get('success', False))
            comprehensive_results['extraction_summary']['services_successful'] = successful_services
            comprehensive_results['extraction_summary']['services_failed'] = len(comprehensive_results['results']) - successful_services
            comprehensive_results['extraction_summary']['services_total'] = len(comprehensive_results['results'])
            
            # Ensure files_created contains all available files from successful services
            comprehensive_results['files_created'] = comprehensive_results['all_files']
            
            # Determine overall success
            if not comprehensive_results['results'] and extraction_errors:
                comprehensive_results['success'] = False
                comprehensive_results['error'] = f"All extractions failed: {'; '.join(extraction_errors)}"
            elif extraction_errors:
                comprehensive_results['partial_success'] = True
                comprehensive_results['warning'] = f"Some extractions failed: {'; '.join(extraction_errors)}"
            
            logger.info(f"Comprehensive extraction completed: {len(comprehensive_results['results'])} services successful")
            return comprehensive_results
            
        except Exception as e:
            logger.error(f"Comprehensive extraction error for {file_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'results': {}
            }
    
    def _determine_optimal_extraction_strategy(self, file_path: Path) -> Dict[str, Any]:
        """Analyze PDF characteristics and recommend extraction methods.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with extraction strategy recommendations
        """
        try:
            recommendations = {
                'text_extraction': {
                    'recommended_method': 'auto',
                    'reason': 'Standard approach',
                    'confidence': 0.8
                },
                'table_extraction': {
                    'recommended_method': 'auto',
                    'reason': 'Will determine best approach based on PDF structure',
                    'confidence': 0.7,
                    'likely_success': True
                },
                'image_extraction': {
                    'recommended_format': 'PNG',
                    'include_page_renders': False,
                    'reason': 'PNG preserves quality without size issues',
                    'confidence': 0.9
                }
            }
            
            # Analyze PDF characteristics
            validation_result = self.validate_pdf(file_path)
            if not validation_result['is_valid']:
                return {
                    'success': False,
                    'error': validation_result.get('error'),
                    'recommendations': recommendations
                }
            
            has_text_layer = validation_result.get('has_text_layer', False)
            page_count = validation_result.get('page_count', 0)
            
            # Adjust text extraction recommendations
            if not has_text_layer:
                recommendations['text_extraction'] = {
                    'recommended_method': 'ocr',
                    'reason': 'No text layer detected, OCR required',
                    'confidence': 0.6
                }
            elif page_count > 100:
                recommendations['text_extraction'] = {
                    'recommended_method': 'text_layer',
                    'reason': 'Large document, text layer is faster',
                    'confidence': 0.9
                }
            
            # Adjust table extraction recommendations
            if page_count > 50:
                recommendations['table_extraction']['recommended_method'] = 'camelot'
                recommendations['table_extraction']['reason'] = 'Large document, camelot is more efficient'
                recommendations['table_extraction']['confidence'] = 0.8
            
            # Adjust image extraction recommendations
            if page_count > 20:
                recommendations['image_extraction']['include_page_renders'] = False
                recommendations['image_extraction']['reason'] = 'Large document, extract embedded images only'
            
            return {
                'success': True,
                'recommendations': recommendations,
                'document_characteristics': {
                    'has_text_layer': has_text_layer,
                    'page_count': page_count,
                    'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error determining extraction strategy for {file_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'recommendations': recommendations
            }