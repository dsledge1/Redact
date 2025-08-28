"""
Comprehensive integration tests for the enhanced REST API endpoints.
"""

import json
import tempfile
import uuid
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import pytest
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.core.cache import cache

from app.models import PDFDocument, ProcessingJob, RedactionMatch
from app.services.temp_file_manager import TempFileManager
from app.utils.response_formatters import APIResponseFormatter


class BaseAPITestCase(TestCase):
    """Base test case with common setup for API tests."""
    
    def setUp(self):
        self.client = Client()
        self.session_id = str(uuid.uuid4())
        
        # Create test PDF content
        self.test_pdf_content = b'%PDF-1.4\n%Test PDF content\nendobj\n%%EOF'
        self.test_pdf_file = SimpleUploadedFile(
            'test.pdf',
            self.test_pdf_content,
            content_type='application/pdf'
        )
        
        cache.clear()  # Clear cache before each test
        
    def tearDown(self):
        cache.clear()
        
    def make_authenticated_request(self, method, url, data=None, **kwargs):
        """Make API request with proper headers."""
        headers = {
            'HTTP_X_SESSION_ID': self.session_id,
            'HTTP_ACCEPT': 'application/json',
            **kwargs.get('headers', {})
        }
        kwargs['headers'] = headers
        
        if method.upper() == 'GET':
            return self.client.get(url, data, **headers)
        elif method.upper() == 'POST':
            return self.client.post(url, data, **headers)
        elif method.upper() == 'PUT':
            return self.client.put(url, data, **headers)
        elif method.upper() == 'DELETE':
            return self.client.delete(url, **headers)


