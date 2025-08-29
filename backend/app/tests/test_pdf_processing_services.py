"""
Comprehensive unit tests for PDF processing services.

This module tests all PDF processing services including PDFProcessor,
FuzzyMatcher, OCRService, RedactionService, and extraction services.
"""

import io
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

# Lazy imports for heavy dependencies
PIL = pytest.importorskip("PIL", reason="PIL/Pillow not available")
cv2 = pytest.importorskip("cv2", reason="OpenCV not available")
np = pytest.importorskip("numpy", reason="NumPy not available")
pd = pytest.importorskip("pandas", reason="Pandas not available")

from PIL import Image

from app.services.pdf_processor import PDFProcessor
from app.services.fuzzy_matcher import FuzzyMatcher
from app.services.ocr_service import OCRService
from app.services.redaction_service import RedactionService
from app.services.table_extraction_service import TableExtractionService
from app.services.image_extraction_service import ImageExtractionService
from app.services.text_extraction_service import TextExtractionService
from app.models import Document, ProcessingJob, RedactionMatch


@pytest.mark.unit
class TestPDFProcessor:
    """Test PDFProcessor service functionality."""
    
    def test_pdf_validation_valid_file(self, simple_text_pdf):
        """Test PDF validation with valid PDF file."""
        processor = PDFProcessor()
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(simple_text_pdf)
            temp_path = temp_file.name
        
        try:
            is_valid = processor.validate_pdf(temp_path)
            assert is_valid is True
        finally:
            os.unlink(temp_path)
    
    def test_pdf_validation_corrupted_file(self, corrupted_pdf):
        """Test PDF validation with corrupted PDF file."""
        processor = PDFProcessor()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(corrupted_pdf)
            temp_path = temp_file.name
        
        try:
            is_valid = processor.validate_pdf(temp_path)
            assert is_valid is False
        finally:
            os.unlink(temp_path)
    
    def test_pdf_validation_nonexistent_file(self):
        """Test PDF validation with non-existent file."""
        processor = PDFProcessor()
        
        is_valid = processor.validate_pdf('/nonexistent/file.pdf')
        assert is_valid is False
    
    def test_text_extraction_success(self, simple_text_pdf):
        """Test successful text extraction from PDF."""
        processor = PDFProcessor()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(simple_text_pdf)
            temp_path = temp_file.name
        
        try:
            text = processor.extract_text(temp_path)
            assert isinstance(text, str)
            assert len(text) > 0
            assert 'test' in text.lower() or 'document' in text.lower()
        finally:
            os.unlink(temp_path)
    
    def test_text_extraction_empty_pdf(self):
        """Test text extraction from PDF without text."""
        processor = PDFProcessor()
        
        # Create empty PDF
        from reportlab.pdfgen import canvas
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer)
        c.showPage()  # Empty page
        c.save()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(buffer.getvalue())
            temp_path = temp_file.name
        
        try:
            text = processor.extract_text(temp_path)
            assert isinstance(text, str)
            assert len(text.strip()) == 0
        finally:
            os.unlink(temp_path)
    
    def test_metadata_extraction(self, simple_text_pdf):
        """Test metadata extraction from PDF."""
        processor = PDFProcessor()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(simple_text_pdf)
            temp_path = temp_file.name
        
        try:
            metadata = processor.extract_metadata(temp_path)
            assert isinstance(metadata, dict)
            assert 'pages' in metadata
            assert isinstance(metadata['pages'], int)
            assert metadata['pages'] > 0
        finally:
            os.unlink(temp_path)
    
    def test_page_count_extraction(self, multi_page_pdf):
        """Test page count extraction from multi-page PDF."""
        processor = PDFProcessor()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(multi_page_pdf)
            temp_path = temp_file.name
        
        try:
            page_count = processor.get_page_count(temp_path)
            assert isinstance(page_count, int)
            assert page_count >= 1
        finally:
            os.unlink(temp_path)
    
    def test_page_extraction_as_image(self, simple_text_pdf):
        """Test extracting PDF pages as images."""
        processor = PDFProcessor()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(simple_text_pdf)
            temp_path = temp_file.name
        
        try:
            image = processor.extract_page_as_image(temp_path, page_number=0)
            assert image is not None
            # Image should be PIL Image or numpy array
            assert hasattr(image, 'size') or hasattr(image, 'shape')
        finally:
            os.unlink(temp_path)
    
    def test_password_protected_pdf_handling(self, password_protected_pdf):
        """Test handling of password-protected PDFs."""
        processor = PDFProcessor()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(password_protected_pdf)
            temp_path = temp_file.name
        
        try:
            # Should fail without password
            with pytest.raises(Exception):
                processor.extract_text(temp_path)
            
            # Should succeed with correct password
            text = processor.extract_text(temp_path, password="testpass123")
            assert isinstance(text, str)
        finally:
            os.unlink(temp_path)


