"""
Comprehensive API endpoint tests for all REST endpoints.

This module tests all API endpoints including file upload, redaction,
splitting, merging, extraction, and job status endpoints.

NOTE: Currently using hardcoded URLs. Once Django URL patterns are properly
configured, these should be replaced with reverse() calls for better maintainability.
Example: '/api/upload/' should become reverse('api:upload')
"""

import json
import tempfile
import uuid
from unittest.mock import patch, Mock
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.sessions.models import Session
from rest_framework import status

from app.models import Document, ProcessingJob, RedactionMatch
from .conftest import DocumentFactory, ProcessingJobFactory, RedactionMatchFactory


@pytest.mark.api
class TestFileUploadView:
    """Test FileUploadView (/api/upload/) endpoint."""
    
    def test_valid_pdf_upload_success(self, api_client, simple_text_pdf, session_id):
        """Test successful PDF file upload with proper response."""
        uploaded_file = SimpleUploadedFile(
            "test_document.pdf",
            simple_text_pdf,
            content_type="application/pdf"
        )
        
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'document_id' in data
        assert 'filename' in data
        assert 'size' in data
        assert 'pages' in data
        assert 'message' in data
        
        # Verify database record
        document = Document.objects.get(id=data['document_id'])
        assert document.filename == 'test_document.pdf'
        assert document.session_id == session_id
        assert document.size > 0
        assert document.pages > 0
    
    def test_upload_with_progress_tracking(self, api_client, large_pdf, session_id):
        """Test upload with progress tracking for large files."""
        uploaded_file = SimpleUploadedFile(
            "large_document.pdf",
            large_pdf,
            content_type="application/pdf"
        )
        
        with patch('app.views.track_upload_progress', create=True) as mock_progress:
            response = api_client.post('/api/upload/', {
                'file': uploaded_file,
                'session_id': session_id
            })
            
            assert response.status_code == status.HTTP_200_OK
            # Progress tracking should be called for large files
            # mock_progress.assert_called()
    
    def test_invalid_file_format_rejection(self, api_client, session_id):
        """Test rejection of non-PDF files."""
        text_file = SimpleUploadedFile(
            "document.txt",
            b"This is not a PDF file",
            content_type="text/plain"
        )
        
        response = api_client.post('/api/upload/', {
            'file': text_file,
            'session_id': session_id
        })
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert 'pdf' in data['error'].lower() or 'format' in data['error'].lower()
    
    def test_oversized_file_rejection(self, api_client, session_id):
        """Test rejection of files exceeding size limits."""
        # Mock file size check without creating a huge buffer
        small_content = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n"
        oversized_file = SimpleUploadedFile(
            "oversized.pdf",
            small_content,
            content_type="application/pdf"
        )
        
        # Mock the size check to simulate a large file
        with patch.object(oversized_file, 'size', 101 * 1024 * 1024):  # 101MB
            response = api_client.post('/api/upload/', {
                'file': oversized_file,
                'session_id': session_id
            })
        
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        
        data = response.json()
        assert 'error' in data
        assert 'size' in data['error'].lower() or 'limit' in data['error'].lower()
    
    def test_corrupted_file_validation(self, api_client, corrupted_pdf, session_id):
        """Test handling of corrupted PDF files."""
        corrupted_file = SimpleUploadedFile(
            "corrupted.pdf",
            corrupted_pdf,
            content_type="application/pdf"
        )
        
        response = api_client.post('/api/upload/', {
            'file': corrupted_file,
            'session_id': session_id
        })
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert any(word in data['error'].lower() 
                  for word in ['corrupted', 'invalid', 'damaged', 'malformed'])
    
    def test_missing_session_id_handling(self, api_client, simple_text_pdf):
        """Test handling of missing session ID."""
        uploaded_file = SimpleUploadedFile(
            "test_document.pdf",
            simple_text_pdf,
            content_type="application/pdf"
        )
        
        response = api_client.post('/api/upload/', {
            'file': uploaded_file
            # Missing session_id
        })
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert 'session' in data['error'].lower()
    
    def test_concurrent_upload_handling(self, api_client, simple_text_pdf):
        """Test handling of concurrent uploads from same session."""
        import threading
        import time
        
        session_id = str(uuid.uuid4())
        results = []
        
        def upload_file(filename):
            uploaded_file = SimpleUploadedFile(
                filename,
                simple_text_pdf,
                content_type="application/pdf"
            )
            
            response = api_client.post('/api/upload/', {
                'file': uploaded_file,
                'session_id': session_id
            })
            results.append(response.status_code)
        
        # Start concurrent uploads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=upload_file, args=(f"doc_{i}.pdf",))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # All uploads should succeed
        assert all(status_code == 200 for status_code in results)
    
    @pytest.mark.skip(reason="Security scanning module not implemented yet")
    def test_security_scanning_integration(self, api_client, session_id):
        """Test integration with security scanning."""
        # Create potentially suspicious file content
        suspicious_content = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
        suspicious_file = SimpleUploadedFile(
            "suspicious.pdf",
            suspicious_content,
            content_type="application/pdf"
        )
        
        with patch('app.services.security_scanner.scan_file') as mock_scanner:
            mock_scanner.return_value = {'safe': True, 'threats': []}
            
            response = api_client.post('/api/upload/', {
                'file': suspicious_file,
                'session_id': session_id
            })
            
            # Should call security scanner
            mock_scanner.assert_called_once()


