"""
Comprehensive unit tests for the ImageExtractionService.

This test suite covers embedded image extraction, page-to-image conversion,
format conversion, size validation, metadata extraction, error handling, and integration scenarios.
"""

import pytest
import tempfile
import io
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from PIL import Image

from app.services.image_extraction_service import ImageExtractionService
from app.utils.temp_file_manager import TempFileManager


class TestImageExtractionService:
    """Test cases for ImageExtractionService functionality."""
    
    @pytest.fixture
    def mock_session_id(self):
        """Generate a mock session ID for testing."""
        return "test_session_67890"
    
    @pytest.fixture
    def image_service(self, mock_session_id):
        """Create ImageExtractionService instance for testing."""
        return ImageExtractionService(mock_session_id)
    
    @pytest.fixture
    def sample_pdf_path(self):
        """Create a temporary PDF file path for testing."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            pdf_path = Path(f.name)
        yield pdf_path
        if pdf_path.exists():
            pdf_path.unlink()
    
    @pytest.fixture
    def sample_image_data(self):
        """Create sample image data for testing."""
        # Create a simple 100x100 RGB image
        img = Image.new('RGB', (100, 100), color='red')
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        return img_buffer.getvalue()
    
    @pytest.fixture
    def sample_jpeg_data(self):
        """Create sample JPEG image data for testing."""
        img = Image.new('RGB', (200, 150), color='blue')
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG')
        return img_buffer.getvalue()
    
    def test_image_service_initialization(self, mock_session_id):
        """Test ImageExtractionService initialization."""
        service = ImageExtractionService(mock_session_id)
        
        assert service.session_id == mock_session_id
        assert isinstance(service.temp_file_manager, TempFileManager)
        assert service.MAX_IMAGE_SIZE_MB == 10
        assert 'PNG' in service.SUPPORTED_FORMATS
        assert 'JPEG' in service.SUPPORTED_FORMATS
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_success(self, mock_fitz, image_service, sample_pdf_path, sample_image_data):
        """Test successful image extraction from PDF."""
        # Mock PyMuPDF document
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 3  # 3 pages
        mock_doc.close.return_value = None
        
        # Mock page with embedded images
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        mock_page.get_images.return_value = [(1, 2, 3, 4, 5, 'image1', 'DCTDecode', 100, 100)]
        
        # Mock image extraction
        mock_doc.extract_image.return_value = {
            'image': sample_image_data,
            'ext': 'png'
        }
        
        with patch.object(image_service.temp_file_manager, 'downloads_dir') as mock_downloads_dir:
            mock_file_path = Path('/tmp/image_page_1_1.png')
            mock_downloads_dir.__truediv__.return_value = mock_file_path
            
            with patch('builtins.open', mock_builtins_open):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = len(sample_image_data)
                    
                    result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is True
        assert len(result['images']) == 3  # One image per page
        assert result['output_format'] == 'PNG'
        assert result['statistics']['embedded_images_extracted'] == 3
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_with_page_range(self, mock_fitz, image_service, sample_pdf_path, sample_image_data):
        """Test image extraction with specific page range."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 10  # 10 pages
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        mock_page.get_images.return_value = [(1, 0, 0, 0, 0, 'img', 'DCT', 50, 50)]
        mock_doc.extract_image.return_value = {'image': sample_image_data, 'ext': 'png'}
        
        with patch.object(image_service.temp_file_manager, 'downloads_dir'):
            with patch('builtins.open', mock_builtins_open):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 1024
                    
                    result = image_service.extract_images(
                        sample_pdf_path,
                        page_range=(3, 5)  # Pages 3-5
                    )
        
        assert result['success'] is True
        assert result['total_pages_processed'] == 3  # Pages 3, 4, 5
    
    def test_extract_images_unsupported_format(self, image_service, sample_pdf_path):
        """Test handling of unsupported output format."""
        result = image_service.extract_images(
            sample_pdf_path,
            output_format='BMP'  # Not in SUPPORTED_FORMATS
        )
        
        assert result['success'] is False
        assert 'Unsupported output format' in result['error']
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_embedded_images_format_conversion(self, mock_fitz, image_service, sample_pdf_path, sample_jpeg_data):
        """Test format conversion during image extraction."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 1
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        mock_page.get_images.return_value = [(1, 0, 0, 0, 0, 'img', 'DCT', 100, 100)]
        
        # Mock JPEG image that needs conversion to PNG
        mock_doc.extract_image.return_value = {'image': sample_jpeg_data, 'ext': 'jpg'}
        
        with patch.object(image_service, '_convert_image_format') as mock_convert:
            mock_convert.return_value = sample_jpeg_data  # Mock converted data
            
            with patch.object(image_service.temp_file_manager, 'downloads_dir'):
                with patch('builtins.open', mock_builtins_open):
                    with patch('pathlib.Path.stat') as mock_stat:
                        mock_stat.return_value.st_size = 2048
                        
                        result = image_service.extract_images(
                            sample_pdf_path,
                            output_format='PNG'
                        )
        
        assert result['success'] is True
        mock_convert.assert_called_once()
        assert result['statistics']['format_conversions'] == 1
    
    def test_validate_image_size_within_limit(self, image_service, sample_image_data):
        """Test image size validation for images within size limit."""
        is_valid = image_service._validate_image_size(sample_image_data)
        
        assert is_valid is True
    
    def test_validate_image_size_exceeds_limit(self, image_service):
        """Test image size validation for oversized images."""
        # Create data larger than 10MB limit
        oversized_data = b'x' * (11 * 1024 * 1024)  # 11MB
        
        is_valid = image_service._validate_image_size(oversized_data)
        
        assert is_valid is False
    
    def test_convert_image_format_jpeg_to_png(self, image_service, sample_jpeg_data):
        """Test image format conversion from JPEG to PNG."""
        converted_data = image_service._convert_image_format(
            sample_jpeg_data, 'JPEG', 'PNG', 95
        )
        
        assert converted_data is not None
        assert len(converted_data) > 0
        
        # Verify converted image can be opened as PNG
        converted_img = Image.open(io.BytesIO(converted_data))
        assert converted_img.format == 'PNG'
    
    def test_convert_image_format_png_to_jpeg(self, image_service, sample_image_data):
        """Test image format conversion from PNG to JPEG."""
        converted_data = image_service._convert_image_format(
            sample_image_data, 'PNG', 'JPEG', 85
        )
        
        assert converted_data is not None
        
        # Verify converted image can be opened as JPEG
        converted_img = Image.open(io.BytesIO(converted_data))
        assert converted_img.format == 'JPEG'
    
    def test_convert_image_format_with_quality(self, image_service, sample_jpeg_data):
        """Test image format conversion with specific quality settings."""
        high_quality = image_service._convert_image_format(
            sample_jpeg_data, 'JPEG', 'JPEG', 95
        )
        
        low_quality = image_service._convert_image_format(
            sample_jpeg_data, 'JPEG', 'JPEG', 20
        )
        
        # Low quality should result in smaller file size
        assert len(low_quality) < len(high_quality)
    
    def test_convert_image_format_invalid_data(self, image_service):
        """Test format conversion with invalid image data."""
        invalid_data = b'not an image'
        
        result = image_service._convert_image_format(
            invalid_data, 'PNG', 'JPEG', 95
        )
        
        assert result is None
    
    def test_handle_color_space_conversion_cmyk(self, image_service):
        """Test CMYK color space conversion."""
        # Create a mock CMYK image
        cmyk_img = Image.new('CMYK', (100, 100), color=(100, 0, 100, 0))
        
        converted_img = image_service._handle_color_space_conversion(cmyk_img)
        
        assert converted_img.mode == 'RGB'
    
    def test_handle_color_space_conversion_lab(self, image_service):
        """Test LAB color space conversion."""
        # Create a mock LAB image
        lab_img = Image.new('LAB', (100, 100), color=(50, 0, 0))
        
        converted_img = image_service._handle_color_space_conversion(lab_img)
        
        assert converted_img.mode == 'RGB'
    
    def test_handle_color_space_conversion_1bit(self, image_service):
        """Test 1-bit color space conversion."""
        # Create a mock 1-bit image
        bit_img = Image.new('1', (100, 100), color=1)
        
        converted_img = image_service._handle_color_space_conversion(bit_img)
        
        assert converted_img.mode == 'L'  # Grayscale
    
    def test_extract_image_metadata_comprehensive(self, image_service, sample_image_data):
        """Test comprehensive image metadata extraction."""
        metadata = image_service._extract_image_metadata(sample_image_data, 2, 1)
        
        assert metadata['page'] == 2
        assert metadata['index'] == 1
        assert 'file_size_bytes' in metadata
        assert 'file_size_mb' in metadata
        assert 'width' in metadata
        assert 'height' in metadata
        assert 'mode' in metadata
        assert 'format' in metadata
        assert 'dpi_x' in metadata
        assert 'dpi_y' in metadata
    
    def test_extract_image_metadata_with_transparency(self, image_service):
        """Test metadata extraction for images with transparency."""
        # Create PNG with transparency
        rgba_img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        img_buffer = io.BytesIO()
        rgba_img.save(img_buffer, format='PNG')
        rgba_data = img_buffer.getvalue()
        
        metadata = image_service._extract_image_metadata(rgba_data, 1, 0)
        
        assert metadata['has_transparency'] is True
        assert metadata['mode'] == 'RGBA'
    
    def test_optimize_image_quality_jpeg(self, image_service, sample_jpeg_data):
        """Test image quality optimization for JPEG."""
        optimized_data = image_service._optimize_image_quality(
            sample_jpeg_data, 'JPEG', 75
        )
        
        # Should return optimized data if significant size reduction
        if optimized_data:
            assert len(optimized_data) <= len(sample_jpeg_data)
    
    def test_optimize_image_quality_png(self, image_service, sample_image_data):
        """Test image quality optimization for PNG (should return None)."""
        optimized_data = image_service._optimize_image_quality(
            sample_image_data, 'PNG', 95
        )
        
        # PNG doesn't support quality optimization in this implementation
        assert optimized_data is None
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_page_images_as_renders(self, mock_fitz, image_service, sample_pdf_path):
        """Test extraction of page renders as images."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 2
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        
        # Mock pixmap
        mock_pixmap = Mock()
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_pixmap.tobytes.return_value = b'mock_image_data'
        
        # Mock page with no embedded images
        mock_page.get_images.return_value = []
        
        with patch.object(image_service.temp_file_manager, 'downloads_dir'):
            with patch('builtins.open', mock_builtins_open):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 5000
                    
                    result = image_service.extract_images(
                        sample_pdf_path,
                        include_page_renders=True,
                        dpi=150
                    )
        
        assert result['success'] is True
        assert result['statistics']['page_renders_created'] == 2
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_no_images_found(self, mock_fitz, image_service, sample_pdf_path):
        """Test handling when no images are found in PDF."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 3
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        mock_page.get_images.return_value = []  # No images
        
        result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is True
        assert len(result['images']) == 0
        assert result['statistics']['embedded_images_found'] == 0
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_corrupted_image_data(self, mock_fitz, image_service, sample_pdf_path):
        """Test handling of corrupted image data in PDF."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 1
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        mock_page.get_images.return_value = [(1, 0, 0, 0, 0, 'img', 'DCT', 100, 100)]
        
        # Mock corrupted image extraction
        mock_doc.extract_image.return_value = {'image': b'corrupted_data', 'ext': 'jpg'}
        
        with patch.object(image_service.temp_file_manager, 'downloads_dir'):
            result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is True
        assert result['statistics']['embedded_images_extracted'] == 0  # Should skip corrupted images
    
    def test_extract_images_file_not_found(self, image_service):
        """Test error handling when PDF file doesn't exist."""
        non_existent_file = Path('/non/existent/file.pdf')
        
        result = image_service.extract_images(non_existent_file)
        
        assert result['success'] is False
        assert 'error' in result
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_pdf_processing_error(self, mock_fitz, image_service, sample_pdf_path):
        """Test handling of PDF processing errors."""
        mock_fitz.open.side_effect = Exception("PDF processing error")
        
        result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is False
        assert 'PDF processing error' in result['error']
    
    def test_generate_image_thumbnails_success(self, image_service, sample_image_data):
        """Test successful thumbnail generation."""
        thumbnail_data = image_service._generate_image_thumbnails(
            sample_image_data, (50, 50)
        )
        
        assert thumbnail_data is not None
        assert len(thumbnail_data) < len(sample_image_data)  # Thumbnail should be smaller
        
        # Verify thumbnail is valid JPEG
        thumbnail_img = Image.open(io.BytesIO(thumbnail_data))
        assert thumbnail_img.format == 'JPEG'
        assert thumbnail_img.size[0] <= 50
        assert thumbnail_img.size[1] <= 50
    
    def test_generate_image_thumbnails_rgba(self, image_service):
        """Test thumbnail generation for RGBA images."""
        # Create RGBA image
        rgba_img = Image.new('RGBA', (200, 200), color=(255, 0, 0, 128))
        img_buffer = io.BytesIO()
        rgba_img.save(img_buffer, format='PNG')
        rgba_data = img_buffer.getvalue()
        
        thumbnail_data = image_service._generate_image_thumbnails(rgba_data)
        
        assert thumbnail_data is not None
        # Should be converted to RGB for JPEG thumbnail
        thumbnail_img = Image.open(io.BytesIO(thumbnail_data))
        assert thumbnail_img.mode == 'RGB'
    
    def test_generate_image_thumbnails_invalid_data(self, image_service):
        """Test thumbnail generation with invalid image data."""
        invalid_data = b'not an image'
        
        result = image_service._generate_image_thumbnails(invalid_data)
        
        assert result is None
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_multiple_formats_on_page(self, mock_fitz, image_service, sample_pdf_path):
        """Test extraction of multiple image formats from single page."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 1
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        # Multiple images with different formats
        mock_page.get_images.return_value = [
            (1, 0, 0, 0, 0, 'img1', 'DCT', 100, 100),
            (2, 0, 0, 0, 0, 'img2', 'FlateDecode', 100, 100),
            (3, 0, 0, 0, 0, 'img3', 'JPXDecode', 100, 100)
        ]
        
        # Mock different image extractions
        mock_doc.extract_image.side_effect = [
            {'image': b'jpeg_data', 'ext': 'jpg'},
            {'image': b'png_data', 'ext': 'png'},
            {'image': b'jp2_data', 'ext': 'jp2'}
        ]
        
        with patch.object(image_service.temp_file_manager, 'downloads_dir'):
            with patch('builtins.open', mock_builtins_open):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 1024
                    
                    result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is True
        assert result['statistics']['embedded_images_found'] == 3
    
    @pytest.mark.parametrize("output_format,quality", [
        ('PNG', 95),
        ('JPEG', 85),
        ('TIFF', 95),
        ('WEBP', 80)
    ])
    def test_extract_images_different_output_formats(self, image_service, sample_pdf_path, output_format, quality):
        """Test extraction with different output formats."""
        with patch('app.services.image_extraction_service.fitz') as mock_fitz:
            mock_doc = Mock()
            mock_fitz.open.return_value = mock_doc
            mock_doc.__len__.return_value = 1
            
            mock_page = Mock()
            mock_doc.load_page.return_value = mock_page
            mock_page.get_images.return_value = [(1, 0, 0, 0, 0, 'img', 'DCT', 50, 50)]
            mock_doc.extract_image.return_value = {'image': b'test_data', 'ext': 'png'}
            
            with patch.object(image_service.temp_file_manager, 'downloads_dir'):
                with patch('builtins.open', mock_builtins_open):
                    with patch('pathlib.Path.stat') as mock_stat:
                        mock_stat.return_value.st_size = 1024
                        
                        result = image_service.extract_images(
                            sample_pdf_path,
                            output_format=output_format,
                            quality=quality
                        )
        
        assert result['success'] is True
        assert result['output_format'] == output_format
    
    @patch('app.services.image_extraction_service.fitz')
    def test_extract_images_memory_management_large_images(self, mock_fitz, image_service, sample_pdf_path):
        """Test memory management with large images."""
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 5
        
        mock_page = Mock()
        mock_doc.load_page.return_value = mock_page
        mock_page.get_images.return_value = [(1, 0, 0, 0, 0, 'img', 'DCT', 2000, 2000)]  # Large image
        
        # Mock large image data (but within 10MB limit)
        large_image_data = b'x' * (8 * 1024 * 1024)  # 8MB
        mock_doc.extract_image.return_value = {'image': large_image_data, 'ext': 'png'}
        
        with patch.object(image_service.temp_file_manager, 'downloads_dir'):
            with patch('builtins.open', mock_builtins_open):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = len(large_image_data)
                    
                    result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is True
        assert result['statistics']['embedded_images_extracted'] == 5
    
    def test_image_extraction_with_progress_tracking(self, image_service, sample_pdf_path):
        """Test that image extraction properly tracks progress through pages."""
        with patch('app.services.image_extraction_service.fitz') as mock_fitz:
            mock_doc = Mock()
            mock_fitz.open.return_value = mock_doc
            mock_doc.__len__.return_value = 10  # Multiple pages
            
            mock_page = Mock()
            mock_doc.load_page.return_value = mock_page
            mock_page.get_images.return_value = []  # No images for simplicity
            
            result = image_service.extract_images(sample_pdf_path)
        
        assert result['success'] is True
        assert result['total_pages_processed'] == 10
        assert result['statistics']['pages_processed'] == 10


# Helper function for mocking file operations
def mock_builtins_open(*args, **kwargs):
    """Mock builtin open function for file operations."""
    mock_file = Mock()
    mock_file.__enter__ = Mock(return_value=mock_file)
    mock_file.__exit__ = Mock(return_value=None)
    mock_file.write = Mock()
    return mock_file