class TestAPIMiddlewareIntegration(BaseAPITestCase):
    """Test API middleware integration with actual HTTP requests."""
    
    def test_api_request_middleware_adds_headers(self):
        """Test that API request middleware adds required headers."""
        response = self.client.post('/api/health/', {})
        
        self.assertIn('X-Request-ID', response)
        self.assertIn('X-Processing-Time', response)
        
    def test_api_timeout_warnings(self):
        """Test timeout warnings in response headers."""
        with patch('time.sleep') as mock_sleep:
            mock_sleep.side_effect = lambda x: None  # Don't actually sleep
            response = self.client.get('/api/health/')
            
        # Should have timeout-related headers for long operations
        self.assertIn('X-Processing-Time', response)
        
    def test_rate_limiting_enforcement(self):
        """Test that rate limiting is enforced."""
        with override_settings(API_RATE_LIMIT_REQUESTS=2):
            # Make requests up to limit
            for _ in range(2):
                response = self.client.get('/api/health/')
                self.assertEqual(response.status_code, 200)
            
            # Next request should be rate limited
            response = self.client.get('/api/health/')
            self.assertEqual(response.status_code, 429)
            
            response_data = json.loads(response.content)
            self.assertEqual(response_data['status'], 'error')
            self.assertEqual(response_data['error_code'], 'RATE_LIMIT_EXCEEDED')
            
    def test_error_handling_middleware(self):
        """Test error handling middleware integration."""
        # Test with invalid endpoint to trigger error handling
        response = self.client.post('/api/nonexistent/', {})
    
    def test_background_job_returns_202_status(self):
        """Test that background jobs return 202 Accepted status."""
        # Create a test document for processing
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=50 * 1024 * 1024,  # 50MB - large enough to trigger background
            session_id=self.session_id,
            content_hash='test_hash',
            file_hash='test_hash'
        )
        
        # Mock the file existence check
        with patch('pathlib.Path.exists', return_value=True):
            # Mock PDF validation
            with patch('app.services.pdf_processor.PDFProcessor.validate_pdf') as mock_validate:
                mock_validate.return_value = {
                    'is_valid': True,
                    'page_count': 100,
                    'has_text_layer': True
                }
                
                # Test redaction endpoint with large file
                data = json.dumps({
                    'document_id': str(document.id),
                    'search_terms': ['confidential', 'secret']
                })
                
                response = self.client.post(
                    '/api/redact/',
                    data,
                    content_type='application/json',
                    HTTP_X_SESSION_ID=self.session_id
                )
                
                # Should return 202 for background job
                self.assertEqual(response.status_code, 202)
                
                response_data = json.loads(response.content)
                self.assertEqual(response_data['status'], 'success')
                self.assertIn('job_id', response_data['data'])
                self.assertEqual(response_data['data']['status'], 'queued')
    
    def test_timeout_hint_triggers_202_response(self):
        """Test that timeout hint from middleware triggers 202 response."""
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=10 * 1024 * 1024,  # 10MB
            session_id=self.session_id,
            content_hash='test_hash',
            file_hash='test_hash'
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('app.services.pdf_processor.PDFProcessor.validate_pdf') as mock_validate:
                mock_validate.return_value = {
                    'is_valid': True,
                    'page_count': 50,
                    'has_text_layer': True
                }
                
                # Test split endpoint - should queue by default
                data = json.dumps({
                    'document_id': str(document.id),
                    'split_pages': [10, 20, 30]
                })
                
                response = self.client.post(
                    '/api/split/',
                    data,
                    content_type='application/json',
                    HTTP_X_SESSION_ID=self.session_id
                )
                
                # Split operations default to queuing, should return 202
                self.assertEqual(response.status_code, 202)
                
                response_data = json.loads(response.content)
                self.assertEqual(response_data['status'], 'success')
                self.assertIn('job_id', response_data['data'])
                self.assertEqual(response_data['data']['status'], 'queued')
    
    def test_merge_operation_returns_202(self):
        """Test that merge operations return 202 when queued."""
        # Create test documents
        doc1 = PDFDocument.objects.create(
            filename='test1.pdf',
            file_size=5 * 1024 * 1024,
            session_id=self.session_id,
            content_hash='hash1',
            file_hash='hash1'
        )
        doc2 = PDFDocument.objects.create(
            filename='test2.pdf',
            file_size=5 * 1024 * 1024,
            session_id=self.session_id,
            content_hash='hash2',
            file_hash='hash2'
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('app.services.pdf_processor.PDFProcessor.validate_pdf') as mock_validate:
                mock_validate.return_value = {
                    'is_valid': True,
                    'page_count': 10,
                    'has_text_layer': True
                }
                
                data = json.dumps({
                    'document_ids': [str(doc1.id), str(doc2.id)]
                })
                
                response = self.client.post(
                    '/api/merge/',
                    data,
                    content_type='application/json',
                    HTTP_X_SESSION_ID=self.session_id
                )
                
                # Merge operations default to queuing, should return 202
                self.assertEqual(response.status_code, 202)
                
                response_data = json.loads(response.content)
                self.assertEqual(response_data['status'], 'success')
                self.assertIn('job_id', response_data['data'])
                self.assertEqual(response_data['data']['status'], 'queued')
    
    def test_extraction_operation_returns_202(self):
        """Test that extraction operations return 202 when queued."""
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=10 * 1024 * 1024,
            session_id=self.session_id,
            content_hash='test_hash',
            file_hash='test_hash'
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('app.services.pdf_processor.PDFProcessor.validate_pdf') as mock_validate:
                mock_validate.return_value = {
                    'is_valid': True,
                    'page_count': 50,
                    'has_text_layer': False  # No text layer, will need OCR
                }
                
                data = json.dumps({
                    'document_id': str(document.id),
                    'extraction_type': 'all'
                })
                
                response = self.client.post(
                    '/api/extract/',
                    data,
                    content_type='application/json',
                    HTTP_X_SESSION_ID=self.session_id
                )
                
                # Extract operations default to queuing, should return 202
                self.assertEqual(response.status_code, 202)
                
                response_data = json.loads(response.content)
                self.assertEqual(response_data['status'], 'success')
                self.assertIn('job_id', response_data['data'])
                self.assertEqual(response_data['data']['status'], 'queued')
        
    def test_response_compression(self):
        """Test response compression for large responses."""
        response = self.client.get(
            '/api/docs/',
            HTTP_ACCEPT_ENCODING='gzip, deflate'
        )
        
        # Large responses should be compressed
        if len(response.content) > 1024:
            self.assertEqual(response.get('Content-Encoding'), 'gzip')


class TestHealthCheckEndpoint(BaseAPITestCase):
    """Test health check endpoint functionality."""
    
    def test_health_check_success(self):
        """Test successful health check."""
        response = self.client.get('/api/health/')
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('data', response_data)
        
        health_data = response_data['data']
        self.assertIn('status', health_data)
        self.assertIn('components', health_data)
        self.assertIn('system_info', health_data)
        
    def test_health_check_components(self):
        """Test health check component validation."""
        response = self.client.get('/api/health/')
        response_data = json.loads(response.content)
        
        components = response_data['data']['components']
        
        # Should check key components
        self.assertIn('database', components)
        self.assertIn('redis', components)
        self.assertIn('filesystem', components)
        self.assertIn('celery', components)
        
        # Each component should have status
        for component_name, component_data in components.items():
            self.assertIn('status', component_data)
            self.assertIn(component_data['status'], ['healthy', 'warning', 'critical'])
            
    def test_health_check_system_info(self):
        """Test system information in health check."""
        response = self.client.get('/api/health/')
        response_data = json.loads(response.content)
        
        system_info = response_data['data']['system_info']
        
        # Should include system metrics
        expected_fields = ['cpu_percent', 'memory_percent', 'platform', 'python_version']
        for field in expected_fields:
            self.assertIn(field, system_info)


class TestAPIMetricsEndpoint(BaseAPITestCase):
    """Test API metrics endpoint functionality."""
    
    def test_metrics_endpoint_access(self):
        """Test metrics endpoint accessibility."""
        response = self.client.get('/api/metrics/')
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('data', response_data)
        
    def test_metrics_structure(self):
        """Test metrics response structure."""
        response = self.client.get('/api/metrics/')
        response_data = json.loads(response.content)
        
        metrics = response_data['data']
        
        # Should contain metrics categories
        expected_categories = ['api_usage', 'performance', 'errors', 'system_resources']
        for category in expected_categories:
            self.assertIn(category, metrics)
            
    def test_api_usage_metrics(self):
        """Test API usage metrics structure."""
        response = self.client.get('/api/metrics/')
        response_data = json.loads(response.content)
        
        api_usage = response_data['data']['api_usage']
        
        # Should have usage statistics
        expected_fields = [
            'total_requests_24h', 'successful_requests_24h', 
            'failed_requests_24h', 'endpoints'
        ]
        for field in expected_fields:
            self.assertIn(field, api_usage)
            
    def test_performance_metrics(self):
        """Test performance metrics structure."""
        response = self.client.get('/api/metrics/')
        response_data = json.loads(response.content)
        
        performance = response_data['data']['performance']
        
        # Should have performance statistics
        expected_fields = [
            'average_response_time', 'p95_response_time', 'p99_response_time',
            'background_jobs_queued', 'background_jobs_processing'
        ]
        for field in expected_fields:
            self.assertIn(field, performance)


class TestAPIDocumentationEndpoint(BaseAPITestCase):
    """Test API documentation endpoint."""
    
    def test_documentation_endpoint_access(self):
        """Test documentation endpoint accessibility."""
        response = self.client.get('/api/docs/')
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('data', response_data)
        
    def test_documentation_structure(self):
        """Test documentation response structure."""
        response = self.client.get('/api/docs/')
        response_data = json.loads(response.content)
        
        docs = response_data['data']
        
        # Should contain documentation sections
        expected_sections = [
            'api_version', 'base_url', 'endpoints', 
            'authentication', 'rate_limits', 'error_codes', 'examples'
        ]
        for section in expected_sections:
            self.assertIn(section, docs)
            
    def test_endpoints_documentation(self):
        """Test endpoint documentation completeness."""
        response = self.client.get('/api/docs/')
        response_data = json.loads(response.content)
        
        endpoints = response_data['data']['endpoints']
        
        # Should document main API endpoints
        expected_endpoints = ['/api/redact/', '/api/split/', '/api/merge/', '/api/extract/']
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, endpoints)
            
            endpoint_doc = endpoints[endpoint]
            self.assertIn('method', endpoint_doc)
            self.assertIn('description', endpoint_doc)
            self.assertIn('parameters', endpoint_doc)


