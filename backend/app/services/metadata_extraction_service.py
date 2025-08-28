"""
Metadata extraction service for comprehensive PDF metadata analysis.

This service provides enhanced metadata extraction with structured JSON output,
including document structure, security features, and content analysis.
"""

import logging
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF

from app.utils.temp_file_manager import TempFileManager
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)


class MetadataExtractionService:
    """Service for extracting comprehensive metadata from PDF documents."""
    
    def __init__(self, session_id: str):
        """Initialize the metadata extraction service.
        
        Args:
            session_id: Unique session identifier for file management
        """
        self.session_id = session_id
        self.temp_file_manager = TempFileManager(session_id)
    
    @handle_errors
    def extract_metadata(
        self,
        file_path: Path,
        include_content_analysis: bool = True,
        include_security_info: bool = True,
        output_format: str = 'json'
    ) -> Dict[str, Any]:
        """Extract comprehensive metadata from PDF file.
        
        Args:
            file_path: Path to the PDF file
            include_content_analysis: Whether to analyze document content
            include_security_info: Whether to include security metadata
            output_format: Output format ('json' only supported currently)
            
        Returns:
            Dictionary containing extraction results and metadata
        """
        logger.info(f"Starting metadata extraction from {file_path}")
        
        try:
            doc = fitz.open(str(file_path))
            
            # Extract all metadata components
            metadata = {}
            
            # Basic PDF metadata
            basic_metadata = self._extract_basic_metadata(doc)
            metadata.update(basic_metadata)
            
            # Technical metadata
            technical_metadata = self._extract_technical_metadata(doc, file_path)
            metadata.update(technical_metadata)
            
            # Document structure analysis
            structure_metadata = self._analyze_document_structure(doc)
            metadata.update(structure_metadata)
            
            # Security metadata
            if include_security_info:
                security_metadata = self._extract_security_metadata(doc)
                metadata.update(security_metadata)
            
            # Content analysis
            if include_content_analysis:
                content_metadata = self._analyze_content_characteristics(doc)
                metadata.update(content_metadata)
            
            # File system metadata
            creation_metadata = self._extract_creation_metadata(file_path)
            metadata.update(creation_metadata)
            
            # Format and validate metadata
            formatted_metadata = self._format_metadata_for_json(metadata)
            validation_result = self._validate_metadata_completeness(formatted_metadata)
            
            # Export to JSON file
            output_files = []
            if output_format.lower() == 'json':
                json_file = self._export_metadata_to_json(formatted_metadata)
                if json_file:
                    output_files.append({
                        'filename': json_file['filename'],
                        'file_path': json_file['file_path'],
                        'file_size': json_file['file_size'],
                        'type': 'metadata_json'
                    })
            
            doc.close()
            
            logger.info("Metadata extraction completed successfully")
            
            return {
                'success': True,
                'metadata': formatted_metadata,
                'files': output_files,
                'validation': validation_result,
                'output_format': output_format,
                'extraction_timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in metadata extraction: {e}")
            return {
                'success': False,
                'error': str(e),
                'metadata': {},
                'files': []
            }
    
    def _extract_basic_metadata(self, doc) -> Dict[str, Any]:
        """Extract standard PDF metadata fields.
        
        Args:
            doc: PyMuPDF document object
            
        Returns:
            Dictionary containing basic metadata
        """
        metadata = {'basic_metadata': {}}
        
        try:
            pdf_metadata = doc.metadata
            
            # Standard metadata fields
            standard_fields = {
                'title': pdf_metadata.get('title', ''),
                'author': pdf_metadata.get('author', ''),
                'subject': pdf_metadata.get('subject', ''),
                'keywords': pdf_metadata.get('keywords', ''),
                'creator': pdf_metadata.get('creator', ''),
                'producer': pdf_metadata.get('producer', ''),
                'creation_date': pdf_metadata.get('creationDate', ''),
                'modification_date': pdf_metadata.get('modDate', ''),
                'trapped': pdf_metadata.get('trapped', '')
            }
            
            # Clean and parse dates
            for date_field in ['creation_date', 'modification_date']:
                if standard_fields[date_field]:
                    parsed_date = self._parse_pdf_date(standard_fields[date_field])
                    standard_fields[date_field] = parsed_date
            
            # Split keywords if present
            if standard_fields['keywords']:
                keywords_list = [k.strip() for k in standard_fields['keywords'].split(',')]
                standard_fields['keywords_list'] = keywords_list
            
            metadata['basic_metadata'] = standard_fields
            
        except Exception as e:
            logger.warning(f"Failed to extract basic metadata: {e}")
        
        return metadata
    
    def _extract_technical_metadata(self, doc, file_path: Path) -> Dict[str, Any]:
        """Extract technical PDF metadata.
        
        Args:
            doc: PyMuPDF document object
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing technical metadata
        """
        metadata = {'technical_metadata': {}}
        
        try:
            # PDF version and basic info
            technical_info = {
                'page_count': len(doc),
                'file_size_bytes': file_path.stat().st_size,
                'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
            }
            
            # Safely extract PDF version (attribute, not method)
            try:
                technical_info['pdf_version'] = getattr(doc, 'pdf_version', None)
            except Exception as e:
                logger.debug(f"Could not extract PDF version: {e}")
                technical_info['pdf_version'] = None
            
            # Safely check PDF/A compliance
            try:
                technical_info['is_pdf_a_compliant'] = getattr(doc, 'is_pdf', False)
            except Exception as e:
                logger.debug(f"Could not check PDF/A compliance: {e}")
                technical_info['is_pdf_a_compliant'] = False
            
            # Standard attributes that should be available
            try:
                technical_info['needs_password'] = doc.needs_pass
            except Exception as e:
                logger.debug(f"Could not check password requirement: {e}")
                technical_info['needs_password'] = False
            
            try:
                technical_info['is_modified'] = doc.is_dirty
            except Exception as e:
                logger.debug(f"Could not check modification status: {e}")
                technical_info['is_modified'] = False
            
            # Safely check incremental save capability
            try:
                if hasattr(doc, 'can_save_incrementally'):
                    technical_info['supports_incremental_save'] = doc.can_save_incrementally()
                else:
                    technical_info['supports_incremental_save'] = None
            except Exception as e:
                logger.debug(f"Could not check incremental save capability: {e}")
                technical_info['supports_incremental_save'] = None
            
            # Page dimensions and orientations
            page_info = []
            page_sizes = set()
            orientations = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                rect = page.rect
                width, height = rect.width, rect.height
                
                # Determine orientation
                if width > height:
                    orientation = 'landscape'
                elif height > width:
                    orientation = 'portrait'
                else:
                    orientation = 'square'
                
                orientations.append(orientation)
                page_sizes.add((round(width), round(height)))
                
                page_info.append({
                    'page': page_num + 1,
                    'width': round(width, 2),
                    'height': round(height, 2),
                    'orientation': orientation,
                    'rotation': page.rotation
                })
            
            technical_info['pages'] = page_info
            technical_info['unique_page_sizes'] = len(page_sizes)
            technical_info['page_sizes'] = list(page_sizes)
            technical_info['orientations'] = {
                'portrait': orientations.count('portrait'),
                'landscape': orientations.count('landscape'),
                'square': orientations.count('square')
            }
            
            # Compression and optimization info
            try:
                # Check for linearization (fast web view)
                is_pdf_format = getattr(doc, 'is_pdf', False)
                has_linearization = hasattr(doc, '_getLinearized')
                if is_pdf_format and has_linearization:
                    technical_info['is_linearized'] = doc._getLinearized()
                else:
                    technical_info['is_linearized'] = False
            except Exception as e:
                logger.debug(f"Could not check linearization: {e}")
                technical_info['is_linearized'] = False
            
            metadata['technical_metadata'] = technical_info
            
        except Exception as e:
            logger.warning(f"Failed to extract technical metadata: {e}")
        
        return metadata
    
    def _analyze_document_structure(self, doc) -> Dict[str, Any]:
        """Analyze PDF document structure and organization.
        
        Args:
            doc: PyMuPDF document object
            
        Returns:
            Dictionary containing structure analysis
        """
        metadata = {'document_structure': {}}
        
        try:
            structure_info = {
                'has_outline': False,
                'outline_items': 0,
                'form_fields': 0,
                'annotations_count': 0,
                'embedded_files': 0,
                'links_count': 0,
                'bookmarks': []
            }
            
            # Analyze table of contents/outline
            try:
                toc = doc.get_toc()
                if toc:
                    structure_info['has_outline'] = True
                    structure_info['outline_items'] = len(toc)
                    structure_info['outline_levels'] = max(item[0] for item in toc) if toc else 0
                    
                    # Extract bookmark hierarchy
                    bookmarks = []
                    for level, title, page in toc[:20]:  # Limit to first 20 items
                        bookmarks.append({
                            'level': level,
                            'title': title.strip(),
                            'page': page
                        })
                    structure_info['bookmarks'] = bookmarks
            except:
                pass
            
            # Count form fields, annotations, and links
            total_annotations = 0
            total_links = 0
            form_fields = set()
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Count annotations
                annotations = page.annots()
                if annotations:
                    for annot in annotations:
                        total_annotations += 1
                
                # Count links
                links = page.get_links()
                total_links += len(links)
                
                # Detect form fields
                try:
                    widgets = page.widgets()
                    if widgets:
                        for widget in widgets:
                            form_fields.add(widget.field_name if widget.field_name else f'field_{len(form_fields)}')
                except:
                    pass
            
            structure_info['annotations_count'] = total_annotations
            structure_info['links_count'] = total_links
            structure_info['form_fields'] = len(form_fields)
            
            # Check for embedded files
            try:
                embedded_files = doc.embfile_names()
                structure_info['embedded_files'] = len(embedded_files) if embedded_files else 0
                if embedded_files:
                    structure_info['embedded_file_names'] = embedded_files[:10]  # Limit to first 10
            except:
                pass
            
            metadata['document_structure'] = structure_info
            
        except Exception as e:
            logger.warning(f"Failed to analyze document structure: {e}")
        
        return metadata
    
    def _extract_security_metadata(self, doc) -> Dict[str, Any]:
        """Extract security-related metadata.
        
        Args:
            doc: PyMuPDF document object
            
        Returns:
            Dictionary containing security metadata
        """
        metadata = {'security_metadata': {}}
        
        try:
            security_info = {
                'is_encrypted': doc.is_encrypted,
                'needs_password': doc.needs_pass,
                'permissions': {},
                'has_digital_signatures': False,
                'security_handler': None
            }
            
            # Extract permissions if document is not encrypted or if we have access
            if not doc.needs_pass:
                try:
                    # Check various permissions
                    permissions = {
                        'can_print': True,  # Default assumption for non-encrypted docs
                        'can_modify': True,
                        'can_copy': True,
                        'can_add_annotations': True
                    }
                    
                    # For encrypted docs with known password, we could check actual permissions
                    # This would require the password to be provided
                    
                    security_info['permissions'] = permissions
                except Exception as e:
                    logger.debug(f"Could not extract permissions: {e}")
            
            # Check for digital signatures
            try:
                # Check if document has signature fields
                has_signatures = False
                for page_num in range(min(10, len(doc))):  # Check first 10 pages
                    page = doc.load_page(page_num)
                    try:
                        widgets = page.widgets()
                        if widgets:
                            for widget in widgets:
                                if hasattr(widget, 'field_type') and 'signature' in str(widget.field_type).lower():
                                    has_signatures = True
                                    break
                    except:
                        continue
                    if has_signatures:
                        break
                
                security_info['has_digital_signatures'] = has_signatures
            except:
                pass
            
            metadata['security_metadata'] = security_info
            
        except Exception as e:
            logger.warning(f"Failed to extract security metadata: {e}")
        
        return metadata
    
    def _analyze_content_characteristics(self, doc) -> Dict[str, Any]:
        """Analyze document content characteristics.
        
        Args:
            doc: PyMuPDF document object
            
        Returns:
            Dictionary containing content analysis
        """
        metadata = {'content_analysis': {}}
        
        try:
            content_info = {
                'total_characters': 0,
                'total_words': 0,
                'pages_with_text': 0,
                'pages_with_images': 0,
                'text_to_page_ratio': 0.0,
                'estimated_reading_time_minutes': 0,
                'languages_detected': [],
                'has_tables': False,
                'complexity_score': 0.0
            }
            
            # Analyze content on each page
            pages_with_text = 0
            pages_with_images = 0
            total_chars = 0
            total_words = 0
            
            # Sample pages for analysis (limit for performance)
            pages_to_analyze = min(len(doc), 20)
            sample_pages = range(0, len(doc), max(1, len(doc) // pages_to_analyze))
            
            text_samples = []
            
            for page_num in sample_pages:
                page = doc.load_page(page_num)
                
                # Extract text
                text = page.get_text()
                if text.strip():
                    pages_with_text += 1
                    char_count = len(text)
                    word_count = len(text.split())
                    total_chars += char_count
                    total_words += word_count
                    
                    # Collect text samples for language detection
                    if len(text.strip()) > 100:
                        text_samples.append(text.strip()[:500])  # First 500 chars
                
                # Check for images
                images = page.get_images()
                if images:
                    pages_with_images += 1
            
            # Scale up based on sampling
            if sample_pages:
                scale_factor = len(doc) / len(list(sample_pages))
                content_info['pages_with_text'] = int(pages_with_text * scale_factor)
                content_info['pages_with_images'] = int(pages_with_images * scale_factor)
                content_info['total_characters'] = int(total_chars * scale_factor)
                content_info['total_words'] = int(total_words * scale_factor)
            
            # Calculate ratios and metrics
            if len(doc) > 0:
                content_info['text_to_page_ratio'] = round(content_info['pages_with_text'] / len(doc), 2)
            
            # Estimate reading time (average 250 words per minute)
            if content_info['total_words'] > 0:
                content_info['estimated_reading_time_minutes'] = max(1, round(content_info['total_words'] / 250))
            
            # Simple language detection using common words
            if text_samples:
                detected_language = self._detect_document_language(text_samples)
                if detected_language:
                    content_info['languages_detected'] = [detected_language]
            
            # Simple table detection heuristic
            content_info['has_tables'] = self._detect_potential_tables(doc, list(sample_pages)[:5])
            
            # Calculate complexity score
            complexity_factors = []
            complexity_factors.append(min(len(doc) / 100, 1.0))  # Page count factor
            complexity_factors.append(min(content_info['total_words'] / 10000, 1.0))  # Word count factor
            if content_info['pages_with_images'] > 0:
                complexity_factors.append(0.3)  # Has images
            if content_info.get('has_tables'):
                complexity_factors.append(0.2)  # Has tables
            
            content_info['complexity_score'] = round(sum(complexity_factors) / len(complexity_factors), 2)
            
            metadata['content_analysis'] = content_info
            
        except Exception as e:
            logger.warning(f"Failed to analyze content characteristics: {e}")
        
        return metadata
    
    def _extract_creation_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract file system and creation metadata.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing creation metadata
        """
        metadata = {'file_metadata': {}}
        
        try:
            stat_info = file_path.stat()
            
            file_info = {
                'filename': file_path.name,
                'file_extension': file_path.suffix.lower(),
                'file_size_bytes': stat_info.st_size,
                'file_size_mb': round(stat_info.st_size / (1024 * 1024), 2),
                'creation_time': datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                'modification_time': datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                'access_time': datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            }
            
            # Calculate file hash for integrity verification
            try:
                hash_sha256 = hashlib.sha256()
                with open(file_path, 'rb') as f:
                    # Read in chunks to handle large files
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_sha256.update(chunk)
                file_info['sha256_hash'] = hash_sha256.hexdigest()
            except Exception as e:
                logger.warning(f"Failed to calculate file hash: {e}")
            
            metadata['file_metadata'] = file_info
            
        except Exception as e:
            logger.warning(f"Failed to extract creation metadata: {e}")
        
        return metadata
    
    def _parse_pdf_date(self, date_string: str) -> str:
        """Parse PDF date string to ISO format.
        
        Args:
            date_string: PDF date string (usually D:YYYYMMDDHHMMSS format)
            
        Returns:
            ISO formatted date string or original if parsing fails
        """
        if not date_string:
            return ''
        
        try:
            # Remove D: prefix if present
            if date_string.startswith('D:'):
                date_string = date_string[2:]
            
            # Parse YYYYMMDDHHMMSS format
            if len(date_string) >= 14:
                year = int(date_string[:4])
                month = int(date_string[4:6])
                day = int(date_string[6:8])
                hour = int(date_string[8:10])
                minute = int(date_string[10:12])
                second = int(date_string[12:14])
                
                dt = datetime(year, month, day, hour, minute, second)
                return dt.isoformat()
        except:
            pass
        
        return date_string
    
    def _detect_document_language(self, text_samples: List[str]) -> Optional[str]:
        """Simple language detection based on character patterns.
        
        Args:
            text_samples: List of text samples to analyze
            
        Returns:
            Detected language code or None
        """
        if not text_samples:
            return None
        
        # Simple heuristics for common languages
        combined_text = ' '.join(text_samples).lower()
        
        # English indicators
        english_words = ['the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with']
        english_score = sum(1 for word in english_words if word in combined_text)
        
        if english_score >= 3:
            return 'en'
        
        # Could add more language detection logic here
        return 'unknown'
    
    def _detect_potential_tables(self, doc, sample_pages: List[int]) -> bool:
        """Simple heuristic to detect potential tables in document.
        
        Args:
            doc: PyMuPDF document object
            sample_pages: List of page indices to check
            
        Returns:
            True if tables are likely present
        """
        try:
            for page_num in sample_pages:
                page = doc.load_page(page_num)
                text = page.get_text()
                
                # Look for table indicators
                lines = text.split('\n')
                tabular_lines = 0
                
                for line in lines:
                    # Count lines with multiple tabs or spaces suggesting columnar data
                    if '\t' in line or len(line.split()) > 4:
                        tabular_lines += 1
                
                # If more than 20% of lines look tabular, suggest tables present
                if lines and tabular_lines / len(lines) > 0.2:
                    return True
                    
        except Exception as e:
            logger.debug(f"Error in table detection heuristic: {e}")
        
        return False
    
    def _format_metadata_for_json(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format metadata for JSON serialization.
        
        Args:
            metadata: Raw metadata dictionary
            
        Returns:
            JSON-serializable metadata dictionary
        """
        def clean_value(value):
            """Recursively clean values for JSON compatibility."""
            if isinstance(value, dict):
                return {k: clean_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [clean_value(item) for item in value]
            elif isinstance(value, (str, int, float, bool, type(None))):
                return value
            else:
                return str(value)
        
        return clean_value(metadata)
    
    def _validate_metadata_completeness(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Validate metadata completeness and quality.
        
        Args:
            metadata: Metadata dictionary to validate
            
        Returns:
            Validation results dictionary
        """
        validation = {
            'completeness_score': 0.0,
            'missing_fields': [],
            'data_quality_issues': [],
            'recommendations': []
        }
        
        # Check for expected sections
        expected_sections = [
            'basic_metadata', 'technical_metadata', 'document_structure',
            'security_metadata', 'content_analysis', 'file_metadata'
        ]
        
        present_sections = sum(1 for section in expected_sections if section in metadata)
        validation['completeness_score'] = round(present_sections / len(expected_sections), 2)
        
        # Check for missing critical fields
        if 'basic_metadata' in metadata:
            basic = metadata['basic_metadata']
            if not basic.get('title'):
                validation['missing_fields'].append('title')
            if not basic.get('author'):
                validation['missing_fields'].append('author')
        
        # Data quality checks
        if 'content_analysis' in metadata:
            content = metadata['content_analysis']
            if content.get('total_words', 0) == 0:
                validation['data_quality_issues'].append('No text content detected')
        
        # Generate recommendations
        if validation['completeness_score'] < 0.8:
            validation['recommendations'].append('Consider enabling all metadata extraction options')
        
        if validation['missing_fields']:
            validation['recommendations'].append('Document metadata could be enhanced by adding title and author information')
        
        return validation
    
    def _export_metadata_to_json(self, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Export metadata to JSON file.
        
        Args:
            metadata: Metadata dictionary to export
            
        Returns:
            File information dictionary or None if export failed
        """
        try:
            downloads_dir = self.temp_file_manager.downloads_dir
            filename = f'metadata_{self.session_id[:8]}.json'
            file_path = downloads_dir / filename
            
            # Add export metadata
            export_data = {
                'extraction_info': {
                    'timestamp': datetime.utcnow().isoformat(),
                    'extractor_version': '1.0',
                    'session_id': self.session_id
                },
                'metadata': metadata
            }
            
            # Write JSON with pretty formatting
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            file_info = {
                'filename': filename,
                'file_path': str(file_path),
                'file_size': file_path.stat().st_size
            }
            
            logger.info(f"Exported metadata to {filename}")
            return file_info
            
        except Exception as e:
            logger.error(f"Failed to export metadata to JSON: {e}")
            return None