"""
Comprehensive test fixtures and utilities for backend testing.

This module provides fixtures for PDF documents, database objects,
API clients, and testing utilities for the PDF processing application.
"""

import os
import io
import tempfile
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from unittest.mock import Mock, patch
import uuid

import pytest
import factory
from faker import Faker
from freezegun import freeze_time
import responses
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test.utils import override_settings

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from PyPDF2 import PdfWriter, PdfReader

from app.models import Document, ProcessingJob, RedactionMatch
from app.services.pdf_processor import PDFProcessor

fake = Faker()


# Test settings override
TEST_MEDIA_ROOT = tempfile.mkdtemp()
TEST_REDIS_URL = "redis://localhost:6379/1"


@pytest.fixture(scope="session")
def test_settings(django_db_blocker):
    """Set up test database with proper configuration."""
    from django.test.utils import override_settings
    with django_db_blocker.unblock():
        os.makedirs(TEST_MEDIA_ROOT, exist_ok=True)
        with override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, REDIS_URL=TEST_REDIS_URL,
                               CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True):
            yield


@pytest.fixture
def api_client():
    """Create Django test client for API testing."""
    return APIClient()


@pytest.fixture
def session_id():
    """Generate unique session ID for testing."""
    return str(uuid.uuid4())


@pytest.fixture
def test_user():
    """Create anonymous test user."""
    return AnonymousUser()