@pytest.mark.unit
class TestFuzzyMatcher:
    """Test FuzzyMatcher service functionality."""
    
    def test_fuzzy_matching_exact_match(self):
        """Test fuzzy matching with exact text matches."""
        matcher = FuzzyMatcher()
        
        text = "Contact John Doe at john.doe@example.com for more information."
        search_terms = ["john.doe@example.com"]
        confidence_threshold = 80
        
        matches = matcher.find_matches(text, search_terms, confidence_threshold)
        
        assert len(matches) == 1
        assert matches[0]['text'] == 'john.doe@example.com'
        assert matches[0]['confidence'] == 100
        assert 'start' in matches[0]
        assert 'end' in matches[0]
    
    def test_fuzzy_matching_partial_match(self):
        """Test fuzzy matching with partial/fuzzy matches."""
        matcher = FuzzyMatcher()
        
        text = "Contact Jon Doe at jon.doe@email.com for information."
        search_terms = ["john.doe@example.com"]
        confidence_threshold = 60
        
        matches = matcher.find_matches(text, search_terms, confidence_threshold)
        
        # Should find fuzzy matches
        assert len(matches) >= 1
        assert matches[0]['confidence'] >= confidence_threshold
        assert matches[0]['confidence'] < 100
    
    def test_fuzzy_matching_confidence_threshold(self):
        """Test fuzzy matching respects confidence thresholds."""
        matcher = FuzzyMatcher()
        
        text = "Contact information: call 555-1234"
        search_terms = ["john.doe@example.com"]
        
        # High threshold should return no matches
        high_threshold_matches = matcher.find_matches(text, search_terms, 95)
        assert len(high_threshold_matches) == 0
        
        # Low threshold might return false positives
        low_threshold_matches = matcher.find_matches(text, search_terms, 30)
        # This is acceptable behavior for low thresholds
    
    def test_multiple_search_terms(self):
        """Test fuzzy matching with multiple search terms."""
        matcher = FuzzyMatcher()
        
        text = """
        Contact Details:
        Email: alice@company.com
        Phone: 555-123-4567
        SSN: 123-45-6789
        """
        
        search_terms = ["email", "phone", "ssn", "social security"]
        confidence_threshold = 70
        
        matches = matcher.find_matches(text, search_terms, confidence_threshold)
        
        # Should find multiple matches
        assert len(matches) >= 2
        # Verify different terms were matched
        matched_texts = [match['text'].lower() for match in matches]
        assert any('email' in text for text in matched_texts)
    
    def test_matching_algorithms(self):
        """Test different fuzzy matching algorithms."""
        matcher = FuzzyMatcher()
        
        text = "John Smith contacted us yesterday"
        search_term = "Jon Smith"
        
        # Test different algorithms
        algorithms = ['token_sort_ratio', 'token_set_ratio', 'partial_ratio', 'ratio']
        
        for algorithm in algorithms:
            score = matcher.calculate_similarity(text, search_term, algorithm=algorithm)
            assert isinstance(score, (int, float))
            assert 0 <= score <= 100
    
    def test_text_preprocessing(self):
        """Test text preprocessing and normalization."""
        matcher = FuzzyMatcher()
        
        # Test with various whitespace and formatting
        text1 = "  John   Doe  \n\t john.doe@example.com  "
        text2 = "John Doe john.doe@example.com"
        
        processed1 = matcher.preprocess_text(text1)
        processed2 = matcher.preprocess_text(text2)
        
        # Should normalize whitespace
        assert processed1 == processed2
        assert "  " not in processed1
        assert processed1.strip() == processed1
    
    def test_performance_with_large_text(self):
        """Test fuzzy matching performance with large documents."""
        matcher = FuzzyMatcher()
        
        # Create large text document
        large_text = "Lorem ipsum dolor sit amet. " * 10000
        large_text += "Contact john.doe@example.com for details."
        
        search_terms = ["john.doe@example.com"]
        confidence_threshold = 80
        
        import time
        start_time = time.time()
        matches = matcher.find_matches(large_text, search_terms, confidence_threshold)
        end_time = time.time()
        
        # Should complete within reasonable time (< 5 seconds)
        assert end_time - start_time < 5.0
        assert len(matches) >= 1


