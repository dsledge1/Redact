"""File validation utilities for Ultimate PDF application."""

import mimetypes
import hashlib
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings
from fuzzywuzzy import fuzz

from .errors import ValidationError, FileError

logger = logging.getLogger(__name__)


class PDFValidator:
    """Validator class for PDF file validation with comprehensive security checks."""
    
    # File validation constants
    MAX_FILE_SIZE = getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 100 * 1024 * 1024)  # 100MB
    MIN_FILE_SIZE = 1024  # 1KB minimum
    ALLOWED_EXTENSIONS = ['.pdf']
    ALLOWED_MIME_TYPES = ['application/pdf', 'application/x-pdf']
    
    # PDF signature validation
    PDF_SIGNATURES = [
        b'%PDF-1.',  # Standard PDF signature
        b'%PDF-2.'   # PDF 2.0 signature
    ]
    
    # Suspicious content patterns to detect potentially malicious files
    SUSPICIOUS_PATTERNS = [
        b'<script',
        b'javascript:',
        b'eval(',
        b'ActiveXObject',
        b'XMLHttpRequest'
    ]
    
    def __init__(self):
        """Initialize PDF validator with default settings."""
        self.max_file_size = self.MAX_FILE_SIZE
        self.min_file_size = self.MIN_FILE_SIZE
    
    def validate_pdf_file(self, uploaded_file: UploadedFile) -> Dict[str, Any]:
        """Comprehensive PDF file validation.
        
        Args:
            uploaded_file: Django UploadedFile instance
            
        Returns:
            Dictionary with validation results and file metadata
            
        Raises:
            ValidationError: If file validation fails
            FileError: If file operations fail
        """
        try:
            validation_results = {
                'is_valid': True,
                'filename': uploaded_file.name,
                'size': uploaded_file.size,
                'content_type': uploaded_file.content_type,
                'validations_passed': [],
                'warnings': []
            }
            
            # Basic file presence check
            if not uploaded_file:
                raise ValidationError("No file provided")
            
            validation_results['validations_passed'].append('file_present')
            
            # File size validation
            self._validate_file_size(uploaded_file.size)
            validation_results['validations_passed'].append('size_check')
            
            # File extension validation
            self._validate_file_extension(uploaded_file.name)
            validation_results['validations_passed'].append('extension_check')
            
            # MIME type validation
            mime_warnings = self._validate_mime_type(uploaded_file)
            if mime_warnings:
                validation_results['warnings'].extend(mime_warnings)
            validation_results['validations_passed'].append('mime_type_check')
            
            # PDF signature validation (read file content)
            uploaded_file.seek(0)  # Reset file pointer
            file_content = uploaded_file.read(1024)  # Read first 1KB for signature check
            uploaded_file.seek(0)  # Reset file pointer again
            
            self._validate_pdf_signature(file_content)
            validation_results['validations_passed'].append('signature_check')
            
            # Security scan for suspicious content
            security_warnings = self._scan_for_suspicious_content(file_content)
            if security_warnings:
                validation_results['warnings'].extend(security_warnings)
            validation_results['validations_passed'].append('security_scan')
            
            # Calculate file hash for integrity
            uploaded_file.seek(0)
            file_hash = self._calculate_file_hash(uploaded_file)
            validation_results['file_hash'] = file_hash
            validation_results['validations_passed'].append('hash_calculation')
            
            # Additional PDF metadata validation
            try:
                uploaded_file.seek(0)
                pdf_metadata = self._extract_pdf_metadata(uploaded_file)
                validation_results['pdf_metadata'] = pdf_metadata
                validation_results['validations_passed'].append('metadata_extraction')
            except Exception as e:
                logger.warning(f"PDF metadata extraction failed: {str(e)}")
                validation_results['warnings'].append(f"Could not extract PDF metadata: {str(e)}")
            
            logger.info(
                f"PDF validation successful for file: {uploaded_file.name}",
                extra={
                    'file_size': uploaded_file.size,
                    'validations_passed': len(validation_results['validations_passed']),
                    'warnings': len(validation_results['warnings'])
                }
            )
            
            uploaded_file.seek(0)  # Leave file pointer at start after validation
            return validation_results
            
        except (ValidationError, FileError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error during PDF validation: {str(e)}")
            raise FileError(
                message="File validation failed due to unexpected error",
                operation="validation",
                details={'error': str(e)}
            )
    
    def _validate_file_size(self, file_size: int) -> None:
        """Validate file size is within acceptable limits.
        
        Args:
            file_size: Size of the file in bytes
            
        Raises:
            ValidationError: If file size is invalid
        """
        if file_size < self.min_file_size:
            raise ValidationError(
                f"File is too small. Minimum size is {self.min_file_size} bytes",
                field="file_size",
                value=file_size
            )
        
        if file_size > self.max_file_size:
            raise ValidationError(
                f"File is too large. Maximum size is {self.max_file_size / (1024*1024):.1f} MB",
                field="file_size", 
                value=file_size
            )
    
    def _validate_file_extension(self, filename: str) -> None:
        """Validate file has an allowed extension.
        
        Args:
            filename: Name of the uploaded file
            
        Raises:
            ValidationError: If file extension is not allowed
        """
        if not filename:
            raise ValidationError("Filename is required")
        
        file_path = Path(filename)
        extension = file_path.suffix.lower()
        
        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Invalid file extension '{extension}'. Only {', '.join(self.ALLOWED_EXTENSIONS)} files are allowed",
                field="file_extension",
                value=extension
            )
    
    def _validate_mime_type(self, uploaded_file: UploadedFile) -> List[str]:
        """Validate MIME type of the uploaded file.
        
        Args:
            uploaded_file: Django UploadedFile instance
            
        Returns:
            List of warnings (empty if no issues)
            
        Raises:
            ValidationError: If MIME type is completely invalid
        """
        warnings = []
        
        # Check reported content type
        reported_mime = uploaded_file.content_type
        
        if reported_mime not in self.ALLOWED_MIME_TYPES:
            # Try to guess MIME type from filename
            guessed_mime, _ = mimetypes.guess_type(uploaded_file.name)
            
            if guessed_mime in self.ALLOWED_MIME_TYPES:
                warnings.append(
                    f"MIME type mismatch: reported as '{reported_mime}', "
                    f"but filename suggests '{guessed_mime}'"
                )
            else:
                raise ValidationError(
                    f"Invalid file type '{reported_mime}'. Only PDF files are allowed",
                    field="content_type",
                    value=reported_mime
                )
        
        return warnings
    
    def _validate_pdf_signature(self, file_content: bytes) -> None:
        """Validate PDF file signature.
        
        Args:
            file_content: First portion of file content
            
        Raises:
            ValidationError: If PDF signature is invalid
        """
        if len(file_content) < 8:
            raise ValidationError("File is too small to contain a valid PDF header")
        
        # Check for PDF signature at the beginning of file
        has_valid_signature = any(
            file_content.startswith(signature) 
            for signature in self.PDF_SIGNATURES
        )
        
        if not has_valid_signature:
            raise ValidationError(
                "File does not appear to be a valid PDF (invalid signature)",
                field="pdf_signature"
            )
    
    def _scan_for_suspicious_content(self, file_content: bytes) -> List[str]:
        """Scan file content for potentially malicious patterns.
        
        Args:
            file_content: File content to scan
            
        Returns:
            List of security warnings
        """
        warnings = []
        
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.lower() in file_content.lower():
                warnings.append(
                    f"Suspicious content detected: file contains '{pattern.decode('utf-8', errors='ignore')}'"
                )
        
        return warnings
    
    def _calculate_file_hash(self, uploaded_file: UploadedFile) -> str:
        """Calculate SHA-256 hash of the file.
        
        Args:
            uploaded_file: Django UploadedFile instance
            
        Returns:
            Hexadecimal SHA-256 hash string
        """
        sha256_hash = hashlib.sha256()
        
        for chunk in uploaded_file.chunks():
            sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def _extract_pdf_metadata(self, uploaded_file: UploadedFile) -> Dict[str, Any]:
        """Extract basic PDF metadata without full parsing.
        
        Args:
            uploaded_file: Django UploadedFile instance
            
        Returns:
            Dictionary with basic PDF metadata
        """
        metadata = {
            'filename': uploaded_file.name,
            'size_bytes': uploaded_file.size,
            'size_mb': round(uploaded_file.size / (1024 * 1024), 2),
            'content_type': uploaded_file.content_type
        }
        
        try:
            # Read first few KB to extract basic information
            uploaded_file.seek(0)
            header = uploaded_file.read(4096).decode('latin-1', errors='ignore')
            
            # Extract PDF version
            if '%PDF-' in header:
                version_start = header.find('%PDF-') + 5
                version_end = header.find('\n', version_start)
                if version_end > version_start:
                    metadata['pdf_version'] = header[version_start:version_end].strip()
            
            # Look for basic metadata indicators
            if '/Title' in header:
                metadata['has_title'] = True
            if '/Author' in header:
                metadata['has_author'] = True
            if '/Creator' in header:
                metadata['has_creator'] = True
            if '/Encrypt' in header:
                metadata['is_encrypted'] = True
                
        except Exception as e:
            logger.warning(f"Could not extract PDF metadata: {str(e)}")
            metadata['metadata_extraction_error'] = str(e)
        
        return metadata


