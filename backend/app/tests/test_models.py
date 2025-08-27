"""Unit tests for Django models in Ultimate PDF application."""

import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import timezone
from unittest.mock import patch
import uuid

from app.models import PDFDocument, ProcessingJob, RedactionMatch


class PDFDocumentModelTest(TestCase):
    """Test cases for PDFDocument model."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_document_data = {
            'filename': 'test_document.pdf',
            'file_size': 1024000,
            'session_id': 'test_session_123',
            'content_hash': 'abc123def456'
        }
    
    def test_pdf_document_creation(self):
        """Test creating a PDFDocument with valid data."""
        document = PDFDocument.objects.create(**self.valid_document_data)
        
        self.assertEqual(document.filename, 'test_document.pdf')
        self.assertEqual(document.file_size, 1024000)
        self.assertEqual(document.session_id, 'test_session_123')
        self.assertEqual(document.content_hash, 'abc123def456')
        self.assertIsInstance(document.id, uuid.UUID)
        self.assertIsNotNone(document.upload_timestamp)
    
    def test_pdf_document_str_representation(self):
        """Test string representation of PDFDocument."""
        document = PDFDocument.objects.create(**self.valid_document_data)
        expected_str = f"{document.filename} ({document.session_id})"
        self.assertEqual(str(document), expected_str)
    
    def test_pdf_document_ordering(self):
        """Test that documents are ordered by upload timestamp (newest first)."""
        # Create first document
        doc1 = PDFDocument.objects.create(
            filename='first.pdf',
            file_size=100,
            session_id='session1',
            content_hash='hash1'
        )
        
        # Create second document
        doc2 = PDFDocument.objects.create(
            filename='second.pdf',
            file_size=200,
            session_id='session2',
            content_hash='hash2'
        )
        
        documents = list(PDFDocument.objects.all())
        self.assertEqual(documents[0], doc2)  # Newest first
        self.assertEqual(documents[1], doc1)
    
    def test_pdf_document_required_fields(self):
        """Test that required fields cannot be empty."""
        with self.assertRaises(IntegrityError):
            PDFDocument.objects.create(
                filename='',  # Empty filename should fail
                file_size=1000,
                session_id='session',
                content_hash='hash'
            )
    
    def test_pdf_document_session_id_indexing(self):
        """Test that session_id is properly indexed."""
        # Create documents with same session_id
        for i in range(3):
            PDFDocument.objects.create(
                filename=f'doc_{i}.pdf',
                file_size=1000 * i,
                session_id='shared_session',
                content_hash=f'hash_{i}'
            )
        
        # Query by session_id should be efficient (indexed)
        session_docs = PDFDocument.objects.filter(session_id='shared_session')
        self.assertEqual(session_docs.count(), 3)


class ProcessingJobModelTest(TestCase):
    """Test cases for ProcessingJob model."""
    
    def setUp(self):
        """Set up test data."""
        self.document = PDFDocument.objects.create(
            filename='test.pdf',
            file_size=5000,
            session_id='job_test_session',
            content_hash='job_test_hash'
        )
    
    def test_processing_job_creation(self):
        """Test creating a ProcessingJob with valid data."""
        job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
        
        self.assertEqual(job.document, self.document)
        self.assertEqual(job.job_type, 'redact')
        self.assertEqual(job.status, 'pending')  # Default status
        self.assertEqual(job.progress, 0)  # Default progress
        self.assertEqual(job.error_messages, '')  # Default empty
        self.assertIsInstance(job.id, uuid.UUID)
        self.assertIsNotNone(job.created_at)
        self.assertIsNotNone(job.updated_at)
    
    def test_processing_job_str_representation(self):
        """Test string representation of ProcessingJob."""
        job = ProcessingJob.objects.create(
            document=self.document,
            job_type='split',
            status='processing'
        )
        expected_str = f"split job for {self.document.filename} (processing)"
        self.assertEqual(str(job), expected_str)
    
    def test_job_type_choices(self):
        """Test that only valid job types are accepted."""
        valid_types = ['redact', 'split', 'merge', 'extract']
        
        for job_type in valid_types:
            job = ProcessingJob.objects.create(
                document=self.document,
                job_type=job_type
            )
            self.assertEqual(job.job_type, job_type)
    
    def test_status_choices(self):
        """Test that only valid status values are accepted."""
        valid_statuses = ['pending', 'processing', 'completed', 'failed']
        
        for status_val in valid_statuses:
            job = ProcessingJob.objects.create(
                document=self.document,
                job_type='redact',
                status=status_val
            )
            self.assertEqual(job.status, status_val)
    
    def test_progress_validation(self):
        """Test progress field validation (0-100)."""
        # Valid progress values
        for progress in [0, 25, 50, 75, 100]:
            job = ProcessingJob.objects.create(
                document=self.document,
                job_type='redact',
                progress=progress
            )
            self.assertEqual(job.progress, progress)
    
    def test_job_ordering(self):
        """Test that jobs are ordered by creation time (newest first)."""
        job1 = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
        
        job2 = ProcessingJob.objects.create(
            document=self.document,
            job_type='split'
        )
        
        jobs = list(ProcessingJob.objects.all())
        self.assertEqual(jobs[0], job2)  # Newest first
        self.assertEqual(jobs[1], job1)
    
    def test_job_document_relationship(self):
        """Test the relationship between ProcessingJob and PDFDocument."""
        job1 = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
        
        job2 = ProcessingJob.objects.create(
            document=self.document,
            job_type='split'
        )
        
        # Test reverse relationship
        document_jobs = self.document.jobs.all()
        self.assertEqual(document_jobs.count(), 2)
        self.assertIn(job1, document_jobs)
        self.assertIn(job2, document_jobs)


class RedactionMatchModelTest(TestCase):
    """Test cases for RedactionMatch model."""
    
    def setUp(self):
        """Set up test data."""
        self.document = PDFDocument.objects.create(
            filename='redaction_test.pdf',
            file_size=3000,
            session_id='redaction_session',
            content_hash='redaction_hash'
        )
        
        self.job = ProcessingJob.objects.create(
            document=self.document,
            job_type='redact'
        )
    
    def test_redaction_match_creation(self):
        """Test creating a RedactionMatch with valid data."""
        match = RedactionMatch.objects.create(
            job=self.job,
            text='John Adams',
            confidence_score=85.5,
            page_number=1,
            x_coordinate=100.0,
            y_coordinate=200.0,
            width=50.0,
            height=15.0
        )
        
        self.assertEqual(match.job, self.job)
        self.assertEqual(match.text, 'John Adams')
        self.assertEqual(match.confidence_score, 85.5)
        self.assertEqual(match.page_number, 1)
        self.assertEqual(match.x_coordinate, 100.0)
        self.assertEqual(match.y_coordinate, 200.0)
        self.assertEqual(match.width, 50.0)
        self.assertEqual(match.height, 15.0)
        self.assertIsNone(match.approved_status)  # Default null
        self.assertIsNotNone(match.created_at)
    
    def test_redaction_match_str_representation(self):
        """Test string representation of RedactionMatch."""
        long_text = "This is a very long text that should be truncated in the string representation"
        match = RedactionMatch.objects.create(
            job=self.job,
            text=long_text,
            confidence_score=92.3,
            page_number=2,
            x_coordinate=150.0,
            y_coordinate=300.0,
            width=100.0,
            height=20.0
        )
        
        expected_str = f"Match '{long_text[:50]}...' (92.3% confidence)"
        self.assertEqual(str(match), expected_str)
    
    def test_redaction_match_approval_status(self):
        """Test approval status field (True, False, None)."""
        # Test approved match
        approved_match = RedactionMatch.objects.create(
            job=self.job,
            text='Approved text',
            confidence_score=90.0,
            page_number=1,
            approved_status=True,
            x_coordinate=100.0,
            y_coordinate=200.0,
            width=50.0,
            height=15.0
        )
        self.assertTrue(approved_match.approved_status)
        
        # Test rejected match
        rejected_match = RedactionMatch.objects.create(
            job=self.job,
            text='Rejected text',
            confidence_score=75.0,
            page_number=1,
            approved_status=False,
            x_coordinate=200.0,
            y_coordinate=300.0,
            width=60.0,
            height=18.0
        )
        self.assertFalse(rejected_match.approved_status)
        
        # Test pending match (None)
        pending_match = RedactionMatch.objects.create(
            job=self.job,
            text='Pending text',
            confidence_score=80.0,
            page_number=2,
            x_coordinate=300.0,
            y_coordinate=400.0,
            width=70.0,
            height=20.0
        )
        self.assertIsNone(pending_match.approved_status)
    
    def test_redaction_match_ordering(self):
        """Test that matches are ordered by confidence (highest first) then page number."""
        match1 = RedactionMatch.objects.create(
            job=self.job,
            text='Low confidence',
            confidence_score=75.0,
            page_number=2,
            x_coordinate=100.0,
            y_coordinate=200.0,
            width=50.0,
            height=15.0
        )
        
        match2 = RedactionMatch.objects.create(
            job=self.job,
            text='High confidence',
            confidence_score=95.0,
            page_number=1,
            x_coordinate=150.0,
            y_coordinate=250.0,
            width=60.0,
            height=18.0
        )
        
        match3 = RedactionMatch.objects.create(
            job=self.job,
            text='Same confidence, later page',
            confidence_score=95.0,
            page_number=3,
            x_coordinate=200.0,
            y_coordinate=300.0,
            width=70.0,
            height=20.0
        )
        
        matches = list(RedactionMatch.objects.all())
        self.assertEqual(matches[0], match2)  # Highest confidence, earliest page
        self.assertEqual(matches[1], match3)  # Same confidence, later page
        self.assertEqual(matches[2], match1)  # Lowest confidence
    
    def test_redaction_match_job_relationship(self):
        """Test the relationship between RedactionMatch and ProcessingJob."""
        match1 = RedactionMatch.objects.create(
            job=self.job,
            text='First match',
            confidence_score=80.0,
            page_number=1,
            x_coordinate=100.0,
            y_coordinate=200.0,
            width=50.0,
            height=15.0
        )
        
        match2 = RedactionMatch.objects.create(
            job=self.job,
            text='Second match',
            confidence_score=90.0,
            page_number=2,
            x_coordinate=150.0,
            y_coordinate=250.0,
            width=60.0,
            height=18.0
        )
        
        # Test reverse relationship
        job_matches = self.job.matches.all()
        self.assertEqual(job_matches.count(), 2)
        self.assertIn(match1, job_matches)
        self.assertIn(match2, job_matches)
    
    def test_redaction_match_coordinate_precision(self):
        """Test that coordinate fields handle float precision correctly."""
        match = RedactionMatch.objects.create(
            job=self.job,
            text='Precision test',
            confidence_score=88.888,
            page_number=1,
            x_coordinate=123.456789,
            y_coordinate=987.654321,
            width=45.123456,
            height=12.987654
        )
        
        # Verify precision is maintained
        self.assertAlmostEqual(match.confidence_score, 88.888, places=3)
        self.assertAlmostEqual(match.x_coordinate, 123.456789, places=6)
        self.assertAlmostEqual(match.y_coordinate, 987.654321, places=6)
        self.assertAlmostEqual(match.width, 45.123456, places=6)
        self.assertAlmostEqual(match.height, 12.987654, places=6)


@pytest.mark.django_db
class ModelIntegrationTest(TestCase):
    """Integration tests for model relationships."""
    
    def test_cascade_deletion(self):
        """Test that related objects are properly deleted on cascade."""
        # Create document
        document = PDFDocument.objects.create(
            filename='cascade_test.pdf',
            file_size=2000,
            session_id='cascade_session',
            content_hash='cascade_hash'
        )
        
        # Create job
        job = ProcessingJob.objects.create(
            document=document,
            job_type='redact'
        )
        
        # Create matches
        RedactionMatch.objects.create(
            job=job,
            text='Match 1',
            confidence_score=85.0,
            page_number=1,
            x_coordinate=100.0,
            y_coordinate=200.0,
            width=50.0,
            height=15.0
        )
        
        RedactionMatch.objects.create(
            job=job,
            text='Match 2',
            confidence_score=90.0,
            page_number=2,
            x_coordinate=150.0,
            y_coordinate=250.0,
            width=60.0,
            height=18.0
        )
        
        # Verify initial counts
        self.assertEqual(PDFDocument.objects.count(), 1)
        self.assertEqual(ProcessingJob.objects.count(), 1)
        self.assertEqual(RedactionMatch.objects.count(), 2)
        
        # Delete document - should cascade delete job and matches
        document.delete()
        
        # Verify cascade deletion
        self.assertEqual(PDFDocument.objects.count(), 0)
        self.assertEqual(ProcessingJob.objects.count(), 0)
        self.assertEqual(RedactionMatch.objects.count(), 0)
    
    def test_model_meta_properties(self):
        """Test model Meta class properties."""
        # Test PDFDocument Meta
        self.assertEqual(PDFDocument._meta.db_table, 'pdf_documents')
        self.assertEqual(PDFDocument._meta.ordering, ['-upload_timestamp'])
        
        # Test ProcessingJob Meta  
        self.assertEqual(ProcessingJob._meta.db_table, 'processing_jobs')
        self.assertEqual(ProcessingJob._meta.ordering, ['-created_at'])
        
        # Test RedactionMatch Meta
        self.assertEqual(RedactionMatch._meta.db_table, 'redaction_matches')
        self.assertEqual(RedactionMatch._meta.ordering, ['-confidence_score', 'page_number'])