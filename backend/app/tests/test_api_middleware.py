"""
Comprehensive unit tests for API middleware components.
"""

import json
import time
import uuid
from unittest.mock import Mock, patch, MagicMock
import pytest
from django.test import TestCase, RequestFactory
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from django.conf import settings

from app.middleware.api_middleware import (
    APIRequestMiddleware, APIResponseMiddleware, 
    APIErrorHandlerMiddleware, APIRateLimitMiddleware
)
from app.middleware.timeout_middleware import TimeoutHandlerMiddleware
from app.utils.errors import APIError, ValidationError


class TestAPIRequestMiddleware(TestCase):
    """Test APIRequestMiddleware functionality."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = APIRequestMiddleware()
        
    def test_process_request_api_endpoint(self):
        """Test request processing for API endpoints."""
        request = self.factory.post('/api/test/', {'data': 'test'})
        
        response = self.middleware.process_request(request)
        
        # Should not return response (None means continue processing)
        self.assertIsNone(response)
        
        # Should add request metadata
        self.assertTrue(hasattr(request, 'api_request_id'))
        self.assertTrue(hasattr(request, 'api_start_time'))
        self.assertIsInstance(request.api_request_id, str)
        self.assertIsInstance(request.api_start_time, float)
        
    def test_process_request_non_api_endpoint(self):
        """Test request processing for non-API endpoints."""
        request = self.factory.get('/admin/')
        
        response = self.middleware.process_request(request)
        
        # Should return None and skip processing
        self.assertIsNone(response)
        self.assertFalse(hasattr(request, 'api_request_id'))
        
    def test_process_request_invalid_content_type(self):
        """Test request with invalid content type."""
        request = self.factory.post(
            '/api/test/', 
            {'data': 'test'}, 
            content_type='text/plain'
        )
        
        response = self.middleware.process_request(request)
        
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        
        response_data = json.loads(response.content)
        self.assertIn('error', response_data)
        self.assertIn('request_id', response_data)
        
    def test_get_client_ip_with_forwarded_header(self):
        """Test client IP extraction with X-Forwarded-For header."""
        request = self.factory.get('/api/test/')
        request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.1,10.0.0.1'
        
        client_ip = self.middleware._get_client_ip(request)
        
        self.assertEqual(client_ip, '192.168.1.1')
        
    def test_get_client_ip_without_forwarded_header(self):
        """Test client IP extraction without X-Forwarded-For header."""
        request = self.factory.get('/api/test/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        client_ip = self.middleware._get_client_ip(request)
        
        self.assertEqual(client_ip, '127.0.0.1')


class TestAPIResponseMiddleware(TestCase):
    """Test APIResponseMiddleware functionality."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = APIResponseMiddleware()
        
    def test_process_response_api_endpoint(self):
        """Test response processing for API endpoints."""
        request = self.factory.get('/api/test/')
        request.api_request_id = str(uuid.uuid4())
        request.api_start_time = time.time() - 1.5  # 1.5 seconds ago
        
        response = JsonResponse({'status': 'success'})
        
        processed_response = self.middleware.process_response(request, response)
        
        # Check security headers
        self.assertEqual(processed_response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(processed_response['X-Frame-Options'], 'DENY')
        self.assertEqual(processed_response['X-XSS-Protection'], '1; mode=block')
        
        # Check API-specific headers
        self.assertEqual(processed_response['X-Request-ID'], request.api_request_id)
        self.assertIn('X-Processing-Time', processed_response)
        
        # Check processing time format
        processing_time = processed_response['X-Processing-Time']
        self.assertTrue(processing_time.endswith('s'))
        
    def test_process_response_non_api_endpoint(self):
        """Test response processing for non-API endpoints."""
        request = self.factory.get('/admin/')
        response = HttpResponse('Admin page')
        
        processed_response = self.middleware.process_response(request, response)
        
        # Should return response unchanged
        self.assertEqual(processed_response, response)
        self.assertNotIn('X-Request-ID', processed_response)
        
    def test_process_response_cors_options(self):
        """Test CORS headers for OPTIONS request."""
        request = self.factory.options('/api/test/')
        response = HttpResponse()
        
        processed_response = self.middleware.process_response(request, response)
        
        # Check CORS headers
        self.assertEqual(processed_response['Access-Control-Allow-Origin'], '*')
        self.assertIn('Access-Control-Allow-Methods', processed_response)
        self.assertIn('Access-Control-Allow-Headers', processed_response)
        
    @patch('app.middleware.api_middleware.settings.API_ENABLE_COMPRESSION', True)
    def test_compress_response(self):
        """Test response compression for large responses."""
        request = self.factory.get('/api/test/')
        request.META['HTTP_ACCEPT_ENCODING'] = 'gzip, deflate'
        
        # Create large response
        large_data = {'data': 'x' * 2000}
        response = JsonResponse(large_data)
        
        processed_response = self.middleware.process_response(request, response)
        
        # Should be compressed
        self.assertEqual(processed_response.get('Content-Encoding'), 'gzip')
        self.assertTrue(len(processed_response.content) < len(json.dumps(large_data)))


class TestAPIErrorHandlerMiddleware(TestCase):
    """Test APIErrorHandlerMiddleware functionality."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = APIErrorHandlerMiddleware()
        
    def test_process_exception_api_endpoint(self):
        """Test exception handling for API endpoints."""
        request = self.factory.post('/api/test/')
        request.api_request_id = str(uuid.uuid4())
        
        exception = APIError("Test error", "TEST_ERROR", 400)
        
        response = self.middleware.process_exception(request, exception)
        
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['error'], 'TEST_ERROR')
        self.assertEqual(response_data['message'], 'Test error')
        self.assertEqual(response_data['request_id'], request.api_request_id)
        
    def test_process_exception_non_api_endpoint(self):
        """Test exception handling for non-API endpoints."""
        request = self.factory.get('/admin/')
        exception = Exception("Test error")
        
        response = self.middleware.process_exception(request, exception)
        
        # Should return None for non-API endpoints
        self.assertIsNone(response)
        
    def test_process_exception_validation_error(self):
        """Test handling ValidationError."""
        request = self.factory.post('/api/test/')
        exception = ValidationError("Validation failed")
        
        response = self.middleware.process_exception(request, exception)
        
        self.assertIsInstance(response, JsonResponse)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['message'], 'Validation failed')
        
    def test_process_exception_generic_error(self):
        """Test handling generic exceptions."""
        request = self.factory.post('/api/test/')
        exception = ValueError("Generic error")
        
        response = self.middleware.process_exception(request, exception)
        
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 500)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['error'], 'INTERNAL_SERVER_ERROR')


class TestAPIRateLimitMiddleware(TestCase):
    """Test APIRateLimitMiddleware functionality."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = APIRateLimitMiddleware()
        cache.clear()  # Clear cache before each test
        
    @patch('app.middleware.api_middleware.settings.API_RATE_LIMIT_REQUESTS', 2)
    @patch('app.middleware.api_middleware.settings.API_RATE_LIMIT_WINDOW', 60)
    def test_rate_limit_within_limit(self):
        """Test requests within rate limit."""
        request = self.factory.post('/api/test/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        # First request should pass
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        
        # Second request should pass
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        
    @patch('app.middleware.api_middleware.settings.API_RATE_LIMIT_REQUESTS', 2)
    @patch('app.middleware.api_middleware.settings.API_RATE_LIMIT_WINDOW', 60)
    def test_rate_limit_exceeded(self):
        """Test rate limit exceeded."""
        request = self.factory.post('/api/test/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        # Exhaust rate limit
        for _ in range(2):
            self.middleware.process_request(request)
            
        # Third request should be rate limited
        response = self.middleware.process_request(request)
        
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 429)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['error'], 'RATE_LIMIT_EXCEEDED')
        
    def test_rate_limit_different_ips(self):
        """Test rate limiting is per IP address."""
        request1 = self.factory.post('/api/test/')
        request1.META['REMOTE_ADDR'] = '127.0.0.1'
        
        request2 = self.factory.post('/api/test/')
        request2.META['REMOTE_ADDR'] = '192.168.1.1'
        
        with patch('app.middleware.api_middleware.settings.API_RATE_LIMIT_REQUESTS', 1):
            # First IP exhausts limit
            self.middleware.process_request(request1)
            response1 = self.middleware.process_request(request1)
            self.assertEqual(response1.status_code, 429)
            
            # Second IP should still be allowed
            response2 = self.middleware.process_request(request2)
            self.assertIsNone(response2)
            
    def test_get_client_ip_with_forwarded_header(self):
        """Test client IP extraction with X-Forwarded-For header."""
        request = self.factory.get('/api/test/')
        request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.1,10.0.0.1'
        
        client_ip = self.middleware._get_client_ip(request)
        
        self.assertEqual(client_ip, '192.168.1.1')


class TestTimeoutHandlerMiddleware(TestCase):
    """Test TimeoutHandlerMiddleware functionality."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TimeoutHandlerMiddleware()
        
    def test_process_request_api_endpoint(self):
        """Test timeout configuration for API endpoints."""
        request = self.factory.post('/api/redact/')
        
        response = self.middleware.process_request(request)
        
        self.assertIsNone(response)
        self.assertTrue(hasattr(request, 'timeout_config'))
        self.assertTrue(hasattr(request, 'operation_type'))
        self.assertEqual(request.operation_type, 'redact')
        
    def test_get_operation_type(self):
        """Test operation type detection from URL path."""
        test_cases = [
            ('/api/redact/', 'redact'),
            ('/api/split/', 'split'),
            ('/api/merge/', 'merge'),
            ('/api/extract/', 'extract'),
            ('/api/other/', 'default')
        ]
        
        for path, expected_type in test_cases:
            operation_type = self.middleware._get_operation_type(path)
            self.assertEqual(operation_type, expected_type)
            
    def test_should_queue_background_task_large_file(self):
        """Test background task queuing for large files."""
        request = self.factory.post('/api/redact/')
        request.META['CONTENT_LENGTH'] = str(60 * 1024 * 1024)  # 60MB
        
        should_queue = self.middleware._should_queue_background_task(request)
        
        self.assertTrue(should_queue)
        
    def test_should_queue_background_task_explicit_header(self):
        """Test background task queuing with explicit header."""
        request = self.factory.post('/api/redact/')
        request.META['HTTP_X_BACKGROUND_PROCESSING'] = 'true'
        
        should_queue = self.middleware._should_queue_background_task(request)
        
        self.assertTrue(should_queue)
        
    def test_estimate_file_count(self):
        """Test file count estimation."""
        request = self.factory.post('/api/merge/')
        request.META['CONTENT_TYPE'] = 'multipart/form-data'
        request.META['CONTENT_LENGTH'] = str(20 * 1024 * 1024)  # 20MB
        
        file_count = self.middleware._estimate_file_count(request)
        
        self.assertGreater(file_count, 1)
        
    @patch('app.middleware.timeout_middleware.uuid.uuid4')
    def test_queue_background_task(self):
        """Test background task queuing."""
        mock_uuid = Mock()
        mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
        
        request = self.factory.post('/api/redact/')
        request.api_request_id = str(uuid.uuid4())
        request.timeout_config = {'max_background': 3600}
        request.operation_type = 'redact'
        
        view_func = Mock()
        view_args = ()
        view_kwargs = {}
        
        response = self.middleware._queue_background_task(
            request, view_func, view_args, view_kwargs
        )
        
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 202)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'accepted')
        self.assertIn('job_id', response_data)
        
    def test_process_response_timeout_warning(self):
        """Test timeout warning in response."""
        request = self.factory.post('/api/redact/')
        request.timeout_start = time.time() - 25  # 25 seconds ago
        request.timeout_config = {'background_threshold': 25, 'sync': 30}
        request.operation_type = 'redact'
        request.api_request_id = str(uuid.uuid4())
        
        response = JsonResponse({'status': 'success'})
        
        processed_response = self.middleware.process_response(request, response)
        
        self.assertEqual(processed_response.get('X-Timeout-Warning'), 'true')
        self.assertEqual(
            processed_response.get('X-Recommended-Action'), 
            'Consider using background processing'
        )


class TestMiddlewareIntegration(TestCase):
    """Test middleware integration and interaction."""
    
    def setUp(self):
        self.factory = RequestFactory()
        
    def test_middleware_chain_api_request(self):
        """Test complete middleware chain for API request."""
        # Create request
        request = self.factory.post(
            '/api/redact/', 
            json.dumps({'document_id': 'test'}),
            content_type='application/json'
        )
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        # Process through middleware chain
        request_middleware = APIRequestMiddleware()
        timeout_middleware = TimeoutHandlerMiddleware()
        rate_limit_middleware = APIRateLimitMiddleware()
        response_middleware = APIResponseMiddleware()
        
        # Process request
        request_middleware.process_request(request)
        timeout_middleware.process_request(request)
        rate_limit_middleware.process_request(request)
        
        # Verify request attributes
        self.assertTrue(hasattr(request, 'api_request_id'))
        self.assertTrue(hasattr(request, 'timeout_config'))
        self.assertEqual(request.operation_type, 'redact')
        
        # Process response
        response = JsonResponse({'status': 'success'})
        timeout_middleware.process_response(request, response)
        final_response = response_middleware.process_response(request, response)
        
        # Verify response headers
        self.assertIn('X-Request-ID', final_response)
        self.assertIn('X-Processing-Time', final_response)
        self.assertEqual(final_response['X-Content-Type-Options'], 'nosniff')
        
    def test_middleware_error_handling_integration(self):
        """Test error handling across middleware."""
        request = self.factory.post('/api/test/')
        request.api_request_id = str(uuid.uuid4())
        
        error_middleware = APIErrorHandlerMiddleware()
        response_middleware = APIResponseMiddleware()
        
        # Simulate exception
        exception = APIError("Test error", "TEST_ERROR", 400)
        error_response = error_middleware.process_exception(request, exception)
        
        # Process error response through response middleware
        final_response = response_middleware.process_response(request, error_response)
        
        # Verify error response structure
        response_data = json.loads(final_response.content)
        self.assertEqual(response_data['error'], 'TEST_ERROR')
        self.assertEqual(final_response['X-Request-ID'], request.api_request_id)


if __name__ == '__main__':
    pytest.main([__file__])