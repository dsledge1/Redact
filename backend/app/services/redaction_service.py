"""
RedactionService: Implements permanent text-layer redaction using PyPDF2.

This service provides comprehensive functionality for permanently removing text
from PDF documents, ensuring complete deletion rather than visual overlays.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import tempfile
import traceback

import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import RectangleObject

from app.models import RedactionMatch, ProcessingJob, OCRResult
from app.services.temp_file_manager import TempFileManager
from app.services.bounding_box_calculator import BoundingBoxCalculator
from app.utils.errors import (
    PDFProcessingError,
    RedactionError,
    FileNotFoundError as CustomFileNotFoundError
)

logger = logging.getLogger(__name__)


class RedactionService:
    """Service for performing permanent text-layer redaction on PDF documents."""
    
    def __init__(self, session_id: str):
        """
        Initialize the RedactionService with session-specific file management.
        
        Args:
            session_id: Unique session identifier for file management
        """
        self.session_id = session_id
        self.temp_file_manager = TempFileManager(session_id)
        self.logger = logger
        
    def redact_pdf(
        self, 
        file_path: Path, 
        matches: List[RedactionMatch],
        **options
    ) -> Dict[str, Any]:
        """
        Main entry point for PDF redaction operations.
        
        Args:
            file_path: Path to the PDF file to redact
            matches: List of RedactionMatch objects with coordinates
            **options: Additional redaction options (fill_color, border_style, etc.)
            
        Returns:
            Dictionary containing:
                - success: Boolean indicating operation success
                - output_path: Path to redacted PDF
                - statistics: Redaction statistics
                - errors: Any errors encountered
        """
        start_time = datetime.now()
        statistics = {
            'total_matches': len(matches),
            'pages_affected': 0,
            'redactions_applied': 0,
            'processing_time_ms': 0
        }
        
        try:
            # Validate input
            self._validate_redaction_input(file_path, matches)
            
            # Ensure all matches have bounding boxes
            validated_matches = self._ensure_bounding_boxes(matches, file_path)
            
            # Group matches by page
            matches_by_page = self._group_matches_by_page(validated_matches)
            statistics['pages_affected'] = len(matches_by_page)
            
            # Create output file path
            output_path = self.temp_file_manager.get_download_path(
                f"redacted_{file_path.name}"
            )
            
            # Apply redactions
            success = self._apply_redactions(
                file_path, 
                output_path, 
                matches_by_page,
                options
            )
            
            if success:
                # Update match records
                self._update_match_records(validated_matches)
                statistics['redactions_applied'] = len(validated_matches)
                
                # Verify redactions were applied
                self._verify_redactions(file_path, output_path, validated_matches)
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            statistics['processing_time_ms'] = int(processing_time)
            
            return {
                'success': success,
                'output_path': str(output_path),
                'statistics': statistics,
                'errors': []
            }
            
        except Exception as e:
            self.logger.error(f"Redaction failed: {str(e)}\n{traceback.format_exc()}")
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            statistics['processing_time_ms'] = int(processing_time)
            
            return {
                'success': False,
                'output_path': None,
                'statistics': statistics,
                'errors': [str(e)]
            }
    
    def _validate_redaction_input(
        self, 
        file_path: Path, 
        matches: List[RedactionMatch]
    ) -> None:
        """
        Validate PDF file and redaction matches.
        
        Args:
            file_path: Path to PDF file
            matches: List of redaction matches
            
        Raises:
            CustomFileNotFoundError: If file doesn't exist
            PDFProcessingError: If PDF is invalid
            RedactionError: If matches are invalid
        """
        if not file_path.exists():
            raise CustomFileNotFoundError(f"PDF file not found: {file_path}")
            
        if not matches:
            raise RedactionError("No redaction matches provided")
            
        # Validate PDF can be opened
        try:
            with open(file_path, 'rb') as pdf_file:
                PdfReader(pdf_file)
        except Exception as e:
            raise PDFProcessingError(f"Invalid PDF file: {str(e)}")
    
    def _group_matches_by_page(
        self, 
        matches: List[RedactionMatch]
    ) -> Dict[int, List[RedactionMatch]]:
        """
        Group matches by page number for efficient processing.
        
        Args:
            matches: List of redaction matches
            
        Returns:
            Dictionary mapping page numbers to matches
        """
        matches_by_page = {}
        for match in matches:
            page_num = match.page_number
            if page_num not in matches_by_page:
                matches_by_page[page_num] = []
            matches_by_page[page_num].append(match)
        
        return matches_by_page
    
    def _ensure_bounding_boxes(
        self, 
        matches: List[RedactionMatch],
        pdf_path: Optional[Path] = None
    ) -> List[RedactionMatch]:
        """
        Validate and compute missing bounding box coordinates using BoundingBoxCalculator.
        
        Args:
            matches: List of redaction matches
            pdf_path: Path to PDF file for coordinate calculation
            
        Returns:
            List of matches with validated coordinates
        """
        validated_matches = []
        calculator = BoundingBoxCalculator()
        
        try:
            for match in matches:
                # Check if coordinates already exist and are valid
                if self._has_valid_coordinates(match):
                    validated_matches.append(match)
                    continue
                
                # Log attempt to calculate missing coordinates
                self.logger.info(
                    f"Match {match.id} missing coordinates, attempting calculation for text: '{match.matched_text[:50]}...'"
                )
                
                # Attempt coordinate calculation
                best_box = self._calculate_best_bounding_box(
                    calculator, match, pdf_path
                )
                
                if best_box:
                    # Attach computed coordinates to the match
                    self._attach_coordinates_to_match(match, best_box)
                    
                    # Persist the updated match
                    try:
                        match.save()
                        self.logger.debug(f"Successfully calculated and saved coordinates for match {match.id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to save calculated coordinates for match {match.id}: {str(e)}")
                    
                    validated_matches.append(match)
                else:
                    self.logger.warning(
                        f"Could not calculate coordinates for match {match.id} with text: '{match.matched_text[:50]}...'"
                    )
                    # Skip matches without calculable coordinates
                    continue
                    
        finally:
            # Clean up calculator cache
            calculator.clear_cache()
                
        return validated_matches
    
    def _has_valid_coordinates(self, match: RedactionMatch) -> bool:
        """
        Check if match has valid coordinates.
        
        Args:
            match: RedactionMatch to validate
            
        Returns:
            Boolean indicating if coordinates are valid
        """
        return all([
            match.x_coordinate is not None,
            match.y_coordinate is not None,
            match.width is not None,
            match.height is not None,
            match.width > 0,
            match.height > 0
        ])
    
    def _calculate_best_bounding_box(
        self, 
        calculator: BoundingBoxCalculator, 
        match: RedactionMatch,
        pdf_path: Optional[Path]
    ) -> Optional['BoundingBox']:
        """
        Calculate the best bounding box for a match using multiple methods.
        
        Args:
            calculator: BoundingBoxCalculator instance
            match: RedactionMatch without coordinates
            pdf_path: Path to PDF file
            
        Returns:
            Best BoundingBox found or None if no suitable box found
        """
        if not pdf_path:
            self.logger.warning("No PDF path provided for coordinate calculation")
            return None
            
        all_boxes = []
        
        # Method 1: Text layer search
        try:
            text_layer_boxes = calculator.calculate_text_layer_boxes(
                str(pdf_path), 
                match.matched_text, 
                page_number=match.page_number
            )
            all_boxes.extend(text_layer_boxes)
            self.logger.debug(f"Found {len(text_layer_boxes)} boxes from text layer for match {match.id}")
        except Exception as e:
            self.logger.debug(f"Text layer calculation failed for match {match.id}: {str(e)}")
        
        # Method 2: Fallback calculation if text layer failed
        if not all_boxes:
            try:
                fallback_boxes = calculator.calculate_fallback_boxes(
                    str(pdf_path),
                    match.matched_text,
                    match.page_number
                )
                all_boxes.extend(fallback_boxes)
                self.logger.debug(f"Found {len(fallback_boxes)} boxes from fallback method for match {match.id}")
            except Exception as e:
                self.logger.debug(f"Fallback calculation failed for match {match.id}: {str(e)}")
        
        # Method 3: OCR boxes if available and other methods failed
        if not all_boxes:
            try:
                ocr_boxes = self._get_ocr_boxes(calculator, match)
                all_boxes.extend(ocr_boxes)
                self.logger.debug(f"Found {len(ocr_boxes)} boxes from OCR for match {match.id}")
            except Exception as e:
                self.logger.debug(f"OCR calculation failed for match {match.id}: {str(e)}")
        
        if not all_boxes:
            return None
            
        # Choose the best box (highest confidence)
        best_box = max(all_boxes, key=lambda box: box.confidence)
        
        # Expand margins for better coverage
        try:
            # Get page dimensions for margin expansion validation
            import fitz
            doc = fitz.open(str(pdf_path))
            page = doc[match.page_number]
            page_dimensions = {
                'width': page.rect.width,
                'height': page.rect.height
            }
            doc.close()
            
            best_box = calculator.expand_box_margins(
                best_box, 
                margin_pixels=2.0,
                page_dimensions=page_dimensions
            )
        except Exception as e:
            self.logger.warning(f"Failed to expand margins for match {match.id}: {str(e)}")
        
        # Validate coordinates
        if self._validate_box_coordinates(best_box, pdf_path):
            return best_box
        else:
            self.logger.warning(f"Best box coordinates failed validation for match {match.id}")
            return None
    
    def _get_ocr_boxes(
        self, 
        calculator: BoundingBoxCalculator, 
        match: RedactionMatch
    ) -> List['BoundingBox']:
        """
        Get bounding boxes from OCR results if available.
        
        Args:
            calculator: BoundingBoxCalculator instance
            match: RedactionMatch to find OCR boxes for
            
        Returns:
            List of BoundingBox objects from OCR data
        """
        try:
            # Find OCR results for this document and page
            ocr_results = OCRResult.objects.filter(
                document=match.document,
                page_number=match.page_number
            ).order_by('-confidence_score')
            
            if not ocr_results.exists():
                return []
            
            # Use the highest confidence OCR result
            best_ocr_result = ocr_results.first()
            return calculator.calculate_ocr_boxes(best_ocr_result, match.matched_text)
            
        except Exception as e:
            self.logger.error(f"Error retrieving OCR boxes for match {match.id}: {str(e)}")
            return []
    
    def _validate_box_coordinates(
        self, 
        box: 'BoundingBox', 
        pdf_path: Path
    ) -> bool:
        """
        Validate bounding box coordinates against PDF page dimensions.
        
        Args:
            box: BoundingBox to validate
            pdf_path: Path to PDF file
            
        Returns:
            Boolean indicating if coordinates are valid
        """
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            
            if box.page_number >= len(doc):
                doc.close()
                return False
                
            page = doc[box.page_number]
            page_dimensions = {
                'width': page.rect.width,
                'height': page.rect.height
            }
            doc.close()
            
            # Use calculator's validation method
            calculator = BoundingBoxCalculator()
            return calculator.validate_coordinates(
                box.x, box.y, box.width, box.height, page_dimensions
            )
            
        except Exception as e:
            self.logger.error(f"Error validating box coordinates: {str(e)}")
            return False
    
    def _attach_coordinates_to_match(
        self, 
        match: RedactionMatch, 
        box: 'BoundingBox'
    ) -> None:
        """
        Attach calculated coordinates to a RedactionMatch instance.
        
        Args:
            match: RedactionMatch to update
            box: BoundingBox with calculated coordinates
        """
        match.x_coordinate = box.x
        match.y_coordinate = box.y
        match.width = box.width
        match.height = box.height
        
        # Update confidence breakdown to reflect coordinate calculation
        if not match.confidence_breakdown:
            match.confidence_breakdown = {}
        
        match.confidence_breakdown.update({
            'coordinate_source': box.source,
            'coordinate_confidence': box.confidence,
            'calculation_method': 'BoundingBoxCalculator'
        })
    
    def _apply_redactions(
        self,
        input_path: Path,
        output_path: Path,
        matches_by_page: Dict[int, List[RedactionMatch]],
        options: Dict[str, Any]
    ) -> bool:
        """
        Apply permanent redactions to PDF using PyPDF2.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output PDF
            matches_by_page: Matches grouped by page number
            options: Redaction appearance options
            
        Returns:
            Boolean indicating success
        """
        try:
            # Read the PDF
            with open(input_path, 'rb') as pdf_file:
                reader = PdfReader(pdf_file)
                writer = PdfWriter()
                
                # Process each page
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    
                    # Check if this page has redactions
                    if page_num in matches_by_page:
                        # Apply redaction annotations
                        for match in matches_by_page[page_num]:
                            self._apply_page_redaction(page, match, options)
                        
                        # Finalize redactions (permanent text deletion)
                        self._finalize_redactions(page)
                    
                    # Add page to writer
                    writer.add_page(page)
                
                # Save the redacted PDF
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply redactions: {str(e)}")
            return False
    
    def _apply_page_redaction(
        self,
        page: PyPDF2.PageObject,
        match: RedactionMatch,
        options: Dict[str, Any]
    ) -> None:
        """
        Apply redaction annotation to a page.
        
        Args:
            page: PDF page object
            match: RedactionMatch with coordinates
            options: Redaction appearance options
        """
        try:
            # Import redaction utilities
            from app.utils.redaction_utils import validate_redaction_coordinates
            
            # Compute page height from mediabox
            page_height = float(page.mediabox.top) - float(page.mediabox.bottom)
            page_width = float(page.mediabox.right) - float(page.mediabox.left)
            
            # Convert coordinates to PDF bottom-left space
            x = match.x_coordinate
            width = match.width
            height = match.height
            y_pdf = page_height - (match.y_coordinate + match.height)
            
            # Validate coordinates against page bounds
            if not validate_redaction_coordinates(x, y_pdf, width, height, page_width, page_height):
                self.logger.warning(
                    f"Redaction coordinates out of bounds for match {match.id}, "
                    f"x={x}, y={y_pdf}, w={width}, h={height}, page={page_width}x{page_height}"
                )
                return
            
            # Build rectangle using converted coordinates
            x1, y1 = x, y_pdf
            x2 = x1 + width
            y2 = y1 + height
            
            # Create rectangle for redaction area
            rect = RectangleObject([x1, y1, x2, y2])
            
            # Apply redaction annotation
            # Note: PyPDF2 3.0+ supports add_redact_annot
            if hasattr(page, 'add_redact_annot'):
                # Get fill color from options or use default black
                fill_color = options.get('fill_color', (0, 0, 0))
                
                # Add redaction annotation
                page.add_redact_annot(
                    rect=rect,
                    fill_color=fill_color,
                    text=""  # Empty text to remove content
                )
            else:
                raise RedactionError(
                    "Unsupported PyPDF2 version: permanent redaction cannot be performed. "
                    "The add_redact_annot method is not available in this PyPDF2 version."
                )
                
        except Exception as e:
            self.logger.error(f"Failed to apply redaction annotation: {str(e)}")
            raise RedactionError(f"Redaction annotation failed: {str(e)}")
    
    def _finalize_redactions(self, page: PyPDF2.PageObject) -> None:
        """
        Finalize redactions for permanent text deletion.
        
        Args:
            page: PDF page with redaction annotations
        """
        try:
            # Apply redactions for permanent deletion
            # Note: PyPDF2 3.0+ supports apply_redactions
            if hasattr(page, 'apply_redactions'):
                page.apply_redactions()
                self.logger.debug("Redactions permanently applied to page")
            else:
                raise RedactionError(
                    "Unsupported PyPDF2 version: permanent redaction cannot be performed. "
                    "The apply_redactions method is not available in this PyPDF2 version."
                )
        except Exception as e:
            self.logger.error(f"Failed to finalize redactions: {str(e)}")
            raise RedactionError(f"Redaction finalization failed: {str(e)}")
    
    def _add_overlay_rectangle(
        self,
        page: PyPDF2.PageObject,
        rect: RectangleObject,
        options: Dict[str, Any]
    ) -> None:
        """
        Raises RedactionError indicating unsupported PyPDF2 version.
        
        Args:
            page: PDF page object
            rect: Rectangle coordinates
            options: Appearance options
            
        Raises:
            RedactionError: Always raises to indicate permanent redaction cannot be performed
        """
        raise RedactionError(
            "Unsupported PyPDF2 version: permanent redaction cannot be performed. "
            "This method would only create a visual overlay, leaving text recoverable."
        )
    
    def _update_match_records(self, matches: List[RedactionMatch]) -> None:
        """
        Update RedactionMatch records to mark as redacted.
        
        Args:
            matches: List of processed matches
        """
        for match in matches:
            try:
                match.redacted = True
                match.redaction_applied_at = datetime.now()
                match.save()
            except Exception as e:
                self.logger.error(f"Failed to update match {match.id}: {str(e)}")
    
    def _verify_redactions(
        self, 
        original_path: Path,
        output_path: Path, 
        matches: List[RedactionMatch]
    ) -> bool:
        """
        Verify that redactions were successfully applied.
        
        Args:
            original_path: Path to original PDF
            output_path: Path to redacted PDF
            matches: List of redaction matches
            
        Returns:
            Boolean indicating verification success
        """
        try:
            with open(output_path, 'rb') as pdf_file:
                reader = PdfReader(pdf_file)
                
                # Build coordinates list from matches (after converting to PDF space)
                coordinates = []
                
                for match in matches:
                    # Validate page number bounds with graceful logging
                    if match.page_number >= len(reader.pages):
                        self.logger.warning(
                            f"Match page number {match.page_number} exceeds PDF page count {len(reader.pages)}, skipping"
                        )
                        continue
                    
                    page = reader.pages[match.page_number]
                    page_text = page.extract_text() or ''  # Coalesce to empty string
                    
                    # Compute page height from mediabox for coordinate conversion
                    page_height = float(page.mediabox.top) - float(page.mediabox.bottom)
                    
                    # Convert coordinates to PDF space (bottom-left origin)
                    y_pdf = page_height - (match.y_coordinate + match.height)
                    
                    coordinates.append({
                        'page_number': match.page_number,
                        'x': match.x_coordinate,
                        'y': y_pdf,
                        'width': match.width,
                        'height': match.height
                    })
                
                # Call redaction_utils.check_redaction_completeness
                from app.utils.redaction_utils import check_redaction_completeness
                verification_result = check_redaction_completeness(
                    original_file=original_path,
                    redacted_file=output_path,
                    coordinates=coordinates
                )
                
                # Return True only if is_complete is True
                if verification_result['is_complete']:
                    self.logger.info("Redaction verification completed successfully")
                    return True
                else:
                    self.logger.warning(
                        f"Redaction verification failed. Verified: {verification_result['verified_count']}, "
                        f"Failed: {len(verification_result['failed_verifications'])}"
                    )
                    return False
            
        except Exception as e:
            self.logger.error(f"Redaction verification failed: {str(e)}")
            return False
    
    def _calculate_redaction_statistics(
        self,
        matches: List[RedactionMatch],
        processing_time: float
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive redaction statistics.
        
        Args:
            matches: List of redaction matches
            processing_time: Processing time in milliseconds
            
        Returns:
            Dictionary of statistics
        """
        pages_affected = len(set(m.page_number for m in matches))
        
        return {
            'total_matches': len(matches),
            'pages_affected': pages_affected,
            'redactions_applied': len([m for m in matches if m.redacted]),
            'processing_time_ms': int(processing_time),
            'average_confidence': sum(m.confidence_score for m in matches) / len(matches) if matches else 0,
            'timestamp': datetime.now().isoformat()
        }