# Convenience function for quick validation
def validate_pdf_file(uploaded_file: UploadedFile) -> Dict[str, Any]:
    """Quick PDF validation function.
    
    Args:
        uploaded_file: Django UploadedFile instance
        
    Returns:
        Validation results dictionary
        
    Raises:
        ValidationError: If validation fails
        FileError: If file operations fail
    """
    validator = PDFValidator()
    return validator.validate_pdf_file(uploaded_file)


def validate_file_exists(file_path: Path) -> None:
    """Validate that a file exists and is readable.
    
    Args:
        file_path: Path to the file to validate
        
    Raises:
        FileError: If file doesn't exist or isn't readable
    """
    if not isinstance(file_path, Path):
        file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileError(
            f"File not found: {file_path}",
            file_path=str(file_path),
            operation="existence_check"
        )
    
    if not file_path.is_file():
        raise FileError(
            f"Path is not a file: {file_path}",
            file_path=str(file_path),
            operation="file_type_check"
        )
    
    try:
        # Test file readability
        with open(file_path, 'rb') as f:
            f.read(1)  # Try to read one byte
    except PermissionError:
        raise FileError(
            f"Permission denied reading file: {file_path}",
            file_path=str(file_path),
            operation="permission_check"
        )
    except Exception as e:
        raise FileError(
            f"Cannot read file {file_path}: {str(e)}",
            file_path=str(file_path),
            operation="readability_check"
        )


