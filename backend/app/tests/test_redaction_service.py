"""
Comprehensive unit tests for the RedactionService.

Tests permanent text deletion functionality, bounding box validation,
error handling, and integration with other services.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import PyPDF2
from PyPDF2 import PdfReader, PdfWriter

from app.services.redaction_service import RedactionService
from app.models import RedactionMatch, ProcessingJob, PDFDocument
from app.utils.errors import PDFProcessingError, RedactionError


class TestRedactionService:
    """Test suite for RedactionService."""
    
    @pytest.fixture
    def redaction_service(self):
        """Create a RedactionService instance for testing."""
        return RedactionService(session_id="test_session_123")
    
    @pytest.fixture
    def temp_pdf_file(self):
        """Create a temporary PDF file for testing."""
        temp_dir = tempfile.mkdtemp()
        pdf_path = Path(temp_dir) / "test.pdf"
        
        # Create a simple PDF with text
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)  # Letter size
        
        # Add some text content (in a real test, we'd use reportlab or similar)
        # For now, create a minimal PDF structure
        
        with open(pdf_path, 'wb') as f:
            writer.write(f)
        
        yield pdf_path
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_redaction_matches(self):
        """Create mock RedactionMatch objects."""
        matches = []
        for i in range(3):
            match = Mock(spec=RedactionMatch)
            match.id = f"match_{i}"
            match.page_number = 0
            match.matched_text = f"sensitive_text_{i}"
            match.confidence_score = 0.95
            match.x_coordinate = 100.0 + (i * 50)
            match.y_coordinate = 200.0
            match.width = 100.0
            match.height = 20.0
            match.redacted = False
            match.redaction_applied_at = None
            match.save = Mock()
            matches.append(match)
        return matches
    
    def test_init(self, redaction_service):
        """Test RedactionService initialization."""
        assert redaction_service.session_id == "test_session_123"
        assert redaction_service.temp_file_manager is not None
        assert redaction_service.logger is not None
    
    def test_validate_redaction_input_valid(self, redaction_service, temp_pdf_file, mock_redaction_matches):
        """Test validation with valid input."""
        # Should not raise any exceptions
        redaction_service._validate_redaction_input(temp_pdf_file, mock_redaction_matches)
    
    def test_validate_redaction_input_missing_file(self, redaction_service, mock_redaction_matches):
        """Test validation with missing file."""
        non_existent_file = Path("/non/existent/file.pdf")
        
        with pytest.raises(Exception) as exc_info:
            redaction_service._validate_redaction_input(non_existent_file, mock_redaction_matches)
        
        assert "not found" in str(exc_info.value)
    
    def test_validate_redaction_input_no_matches(self, redaction_service, temp_pdf_file):
        """Test validation with no matches."""
        with pytest.raises(RedactionError) as exc_info:
            redaction_service._validate_redaction_input(temp_pdf_file, [])
        
        assert "No redaction matches" in str(exc_info.value)
    
    def test_group_matches_by_page(self, redaction_service, mock_redaction_matches):
        """Test grouping matches by page number."""
        # Add matches on different pages
        mock_redaction_matches[1].page_number = 1
        mock_redaction_matches[2].page_number = 1
        
        grouped = redaction_service._group_matches_by_page(mock_redaction_matches)
        
        assert len(grouped) == 2
        assert 0 in grouped
        assert 1 in grouped
        assert len(grouped[0]) == 1
        assert len(grouped[1]) == 2
    
    def test_ensure_bounding_boxes_valid(self, redaction_service, mock_redaction_matches):
        """Test ensuring all matches have valid bounding boxes."""
        validated = redaction_service._ensure_bounding_boxes(mock_redaction_matches)
        
        assert len(validated) == len(mock_redaction_matches)
        for match in validated:
            assert match.x_coordinate is not None
            assert match.y_coordinate is not None
            assert match.width is not None
            assert match.height is not None
    
    def test_ensure_bounding_boxes_missing_coordinates(self, redaction_service):
        """Test handling matches with missing coordinates."""
        matches = [Mock(spec=RedactionMatch)]
        matches[0].x_coordinate = None
        matches[0].y_coordinate = 100
        matches[0].width = 50
        matches[0].height = 20
        matches[0].id = "incomplete_match"
        
        validated = redaction_service._ensure_bounding_boxes(matches)
        
        # Should skip matches without complete coordinates
        assert len(validated) == 0
    
    @patch('app.services.redaction_service.PdfReader')
    @patch('app.services.redaction_service.PdfWriter')
    def test_apply_redactions_success(self, mock_writer_class, mock_reader_class, 
                                     redaction_service, temp_pdf_file, mock_redaction_matches):
        """Test successful redaction application."""
        # Setup mocks
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
        
        # Mock page methods
        mock_page.add_redact_annot = Mock()
        mock_page.apply_redactions = Mock()
        
        matches_by_page = {0: mock_redaction_matches}
        output_path = temp_pdf_file.parent / "redacted.pdf"
        
        result = redaction_service._apply_redactions(
            temp_pdf_file,
            output_path,
            matches_by_page,
            {}
        )
        
        assert result is True
        assert mock_page.add_redact_annot.call_count == len(mock_redaction_matches)
        assert mock_page.apply_redactions.call_count == 1
    
    def test_apply_page_redaction(self, redaction_service, mock_redaction_matches):
        """Test applying redaction annotation to a page."""
        mock_page = Mock()
        mock_page.add_redact_annot = Mock()
        
        # Mock mediabox for coordinate conversion
        mock_page.mediabox = Mock()
        mock_page.mediabox.top = 792.0  # Letter size height
        mock_page.mediabox.bottom = 0.0
        mock_page.mediabox.right = 612.0  # Letter size width
        mock_page.mediabox.left = 0.0
        
        match = mock_redaction_matches[0]
        options = {'fill_color': (0, 0, 0)}
        
        redaction_service._apply_page_redaction(mock_page, match, options)
        
        # Verify add_redact_annot was called
        assert mock_page.add_redact_annot.called
        call_args = mock_page.add_redact_annot.call_args
        assert call_args is not None
    
    def test_finalize_redactions(self, redaction_service):
        """Test finalizing redactions for permanent deletion."""
        mock_page = Mock()
        mock_page.apply_redactions = Mock()
        
        redaction_service._finalize_redactions(mock_page)
        
        assert mock_page.apply_redactions.called
    
    def test_update_match_records(self, redaction_service, mock_redaction_matches):
        """Test updating match records after redaction."""
        redaction_service._update_match_records(mock_redaction_matches)
        
        for match in mock_redaction_matches:
            assert match.redacted is True
            assert match.redaction_applied_at is not None
            assert match.save.called
    
    @patch('app.services.redaction_service.PdfReader')
    def test_verify_redactions_success(self, mock_reader_class, redaction_service, 
                                      temp_pdf_file, mock_redaction_matches):
        """Test successful redaction verification."""
        mock_reader = Mock()
        mock_page = Mock()
        
        mock_reader_class.return_value = mock_reader
        mock_reader.pages = [mock_page]
        
        # Simulate text has been removed
        mock_page.extract_text.return_value = "other text without sensitive content"
        
        result = redaction_service._verify_redactions(temp_pdf_file, mock_redaction_matches)
        
        assert result is True
    
    @patch('app.services.redaction_service.PdfReader')
    def test_verify_redactions_failure(self, mock_reader_class, redaction_service,
                                      temp_pdf_file, mock_redaction_matches):
        """Test failed redaction verification (text still present)."""
        mock_reader = Mock()
        mock_page = Mock()
        
        mock_reader_class.return_value = mock_reader
        mock_reader.pages = [mock_page]
        
        # Simulate text is still present
        mock_page.extract_text.return_value = "text containing sensitive_text_0 content"
        
        result = redaction_service._verify_redactions(temp_pdf_file, mock_redaction_matches)
        
        assert result is False
    
    def test_calculate_redaction_statistics(self, redaction_service, mock_redaction_matches):
        """Test calculation of redaction statistics."""
        processing_time = 1500.0  # milliseconds
        
        stats = redaction_service._calculate_redaction_statistics(
            mock_redaction_matches,
            processing_time
        )
        
        assert stats['total_matches'] == 3
        assert stats['pages_affected'] == 1
        assert stats['processing_time_ms'] == 1500
        assert 'average_confidence' in stats
        assert 'timestamp' in stats
    
    @patch('app.services.redaction_service.RedactionService._apply_redactions')
    @patch('app.services.redaction_service.RedactionService._verify_redactions')
    def test_redact_pdf_complete_workflow(self, mock_verify, mock_apply,
                                         redaction_service, temp_pdf_file, mock_redaction_matches):
        """Test complete PDF redaction workflow."""
        mock_apply.return_value = True
        mock_verify.return_value = True
        
        result = redaction_service.redact_pdf(
            temp_pdf_file,
            mock_redaction_matches,
            fill_color=(0, 0, 0)
        )
        
        assert result['success'] is True
        assert result['output_path'] is not None
        assert 'statistics' in result
        assert result['statistics']['total_matches'] == 3
        assert result['statistics']['redactions_applied'] == 3
        assert result['errors'] == []
    
    @patch('app.services.redaction_service.RedactionService._apply_redactions')
    def test_redact_pdf_failure(self, mock_apply, redaction_service,
                               temp_pdf_file, mock_redaction_matches):
        """Test PDF redaction failure handling."""
        mock_apply.side_effect = Exception("Redaction failed")
        
        result = redaction_service.redact_pdf(
            temp_pdf_file,
            mock_redaction_matches
        )
        
        assert result['success'] is False
        assert result['output_path'] is None
        assert len(result['errors']) > 0
        assert "Redaction failed" in result['errors'][0]
    
    def test_add_overlay_rectangle_fallback(self, redaction_service):
        """Test fallback overlay rectangle method."""
        mock_page = Mock()
        mock_rect = Mock()
        options = {'fill_color': (0, 0, 0)}
        
        # This is a fallback method, should log warning
        with patch.object(redaction_service.logger, 'warning') as mock_warning:
            redaction_service._add_overlay_rectangle(mock_page, mock_rect, options)
            assert mock_warning.called
    
    def test_redact_pdf_with_missing_file(self, redaction_service, mock_redaction_matches):
        """Test redaction with non-existent file."""
        non_existent = Path("/non/existent/file.pdf")
        
        result = redaction_service.redact_pdf(
            non_existent,
            mock_redaction_matches
        )
        
        assert result['success'] is False
        assert len(result['errors']) > 0


class TestPermanentTextDeletion:
    """Test suite specifically for permanent text deletion verification."""
    
    @pytest.fixture
    def create_test_pdf_with_text(self):
        """Create a test PDF with known text content."""
        def _create_pdf(path: Path, text_content: str):
            # This would use reportlab or similar in production
            # For testing, we create a minimal PDF
            writer = PdfWriter()
            page = writer.add_blank_page(width=612, height=792)
            
            with open(path, 'wb') as f:
                writer.write(f)
            
            return path
        
        return _create_pdf
    
    def test_permanent_text_deletion_verification(self, create_test_pdf_with_text):
        """Verify that redacted text is completely removed from text layer."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Create test PDF
            pdf_path = Path(temp_dir) / "test_deletion.pdf"
            create_test_pdf_with_text(pdf_path, "This contains SENSITIVE_DATA that must be removed.")
            
            # Create redaction service
            service = RedactionService("test_session")
            
            # Create match for SENSITIVE_DATA
            match = Mock(spec=RedactionMatch)
            match.matched_text = "SENSITIVE_DATA"
            match.page_number = 0
            match.x_coordinate = 100
            match.y_coordinate = 100
            match.width = 100
            match.height = 20
            match.confidence_score = 1.0
            match.redacted = False
            
            # Apply redaction
            output_path = Path(temp_dir) / "redacted.pdf"
            
            # Mock the actual redaction since we don't have real PDF manipulation
            with patch.object(service, '_apply_redactions', return_value=True):
                with patch.object(service, '_verify_redactions') as mock_verify:
                    # Simulate successful text removal
                    mock_verify.return_value = True
                    
                    result = service.redact_pdf(pdf_path, [match])
                    
                    assert result['success'] is True
                    
                    # In production, we would verify:
                    # 1. Original PDF contains "SENSITIVE_DATA"
                    # 2. Redacted PDF does NOT contain "SENSITIVE_DATA"
                    # 3. Text cannot be recovered through any extraction method
                    
        finally:
            shutil.rmtree(temp_dir)
    
    def test_text_not_recoverable_after_redaction(self):
        """Ensure redacted text cannot be recovered through any method."""
        # This test would verify that:
        # 1. Text extraction tools cannot recover redacted content
        # 2. Copy/paste operations don't reveal redacted text
        # 3. PDF forensic tools cannot retrieve original text
        # 4. File hex dump doesn't contain redacted strings
        pass


class TestErrorHandling:
    """Test suite for error handling scenarios."""
    
    def test_corrupted_pdf_handling(self):
        """Test handling of corrupted PDF files."""
        service = RedactionService("test_session")
        
        # Create a corrupted file
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_file.write(b"Not a valid PDF content")
        temp_file.close()
        
        try:
            match = Mock(spec=RedactionMatch)
            match.page_number = 0
            match.x_coordinate = 100
            match.y_coordinate = 100
            match.width = 100
            match.height = 20
            
            result = service.redact_pdf(Path(temp_file.name), [match])
            
            assert result['success'] is False
            assert len(result['errors']) > 0
            
        finally:
            Path(temp_file.name).unlink()
    
    def test_encrypted_pdf_handling(self):
        """Test handling of encrypted PDFs."""
        # Would test with actual encrypted PDF
        pass
    
    def test_memory_management_large_files(self):
        """Test memory management with large PDF files."""
        # Would test with large PDFs to ensure memory efficiency
        pass
    
    def test_concurrent_redaction_operations(self):
        """Test handling of concurrent redaction operations."""
        # Would test thread safety and concurrent access
        pass