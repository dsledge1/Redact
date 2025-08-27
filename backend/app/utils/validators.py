"""File validation utilities for Ultimate PDF application."""

import mimetypes
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings

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


def validate_page_numbers(page_numbers: List[int], total_pages: Optional[int] = None) -> None:
    """Validate page numbers for PDF operations.
    
    Args:
        page_numbers: List of page numbers to validate
        total_pages: Total pages in document (for range checking)
        
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
    if len(unique_pages) != len(page_numbers):
        duplicates = [page for page in unique_pages if page_numbers.count(page) > 1]
        raise ValidationError(
            f"Duplicate page numbers found: {duplicates}",
            field="page_numbers",
            value=duplicates
        )