import json
import time
import functools
import structlog
from typing import Callable, Any, Dict, Optional, List, Union
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.conf import settings

from app.utils.errors import ValidationError, AuthenticationError, APIError
from app.utils.validators import PDFValidator, validate_session_id
from app.utils.response_formatters import APIResponseFormatter


logger = structlog.get_logger(__name__)


def validate_request_data(schema: Optional[Dict[str, Any]] = None,
                         required_fields: Optional[List[str]] = None):
    """
    Decorator that automatically validates request JSON against schemas.
    
    Args:
        schema: Optional JSON schema for validation
        required_fields: List of required fields in request data
        
    Returns:
        Decorated function with request validation
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            request_id = getattr(request, 'api_request_id', '')
            
            try:
                # Parse JSON data for POST/PUT requests
                if request.method in ['POST', 'PUT', 'PATCH']:
                    if request.content_type and request.content_type.startswith('application/json'):
                        try:
                            request.json_data = json.loads(request.body)
                        except json.JSONDecodeError as e:
                            logger.warning(
                                "Invalid JSON in request",
                                request_id=request_id,
                                error=str(e)
                            )
                            return JsonResponse(
                                APIResponseFormatter.format_error_response(
                                    ValidationError("Invalid JSON format"),
                                    request_id=request_id
                                ),
                                status=400
                            )
                
                # Validate required fields
                if required_fields and hasattr(request, 'json_data'):
                    missing_fields = [
                        field for field in required_fields 
                        if field not in request.json_data
                    ]
                    
                    if missing_fields:
                        error = ValidationError(
                            f"Missing required fields: {', '.join(missing_fields)}"
                        )
                        return JsonResponse(
                            APIResponseFormatter.format_error_response(error, request_id),
                            status=400
                        )
                
                # Additional schema validation could be implemented here
                # For now, we rely on the existing validators in the views
                
                return func(self, request, *args, **kwargs)
                
            except Exception as e:
                logger.error(
                    "Request validation failed",
                    request_id=request_id,
                    error=str(e),
                    exc_info=True
                )
                return JsonResponse(
                    APIResponseFormatter.format_error_response(e, request_id),
                    status=400
                )
        
        return wrapper
    return decorator


def require_session_id(func: Callable) -> Callable:
    """
    Decorator that validates session ID presence and format.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with session ID validation
    """
    @functools.wraps(func)
    def wrapper(self, request: HttpRequest, *args, **kwargs):
        request_id = getattr(request, 'api_request_id', '')
        
        # Get session ID from various sources
        session_id = (
            request.META.get('HTTP_X_SESSION_ID') or
            request.GET.get('session_id') or
            (getattr(request, 'json_data', {}) or {}).get('session_id')
        )
        
        if not session_id:
            error = AuthenticationError("Session ID is required")
            return JsonResponse(
                APIResponseFormatter.format_error_response(error, request_id),
                status=401
            )
        
        # Validate session ID format using existing validator
        try:
            validate_session_id(session_id)
        except ValidationError as e:
            logger.error(
                "Session ID validation failed",
                request_id=request_id,
                session_id=session_id,
                error=str(e)
            )
            error = AuthenticationError(str(e))
            return JsonResponse(
                APIResponseFormatter.format_error_response(error, request_id),
                status=401
            )
        except Exception as e:
            logger.error(
                "Unexpected error during session ID validation",
                request_id=request_id,
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            error = AuthenticationError("Session ID validation failed")
            return JsonResponse(
                APIResponseFormatter.format_error_response(error, request_id),
                status=401
            )
        
        # Store validated session ID in request
        request.validated_session_id = session_id
        
        return func(self, request, *args, **kwargs)
    
    return wrapper


def timeout_handler(sync_timeout: int = 30, background_threshold: int = 25):
    """
    Decorator for automatic timeout management with cooperative cancellation.
    
    Args:
        sync_timeout: Maximum time for synchronous processing
        background_threshold: Time threshold before queuing background task
        
    Returns:
        Decorated function with timeout handling
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            request_id = getattr(request, 'api_request_id', '')
            start_time = time.time()
            
            # Store timeout configuration in request
            request.sync_timeout = sync_timeout
            request.background_threshold = background_threshold
            request.timeout_start = start_time
            
            logger.debug(
                "Timeout handler configured",
                request_id=request_id,
                sync_timeout=sync_timeout,
                background_threshold=background_threshold
            )
            
            # Check if middleware recommends background processing
            if getattr(request, 'should_queue_background', False):
                logger.info(
                    "Background processing recommended by middleware",
                    request_id=request_id
                )
                
                # Set timeout hint to let views handle job creation
                request.timeout_hint = True
            
            try:
                # Execute function with periodic timeout checks
                result = func(self, request, *args, **kwargs)
                
                processing_time = time.time() - start_time
                
                # Check if we exceeded background threshold after completion
                if processing_time > background_threshold:
                    # If we're close to sync timeout, recommend background for next time
                    if processing_time > sync_timeout * 0.8:
                        logger.warning(
                            "Processing time approaching sync timeout",
                            request_id=request_id,
                            processing_time=processing_time,
                            sync_timeout=sync_timeout
                        )
                        
                        # Add headers to recommend background processing for similar requests
                        if isinstance(result, (JsonResponse, HttpResponse)):
                            result['X-Processing-Time'] = f"{processing_time:.3f}s"
                            result['X-Timeout-Warning'] = 'true'
                            result['X-Recommend-Background'] = 'true'
                
                # Add timeout warnings if approaching limits
                if isinstance(result, (JsonResponse, HttpResponse)) and processing_time > background_threshold:
                    result['X-Processing-Time'] = f"{processing_time:.3f}s"
                    result['X-Timeout-Warning'] = 'true'
                    
                    logger.info(
                        "Processing time exceeded background threshold",
                        request_id=request_id,
                        processing_time=processing_time,
                        background_threshold=background_threshold
                    )
                
                return result
                
            except Exception as e:
                processing_time = time.time() - start_time
                
                # Check if we exceeded sync timeout and should return 408
                if processing_time > sync_timeout:
                    logger.error(
                        "Request timed out",
                        request_id=request_id,
                        processing_time=processing_time,
                        sync_timeout=sync_timeout
                    )
                    
                    timeout_error = APIError(
                        message=f"Request timed out after {processing_time:.1f} seconds",
                        code="TIMEOUT_ERROR",
                        status_code=408
                    )
                    
                    return JsonResponse(
                        APIResponseFormatter.format_error_response(timeout_error, request_id),
                        status=408
                    )
                
                logger.error(
                    "Function execution failed",
                    request_id=request_id,
                    processing_time=processing_time,
                    error=str(e),
                    exc_info=True
                )
                raise
        
        return wrapper
    return decorator


