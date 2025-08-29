"""
Comprehensive integration tests for the complete file upload/download workflow.

This module tests end-to-end workflows for PDF processing including upload,
redaction, splitting, merging, extraction, and download operations.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import uuid
import time

import pytest
from django.test import Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from app.models import Document, ProcessingJob, RedactionMatch
from app.services.pdf_processor import PDFProcessor
from app.services.fuzzy_matcher import FuzzyMatcher
from app.services.redaction_service import RedactionService
from .conftest import DocumentFactory, ProcessingJobFactory, RedactionMatchFactory


@pytest.mark.integration
class TestFileUploadWorkflow:
    """Test complete file upload workflow."""
    
    def test_successful_pdf_upload(self, api_client, simple_text_pdf, session_id):
        """Test successful PDF file upload with validation and processing."""
        # Prepare upload data
        uploaded_file = SimpleUploadedFile(
            "test_document.pdf",
            simple_text_pdf,
            content_type="application/pdf"
        )
        
        # Perform upload
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert 'document_id' in data
        assert 'filename' in data
        assert data['filename'] == 'test_document.pdf'
        
        # Verify database record
        document = Document.objects.get(id=data['document_id'])
        assert document.filename == 'test_document.pdf'
        assert document.session_id == session_id
        assert document.size > 0
        assert document.pages > 0
    
    def test_large_file_upload_performance(self, api_client, large_pdf, session_id, performance_timer):
        """Test large file upload performance and handling."""
        uploaded_file = SimpleUploadedFile(
            "large_document.pdf",
            large_pdf,
            content_type="application/pdf"
        )
        
        performance_timer.start()
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        performance_timer.stop()
        
        # Verify successful upload within reasonable time (< 30 seconds)
        assert response.status_code == 200
        assert performance_timer.elapsed < 30.0
        
        # Verify document metadata
        data = response.json()
        document = Document.objects.get(id=data['document_id'])
        assert document.pages >= 10  # Large PDF should have many pages
    
    def test_corrupted_file_upload_error(self, api_client, corrupted_pdf, session_id):
        """Test error handling for corrupted PDF upload."""
        uploaded_file = SimpleUploadedFile(
            "corrupted_document.pdf",
            corrupted_pdf,
            content_type="application/pdf"
        )
        
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        
        # Should return error for corrupted file
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'corrupted' in data['error'].lower() or 'invalid' in data['error'].lower()
    
    def test_invalid_file_type_upload(self, api_client, session_id):
        """Test upload error handling for invalid file types."""
        # Upload a text file instead of PDF
        uploaded_file = SimpleUploadedFile(
            "document.txt",
            b"This is not a PDF file",
            content_type="text/plain"
        )
        
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'pdf' in data['error'].lower() or 'format' in data['error'].lower()
    
    def test_oversized_file_upload(self, api_client, session_id):
        """Test handling of files exceeding size limits."""
        # Mock file size check without creating a huge buffer
        small_content = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n"
        
        # Create a small file and mock its size property
        uploaded_file = SimpleUploadedFile(
            "oversized.pdf",
            small_content,
            content_type="application/pdf"
        )
        
        # Mock the size check to simulate a large file
        with patch.object(uploaded_file, 'size', 101 * 1024 * 1024):  # 101MB
            response = api_client.post('/api/upload/', {
                'file': uploaded_file,
                'session_id': session_id
            })
        
        assert response.status_code == 413  # Request Entity Too Large
        data = response.json()
        assert 'error' in data
        assert 'size' in data['error'].lower() or 'limit' in data['error'].lower()


@pytest.mark.integration
class TestRedactionWorkflow:
    """Test complete redaction workflow."""
    
    def test_complete_redaction_workflow(self, api_client, db, test_session):
        """Test end-to-end redaction workflow from upload to download."""
        # Create test document
        document = DocumentFactory(session_id=test_session)
        
        # Step 1: Initiate redaction
        response = api_client.post('/api/redact/', {
            'document_id': document.id,
            'search_terms': ['email', 'phone', 'ssn'],
            'confidence_threshold': 80
        })
        
        assert response.status_code == 200
        data = response.json()
        job_id = data['job_id']
        
        # Verify job creation
        job = ProcessingJob.objects.get(id=job_id)
        assert job.job_type == 'redaction'
        assert job.document == document
        
        # Step 2: Simulate fuzzy matching results
        matches = []
        for i in range(3):
            match = RedactionMatchFactory(
                job=job,
                text=f'test{i}@example.com',
                confidence=85 + i,
                approved=None
            )
            matches.append(match)
        
        # Step 3: Review and approve matches
        response = api_client.get(f'/api/jobs/{job_id}/')
        assert response.status_code == 200
        data = response.json()
        assert 'matches' in data
        assert len(data['matches']) == 3
        
        # Step 4: Approve some matches, reject others
        approval_data = {
            'approvals': {
                str(matches[0].id): True,
                str(matches[1].id): True,
                str(matches[2].id): False
            }
        }
        
        response = api_client.post(f'/api/redact/{job_id}/approve/', approval_data)
        assert response.status_code == 200
        
        # Verify approvals
        matches[0].refresh_from_db()
        matches[1].refresh_from_db()
        matches[2].refresh_from_db()
        assert matches[0].approved is True
        assert matches[1].approved is True
        assert matches[2].approved is False
        
        # Step 5: Add manual redaction
        manual_redaction = {
            'page_number': 1,
            'coordinates': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 220},
            'text': 'Manual redaction'
        }
        
        response = api_client.post(f'/api/redact/{job_id}/manual/', manual_redaction)
        assert response.status_code == 200
        
        # Step 6: Finalize redaction
        response = api_client.post(f'/api/redact/{job_id}/finalize/')
        assert response.status_code == 200
        data = response.json()
        assert 'download_url' in data
        
        # Step 7: Download redacted file
        download_url = data['download_url']
        response = api_client.get(download_url)
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert len(response.content) > 0
    
    def test_fuzzy_matching_confidence_thresholds(self, api_client, db, test_session):
        """Test fuzzy matching with different confidence thresholds."""
        document = DocumentFactory(session_id=test_session)
        
        # Test with high confidence threshold
        response = api_client.post('/api/redact/', {
            'document_id': document.id,
            'search_terms': ['email'],
            'confidence_threshold': 95
        })
        
        assert response.status_code == 200
        data = response.json()
        high_threshold_job_id = data['job_id']
        
        # Test with low confidence threshold
        response = api_client.post('/api/redact/', {
            'document_id': document.id,
            'search_terms': ['email'],
            'confidence_threshold': 60
        })
        
        assert response.status_code == 200
        data = response.json()
        low_threshold_job_id = data['job_id']
        
        # Verify different jobs were created
        assert high_threshold_job_id != low_threshold_job_id
        
        high_job = ProcessingJob.objects.get(id=high_threshold_job_id)
        low_job = ProcessingJob.objects.get(id=low_threshold_job_id)
        
        assert high_job.job_type == 'redaction'
        assert low_job.job_type == 'redaction'
    
    def test_coordinate_validation_and_conversion(self, api_client, db, test_session):
        """Test coordinate validation and conversion for redaction boxes."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, job_type='redaction')
        
        # Test valid coordinates
        valid_coords = {
            'page_number': 1,
            'coordinates': {'x1': 50, 'y1': 100, 'x2': 200, 'y2': 120},
            'text': 'Valid redaction'
        }
        
        response = api_client.post(f'/api/redact/{job.id}/manual/', valid_coords)
        assert response.status_code == 200
        
        # Test invalid coordinates (x1 > x2)
        invalid_coords = {
            'page_number': 1,
            'coordinates': {'x1': 200, 'y1': 100, 'x2': 50, 'y2': 120},
            'text': 'Invalid redaction'
        }
        
        response = api_client.post(f'/api/redact/{job.id}/manual/', invalid_coords)
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'coordinate' in data['error'].lower()