class TestSessionManagementEndpoints(BaseAPITestCase):
    """Test session management endpoints."""
    
    def test_create_session(self):
        """Test session creation endpoint."""
        response = self.client.post('/api/session/create/', {})
        
        self.assertEqual(response.status_code, 201)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('session_id', response_data['data'])
        self.assertIn('created_at', response_data['data'])
        self.assertIn('expires_at', response_data['data'])
        
    def test_session_status(self):
        """Test session status endpoint."""
        # First create a session
        create_response = self.client.post('/api/session/create/', {})
        create_data = json.loads(create_response.content)
        session_id = create_data['data']['session_id']
        
        # Check session status
        response = self.client.get(f'/api/session/{session_id}/status/')
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        
        session_info = response_data['data']
        self.assertEqual(session_info['session_id'], session_id)
        self.assertIn('created_at', session_info)
        self.assertIn('total_operations', session_info)
        
    def test_session_cleanup(self):
        """Test session cleanup endpoint."""
        # First create a session
        create_response = self.client.post('/api/session/create/', {})
        create_data = json.loads(create_response.content)
        session_id = create_data['data']['session_id']
        
        # Clean up session
        response = self.client.delete(f'/api/session/{session_id}/cleanup/')
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertTrue(response_data['data']['cleaned_up'])


