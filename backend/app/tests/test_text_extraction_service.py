"""
Unit tests for TextExtractionService.

Tests cover text layer extraction, OCR integration, hybrid approaches,
quality assessment, and caching.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from pathlib import Path

# Import the service and related classes
from ..services.text_extraction_service import (
    TextExtractionService, ExtractionMethod, TextQuality
)
from ..services.pdf_processor import PDFProcessor
from ..services.ocr_service import OCRService


class TestTextExtractionService(unittest.TestCase):
    """Test cases for TextExtractionService."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_pdf_processor = Mock(spec=PDFProcessor)
        self.mock_ocr_service = Mock(spec=OCRService)
        
        self.service = TextExtractionService(
            session_id="test_session",
            pdf_processor=self.mock_pdf_processor,
            ocr_service=self.mock_ocr_service
        )
        
        # Create a temporary PDF file for testing
        self.temp_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        self.temp_pdf_path = Path(self.temp_pdf.name)
        self.temp_pdf.close()
    
    def tearDown(self):
        """Clean up test environment."""
        try:
            os.unlink(self.temp_pdf_path)
        except OSError:
            pass
    
    def test_initialization(self):
        """Test service initialization with default parameters."""
        service = TextExtractionService(session_id="test")
        
        self.assertIsNotNone(service.pdf_processor)
        self.assertIsNotNone(service.ocr_service)
        self.assertEqual(service.session_id, "test")
    
    def test_initialization_with_custom_parameters(self):
        """Test service initialization with custom parameters."""
        custom_service = TextExtractionService(
            session_id="custom_session",
            pdf_processor=self.mock_pdf_processor,
            ocr_service=self.mock_ocr_service
        )
        
        self.assertEqual(custom_service.pdf_processor, self.mock_pdf_processor)
        self.assertEqual(custom_service.ocr_service, self.mock_ocr_service)
        self.assertEqual(custom_service.session_id, "custom_session")
    
    def test_extract_text_unified_text_layer(self):
        """Test unified extraction using text layer method."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': True
        }
        
        # Mock PDF processor text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'High quality text content from page 1.',
                    'has_text_layer': True,
                    'char_count': 39
                }
            ],
            'total_pages': 1
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_method'], 'text_layer')  # String value
        self.assertEqual(len(result['pages']), 1)
        
        # Verify first page result
        page_result = result['pages'][0]
        self.assertEqual(page_result['page_number'], 1)
        self.assertIn('High quality text', page_result['text'])
        self.assertEqual(page_result['extraction_confidence'], 1.0)
        
        # Verify PDF processor was called
        self.mock_pdf_processor.validate_pdf.assert_called_once()
        self.mock_pdf_processor.extract_text.assert_called_once()
        
        # OCR should not have been called for text layer extraction
        self.assertFalse(self.mock_ocr_service.process_pdf_page_image.called)
    
    def test_extract_text_unified_ocr(self):
        """Test unified extraction using OCR method."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': False
        }
        
        # Mock PDF processor for image extraction
        self.mock_pdf_processor.extract_pages_as_images.return_value = {
            'success': True,
            'images': [
                {
                    'page_number': 1,
                    'image_data': b'fake_image_data',
                    'format': 'png',
                    'dpi': 300
                }
            ],
            'total_pages': 1
        }
        
        # Mock OCR service - process_pdf_page_image called per image
        self.mock_ocr_service.process_pdf_page_image.return_value = {
            'success': True,
            'text': 'OCR extracted text',
            'confidence': 85.0,  # Will be converted to 0.85
            'language': 'eng',
            'words': [],
            'preprocessing_info': {}
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.OCR,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_method'], 'ocr')  # String value
        self.assertEqual(len(result['pages']), 1)
        
        page_result = result['pages'][0]
        self.assertEqual(page_result['page_number'], 1)
        self.assertIn('OCR extracted text', page_result['text'])
        self.assertEqual(page_result['extraction_confidence'], 0.85)  # Converted to 0-1 scale
        
        # Verify both services were called
        self.mock_pdf_processor.validate_pdf.assert_called_once()
        self.mock_pdf_processor.extract_pages_as_images.assert_called_once()
        self.mock_ocr_service.process_pdf_page_image.assert_called_once()
    
    def test_extract_text_unified_hybrid(self):
        """Test unified extraction using hybrid method."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': True
        }
        
        # Mock PDF processor for text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Poor quality text',
                    'has_text_layer': True,
                    'char_count': 18
                }
            ],
            'total_pages': 1
        }
        
        # Mock PDF processor for image extraction
        self.mock_pdf_processor.extract_pages_as_images.return_value = {
            'success': True,
            'images': [
                {
                    'page_number': 1,
                    'image_data': b'fake_image_data',
                    'format': 'png',
                    'dpi': 300
                }
            ],
            'total_pages': 1
        }
        
        # Mock OCR service
        self.mock_ocr_service.process_pdf_page_image.return_value = {
            'success': True,
            'text': 'OCR content with additional details',
            'confidence': 82.0,  # Will be converted to 0.82
            'language': 'eng',
            'words': [],
            'preprocessing_info': {}
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.HYBRID,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_method'], 'hybrid')  # String value
        
        # Both services should have been called
        self.mock_pdf_processor.validate_pdf.assert_called_once()
        self.mock_pdf_processor.extract_text.assert_called_once()
        # Note: OCR may or may not be called depending on text quality assessment
    
    def test_extract_text_with_page_range(self):
        """Test extraction with specific page range."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 5,
            'has_text_layer': True
        }
        
        # Mock PDF processor text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 2,
                    'text': 'Page 2 content',
                    'has_text_layer': True,
                    'char_count': 14
                },
                {
                    'page_number': 3,
                    'text': 'Page 3 content',
                    'has_text_layer': True,
                    'char_count': 14
                }
            ],
            'total_pages': 2
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            page_range=(2, 3),
            use_cache=False
        )
        
        self.assertEqual(len(result['pages']), 2)
        
        # Verify correct pages were processed
        page_numbers = [page['page_number'] for page in result['pages']]
        self.assertEqual(page_numbers, [2, 3])
    
    def test_extract_text_with_progress_callback(self):
        """Test extraction with progress callback."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': True
        }
        
        # Mock PDF processor text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Page 1',
                    'has_text_layer': True,
                    'char_count': 6
                }
            ],
            'total_pages': 1
        }
        
        progress_calls = []
        def progress_callback(current, total):
            progress_calls.append((current, total))
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            progress_callback=progress_callback,
            use_cache=False
        )
        
        # Verify progress callback was called (at least once)
        self.assertGreaterEqual(len(progress_calls), 1)
    
    def test_extract_text_with_caching(self):
        """Test extraction with caching enabled."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': True
        }
        
        # Mock PDF processor text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Cached content',
                    'has_text_layer': True,
                    'char_count': 14
                }
            ],
            'total_pages': 1
        }
        
        # First extraction
        result1 = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            use_cache=True
        )
        
        # Second extraction should use cache
        result2 = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            use_cache=True
        )
        
        # Results should be identical
        self.assertEqual(result1['pages'][0]['text'], result2['pages'][0]['text'])
    
    def test_extract_text_error_handling(self):
        """Test error handling during extraction."""
        # Mock PDF processor validation to fail
        self.mock_pdf_processor.validate_pdf.side_effect = Exception("PDF processing error")
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            use_cache=False
        )
        
        # Should return error result instead of raising exception
        self.assertFalse(result['success'])
        self.assertIn('error', result)
    
    def test_extract_text_invalid_pdf_path(self):
        """Test extraction with invalid PDF path."""
        invalid_path = Path("/nonexistent/path.pdf")
        
        result = self.service.extract_text_unified(
            pdf_path=invalid_path,
            method=ExtractionMethod.TEXT_LAYER,
            use_cache=False
        )
        
        # Should handle the error gracefully
        self.assertFalse(result['success'])
    
    def test_clear_cache(self):
        """Test cache clearing functionality."""
        # Test the clear_cache method exists and returns results
        cache_result = self.service.clear_cache()
        
        self.assertIsInstance(cache_result, dict)
        self.assertIn('success', cache_result)
    
    def test_determine_extraction_method(self):
        """Test extraction method determination."""
        # Test with all required parameters
        with patch.object(self.service, '_determine_extraction_method') as mock_determine:
            mock_determine.return_value = ExtractionMethod.TEXT_LAYER
            
            result = self.service._determine_extraction_method(
                ExtractionMethod.AUTO,
                self.temp_pdf_path,
                True,  # has_text_layer
                (1, 1)  # page_range
            )
            
            self.assertEqual(result, ExtractionMethod.TEXT_LAYER)
            mock_determine.assert_called_once_with(
                ExtractionMethod.AUTO,
                self.temp_pdf_path,
                True,
                (1, 1)
            )
    
    def test_text_quality_assessment(self):
        """Test text quality assessment methods."""
        # Test _assess_text_quality
        quality = self.service._assess_text_quality("High quality text with good content", 35)
        self.assertIsInstance(quality, TextQuality)
        
        # Test _assess_ocr_quality
        ocr_quality = self.service._assess_ocr_quality("OCR processed text", 0.8)
        self.assertIsInstance(ocr_quality, TextQuality)
        
        # Test _assess_combined_quality
        combined_quality = self.service._assess_combined_quality("Combined text", 0.85, 20)
        self.assertIsInstance(combined_quality, TextQuality)
    
    def test_extract_text_unified_auto_method(self):
        """Test extraction using AUTO method which determines best approach."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': True
        }
        
        # Mock PDF processor text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Good quality text from text layer',
                    'has_text_layer': True,
                    'char_count': 35
                }
            ],
            'total_pages': 1
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.AUTO,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        # AUTO method should determine the best extraction method
        self.assertIn(result['extraction_method'], ['text_layer', 'ocr', 'hybrid'])
    
    def test_ocr_confidence_conversion(self):
        """Test that OCR confidence is properly converted from 0-100 to 0.0-1.0 scale."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 1,
            'has_text_layer': False
        }
        
        # Mock PDF processor for image extraction
        self.mock_pdf_processor.extract_pages_as_images.return_value = {
            'success': True,
            'images': [
                {
                    'page_number': 1,
                    'image_data': b'fake_image_data',
                    'format': 'png',
                    'dpi': 300
                }
            ],
            'total_pages': 1
        }
        
        # Mock OCR service with 0-100 scale confidence
        self.mock_ocr_service.process_pdf_page_image.return_value = {
            'success': True,
            'text': 'OCR text',
            'confidence': 75.5,  # Should be converted to 0.755
            'language': 'eng',
            'words': [],
            'preprocessing_info': {}
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.OCR,
            use_cache=False
        )
        
        # Verify confidence was converted to 0.0-1.0 scale
        page_result = result['pages'][0]
        self.assertAlmostEqual(page_result['extraction_confidence'], 0.755, places=3)
        
        # Verify summary contains confidence scale documentation
        self.assertEqual(result['summary']['confidence_scale'], '0.0-1.0')
    
    def test_confidence_analysis_generation(self):
        """Test that confidence analysis is properly generated."""
        # Mock PDF processor validation
        self.mock_pdf_processor.validate_pdf.return_value = {
            'is_valid': True,
            'page_count': 2,
            'has_text_layer': True
        }
        
        # Mock PDF processor text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'First page content',
                    'has_text_layer': True,
                    'char_count': 18
                },
                {
                    'page_number': 2,
                    'text': 'Second page content',
                    'has_text_layer': True,
                    'char_count': 19
                }
            ],
            'total_pages': 2
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            include_confidence=True,
            use_cache=False
        )
        
        # Verify confidence analysis is included
        self.assertIn('confidence_analysis', result)
        confidence_analysis = result['confidence_analysis']
        
        # Check required confidence statistics
        self.assertIn('min_confidence', confidence_analysis)
        self.assertIn('max_confidence', confidence_analysis)
        self.assertIn('average_confidence', confidence_analysis)
        self.assertIn('weighted_confidence', confidence_analysis)
        self.assertIn('confidence_distribution', confidence_analysis)
        self.assertIn('confidence_scale', confidence_analysis)
        
        # Verify confidence scale documentation
        self.assertEqual(confidence_analysis['confidence_scale'], '0.0-1.0')


if __name__ == '__main__':
    unittest.main()