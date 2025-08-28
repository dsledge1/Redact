"""
Comprehensive integration tests for the complete extraction workflow.

This test suite covers end-to-end extraction pipeline, API endpoint integration,
Celery task integration, service integration, file management integration,
and comprehensive extraction workflows.
"""

import pytest
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.test import APIClient

from app.models import PDFDocument, ProcessingJob
from app.services.pdf_processor import PDFProcessor
from app.utils.temp_file_manager import TempFileManager


class TestExtractionIntegration(TestCase):
    """Integration test cases for complete extraction workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = APIClient()
        self.session_id = "integration_test_session"
        
        # Create test PDF document
        self.test_document = PDFDocument.objects.create(
            filename="test_document.pdf",
            file_size=1024000,
            session_id=self.session_id,
            content_hash="test_hash_123",
            file_hash="test_hash_123"
        )
    
    def tearDown(self):
        """Clean up after tests."""
        # Clean up test files
        TempFileManager.cleanup_session(self.session_id)
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    @patch('tasks.process_pdf_extraction.delay')
    def test_end_to_end_table_extraction_pipeline(self, mock_task_delay, mock_validate_pdf):
        """Test complete table extraction pipeline from API to file download."""
        # Mock PDF validation
        mock_validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 5,
            'has_text_layer': True
        }
        
        # Mock file existence
        with patch('pathlib.Path.exists', return_value=True):
            # Step 1: Request table extraction via API
            response = self.client.post('/api/extract/', {
                'document_id': str(self.test_document.id),
                'extraction_type': 'tables',
                'csv_delimiter': ';',
                'table_extraction_method': 'camelot'
            })
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertTrue(response_data['success'])
        self.assertIn('job_id', response_data)
        self.assertEqual(response_data['extraction_info']['extraction_type'], 'tables')
        self.assertEqual(response_data['extraction_info']['extraction_parameters']['csv_delimiter'], ';')
        
        # Verify task was queued
        mock_task_delay.assert_called_once()
        args, kwargs = mock_task_delay.call_args
        self.assertEqual(args[0], str(self.test_document.id))
        self.assertEqual(args[2], 'tables')  # extraction_type
        self.assertIsNotNone(args[4])  # extraction_options
        
        # Step 2: Verify ProcessingJob was created
        job_id = response_data['job_id']
        job = ProcessingJob.objects.get(id=job_id)
        self.assertEqual(job.job_type, 'extract')
        self.assertEqual(job.processing_parameters['extraction_type'], 'tables')
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    @patch('tasks.process_pdf_extraction.delay')
    def test_end_to_end_image_extraction_pipeline(self, mock_task_delay, mock_validate_pdf):
        """Test complete image extraction pipeline."""
        mock_validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 10,
            'has_text_layer': False
        }
        
        with patch('pathlib.Path.exists', return_value=True):
            response = self.client.post('/api/extract/', {
                'document_id': str(self.test_document.id),
                'extraction_type': 'images',
                'image_format': 'JPEG',
                'image_quality': 85,
                'page_range': [3, 7]
            })
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['extraction_info']['extraction_parameters']['image_format'], 'JPEG')
        self.assertEqual(response_data['extraction_info']['extraction_parameters']['image_quality'], 85)
        self.assertEqual(response_data['extraction_info']['page_range'], [3, 7])
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')  
    @patch('tasks.process_pdf_extraction.delay')
    def test_end_to_end_comprehensive_extraction(self, mock_task_delay, mock_validate_pdf):
        """Test comprehensive extraction of all types."""
        mock_validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 25,
            'has_text_layer': True
        }
        
        with patch('pathlib.Path.exists', return_value=True):
            response = self.client.post('/api/extract/', {
                'document_id': str(self.test_document.id),
                'extraction_type': 'all',
                'output_format': 'json',
                'include_formatting': True,
                'csv_delimiter': '|',
                'image_format': 'PNG',
                'table_extraction_method': 'auto'
            })
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['extraction_info']['extraction_type'], 'all')
        
        # Verify all parameters were captured
        params = response_data['extraction_info']['extraction_parameters']
        self.assertEqual(params['csv_delimiter'], '|')
        self.assertEqual(params['image_format'], 'PNG')
        self.assertEqual(params['include_formatting'], True)
        self.assertEqual(params['table_extraction_method'], 'auto')
    
    def test_api_parameter_validation_invalid_extraction_type(self):
        """Test API parameter validation for invalid extraction type."""
        response = self.client.post('/api/extract/', {
            'document_id': str(self.test_document.id),
            'extraction_type': 'invalid_type'
        })
        
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn('Invalid extraction type', response_data['error'])
    
    def test_api_parameter_validation_invalid_csv_delimiter(self):
        """Test API parameter validation for invalid CSV delimiter."""
        response = self.client.post('/api/extract/', {
            'document_id': str(self.test_document.id),
            'extraction_type': 'tables',
            'csv_delimiter': 'invalid'  # Must be single character
        })
        
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn('CSV delimiter must be a single character', response_data['error'])
    
    def test_api_parameter_validation_invalid_image_quality(self):
        """Test API parameter validation for invalid image quality."""
        response = self.client.post('/api/extract/', {
            'document_id': str(self.test_document.id),
            'extraction_type': 'images',
            'image_quality': 150  # Must be 1-100
        })
        
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn('Image quality must be between 1 and 100', response_data['error'])
    
    def test_api_parameter_validation_invalid_combination(self):
        """Test API parameter validation for invalid parameter combinations."""
        response = self.client.post('/api/extract/', {
            'document_id': str(self.test_document.id),
            'extraction_type': 'text',
            'csv_delimiter': ';'  # Only valid for table extraction
        })
        
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn('CSV delimiter is only valid for table extraction', response_data['error'])
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    def test_api_invalid_pdf_handling(self, mock_validate_pdf):
        """Test handling of invalid PDF files."""
        mock_validate_pdf.return_value = {
            'is_valid': False,
            'error': 'Corrupted PDF file'
        }
        
        with patch('pathlib.Path.exists', return_value=True):
            response = self.client.post('/api/extract/', {
                'document_id': str(self.test_document.id),
                'extraction_type': 'text'
            })
        
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn('PDF processing error', response_data['error'])
    
    def test_api_file_not_found_handling(self):
        """Test handling when document file is not found."""
        with patch('pathlib.Path.exists', return_value=False):
            response = self.client.post('/api/extract/', {
                'document_id': str(self.test_document.id),
                'extraction_type': 'text'
            })
        
        self.assertEqual(response.status_code, 404)
        response_data = response.json()
        self.assertIn('Document file not found', response_data['error'])
    
    def test_api_document_not_found(self):
        """Test handling when document doesn't exist in database."""
        response = self.client.post('/api/extract/', {
            'document_id': '00000000-0000-0000-0000-000000000000',
            'extraction_type': 'text'
        })
        
        self.assertEqual(response.status_code, 404)
    
    @patch('app.services.table_extraction_service.TableExtractionService.extract_tables')
    def test_celery_task_table_extraction_success(self, mock_extract_tables):
        """Test Celery task for table extraction success scenario."""
        from tasks import process_pdf_extraction
        
        # Mock successful table extraction
        mock_extract_tables.return_value = {
            'success': True,
            'tables': [{'page': 1, 'rows': 10, 'columns': 4}],
            'files': [{'filename': 'table_1.csv', 'file_size': 2048}],
            'statistics': {'tables_detected': 1, 'extraction_method': 'camelot'}
        }
        
        # Create processing job
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='queued',
            processing_parameters={
                'extraction_type': 'tables',
                'csv_delimiter': ',',
                'table_extraction_method': 'auto'
            }
        )
        
        # Mock file existence
        with patch('pathlib.Path.exists', return_value=True):
            result = process_pdf_extraction(
                str(self.test_document.id),
                str(job.id),
                'tables',
                None,
                {'csv_delimiter': ',', 'table_extraction_method': 'auto'}
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_type'], 'tables')
        
        # Verify job was updated
        job.refresh_from_db()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.progress, 100)
        self.assertIsNotNone(job.results)
    
    @patch('app.services.image_extraction_service.ImageExtractionService.extract_images')
    def test_celery_task_image_extraction_success(self, mock_extract_images):
        """Test Celery task for image extraction success scenario."""
        from tasks import process_pdf_extraction
        
        mock_extract_images.return_value = {
            'success': True,
            'images': [{'filename': 'image_1.png', 'page': 1, 'file_size': 5120}],
            'files': [{'filename': 'image_1.png', 'file_size': 5120}],
            'statistics': {'embedded_images_extracted': 1, 'format_conversions': 0}
        }
        
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='queued',
            processing_parameters={
                'extraction_type': 'images',
                'image_format': 'PNG',
                'image_quality': 95
            }
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            result = process_pdf_extraction(
                str(self.test_document.id),
                str(job.id),
                'images',
                [1, 5],
                {'image_format': 'PNG', 'image_quality': 95}
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_type'], 'images')
        
        job.refresh_from_db()
        self.assertEqual(job.status, 'completed')
    
    @patch('app.services.pdf_processor.PDFProcessor.extract_comprehensive')
    def test_celery_task_comprehensive_extraction(self, mock_extract_comprehensive):
        """Test Celery task for comprehensive extraction."""
        from tasks import process_pdf_extraction
        
        mock_extract_comprehensive.return_value = {
            'success': True,
            'results': {
                'text': {'success': True, 'pages': 5},
                'tables': {'success': True, 'tables': [{'page': 2}]},
                'images': {'success': True, 'images': [{'page': 3}]},
                'metadata': {'success': True, 'completeness_score': 0.9}
            },
            'all_files': [
                {'filename': 'text_output.json', 'type': 'text'},
                {'filename': 'table_1.csv', 'type': 'table'},
                {'filename': 'image_1.png', 'type': 'image'},
                {'filename': 'metadata.json', 'type': 'metadata'}
            ],
            'extraction_summary': {
                'services_used': ['text_extraction', 'table_extraction', 'image_extraction', 'metadata_extraction'],
                'services_successful': 4,
                'total_files_created': 4
            }
        }
        
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='queued',
            processing_parameters={'extraction_type': 'all'}
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            result = process_pdf_extraction(
                str(self.test_document.id),
                str(job.id),
                'all',
                None,
                {}
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_type'], 'all')
        
        job.refresh_from_db()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.results['result']['extraction_summary']['services_successful'], 4)
    
    def test_celery_task_job_not_found(self):
        """Test Celery task handling when job is not found."""
        from tasks import process_pdf_extraction
        
        result = process_pdf_extraction(
            str(self.test_document.id),
            '00000000-0000-0000-0000-000000000000',  # Non-existent job
            'text',
            None,
            {}
        )
        
        self.assertFalse(result['success'])
        self.assertIn('Job', result['error'])
        self.assertIn('not found', result['error'])
    
    def test_celery_task_document_not_found(self):
        """Test Celery task handling when document is not found."""
        from tasks import process_pdf_extraction
        
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='queued'
        )
        
        result = process_pdf_extraction(
            '00000000-0000-0000-0000-000000000000',  # Non-existent document
            str(job.id),
            'text',
            None,
            {}
        )
        
        self.assertFalse(result['success'])
        self.assertIn('Document', result['error'])
        self.assertIn('not found', result['error'])
    
    @patch('app.services.table_extraction_service.TableExtractionService.extract_tables')
    def test_celery_task_extraction_failure(self, mock_extract_tables):
        """Test Celery task handling of extraction failures."""
        from tasks import process_pdf_extraction
        
        mock_extract_tables.return_value = {
            'success': False,
            'error': 'Table extraction failed due to PDF corruption',
            'tables': [],
            'files': []
        }
        
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='queued'
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            result = process_pdf_extraction(
                str(self.test_document.id),
                str(job.id),
                'tables',
                None,
                {}
            )
        
        self.assertFalse(result['success'])
        
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertIn('Table extraction failed', job.error_messages[0])
    
    @patch('app.services.pdf_processor.PDFProcessor')
    def test_service_integration_pdf_processor_with_table_service(self, mock_pdf_processor_class):
        """Test integration between PDFProcessor and TableExtractionService."""
        mock_processor = Mock()
        mock_pdf_processor_class.return_value = mock_processor
        
        # Mock table extraction result
        mock_processor.extract_tables.return_value = {
            'success': True,
            'tables': [{'page': 1, 'confidence': 0.95}],
            'statistics': {'extraction_method': 'camelot', 'tables_detected': 1}
        }
        
        processor = PDFProcessor(self.session_id)
        
        with patch('pathlib.Path.exists', return_value=True):
            result = processor.extract_tables(
                Path('test.pdf'),
                extraction_method='camelot'
            )
        
        self.assertTrue(result['success'])
        mock_processor.extract_tables.assert_called_once()
    
    @patch('app.utils.temp_file_manager.TempFileManager')
    def test_file_management_integration_downloads_organization(self, mock_temp_manager_class):
        """Test integration with TempFileManager for file organization."""
        mock_temp_manager = Mock()
        mock_temp_manager_class.return_value = mock_temp_manager
        
        # Mock downloads directory
        mock_downloads_dir = Path('/tmp/test_session/downloads')
        mock_temp_manager.downloads_dir = mock_downloads_dir
        
        from app.services.table_extraction_service import TableExtractionService
        
        service = TableExtractionService(self.session_id)
        
        # Verify TempFileManager integration
        self.assertEqual(service.temp_file_manager, mock_temp_manager)
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    @patch('app.services.table_extraction_service.TableExtractionService.extract_tables')
    @patch('app.services.image_extraction_service.ImageExtractionService.extract_images')  
    @patch('app.services.metadata_extraction_service.MetadataExtractionService.extract_metadata')
    def test_comprehensive_extraction_workflow_large_document(self, mock_metadata, mock_images, mock_tables, mock_validate):
        """Test comprehensive extraction workflow with large document."""
        # Mock PDF validation for large document
        mock_validate.return_value = {
            'is_valid': True,
            'page_count': 150,
            'has_text_layer': True,
            'file_size_mb': 45
        }
        
        # Mock successful extractions
        mock_tables.return_value = {
            'success': True,
            'tables': [{'page': i, 'rows': 10, 'columns': 5} for i in range(1, 11)],  # 10 tables
            'files': [{'filename': f'table_{i}.csv'} for i in range(1, 11)],
            'statistics': {'tables_detected': 10, 'extraction_method': 'camelot'}
        }
        
        mock_images.return_value = {
            'success': True,
            'images': [{'page': i, 'format': 'PNG'} for i in range(5, 26)],  # 21 images
            'files': [{'filename': f'image_{i}.png'} for i in range(5, 26)],
            'statistics': {'embedded_images_extracted': 21, 'format_conversions': 5}
        }
        
        mock_metadata.return_value = {
            'success': True,
            'metadata': {'title': 'Large Test Document', 'page_count': 150},
            'files': [{'filename': 'metadata.json'}],
            'validation': {'completeness_score': 0.95}
        }
        
        processor = PDFProcessor(self.session_id)
        
        with patch('pathlib.Path.exists', return_value=True):
            result = processor.extract_comprehensive(
                Path('large_document.pdf'),
                extraction_options={
                    'csv_delimiter': ',',
                    'image_format': 'PNG',
                    'include_content_analysis': True
                }
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['extraction_summary']['services_used']), 4)  # All services
        self.assertEqual(result['extraction_summary']['total_files_created'], 32)  # 10 + 21 + 1
    
    def test_extraction_result_file_organization_and_validation(self):
        """Test that extraction results are properly organized and validated."""
        from app.utils.extraction_utils import organize_extraction_files, validate_extraction_output
        
        # Create temporary test files
        temp_files = []
        for i in range(3):
            temp_file = tempfile.NamedTemporaryFile(suffix=f'_test_{i}.csv', delete=False)
            temp_file.write(b'col1,col2\nval1,val2\n')
            temp_file.close()
            temp_files.append(Path(temp_file.name))
        
        try:
            # Test file organization
            organization_result = organize_extraction_files(
                self.session_id,
                'tables',
                temp_files
            )
            
            self.assertTrue(organization_result['success'])
            self.assertEqual(organization_result['total_files_organized'], 3)
            
            # Test file validation
            validation_result = validate_extraction_output(temp_files, 'tables')
            
            self.assertTrue(validation_result['valid'])
            self.assertEqual(validation_result['valid_files'], 3)
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()
    
    def test_extraction_error_handling_and_recovery(self):
        """Test error handling and recovery mechanisms."""
        from app.utils.extraction_utils import format_extraction_errors, cleanup_failed_extraction
        
        # Test error formatting
        test_errors = [
            Exception("Table detection failed"),
            Exception("Memory allocation error"),
            ValueError("Invalid parameter")
        ]
        
        formatted_errors = format_extraction_errors(test_errors, 'tables')
        
        self.assertEqual(formatted_errors['error_count'], 3)
        self.assertEqual(formatted_errors['extraction_type'], 'tables')
        self.assertIsNotNone(formatted_errors['error_summary'])
        self.assertTrue(len(formatted_errors['recovery_suggestions']) > 0)
        
        # Test cleanup of failed extraction
        cleanup_result = cleanup_failed_extraction(self.session_id, 'tables')
        
        # Should succeed even if no files to clean up
        self.assertTrue(cleanup_result)
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    def test_extraction_performance_with_realistic_document_sizes(self, mock_validate):
        """Test extraction performance considerations with realistic document sizes."""
        from app.utils.extraction_utils import estimate_extraction_time
        
        # Test time estimation for different scenarios
        small_doc_time = estimate_extraction_time(1024000, 5, 'text')  # 1MB, 5 pages
        medium_doc_time = estimate_extraction_time(10240000, 25, 'tables')  # 10MB, 25 pages
        large_doc_time = estimate_extraction_time(52428800, 100, 'all')  # 50MB, 100 pages
        
        self.assertLess(small_doc_time, medium_doc_time)
        self.assertLess(medium_doc_time, large_doc_time)
        self.assertLessEqual(large_doc_time, 1800)  # Max 30 minutes
    
    def test_extraction_workflow_with_mixed_content_types(self):
        """Test extraction workflow with documents containing mixed content types."""
        from app.utils.extraction_utils import validate_extraction_parameters, format_extraction_results
        
        # Test parameter validation for comprehensive extraction
        mixed_params = {
            'extraction_type': 'all',
            'page_range': [1, 50],
            'csv_delimiter': '|',
            'image_format': 'JPEG',
            'image_quality': 80,
            'output_format': 'json',
            'include_formatting': True,
            'table_extraction_method': 'auto'
        }
        
        validation_result = validate_extraction_parameters('all', mixed_params)
        
        self.assertTrue(validation_result['valid'])
        self.assertEqual(len(validation_result['errors']), 0)
        
        # Test result formatting for mixed content
        mixed_results = {
            'success': True,
            'results': {
                'text': {'success': True, 'total_words': 5000},
                'tables': {'success': True, 'tables': [{'rows': 10, 'columns': 4}]},
                'images': {'success': True, 'images': [{'format': 'JPEG', 'file_size': 102400}]},
                'metadata': {'success': True, 'completeness_score': 0.9}
            },
            'all_files': [
                {'filename': 'text.json', 'type': 'text'},
                {'filename': 'table_1.csv', 'type': 'table'},
                {'filename': 'image_1.jpg', 'type': 'image'},
                {'filename': 'metadata.json', 'type': 'metadata'}
            ],
            'extraction_summary': {
                'services_used': ['text_extraction', 'table_extraction', 'image_extraction', 'metadata_extraction'],
                'services_successful': 4,
                'total_files_created': 4
            }
        }
        
        formatted_result = format_extraction_results(mixed_results, 'all')
        
        self.assertTrue(formatted_result['success'])
        self.assertEqual(formatted_result['extraction_type'], 'all')
        self.assertEqual(formatted_result['statistics']['services_successful'], 4)
        self.assertEqual(len(formatted_result['files_created']), 4)
    
    def test_job_status_tracking_throughout_extraction(self):
        """Test job status tracking and progress updates throughout extraction process."""
        # Create a processing job
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='queued',
            progress=0,
            processing_parameters={'extraction_type': 'tables'}
        )
        
        # Test job status API endpoint
        response = self.client.get(f'/api/status/{job.id}/')
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['job_id'], str(job.id))
        self.assertEqual(response_data['status'], 'queued')
        self.assertEqual(response_data['job_type'], 'extract')
        self.assertEqual(response_data['document_id'], str(self.test_document.id))
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    def test_extraction_capabilities_assessment(self, mock_validate):
        """Test extraction capabilities assessment in API response."""
        mock_validate.return_value = {
            'is_valid': True,
            'page_count': 20,
            'has_text_layer': False  # Requires OCR
        }
        
        with patch('pathlib.Path.exists', return_value=True):
            response = self.client.post('/api/extract/', {
                'document_id': str(self.test_document.id),
                'extraction_type': 'text'
            })
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        # Verify capabilities assessment is included
        self.assertIn('capabilities_assessment', response_data['extraction_info'])
        capabilities = response_data['extraction_info']['capabilities_assessment']
        
        self.assertIn('text_extraction', capabilities)
        self.assertEqual(capabilities['text_extraction']['method'], 'ocr_required')
        self.assertEqual(capabilities['text_extraction']['confidence'], 'medium')
    
    def test_extraction_with_resource_usage_monitoring(self):
        """Test extraction with resource usage monitoring and limits."""
        # Create a job and test resource usage info
        job = ProcessingJob.objects.create(
            document=self.test_document,
            job_type='extract',
            status='processing'
        )
        
        # Test the resource usage monitoring method
        with patch('app.utils.temp_file_manager.TempFileManager.get_session_info') as mock_session_info:
            mock_session_info.return_value = {
                'total_size_mb': 25.5,
                'uploads': {'count': 3},
                'processing': {'count': 5},
                'downloads': {'count': 12}
            }
            
            response = self.client.get(f'/api/status/{job.id}/')
            
            self.assertEqual(response.status_code, 200)
            response_data = response.json()
            
            self.assertIn('resource_usage', response_data)
            self.assertEqual(response_data['resource_usage']['session_disk_usage_mb'], 25.5)
            self.assertEqual(response_data['resource_usage']['session_file_count'], 20)  # 3+5+12
    
    @patch('app.services.pdf_processor.PDFProcessor.validate_pdf')
    @patch('app.services.pdf_processor.PDFProcessor.extract_text')
    @patch('app.services.pdf_processor.PDFProcessor.extract_tables')
    @patch('app.services.pdf_processor.PDFProcessor.extract_images_enhanced')  
    @patch('app.services.pdf_processor.PDFProcessor.extract_metadata_structured')
    def test_comprehensive_extraction_partial_failure(self, mock_metadata, mock_images, mock_tables, mock_text, mock_validate):
        """Test comprehensive extraction with partial failures - some services succeed, others fail."""
        # Mock PDF validation
        mock_validate.return_value = {
            'is_valid': True,
            'page_count': 20,
            'has_text_layer': True
        }
        
        # Mock text extraction - SUCCESS
        mock_text.return_value = {
            'success': True,
            'pages': [{'page_number': 1, 'text': 'Sample text', 'char_count': 11}],
            'total_pages': 1,
            'has_text': True,
            'files': [{'filename': 'text_output.json', 'file_path': '/path/to/text_output.json'}]
        }
        
        # Mock table extraction - FAILURE
        mock_tables.return_value = {
            'success': False,
            'error': 'No tables detected in document',
            'tables': [],
            'files': []
        }
        
        # Mock image extraction - SUCCESS
        mock_images.return_value = {
            'success': True,
            'images': [{'filename': 'image_1.png', 'page': 2, 'file_size': 2048}],
            'files': [{'filename': 'image_1.png', 'file_path': '/path/to/image_1.png'}],
            'statistics': {'embedded_images_extracted': 1}
        }
        
        # Mock metadata extraction - FAILURE
        mock_metadata.return_value = {
            'success': False,
            'error': 'Metadata corruption detected',
            'metadata': {},
            'files': []
        }
        
        processor = PDFProcessor(self.session_id)
        
        with patch('pathlib.Path.exists', return_value=True):
            result = processor.extract_comprehensive(
                Path('test_document.pdf'),
                extraction_options={'csv_delimiter': ',', 'image_format': 'PNG'}
            )
        
        # Verify overall result structure
        self.assertTrue(result['success'])  # Should be True because some services succeeded
        self.assertTrue(result.get('partial_success', False))  # Should indicate partial success
        self.assertIn('warning', result)  # Should contain warning about failures
        
        # Verify all service keys are present in results
        self.assertIn('text', result['results'])
        self.assertIn('tables', result['results'])
        self.assertIn('images', result['results'])
        self.assertIn('metadata', result['results'])
        
        # Verify successful service results
        self.assertTrue(result['results']['text']['success'])
        self.assertEqual(len(result['results']['text']['pages']), 1)
        
        self.assertTrue(result['results']['images']['success'])
        self.assertEqual(len(result['results']['images']['images']), 1)
        
        # Verify failed service results have success=False and errors
        self.assertFalse(result['results']['tables']['success'])
        self.assertEqual(result['results']['tables']['error'], 'No tables detected in document')
        self.assertEqual(result['results']['tables']['tables'], [])
        self.assertEqual(result['results']['tables']['files'], [])
        
        self.assertFalse(result['results']['metadata']['success'])
        self.assertEqual(result['results']['metadata']['error'], 'Metadata corruption detected')
        self.assertEqual(result['results']['metadata']['metadata'], {})
        self.assertEqual(result['results']['metadata']['files'], [])
        
        # Verify files_created aggregates only files from successful services
        self.assertEqual(len(result['files_created']), 2)  # text + image files
        file_names = [f['filename'] for f in result['files_created']]
        self.assertIn('text_output.json', file_names)
        self.assertIn('image_1.png', file_names)
        
        # Verify summary counts
        self.assertEqual(result['extraction_summary']['services_total'], 4)
        self.assertEqual(result['extraction_summary']['services_successful'], 2)
        self.assertEqual(result['extraction_summary']['services_failed'], 2)
        self.assertEqual(result['extraction_summary']['total_files_created'], 2)
        
        # Verify extraction errors are captured
        self.assertEqual(len(result['extraction_summary']['extraction_errors']), 2)
        error_messages = ' '.join(result['extraction_summary']['extraction_errors'])
        self.assertIn('Table extraction: No tables detected', error_messages)
        self.assertIn('Metadata extraction: Metadata corruption detected', error_messages)