@pytest.mark.unit
class TestOCRService:
    """Test OCRService functionality."""
    
    @patch('pytesseract.image_to_string')
    @patch('cv2.imread')
    def test_ocr_processing_success(self, mock_imread, mock_tesseract):
        """Test successful OCR processing."""
        # Mock image and OCR result
        mock_image = np.ones((100, 100, 3), dtype=np.uint8) * 255  # White image
        mock_imread.return_value = mock_image
        mock_tesseract.return_value = "Sample OCR text result"
        
        ocr_service = OCRService()
        result = ocr_service.process_image("dummy_path.png")
        
        assert result == "Sample OCR text result"
        mock_imread.assert_called_once()
        mock_tesseract.assert_called_once()
    
    @patch('cv2.imread')
    def test_image_preprocessing(self, mock_imread):
        """Test image preprocessing for OCR."""
        # Create test image
        test_image = np.ones((100, 100, 3), dtype=np.uint8) * 128  # Gray image
        mock_imread.return_value = test_image
        
        ocr_service = OCRService()
        preprocessed = ocr_service.preprocess_image("dummy_path.png")
        
        assert preprocessed is not None
        # Should be grayscale
        assert len(preprocessed.shape) == 2 or preprocessed.shape[2] == 1
        mock_imread.assert_called_once()
    
    @patch('pytesseract.image_to_data')
    def test_ocr_confidence_filtering(self, mock_image_to_data):
        """Test OCR result filtering by confidence."""
        # Mock OCR data with different confidence levels
        mock_data = {
            'text': ['', 'High', 'confidence', 'Low', 'confidence'],
            'conf': [-1, 95, 90, 40, 35]
        }
        mock_image_to_data.return_value = mock_data
        
        ocr_service = OCRService(confidence_threshold=80)
        
        # Mock image
        with patch('cv2.imread') as mock_imread:
            mock_imread.return_value = np.ones((100, 100, 3), dtype=np.uint8)
            filtered_text = ocr_service.extract_text_with_confidence("dummy_path.png")
        
        # Should only include high confidence text
        assert 'High confidence' in filtered_text
        assert 'Low confidence' not in filtered_text
    
    def test_ocr_caching(self):
        """Test OCR result caching mechanism."""
        ocr_service = OCRService()
        
        with patch('pytesseract.image_to_string') as mock_tesseract, \
             patch('cv2.imread') as mock_imread:
            
            mock_imread.return_value = np.ones((100, 100, 3), dtype=np.uint8)
            mock_tesseract.return_value = "Cached OCR result"
            
            # First call
            result1 = ocr_service.process_image("test_image.png")
            
            # Second call should use cache
            result2 = ocr_service.process_image("test_image.png")
            
            assert result1 == result2
            # Should only call tesseract once due to caching
            assert mock_tesseract.call_count == 1
    
    @patch('cv2.imread', return_value=None)
    def test_invalid_image_handling(self, mock_imread):
        """Test handling of invalid or corrupted images."""
        ocr_service = OCRService()
        
        with pytest.raises(Exception):
            ocr_service.process_image("invalid_image.png")
    
    def test_different_image_formats(self):
        """Test OCR with different image formats."""
        ocr_service = OCRService()
        
        formats = ['png', 'jpg', 'jpeg', 'tiff', 'bmp']
        
        for fmt in formats:
            with patch('cv2.imread') as mock_imread, \
                 patch('pytesseract.image_to_string') as mock_tesseract:
                
                mock_imread.return_value = np.ones((100, 100, 3), dtype=np.uint8)
                mock_tesseract.return_value = f"Text from {fmt} image"
                
                result = ocr_service.process_image(f"test_image.{fmt}")
                assert result == f"Text from {fmt} image"


