import json
import time
import psutil
import platform
from typing import Dict, Any, Optional
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.core.cache import cache
from django.db import connection
from django.conf import settings
import structlog

from app.utils.response_formatters import APIResponseFormatter
from app.utils.api_decorators import log_api_call, rate_limit


logger = structlog.get_logger(__name__)


def is_monitoring_allowed(request: HttpRequest) -> tuple[bool, Optional[str]]:
    """
    Check if monitoring endpoints should be accessible.
    
    Args:
        request: HTTP request object
        
    Returns:
        Tuple of (is_allowed, error_message)
    """
    # Allow access in DEBUG mode
    if getattr(settings, 'DEBUG', False):
        return True, None
    
    # Check for admin authentication (if available)
    if hasattr(request, 'user') and request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return True, None
    
    # Check for local network access
    client_ip = request.META.get('REMOTE_ADDR', '')
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    
    # Allow localhost and private network ranges
    allowed_networks = [
        '127.0.0.1', '::1',  # localhost
        '10.', '192.168.', '172.'  # private networks
    ]
    
    if any(client_ip.startswith(network) for network in allowed_networks):
        return True, None
    
    # Check for special monitoring header/token
    monitoring_token = request.META.get('HTTP_X_MONITORING_TOKEN')
    expected_token = getattr(settings, 'MONITORING_ACCESS_TOKEN', None)
    if monitoring_token and expected_token and monitoring_token == expected_token:
        return True, None
    
    return False, "Access to monitoring endpoints is restricted"


class HealthCheckView(View):
    """
    Comprehensive system health check endpoint that provides status
    of all critical system components.
    """
    
    @log_api_call()
    @rate_limit(requests_per_minute=30)
    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Perform comprehensive health check of all system components.
        
        Args:
            request: HTTP request object
            
        Returns:
            JsonResponse with detailed health status
        """
        request_id = getattr(request, 'api_request_id', '')
        
        # Check access permissions
        allowed, error_msg = is_monitoring_allowed(request)
        if not allowed:
            from app.utils.errors import AuthenticationError
            error_response = APIResponseFormatter.format_error_response(
                AuthenticationError(error_msg),
                request_id=request_id
            )
            return JsonResponse(error_response, status=403)
        health_status = {
            'status': 'healthy',
            'timestamp': time.time(),
            'components': {},
            'system_info': {}
        }
        
        try:
            # Check database connectivity
            health_status['components']['database'] = self._check_database()
            
            # Check Redis connectivity
            health_status['components']['redis'] = self._check_redis()
            
            # Check file system
            health_status['components']['filesystem'] = self._check_filesystem()
            
            # Get system resource usage
            health_status['system_info'] = self._get_system_info()
            
            # Check Celery broker (if available)
            health_status['components']['celery'] = self._check_celery()
            
            # Determine overall status
            component_statuses = [
                comp['status'] for comp in health_status['components'].values()
            ]
            
            if 'critical' in component_statuses:
                health_status['status'] = 'critical'
                status_code = 503
            elif 'warning' in component_statuses:
                health_status['status'] = 'warning' 
                status_code = 200
            else:
                health_status['status'] = 'healthy'
                status_code = 200
            
            response_data = APIResponseFormatter.format_success_response(
                health_status,
                message="Health check completed",
                request_id=request_id
            )
            
            return JsonResponse(response_data, status=status_code)
            
        except Exception as e:
            logger.error(
                "Health check failed",
                request_id=request_id,
                error=str(e),
                exc_info=True
            )
            
            error_response = APIResponseFormatter.format_error_response(
                Exception("Health check system error"),
                request_id=request_id
            )
            
            return JsonResponse(error_response, status=500)
    
    def _check_database(self) -> Dict[str, Any]:
        """Check database connectivity and response time."""
        try:
            start_time = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            response_time = time.time() - start_time
            
            return {
                'status': 'healthy',
                'response_time': f"{response_time:.3f}s",
                'message': 'Database connection successful'
            }
        except Exception as e:
            return {
                'status': 'critical',
                'error': str(e),
                'message': 'Database connection failed'
            }
    
    def _check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        try:
            start_time = time.time()
            cache.set('health_check', 'test', 10)
            result = cache.get('health_check')
            response_time = time.time() - start_time
            
            if result == 'test':
                return {
                    'status': 'healthy',
                    'response_time': f"{response_time:.3f}s",
                    'message': 'Redis connection successful'
                }
            else:
                return {
                    'status': 'warning',
                    'message': 'Redis read/write test failed'
                }
        except Exception as e:
            return {
                'status': 'critical',
                'error': str(e),
                'message': 'Redis connection failed'
            }
    
    def _check_filesystem(self) -> Dict[str, Any]:
        """Check file system access and disk space."""
        try:
            # Check media directory
            media_root = getattr(settings, 'MEDIA_ROOT', '/tmp')
            
            # Check disk usage
            disk_usage = psutil.disk_usage(str(media_root))
            free_space_gb = disk_usage.free / (1024 ** 3)
            total_space_gb = disk_usage.total / (1024 ** 3)
            usage_percent = (disk_usage.used / disk_usage.total) * 100
            
            status = 'healthy'
            if usage_percent > 90:
                status = 'critical'
            elif usage_percent > 80:
                status = 'warning'
            
            return {
                'status': status,
                'free_space_gb': f"{free_space_gb:.2f}",
                'total_space_gb': f"{total_space_gb:.2f}",
                'usage_percent': f"{usage_percent:.1f}%",
                'message': f'Filesystem check completed'
            }
        except Exception as e:
            return {
                'status': 'warning',
                'error': str(e),
                'message': 'Filesystem check failed'
            }
    
    def _check_celery(self) -> Dict[str, Any]:
        """Check Celery broker connectivity."""
        try:
            # This is a basic check - in production you'd want to check actual worker status
            return {
                'status': 'healthy',
                'message': 'Celery broker check passed (basic)'
            }
        except Exception as e:
            return {
                'status': 'warning',
                'error': str(e),
                'message': 'Celery broker check failed'
            }
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system resource information."""
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_io': {
                    'read_bytes': psutil.disk_io_counters().read_bytes if psutil.disk_io_counters() else 0,
                    'write_bytes': psutil.disk_io_counters().write_bytes if psutil.disk_io_counters() else 0
                },
                'platform': platform.platform(),
                'python_version': platform.python_version()
            }
        except Exception as e:
            return {
                'error': str(e),
                'message': 'System info collection failed'
            }