@pytest.mark.integration 
class TestSplitWorkflow:
    """Test complete PDF splitting workflow."""
    
    def test_page_range_splitting(self, api_client, db, test_session):
        """Test PDF splitting by page ranges."""
        document = DocumentFactory(session_id=test_session, pages=10)
        
        # Test splitting pages 1-5 and 6-10
        response = api_client.post('/api/split/', {
            'document_id': document.id,
            'split_type': 'page_range',
            'ranges': [
                {'start': 1, 'end': 5, 'name': 'part1.pdf'},
                {'start': 6, 'end': 10, 'name': 'part2.pdf'}
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert 'job_id' in data
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'split'
        assert job.document == document
    
    def test_pattern_based_splitting(self, api_client, db, test_session):
        """Test PDF splitting based on text patterns."""
        document = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/split/', {
            'document_id': document.id,
            'split_type': 'pattern',
            'pattern': 'Chapter \\d+',
            'split_before': True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'split'
    
    def test_invalid_split_parameters(self, api_client, db, test_session):
        """Test error handling for invalid split parameters."""
        document = DocumentFactory(session_id=test_session, pages=5)
        
        # Test invalid page range (beyond document pages)
        response = api_client.post('/api/split/', {
            'document_id': document.id,
            'split_type': 'page_range',
            'ranges': [
                {'start': 1, 'end': 10, 'name': 'invalid.pdf'}  # Document only has 5 pages
            ]
        })
        
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'page' in data['error'].lower() or 'range' in data['error'].lower()


@pytest.mark.integration
class TestMergeWorkflow:
    """Test complete PDF merging workflow."""
    
    def test_multiple_file_merge(self, api_client, db, test_session):
        """Test merging multiple PDF files with proper ordering."""
        # Create multiple documents
        doc1 = DocumentFactory(session_id=test_session, filename='doc1.pdf')
        doc2 = DocumentFactory(session_id=test_session, filename='doc2.pdf')
        doc3 = DocumentFactory(session_id=test_session, filename='doc3.pdf')
        
        response = api_client.post('/api/merge/', {
            'session_id': test_session,
            'documents': [
                {'document_id': doc1.id, 'order': 1},
                {'document_id': doc3.id, 'order': 2},
                {'document_id': doc2.id, 'order': 3}
            ],
            'output_filename': 'merged_document.pdf'
        })
        
        assert response.status_code == 200
        data = response.json()
        assert 'job_id' in data
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'merge'
    
    def test_merge_with_bookmarks(self, api_client, db, test_session):
        """Test merging with bookmark preservation and creation."""
        doc1 = DocumentFactory(session_id=test_session)
        doc2 = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/merge/', {
            'session_id': test_session,
            'documents': [
                {'document_id': doc1.id, 'order': 1},
                {'document_id': doc2.id, 'order': 2}
            ],
            'preserve_bookmarks': True,
            'create_bookmarks': True,
            'output_filename': 'merged_with_bookmarks.pdf'
        })
        
        assert response.status_code == 200
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'merge'
    
    def test_merge_size_validation(self, api_client, db, test_session):
        """Test merge size limit validation."""
        # Create documents that would exceed merge size limit
        large_docs = []
        for i in range(5):
            doc = DocumentFactory(
                session_id=test_session,
                size=30 * 1024 * 1024  # 30MB each
            )
            large_docs.append(doc)
        
        document_list = [{'document_id': doc.id, 'order': i+1} for i, doc in enumerate(large_docs)]
        
        response = api_client.post('/api/merge/', {
            'session_id': test_session,
            'documents': document_list,
            'output_filename': 'oversized_merge.pdf'
        })
        
        # Should reject merge if total size exceeds limit
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'size' in data['error'].lower() or 'limit' in data['error'].lower()


@pytest.mark.integration
class TestExtractionWorkflow:
    """Test complete data extraction workflow."""
    
    def test_text_extraction_workflow(self, api_client, db, test_session):
        """Test text extraction with different formats."""
        document = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/extract/', {
            'document_id': document.id,
            'extraction_type': 'text',
            'format': 'txt',
            'page_range': {'start': 1, 'end': 5}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert 'job_id' in data
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'extraction'
    
    def test_table_extraction_workflow(self, api_client, db, test_session, table_pdf):
        """Test table extraction with CSV export."""
        document = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/extract/', {
            'document_id': document.id,
            'extraction_type': 'tables',
            'format': 'csv',
            'table_detection_method': 'camelot'
        })
        
        assert response.status_code == 200
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'extraction'
    
    def test_image_extraction_workflow(self, api_client, db, test_session):
        """Test image extraction with format conversion."""
        document = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/extract/', {
            'document_id': document.id,
            'extraction_type': 'images',
            'format': 'png',
            'quality': 85
        })
        
        assert response.status_code == 200
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'extraction'
    
    def test_metadata_extraction_workflow(self, api_client, db, test_session):
        """Test metadata extraction with JSON output."""
        document = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/extract/', {
            'document_id': document.id,
            'extraction_type': 'metadata',
            'format': 'json'
        })
        
        assert response.status_code == 200
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'extraction'
    
    def test_comprehensive_extraction(self, api_client, db, test_session):
        """Test extraction of multiple data types in one operation."""
        document = DocumentFactory(session_id=test_session)
        
        response = api_client.post('/api/extract/', {
            'document_id': document.id,
            'extraction_type': 'comprehensive',
            'include': ['text', 'images', 'tables', 'metadata'],
            'formats': {
                'text': 'txt',
                'images': 'png', 
                'tables': 'csv',
                'metadata': 'json'
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'extraction'


@pytest.mark.integration
class TestJobStatusAndProgress:
    """Test job status tracking and progress polling."""
    
    def test_job_status_polling(self, api_client, db, test_session):
        """Test job status polling and progress updates."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, status='processing', progress=50)
        
        # Poll job status
        response = api_client.get(f'/api/jobs/{job.id}/')
        assert response.status_code == 200
        data = response.json()
        
        assert data['id'] == str(job.id)
        assert data['status'] == 'processing'
        assert data['progress'] == 50
        assert 'created_at' in data
        assert 'document' in data
    
    def test_job_completion_and_results(self, api_client, db, test_session):
        """Test job completion status and result retrieval."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            status='completed',
            progress=100
        )
        
        response = api_client.get(f'/api/jobs/{job.id}/')
        assert response.status_code == 200
        data = response.json()
        
        assert data['status'] == 'completed'
        assert data['progress'] == 100
    
    def test_job_error_handling(self, api_client, db, test_session):
        """Test job error status and error message retrieval."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            status='failed',
            progress=75,
            error_message='Processing failed due to corrupted file'
        )
        
        response = api_client.get(f'/api/jobs/{job.id}/')
        assert response.status_code == 200
        data = response.json()
        
        assert data['status'] == 'failed'
        assert data['progress'] == 75
        assert 'error_message' in data
        assert data['error_message'] == 'Processing failed due to corrupted file'
    
    def test_concurrent_job_handling(self, api_client, db, test_session):
        """Test handling of concurrent operations on the same document."""
        document = DocumentFactory(session_id=test_session)
        
        # Start multiple operations on the same document
        operations = []
        for op_type in ['redaction', 'extraction']:
            if op_type == 'redaction':
                response = api_client.post('/api/redact/', {
                    'document_id': document.id,
                    'search_terms': ['test'],
                    'confidence_threshold': 80
                })
            else:
                response = api_client.post('/api/extract/', {
                    'document_id': document.id,
                    'extraction_type': 'text',
                    'format': 'txt'
                })
            
            assert response.status_code == 200
            operations.append(response.json()['job_id'])
        
        # Verify both jobs were created
        assert len(operations) == 2
        for job_id in operations:
            job = ProcessingJob.objects.get(id=job_id)
            assert job.document == document


@pytest.mark.integration
@pytest.mark.performance
class TestPerformanceAndScalability:
    """Test performance and scalability of workflows."""
    
    def test_large_file_processing_performance(self, api_client, large_pdf, session_id, performance_timer):
        """Test performance with large PDF files."""
        uploaded_file = SimpleUploadedFile(
            "performance_test.pdf",
            large_pdf,
            content_type="application/pdf"
        )
        
        # Upload large file
        performance_timer.start()
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        performance_timer.stop()
        
        assert response.status_code == 200
        # Large file upload should complete within 1 minute
        assert performance_timer.elapsed < 60.0
        
        data = response.json()
        document_id = data['document_id']
        
        # Test processing performance
        performance_timer.start()
        response = api_client.post('/api/extract/', {
            'document_id': document_id,
            'extraction_type': 'text',
            'format': 'txt'
        })
        performance_timer.stop()
        
        assert response.status_code == 200
        # Processing initiation should be quick
        assert performance_timer.elapsed < 5.0
    
    def test_memory_usage_validation(self, api_client, db, test_session):
        """Test memory usage during concurrent operations."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create multiple documents and operations
        documents = []
        for i in range(5):
            doc = DocumentFactory(session_id=test_session)
            documents.append(doc)
        
        # Start multiple operations
        for doc in documents:
            response = api_client.post('/api/extract/', {
                'document_id': doc.id,
                'extraction_type': 'text',
                'format': 'txt'
            })
            assert response.status_code == 200
        
        # Check memory usage hasn't grown excessively
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be reasonable (< 100MB for this test)
        assert memory_growth < 100
    
    @pytest.mark.slow
    def test_stress_test_concurrent_uploads(self, api_client, simple_text_pdf, performance_timer):
        """Test system behavior under concurrent upload load."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def upload_file(session_id):
            try:
                local_client = Client()
                uploaded_file = SimpleUploadedFile(
                    f"stress_test_{session_id}.pdf",
                    simple_text_pdf,
                    content_type="application/pdf"
                )
                
                response = local_client.post('/api/upload/', {
                    'file': uploaded_file,
                    'session_id': session_id
                })
                
                results.put(response.status_code)
            except Exception as e:
                results.put(str(e))
        
        # Create 10 concurrent uploads
        threads = []
        for i in range(10):
            session_id = f"stress_test_{i}"
            thread = threading.Thread(target=upload_file, args=(session_id,))
            threads.append(thread)
        
        # Start all threads
        performance_timer.start()
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        performance_timer.stop()
        
        # Verify results
        success_count = 0
        while not results.empty():
            result = results.get()
            if result == 200:
                success_count += 1
        
        # At least 80% should succeed under load
        assert success_count >= 8
        # Should complete within reasonable time (2 minutes)
        assert performance_timer.elapsed < 120.0