@pytest.mark.unit
class TestRedactionService:
    """Test RedactionService functionality."""
    
    def test_coordinate_validation(self):
        """Test redaction coordinate validation."""
        redaction_service = RedactionService()
        
        # Valid coordinates
        valid_coords = {'x1': 10, 'y1': 20, 'x2': 100, 'y2': 40}
        assert redaction_service.validate_coordinates(valid_coords) is True
        
        # Invalid coordinates (x1 > x2)
        invalid_coords = {'x1': 100, 'y1': 20, 'x2': 10, 'y2': 40}
        assert redaction_service.validate_coordinates(invalid_coords) is False
        
        # Invalid coordinates (y1 > y2)
        invalid_coords2 = {'x1': 10, 'y1': 40, 'x2': 100, 'y2': 20}
        assert redaction_service.validate_coordinates(invalid_coords2) is False
    
    def test_coordinate_conversion(self):
        """Test coordinate system conversion."""
        redaction_service = RedactionService()
        
        # Test PDF coordinate to screen coordinate conversion
        pdf_coords = {'x1': 72, 'y1': 720, 'x2': 144, 'y2': 700}  # PDF coordinates (points)
        page_height = 792  # Standard letter size height
        
        screen_coords = redaction_service.pdf_to_screen_coordinates(pdf_coords, page_height)
        
        assert isinstance(screen_coords, dict)
        assert 'x1' in screen_coords and 'y1' in screen_coords
        assert 'x2' in screen_coords and 'y2' in screen_coords
        # Y coordinates should be flipped
        assert screen_coords['y1'] < screen_coords['y2']
    
    @patch('PyPDF2.PdfWriter')
    @patch('PyPDF2.PdfReader')
    def test_permanent_text_deletion(self, mock_reader, mock_writer):
        """Test permanent text deletion using PyPDF2."""
        # Mock PDF objects
        mock_page = Mock()
        mock_reader.return_value.pages = [mock_page]
        mock_writer_instance = Mock()
        mock_writer.return_value = mock_writer_instance
        
        redaction_service = RedactionService()
        
        redaction_coords = [
            {'page': 0, 'x1': 100, 'y1': 200, 'x2': 300, 'y2': 220}
        ]
        
        with tempfile.NamedTemporaryFile(suffix='.pdf') as input_file, \
             tempfile.NamedTemporaryFile(suffix='.pdf') as output_file:
            
            result = redaction_service.apply_redactions(
                input_file.name,
                output_file.name,
                redaction_coords
            )
            
            assert result is True
            mock_writer_instance.add_page.assert_called()
    
    def test_redaction_statistics(self):
        """Test redaction statistics and reporting."""
        redaction_service = RedactionService()
        
        redactions = [
            {'page': 0, 'text': 'john@example.com', 'x1': 100, 'y1': 200, 'x2': 200, 'y2': 220},
            {'page': 0, 'text': '555-1234', 'x1': 100, 'y1': 250, 'x2': 150, 'y2': 270},
            {'page': 1, 'text': 'confidential', 'x1': 50, 'y1': 100, 'x2': 120, 'y2': 120}
        ]
        
        stats = redaction_service.calculate_redaction_statistics(redactions)
        
        assert isinstance(stats, dict)
        assert stats['total_redactions'] == 3
        assert stats['pages_affected'] == 2
        assert 'redaction_types' in stats
    
    def test_bounding_box_calculation(self):
        """Test bounding box calculation for text matches."""
        redaction_service = RedactionService()
        
        text = "Contact john.doe@example.com for details"
        match_start = text.find("john.doe@example.com")
        match_end = match_start + len("john.doe@example.com")
        
        # Mock font metrics
        with patch.object(redaction_service, 'get_font_metrics') as mock_metrics:
            mock_metrics.return_value = {'char_width': 6, 'line_height': 12}
            
            bbox = redaction_service.calculate_text_bounding_box(
                text, match_start, match_end, x=100, y=200
            )
            
            assert isinstance(bbox, dict)
            assert 'x1' in bbox and 'y1' in bbox
            assert 'x2' in bbox and 'y2' in bbox
            assert bbox['x2'] > bbox['x1']
            assert bbox['y2'] > bbox['y1']
    
    def test_redaction_validation(self):
        """Test redaction integrity validation."""
        redaction_service = RedactionService()
        
        # Mock PDF content before and after redaction
        original_text = "Contact john.doe@example.com for details"
        redacted_text = "Contact [REDACTED] for details"
        
        is_properly_redacted = redaction_service.validate_redaction_integrity(
            original_text, redacted_text, ["john.doe@example.com"]
        )
        
        assert is_properly_redacted is True
        
        # Test incomplete redaction
        incomplete_redacted = "Contact john@example.com for details"
        is_incomplete = redaction_service.validate_redaction_integrity(
            original_text, incomplete_redacted, ["john.doe@example.com"]
        )
        
        assert is_incomplete is False