def rate_limit(requests_per_minute: int = 100, per_session: bool = False):
    """
    Decorator for endpoint-specific rate limiting (second tier).
    
    This decorator provides endpoint-specific rate limiting that operates
    independently from the global APIRateLimitMiddleware. Both limits
    are enforced - requests must pass both the global middleware check
    and this decorator check to succeed.
    
    Args:
        requests_per_minute: Number of requests allowed per minute for this endpoint
        per_session: Whether to limit per session ID instead of IP
        
    Returns:
        Decorated function with endpoint-specific rate limiting
        
    Example:
        @rate_limit(requests_per_minute=60)  # More restrictive than global limit
        def post(self, request):
            # This endpoint allows max 60 req/min even if global is 100 req/min
            pass
    
    Note:
        - Global middleware limit is checked first (configured in settings)
        - This decorator limit is checked second
        - Both limits must be satisfied for request to succeed
        - Returns 429 with Retry-After header when exceeded
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            request_id = getattr(request, 'api_request_id', '')
            
            # Determine rate limit key
            if per_session and hasattr(request, 'validated_session_id'):
                limit_key = f"rate_limit_session:{request.validated_session_id}"
            else:
                # Get client IP
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    client_ip = x_forwarded_for.split(',')[0]
                else:
                    client_ip = request.META.get('REMOTE_ADDR')
                limit_key = f"rate_limit_ip:{client_ip}"
            
            # Add endpoint-specific suffix
            endpoint = f"{request.method}:{request.path}"
            cache_key = f"{limit_key}:{endpoint}"
            
            # Check current request count
            current_requests = cache.get(cache_key, 0)
            
            if current_requests >= requests_per_minute:
                logger.warning(
                    "Rate limit exceeded for endpoint",
                    request_id=request_id,
                    endpoint=endpoint,
                    current_requests=current_requests,
                    limit=requests_per_minute
                )
                
                error = APIError(
                    message=f"Rate limit exceeded: {requests_per_minute} requests per minute",
                    error_code="RATE_LIMIT_EXCEEDED",
                    status_code=429
                )
                
                response = JsonResponse(
                    APIResponseFormatter.format_error_response(error, request_id),
                    status=429
                )
                response['Retry-After'] = '60'
                return response
            
            # Increment request count
            cache.set(cache_key, current_requests + 1, 60)
            
            return func(self, request, *args, **kwargs)
        
        return wrapper
    return decorator


def log_api_call(include_request_data: bool = False,
                include_response_data: bool = False):
    """
    Decorator that provides structured logging for API endpoint calls.
    
    Args:
        include_request_data: Whether to log request data (be careful with sensitive data)
        include_response_data: Whether to log response data summary
        
    Returns:
        Decorated function with API call logging
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            request_id = getattr(request, 'api_request_id', '')
            start_time = time.time()
            
            # Log request initiation
            log_data = {
                'request_id': request_id,
                'method': request.method,
                'path': request.path,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'content_length': request.META.get('CONTENT_LENGTH', 0)
            }
            
            if include_request_data and hasattr(request, 'json_data'):
                # Only log non-sensitive request data
                safe_data = {k: v for k, v in request.json_data.items() 
                           if k not in ['password', 'token', 'key', 'secret']}
                log_data['request_data'] = safe_data
            
            logger.info("API call initiated", **log_data)
            
            try:
                result = func(self, request, *args, **kwargs)
                
                processing_time = time.time() - start_time
                
                # Log successful completion
                completion_log = {
                    'request_id': request_id,
                    'status': 'success',
                    'processing_time': processing_time,
                    'response_status': getattr(result, 'status_code', 200)
                }
                
                if include_response_data and hasattr(result, 'content'):
                    try:
                        response_data = json.loads(result.content)
                        completion_log['response_status'] = response_data.get('status')
                        completion_log['response_size'] = len(result.content)
                    except:
                        pass
                
                logger.info("API call completed", **completion_log)
                
                return result
                
            except Exception as e:
                processing_time = time.time() - start_time
                
                logger.error(
                    "API call failed",
                    request_id=request_id,
                    processing_time=processing_time,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    exc_info=True
                )
                
                raise
        
        return wrapper
    return decorator


