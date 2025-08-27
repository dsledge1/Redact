"""Error handling utilities for Ultimate PDF application."""

from typing import Dict, Any, Optional
from rest_framework import status
import structlog

logger = structlog.get_logger(__name__)


class APIError(Exception):
    """Custom exception class for API errors with structured error information."""
    
    def __init__(
        self, 
        message: str, 
        code: str, 
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize API error.
        
        Args:
            message: Human-readable error message
            code: Unique error code for programmatic handling
            status_code: HTTP status code (default 400)
            details: Additional error details dictionary
        """
        self.message = message
        self.code = code
        self.status = status_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format for API responses.
        
        Returns:
            Dictionary with error information
        """
        error_dict = {
            'success': False,
            'error': {
                'message': self.message,
                'code': self.code,
                'status': self.status
            }
        }
        
        if self.details:
            error_dict['error']['details'] = self.details
        
        return error_dict
    
    def log_error(self, context: Optional[Dict[str, Any]] = None) -> None:
        """Log the error with structured logging.
        
        Args:
            context: Additional context for logging
        """
        log_data = {
            'error_code': self.code,
            'error_message': self.message,
            'status_code': self.status,
            'error_details': self.details
        }
        
        if context:
            log_data.update(context)
        
        logger.error("API Error occurred", **log_data)


class ValidationError(APIError):
    """Specialized error for validation failures."""
    
    def __init__(
        self, 
        message: str, 
        field: Optional[str] = None, 
        value: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize validation error.
        
        Args:
            message: Validation error message
            field: Field name that failed validation
            value: Invalid value that was provided
            details: Additional validation details
        """
        if not details:
            details = {}
        
        if field:
            details['field'] = field
        
        if value is not None:
            details['invalid_value'] = str(value)
        
        super().__init__(
            message=message,
            code='VALIDATION_ERROR',
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )
        
        self.field = field
        self.value = value


class ProcessingError(APIError):
    """Specialized error for processing failures."""
    
    def __init__(
        self,
        message: str,
        processing_stage: str,
        job_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize processing error.
        
        Args:
            message: Processing error message
            processing_stage: Stage where processing failed
            job_id: Job ID if applicable
            details: Additional processing details
        """
        if not details:
            details = {}
        
        details['processing_stage'] = processing_stage
        
        if job_id:
            details['job_id'] = job_id
        
        super().__init__(
            message=message,
            code='PROCESSING_ERROR',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )
        
        self.processing_stage = processing_stage
        self.job_id = job_id


class FileError(APIError):
    """Specialized error for file-related operations."""
    
    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize file error.
        
        Args:
            message: File error message
            file_path: Path to file that caused error
            operation: File operation that failed
            details: Additional file operation details
        """
        if not details:
            details = {}
        
        if file_path:
            details['file_path'] = file_path
        
        if operation:
            details['operation'] = operation
        
        super().__init__(
            message=message,
            code='FILE_ERROR',
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )
        
        self.file_path = file_path
        self.operation = operation


# Predefined error mappings for common scenarios
ERROR_MAPPINGS = {
    'MISSING_FILE': APIError(
        message="No file was provided in the request",
        code="MISSING_FILE",
        status_code=status.HTTP_400_BAD_REQUEST
    ),
    
    'INVALID_FILE_TYPE': APIError(
        message="Invalid file type. Only PDF files are allowed",
        code="INVALID_FILE_TYPE", 
        status_code=status.HTTP_400_BAD_REQUEST
    ),
    
    'FILE_TOO_LARGE': APIError(
        message="File size exceeds the maximum allowed limit of 100MB",
        code="FILE_TOO_LARGE",
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    ),
    
    'DOCUMENT_NOT_FOUND': APIError(
        message="The requested document was not found",
        code="DOCUMENT_NOT_FOUND",
        status_code=status.HTTP_404_NOT_FOUND
    ),
    
    'JOB_NOT_FOUND': APIError(
        message="The requested processing job was not found", 
        code="JOB_NOT_FOUND",
        status_code=status.HTTP_404_NOT_FOUND
    ),
    
    'UPLOAD_ERROR': APIError(
        message="Failed to upload file. Please try again",
        code="UPLOAD_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'PROCESSING_ERROR': APIError(
        message="An error occurred during PDF processing",
        code="PROCESSING_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'OCR_ERROR': APIError(
        message="OCR processing failed for this document",
        code="OCR_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'FUZZY_MATCH_ERROR': APIError(
        message="Fuzzy matching failed for the provided search terms",
        code="FUZZY_MATCH_ERROR", 
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'REDACTION_ERROR': APIError(
        message="PDF redaction failed. Please check your input and try again",
        code="REDACTION_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'SPLIT_ERROR': APIError(
        message="PDF splitting failed. Please verify the page numbers and try again",
        code="SPLIT_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'MERGE_ERROR': APIError(
        message="PDF merging failed. Please check that all files are valid PDFs",
        code="MERGE_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'EXTRACTION_ERROR': APIError(
        message="Data extraction failed for this document",
        code="EXTRACTION_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'INVALID_PDF': APIError(
        message="The uploaded file is not a valid PDF or is corrupted",
        code="INVALID_PDF",
        status_code=status.HTTP_400_BAD_REQUEST
    ),
    
    'ENCRYPTED_PDF': APIError(
        message="Cannot process password-protected PDF files",
        code="ENCRYPTED_PDF",
        status_code=status.HTTP_400_BAD_REQUEST
    ),
    
    'MISSING_PARAMETERS': APIError(
        message="Required parameters are missing from the request",
        code="MISSING_PARAMETERS",
        status_code=status.HTTP_400_BAD_REQUEST
    ),
    
    'INVALID_SESSION': APIError(
        message="Invalid or expired session ID",
        code="INVALID_SESSION",
        status_code=status.HTTP_400_BAD_REQUEST
    ),
    
    'DISK_SPACE_ERROR': APIError(
        message="Insufficient disk space to process this file",
        code="DISK_SPACE_ERROR",
        status_code=status.HTTP_507_INSUFFICIENT_STORAGE
    ),
    
    'RATE_LIMIT_EXCEEDED': APIError(
        message="Too many requests. Please wait before trying again",
        code="RATE_LIMIT_EXCEEDED",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS
    ),
    
    'TIMEOUT_ERROR': APIError(
        message="Processing timeout. Please try with a smaller file or simpler operation",
        code="TIMEOUT_ERROR",
        status_code=status.HTTP_408_REQUEST_TIMEOUT
    ),
    
    'SERVER_ERROR': APIError(
        message="An unexpected server error occurred. Please try again later",
        code="SERVER_ERROR", 
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    ),
    
    'MAINTENANCE_MODE': APIError(
        message="Service temporarily unavailable due to maintenance",
        code="MAINTENANCE_MODE",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )
}


def format_validation_errors(errors: Dict[str, Any]) -> APIError:
    """Format Django validation errors into a structured APIError.
    
    Args:
        errors: Django form or serializer errors
        
    Returns:
        Formatted APIError with validation details
    """
    formatted_errors = {}
    
    for field, field_errors in errors.items():
        if isinstance(field_errors, list):
            formatted_errors[field] = [str(error) for error in field_errors]
        else:
            formatted_errors[field] = [str(field_errors)]
    
    return APIError(
        message="Validation failed",
        code="VALIDATION_FAILED",
        status_code=status.HTTP_400_BAD_REQUEST,
        details={'field_errors': formatted_errors}
    )


def handle_exception(exception: Exception, context: Optional[Dict[str, Any]] = None) -> APIError:
    """Convert various exception types to APIError instances.
    
    Args:
        exception: Exception to handle
        context: Additional context for error handling
        
    Returns:
        APIError instance
    """
    if isinstance(exception, APIError):
        if context:
            exception.log_error(context)
        return exception
    
    # Map common exceptions to API errors
    exception_mappings = {
        FileNotFoundError: ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'],
        PermissionError: APIError(
            message="Permission denied accessing file",
            code="PERMISSION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN
        ),
        TimeoutError: ERROR_MAPPINGS['TIMEOUT_ERROR'],
        ValueError: APIError(
            message="Invalid input value provided",
            code="INVALID_INPUT",
            status_code=status.HTTP_400_BAD_REQUEST
        ),
        TypeError: APIError(
            message="Invalid data type provided",
            code="INVALID_TYPE",
            status_code=status.HTTP_400_BAD_REQUEST
        )
    }
    
    # Check for specific exception types
    for exc_type, api_error in exception_mappings.items():
        if isinstance(exception, exc_type):
            # Create new instance with original exception message
            mapped_error = APIError(
                message=f"{api_error.message}: {str(exception)}",
                code=api_error.code,
                status_code=api_error.status,
                details={'original_exception': str(exception)}
            )
            
            if context:
                mapped_error.log_error(context)
            
            return mapped_error
    
    # Default handling for unknown exceptions
    generic_error = APIError(
        message="An unexpected error occurred",
        code="UNKNOWN_ERROR", 
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={
            'exception_type': type(exception).__name__,
            'exception_message': str(exception)
        }
    )
    
    if context:
        generic_error.log_error(context)
    
    logger.error(
        "Unhandled exception converted to APIError",
        exception_type=type(exception).__name__,
        exception_message=str(exception),
        context=context or {}
    )
    
    return generic_error


def create_success_response(data: Any = None, message: str = None) -> Dict[str, Any]:
    """Create a standardized success response.
    
    Args:
        data: Response data
        message: Success message
        
    Returns:
        Standardized success response dictionary
    """
    response = {'success': True}
    
    if data is not None:
        response['data'] = data
    
    if message:
        response['message'] = message
    
    return response


def create_error_response(error: APIError) -> Dict[str, Any]:
    """Create a standardized error response from an APIError.
    
    Args:
        error: APIError instance
        
    Returns:
        Standardized error response dictionary
    """
    return error.to_dict()


# HTTP status code helpers for quick reference
HTTP_STATUS_CODES = {
    'OK': status.HTTP_200_OK,
    'CREATED': status.HTTP_201_CREATED,
    'NO_CONTENT': status.HTTP_204_NO_CONTENT,
    'BAD_REQUEST': status.HTTP_400_BAD_REQUEST,
    'UNAUTHORIZED': status.HTTP_401_UNAUTHORIZED,
    'FORBIDDEN': status.HTTP_403_FORBIDDEN,
    'NOT_FOUND': status.HTTP_404_NOT_FOUND,
    'METHOD_NOT_ALLOWED': status.HTTP_405_METHOD_NOT_ALLOWED,
    'TIMEOUT': status.HTTP_408_REQUEST_TIMEOUT,
    'PAYLOAD_TOO_LARGE': status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    'TOO_MANY_REQUESTS': status.HTTP_429_TOO_MANY_REQUESTS,
    'INTERNAL_SERVER_ERROR': status.HTTP_500_INTERNAL_SERVER_ERROR,
    'NOT_IMPLEMENTED': status.HTTP_501_NOT_IMPLEMENTED,
    'SERVICE_UNAVAILABLE': status.HTTP_503_SERVICE_UNAVAILABLE,
    'INSUFFICIENT_STORAGE': status.HTTP_507_INSUFFICIENT_STORAGE
}