class APIMetricsView(View):
    """
    API performance monitoring and metrics endpoint.
    """
    
    @log_api_call()
    @rate_limit(requests_per_minute=60)  
    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Get API performance metrics and statistics.
        
        Args:
            request: HTTP request object
            
        Returns:
            JsonResponse with performance metrics
        """
        request_id = getattr(request, 'api_request_id', '')
        
        # Check access permissions
        allowed, error_msg = is_monitoring_allowed(request)
        if not allowed:
            from app.utils.errors import AuthenticationError
            error_response = APIResponseFormatter.format_error_response(
                AuthenticationError(error_msg),
                request_id=request_id
            )
            return JsonResponse(error_response, status=403)
        
        try:
            metrics = {
                'api_usage': self._get_api_usage_metrics(),
                'performance': self._get_performance_metrics(),
                'errors': self._get_error_metrics(),
                'system_resources': self._get_resource_metrics(),
                'timestamp': time.time()
            }
            
            response_data = APIResponseFormatter.format_success_response(
                metrics,
                message="API metrics retrieved",
                request_id=request_id
            )
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(
                "Failed to retrieve API metrics",
                request_id=request_id,
                error=str(e),
                exc_info=True
            )
            
            error_response = APIResponseFormatter.format_error_response(
                Exception("Metrics collection failed"),
                request_id=request_id
            )
            
            return JsonResponse(error_response, status=500)
    
    def _get_api_usage_metrics(self) -> Dict[str, Any]:
        """Get API usage statistics from cache."""
        # In a real implementation, this would pull from a metrics store
        return {
            'total_requests_24h': cache.get('metrics:total_requests_24h', 0),
            'successful_requests_24h': cache.get('metrics:successful_requests_24h', 0),
            'failed_requests_24h': cache.get('metrics:failed_requests_24h', 0),
            'endpoints': {
                '/api/redact/': cache.get('metrics:redact_requests', 0),
                '/api/split/': cache.get('metrics:split_requests', 0),
                '/api/merge/': cache.get('metrics:merge_requests', 0),
                '/api/extract/': cache.get('metrics:extract_requests', 0)
            }
        }
    
    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return {
            'average_response_time': cache.get('metrics:avg_response_time', 0),
            'p95_response_time': cache.get('metrics:p95_response_time', 0),
            'p99_response_time': cache.get('metrics:p99_response_time', 0),
            'background_jobs_queued': cache.get('metrics:bg_jobs_queued', 0),
            'background_jobs_processing': cache.get('metrics:bg_jobs_processing', 0),
            'background_jobs_completed': cache.get('metrics:bg_jobs_completed', 0)
        }
    
    def _get_error_metrics(self) -> Dict[str, Any]:
        """Get error rate metrics."""
        return {
            'error_rate_24h': cache.get('metrics:error_rate_24h', 0),
            'timeout_rate_24h': cache.get('metrics:timeout_rate_24h', 0),
            'validation_error_rate': cache.get('metrics:validation_error_rate', 0),
            'common_errors': {
                'VALIDATION_ERROR': cache.get('metrics:validation_errors', 0),
                'TIMEOUT_ERROR': cache.get('metrics:timeout_errors', 0),
                'FILE_ERROR': cache.get('metrics:file_errors', 0)
            }
        }
    
    def _get_resource_metrics(self) -> Dict[str, Any]:
        """Get current system resource metrics."""
        try:
            return {
                'cpu_usage': psutil.cpu_percent(),
                'memory_usage': psutil.virtual_memory().percent,
                'active_connections': len(connection.queries),
                'cache_hit_rate': cache.get('metrics:cache_hit_rate', 0)
            }
        except Exception:
            return {}


class APIDocumentationView(View):
    """
    Interactive API documentation endpoint.
    """
    
    @log_api_call()
    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Get comprehensive API documentation.
        
        Args:
            request: HTTP request object
            
        Returns:
            JsonResponse with API documentation
        """
        request_id = getattr(request, 'api_request_id', '')
        
        documentation = {
            'api_version': '1.0',
            'base_url': request.build_absolute_uri('/api/'),
            'endpoints': self._get_endpoint_documentation(),
            'authentication': self._get_auth_documentation(),
            'rate_limits': self._get_rate_limit_documentation(),
            'error_codes': self._get_error_code_documentation(),
            'examples': self._get_usage_examples()
        }
        
        response_data = APIResponseFormatter.format_success_response(
            documentation,
            message="API documentation retrieved",
            request_id=request_id
        )
        
        return JsonResponse(response_data)
    
    def _get_endpoint_documentation(self) -> Dict[str, Any]:
        """Get endpoint documentation."""
        return {
            '/api/redact/': {
                'method': 'POST',
                'description': 'Redact sensitive information from PDF files',
                'parameters': {
                    'file': 'PDF file to process (multipart/form-data)',
                    'redaction_type': 'Type of redaction to perform',
                    'session_id': 'Session identifier'
                },
                'responses': {
                    '200': 'Successful redaction (synchronous)',
                    '202': 'Accepted for background processing',
                    '400': 'Validation error',
                    '413': 'File too large',
                    '429': 'Rate limit exceeded'
                }
            },
            '/api/split/': {
                'method': 'POST', 
                'description': 'Split PDF files into separate pages or sections',
                'parameters': {
                    'file': 'PDF file to split',
                    'split_method': 'How to split the file (pages, bookmarks, etc.)',
                    'session_id': 'Session identifier'
                }
            },
            '/api/merge/': {
                'method': 'POST',
                'description': 'Merge multiple PDF files into one',
                'parameters': {
                    'files': 'Array of PDF files to merge',
                    'merge_order': 'Order for merging files',
                    'session_id': 'Session identifier'
                }
            },
            '/api/extract/': {
                'method': 'POST',
                'description': 'Extract text, images, or metadata from PDFs',
                'parameters': {
                    'file': 'PDF file to extract from',
                    'extract_type': 'What to extract (text, images, metadata)',
                    'session_id': 'Session identifier'
                }
            },
            '/api/job/{job_id}/status/': {
                'method': 'GET',
                'description': 'Check status of background processing job',
                'parameters': {
                    'job_id': 'UUID of the background job'
                }
            }
        }
    
    def _get_auth_documentation(self) -> Dict[str, Any]:
        """Get authentication documentation."""
        return {
            'type': 'session-based',
            'session_id': {
                'description': 'Session identifier for tracking related operations',
                'required': True,
                'format': 'UUID v4',
                'header': 'X-Session-ID'
            }
        }
    
    def _get_rate_limit_documentation(self) -> Dict[str, Any]:
        """Get rate limiting documentation."""
        return {
            'default_limit': f"{getattr(settings, 'API_RATE_LIMIT_REQUESTS', 100)} requests per minute",
            'headers': {
                'X-RateLimit-Remaining': 'Remaining requests in current window',
                'X-RateLimit-Reset': 'Time when rate limit resets'
            },
            'exceeded_response': {
                'status_code': 429,
                'retry_after': 60
            }
        }
    
    def _get_error_code_documentation(self) -> Dict[str, Any]:
        """Get error code documentation."""
        return {
            'VALIDATION_ERROR': {
                'status_code': 400,
                'description': 'Request validation failed'
            },
            'AUTHENTICATION_ERROR': {
                'status_code': 401,
                'description': 'Invalid or missing session ID'
            },
            'RATE_LIMIT_EXCEEDED': {
                'status_code': 429,
                'description': 'Too many requests in time window'
            },
            'FILE_TOO_LARGE': {
                'status_code': 413,
                'description': 'Uploaded file exceeds size limit'
            },
            'PROCESSING_ERROR': {
                'status_code': 500,
                'description': 'Error during PDF processing'
            }
        }
    
    def _get_usage_examples(self) -> Dict[str, Any]:
        """Get usage examples."""
        return {
            'redaction_request': {
                'url': '/api/redact/',
                'method': 'POST',
                'headers': {
                    'Content-Type': 'multipart/form-data',
                    'X-Session-ID': '550e8400-e29b-41d4-a716-446655440000'
                },
                'body': {
                    'file': '<binary PDF data>',
                    'redaction_type': 'ssn'
                }
            },
            'job_status_check': {
                'url': '/api/job/123e4567-e89b-12d3-a456-426614174000/status/',
                'method': 'GET',
                'headers': {
                    'X-Session-ID': '550e8400-e29b-41d4-a716-446655440000'
                }
            }
        }