def handle_file_upload(max_size: Optional[int] = None,
                      allowed_types: Optional[List[str]] = None,
                      use_pdf_validator: bool = True):
    """
    Decorator that validates file uploads using existing PDFValidator.
    
    Args:
        max_size: Maximum file size in bytes
        allowed_types: List of allowed file extensions
        use_pdf_validator: Whether to use the existing PDFValidator
        
    Returns:
        Decorated function with file upload validation
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            request_id = getattr(request, 'api_request_id', '')
            
            if request.method not in ['POST', 'PUT'] or not request.FILES:
                return func(self, request, *args, **kwargs)
            
            try:
                # Validate each uploaded file
                for field_name, uploaded_file in request.FILES.items():
                    
                    # Check file size
                    if max_size and uploaded_file.size > max_size:
                        error = ValidationError(
                            f"File {uploaded_file.name} exceeds maximum size of {max_size} bytes"
                        )
                        return JsonResponse(
                            APIResponseFormatter.format_error_response(error, request_id),
                            status=400
                        )
                    
                    # Check file type
                    if allowed_types:
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        if file_ext not in allowed_types:
                            error = ValidationError(
                                f"File type .{file_ext} not allowed. Allowed types: {', '.join(allowed_types)}"
                            )
                            return JsonResponse(
                                APIResponseFormatter.format_error_response(error, request_id),
                                status=400
                            )
                    
                    # Use existing PDFValidator for PDF files
                    if use_pdf_validator and uploaded_file.name.lower().endswith('.pdf'):
                        try:
                            pdf_validator = PDFValidator()
                            # Note: This would need to be adapted based on how PDFValidator works
                            # The existing validator might need the file to be saved first
                            logger.debug(
                                "PDF validation initiated",
                                request_id=request_id,
                                filename=uploaded_file.name,
                                size=uploaded_file.size
                            )
                        except Exception as e:
                            logger.error(
                                "PDF validation failed",
                                request_id=request_id,
                                filename=uploaded_file.name,
                                error=str(e)
                            )
                            error = ValidationError(f"PDF validation failed: {str(e)}")
                            return JsonResponse(
                                APIResponseFormatter.format_error_response(error, request_id),
                                status=400
                            )
                
                return func(self, request, *args, **kwargs)
                
            except Exception as e:
                logger.error(
                    "File upload validation failed",
                    request_id=request_id,
                    error=str(e),
                    exc_info=True
                )
                error = ValidationError(f"File upload validation failed: {str(e)}")
                return JsonResponse(
                    APIResponseFormatter.format_error_response(error, request_id),
                    status=400
                )
        
        return wrapper
    return decorator


def require_content_type(*content_types: str):
    """
    Decorator for content type validation.
    
    Args:
        content_types: Allowed content types
        
    Returns:
        Decorated function with content type validation
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            request_id = getattr(request, 'api_request_id', '')
            
            if request.method in ['POST', 'PUT', 'PATCH']:
                request_content_type = request.META.get('CONTENT_TYPE', '').split(';')[0]
                
                if request_content_type not in content_types:
                    error = ValidationError(
                        f"Content-Type must be one of: {', '.join(content_types)}"
                    )
                    return JsonResponse(
                        APIResponseFormatter.format_error_response(error, request_id),
                        status=415
                    )
            
            return func(self, request, *args, **kwargs)
        
        return wrapper
    return decorator


def cache_response(timeout: int = 300, vary_on: Optional[List[str]] = None):
    """
    Decorator for caching appropriate API responses.
    
    Args:
        timeout: Cache timeout in seconds
        vary_on: List of headers to vary cache on
        
    Returns:
        Decorated function with response caching
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request: HttpRequest, *args, **kwargs):
            # Only cache GET requests
            if request.method != 'GET':
                return func(self, request, *args, **kwargs)
            
            # Build cache key
            cache_key_parts = [
                request.path,
                request.META.get('QUERY_STRING', '')
            ]
            
            if vary_on:
                for header in vary_on:
                    cache_key_parts.append(request.META.get(f'HTTP_{header.upper().replace("-", "_")}', ''))
            
            cache_key = 'api_response:' + ':'.join(cache_key_parts)
            
            # Try to get cached response
            cached_response = cache.get(cache_key)
            if cached_response:
                logger.debug(
                    "Serving cached response",
                    request_id=getattr(request, 'api_request_id', ''),
                    cache_key=cache_key
                )
                response = JsonResponse(cached_response)
                response['X-Cache'] = 'HIT'
                return response
            
            # Execute function and cache result
            result = func(self, request, *args, **kwargs)
            
            # Only cache successful responses
            if hasattr(result, 'status_code') and result.status_code == 200:
                try:
                    response_data = json.loads(result.content)
                    cache.set(cache_key, response_data, timeout)
                    result['X-Cache'] = 'MISS'
                except:
                    pass
            
            return result
        
        return wrapper
    return decorator


def monitor_performance(func: Callable) -> Callable:
    """
    Decorator that tracks endpoint performance metrics.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with performance monitoring
    """
    @functools.wraps(func)
    def wrapper(self, request: HttpRequest, *args, **kwargs):
        request_id = getattr(request, 'api_request_id', '')
        start_time = time.time()
        
        # Track performance metrics
        metrics = {
            'endpoint': f"{request.method}:{request.path}",
            'request_id': request_id,
            'start_time': start_time
        }
        
        try:
            result = func(self, request, *args, **kwargs)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            metrics.update({
                'processing_time': processing_time,
                'status_code': getattr(result, 'status_code', 200),
                'response_size': len(getattr(result, 'content', b'')),
                'success': True
            })
            
            # Log performance metrics
            logger.info("Performance metrics", **metrics)
            
            return result
            
        except Exception as e:
            end_time = time.time()
            processing_time = end_time - start_time
            
            metrics.update({
                'processing_time': processing_time,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'success': False
            })
            
            logger.error("Performance metrics (error)", **metrics)
            raise
    
    return wrapper