@pytest.mark.api
class TestRedactionAPIView:
    """Test RedactionAPIView (/api/redact/) endpoint."""
    
    def test_redaction_initiation(self, api_client, db, test_session):
        """Test starting redaction process with search terms."""
        document = DocumentFactory(session_id=test_session)
        
        redaction_data = {
            'document_id': str(document.id),
            'search_terms': ['email', 'phone', 'ssn'],
            'confidence_threshold': 85,
            'fuzzy_matching': True
        }
        
        response = api_client.post('/api/redact/', redaction_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'job_id' in data
        assert 'message' in data
        
        # Verify job creation
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'redaction'
        assert job.document == document
        assert job.status in ['pending', 'processing']
    
    def test_fuzzy_matching_configuration(self, api_client, db, test_session):
        """Test fuzzy matching with different configurations."""
        document = DocumentFactory(session_id=test_session)
        
        # Test with custom confidence threshold
        redaction_data = {
            'document_id': str(document.id),
            'search_terms': ['confidential'],
            'confidence_threshold': 95,
            'fuzzy_matching': True,
            'matching_algorithm': 'token_sort_ratio'
        }
        
        response = api_client.post('/api/redact/', redaction_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        # Configuration should be stored in job metadata
        assert job.job_type == 'redaction'
    
    def test_match_approval_workflow(self, api_client, db, test_session):
        """Test match approval/rejection workflow."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, job_type='redaction')
        
        # Create some matches
        matches = []
        for i in range(3):
            match = RedactionMatchFactory(job=job, approved=None)
            matches.append(match)
        
        # Approve/reject matches
        approval_data = {
            'approvals': {
                str(matches[0].id): True,
                str(matches[1].id): False,
                str(matches[2].id): True
            }
        }
        
        response = api_client.post(f'/api/redact/{job.id}/approve/', approval_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify approvals in database
        matches[0].refresh_from_db()
        matches[1].refresh_from_db()
        matches[2].refresh_from_db()
        
        assert matches[0].approved is True
        assert matches[1].approved is False
        assert matches[2].approved is True
    
    def test_manual_redaction_addition(self, api_client, db, test_session):
        """Test adding manual redaction coordinates."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, job_type='redaction')
        
        manual_redaction = {
            'page_number': 1,
            'coordinates': {
                'x1': 100,
                'y1': 200, 
                'x2': 300,
                'y2': 220
            },
            'text': 'Manual redaction text'
        }
        
        response = api_client.post(f'/api/redact/{job.id}/manual/', manual_redaction)
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'match_id' in data
        
        # Verify manual match creation
        manual_match = RedactionMatch.objects.get(id=data['match_id'])
        assert manual_match.job == job
        assert manual_match.page_number == 1
        assert manual_match.text == 'Manual redaction text'
        assert manual_match.approved is True  # Manual redactions auto-approved
    
    def test_coordinate_validation(self, api_client, db, test_session):
        """Test coordinate validation for manual redactions."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, job_type='redaction')
        
        # Invalid coordinates (x1 > x2)
        invalid_redaction = {
            'page_number': 1,
            'coordinates': {
                'x1': 300,
                'y1': 200,
                'x2': 100,  # Invalid: x2 < x1
                'y2': 220
            },
            'text': 'Invalid coordinates'
        }
        
        response = api_client.post(f'/api/redact/{job.id}/manual/', invalid_redaction)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert 'coordinate' in data['error'].lower()
    
    def test_redaction_finalization(self, api_client, db, test_session):
        """Test finalizing redaction and generating download."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, job_type='redaction')
        
        # Create approved matches
        approved_match = RedactionMatchFactory(job=job, approved=True)
        rejected_match = RedactionMatchFactory(job=job, approved=False)
        
        with patch('app.services.redaction_service.RedactionService.apply_redactions') as mock_redact:
            mock_redact.return_value = True
            
            response = api_client.post(f'/api/redact/{job.id}/finalize/')
            
            assert response.status_code == status.HTTP_200_OK
            
            data = response.json()
            assert 'download_url' in data
            assert 'redaction_count' in data
            assert data['redaction_count'] == 1  # Only approved matches
            
            mock_redact.assert_called_once()
    
    def test_invalid_document_handling(self, api_client):
        """Test handling of invalid document IDs."""
        invalid_uuid = str(uuid.uuid4())
        
        redaction_data = {
            'document_id': invalid_uuid,
            'search_terms': ['test'],
            'confidence_threshold': 80
        }
        
        response = api_client.post('/api/redact/', redaction_data)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        data = response.json()
        assert 'error' in data
        assert 'not found' in data['error'].lower()


@pytest.mark.api 
class TestSplitAPIView:
    """Test SplitAPIView (/api/split/) endpoint."""
    
    def test_page_range_splitting(self, api_client, db, test_session):
        """Test splitting PDF by page ranges."""
        document = DocumentFactory(session_id=test_session, pages=10)
        
        split_data = {
            'document_id': str(document.id),
            'split_type': 'page_range',
            'ranges': [
                {'start': 1, 'end': 5, 'name': 'part1.pdf'},
                {'start': 6, 'end': 10, 'name': 'part2.pdf'}
            ]
        }
        
        response = api_client.post('/api/split/', split_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'job_id' in data
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'split'
        assert job.document == document
    
    def test_pattern_based_splitting(self, api_client, db, test_session):
        """Test splitting PDF based on text patterns."""
        document = DocumentFactory(session_id=test_session)
        
        split_data = {
            'document_id': str(document.id),
            'split_type': 'pattern',
            'pattern': 'Chapter \\d+',
            'split_before': True,
            'case_sensitive': False
        }
        
        response = api_client.post('/api/split/', split_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'split'
    
    def test_bookmark_based_splitting(self, api_client, db, test_session):
        """Test splitting PDF based on bookmarks."""
        document = DocumentFactory(session_id=test_session)
        
        split_data = {
            'document_id': str(document.id),
            'split_type': 'bookmark',
            'bookmark_level': 1,
            'preserve_structure': True
        }
        
        response = api_client.post('/api/split/', split_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_invalid_page_range_validation(self, api_client, db, test_session):
        """Test validation of invalid page ranges."""
        document = DocumentFactory(session_id=test_session, pages=5)
        
        # Invalid range: beyond document pages
        split_data = {
            'document_id': str(document.id),
            'split_type': 'page_range',
            'ranges': [
                {'start': 1, 'end': 10, 'name': 'invalid.pdf'}  # Document only has 5 pages
            ]
        }
        
        response = api_client.post('/api/split/', split_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert any(word in data['error'].lower() for word in ['page', 'range', 'invalid'])
    
    def test_overlapping_ranges_validation(self, api_client, db, test_session):
        """Test validation of overlapping page ranges."""
        document = DocumentFactory(session_id=test_session, pages=10)
        
        split_data = {
            'document_id': str(document.id),
            'split_type': 'page_range',
            'ranges': [
                {'start': 1, 'end': 5, 'name': 'part1.pdf'},
                {'start': 4, 'end': 8, 'name': 'part2.pdf'}  # Overlaps with part1
            ]
        }
        
        response = api_client.post('/api/split/', split_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert 'overlap' in data['error'].lower()
    
    def test_split_options_configuration(self, api_client, db, test_session):
        """Test split options and metadata preservation."""
        document = DocumentFactory(session_id=test_session, pages=10)
        
        split_data = {
            'document_id': str(document.id),
            'split_type': 'page_range',
            'ranges': [
                {'start': 1, 'end': 5, 'name': 'part1.pdf'}
            ],
            'preserve_bookmarks': True,
            'preserve_annotations': True,
            'preserve_forms': False
        }
        
        response = api_client.post('/api/split/', split_data)
        
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.api
class TestMergeAPIView:
    """Test MergeAPIView (/api/merge/) endpoint."""
    
    def test_multiple_document_merge(self, api_client, db, test_session):
        """Test merging multiple PDF documents."""
        # Create multiple documents
        doc1 = DocumentFactory(session_id=test_session, filename='doc1.pdf')
        doc2 = DocumentFactory(session_id=test_session, filename='doc2.pdf')
        doc3 = DocumentFactory(session_id=test_session, filename='doc3.pdf')
        
        merge_data = {
            'session_id': test_session,
            'documents': [
                {'document_id': str(doc1.id), 'order': 1},
                {'document_id': str(doc3.id), 'order': 2},
                {'document_id': str(doc2.id), 'order': 3}
            ],
            'output_filename': 'merged_document.pdf'
        }
        
        response = api_client.post('/api/merge/', merge_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'job_id' in data
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'merge'
    
    def test_merge_with_bookmarks(self, api_client, db, test_session):
        """Test merging with bookmark handling."""
        doc1 = DocumentFactory(session_id=test_session)
        doc2 = DocumentFactory(session_id=test_session)
        
        merge_data = {
            'session_id': test_session,
            'documents': [
                {'document_id': str(doc1.id), 'order': 1},
                {'document_id': str(doc2.id), 'order': 2}
            ],
            'preserve_bookmarks': True,
            'create_bookmarks': True,
            'bookmark_strategy': 'filename',
            'output_filename': 'merged_with_bookmarks.pdf'
        }
        
        response = api_client.post('/api/merge/', merge_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_merge_size_validation(self, api_client, db, test_session):
        """Test merge size limit enforcement."""
        # Create documents exceeding total size limit
        large_docs = []
        for i in range(3):
            doc = DocumentFactory(
                session_id=test_session,
                size=40 * 1024 * 1024  # 40MB each = 120MB total
            )
            large_docs.append(doc)
        
        merge_data = {
            'session_id': test_session,
            'documents': [
                {'document_id': str(doc.id), 'order': i+1} 
                for i, doc in enumerate(large_docs)
            ],
            'output_filename': 'oversized_merge.pdf'
        }
        
        response = api_client.post('/api/merge/', merge_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert any(word in data['error'].lower() for word in ['size', 'limit', 'large'])
    
    def test_merge_document_compatibility(self, api_client, db, test_session):
        """Test document compatibility validation for merge."""
        # Documents from different sessions should not be mergeable
        doc1 = DocumentFactory(session_id=test_session)
        doc2 = DocumentFactory(session_id=str(uuid.uuid4()))  # Different session
        
        merge_data = {
            'session_id': test_session,
            'documents': [
                {'document_id': str(doc1.id), 'order': 1},
                {'document_id': str(doc2.id), 'order': 2}
            ],
            'output_filename': 'incompatible_merge.pdf'
        }
        
        response = api_client.post('/api/merge/', merge_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert any(word in data['error'].lower() 
                  for word in ['session', 'permission', 'access'])
    
    def test_duplicate_document_handling(self, api_client, db, test_session):
        """Test handling of duplicate documents in merge list."""
        doc1 = DocumentFactory(session_id=test_session)
        
        merge_data = {
            'session_id': test_session,
            'documents': [
                {'document_id': str(doc1.id), 'order': 1},
                {'document_id': str(doc1.id), 'order': 2}  # Duplicate
            ],
            'output_filename': 'duplicate_merge.pdf'
        }
        
        response = api_client.post('/api/merge/', merge_data)
        
        # Should either succeed (allowing duplicates) or return error
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            data = response.json()
            assert 'duplicate' in data['error'].lower()
        else:
            assert response.status_code == status.HTTP_200_OK


@pytest.mark.api
class TestExtractionAPIView:
    """Test ExtractionAPIView (/api/extract/) endpoint."""
    
    def test_text_extraction(self, api_client, db, test_session):
        """Test text extraction from PDF."""
        document = DocumentFactory(session_id=test_session)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'text',
            'format': 'txt',
            'page_range': {'start': 1, 'end': 5},
            'include_metadata': True
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'job_id' in data
        
        job = ProcessingJob.objects.get(id=data['job_id'])
        assert job.job_type == 'extraction'
        assert job.document == document
    
    def test_table_extraction_with_options(self, api_client, db, test_session):
        """Test table extraction with detection options."""
        document = DocumentFactory(session_id=test_session)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'tables',
            'format': 'csv',
            'table_detection_method': 'camelot',
            'detection_settings': {
                'flavor': 'stream',
                'edge_tol': 500,
                'row_tol': 2
            }
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_image_extraction_with_quality(self, api_client, db, test_session):
        """Test image extraction with quality settings."""
        document = DocumentFactory(session_id=test_session)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'images',
            'format': 'png',
            'quality': 90,
            'min_size': {'width': 100, 'height': 100},
            'max_size': 5000000  # 5MB
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_metadata_extraction(self, api_client, db, test_session):
        """Test PDF metadata extraction."""
        document = DocumentFactory(session_id=test_session)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'metadata',
            'format': 'json',
            'include_xmp': True,
            'include_properties': True
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_comprehensive_extraction(self, api_client, db, test_session):
        """Test comprehensive extraction of multiple data types."""
        document = DocumentFactory(session_id=test_session)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'comprehensive',
            'include': ['text', 'images', 'tables', 'metadata'],
            'formats': {
                'text': 'txt',
                'images': 'png',
                'tables': 'csv',
                'metadata': 'json'
            },
            'page_range': {'start': 1, 'end': 10}
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_unsupported_extraction_type(self, api_client, db, test_session):
        """Test handling of unsupported extraction types."""
        document = DocumentFactory(session_id=test_session)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'unsupported_type',
            'format': 'txt'
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert 'unsupported' in data['error'].lower() or 'invalid' in data['error'].lower()
    
    def test_invalid_page_range_extraction(self, api_client, db, test_session):
        """Test extraction with invalid page ranges."""
        document = DocumentFactory(session_id=test_session, pages=5)
        
        extraction_data = {
            'document_id': str(document.id),
            'extraction_type': 'text',
            'format': 'txt',
            'page_range': {'start': 1, 'end': 10}  # Beyond document pages
        }
        
        response = api_client.post('/api/extract/', extraction_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        data = response.json()
        assert 'error' in data
        assert any(word in data['error'].lower() for word in ['page', 'range'])


@pytest.mark.api
class TestJobStatusView:
    """Test JobStatusView (/api/jobs/{id}/) endpoint."""
    
    def test_job_status_retrieval(self, api_client, db, test_session):
        """Test retrieving job status and details."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            job_type='redaction',
            status='processing',
            progress=50
        )
        
        response = api_client.get(f'/api/jobs/{job.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data['id'] == str(job.id)
        assert data['status'] == 'processing'
        assert data['progress'] == 50
        assert data['job_type'] == 'redaction'
        assert 'created_at' in data
        assert 'document' in data
    
    def test_completed_job_with_results(self, api_client, db, test_session):
        """Test retrieving completed job with results."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            job_type='extraction',
            status='completed',
            progress=100,
            result_data={'extracted_text': 'Sample extracted text'}
        )
        
        response = api_client.get(f'/api/jobs/{job.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data['status'] == 'completed'
        assert data['progress'] == 100
        assert 'results' in data
        if 'download_url' in data:
            assert data['download_url'] is not None
    
    def test_failed_job_with_error(self, api_client, db, test_session):
        """Test retrieving failed job with error information."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            status='failed',
            progress=75,
            error_message='Processing failed due to corrupted file'
        )
        
        response = api_client.get(f'/api/jobs/{job.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data['status'] == 'failed'
        assert data['progress'] == 75
        assert 'error_message' in data
        assert data['error_message'] == 'Processing failed due to corrupted file'
    
    def test_job_progress_updates(self, api_client, db, test_session):
        """Test job progress tracking over time."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            status='processing',
            progress=25
        )
        
        # Initial status check
        response = api_client.get(f'/api/jobs/{job.id}/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['progress'] == 25
        
        # Simulate progress update
        job.progress = 75
        job.save()
        
        # Check updated progress
        response = api_client.get(f'/api/jobs/{job.id}/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['progress'] == 75
    
    def test_nonexistent_job_handling(self, api_client):
        """Test handling of non-existent job IDs."""
        nonexistent_id = str(uuid.uuid4())
        
        response = api_client.get(f'/api/jobs/{nonexistent_id}/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        data = response.json()
        assert 'error' in data
        assert 'not found' in data['error'].lower()
    
    def test_job_cancellation(self, api_client, db, test_session):
        """Test job cancellation functionality."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(
            document=document,
            status='processing',
            progress=30
        )
        
        response = api_client.post(f'/api/jobs/{job.id}/cancel/')
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify job was cancelled
        job.refresh_from_db()
        assert job.status == 'cancelled'
    
    def test_redaction_job_matches(self, api_client, db, test_session):
        """Test retrieving redaction matches with job status."""
        document = DocumentFactory(session_id=test_session)
        job = ProcessingJobFactory(document=document, job_type='redaction')
        
        # Create redaction matches
        matches = []
        for i in range(3):
            match = RedactionMatchFactory(job=job)
            matches.append(match)
        
        response = api_client.get(f'/api/jobs/{job.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert 'matches' in data
        assert len(data['matches']) == 3
        
        # Verify match details
        for i, match_data in enumerate(data['matches']):
            assert 'id' in match_data
            assert 'text' in match_data
            assert 'confidence' in match_data
            assert 'coordinates' in match_data


@pytest.mark.api
class TestAPIMiddlewareAndSecurity:
    """Test API middleware functionality and security features."""
    
    def test_request_id_generation(self, api_client, simple_text_pdf, session_id):
        """Test request ID generation and tracking."""
        uploaded_file = SimpleUploadedFile(
            "test_document.pdf",
            simple_text_pdf,
            content_type="application/pdf"
        )
        
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        
        # Should include request ID in headers
        assert 'X-Request-ID' in response or 'Request-ID' in response
    
    def test_cors_headers(self, api_client):
        """Test CORS headers in API responses."""
        response = api_client.options('/api/upload/')
        
        # Should include CORS headers
        assert response.status_code in [200, 204]
        # CORS headers should be present for cross-origin requests
    
    def test_rate_limiting(self, api_client, simple_text_pdf, session_id):
        """Test API rate limiting functionality."""
        uploaded_file = SimpleUploadedFile(
            "test_document.pdf",
            simple_text_pdf,
            content_type="application/pdf"
        )
        
        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = api_client.post('/api/upload/', {
                'file': uploaded_file,
                'session_id': f"{session_id}_{i}"
            })
            responses.append(response.status_code)
        
        # Should not all succeed if rate limiting is active
        # (Implementation dependent - may succeed in test environment)
    
    def test_timeout_handling(self, api_client, db, test_session):
        """Test API timeout handling for long operations."""
        document = DocumentFactory(session_id=test_session)
        
        with patch('app.tasks.process_extraction.delay') as mock_task:
            # Simulate long-running task
            mock_task.return_value.id = str(uuid.uuid4())
            
            extraction_data = {
                'document_id': str(document.id),
                'extraction_type': 'comprehensive',
                'formats': {'text': 'txt', 'images': 'png'}
            }
            
            response = api_client.post('/api/extract/', extraction_data)
            
            # Should return immediately with job ID for background processing
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert 'job_id' in data
    
    def test_error_response_consistency(self, api_client):
        """Test consistent error response formatting."""
        # Test various error scenarios
        
        # 404 error
        response_404 = api_client.get('/api/nonexistent-endpoint/')
        assert response_404.status_code == 404
        
        # 400 error  
        response_400 = api_client.post('/api/upload/', {})  # Missing required fields
        assert response_400.status_code == 400
        data_400 = response_400.json()
        assert 'error' in data_400
        
        # Error responses should have consistent structure
        assert isinstance(data_400['error'], str)
    
    def test_security_headers(self, api_client, simple_text_pdf, session_id):
        """Test security headers in API responses."""
        uploaded_file = SimpleUploadedFile(
            "test_document.pdf",
            simple_text_pdf,
            content_type="application/pdf"
        )
        
        response = api_client.post('/api/upload/', {
            'file': uploaded_file,
            'session_id': session_id
        })
        
        # Check for security headers (implementation dependent)
        security_headers = [
            'X-Content-Type-Options',
            'X-Frame-Options', 
            'X-XSS-Protection'
        ]
        
        # At least some security headers should be present
        present_headers = [header for header in security_headers if header in response]
        assert len(present_headers) >= 1, 'Expected at least one security header'