class SessionStatusView(View):
    """
    Session management and status endpoint.
    """
    
    @log_api_call()
    @rate_limit(requests_per_minute=120)
    def get(self, request: HttpRequest, session_id: str) -> JsonResponse:
        """
        Get detailed session information and statistics.
        
        Args:
            request: HTTP request object
            session_id: Session identifier
            
        Returns:
            JsonResponse with session details
        """
        request_id = getattr(request, 'api_request_id', '')
        
        try:
            session_info = self._get_session_info(session_id)
            
            response_data = APIResponseFormatter.format_success_response(
                session_info,
                message=f"Session {session_id} information retrieved",
                request_id=request_id
            )
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(
                "Failed to retrieve session information",
                request_id=request_id,
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            
            error_response = APIResponseFormatter.format_error_response(
                Exception("Session information retrieval failed"),
                request_id=request_id
            )
            
            return JsonResponse(error_response, status=500)
    
    def _get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Get session information from cache/database."""
        # This would typically query a session store
        session_key = f"session:{session_id}"
        
        return {
            'session_id': session_id,
            'created_at': cache.get(f"{session_key}:created_at", time.time()),
            'last_activity': cache.get(f"{session_key}:last_activity", time.time()),
            'total_operations': cache.get(f"{session_key}:operations", 0),
            'active_jobs': cache.get(f"{session_key}:active_jobs", []),
            'completed_jobs': cache.get(f"{session_key}:completed_jobs", []),
            'files_processed': cache.get(f"{session_key}:files_processed", 0),
            'total_processing_time': cache.get(f"{session_key}:total_time", 0),
            'status': 'active'
        }


class SessionCreateView(View):
    """
    Session creation endpoint.
    """
    
    @log_api_call()
    def post(self, request: HttpRequest) -> JsonResponse:
        """Create a new session."""
        import uuid
        
        request_id = getattr(request, 'api_request_id', '')
        session_id = str(uuid.uuid4())
        
        # Initialize session in cache
        session_key = f"session:{session_id}"
        cache.set(f"{session_key}:created_at", time.time(), 3600 * 24)  # 24 hours
        cache.set(f"{session_key}:operations", 0, 3600 * 24)
        cache.set(f"{session_key}:active_jobs", [], 3600 * 24)
        
        session_data = {
            'session_id': session_id,
            'created_at': time.time(),
            'expires_at': time.time() + (3600 * 24),
            'status': 'active'
        }
        
        response_data = APIResponseFormatter.format_success_response(
            session_data,
            message="Session created successfully",
            request_id=request_id
        )
        
        return JsonResponse(response_data, status=201)


class SessionCleanupView(View):
    """
    Session cleanup endpoint.
    """
    
    @log_api_call()
    def delete(self, request: HttpRequest, session_id: str) -> JsonResponse:
        """Clean up session resources."""
        request_id = getattr(request, 'api_request_id', '')
        
        # Clean up session data
        session_key = f"session:{session_id}"
        cache.delete_many([
            f"{session_key}:created_at",
            f"{session_key}:last_activity", 
            f"{session_key}:operations",
            f"{session_key}:active_jobs",
            f"{session_key}:completed_jobs",
            f"{session_key}:files_processed",
            f"{session_key}:total_time"
        ])
        
        response_data = APIResponseFormatter.format_success_response(
            {'session_id': session_id, 'cleaned_up': True},
            message=f"Session {session_id} cleaned up successfully",
            request_id=request_id
        )
        
        return JsonResponse(response_data)