@pytest.mark.unit
class TestTableExtractionService:
    """Test TableExtractionService functionality."""
    
    @patch('camelot.read_pdf')
    def test_camelot_table_detection(self, mock_camelot):
        """Test table detection using camelot-py."""
        # Mock camelot response
        mock_table = Mock()
        mock_table.df = Mock()
        mock_table.df.to_csv.return_value = "Name,Age,City\nJohn,30,NYC\nJane,25,LA"
        mock_camelot.return_value = [mock_table]
        
        table_service = TableExtractionService()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
            tables = table_service.extract_tables_camelot(temp_file.name)
            
            assert len(tables) == 1
            mock_camelot.assert_called_once()
    
    @patch('tabula.read_pdf')
    def test_tabula_table_detection(self, mock_tabula):
        """Test table detection using tabula-py."""
        # Mock tabula response
        mock_df = pd.DataFrame({
            'Name': ['John', 'Jane'],
            'Age': [30, 25],
            'City': ['NYC', 'LA']
        })
        mock_tabula.return_value = [mock_df]
        
        table_service = TableExtractionService()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
            tables = table_service.extract_tables_tabula(temp_file.name)
            
            assert len(tables) == 1
            mock_tabula.assert_called_once()
    
    def test_csv_export_formatting(self):
        """Test CSV export with different formatting options."""
        table_service = TableExtractionService()
        
        # Mock table data
        df = pd.DataFrame({
            'Name': ['John Doe', 'Jane Smith'],
            'Email': ['john@example.com', 'jane@example.com'],
            'Age': [30, 25]
        })
        
        # Test different delimiters
        csv_comma = table_service.format_table_as_csv(df, delimiter=',')
        csv_semicolon = table_service.format_table_as_csv(df, delimiter=';')
        
        assert ',' in csv_comma
        assert ';' in csv_semicolon
        assert csv_comma != csv_semicolon
    
    def test_table_validation_and_filtering(self):
        """Test table validation and quality filtering."""
        table_service = TableExtractionService()
        
        # Valid table
        valid_table = pd.DataFrame({
            'Column1': ['A', 'B', 'C'],
            'Column2': [1, 2, 3],
            'Column3': ['X', 'Y', 'Z']
        })
        
        # Invalid table (too few rows/columns)
        invalid_table = pd.DataFrame({'Col1': ['A']})
        
        assert table_service.is_valid_table(valid_table) is True
        assert table_service.is_valid_table(invalid_table) is False
    
    def test_fallback_detection_methods(self):
        """Test fallback between different table detection methods."""
        table_service = TableExtractionService()
        
        with patch('camelot.read_pdf') as mock_camelot, \
             patch('tabula.read_pdf') as mock_tabula:
            
            # Camelot fails, should fallback to tabula
            mock_camelot.side_effect = Exception("Camelot failed")
            
            mock_df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
            mock_tabula.return_value = [mock_df]
            
            with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
                tables = table_service.extract_tables_with_fallback(temp_file.name)
                
                assert len(tables) == 1
                mock_camelot.assert_called_once()
                mock_tabula.assert_called_once()
    
    def test_complex_table_layouts(self):
        """Test handling of complex table layouts."""
        table_service = TableExtractionService()
        
        # Mock complex table with merged cells, headers, etc.
        with patch('camelot.read_pdf') as mock_camelot:
            mock_table = Mock()
            # Complex table structure
            complex_data = pd.DataFrame({
                'Quarter': ['Q1', 'Q1', 'Q2', 'Q2'],
                'Month': ['Jan', 'Feb', 'Apr', 'May'],
                'Sales': [1000, 1200, 1500, 1300]
            })
            mock_table.df = complex_data
            mock_camelot.return_value = [mock_table]
            
            with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
                tables = table_service.extract_tables_camelot(temp_file.name)
                
                assert len(tables) == 1
                # Should handle complex structure
                assert len(tables[0].columns) == 3