def validate_session_id(session_id: str) -> None:
    """Validate session ID format and content.
    
    Args:
        session_id: Session ID to validate
        
    Raises:
        ValidationError: If session ID is invalid
    """
    if not session_id:
        raise ValidationError("Session ID is required")
    
    if not isinstance(session_id, str):
        raise ValidationError(
            "Session ID must be a string",
            field="session_id",
            value=type(session_id).__name__
        )
    
    # Session ID should be alphanumeric and reasonable length
    if len(session_id) < 8 or len(session_id) > 64:
        raise ValidationError(
            "Session ID must be between 8 and 64 characters",
            field="session_id",
            value=len(session_id)
        )
    
    if not session_id.replace('_', '').replace('-', '').isalnum():
        raise ValidationError(
            "Session ID must contain only alphanumeric characters, hyphens, and underscores",
            field="session_id",
            value=session_id
        )


def validate_search_terms(search_terms: List[str]) -> None:
    """Validate search terms for fuzzy matching.
    
    Args:
        search_terms: List of search terms to validate
        
    Raises:
        ValidationError: If search terms are invalid
    """
    if not search_terms:
        raise ValidationError("At least one search term is required")
    
    if not isinstance(search_terms, list):
        raise ValidationError(
            "Search terms must be provided as a list",
            field="search_terms",
            value=type(search_terms).__name__
        )
    
    if len(search_terms) > 50:  # Reasonable limit
        raise ValidationError(
            "Too many search terms. Maximum is 50",
            field="search_terms",
            value=len(search_terms)
        )
    
    for i, term in enumerate(search_terms):
        if not isinstance(term, str):
            raise ValidationError(
                f"Search term at index {i} must be a string",
                field="search_terms",
                value=f"index {i}: {type(term).__name__}"
            )
        
        if not term.strip():
            raise ValidationError(
                f"Search term at index {i} cannot be empty",
                field="search_terms",
                value=f"index {i}: empty string"
            )
        
        if len(term) > 500:  # Reasonable term length limit
            raise ValidationError(
                f"Search term at index {i} is too long (max 500 characters)",
                field="search_terms",
                value=f"index {i}: {len(term)} characters"
            )