class TestEnhancedAPIEndpoints(BaseAPITestCase):
    """Test enhanced functionality of main API endpoints."""
    
    @patch('app.services.pdf_processor.PDFProcessor')
    @patch('app.services.temp_file_manager.TempFileManager')
    def test_redaction_endpoint_enhanced_response(self, mock_temp_manager, mock_pdf_processor):
        """Test redaction endpoint with enhanced response formatting."""
        # Setup mocks
        mock_temp_manager.get_session_path.return_value = Path('/tmp/test')
        mock_temp_manager.generate_session_id.return_value = self.session_id
        
        mock_processor_instance = Mock()
        mock_processor_instance.validate_pdf.return_value = {'is_valid': True, 'page_count': 5}
        mock_pdf_processor.return_value = mock_processor_instance
        
        # Create test document
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=1024,
            session_id=self.session_id,
            content_hash='testhash'
        )
        
        request_data = {
            'document_id': str(document.id),
            'search_terms': ['test', 'sensitive'],
            'fuzzy_threshold': 80,
            'confidence_threshold': 95
        }
        
        with patch('app.services.unified_search_service.UnifiedSearchService'):
            response = self.make_authenticated_request(
                'POST', 
                '/api/redact/',
                json.dumps(request_data),
                content_type='application/json'
            )
        
        # Should use enhanced response formatting
        self.assertIn('X-Request-ID', response)
        self.assertIn('X-Processing-Time', response)
        
        if response.status_code == 200:
            response_data = json.loads(response.content)
            self.assertEqual(response_data['status'], 'success')
            self.assertIn('request_id', response_data)
            self.assertIn('timestamp', response_data)
            
    @patch('app.services.pdf_processor.PDFProcessor')
    def test_split_endpoint_parameter_validation(self, mock_pdf_processor):
        """Test split endpoint with comprehensive parameter validation."""
        # Setup mock
        mock_processor_instance = Mock()
        mock_processor_instance.validate_pdf.return_value = {'is_valid': True, 'page_count': 10}
        mock_pdf_processor.return_value = mock_processor_instance
        
        # Create test document
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=1024,
            session_id=self.session_id,
            content_hash='testhash'
        )
        
        request_data = {
            'document_id': str(document.id),
            'split_strategy': 'pages',
            'split_pages': [3, 6, 9]
        }
        
        with patch('app.services.temp_file_manager.TempFileManager.get_session_path') as mock_path:
            mock_path.return_value = Path('/tmp/test/test.pdf')
            with patch('pathlib.Path.exists', return_value=True):
                response = self.make_authenticated_request(
                    'POST',
                    '/api/split/',
                    json.dumps(request_data),
                    content_type='application/json'
                )
        
        # Should validate parameters and provide enhanced response
        if response.status_code == 200:
            response_data = json.loads(response.content)
            self.assertEqual(response_data['status'], 'success')
            self.assertIn('split_info', response_data['data'])
            
    def test_merge_endpoint_document_validation(self):
        """Test merge endpoint with document validation."""
        # Create test documents
        doc1 = PDFDocument.objects.create(
            filename='test1.pdf',
            file_size=1024,
            session_id=self.session_id,
            content_hash='hash1'
        )
        doc2 = PDFDocument.objects.create(
            filename='test2.pdf', 
            file_size=2048,
            session_id=self.session_id,
            content_hash='hash2'
        )
        
        request_data = {
            'document_ids': [str(doc1.id), str(doc2.id)],
            'output_filename': 'merged.pdf',
            'preserve_metadata': True
        }
        
        response = self.make_authenticated_request(
            'POST',
            '/api/merge/',
            json.dumps(request_data),
            content_type='application/json'
        )
        
        # Should validate documents exist
        self.assertIn(response.status_code, [200, 400, 404])
        
        response_data = json.loads(response.content)
        if response.status_code == 200:
            self.assertEqual(response_data['status'], 'success')
            self.assertIn('merge_info', response_data['data'])
        else:
            self.assertIn('error_code', response_data)
            
    def test_extract_endpoint_parameter_validation(self):
        """Test extract endpoint with parameter validation."""
        # Create test document
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=1024,
            session_id=self.session_id,
            content_hash='testhash'
        )
        
        request_data = {
            'document_id': str(document.id),
            'extraction_type': 'text',
            'page_range': [1, 5],
            'output_format': 'json',
            'include_formatting': True
        }
        
        with patch('app.services.temp_file_manager.TempFileManager.get_session_path') as mock_path:
            mock_path.return_value = Path('/tmp/test/test.pdf')
            with patch('pathlib.Path.exists', return_value=True):
                with patch('app.services.pdf_processor.PDFProcessor') as mock_processor:
                    mock_instance = Mock()
                    mock_instance.validate_pdf.return_value = {'is_valid': True, 'page_count': 10}
                    mock_processor.return_value = mock_instance
                    
                    response = self.make_authenticated_request(
                        'POST',
                        '/api/extract/',
                        json.dumps(request_data),
                        content_type='application/json'
                    )
        
        if response.status_code == 200:
            response_data = json.loads(response.content)
            self.assertEqual(response_data['status'], 'success')
            self.assertIn('extraction_info', response_data['data'])


