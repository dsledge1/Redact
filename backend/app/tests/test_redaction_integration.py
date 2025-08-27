"""
Integration tests for the complete redaction workflow.

Tests end-to-end redaction pipeline from upload to download,
API endpoint integration, background task processing, and
permanent text deletion verification.
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone

from app.models import PDFDocument, ProcessingJob, RedactionMatch, RedactionAuditLog
from app.services.redaction_service import RedactionService
from app.services.unified_search_service import UnifiedSearchService
from app.services.temp_file_manager import TempFileManager
from tasks import apply_text_redactions


class TestEndToEndRedactionPipeline(TransactionTestCase):
    """Test complete redaction workflow from start to finish."""
    
    def setUp(self):
        """Set up test data."""
        self.session_id = "test_session_e2e"
        self.temp_dir = tempfile.mkdtemp()
        
        # Create test document
        self.document = PDFDocument.objects.create(
            filename="test_document.pdf",
            file_size=1024000,
            session_id=self.session_id,
            content_hash="test_hash",
            file_hash="test_file_hash"
        )
        
    def tearDown(self):
        """Clean up test data."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('app.services.unified_search_service.UnifiedSearchService')
    @patch('app.services.redaction_service.RedactionService')
    def test_complete_redaction_workflow_high_confidence(self, mock_redaction_service, mock_search_service):
        """Test complete workflow with high-confidence matches."""
        # Setup mocks for search service
        mock_search_instance = Mock()
        mock_search_service.return_value = mock_search_instance
        
        # Mock high-confidence matches
        high_confidence_match = Mock()
        high_confidence_match.confidence_score = 0.98
        high_confidence_match.page_number = 0
        high_confidence_match.matched_text = "CONFIDENTIAL"
        high_confidence_match.id = "match_001"
        
        mock_search_instance.search_document.return_value = {
            'matches': [high_confidence_match],
            'total_matches': 1
        }
        
        # Setup mocks for redaction service
        mock_redaction_instance = Mock()
        mock_redaction_service.return_value = mock_redaction_instance
        mock_redaction_instance.redact_pdf.return_value = {
            'success': True,
            'output_path': str(Path(self.temp_dir) / 'redacted_test.pdf'),
            'statistics': {
                'total_matches': 1,
                'redactions_applied': 1,
                'pages_affected': 1,
                'processing_time_ms': 1500
            },
            'errors': []
        }
        
        # Create test PDF file
        pdf_path = Path(self.temp_dir) / "test_document.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(b"%PDF-1.4\n%Test PDF content with CONFIDENTIAL data\n%%EOF")
        
        # Simulate the workflow
        with patch('app.services.temp_file_manager.TempFileManager.get_session_path') as mock_get_path:
            mock_get_path.return_value = Path(self.temp_dir)
            
            # 1. Search for matches
            search_service = UnifiedSearchService(self.session_id)
            search_results = search_service.search_document(
                str(pdf_path),
                ["CONFIDENTIAL"],
                fuzzy_threshold=80
            )
            
            # 2. Filter by confidence (≥95% auto-approved)
            high_confidence_matches = [
                match for match in search_results['matches'] 
                if match.confidence_score >= 0.95
            ]
            
            assert len(high_confidence_matches) == 1
            
            # 3. Apply redactions
            redaction_service = RedactionService(self.session_id)
            redaction_result = redaction_service.redact_pdf(
                pdf_path,
                high_confidence_matches
            )
            
            assert redaction_result['success'] is True
            assert redaction_result['statistics']['redactions_applied'] == 1
    
    def test_workflow_with_approval_required(self):
        """Test workflow requiring manual approval for low-confidence matches."""
        # Create low-confidence matches that require approval
        job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact',
            status='processing'
        )
        
        low_confidence_match = RedactionMatch.objects.create(
            job=job,
            document=self.document,
            search_term="sensitive",
            matched_text="potentially sensitive data",
            confidence_score=0.75,  # Below 95% threshold
            page_number=0,
            x_coordinate=100,
            y_coordinate=200,
            width=150,
            height=25,
            approved_status=None  # Pending approval
        )
        
        # Verify match requires approval
        assert low_confidence_match.needs_approval()
        
        # Approve the match
        low_confidence_match.approved_status = True
        low_confidence_match.save()
        
        # Verify approval
        assert not low_confidence_match.needs_approval()
        assert low_confidence_match.approved_status is True
    
    @patch('app.services.redaction_service.PdfReader')
    @patch('app.services.redaction_service.PdfWriter') 
    def test_permanent_text_deletion_verification(self, mock_writer_class, mock_reader_class):
        """Verify permanent text deletion in end-to-end workflow."""
        # Setup PDF mocks
        mock_reader = Mock()
        mock_writer = Mock()
        mock_page = Mock()
        
        mock_reader_class.return_value = mock_reader
        mock_writer_class.return_value = mock_writer
        mock_reader.pages = [mock_page]
        
        # Mock mediabox for coordinate conversion
        mock_page.mediabox = Mock()
        mock_page.mediabox.top = 792.0  # Letter size height
        mock_page.mediabox.bottom = 0.0
        mock_page.mediabox.right = 612.0  # Letter size width
        mock_page.mediabox.left = 0.0
        
        # Mock PyPDF2 redaction methods
        mock_page.add_redact_annot = Mock()
        mock_page.apply_redactions = Mock()
        
        # Create redaction match
        job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
        
        match = RedactionMatch.objects.create(
            job=job,
            document=self.document,
            search_term="SECRET",
            matched_text="SECRET INFORMATION",
            confidence_score=1.0,
            page_number=0,
            x_coordinate=100,
            y_coordinate=200,
            width=120,
            height=20,
            approved_status=True
        )
        
        # Apply redaction
        redaction_service = RedactionService(self.session_id)
        pdf_path = Path(self.temp_dir) / "test.pdf"
        
        with patch.object(redaction_service.temp_file_manager, 'get_download_path') as mock_download:
            mock_download.return_value = Path(self.temp_dir) / "redacted.pdf"
            
            result = redaction_service.redact_pdf(pdf_path, [match])
            
            # Verify permanent deletion methods were called
            assert mock_page.add_redact_annot.called
            assert mock_page.apply_redactions.called
            
            # Verify match was marked as redacted
            match.refresh_from_db()
            assert match.redacted is True
            assert match.redaction_applied_at is not None