@pytest.mark.unit
class TestImageExtractionService:
    """Test ImageExtractionService functionality."""
    
    @patch('PyPDF2.PdfReader')
    def test_image_extraction_success(self, mock_reader):
        """Test successful image extraction from PDF."""
        # Mock PDF with embedded images
        mock_page = Mock()
        mock_page.images = {
            'img1': Mock(data=b'fake_image_data_png', name='image1.png'),
            'img2': Mock(data=b'fake_image_data_jpg', name='image2.jpg')
        }
        mock_reader.return_value.pages = [mock_page]
        
        image_service = ImageExtractionService()
        
        with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
            images = image_service.extract_images(temp_file.name)
            
            assert len(images) == 2
            assert images[0]['name'] == 'image1.png'
            assert images[1]['name'] == 'image2.jpg'
    
    @patch('PIL.Image.open')
    def test_image_format_conversion(self, mock_image_open):
        """Test image format conversion and optimization."""
        # Mock PIL Image
        mock_image = Mock()
        mock_image.format = 'JPEG'
        mock_image.size = (800, 600)
        mock_image_open.return_value = mock_image
        
        image_service = ImageExtractionService()
        
        # Test conversion to PNG
        with tempfile.NamedTemporaryFile(suffix='.jpg') as input_file, \
             tempfile.NamedTemporaryFile(suffix='.png') as output_file:
            
            result = image_service.convert_image_format(
                input_file.name, output_file.name, 'PNG', quality=85
            )
            
            assert result is True
            mock_image.save.assert_called()
    
    def test_image_size_validation(self):
        """Test image size validation and filtering."""
        image_service = ImageExtractionService()
        
        # Valid image size
        valid_image_info = {'width': 800, 'height': 600, 'size': 1024000}  # 1MB
        assert image_service.is_valid_image_size(valid_image_info, min_width=100, max_size=5000000) is True
        
        # Too small image
        small_image_info = {'width': 50, 'height': 30, 'size': 1000}
        assert image_service.is_valid_image_size(small_image_info, min_width=100, max_size=5000000) is False
        
        # Too large image
        large_image_info = {'width': 2000, 'height': 1500, 'size': 10000000}  # 10MB
        assert image_service.is_valid_image_size(large_image_info, min_width=100, max_size=5000000) is False
    
    @patch('PIL.Image.open')
    def test_image_quality_optimization(self, mock_image_open):
        """Test image quality optimization and compression."""
        mock_image = Mock()
        mock_image.format = 'JPEG'
        mock_image.size = (1200, 900)
        mock_image_open.return_value = mock_image
        
        image_service = ImageExtractionService()
        
        # Test different quality settings
        qualities = [90, 75, 60]
        
        for quality in qualities:
            with tempfile.NamedTemporaryFile(suffix='.jpg') as input_file, \
                 tempfile.NamedTemporaryFile(suffix='.jpg') as output_file:
                
                result = image_service.optimize_image_quality(
                    input_file.name, output_file.name, quality=quality
                )
                
                assert result is True
    
    def test_image_metadata_extraction(self):
        """Test extraction of image metadata."""
        image_service = ImageExtractionService()
        
        with patch('PIL.Image.open') as mock_image_open:
            mock_image = Mock()
            mock_image.format = 'JPEG'
            mock_image.size = (1024, 768)
            mock_image.mode = 'RGB'
            mock_image._getexif.return_value = {'DateTime': '2024:01:01 12:00:00'}
            mock_image_open.return_value = mock_image
            
            with tempfile.NamedTemporaryFile(suffix='.jpg') as temp_file:
                metadata = image_service.extract_image_metadata(temp_file.name)
                
                assert isinstance(metadata, dict)
                assert 'format' in metadata
                assert 'size' in metadata
                assert 'mode' in metadata
    
    def test_corrupted_image_handling(self):
        """Test handling of corrupted or invalid images."""
        image_service = ImageExtractionService()
        
        with patch('PIL.Image.open') as mock_image_open:
            mock_image_open.side_effect = Exception("Corrupted image")
            
            with tempfile.NamedTemporaryFile(suffix='.jpg') as temp_file:
                # Should handle corrupted image gracefully
                with pytest.raises(Exception):
                    image_service.extract_image_metadata(temp_file.name)


