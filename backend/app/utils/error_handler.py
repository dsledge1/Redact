"""Error handling utilities for the PDF processing application."""

import logging
import functools
from typing import Any, Callable, Optional
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def handle_errors(default_return=None):
    """Decorator for handling errors in service methods.
    
    Args:
        default_return: Default value to return on error
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
                
                # If it's a view function, return JsonResponse
                if 'request' in kwargs or (args and hasattr(args[0], 'META')):
                    return JsonResponse(
                        {'error': str(e), 'status': 'error'}, 
                        status=500
                    )
                
                # Otherwise, return default value
                return default_return
        
        return wrapper
    return decorator


class PDFProcessingError(Exception):
    """Base exception for PDF processing errors."""
    pass


class ValidationError(PDFProcessingError):
    """Exception for validation errors."""
    pass


class ExtractionError(PDFProcessingError):
    """Exception for text extraction errors."""
    pass


class RedactionError(PDFProcessingError):
    """Exception for redaction errors."""
    pass


class MergeError(PDFProcessingError):
    """Exception for merge errors."""
    pass


class SplitError(PDFProcessingError):
    """Exception for split errors."""
    pass


class OCRError(PDFProcessingError):
    """Exception for OCR processing errors."""
    pass


def log_error(error: Exception, context: Optional[dict] = None):
    """Log an error with context.
    
    Args:
        error: Exception to log
        context: Additional context information
    """
    error_info = {
        'error_type': type(error).__name__,
        'error_message': str(error),
    }
    
    if context:
        error_info.update(context)
    
    logger.error(f"Error occurred: {error_info}", exc_info=error)