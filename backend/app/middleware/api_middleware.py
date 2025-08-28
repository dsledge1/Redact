import json
import time
import uuid
import structlog
from typing import Callable, Dict, Any, Optional
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.core.cache import cache
from django.utils.cache import get_max_age
import gzip
from io import BytesIO

from app.utils.errors import APIError, ValidationError, AuthenticationError, ERROR_MAPPINGS
from app.utils.response_formatters import APIResponseFormatter


logger = structlog.get_logger(__name__)


class APIRequestMiddleware(MiddlewareMixin):
    """
    Middleware for handling API request processing including ID generation,
    timing, and structured logging.
    """
    
    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """
        Process incoming API requests with request ID and timing.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            Optional HttpResponse if request should be rejected
        """
        if not request.path.startswith('/api/'):
            return None
            
        # Generate unique request ID
        request.api_request_id = str(uuid.uuid4())
        request.api_start_time = time.time()
        
        # Check request size limit
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length:
            try:
                content_length = int(content_length)
                max_request_size = getattr(settings, 'API_MAX_REQUEST_SIZE', 100 * 1024 * 1024)
                
                if content_length > max_request_size:
                    logger.warning(
                        "Request size exceeds limit",
                        request_id=request.api_request_id,
                        content_length=content_length,
                        max_allowed=max_request_size,
                        path=request.path
                    )
                    
                    error_response = APIResponseFormatter.format_error_response(
                        ERROR_MAPPINGS['FILE_TOO_LARGE'], 
                        request.api_request_id
                    )
                    return JsonResponse(error_response, status=413)
                    
            except (ValueError, TypeError):
                # Invalid CONTENT_LENGTH header, ignore silently
                pass
        
        # Validate required headers
        content_type = request.META.get('CONTENT_TYPE', '')
        if request.method in ['POST', 'PUT', 'PATCH']:
            allowed_types = [
                'application/json',
                'multipart/form-data',
                'application/x-www-form-urlencoded'
            ]
            
            if content_type and not any(content_type.startswith(allowed) for allowed in allowed_types):
                error = ValidationError('Content-Type must be application/json, multipart/form-data, or application/x-www-form-urlencoded')
                error_response = APIResponseFormatter.format_error_response(error, request.api_request_id)
                return JsonResponse(error_response, status=400)
        
        # Log request initiation
        logger.info(
            "API request initiated",
            request_id=request.api_request_id,
            method=request.method,
            path=request.path,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            remote_addr=self._get_client_ip(request),
            content_length=request.META.get('CONTENT_LENGTH', 0)
        )
        
        return None
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class APIResponseMiddleware(MiddlewareMixin):
    """
    Middleware for handling API response processing including security headers,
    CORS, and response formatting.
    """
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Process API responses with security headers and metadata.
        
        Args:
            request: The Django HTTP request object
            response: The Django HTTP response object
            
        Returns:
            Enhanced HttpResponse with additional headers and metadata
        """
        if not request.path.startswith('/api/'):
            return response
            
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Add API-specific headers
        if hasattr(request, 'api_request_id'):
            response['X-Request-ID'] = request.api_request_id
            
        if hasattr(request, 'api_start_time'):
            processing_time = time.time() - request.api_start_time
            response['X-Processing-Time'] = f"{processing_time:.3f}s"
            
            # Log response completion
            logger.info(
                "API response completed",
                request_id=getattr(request, 'api_request_id', ''),
                status_code=response.status_code,
                processing_time=processing_time,
                response_size=len(response.content) if hasattr(response, 'content') else 0
            )
        
        # Handle CORS for API endpoints
        # Let django-cors-headers handle CORS to avoid conflicts with credentials settings
        # Only add API-specific exposed headers if not handled by django-cors-headers
        if not response.get('Access-Control-Allow-Origin'):
            origin = request.META.get('HTTP_ORIGIN')
            allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
            allow_credentials = getattr(settings, 'CORS_ALLOW_CREDENTIALS', False)
            
            # Only set CORS headers if django-cors-headers didn't handle them
            if request.method == 'OPTIONS' and origin:
                if not allow_credentials:
                    # Can use * when credentials are not allowed
                    response['Access-Control-Allow-Origin'] = '*'
                elif origin in allowed_origins:
                    # Use specific origin when credentials are allowed
                    response['Access-Control-Allow-Origin'] = origin
                    response['Access-Control-Allow-Credentials'] = 'true'
                    
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Session-ID'
                
            # Always expose API-specific headers regardless of who handles CORS
            response['Access-Control-Expose-Headers'] = 'X-Request-ID, X-Processing-Time, X-Timeout-Warning'
            
        # Compress large responses if enabled
        if (getattr(settings, 'API_ENABLE_COMPRESSION', True) and 
            hasattr(response, 'content') and 
            len(response.content) > 1024):
            
            # Skip compression for streaming responses
            from django.http import StreamingHttpResponse, FileResponse
            if isinstance(response, (StreamingHttpResponse, FileResponse)):
                return response
                
            accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
            if 'gzip' in accept_encoding:
                response = self._compress_response(response)
                
        return response
    
    def _compress_response(self, response: HttpResponse) -> HttpResponse:
        """Compress response content using gzip."""
        if response.get('Content-Encoding') == 'gzip':
            return response
            
        content = response.content
        if isinstance(content, str):
            content = content.encode('utf-8')
            
        buf = BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as gz_file:
            gz_file.write(content)
            
        response.content = buf.getvalue()
        response['Content-Encoding'] = 'gzip'
        response['Content-Length'] = str(len(response.content))
        response['Vary'] = 'Accept-Encoding'
        
        return response


class APIErrorHandlerMiddleware(MiddlewareMixin):
    """
    Middleware for handling unhandled exceptions and converting them
    to structured API error responses.
    """
    
    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        """
        Handle unhandled exceptions in API requests.
        
        Args:
            request: The Django HTTP request object
            exception: The unhandled exception
            
        Returns:
            JsonResponse with structured error information
        """
        if not request.path.startswith('/api/'):
            return None
            
        request_id = getattr(request, 'api_request_id', str(uuid.uuid4()))
        
        # Log the exception
        logger.error(
            "Unhandled API exception",
            request_id=request_id,
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            path=request.path,
            method=request.method,
            exc_info=True
        )
        
        # Convert known exceptions to APIError
        if isinstance(exception, APIError):
            api_error = exception
        elif isinstance(exception, ValidationError):
            api_error = ValidationError(str(exception))
        else:
            # Convert unknown exceptions to generic APIError
            api_error = APIError(
                message="An unexpected error occurred",
                error_code="INTERNAL_SERVER_ERROR",
                status_code=500
            )
        
        # Create structured error response using APIResponseFormatter
        error_response = APIResponseFormatter.format_error_response(api_error, request_id)
            
        return JsonResponse(error_response, status=api_error.status_code)


class APIRateLimitMiddleware(MiddlewareMixin):
    """
    Middleware for implementing global rate limiting on API endpoints.
    
    This middleware provides the first tier of rate limiting, applying a global
    limit to all API endpoints. It operates independently from endpoint-specific
    @rate_limit decorators, which provide the second tier of rate limiting.
    
    Configuration:
        - API_RATE_LIMIT_REQUESTS: Number of requests allowed per window (default: 100)
        - API_RATE_LIMIT_WINDOW: Time window in seconds (default: 60)
    
    Rate limiting is per IP address using a sliding window algorithm.
    When limits are exceeded, returns 429 with Retry-After header.
    """
    
    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """
        Check rate limits for API requests.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            Optional HttpResponse with 429 status if rate limited
        """
        if not request.path.startswith('/api/'):
            return None
            
        # Get rate limit configuration
        rate_limit = getattr(settings, 'API_RATE_LIMIT_REQUESTS', 100)
        window = getattr(settings, 'API_RATE_LIMIT_WINDOW', 60)
        
        # Get client identifier
        client_ip = self._get_client_ip(request)
        cache_key = f"rate_limit:{client_ip}"
        
        # Get current request count
        current_requests = cache.get(cache_key, 0)
        
        if current_requests >= rate_limit:
            # Rate limit exceeded
            request_id = getattr(request, 'api_request_id', str(uuid.uuid4()))
            
            logger.warning(
                "Rate limit exceeded",
                request_id=request_id,
                client_ip=client_ip,
                current_requests=current_requests,
                rate_limit=rate_limit
            )
            
            error = APIError(
                message=f'Rate limit of {rate_limit} requests per {window} seconds exceeded',
                error_code='RATE_LIMIT_EXCEEDED',
                status_code=429
            )
            error_response = APIResponseFormatter.format_error_response(error, request_id)
            response = JsonResponse(error_response, status=429)
            response['Retry-After'] = str(window)
            return response
        
        # Increment request count
        cache.set(cache_key, current_requests + 1, window)
        
        return None
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip