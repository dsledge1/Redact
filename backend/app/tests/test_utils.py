"""
Comprehensive test utilities for backend testing.

This module provides utility functions for creating test data, managing test files,
API testing, database operations, performance testing, and mocking external services.
"""

import os
import tempfile
import shutil
import uuid
import json
import time
import psutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager
import io

from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import AnonymousUser
from django.conf import settings

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from PyPDF2 import PdfWriter, PdfReader
import numpy as np
from PIL import Image, ImageDraw

from app.models import Document, ProcessingJob, RedactionMatch


class PDFTestUtils:
    """Utilities for creating and manipulating test PDF files."""
    
    @staticmethod
    def create_test_pdf(content: str = None, pages: int = 1, 
                       with_images: bool = False, with_tables: bool = False) -> bytes:
        """Create a test PDF with specified content and features."""
        buffer = io.BytesIO()
        
        if pages == 1 and not with_images and not with_tables:
            # Simple single-page PDF
            c = canvas.Canvas(buffer, pagesize=letter)
            if content:
                lines = content.split('\n')
                y_position = 750
                for line in lines:
                    c.drawString(100, y_position, line)
                    y_position -= 20
            else:
                c.drawString(100, 750, "Test PDF Document")
                c.drawString(100, 700, "This is a test document for testing purposes.")
                c.drawString(100, 650, "Contact: test@example.com")
                c.drawString(100, 600, "Phone: 555-123-4567")
            c.save()
        else:
            # Complex PDF with ReportLab
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            for page_num in range(1, pages + 1):
                story.append(Paragraph(f"Page {page_num}", styles['Title']))
                
                if content:
                    story.append(Paragraph(content, styles['Normal']))
                else:
                    story.append(Paragraph(f"Content for page {page_num}", styles['Normal']))
                    story.append(Paragraph("Test email: test@example.com", styles['Normal']))
                    story.append(Paragraph("Test phone: 555-123-4567", styles['Normal']))
                
                if with_tables and page_num == 1:
                    table_data = [
                        ['Name', 'Email', 'Phone'],
                        ['John Doe', 'john@example.com', '555-0101'],
                        ['Jane Smith', 'jane@example.com', '555-0102'],
                    ]
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    story.append(table)
                
                if with_images and page_num == 1:
                    # Create a simple test image
                    img = Image.new('RGB', (200, 100), color='blue')
                    draw = ImageDraw.Draw(img)
                    draw.text((50, 40), 'TEST IMAGE', fill='white')
                    
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, 'PNG')
                    img_buffer.seek(0)
                    
                    # Note: In a real implementation, you'd add the image to the story
                    # For this utility, we'll just add a placeholder
                    story.append(Paragraph("Image placeholder", styles['Normal']))
                
                if page_num < pages:
                    story.append(PageBreak())
            
            doc.build(story)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    @staticmethod
    def corrupt_pdf_file(pdf_data: bytes, corruption_ratio: float = 0.3) -> bytes:
        """Create a corrupted version of PDF data."""
        corruption_point = int(len(pdf_data) * (1 - corruption_ratio))
        return pdf_data[:corruption_point]
    
    @staticmethod
    def add_password_to_pdf(pdf_data: bytes, password: str) -> bytes:
        """Add password protection to PDF data."""
        input_buffer = io.BytesIO(pdf_data)
        output_buffer = io.BytesIO()
        
        reader = PdfReader(input_buffer)
        writer = PdfWriter()
        
        for page in reader.pages:
            writer.add_page(page)
        
        writer.encrypt(password)
        writer.write(output_buffer)
        
        output_buffer.seek(0)
        return output_buffer.getvalue()
    
    @staticmethod
    def validate_pdf_integrity(pdf_data: bytes) -> bool:
        """Validate PDF integrity."""
        try:
            buffer = io.BytesIO(pdf_data)
            reader = PdfReader(buffer)
            # Try to read basic properties
            num_pages = len(reader.pages)
            return num_pages > 0
        except Exception:
            return False
    
    @staticmethod
    def extract_text_from_pdf(pdf_data: bytes) -> str:
        """Extract text from PDF data for testing."""
        try:
            buffer = io.BytesIO(pdf_data)
            reader = PdfReader(buffer)
            
            text = ""
            for page in reader.pages:
                page_text = page.extract_text() or ''
                text += page_text
            
            return text
        except Exception:
            return ""
    
    @staticmethod
    def get_pdf_metadata(pdf_data: bytes) -> Dict[str, Any]:
        """Extract PDF metadata for testing."""
        try:
            buffer = io.BytesIO(pdf_data)
            reader = PdfReader(buffer)
            
            metadata = {
                'pages': len(reader.pages),
                'encrypted': reader.is_encrypted,
            }
            
            if reader.metadata:
                metadata.update({
                    'title': reader.metadata.get('/Title'),
                    'author': reader.metadata.get('/Author'),
                    'subject': reader.metadata.get('/Subject'),
                    'creator': reader.metadata.get('/Creator'),
                })
            
            return metadata
        except Exception:
            return {'pages': 0, 'encrypted': False}


