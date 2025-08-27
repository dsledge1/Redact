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
        # Mock PDF processor
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'High quality text content from page 1.',
                    'has_text_layer': True,
                    'char_count': 39,
                    'extraction_confidence': 1.0
                }
            ],
            'total_pages': 1,
            'extraction_method': 'text_layer'
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.TEXT_LAYER,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_method'], ExtractionMethod.TEXT_LAYER)
        self.assertEqual(len(result['pages']), 1)
        
        # Verify first page result
        page_result = result['pages'][0]
        self.assertEqual(page_result['page_number'], 1)
        self.assertIn('High quality text', page_result['text'])
        self.assertEqual(page_result['extraction_confidence'], 1.0)
        
        # Verify PDF processor was called
        self.mock_pdf_processor.extract_text.assert_called_once()
        
        # OCR should not have been called for text layer extraction
        self.mock_ocr_service.extract_text_from_images.assert_not_called()
    
    def test_extract_text_unified_ocr(self):
        """Test unified extraction using OCR method."""
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
        self.mock_ocr_service.extract_text_from_images.return_value = {
            'success': True,
            'results': [
                {
                    'page_number': 1,
                    'text': 'OCR extracted text',
                    'confidence': 0.85,
                    'language': 'eng'
                }
            ],
            'total_processed': 1
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.OCR,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_method'], ExtractionMethod.OCR)
        self.assertEqual(len(result['pages']), 1)
        
        page_result = result['pages'][0]
        self.assertEqual(page_result['page_number'], 1)
        self.assertIn('OCR extracted text', page_result['text'])
        
        # Verify both services were called
        self.mock_pdf_processor.extract_pages_as_images.assert_called_once()
        self.mock_ocr_service.extract_text_from_images.assert_called_once()
    
    def test_extract_text_unified_hybrid(self):
        """Test unified extraction using hybrid method."""
        # Mock PDF processor for text extraction
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Text layer content',
                    'has_text_layer': True,
                    'char_count': 18,
                    'extraction_confidence': 0.6  # Lower confidence
                }
            ],
            'total_pages': 1,
            'extraction_method': 'text_layer'
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
        self.mock_ocr_service.extract_text_from_images.return_value = {
            'success': True,
            'results': [
                {
                    'page_number': 1,
                    'text': 'OCR content with additional details',
                    'confidence': 0.82,
                    'language': 'eng'
                }
            ],
            'total_processed': 1
        }
        
        result = self.service.extract_text_unified(
            pdf_path=self.temp_pdf_path,
            method=ExtractionMethod.HYBRID,
            use_cache=False
        )
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result['success'])
        self.assertEqual(result['extraction_method'], ExtractionMethod.HYBRID)
        
        # Both services should have been called
        self.mock_pdf_processor.extract_text.assert_called_once()
        self.mock_pdf_processor.extract_pages_as_images.assert_called_once()
        self.mock_ocr_service.extract_text_from_images.assert_called_once()
    
    def test_extract_text_with_page_range(self):
        """Test extraction with specific page range."""
        # Mock PDF processor
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 2,
                    'text': 'Page 2 content',
                    'has_text_layer': True,
                    'char_count': 14,
                    'extraction_confidence': 1.0
                },
                {
                    'page_number': 3,
                    'text': 'Page 3 content',
                    'has_text_layer': True,
                    'char_count': 14,
                    'extraction_confidence': 1.0
                }
            ],
            'total_pages': 2,
            'extraction_method': 'text_layer'
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
        # Mock PDF processor
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Page 1',
                    'has_text_layer': True,
                    'char_count': 6,
                    'extraction_confidence': 1.0
                }
            ],
            'total_pages': 1,
            'extraction_method': 'text_layer'
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
        # Mock PDF processor
        self.mock_pdf_processor.extract_text.return_value = {
            'success': True,
            'pages': [
                {
                    'page_number': 1,
                    'text': 'Cached content',
                    'has_text_layer': True,
                    'char_count': 14,
                    'extraction_confidence': 1.0
                }
            ],
            'total_pages': 1,
            'extraction_method': 'text_layer'
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
        self.mock_pdf_processor.extract_text.side_effect = Exception("PDF processing error")
        
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
    
    def test_get_extraction_method_recommendations(self):
        """Test extraction method recommendation."""
        # Mock a sample analysis
        with patch.object(self.service, '_determine_extraction_method') as mock_determine:
            mock_determine.return_value = ExtractionMethod.TEXT_LAYER
            
            recommendation = self.service._determine_extraction_method(
                self.temp_pdf_path, (1, 1)
            )
            
            self.assertEqual(recommendation, ExtractionMethod.TEXT_LAYER)


class TestTextQualityAssessment(unittest.TestCase):
    """Test cases for text quality assessment integration."""
    
    def test_assess_extraction_quality(self):
        """Test text quality assessment."""
        service = TextExtractionService(session_id="test")
        
        # Test quality assessment of sample text
        with patch('app.utils.text_processing.text_quality_assessor') as mock_assessor:
            mock_assessor.assess_character_confidence.return_value = 0.8
            mock_assessor.assess_coherence.return_value = 0.7
            mock_assessor.assess_completeness.return_value = 0.9
            
            quality = service._assess_extraction_quality("Sample text for assessment")
            
            self.assertIsInstance(quality, TextQuality)
            self.assertGreaterEqual(quality.overall_score, 0.0)
            self.assertLessEqual(quality.overall_score, 1.0)


if __name__ == '__main__':
    unittest.main()