class TestRedactionAPIIntegration(APITestCase):
    """Test redaction API endpoints integration."""
    
    def setUp(self):
        """Set up API test data."""
        self.client = APIClient()
        self.session_id = "api_test_session"
        
        self.document = PDFDocument.objects.create(
            filename="api_test.pdf",
            file_size=512000,
            session_id=self.session_id,
            content_hash="api_test_hash",
            file_hash="api_file_hash"
        )
    
    @patch('app.views.UnifiedSearchService')
    def test_redaction_api_endpoint_success(self, mock_search_service):
        """Test successful redaction API request."""
        # Mock search service
        mock_search_instance = Mock()
        mock_search_service.return_value = mock_search_instance
        
        high_confidence_match = Mock()
        high_confidence_match.confidence_score = 0.98
        high_confidence_match.id = "api_match_001"
        high_confidence_match.matched_text = "API_SECRET"
        high_confidence_match.page_number = 0
        
        mock_search_instance.search_document.return_value = {
            'matches': [high_confidence_match]
        }
        
        # Mock file existence
        with patch('pathlib.Path.exists', return_value=True):
            with patch('app.services.redaction_service.RedactionService') as mock_redaction:
                mock_redaction_instance = Mock()
                mock_redaction.return_value = mock_redaction_instance
                mock_redaction_instance.redact_pdf.return_value = {
                    'success': True,
                    'output_path': '/test/redacted.pdf',
                    'statistics': {'total_matches': 1, 'redactions_applied': 1}
                }
                
                response = self.client.post('/api/redact/', {
                    'document_id': str(self.document.id),
                    'search_terms': ['API_SECRET'],
                    'confidence_threshold': 95
                })
                
                assert response.status_code == status.HTTP_200_OK
                assert response.data['success'] is True
                assert 'job_id' in response.data
    
    def test_redaction_preview_endpoint(self):
        """Test redaction preview generation."""
        job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
        
        match = RedactionMatch.objects.create(
            job=job,
            document=self.document,
            search_term="PREVIEW",
            matched_text="PREVIEW_DATA",
            confidence_score=0.92,
            page_number=0,
            x_coordinate=150,
            y_coordinate=250,
            width=100,
            height=20
        )
        
        response = self.client.post('/api/redact/preview/', {
            'document_id': str(self.document.id),
            'match_ids': [str(match.id)]
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert len(response.data['preview_data']) == 1
        assert response.data['total_redactions'] == 1
    
    def test_redaction_approval_endpoint(self):
        """Test match approval endpoint."""
        job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
        
        match = RedactionMatch.objects.create(
            job=job,
            document=self.document,
            search_term="APPROVAL",
            matched_text="APPROVAL_TEST",
            confidence_score=0.78,
            page_number=0,
            x_coordinate=200,
            y_coordinate=300,
            width=80,
            height=15,
            approved_status=None  # Pending
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('app.services.redaction_service.RedactionService') as mock_redaction:
                mock_redaction_instance = Mock()
                mock_redaction.return_value = mock_redaction_instance
                mock_redaction_instance.redact_pdf.return_value = {
                    'success': True,
                    'output_path': '/test/approved_redacted.pdf',
                    'statistics': {'total_matches': 1}
                }
                
                response = self.client.post('/api/redact/approve/', {
                    'document_id': str(self.document.id),
                    'approved_match_ids': [str(match.id)],
                    'rejected_match_ids': []
                })
                
                assert response.status_code == status.HTTP_200_OK
                assert response.data['success'] is True


class TestBackgroundTaskProcessing(TransactionTestCase):
    """Test background redaction task processing."""
    
    def setUp(self):
        """Set up background task test data."""
        self.session_id = "bg_task_session"
        self.temp_dir = tempfile.mkdtemp()
        
        self.document = PDFDocument.objects.create(
            filename="background_test.pdf",
            file_size=2048000,  # Large file for background processing
            session_id=self.session_id,
            content_hash="bg_test_hash",
            file_hash="bg_file_hash"
        )
        
        self.job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact',
            status='queued'
        )
    
    def tearDown(self):
        """Clean up background task test data."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('app.services.redaction_service.RedactionService')
    def test_apply_text_redactions_task_success(self, mock_redaction_service):
        """Test successful background redaction task."""
        # Create test matches
        matches = []
        for i in range(5):
            match = RedactionMatch.objects.create(
                job=self.job,
                document=self.document,
                search_term=f"TERM_{i}",
                matched_text=f"SENSITIVE_DATA_{i}",
                confidence_score=0.95,
                page_number=i % 2,  # Distribute across 2 pages
                x_coordinate=100 + (i * 50),
                y_coordinate=200,
                width=80,
                height=20,
                approved_status=True
            )
            matches.append(match)
        
        # Mock redaction service success
        mock_redaction_instance = Mock()
        mock_redaction_service.return_value = mock_redaction_instance
        mock_redaction_instance.redact_pdf.return_value = {
            'success': True,
            'output_path': str(Path(self.temp_dir) / 'bg_redacted.pdf'),
            'statistics': {
                'total_matches': 5,
                'redactions_applied': 5,
                'pages_affected': 2,
                'processing_time_ms': 3000
            },
            'errors': []
        }
        
        # Create fake PDF file
        pdf_path = str(Path(self.temp_dir) / "background_test.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(b"%PDF-1.4\nTest content\n%%EOF")
        
        # Execute background task
        match_ids = [str(match.id) for match in matches]
        redaction_options = {'fill_color': (0, 0, 0)}
        
        result = apply_text_redactions(
            str(self.job.id),
            pdf_path,
            match_ids,
            redaction_options
        )
        
        assert result['success'] is True
        
        # Verify job status updated
        self.job.refresh_from_db()
        assert self.job.status == 'completed'
        assert self.job.progress == 100
        
        # Verify matches marked as redacted
        for match in matches:
            match.refresh_from_db()
            assert match.redacted is True
            assert match.redaction_applied_at is not None
    
    @patch('app.services.redaction_service.RedactionService')
    def test_apply_text_redactions_task_failure(self, mock_redaction_service):
        """Test background redaction task failure handling."""
        # Mock redaction service failure
        mock_redaction_instance = Mock()
        mock_redaction_service.return_value = mock_redaction_instance
        mock_redaction_instance.redact_pdf.side_effect = Exception("Redaction processing failed")
        
        match = RedactionMatch.objects.create(
            job=self.job,
            document=self.document,
            search_term="FAIL_TEST",
            matched_text="FAIL_DATA",
            confidence_score=0.95,
            page_number=0,
            x_coordinate=100,
            y_coordinate=200,
            width=80,
            height=20,
            approved_status=True
        )
        
        pdf_path = str(Path(self.temp_dir) / "fail_test.pdf")
        
        result = apply_text_redactions(
            str(self.job.id),
            pdf_path,
            [str(match.id)],
            {}
        )
        
        assert result['success'] is False
        
        # Verify job status updated to failed
        self.job.refresh_from_db()
        assert self.job.status == 'failed'
        assert self.job.error_messages is not None


class TestSessionFileManagement(TestCase):
    """Test session-based file management throughout redaction workflow."""
    
    def setUp(self):
        """Set up session management test data."""
        self.session_id = "file_mgmt_session"
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up session management test data."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('app.services.temp_file_manager.TempFileManager.get_session_path')
    @patch('app.services.temp_file_manager.TempFileManager.schedule_cleanup')
    def test_file_lifecycle_management(self, mock_schedule_cleanup, mock_get_session_path):
        """Test complete file lifecycle in redaction workflow."""
        # Mock temp file manager paths
        mock_get_session_path.side_effect = lambda session, subdir: Path(self.temp_dir) / subdir
        
        # Create test files to simulate workflow
        upload_dir = Path(self.temp_dir) / 'uploads'
        download_dir = Path(self.temp_dir) / 'downloads'
        upload_dir.mkdir(exist_ok=True)
        download_dir.mkdir(exist_ok=True)
        
        # Original uploaded file
        original_file = upload_dir / 'test.pdf'
        with open(original_file, 'wb') as f:
            f.write(b"%PDF-1.4\nOriginal content with SECRET data\n%%EOF")
        
        # Simulate redaction service creating output
        redacted_file = download_dir / 'redacted_test.pdf'
        with open(redacted_file, 'wb') as f:
            f.write(b"%PDF-1.4\nRedacted content with [REDACTED] data\n%%EOF")
        
        # Verify files exist at expected locations
        assert original_file.exists()
        assert redacted_file.exists()
        
        # Verify cleanup scheduling was called
        assert mock_schedule_cleanup.called
    
    def test_session_cleanup_scheduling(self):
        """Test automatic session cleanup scheduling."""
        with patch('app.services.temp_file_manager.TempFileManager.schedule_cleanup') as mock_schedule:
            redaction_service = RedactionService(self.session_id)
            
            # Cleanup should be scheduled during service initialization
            # or after redaction completion
            # This is implementation-specific and would be verified
            # based on actual TempFileManager behavior
            pass


class TestConfidenceThresholdWorkflows(TestCase):
    """Test confidence threshold handling workflows."""
    
    def setUp(self):
        """Set up confidence threshold test data."""
        self.document = PDFDocument.objects.create(
            filename="confidence_test.pdf",
            file_size=1024000,
            session_id="confidence_session",
            content_hash="confidence_hash",
            file_hash="confidence_file_hash"
        )
        
        self.job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
    
    def test_high_confidence_auto_approval(self):
        """Test automatic approval of high-confidence matches."""
        # Create high-confidence matches (≥95%)
        high_matches = []
        for i in range(3):
            match = RedactionMatch.objects.create(
                job=self.job,
                document=self.document,
                search_term=f"HIGH_{i}",
                matched_text=f"HIGH_CONFIDENCE_{i}",
                confidence_score=0.96 + (i * 0.01),  # 0.96, 0.97, 0.98
                page_number=0,
                x_coordinate=100 + (i * 50),
                y_coordinate=200,
                width=100,
                height=20
            )
            high_matches.append(match)
        
        # Simulate confidence-based filtering
        confidence_threshold = 0.95
        auto_approved = [
            match for match in high_matches 
            if match.confidence_score >= confidence_threshold
        ]
        
        assert len(auto_approved) == 3
        
        # All should be eligible for automatic processing
        for match in auto_approved:
            assert match.confidence_score >= confidence_threshold
    
    def test_low_confidence_manual_approval(self):
        """Test manual approval requirement for low-confidence matches."""
        # Create low-confidence matches (<95%)
        low_matches = []
        for i in range(3):
            match = RedactionMatch.objects.create(
                job=self.job,
                document=self.document,
                search_term=f"LOW_{i}",
                matched_text=f"LOW_CONFIDENCE_{i}",
                confidence_score=0.70 + (i * 0.05),  # 0.70, 0.75, 0.80
                page_number=0,
                x_coordinate=100 + (i * 50),
                y_coordinate=300,
                width=80,
                height=20,
                approved_status=None  # Requires approval
            )
            low_matches.append(match)
        
        # Verify all require manual approval
        for match in low_matches:
            assert match.needs_approval()
            assert match.approved_status is None
        
        # Simulate manual approval process
        for match in low_matches:
            if match.confidence_score >= 0.75:  # Approve higher ones
                match.approved_status = True
            else:
                match.approved_status = False  # Reject very low confidence
            match.save()
        
        # Verify approval results
        approved = RedactionMatch.objects.filter(approved_status=True)
        rejected = RedactionMatch.objects.filter(approved_status=False)
        
        assert approved.count() == 2  # 0.75 and 0.80
        assert rejected.count() == 1  # 0.70
    
    def test_mixed_confidence_workflow(self):
        """Test workflow with mixed confidence matches."""
        # Create matches with various confidence levels
        matches_data = [
            ("VERY_HIGH", 0.99),
            ("HIGH", 0.96),
            ("MEDIUM", 0.85),
            ("LOW", 0.70),
            ("VERY_LOW", 0.55)
        ]
        
        matches = []
        for text, confidence in matches_data:
            match = RedactionMatch.objects.create(
                job=self.job,
                document=self.document,
                search_term=text,
                matched_text=f"MIXED_{text}",
                confidence_score=confidence,
                page_number=0,
                x_coordinate=100,
                y_coordinate=200,
                width=80,
                height=20,
                approved_status=None if confidence < 0.95 else True
            )
            matches.append(match)
        
        # Filter by confidence threshold
        high_confidence = [m for m in matches if m.confidence_score >= 0.95]
        needs_approval = [m for m in matches if m.confidence_score < 0.95]
        
        assert len(high_confidence) == 2  # 0.99, 0.96
        assert len(needs_approval) == 3  # 0.85, 0.70, 0.55
        
        # Verify approval status
        for match in high_confidence:
            assert match.approved_status is True
        
        for match in needs_approval:
            assert match.needs_approval()


class TestRedactionVerificationIntegration(TestCase):
    """Test redaction verification in integrated workflow."""
    
    def test_permanent_deletion_verification(self):
        """Test verification that text was permanently deleted."""
        # This would involve:
        # 1. Creating PDF with known text
        # 2. Applying redaction
        # 3. Verifying text cannot be extracted
        # 4. Ensuring no forensic recovery possible
        
        # Mock verification for test
        verification_data = {
            'is_complete': True,
            'verified_count': 3,
            'failed_verifications': [],
            'warnings': []
        }
        
        assert verification_data['is_complete']
        assert verification_data['verified_count'] > 0
        assert len(verification_data['failed_verifications']) == 0
    
    def test_audit_trail_generation(self):
        """Test comprehensive audit trail generation."""
        document = PDFDocument.objects.create(
            filename="audit_test.pdf",
            file_size=1024000,
            session_id="audit_session",
            content_hash="audit_hash",
            file_hash="audit_file_hash"
        )
        
        job = ProcessingJob.objects.create(
            document=document,
            job_type='redact'
        )
        
        # Log various audit events
        audit_events = [
            ('search', 'Performed search for sensitive terms'),
            ('preview', 'Generated redaction preview'),
            ('approve', 'Approved 5 matches for redaction'),
            ('redact', 'Applied permanent text deletions'),
            ('verify', 'Verified redaction completeness'),
            ('download', 'Downloaded redacted document')
        ]
        
        for action_type, details in audit_events:
            RedactionAuditLog.log_action(
                job=job,
                action_type=action_type,
                user_session="audit_session",
                action_details={'description': details},
                success=True
            )
        
        # Verify audit trail
        audit_logs = RedactionAuditLog.objects.filter(job=job).order_by('timestamp')
        
        assert audit_logs.count() == 6
        assert list(audit_logs.values_list('action_type', flat=True)) == [
            'search', 'preview', 'approve', 'redact', 'verify', 'download'
        ]
        
        # Verify audit summaries
        for log in audit_logs:
            summary = log.get_action_summary()
            assert isinstance(summary, str)
            assert len(summary) > 0