@pytest.mark.unit
class TestTextExtractionService:
    """Test TextExtractionService functionality."""
    
    def test_unified_text_extraction(self):
        """Test unified text extraction combining multiple sources."""
        text_service = TextExtractionService()
        
        with patch.object(text_service, 'extract_text_layer') as mock_text_layer, \
             patch.object(text_service, 'extract_text_ocr') as mock_ocr:
            
            mock_text_layer.return_value = "Text from PDF text layer"
            mock_ocr.return_value = "Text from OCR processing"
            
            with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
                combined_text = text_service.extract_unified_text(temp_file.name)
                
                assert isinstance(combined_text, str)
                assert len(combined_text) > 0
    
    def test_text_quality_assessment(self):
        """Test text quality assessment and source selection."""
        text_service = TextExtractionService()
        
        # High quality text (clean, readable)
        high_quality_text = "This is a clear, well-formatted document with proper spacing and punctuation."
        
        # Low quality text (garbled, OCR artifacts)
        low_quality_text = "Th1s 1s @ g@rbl3d d0cum3nt w1th 0CR @rt1f@cts."
        
        high_score = text_service.assess_text_quality(high_quality_text)
        low_score = text_service.assess_text_quality(low_quality_text)
        
        assert high_score > low_score
        assert isinstance(high_score, (int, float))
        assert isinstance(low_score, (int, float))
    
    def test_structured_text_extraction(self):
        """Test structured text extraction with formatting."""
        text_service = TextExtractionService()
        
        sample_text = """
        DOCUMENT TITLE
        
        Section 1: Introduction
        This is the introduction section.
        
        Section 2: Details
        - Item 1
        - Item 2
        - Item 3
        
        Conclusion:
        This is the conclusion.
        """
        
        structured = text_service.extract_structured_text(sample_text)
        
        assert isinstance(structured, dict)
        assert 'title' in structured
        assert 'sections' in structured
        assert len(structured['sections']) > 0
    
    def test_text_statistics_analysis(self):
        """Test text statistics and analysis."""
        text_service = TextExtractionService()
        
        sample_text = """
        This is a sample document for testing text analysis.
        It contains multiple sentences and various words.
        The analysis should provide comprehensive statistics.
        """
        
        stats = text_service.analyze_text_statistics(sample_text)
        
        assert isinstance(stats, dict)
        assert 'word_count' in stats
        assert 'sentence_count' in stats
        assert 'character_count' in stats
        assert 'reading_level' in stats
        assert stats['word_count'] > 0
        assert stats['sentence_count'] > 0
    
    def test_service_integration(self):
        """Test integration with other text processing services."""
        text_service = TextExtractionService()
        
        with patch('app.services.pdf_processor.PDFProcessor') as mock_pdf, \
             patch('app.services.ocr_service.OCRService') as mock_ocr:
            
            mock_pdf.return_value.extract_text.return_value = "PDF extracted text"
            mock_ocr.return_value.process_image.return_value = "OCR extracted text"
            
            with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
                result = text_service.extract_with_multiple_methods(temp_file.name)
                
                assert isinstance(result, dict)
                assert 'pdf_text' in result
                assert 'ocr_text' in result
                assert 'combined_text' in result
    
    def test_language_detection(self):
        """Test language detection in extracted text."""
        text_service = TextExtractionService()
        
        english_text = "This is an English document with standard vocabulary."
        spanish_text = "Este es un documento en español con vocabulario estándar."
        
        with patch('langdetect.detect') as mock_detect:
            mock_detect.side_effect = ['en', 'es']
            
            en_lang = text_service.detect_language(english_text)
            es_lang = text_service.detect_language(spanish_text)
            
            assert en_lang == 'en'
            assert es_lang == 'es'
    
    def test_text_encoding_handling(self):
        """Test handling of different text encodings."""
        text_service = TextExtractionService()
        
        # Test with different encoded text
        utf8_text = "Standard UTF-8 text with special characters: àáâãäå"
        latin1_text = "Latin-1 encoded text"
        
        # Should handle various encodings gracefully
        processed_utf8 = text_service.normalize_text_encoding(utf8_text)
        processed_latin1 = text_service.normalize_text_encoding(latin1_text)
        
        assert isinstance(processed_utf8, str)
        assert isinstance(processed_latin1, str)
        # Should preserve special characters
        assert 'à' in processed_utf8