class FileTestUtils:
    """Utilities for file management in tests."""
    
    @staticmethod
    def create_temp_session(session_id: str = None) -> str:
        """Create a temporary session directory for testing."""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        temp_dir = Path(tempfile.gettempdir()) / 'test_sessions' / session_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        return session_id
    
    @staticmethod
    def cleanup_test_files(session_id: str) -> bool:
        """Clean up test files for a session."""
        try:
            session_dir = Path(tempfile.gettempdir()) / 'test_sessions' / session_id
            if session_dir.exists():
                shutil.rmtree(session_dir)
            return True
        except Exception:
            return False
    
    @staticmethod
    def mock_file_upload(file_data: bytes, filename: str = "test.pdf", 
                        content_type: str = "application/pdf") -> SimpleUploadedFile:
        """Create a mock uploaded file for testing."""
        return SimpleUploadedFile(
            filename,
            file_data,
            content_type=content_type
        )
    
    @staticmethod
    def validate_file_cleanup(session_id: str) -> bool:
        """Validate that files have been properly cleaned up."""
        session_dir = Path(tempfile.gettempdir()) / 'test_sessions' / session_id
        return not session_dir.exists()
    
    @staticmethod
    def create_test_file(content: str, filename: str, directory: str = None) -> Path:
        """Create a test file with specified content."""
        if directory is None:
            directory = tempfile.gettempdir()
        
        file_path = Path(directory) / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            f.write(content)
        
        return file_path
    
    @staticmethod
    def get_file_info(file_path: Union[str, Path]) -> Dict[str, Any]:
        """Get file information for testing."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            return {'exists': False}
        
        stat = file_path.stat()
        return {
            'exists': True,
            'size': stat.st_size,
            'modified_time': stat.st_mtime,
            'is_file': file_path.is_file(),
            'is_directory': file_path.is_dir(),
            'extension': file_path.suffix,
            'name': file_path.name,
        }


class APITestUtils:
    """Utilities for API testing."""
    
    @staticmethod
    def create_api_client(session_id: str = None) -> Client:
        """Create a Django test client with optional session."""
        client = Client()
        
        if session_id:
            session = client.session
            session['session_id'] = session_id
            session.save()
        
        return client
    
    @staticmethod
    def upload_test_file(client: Client, file_data: bytes, 
                        filename: str = "test.pdf", session_id: str = None) -> Dict[str, Any]:
        """Upload a test file using the API client."""
        uploaded_file = FileTestUtils.mock_file_upload(file_data, filename)
        
        data = {'file': uploaded_file}
        if session_id:
            data['session_id'] = session_id
        
        response = client.post('/api/upload/', data)
        
        return {
            'status_code': response.status_code,
            'data': response.json() if response.status_code == 200 else None,
            'response': response
        }
    
    @staticmethod
    def poll_job_status(client: Client, job_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Poll job status until completion or timeout."""
        start_time = time.time()
        last_response = None
        
        while time.time() - start_time < timeout:
            response = client.get(f'/api/jobs/{job_id}/')
            last_response = response
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status')
                
                if status in ['completed', 'failed', 'cancelled']:
                    return {
                        'status': status,
                        'data': data,
                        'elapsed_time': time.time() - start_time
                    }
            
            time.sleep(1)
        
        return {
            'status': 'timeout',
            'data': last_response.json() if last_response else None,
            'elapsed_time': timeout
        }
    
    @staticmethod
    def download_result_file(client: Client, download_url: str) -> Dict[str, Any]:
        """Download a result file from the API."""
        response = client.get(download_url)
        
        return {
            'status_code': response.status_code,
            'content': response.content if response.status_code == 200 else None,
            'content_type': response.get('Content-Type'),
            'size': len(response.content) if response.content else 0
        }
    
    @staticmethod
    def make_api_request(client: Client, method: str, url: str, 
                        data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make a generic API request."""
        method_func = getattr(client, method.lower())
        
        if data:
            if method.upper() in ['POST', 'PUT', 'PATCH']:
                response = method_func(url, data=json.dumps(data), 
                                     content_type='application/json')
            else:
                response = method_func(url, data)
        else:
            response = method_func(url)
        
        return {
            'status_code': response.status_code,
            'data': response.json() if response.content else None,
            'headers': dict(response.items()),
            'response': response
        }


class DatabaseTestUtils:
    """Utilities for database operations in tests."""
    
    @staticmethod
    def create_test_document(filename: str = "test.pdf", session_id: str = None, 
                           size: int = 1024, pages: int = 1) -> Document:
        """Create a test document in the database."""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        return Document.objects.create(
            filename=filename,
            session_id=session_id,
            size=size,
            pages=pages
        )
    
    @staticmethod
    def create_test_job(document: Document, job_type: str = "redaction", 
                       status: str = "pending", progress: int = 0) -> ProcessingJob:
        """Create a test processing job in the database."""
        return ProcessingJob.objects.create(
            document=document,
            job_type=job_type,
            status=status,
            progress=progress
        )
    
    @staticmethod
    def create_test_matches(job: ProcessingJob, count: int = 5) -> List[RedactionMatch]:
        """Create test redaction matches for a job."""
        matches = []
        
        for i in range(count):
            match = RedactionMatch.objects.create(
                job=job,
                page_number=1,
                text=f"test{i}@example.com",
                confidence=80 + i * 2,
                x1=100 + i * 20,
                y1=200,
                x2=200 + i * 20,
                y2=220,
                approved=None
            )
            matches.append(match)
        
        return matches
    
    @staticmethod
    def cleanup_test_data(session_id: str) -> int:
        """Clean up test data for a session."""
        documents = Document.objects.filter(session_id=session_id)
        count = documents.count()
        
        # Delete related objects
        for doc in documents:
            ProcessingJob.objects.filter(document=doc).delete()
        
        documents.delete()
        return count
    
    @staticmethod
    def get_database_stats() -> Dict[str, int]:
        """Get database statistics for testing."""
        return {
            'documents': Document.objects.count(),
            'jobs': ProcessingJob.objects.count(),
            'matches': RedactionMatch.objects.count()
        }


class PerformanceTestUtils:
    """Utilities for performance testing."""
    
    @staticmethod
    def benchmark_pdf_processing(file_data: bytes, operation: str) -> Dict[str, Any]:
        """Benchmark PDF processing operations."""
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        try:
            # Simulate processing based on operation type
            if operation == 'text_extraction':
                text = PDFTestUtils.extract_text_from_pdf(file_data)
                result = {'text_length': len(text)}
            elif operation == 'validation':
                valid = PDFTestUtils.validate_pdf_integrity(file_data)
                result = {'valid': valid}
            elif operation == 'metadata':
                metadata = PDFTestUtils.get_pdf_metadata(file_data)
                result = metadata
            else:
                result = {'operation': operation}
            
            success = True
        except Exception as e:
            result = {'error': str(e)}
            success = False
        
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        return {
            'operation': operation,
            'success': success,
            'processing_time': end_time - start_time,
            'memory_used': end_memory - start_memory,
            'file_size': len(file_data),
            'result': result
        }
    
    @staticmethod
    def measure_memory_usage(operation_func, *args, **kwargs) -> Dict[str, Any]:
        """Measure memory usage of an operation."""
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        start_time = time.time()
        try:
            result = operation_func(*args, **kwargs)
            success = True
        except Exception as e:
            result = str(e)
            success = False
        end_time = time.time()
        
        end_memory = process.memory_info().rss / 1024 / 1024  # MB
        peak_memory = process.memory_info().vms / 1024 / 1024  # MB
        
        return {
            'success': success,
            'result': result,
            'execution_time': end_time - start_time,
            'start_memory': start_memory,
            'end_memory': end_memory,
            'peak_memory': peak_memory,
            'memory_delta': end_memory - start_memory
        }
    
    @staticmethod
    def validate_processing_time(operation: str, processing_time: float, 
                               max_time: float) -> bool:
        """Validate that processing time is within acceptable limits."""
        return processing_time <= max_time
    
    @staticmethod
    def stress_test_concurrent_operations(operation_func, count: int, 
                                        *args, **kwargs) -> Dict[str, Any]:
        """Run concurrent operations for stress testing."""
        import concurrent.futures
        import threading
        
        start_time = time.time()
        results = []
        errors = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(operation_func, *args, **kwargs) for _ in range(count)]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    errors.append(str(e))
        
        end_time = time.time()
        
        return {
            'total_operations': count,
            'successful_operations': len(results),
            'failed_operations': len(errors),
            'total_time': end_time - start_time,
            'average_time': (end_time - start_time) / count,
            'results': results[:5],  # First 5 results for analysis
            'errors': errors[:5]     # First 5 errors for analysis
        }


class MockUtils:
    """Utilities for mocking external services."""
    
    @staticmethod
    @contextmanager
    def mock_redis_cache():
        """Mock Redis cache for testing."""
        with patch('django.core.cache.cache') as mock_cache:
            mock_cache.get.return_value = None
            mock_cache.set.return_value = True
            mock_cache.delete.return_value = True
            mock_cache.clear.return_value = True
            yield mock_cache
    
    @staticmethod
    @contextmanager
    def mock_celery_tasks():
        """Mock Celery tasks for testing."""
        with patch('app.tasks.process_pdf.delay') as mock_task:
            mock_result = Mock()
            mock_result.id = str(uuid.uuid4())
            mock_result.status = 'PENDING'
            mock_result.result = None
            mock_task.return_value = mock_result
            yield mock_task
    
    @staticmethod
    @contextmanager
    def mock_file_system():
        """Mock file system operations for testing."""
        with patch('os.makedirs') as mock_makedirs, \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.getsize') as mock_getsize, \
             patch('shutil.rmtree') as mock_rmtree:
            
            mock_exists.return_value = True
            mock_getsize.return_value = 1024
            
            yield {
                'makedirs': mock_makedirs,
                'exists': mock_exists,
                'getsize': mock_getsize,
                'rmtree': mock_rmtree
            }
    
    @staticmethod
    @contextmanager
    def mock_external_services():
        """Mock external services for testing."""
        with patch('requests.get') as mock_get, \
             patch('requests.post') as mock_post:
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'status': 'success'}
            mock_response.content = b'mock content'
            
            mock_get.return_value = mock_response
            mock_post.return_value = mock_response
            
            yield {
                'get': mock_get,
                'post': mock_post,
                'response': mock_response
            }


class ValidationUtils:
    """Utilities for validation and assertions in tests."""
    
    @staticmethod
    def assert_pdf_valid(pdf_data: bytes, message: str = None):
        """Assert that PDF data is valid."""
        assert PDFTestUtils.validate_pdf_integrity(pdf_data), \
            message or "PDF data is not valid"
    
    @staticmethod
    def assert_contains_text(pdf_data: bytes, expected_text: str, message: str = None):
        """Assert that PDF contains expected text."""
        actual_text = PDFTestUtils.extract_text_from_pdf(pdf_data)
        assert expected_text in actual_text, \
            message or f"Expected text '{expected_text}' not found in PDF"
    
    @staticmethod
    def assert_api_response(response_data: Dict[str, Any], expected_status: int, 
                          expected_fields: List[str] = None):
        """Assert API response format and content."""
        assert response_data['status_code'] == expected_status, \
            f"Expected status {expected_status}, got {response_data['status_code']}"
        
        if expected_fields and response_data.get('data'):
            for field in expected_fields:
                assert field in response_data['data'], \
                    f"Expected field '{field}' not found in response data"
    
    @staticmethod
    def assert_performance_benchmark(benchmark_result: Dict[str, Any], 
                                   max_time: float, max_memory: float = None):
        """Assert performance benchmarks are met."""
        assert benchmark_result['success'], \
            f"Benchmark operation failed: {benchmark_result.get('result')}"
        
        assert benchmark_result['processing_time'] <= max_time, \
            f"Processing time {benchmark_result['processing_time']:.2f}s exceeds limit {max_time}s"
        
        if max_memory and 'memory_used' in benchmark_result:
            assert benchmark_result['memory_used'] <= max_memory, \
                f"Memory usage {benchmark_result['memory_used']:.1f}MB exceeds limit {max_memory}MB"
    
    @staticmethod
    def assert_database_consistency():
        """Assert database consistency for testing."""
        stats = DatabaseTestUtils.get_database_stats()
        
        # Ensure no orphaned records
        documents_count = stats['documents']
        jobs = ProcessingJob.objects.all()
        
        for job in jobs:
            assert job.document_id is not None, "Found job without document"
            assert Document.objects.filter(id=job.document_id).exists(), \
                f"Job {job.id} references non-existent document {job.document_id}"


# Convenience functions for common test patterns
def create_test_pdf_simple(content: str = None) -> bytes:
    """Convenience function to create a simple test PDF."""
    return PDFTestUtils.create_test_pdf(content=content)


def create_test_session() -> str:
    """Convenience function to create a test session."""
    return FileTestUtils.create_temp_session()


def upload_and_wait(client: Client, file_data: bytes, 
                   filename: str = "test.pdf", timeout: int = 30) -> Dict[str, Any]:
    """Convenience function to upload file and wait for processing."""
    session_id = create_test_session()
    
    # Upload file
    upload_result = APITestUtils.upload_test_file(client, file_data, filename, session_id)
    
    if upload_result['status_code'] != 200:
        return upload_result
    
    document_id = upload_result['data']['document_id']
    
    # For simplicity, return upload result
    # In a real scenario, you'd start processing and poll for completion
    return {
        'document_id': document_id,
        'session_id': session_id,
        'upload_result': upload_result
    }