def validate_page_numbers(
    page_numbers: List[int], 
    total_pages: Optional[int] = None,
    allow_duplicates: bool = False,
    require_ascending: bool = True
) -> Dict[str, Any]:
    """Enhanced validation for page numbers with additional options.
    
    Args:
        page_numbers: List of page numbers to validate
        total_pages: Total pages in document (for range checking)
        allow_duplicates: Whether to allow duplicate page numbers
        require_ascending: Whether page numbers must be in ascending order
        
    Returns:
        Dictionary with validation results
        
    Raises:
        ValidationError: If page numbers are invalid
    """
    if not isinstance(page_numbers, list):
        raise ValidationError(
            "Page numbers must be provided as a list",
            field="page_numbers",
            value=type(page_numbers).__name__
        )
    
    if not page_numbers:
        raise ValidationError("At least one page number is required")
    
    # Validate maximum number of split points
    if len(page_numbers) > 100:
        raise ValidationError(
            "Too many page numbers (maximum 100)",
            field="page_numbers",
            value=len(page_numbers)
        )
    
    for i, page_num in enumerate(page_numbers):
        if not isinstance(page_num, int):
            raise ValidationError(
                f"Page number at index {i} must be an integer",
                field="page_numbers",
                value=f"index {i}: {type(page_num).__name__}"
            )
        
        if page_num < 1:
            raise ValidationError(
                f"Page number at index {i} must be positive (1-based)",
                field="page_numbers", 
                value=f"index {i}: {page_num}"
            )
        
        if total_pages and page_num > total_pages:
            raise ValidationError(
                f"Page number at index {i} exceeds document length ({total_pages} pages)",
                field="page_numbers",
                value=f"index {i}: {page_num} > {total_pages}"
            )
    
    # Check for duplicates
    unique_pages = set(page_numbers)
    if not allow_duplicates and len(unique_pages) != len(page_numbers):
        duplicates = [page for page in unique_pages if page_numbers.count(page) > 1]
        raise ValidationError(
            f"Duplicate page numbers found: {duplicates}",
            field="page_numbers",
            value=duplicates
        )
    
    # Check for ascending order
    if require_ascending and page_numbers != sorted(page_numbers):
        raise ValidationError(
            "Page numbers must be in ascending order",
            field="page_numbers",
            value=page_numbers
        )
    
    # Additional validation for split boundaries
    if total_pages:
        # Can't split on page 1 (would create empty first section)
        if 1 in page_numbers:
            raise ValidationError(
                "Cannot split on page 1 (would create empty section)",
                field="page_numbers",
                value="page 1 in split points"
            )
    
    return {
        'valid': True,
        'page_count': len(page_numbers),
        'unique_pages': len(unique_pages),
        'is_sorted': page_numbers == sorted(page_numbers),
        'has_duplicates': len(unique_pages) != len(page_numbers)
    }