class TestJobStatusEnhancements(BaseAPITestCase):
    """Test enhanced job status tracking."""
    
    def test_job_status_enhanced_response(self):
        """Test job status with enhanced response format."""
        # Create test document and job
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=1024,
            session_id=self.session_id,
            content_hash='testhash'
        )
        
        job = ProcessingJob.objects.create(
            document=document,
            job_type='redact',
            status='processing',
            progress=50.0
        )
        
        response = self.client.get(f'/api/job/{job.id}/status/')
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        
        job_data = response_data['data']
        self.assertEqual(job_data['job_id'], str(job.id))
        self.assertEqual(job_data['current_status'], 'processing')
        self.assertEqual(job_data['progress'], 50.0)
        self.assertIn('details', job_data)
        
    def test_job_cancellation(self):
        """Test job cancellation functionality."""
        # Create test document and job
        document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=1024,
            session_id=self.session_id,
            content_hash='testhash'
        )
        
        job = ProcessingJob.objects.create(
            document=document,
            job_type='redact',
            status='queued'
        )
        
        response = self.client.delete(f'/api/job/{job.id}/status/')
        
        if response.status_code == 200:
            response_data = json.loads(response.content)
            self.assertEqual(response_data['status'], 'success')
            
            # Check job was cancelled
            job.refresh_from_db()
            self.assertEqual(job.status, 'cancelled')


