"""
Comprehensive unit tests for the BoundingBoxCalculator.

Tests text layer coordinate calculation, OCR coordinate integration,
coordinate validation and normalization, and fallback mechanisms.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

import fitz  # PyMuPDF

from app.services.bounding_box_calculator import BoundingBoxCalculator, BoundingBox
from app.models import OCRResult


class TestBoundingBoxCalculator:
    """Test suite for BoundingBoxCalculator."""
    
    @pytest.fixture
    def bbox_calculator(self):
        """Create a BoundingBoxCalculator instance for testing."""
        return BoundingBoxCalculator()
    
    @pytest.fixture
    def mock_pdf_document(self):
        """Create a mock PDF document with known text layout."""
        mock_doc = Mock()
        mock_page = Mock()
        
        # Mock search results for "test text"
        mock_rect1 = Mock()
        mock_rect1.x0, mock_rect1.y0 = 100, 200
        mock_rect1.x1, mock_rect1.y1 = 200, 220
        
        mock_rect2 = Mock()
        mock_rect2.x0, mock_rect2.y0 = 300, 400
        mock_rect2.x1, mock_rect2.y1 = 400, 420
        
        mock_page.search_for.return_value = [mock_rect1, mock_rect2]
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.__len__.return_value = 1
        mock_doc.close = Mock()
        
        return mock_doc
    
    @pytest.fixture
    def sample_ocr_result(self):
        """Create a sample OCRResult for testing."""
        ocr_result = Mock(spec=OCRResult)
        ocr_result.page_number = 0
        ocr_result.page_width = 612
        ocr_result.page_height = 792
        ocr_result.text_regions = [
            {
                'text': 'This contains test text that we want',
                'bbox': {'x': 100, 'y': 150, 'width': 200, 'height': 30},
                'confidence': 0.95
            },
            {
                'text': 'Another region with more test content',
                'bbox': {'x': 300, 'y': 200, 'width': 180, 'height': 25},
                'confidence': 0.88
            }
        ]
        return ocr_result


class TestBoundingBox:
    """Test suite for BoundingBox dataclass."""
    
    def test_bounding_box_creation(self):
        """Test BoundingBox creation with all parameters."""
        bbox = BoundingBox(
            x=100.0,
            y=200.0,
            width=150.0,
            height=30.0,
            page_number=0,
            confidence=0.95,
            source="text_layer"
        )
        
        assert bbox.x == 100.0
        assert bbox.y == 200.0
        assert bbox.width == 150.0
        assert bbox.height == 30.0
        assert bbox.page_number == 0
        assert bbox.confidence == 0.95
        assert bbox.source == "text_layer"
    
    def test_bounding_box_to_dict(self):
        """Test conversion to dictionary format."""
        bbox = BoundingBox(x=50, y=100, width=200, height=40, page_number=1)
        result = bbox.to_dict()
        
        expected = {
            'x_coordinate': 50,
            'y_coordinate': 100,
            'width': 200,
            'height': 40,
            'page_number': 1,
            'confidence': 1.0,
            'source': 'text_layer'
        }
        
        assert result == expected
    
    def test_bounding_box_overlaps_same_page(self):
        """Test overlap detection on same page."""
        bbox1 = BoundingBox(x=100, y=100, width=100, height=50, page_number=0)
        bbox2 = BoundingBox(x=150, y=120, width=100, height=50, page_number=0)
        
        assert bbox1.overlaps_with(bbox2)
        assert bbox2.overlaps_with(bbox1)
    
    def test_bounding_box_no_overlap_same_page(self):
        """Test no overlap detection on same page."""
        bbox1 = BoundingBox(x=100, y=100, width=50, height=50, page_number=0)
        bbox2 = BoundingBox(x=200, y=200, width=50, height=50, page_number=0)
        
        assert not bbox1.overlaps_with(bbox2)
        assert not bbox2.overlaps_with(bbox1)
    
    def test_bounding_box_no_overlap_different_pages(self):
        """Test no overlap on different pages."""
        bbox1 = BoundingBox(x=100, y=100, width=100, height=50, page_number=0)
        bbox2 = BoundingBox(x=110, y=110, width=80, height=40, page_number=1)
        
        assert not bbox1.overlaps_with(bbox2)
    
    def test_bounding_box_overlap_with_tolerance(self):
        """Test overlap detection with tolerance."""
        bbox1 = BoundingBox(x=100, y=100, width=50, height=50, page_number=0)
        bbox2 = BoundingBox(x=155, y=100, width=50, height=50, page_number=0)
        
        assert not bbox1.overlaps_with(bbox2, tolerance=0)
        assert bbox1.overlaps_with(bbox2, tolerance=10)


class TestTextLayerCalculation:
    """Test suite for text layer coordinate calculation."""
    
    @patch('fitz.open')
    def test_calculate_text_layer_boxes_success(self, mock_fitz_open, bbox_calculator, mock_pdf_document):
        """Test successful text layer coordinate calculation."""
        mock_fitz_open.return_value = mock_pdf_document
        
        boxes = bbox_calculator.calculate_text_layer_boxes(
            "test.pdf",
            "test text"
        )
        
        assert len(boxes) == 2
        assert all(isinstance(box, BoundingBox) for box in boxes)
        assert boxes[0].x == 100
        assert boxes[0].y == 200
        assert boxes[0].width == 100
        assert boxes[0].height == 20
        assert boxes[0].source == "text_layer"
        assert boxes[0].confidence == 1.0
    
    @patch('fitz.open')
    def test_calculate_text_layer_boxes_specific_page(self, mock_fitz_open, bbox_calculator, mock_pdf_document):
        """Test text layer calculation for specific page."""
        mock_fitz_open.return_value = mock_pdf_document
        
        boxes = bbox_calculator.calculate_text_layer_boxes(
            "test.pdf",
            "test text",
            page_number=0
        )
        
        assert len(boxes) == 2
        assert all(box.page_number == 0 for box in boxes)
        mock_pdf_document[0].search_for.assert_called_once_with("test text")
    
    @patch('fitz.open')
    def test_calculate_text_layer_boxes_no_matches(self, mock_fitz_open, bbox_calculator):
        """Test text layer calculation with no matches."""
        mock_doc = Mock()
        mock_page = Mock()
        mock_page.search_for.return_value = []  # No matches
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.__len__.return_value = 1
        mock_doc.close = Mock()
        
        mock_fitz_open.return_value = mock_doc
        
        boxes = bbox_calculator.calculate_text_layer_boxes("test.pdf", "nonexistent")
        
        assert len(boxes) == 0
    
    @patch('fitz.open')
    def test_calculate_text_layer_boxes_error_handling(self, mock_fitz_open, bbox_calculator):
        """Test error handling in text layer calculation."""
        mock_fitz_open.side_effect = Exception("PDF open failed")
        
        boxes = bbox_calculator.calculate_text_layer_boxes("bad.pdf", "test")
        
        assert len(boxes) == 0  # Should return empty list on error


class TestOCRCoordinateIntegration:
    """Test suite for OCR coordinate integration."""
    
    def test_calculate_ocr_boxes_success(self, bbox_calculator, sample_ocr_result):
        """Test successful OCR coordinate extraction."""
        boxes = bbox_calculator.calculate_ocr_boxes(sample_ocr_result, "test")
        
        assert len(boxes) == 2  # Both regions contain "test"
        assert all(isinstance(box, BoundingBox) for box in boxes)
        assert boxes[0].source == "ocr"
        assert boxes[0].page_number == 0
        assert boxes[0].x == 100
        assert boxes[0].y == 150
        assert boxes[0].confidence == 0.95
    
    def test_calculate_ocr_boxes_case_insensitive(self, bbox_calculator, sample_ocr_result):
        """Test case-insensitive OCR search."""
        boxes = bbox_calculator.calculate_ocr_boxes(sample_ocr_result, "TEST")
        
        assert len(boxes) == 2  # Should find matches despite case difference
    
    def test_calculate_ocr_boxes_no_matches(self, bbox_calculator, sample_ocr_result):
        """Test OCR search with no matches."""
        boxes = bbox_calculator.calculate_ocr_boxes(sample_ocr_result, "nonexistent")
        
        assert len(boxes) == 0
    
    def test_calculate_ocr_boxes_invalid_coordinates(self, bbox_calculator):
        """Test OCR boxes with invalid coordinates."""
        ocr_result = Mock(spec=OCRResult)
        ocr_result.page_number = 0
        ocr_result.page_width = 612
        ocr_result.page_height = 792
        ocr_result.text_regions = [
            {
                'text': 'test text',
                'bbox': {'x': -10, 'y': 100, 'width': 50, 'height': 20},  # Negative x
                'confidence': 0.9
            },
            {
                'text': 'more test content',
                'bbox': {'x': 100, 'y': 100, 'width': 700, 'height': 20},  # Width exceeds page
                'confidence': 0.8
            }
        ]
        
        boxes = bbox_calculator.calculate_ocr_boxes(ocr_result, "test")
        
        assert len(boxes) == 0  # Invalid coordinates should be filtered out


class TestCoordinateValidation:
    """Test suite for coordinate validation and normalization."""
    
    def test_validate_coordinates_valid(self, bbox_calculator):
        """Test validation of valid coordinates."""
        page_dims = {'width': 612, 'height': 792}
        
        result = bbox_calculator.validate_coordinates(100, 200, 150, 30, page_dims)
        
        assert result is True
    
    def test_validate_coordinates_negative(self, bbox_calculator):
        """Test validation rejects negative coordinates."""
        page_dims = {'width': 612, 'height': 792}
        
        result = bbox_calculator.validate_coordinates(-10, 200, 150, 30, page_dims)
        
        assert result is False
    
    def test_validate_coordinates_zero_size(self, bbox_calculator):
        """Test validation rejects zero or negative sizes."""
        page_dims = {'width': 612, 'height': 792}
        
        result1 = bbox_calculator.validate_coordinates(100, 200, 0, 30, page_dims)
        result2 = bbox_calculator.validate_coordinates(100, 200, 150, -10, page_dims)
        
        assert result1 is False
        assert result2 is False
    
    def test_validate_coordinates_exceeds_bounds(self, bbox_calculator):
        """Test validation rejects coordinates exceeding page bounds."""
        page_dims = {'width': 612, 'height': 792}
        
        result1 = bbox_calculator.validate_coordinates(600, 200, 50, 30, page_dims)  # x + width > page width
        result2 = bbox_calculator.validate_coordinates(100, 780, 150, 30, page_dims)  # y + height > page height
        
        assert result1 is False
        assert result2 is False
    
    def test_normalize_coordinates_same_dpi(self, bbox_calculator):
        """Test coordinate normalization with same DPI."""
        bbox = BoundingBox(x=100, y=200, width=150, height=30, page_number=0)
        
        normalized = bbox_calculator.normalize_coordinates(bbox, 300, 300)
        
        assert normalized.x == 100
        assert normalized.y == 200
        assert normalized.width == 150
        assert normalized.height == 30
    
    def test_normalize_coordinates_different_dpi(self, bbox_calculator):
        """Test coordinate normalization with different DPI."""
        bbox = BoundingBox(x=100, y=200, width=150, height=30, page_number=0)
        
        normalized = bbox_calculator.normalize_coordinates(bbox, 150, 300)  # 2x scale
        
        assert normalized.x == 200
        assert normalized.y == 400
        assert normalized.width == 300
        assert normalized.height == 60


class TestBoxManipulation:
    """Test suite for box manipulation operations."""
    
    def test_merge_overlapping_boxes_same_page(self, bbox_calculator):
        """Test merging overlapping boxes on same page."""
        boxes = [
            BoundingBox(x=100, y=100, width=100, height=50, page_number=0),
            BoundingBox(x=150, y=120, width=100, height=50, page_number=0),  # Overlaps with first
            BoundingBox(x=300, y=300, width=50, height=30, page_number=0)   # Separate
        ]
        
        merged = bbox_calculator.merge_overlapping_boxes(boxes, tolerance=5)
        
        assert len(merged) == 2  # Should merge first two
        # First merged box should encompass both original boxes
        merged_box = next(box for box in merged if box.x <= 150 and box.x + box.width >= 250)
        assert merged_box.x == 100
        assert merged_box.width == 150  # 250 - 100
    
    def test_merge_overlapping_boxes_different_pages(self, bbox_calculator):
        """Test that boxes on different pages are not merged."""
        boxes = [
            BoundingBox(x=100, y=100, width=100, height=50, page_number=0),
            BoundingBox(x=110, y=110, width=80, height=40, page_number=1)  # Different page
        ]
        
        merged = bbox_calculator.merge_overlapping_boxes(boxes)
        
        assert len(merged) == 2  # Should not merge different pages
    
    def test_expand_box_margins(self, bbox_calculator):
        """Test expanding box margins."""
        bbox = BoundingBox(x=100, y=200, width=150, height=30, page_number=0)
        
        expanded = bbox_calculator.expand_box_margins(bbox, margin_pixels=5)
        
        assert expanded.x == 95
        assert expanded.y == 195
        assert expanded.width == 160
        assert expanded.height == 40
    
    def test_expand_box_margins_with_page_bounds(self, bbox_calculator):
        """Test expanding box margins with page boundary constraints."""
        bbox = BoundingBox(x=5, y=10, width=50, height=20, page_number=0)
        page_dims = {'width': 100, 'height': 100}
        
        expanded = bbox_calculator.expand_box_margins(bbox, margin_pixels=10, page_dimensions=page_dims)
        
        # Should not go negative or exceed page bounds
        assert expanded.x == 0  # Clipped to page boundary
        assert expanded.y == 0  # Clipped to page boundary
        assert expanded.x + expanded.width <= 100
        assert expanded.y + expanded.height <= 100
    
    def test_convert_coordinate_systems(self, bbox_calculator):
        """Test coordinate system conversion."""
        bbox = BoundingBox(x=100, y=50, width=150, height=30, page_number=0)
        page_height = 792
        
        # Convert from top-left to bottom-left
        converted = bbox_calculator.convert_coordinate_systems(
            bbox, 'top-left', 'bottom-left', page_height
        )
        
        # y should be: 792 - (50 + 30) = 712
        assert converted.x == 100
        assert converted.y == 712
        assert converted.width == 150
        assert converted.height == 30
        
        # Convert back should give original
        back_converted = bbox_calculator.convert_coordinate_systems(
            converted, 'bottom-left', 'top-left', page_height
        )
        
        assert back_converted.x == bbox.x
        assert back_converted.y == bbox.y


class TestFallbackMechanisms:
    """Test suite for fallback coordinate calculation."""
    
    @patch('fitz.open')
    def test_calculate_fallback_boxes(self, mock_fitz_open, bbox_calculator):
        """Test fallback coordinate calculation method."""
        # Mock document structure for fallback text extraction
        mock_doc = Mock()
        mock_page = Mock()
        
        # Mock text blocks structure
        mock_blocks = {
            "blocks": [
                {
                    "type": 0,  # Text block
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "This contains test text",
                                    "bbox": [100, 200, 250, 220]
                                },
                                {
                                    "text": "Another span with test",
                                    "bbox": [300, 300, 450, 320]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        mock_page.get_text.return_value = mock_blocks
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.close = Mock()
        mock_fitz_open.return_value = mock_doc
        
        boxes = bbox_calculator.calculate_fallback_boxes("test.pdf", "test", 0)
        
        assert len(boxes) == 2
        assert all(box.confidence == 0.7 for box in boxes)  # Lower confidence for fallback
        assert all(box.source == "fallback" for box in boxes)
    
    @patch('fitz.open')
    def test_calculate_fallback_boxes_error(self, mock_fitz_open, bbox_calculator):
        """Test fallback method error handling."""
        mock_fitz_open.side_effect = Exception("Fallback failed")
        
        boxes = bbox_calculator.calculate_fallback_boxes("bad.pdf", "test", 0)
        
        assert len(boxes) == 0


class TestBatchProcessing:
    """Test suite for batch coordinate calculation."""
    
    @patch('fitz.open')
    def test_batch_calculate_boxes(self, mock_fitz_open, bbox_calculator, mock_pdf_document):
        """Test batch processing of multiple search terms."""
        mock_fitz_open.return_value = mock_pdf_document
        
        search_terms = ["test", "example", "sample"]
        
        results = bbox_calculator.batch_calculate_boxes("test.pdf", search_terms)
        
        assert len(results) == 3
        assert all(term in results for term in search_terms)
        assert all(isinstance(results[term], list) for term in search_terms)
    
    def test_clear_cache(self, bbox_calculator):
        """Test cache clearing functionality."""
        # Add something to cache
        bbox_calculator._cache["test_doc"] = Mock()
        
        bbox_calculator.clear_cache()
        
        assert len(bbox_calculator._cache) == 0


class TestPerformanceAndEdgeCases:
    """Test suite for performance optimization and edge cases."""
    
    def test_empty_input_handling(self, bbox_calculator):
        """Test handling of empty inputs."""
        # Empty matches list
        merged = bbox_calculator.merge_overlapping_boxes([])
        assert merged == []
        
        # Empty OCR regions
        ocr_result = Mock(spec=OCRResult)
        ocr_result.text_regions = []
        boxes = bbox_calculator.calculate_ocr_boxes(ocr_result, "test")
        assert len(boxes) == 0
    
    def test_large_number_of_boxes(self, bbox_calculator):
        """Test performance with large number of boxes."""
        # Create many boxes
        boxes = [
            BoundingBox(x=i*10, y=i*10, width=50, height=20, page_number=0)
            for i in range(100)
        ]
        
        # Should handle large number efficiently
        merged = bbox_calculator.merge_overlapping_boxes(boxes, tolerance=1)
        assert isinstance(merged, list)
        assert len(merged) <= len(boxes)
    
    def test_precision_handling(self, bbox_calculator):
        """Test handling of floating point precision."""
        bbox = BoundingBox(
            x=100.123456789,
            y=200.987654321,
            width=150.555555555,
            height=30.111111111,
            page_number=0
        )
        
        # Should maintain precision
        expanded = bbox_calculator.expand_box_margins(bbox, margin_pixels=5.5)
        assert isinstance(expanded.x, float)
        assert isinstance(expanded.y, float)