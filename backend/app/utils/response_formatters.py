import time
from typing import Dict, Any, Optional, List, Union
from django.http import JsonResponse
import structlog

from app.utils.errors import APIError


logger = structlog.get_logger(__name__)


class APIResponseFormatter:
    """
    Centralized response formatting utility for consistent API responses
    across all endpoints.
    """
    
    @staticmethod
    def format_success_response(data: Any, message: Optional[str] = None, 
                              metadata: Optional[Dict[str, Any]] = None,
                              request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Format successful API response with standardized structure.
        
        Args:
            data: The response data payload
            message: Optional success message
            metadata: Optional metadata (pagination, processing info, etc.)
            request_id: Optional request ID for tracking
            
        Returns:
            Formatted response dictionary
        """
        response = {
            'status': 'success',
            'success': True,
            'data': data,
            'timestamp': time.time()
        }
        
        if message:
            response['message'] = message
            
        if metadata:
            response['metadata'] = metadata
            
        if request_id:
            response['request_id'] = request_id
            
        return response
    
    @staticmethod
    def format_error_response(error: Union[APIError, Exception], 
                            request_id: Optional[str] = None,
                            include_traceback: bool = False) -> Dict[str, Any]:
        """
        Format error response using existing APIError classes.
        
        Args:
            error: APIError instance or generic exception
            request_id: Optional request ID for tracking
            include_traceback: Whether to include traceback (dev mode only)
            
        Returns:
            Formatted error response dictionary
        """
        if isinstance(error, APIError):
            response = {
                'status': 'error',
                'success': False,
                'error_code': error.error_code,
                'error': error.error_code,  # Backward compatibility alias
                'message': error.message,
                'timestamp': time.time()
            }
            
            if hasattr(error, 'details') and error.details:
                response['details'] = error.details
                
        else:
            # Handle generic exceptions
            response = {
                'status': 'error',
                'success': False,
                'error_code': 'INTERNAL_SERVER_ERROR',
                'error': 'INTERNAL_SERVER_ERROR',  # Backward compatibility alias
                'message': str(error),
                'timestamp': time.time()
            }
        
        if request_id:
            response['request_id'] = request_id
            
        if include_traceback and hasattr(error, '__traceback__'):
            import traceback
            response['traceback'] = traceback.format_exc()
            
        return response
    
    @staticmethod
    def format_progress_response(job_id: str, progress: float, status: str,
                               estimated_completion: Optional[float] = None,
                               operation_type: Optional[str] = None,
                               request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Format progress response for background task tracking.
        
        Args:
            job_id: Unique job identifier
            progress: Progress percentage (0.0 - 100.0)
            status: Current status (queued, processing, completed, failed)
            estimated_completion: Estimated completion timestamp
            operation_type: Type of operation being performed
            request_id: Optional request ID for tracking
            
        Returns:
            Formatted progress response dictionary
        """
        response = {
            'status': 'progress',
            'job_id': job_id,
            'progress': progress,
            'current_status': status,
            'timestamp': time.time()
        }
        
        if estimated_completion:
            response['estimated_completion'] = estimated_completion
            
        if operation_type:
            response['operation_type'] = operation_type
            
        if request_id:
            response['request_id'] = request_id
            
        # Add status-specific information
        if status == 'queued':
            response['message'] = 'Job is queued for processing'
        elif status == 'processing':
            response['message'] = f'Processing in progress ({progress:.1f}% complete)'
        elif status == 'completed':
            response['message'] = 'Job completed successfully'
        elif status == 'failed':
            response['message'] = 'Job processing failed'
            
        return response
    
    @staticmethod
    def format_validation_response(validation_results: Dict[str, Any],
                                 warnings: Optional[List[str]] = None,
                                 request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Format validation response for file upload and parameter validation.
        
        Args:
            validation_results: Dictionary containing validation results
            warnings: Optional list of validation warnings
            request_id: Optional request ID for tracking
            
        Returns:
            Formatted validation response dictionary
        """
        response = {
            'status': 'validation',
            'results': validation_results,
            'timestamp': time.time()
        }
        
        if warnings:
            response['warnings'] = warnings
            
        if request_id:
            response['request_id'] = request_id
            
        # Determine overall validation status
        has_errors = any(
            result.get('valid') is False 
            for result in validation_results.values() 
            if isinstance(result, dict)
        )
        
        response['overall_status'] = 'failed' if has_errors else 'passed'
        
        return response
    
    @staticmethod
    def format_job_status_response(job_info: Dict[str, Any],
                                 include_details: bool = True,
                                 request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Format job status response with configurable detail levels.
        
        Args:
            job_info: Dictionary containing job information
            include_details: Whether to include detailed job information
            request_id: Optional request ID for tracking
            
        Returns:
            Formatted job status response dictionary
        """
        response = {
            'status': 'job_status',
            'job_id': job_info.get('job_id'),
            'current_status': job_info.get('status'),
            'progress': job_info.get('progress', 0.0),
            'timestamp': time.time()
        }
        
        if include_details:
            response['details'] = {
                'operation_type': job_info.get('operation_type'),
                'created_at': job_info.get('created_at'),
                'started_at': job_info.get('started_at'),
                'completed_at': job_info.get('completed_at'),
                'estimated_completion': job_info.get('estimated_completion'),
                'processing_time': job_info.get('processing_time'),
                'result_size': job_info.get('result_size'),
                'error_message': job_info.get('error_message')
            }
            
            # Add result information if job is completed
            if job_info.get('status') == 'completed' and job_info.get('result'):
                response['result'] = job_info['result']
                
        if request_id:
            response['request_id'] = request_id
            
        return response
    
    @staticmethod
    def format_download_response(file_info: Dict[str, Any],
                               download_url: str,
                               request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Format file download response with metadata.
        
        Args:
            file_info: Dictionary containing file information
            download_url: URL for downloading the file
            request_id: Optional request ID for tracking
            
        Returns:
            Formatted download response dictionary
        """
        response = {
            'status': 'download_ready',
            'download_url': download_url,
            'file_info': {
                'filename': file_info.get('filename'),
                'size': file_info.get('size'),
                'format': file_info.get('format'),
                'checksum': file_info.get('checksum'),
                'expires_at': file_info.get('expires_at')
            },
            'timestamp': time.time()
        }
        
        if request_id:
            response['request_id'] = request_id
            
        return response
    
    @staticmethod
    def format_list_response(items: List[Any], 
                           pagination: Optional[Dict[str, Any]] = None,
                           filters: Optional[Dict[str, Any]] = None,
                           request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Format paginated list response for future list endpoints.
        
        Args:
            items: List of items to return
            pagination: Optional pagination information
            filters: Optional applied filters information
            request_id: Optional request ID for tracking
            
        Returns:
            Formatted list response dictionary
        """
        response = {
            'status': 'success',
            'success': True,
            'data': items,
            'count': len(items),
            'timestamp': time.time()
        }
        
        if pagination:
            response['pagination'] = {
                'total_count': pagination.get('total_count'),
                'page': pagination.get('page', 1),
                'page_size': pagination.get('page_size', 20),
                'has_next': pagination.get('has_next', False),
                'has_previous': pagination.get('has_previous', False),
                'next_page': pagination.get('next_page'),
                'previous_page': pagination.get('previous_page')
            }
            
        if filters:
            response['applied_filters'] = filters
            
        if request_id:
            response['request_id'] = request_id
            
        return response
    
    @staticmethod
    def create_json_response(data: Dict[str, Any], status_code: int = 200,
                           compress: bool = False) -> JsonResponse:
        """
        Create JsonResponse with optional compression and headers.
        
        Args:
            data: Response data dictionary
            status_code: HTTP status code
            compress: Whether to enable compression for large responses
            
        Returns:
            JsonResponse object
        """
        response = JsonResponse(data, status=status_code)
        
        # Add cache headers for appropriate responses
        if status_code == 200 and data.get('status') == 'success':
            response['Cache-Control'] = 'private, max-age=300'  # 5 minutes
        elif status_code >= 400:
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            
        return response
    
    @staticmethod
    def add_performance_metadata(response_data: Dict[str, Any],
                               processing_time: Optional[float] = None,
                               database_queries: Optional[int] = None,
                               cache_hits: Optional[int] = None) -> Dict[str, Any]:
        """
        Add performance metadata to response.
        
        Args:
            response_data: Existing response data
            processing_time: Total processing time in seconds
            database_queries: Number of database queries executed
            cache_hits: Number of cache hits
            
        Returns:
            Response data with performance metadata
        """
        if 'metadata' not in response_data:
            response_data['metadata'] = {}
            
        performance_data = {}
        
        if processing_time is not None:
            performance_data['processing_time'] = f"{processing_time:.3f}s"
            
        if database_queries is not None:
            performance_data['database_queries'] = database_queries
            
        if cache_hits is not None:
            performance_data['cache_hits'] = cache_hits
            
        if performance_data:
            response_data['metadata']['performance'] = performance_data
            
        return response_data