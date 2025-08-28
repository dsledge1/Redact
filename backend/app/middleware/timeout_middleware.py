import time
import uuid
import structlog
from typing import Callable, Dict, Any, Optional
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from celery import current_app

from app.utils.errors import APIError


logger = structlog.get_logger(__name__)


class TimeoutHandlerMiddleware(MiddlewareMixin):
    """
    Middleware for handling request timeouts and automatic background
    task queuing for long-running operations.
    """
    
    # Operation-specific timeout configurations
    OPERATION_TIMEOUTS = {
        'redact': {'sync': 30, 'background_threshold': 25, 'max_background': 8 * 3600},
        'split': {'sync': 30, 'background_threshold': 25, 'max_background': 8 * 3600},
        'merge': {'sync': 30, 'background_threshold': 25, 'max_background': 8 * 3600},
        'extract': {'sync': 30, 'background_threshold': 25, 'max_background': 8 * 3600},
        'default': {'sync': 30, 'background_threshold': 25, 'max_background': 300}
    }
    
    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """
        Process request for timeout configuration and monitoring.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            Optional HttpResponse if request should be handled specially
        """
        if not request.path.startswith('/api/'):
            return None
            
        # Determine operation type from URL path
        operation_type = self._get_operation_type(request.path)
        timeout_config = self.OPERATION_TIMEOUTS.get(operation_type, self.OPERATION_TIMEOUTS['default'])
        
        # Store timeout configuration in request
        request.timeout_config = timeout_config
        request.operation_type = operation_type
        request.timeout_start = time.time()
        
        # Add timeout headers to help clients understand limits
        if hasattr(request, 'api_request_id'):
            logger.debug(
                "Timeout monitoring initiated",
                request_id=request.api_request_id,
                operation_type=operation_type,
                sync_timeout=timeout_config['sync'],
                background_threshold=timeout_config['background_threshold']
            )
        
        return None
    
    def process_view(self, request: HttpRequest, view_func: Callable, 
                    view_args: tuple, view_kwargs: dict) -> Optional[HttpResponse]:
        """
        Process view with timeout monitoring and hints for background processing.
        
        Args:
            request: The Django HTTP request object
            view_func: The view function being called
            view_args: Positional arguments for the view
            view_kwargs: Keyword arguments for the view
            
        Returns:
            None - let views handle job creation instead of short-circuiting
        """
        if not request.path.startswith('/api/'):
            return None
            
        # Set hints for views to handle background processing
        if self._should_queue_background_task(request):
            request.should_queue_background = True
            request.background_job_id = str(uuid.uuid4())
            
            # Log background processing recommendation
            logger.info(
                "Background processing recommended",
                request_id=getattr(request, 'api_request_id', 'unknown'),
                job_id=request.background_job_id,
                operation_type=getattr(request, 'operation_type', 'unknown'),
                path=request.path,
                method=request.method
            )
        else:
            request.should_queue_background = False
            
        return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Process response for timeout warnings and monitoring.
        
        Args:
            request: The Django HTTP request object
            response: The Django HTTP response object
            
        Returns:
            Enhanced HttpResponse with timeout information
        """
        if not request.path.startswith('/api/'):
            return response
            
        # Calculate processing time
        if hasattr(request, 'timeout_start'):
            processing_time = time.time() - request.timeout_start
            timeout_config = getattr(request, 'timeout_config', self.OPERATION_TIMEOUTS['default'])
            
            # Add timeout warning headers if approaching limits
            if processing_time > timeout_config['background_threshold'] * 0.8:
                response['X-Timeout-Warning'] = 'true'
                response['X-Recommended-Action'] = 'Consider using background processing'
                
            # Log performance metrics
            if hasattr(request, 'api_request_id'):
                logger.info(
                    "Request processing completed",
                    request_id=request.api_request_id,
                    operation_type=getattr(request, 'operation_type', 'unknown'),
                    processing_time=processing_time,
                    sync_timeout=timeout_config['sync'],
                    approaching_timeout=processing_time > timeout_config['background_threshold'] * 0.8
                )
        
        return response
    
    def _get_operation_type(self, path: str) -> str:
        """
        Determine operation type from URL path.
        
        Args:
            path: The request URL path
            
        Returns:
            Operation type string
        """
        if '/redact/' in path:
            return 'redact'
        elif '/split/' in path:
            return 'split'
        elif '/merge/' in path:
            return 'merge'
        elif '/extract/' in path:
            return 'extract'
        else:
            return 'default'
    
    def _should_queue_background_task(self, request: HttpRequest) -> bool:
        """
        Determine if request should be queued as background task.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            True if should be queued for background processing
        """
        # Check if client explicitly requests background processing
        if request.META.get('HTTP_X_BACKGROUND_PROCESSING') == 'true':
            return True
            
        # Check file size indicators that suggest long processing time
        content_length = int(request.META.get('CONTENT_LENGTH', 0))
        if content_length > 50 * 1024 * 1024:  # 50MB threshold
            return True
            
        # Check for multiple file operations
        if request.method == 'POST':
            # For merge operations with many files
            if 'merge' in request.path and self._estimate_file_count(request) > 10:
                return True
                
        return False
    
    def _estimate_file_count(self, request: HttpRequest) -> int:
        """
        Estimate number of files in request.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            Estimated number of files
        """
        try:
            # This is a simple estimation - in production you'd parse the actual request
            content_type = request.META.get('CONTENT_TYPE', '')
            if 'multipart/form-data' in content_type:
                # Rough estimation based on content length and boundaries
                content_length = int(request.META.get('CONTENT_LENGTH', 0))
                # Assume average file size of 5MB for estimation
                return max(1, content_length // (5 * 1024 * 1024))
        except:
            pass
            
        return 1
    
    def create_background_task_response(self, request: HttpRequest) -> JsonResponse:
        """
        Create 202 response for background task processing.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            JsonResponse with 202 status and job information
        """
        # Use pre-generated job ID from process_view or generate new one
        job_id = getattr(request, 'background_job_id', str(uuid.uuid4()))
        request_id = getattr(request, 'api_request_id', str(uuid.uuid4()))
        
        # Log background task creation
        logger.info(
            "Queuing background task",
            request_id=request_id,
            job_id=job_id,
            operation_type=getattr(request, 'operation_type', 'unknown'),
            path=request.path,
            method=request.method
        )
        
        try:
            # Queue the task using Celery
            # Note: This would need to be implemented with actual Celery task
            # For now, we'll return a placeholder response
            
            # Estimate completion time based on operation type
            timeout_config = getattr(request, 'timeout_config', self.OPERATION_TIMEOUTS['default'])
            estimated_completion = time.time() + (timeout_config['max_background'] / 4)  # Conservative estimate
            
            response_data = {
                'status': 'accepted',
                'message': 'Request queued for background processing',
                'job_id': job_id,
                'request_id': request_id,
                'estimated_completion_time': estimated_completion,
                'status_url': f"/api/job/{job_id}/status/",
                'operation_type': getattr(request, 'operation_type', 'unknown')
            }
            
            return JsonResponse(response_data, status=202)
            
        except Exception as e:
            logger.error(
                "Failed to queue background task",
                request_id=request_id,
                job_id=job_id,
                error=str(e),
                exc_info=True
            )
            
            # Fall back to synchronous processing with timeout warning
            return JsonResponse({
                'error': 'BACKGROUND_QUEUE_FAILED',
                'message': 'Failed to queue background task, will process synchronously with timeout risk',
                'request_id': request_id,
                'fallback_processing': True
            }, status=503)
    
    def _queue_background_task(self, request: HttpRequest, view_func: Callable, 
                               view_args: tuple, view_kwargs: dict) -> JsonResponse:
        """
        Queue a background task and return 202 response.
        This method delegates to create_background_task_response for backward compatibility.
        
        Args:
            request: The Django HTTP request object
            view_func: The view function (unused, kept for signature compatibility)
            view_args: View arguments (unused, kept for signature compatibility)
            view_kwargs: View keyword arguments (unused, kept for signature compatibility)
            
        Returns:
            JsonResponse with 202 status and job information
        """
        return self.create_background_task_response(request)
    
    def _get_estimated_processing_time(self, request: HttpRequest) -> float:
        """
        Estimate processing time based on request characteristics.
        
        Args:
            request: The Django HTTP request object
            
        Returns:
            Estimated processing time in seconds
        """
        base_time = 5.0  # Base processing time
        
        # Adjust based on file size
        content_length = int(request.META.get('CONTENT_LENGTH', 0))
        file_size_factor = content_length / (1024 * 1024)  # Size in MB
        
        # Adjust based on operation type
        operation_type = getattr(request, 'operation_type', 'default')
        operation_factors = {
            'redact': 3.0,    # Redaction is CPU intensive
            'extract': 2.5,   # Extraction requires OCR
            'merge': 1.5,     # Merging is relatively fast
            'split': 1.0,     # Splitting is fastest
            'default': 2.0
        }
        
        estimated_time = base_time * operation_factors[operation_type] * (1 + file_size_factor * 0.1)
        
        return min(estimated_time, 300)  # Cap at 5 minutes for estimation