def validate_split_pattern(pattern: str, pattern_type: str) -> Dict[str, Any]:
    """Validate pattern for pattern-based PDF splitting.
    
    Args:
        pattern: Text pattern to validate
        pattern_type: Type of pattern matching ('regex', 'fuzzy', 'exact')
        
    Returns:
        Dictionary with validation results
        
    Raises:
        ValidationError: If pattern is invalid
    """
    if not pattern:
        return {
            'valid': False,
            'error': 'Pattern cannot be empty',
            'pattern_type': pattern_type
        }
    
    if not isinstance(pattern, str):
        return {
            'valid': False,
            'error': 'Pattern must be a string',
            'pattern_type': pattern_type
        }
    
    # Check pattern length
    if len(pattern) < 1 or len(pattern) > 1000:
        return {
            'valid': False,
            'error': 'Pattern must be between 1 and 1000 characters',
            'pattern_length': len(pattern)
        }
    
    # Validate pattern type
    valid_types = ['regex', 'fuzzy', 'exact']
    if pattern_type not in valid_types:
        return {
            'valid': False,
            'error': f'Pattern type must be one of: {", ".join(valid_types)}',
            'pattern_type': pattern_type
        }
    
    # Type-specific validation
    if pattern_type == 'regex':
        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            
            # Check for potentially dangerous regex patterns
            dangerous_patterns = [
                r'.*\*.*\*',  # Nested quantifiers
                r'\((.*\|.*){10,}\)',  # Too many alternations
                r'(\w+\+){5,}',  # Excessive repetition
            ]
            
            for dangerous in dangerous_patterns:
                if re.search(dangerous, pattern):
                    return {
                        'valid': False,
                        'error': 'Pattern may cause excessive backtracking (potentially dangerous)',
                        'pattern_type': pattern_type,
                        'complexity': 'high'
                    }
            
            # Calculate pattern complexity
            complexity_score = 0
            complexity_score += len(re.findall(r'[\*\+\?\{\}]', pattern))  # Quantifiers
            complexity_score += len(re.findall(r'[\(\)\[\]\|]', pattern))   # Groups and alternations
            complexity_score += len(re.findall(r'\\[dwsWDS]', pattern))     # Character classes
            
            complexity = 'low' if complexity_score < 5 else 'medium' if complexity_score < 15 else 'high'
            
            return {
                'valid': True,
                'pattern_type': pattern_type,
                'compiled_pattern': compiled_pattern.pattern,
                'complexity': complexity,
                'complexity_score': complexity_score
            }
            
        except re.error as e:
            return {
                'valid': False,
                'error': f'Invalid regex pattern: {str(e)}',
                'pattern_type': pattern_type
            }
    
    elif pattern_type == 'fuzzy':
        # For fuzzy patterns, check they contain meaningful text
        if not re.search(r'[a-zA-Z0-9]', pattern):
            return {
                'valid': False,
                'error': 'Fuzzy pattern must contain at least some alphanumeric characters',
                'pattern_type': pattern_type
            }
        
        # Test fuzzy matching capability
        test_ratio = fuzz.ratio(pattern.lower(), pattern.lower())
        if test_ratio != 100:
            return {
                'valid': False,
                'error': 'Fuzzy pattern validation failed',
                'pattern_type': pattern_type
            }
        
        return {
            'valid': True,
            'pattern_type': pattern_type,
            'pattern_length': len(pattern),
            'word_count': len(pattern.split())
        }
    
    elif pattern_type == 'exact':
        # For exact patterns, just ensure they're meaningful
        if pattern.strip() != pattern:
            return {
                'valid': False,
                'error': 'Exact pattern should not have leading/trailing whitespace',
                'pattern_type': pattern_type
            }
        
        return {
            'valid': True,
            'pattern_type': pattern_type,
            'pattern_length': len(pattern),
            'is_case_sensitive': pattern != pattern.lower()
        }
    
    return {
        'valid': True,
        'pattern_type': pattern_type
    }


def validate_merge_parameters(
    document_ids: List[str], 
    merge_strategy: str, 
    custom_order: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Validate parameters for PDF merging operations.
    
    Args:
        document_ids: List of document UUIDs to merge
        merge_strategy: Strategy for merging ('sequential', 'aggregate', 'custom')
        custom_order: Custom order for documents (required if strategy is 'custom')
        
    Returns:
        Dictionary with validation results
        
    Raises:
        ValidationError: If parameters are invalid
    """
    if not document_ids or not isinstance(document_ids, list):
        return {
            'valid': False,
            'error': 'Document IDs must be provided as a non-empty list'
        }
    
    if len(document_ids) < 2:
        return {
            'valid': False,
            'error': 'At least 2 documents are required for merging'
        }
    
    if len(document_ids) > 20:
        return {
            'valid': False,
            'error': 'Too many documents for merging (maximum 20)'
        }
    
    # Validate all document IDs are strings and appear to be UUIDs
    import uuid
    for i, doc_id in enumerate(document_ids):
        if not isinstance(doc_id, str):
            return {
                'valid': False,
                'error': f'Document ID at index {i} must be a string'
            }
        
        try:
            uuid.UUID(doc_id)
        except ValueError:
            return {
                'valid': False,
                'error': f'Document ID at index {i} is not a valid UUID'
            }
    
    # Check for duplicate document IDs
    unique_ids = set(document_ids)
    if len(unique_ids) != len(document_ids):
        duplicates = [doc_id for doc_id in unique_ids if document_ids.count(doc_id) > 1]
        return {
            'valid': False,
            'error': f'Duplicate document IDs found: {duplicates[:3]}...'
        }
    
    # Validate merge strategy
    valid_strategies = ['sequential', 'aggregate', 'custom']
    if merge_strategy not in valid_strategies:
        return {
            'valid': False,
            'error': f'Merge strategy must be one of: {", ".join(valid_strategies)}'
        }
    
    # Validate custom order if strategy is custom
    if merge_strategy == 'custom':
        if not custom_order or not isinstance(custom_order, list):
            return {
                'valid': False,
                'error': 'Custom order must be provided as a list when merge strategy is "custom"'
            }
        
        if len(custom_order) != len(document_ids):
            return {
                'valid': False,
                'error': 'Custom order must contain all document IDs'
            }
        
        if set(custom_order) != set(document_ids):
            return {
                'valid': False,
                'error': 'Custom order must contain exactly the same document IDs as provided'
            }
    
    return {
        'valid': True,
        'document_count': len(document_ids),
        'unique_documents': len(unique_ids),
        'merge_strategy': merge_strategy,
        'has_custom_order': custom_order is not None
    }


def validate_processing_limits(
    operation_type: str, 
    file_count: int, 
    total_size: int
) -> Dict[str, Any]:
    """Validate operation doesn't exceed system resource limits.
    
    Args:
        operation_type: Type of operation ('split', 'merge', 'extract')
        file_count: Number of files involved
        total_size: Total size in bytes
        
    Returns:
        Dictionary with validation results and resource analysis
        
    Raises:
        ValidationError: If limits are exceeded
    """
    # Define limits based on operation type
    limits = {
        'split': {
            'max_file_size': 50 * 1024 * 1024,  # 50MB
            'max_files': 1,
            'max_split_points': 100
        },
        'merge': {
            'max_file_size': 50 * 1024 * 1024,  # 50MB per file
            'max_total_size': 100 * 1024 * 1024,  # 100MB total
            'max_files': 20
        },
        'extract': {
            'max_file_size': 100 * 1024 * 1024,  # 100MB
            'max_files': 1
        }
    }
    
    if operation_type not in limits:
        return {
            'valid': False,
            'error': f'Unknown operation type: {operation_type}'
        }
    
    operation_limits = limits[operation_type]
    
    # Check file count limits
    if file_count > operation_limits.get('max_files', float('inf')):
        return {
            'valid': False,
            'error': f'Too many files for {operation_type} operation (max {operation_limits["max_files"]})',
            'file_count': file_count,
            'limit': operation_limits['max_files']
        }
    
    # Check individual file size limits
    if operation_type in ['split', 'extract']:
        if total_size > operation_limits['max_file_size']:
            return {
                'valid': False,
                'error': f'File too large for {operation_type} operation (max {operation_limits["max_file_size"]/(1024*1024):.0f}MB)',
                'file_size_mb': total_size / (1024 * 1024),
                'limit_mb': operation_limits['max_file_size'] / (1024 * 1024)
            }
    
    # Check total size limits for merge operations
    if operation_type == 'merge':
        if total_size > operation_limits['max_total_size']:
            return {
                'valid': False,
                'error': f'Total file size too large for merge (max {operation_limits["max_total_size"]/(1024*1024):.0f}MB)',
                'total_size_mb': total_size / (1024 * 1024),
                'limit_mb': operation_limits['max_total_size'] / (1024 * 1024)
            }
    
    # Calculate resource usage analysis
    resource_analysis = {
        'estimated_memory_mb': (total_size / (1024 * 1024)) * 2,  # Rough estimate
        'estimated_processing_time': _estimate_processing_time(operation_type, total_size, file_count),
        'resource_efficiency': 'high' if total_size < 10*1024*1024 else 'medium' if total_size < 50*1024*1024 else 'low'
    }
    
    return {
        'valid': True,
        'operation_type': operation_type,
        'file_count': file_count,
        'total_size_mb': total_size / (1024 * 1024),
        'resource_analysis': resource_analysis,
        'recommendations': _generate_processing_recommendations(operation_type, total_size, file_count)
    }


def _estimate_processing_time(operation_type: str, total_size: int, file_count: int) -> int:
    """Estimate processing time in seconds."""
    base_times = {
        'split': 5,
        'merge': 10,
        'extract': 15
    }
    
    base_time = base_times.get(operation_type, 10)
    size_factor = (total_size / (1024 * 1024)) * 0.5  # 0.5 seconds per MB
    file_factor = file_count * 2  # 2 seconds per file
    
    return int(base_time + size_factor + file_factor)


def _generate_processing_recommendations(operation_type: str, total_size: int, file_count: int) -> List[str]:
    """Generate processing recommendations based on file characteristics."""
    recommendations = []
    
    size_mb = total_size / (1024 * 1024)
    
    if size_mb > 50:
        recommendations.append("Consider using background processing for large files")
    
    if file_count > 10:
        recommendations.append("Large number of files may increase processing time")
    
    if operation_type == 'merge' and size_mb > 75:
        recommendations.append("Consider optimizing PDFs before merging to reduce size")
    
    if operation_type == 'split' and size_mb > 25:
        recommendations.append("Pattern-based splitting may be slower for large documents")
    
    return recommendations


def validate_file_integrity(file_path: Path, expected_hash: Optional[str] = None) -> Dict[str, Any]:
    """Calculate and verify file integrity.
    
    Args:
        file_path: Path to file
        expected_hash: Expected SHA-256 hash (optional)
        
    Returns:
        Dictionary with integrity information
        
    Raises:
        FileError: If file operations fail
    """
    try:
        if not file_path.exists():
            return {
                'valid': False,
                'error': 'File does not exist',
                'file_path': str(file_path)
            }
        
        file_size = file_path.stat().st_size
        if file_size == 0:
            return {
                'valid': False,
                'error': 'File is empty',
                'file_size': 0
            }
        
        # Calculate SHA-256 hash
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        calculated_hash = sha256_hash.hexdigest()
        
        result = {
            'valid': True,
            'file_path': str(file_path),
            'file_size': file_size,
            'sha256_hash': calculated_hash
        }
        
        # Verify against expected hash if provided
        if expected_hash:
            hash_matches = calculated_hash == expected_hash
            result.update({
                'expected_hash': expected_hash,
                'hash_matches': hash_matches,
                'valid': hash_matches
            })
            
            if not hash_matches:
                result['error'] = 'File integrity check failed (hash mismatch)'
        
        return result
        
    except Exception as e:
        return {
            'valid': False,
            'error': f'Integrity check failed: {str(e)}',
            'file_path': str(file_path)
        }