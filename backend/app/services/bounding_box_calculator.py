"""
BoundingBoxCalculator: Service for calculating and validating bounding boxes for redaction areas.

This service handles coordinate calculation from various text sources (PDF text layer, OCR)
and ensures accurate bounding box generation for redaction operations.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import fitz  # PyMuPDF
import numpy as np

from app.models import OCRResult

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """Represents a bounding box with coordinates and metadata."""
    x: float
    y: float
    width: float
    height: float
    page_number: int
    confidence: float = 1.0
    source: str = "text_layer"  # text_layer, ocr, manual
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'x_coordinate': self.x,
            'y_coordinate': self.y,
            'width': self.width,
            'height': self.height,
            'page_number': self.page_number,
            'confidence': self.confidence,
            'source': self.source
        }
    
    def overlaps_with(self, other: 'BoundingBox', tolerance: float = 5.0) -> bool:
        """Check if this box overlaps with another."""
        if self.page_number != other.page_number:
            return False
            
        # Check for overlap with tolerance
        x_overlap = not (
            self.x + self.width + tolerance < other.x or
            other.x + other.width + tolerance < self.x
        )
        y_overlap = not (
            self.y + self.height + tolerance < other.y or
            other.y + other.height + tolerance < self.y
        )
        
        return x_overlap and y_overlap


class BoundingBoxCalculator:
    """Service for calculating and validating bounding boxes for redaction areas."""
    
    def __init__(self):
        """Initialize the BoundingBoxCalculator."""
        self.logger = logger
        self._cache = {}
        
    def calculate_text_layer_boxes(
        self,
        pdf_path: str,
        search_text: str,
        page_number: Optional[int] = None
    ) -> List[BoundingBox]:
        """
        Calculate bounding boxes using PyMuPDF's text search.
        
        Args:
            pdf_path: Path to PDF file
            search_text: Text to search for
            page_number: Optional specific page to search (None for all pages)
            
        Returns:
            List of BoundingBox objects with coordinates
        """
        boxes = []
        
        try:
            # Open PDF with PyMuPDF
            doc = fitz.open(pdf_path)
            
            # Determine pages to process
            if page_number is not None:
                pages_to_process = [page_number]
            else:
                pages_to_process = range(len(doc))
            
            # Search each page
            for page_num in pages_to_process:
                if page_num >= len(doc):
                    continue
                    
                page = doc[page_num]
                
                # Search for text on page
                text_instances = page.search_for(search_text)
                
                # Convert each instance to BoundingBox
                for rect in text_instances:
                    # PyMuPDF returns Rect objects with (x0, y0, x1, y1)
                    box = BoundingBox(
                        x=rect.x0,
                        y=rect.y0,
                        width=rect.x1 - rect.x0,
                        height=rect.y1 - rect.y0,
                        page_number=page_num,
                        confidence=1.0,  # Text layer matches have high confidence
                        source="text_layer"
                    )
                    boxes.append(box)
            
            doc.close()
            
            self.logger.debug(
                f"Found {len(boxes)} text instances of '{search_text}' in PDF"
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating text layer boxes: {str(e)}")
            
        return boxes
    
    def calculate_ocr_boxes(
        self,
        ocr_result: OCRResult,
        search_text: str
    ) -> List[BoundingBox]:
        """
        Extract bounding boxes from OCR results.
        
        Args:
            ocr_result: OCRResult model instance with text_regions
            search_text: Text to search for in OCR results
            
        Returns:
            List of BoundingBox objects from OCR data
        """
        boxes = []
        
        try:
            # Parse text_regions JSON field
            text_regions = ocr_result.text_regions or []
            
            for region in text_regions:
                # Check if region contains search text
                region_text = region.get('text', '')
                if search_text.lower() in region_text.lower():
                    # Extract coordinates
                    bbox = region.get('bbox', {})
                    
                    box = BoundingBox(
                        x=bbox.get('x', 0),
                        y=bbox.get('y', 0),
                        width=bbox.get('width', 0),
                        height=bbox.get('height', 0),
                        page_number=ocr_result.page_number,
                        confidence=region.get('confidence', 0.8),
                        source="ocr"
                    )
                    
                    # Only include if coordinates are valid
                    if self.validate_coordinates(
                        box.x, box.y, box.width, box.height,
                        {'width': ocr_result.page_width, 'height': ocr_result.page_height}
                    ):
                        boxes.append(box)
            
            self.logger.debug(
                f"Found {len(boxes)} OCR instances of '{search_text}'"
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating OCR boxes: {str(e)}")
            
        return boxes
    
    def validate_coordinates(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        page_dimensions: Dict[str, float]
    ) -> bool:
        """
        Ensure coordinates are within page boundaries.
        
        Args:
            x: X coordinate
            y: Y coordinate
            width: Box width
            height: Box height
            page_dimensions: Dictionary with 'width' and 'height' keys
            
        Returns:
            Boolean indicating if coordinates are valid
        """
        page_width = page_dimensions.get('width', 0)
        page_height = page_dimensions.get('height', 0)
        
        # Check basic validity
        if width <= 0 or height <= 0:
            return False
            
        # Check if box is within page boundaries
        if x < 0 or y < 0:
            return False
            
        if x + width > page_width or y + height > page_height:
            return False
            
        return True
    
    def normalize_coordinates(
        self,
        coords: BoundingBox,
        source_dpi: int,
        target_dpi: int
    ) -> BoundingBox:
        """
        Convert coordinates between different DPI settings.
        
        Args:
            coords: Original bounding box
            source_dpi: Source DPI
            target_dpi: Target DPI
            
        Returns:
            New BoundingBox with normalized coordinates
        """
        if source_dpi == target_dpi:
            return coords
            
        scale_factor = target_dpi / source_dpi
        
        return BoundingBox(
            x=coords.x * scale_factor,
            y=coords.y * scale_factor,
            width=coords.width * scale_factor,
            height=coords.height * scale_factor,
            page_number=coords.page_number,
            confidence=coords.confidence,
            source=coords.source
        )
    
    def merge_overlapping_boxes(
        self,
        boxes: List[BoundingBox],
        tolerance: float = 5.0
    ) -> List[BoundingBox]:
        """
        Combine adjacent or overlapping redaction areas.
        
        Args:
            boxes: List of bounding boxes
            tolerance: Pixel tolerance for considering boxes as overlapping
            
        Returns:
            List of merged bounding boxes
        """
        if not boxes:
            return []
            
        # Group boxes by page
        boxes_by_page = {}
        for box in boxes:
            if box.page_number not in boxes_by_page:
                boxes_by_page[box.page_number] = []
            boxes_by_page[box.page_number].append(box)
        
        merged_boxes = []
        
        # Process each page
        for page_num, page_boxes in boxes_by_page.items():
            # Sort boxes by position for efficient merging
            page_boxes.sort(key=lambda b: (b.y, b.x))
            
            merged_page_boxes = []
            for box in page_boxes:
                merged = False
                
                # Check if box overlaps with any existing merged box
                for i, merged_box in enumerate(merged_page_boxes):
                    if box.overlaps_with(merged_box, tolerance):
                        # Merge boxes
                        min_x = min(box.x, merged_box.x)
                        min_y = min(box.y, merged_box.y)
                        max_x = max(box.x + box.width, merged_box.x + merged_box.width)
                        max_y = max(box.y + box.height, merged_box.y + merged_box.height)
                        
                        merged_page_boxes[i] = BoundingBox(
                            x=min_x,
                            y=min_y,
                            width=max_x - min_x,
                            height=max_y - min_y,
                            page_number=page_num,
                            confidence=max(box.confidence, merged_box.confidence),
                            source=box.source
                        )
                        merged = True
                        break
                
                if not merged:
                    merged_page_boxes.append(box)
            
            merged_boxes.extend(merged_page_boxes)
        
        self.logger.debug(
            f"Merged {len(boxes)} boxes into {len(merged_boxes)} boxes"
        )
        
        return merged_boxes
    
    def expand_box_margins(
        self,
        box: BoundingBox,
        margin_pixels: float = 2.0,
        page_dimensions: Optional[Dict[str, float]] = None
    ) -> BoundingBox:
        """
        Add padding around text for complete coverage.
        
        Args:
            box: Original bounding box
            margin_pixels: Pixels to add as margin
            page_dimensions: Optional page dimensions for boundary checking
            
        Returns:
            Expanded bounding box
        """
        expanded = BoundingBox(
            x=max(0, box.x - margin_pixels),
            y=max(0, box.y - margin_pixels),
            width=box.width + (2 * margin_pixels),
            height=box.height + (2 * margin_pixels),
            page_number=box.page_number,
            confidence=box.confidence,
            source=box.source
        )
        
        # Clip to page boundaries if dimensions provided
        if page_dimensions:
            page_width = page_dimensions.get('width', float('inf'))
            page_height = page_dimensions.get('height', float('inf'))
            
            # Ensure box doesn't exceed page boundaries
            if expanded.x + expanded.width > page_width:
                expanded.width = page_width - expanded.x
            if expanded.y + expanded.height > page_height:
                expanded.height = page_height - expanded.y
        
        return expanded
    
    def convert_coordinate_systems(
        self,
        box: BoundingBox,
        from_system: str,
        to_system: str,
        page_height: float
    ) -> BoundingBox:
        """
        Convert between coordinate systems (top-left vs bottom-left origin).
        
        Args:
            box: Original bounding box
            from_system: Source coordinate system ('top-left' or 'bottom-left')
            to_system: Target coordinate system ('top-left' or 'bottom-left')
            page_height: Page height for coordinate conversion
            
        Returns:
            BoundingBox in target coordinate system
        """
        if from_system == to_system:
            return box
            
        converted = BoundingBox(
            x=box.x,
            y=box.y,
            width=box.width,
            height=box.height,
            page_number=box.page_number,
            confidence=box.confidence,
            source=box.source
        )
        
        # Convert between top-left and bottom-left origins
        if from_system == 'top-left' and to_system == 'bottom-left':
            # Convert from top-left to bottom-left
            converted.y = page_height - (box.y + box.height)
        elif from_system == 'bottom-left' and to_system == 'top-left':
            # Convert from bottom-left to top-left
            converted.y = page_height - (box.y + box.height)
        
        return converted
    
    def calculate_fallback_boxes(
        self,
        pdf_path: str,
        search_text: str,
        page_number: int
    ) -> List[BoundingBox]:
        """
        Fallback mechanism when primary coordinate calculation fails.
        
        Args:
            pdf_path: Path to PDF file
            search_text: Text to search for
            page_number: Page number to search
            
        Returns:
            List of approximate bounding boxes
        """
        boxes = []
        
        try:
            # Try alternative search methods
            doc = fitz.open(pdf_path)
            page = doc[page_number]
            
            # Get all text blocks on page
            blocks = page.get_text("dict")
            
            # Search through blocks for matching text
            for block in blocks.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "")
                            if search_text.lower() in text.lower():
                                # Extract bbox from span
                                bbox = span.get("bbox", [0, 0, 0, 0])
                                if len(bbox) >= 4:
                                    box = BoundingBox(
                                        x=bbox[0],
                                        y=bbox[1],
                                        width=bbox[2] - bbox[0],
                                        height=bbox[3] - bbox[1],
                                        page_number=page_number,
                                        confidence=0.7,  # Lower confidence for fallback
                                        source="fallback"
                                    )
                                    boxes.append(box)
            
            doc.close()
            
        except Exception as e:
            self.logger.error(f"Fallback box calculation failed: {str(e)}")
            
        return boxes
    
    def batch_calculate_boxes(
        self,
        pdf_path: str,
        search_terms: List[str]
    ) -> Dict[str, List[BoundingBox]]:
        """
        Calculate boxes for multiple search terms efficiently.
        
        Args:
            pdf_path: Path to PDF file
            search_terms: List of terms to search for
            
        Returns:
            Dictionary mapping search terms to their bounding boxes
        """
        results = {}
        
        # Cache document for batch processing
        cache_key = f"doc_{pdf_path}"
        if cache_key not in self._cache:
            self._cache[cache_key] = fitz.open(pdf_path)
        
        doc = self._cache[cache_key]
        
        for term in search_terms:
            boxes = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text_instances = page.search_for(term)
                
                for rect in text_instances:
                    box = BoundingBox(
                        x=rect.x0,
                        y=rect.y0,
                        width=rect.x1 - rect.x0,
                        height=rect.y1 - rect.y0,
                        page_number=page_num,
                        confidence=1.0,
                        source="text_layer"
                    )
                    boxes.append(box)
            
            results[term] = boxes
        
        return results
    
    def clear_cache(self) -> None:
        """Clear the document cache."""
        for key, doc in self._cache.items():
            if hasattr(doc, 'close'):
                doc.close()
        self._cache.clear()