# PDF Document Fixtures
@pytest.fixture
def simple_text_pdf():
    """Create simple text-only PDF document."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    content = [
        Paragraph("Test Document", styles['Title']),
        Paragraph("This is a simple test document with some text content.", styles['Normal']),
        Paragraph("It contains multiple paragraphs for testing text extraction.", styles['Normal']),
        Paragraph("The document includes common words that can be searched and redacted.", styles['Normal']),
        Paragraph("Email: test@example.com", styles['Normal']),
        Paragraph("Phone: 555-123-4567", styles['Normal']),
        Paragraph("SSN: 123-45-6789", styles['Normal']),
    ]
    
    doc.build(content)
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def multi_page_pdf():
    """Create multi-page PDF document."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    
    content = []
    for page_num in range(1, 6):  # 5 pages
        content.extend([
            Paragraph(f"Page {page_num}", styles['Title']),
            Paragraph(f"This is content for page {page_num}.", styles['Normal']),
            Paragraph(f"Page {page_num} contains unique content for testing.", styles['Normal']),
            Paragraph("Common footer text appears on all pages.", styles['Normal']),
        ])
        if page_num < 5:
            content.append(PageBreak())
    
    doc.build(content)
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def table_pdf():
    """Create PDF with tables for extraction testing."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create table data
    table_data = [
        ['Name', 'Age', 'City', 'Email'],
        ['John Doe', '30', 'New York', 'john@example.com'],
        ['Jane Smith', '25', 'Los Angeles', 'jane@example.com'],
        ['Bob Johnson', '35', 'Chicago', 'bob@example.com'],
        ['Alice Brown', '28', 'Houston', 'alice@example.com'],
    ]
    
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    content = [
        Paragraph("Employee Information", styles['Title']),
        table,
        Paragraph("This table contains employee data for testing table extraction.", styles['Normal']),
    ]
    
    doc.build(content)
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def large_pdf():
    """Create large PDF document for performance testing."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    content = []
    # Generate 100 pages of content
    for page_num in range(1, 101):
        content.extend([
            Paragraph(f"Page {page_num} - Performance Test", styles['Title']),
            Paragraph(fake.text(max_nb_chars=2000), styles['Normal']),
            Paragraph(fake.text(max_nb_chars=1500), styles['Normal']),
            Paragraph(fake.text(max_nb_chars=1000), styles['Normal']),
        ])
        if page_num < 100:
            content.append(PageBreak())
    
    doc.build(content)
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def corrupted_pdf():
    """Create corrupted PDF file for error testing."""
    # Create a valid PDF first
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "This will be corrupted")
    c.save()
    
    # Corrupt the PDF by truncating it
    pdf_data = buffer.getvalue()
    corrupted_data = pdf_data[:len(pdf_data)//2]  # Cut in half
    
    return corrupted_data


@pytest.fixture
def password_protected_pdf():
    """Create password-protected PDF document."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "This is a password protected document")
    c.drawString(100, 700, "Password: testpass123")
    c.save()
    
    # Read and encrypt the PDF
    buffer.seek(0)
    reader = PdfReader(buffer)
    writer = PdfWriter()
    
    for page in reader.pages:
        writer.add_page(page)
    
    writer.encrypt("testpass123")
    
    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    
    return output_buffer.getvalue()


# Factory Classes
class DocumentFactory(factory.django.DjangoModelFactory):
    """Factory for creating Document instances."""
    
    class Meta:
        model = Document
    
    filename = factory.LazyFunction(lambda: f"test_{fake.file_name(extension='pdf')}")
    session_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    size = factory.LazyFunction(lambda: fake.random_int(min=1000, max=10000000))
    pages = factory.LazyFunction(lambda: fake.random_int(min=1, max=100))
    created_at = factory.LazyFunction(fake.date_time_this_year)


class ProcessingJobFactory(factory.django.DjangoModelFactory):
    """Factory for creating ProcessingJob instances."""
    
    class Meta:
        model = ProcessingJob
    
    document = factory.SubFactory(DocumentFactory)
    job_type = factory.Iterator(['redaction', 'split', 'merge', 'extraction'])
    status = factory.Iterator(['pending', 'processing', 'completed', 'failed'])
    progress = factory.LazyFunction(lambda: fake.random_int(min=0, max=100))
    created_at = factory.LazyFunction(fake.date_time_this_year)


class RedactionMatchFactory(factory.django.DjangoModelFactory):
    """Factory for creating RedactionMatch instances."""
    
    class Meta:
        model = RedactionMatch
    
    job = factory.SubFactory(ProcessingJobFactory, job_type='redaction')
    page_number = factory.LazyFunction(lambda: fake.random_int(min=1, max=10))
    text = factory.LazyFunction(fake.word)
    confidence = factory.LazyFunction(lambda: fake.random_int(min=60, max=100))
    x1 = factory.LazyFunction(lambda: fake.random_int(min=10, max=400))
    y1 = factory.LazyFunction(lambda: fake.random_int(min=10, max=700))
    x2 = factory.LazyFunction(lambda: fake.random_int(min=450, max=600))
    y2 = factory.LazyFunction(lambda: fake.random_int(min=750, max=800))
    approved = factory.Iterator([True, False, None])


# File Upload Fixtures
@pytest.fixture
def uploaded_pdf_file(simple_text_pdf):
    """Create uploaded PDF file for testing."""
    return SimpleUploadedFile(
        "test_document.pdf",
        simple_text_pdf,
        content_type="application/pdf"
    )


@pytest.fixture
def uploaded_large_file(large_pdf):
    """Create uploaded large PDF file for testing."""
    return SimpleUploadedFile(
        "large_document.pdf",
        large_pdf,
        content_type="application/pdf"
    )


@pytest.fixture
def uploaded_corrupted_file(corrupted_pdf):
    """Create uploaded corrupted PDF file for testing."""
    return SimpleUploadedFile(
        "corrupted_document.pdf",
        corrupted_pdf,
        content_type="application/pdf"
    )


# Mock Fixtures
@pytest.fixture
def mock_redis():
    """Mock Redis cache for testing."""
    with patch('django.core.cache.cache') as mock_cache:
        mock_cache.get.return_value = None
        mock_cache.set.return_value = True
        mock_cache.delete.return_value = True
        yield mock_cache


@pytest.fixture
def mock_celery():
    """Mock Celery tasks for testing."""
    with patch('app.tasks.process_pdf.delay') as mock_task:
        mock_task.return_value.id = str(uuid.uuid4())
        mock_task.return_value.status = 'PENDING'
        yield mock_task


@pytest.fixture
def mock_file_system():
    """Mock file system operations for testing."""
    with patch('os.makedirs'), \
         patch('os.path.exists', return_value=True), \
         patch('os.path.getsize', return_value=1024), \
         patch('shutil.rmtree'):
        yield


@pytest.fixture
def mock_pdf_processor():
    """Mock PDF processor service for testing."""
    with patch('app.services.pdf_processor.PDFProcessor') as mock_processor:
        mock_processor.return_value.validate_pdf.return_value = True
        mock_processor.return_value.extract_text.return_value = "Sample text content"
        mock_processor.return_value.extract_metadata.return_value = {
            'pages': 1, 'title': 'Test Document', 'author': 'Test Author'
        }
        mock_processor.return_value.get_page_count.return_value = 1
        yield mock_processor


# Session and Database Fixtures
@pytest.fixture
def test_session(session_id):
    """Create test session directory and cleanup."""
    session_dir = Path(TEST_MEDIA_ROOT) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    yield session_id
    
    # Cleanup
    import shutil
    if session_dir.exists():
        shutil.rmtree(session_dir)


@pytest.fixture
def sample_documents(db, test_session):
    """Create sample documents for testing."""
    documents = []
    for i in range(3):
        doc = DocumentFactory(session_id=test_session)
        documents.append(doc)
    return documents


@pytest.fixture
def sample_jobs(db, sample_documents):
    """Create sample processing jobs for testing."""
    jobs = []
    for doc in sample_documents:
        job = ProcessingJobFactory(document=doc)
        jobs.append(job)
    return jobs


@pytest.fixture
def sample_redaction_matches(db, sample_jobs):
    """Create sample redaction matches for testing."""
    matches = []
    redaction_job = next((job for job in sample_jobs if job.job_type == 'redaction'), None)
    if redaction_job:
        for i in range(5):
            match = RedactionMatchFactory(job=redaction_job)
            matches.append(match)
    return matches


# Time and Performance Fixtures
@pytest.fixture
def frozen_time():
    """Freeze time for consistent testing."""
    with freeze_time("2024-01-01 12:00:00"):
        yield


@pytest.fixture
def performance_timer():
    """Timer for performance testing."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return Timer()


# HTTP Mocking Fixtures
@pytest.fixture
def mock_http_responses():
    """Mock HTTP responses for external API testing."""
    with responses.RequestsMock() as rsps:
        yield rsps


# Test Data Cleanup
@pytest.fixture(autouse=True)
def cleanup_test_data(request):
    """Automatically cleanup test data after each test."""
    yield
    
    # Cleanup test files
    sid = request.node.funcargs.get('session_id')
    if sid:
        session_dir = Path(TEST_MEDIA_ROOT) / sid
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir)


# Pytest Markers
pytestmark = [
    pytest.mark.django_db,
]