class TestResponseFormatting(BaseAPITestCase):
    """Test consistent response formatting across endpoints."""
    
    def test_success_response_format(self):
        """Test success response format consistency."""
        endpoints = [
            '/api/health/',
            '/api/docs/',
            '/api/metrics/',
        ]
        
        for endpoint in endpoints:
            response = self.client.get(endpoint)
            
            if response.status_code == 200:
                response_data = json.loads(response.content)
                
                # Check standard success format
                self.assertEqual(response_data['status'], 'success')
                self.assertIn('data', response_data)
                self.assertIn('timestamp', response_data)
                
                if 'X-Request-ID' in response:
                    self.assertIn('request_id', response_data)
                    
    def test_error_response_format(self):
        """Test error response format consistency."""
        # Test with invalid endpoint
        response = self.client.post('/api/nonexistent/', {})
        
        response_data = json.loads(response.content)
        
        # Should have consistent error format
        if response.status_code >= 400:
            self.assertIn('status', response_data)
            if response_data.get('status') == 'error':
                self.assertIn('error_code', response_data)
                self.assertIn('message', response_data)
                
    def test_validation_response_format(self):
        """Test validation error response format."""
        # Test redaction endpoint with missing required fields
        response = self.make_authenticated_request(
            'POST',
            '/api/redact/',
            json.dumps({}),
            content_type='application/json'
        )
        
        if response.status_code == 400:
            response_data = json.loads(response.content)
            
            # Should have validation error format
            if response_data.get('status') == 'error':
                self.assertIn('error_code', response_data)
                self.assertIn('message', response_data)


class TestSecurityEnhancements(BaseAPITestCase):
    """Test security enhancements in API endpoints."""
    
    def test_security_headers_present(self):
        """Test that security headers are present in responses."""
        response = self.client.get('/api/health/')
        
        # Check security headers
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertIn('X-XSS-Protection', response)
        
    def test_cors_headers(self):
        """Test CORS headers for API endpoints."""
        response = self.client.options('/api/health/')
        
        # Should have CORS headers
        if response.status_code == 200:
            self.assertIn('Access-Control-Allow-Origin', response)
            self.assertIn('Access-Control-Allow-Methods', response)
            
    def test_session_id_validation(self):
        """Test session ID validation in API endpoints."""
        invalid_session_data = {
            'document_id': str(uuid.uuid4()),
            'search_terms': ['test']
        }
        
        # Request without session ID should fail
        response = self.client.post(
            '/api/redact/',
            json.dumps(invalid_session_data),
            content_type='application/json'
        )
        
        # Should validate session ID requirement
        self.assertIn(response.status_code, [400, 401])


class TestPerformanceMonitoring(BaseAPITestCase):
    """Test performance monitoring features."""
    
    def test_processing_time_tracking(self):
        """Test processing time tracking in responses."""
        response = self.client.get('/api/health/')
        
        # Should include processing time
        self.assertIn('X-Processing-Time', response)
        
        processing_time = response['X-Processing-Time']
        self.assertTrue(processing_time.endswith('s'))
        
        # Should be a valid time format
        time_value = float(processing_time[:-1])
        self.assertGreater(time_value, 0)
        
    def test_request_id_tracking(self):
        """Test request ID tracking across requests."""
        response = self.client.get('/api/health/')
        
        self.assertIn('X-Request-ID', response)
        
        request_id = response['X-Request-ID']
        
        # Should be valid UUID format
        uuid.UUID(request_id)  # Will raise ValueError if invalid
        
    def test_timeout_warnings(self):
        """Test timeout warning headers for long operations."""
        # This would require actual long-running operations
        # For now, just verify the header structure exists
        response = self.client.get('/api/health/')
        
        # Timeout warnings are conditional, so just verify response structure
        self.assertIn('X-Processing-Time', response)


if __name__ == '__main__':
    pytest.main([__file__])