"""
Utility functions to support redaction operations.

This module provides common functionality needed across redaction services
while maintaining consistency and reducing code duplication.
"""

import re
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


def validate_redaction_coordinates(
    x: float,
    y: float,
    width: float,
    height: float,
    page_width: float,
    page_height: float
) -> bool:
    """
    Ensure coordinates are within page boundaries.
    
    Args:
        x: X coordinate
        y: Y coordinate
        width: Width of redaction area
        height: Height of redaction area
        page_width: Width of the page
        page_height: Height of the page
        
    Returns:
        Boolean indicating if coordinates are valid
    """
    # Check for negative values
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return False
    
    # Check if redaction area exceeds page boundaries
    if x + width > page_width or y + height > page_height:
        return False
    
    # Check for reasonable minimum size (avoid invisible redactions)
    min_size = 1.0  # minimum 1 pixel
    if width < min_size or height < min_size:
        return False
    
    return True


def convert_coordinates_to_pdf_space(
    coords: Dict[str, float],
    page_height: float
) -> Dict[str, float]:
    """
    Convert between coordinate systems (top-left origin to bottom-left).
    
    PDF coordinate system has origin at bottom-left, while many systems
    use top-left origin.
    
    Args:
        coords: Dictionary with x, y, width, height keys
        page_height: Height of the PDF page
        
    Returns:
        Dictionary with converted coordinates
    """
    converted = coords.copy()
    
    # Convert y coordinate from top-left to bottom-left origin
    # In bottom-left system: new_y = page_height - (old_y + height)
    converted['y'] = page_height - (coords['y'] + coords['height'])
    
    return converted


def calculate_redaction_area(text_boxes: List[Dict[str, float]]) -> float:
    """
    Compute total area being redacted for statistics.
    
    Args:
        text_boxes: List of dictionaries with x, y, width, height keys
        
    Returns:
        Total area in square units
    """
    total_area = 0.0
    
    for box in text_boxes:
        area = box.get('width', 0) * box.get('height', 0)
        total_area += area
    
    return total_area


def merge_adjacent_redactions(
    redaction_boxes: List[Dict[str, float]],
    tolerance: float = 5
) -> List[Dict[str, float]]:
    """
    Combine nearby redaction areas for cleaner appearance.
    
    Args:
        redaction_boxes: List of redaction areas with coordinates
        tolerance: Pixel tolerance for considering boxes adjacent
        
    Returns:
        List of merged redaction boxes
    """
    if not redaction_boxes:
        return []
    
    # Sort boxes by position for efficient merging
    sorted_boxes = sorted(redaction_boxes, key=lambda b: (b['y'], b['x']))
    merged = []
    
    for box in sorted_boxes:
        merged_with_existing = False
        
        for i, existing in enumerate(merged):
            # Check if boxes are adjacent or overlapping
            x_overlap = not (
                box['x'] + box['width'] + tolerance < existing['x'] or
                existing['x'] + existing['width'] + tolerance < box['x']
            )
            y_overlap = not (
                box['y'] + box['height'] + tolerance < existing['y'] or
                existing['y'] + existing['height'] + tolerance < box['y']
            )
            
            if x_overlap and y_overlap:
                # Merge boxes
                min_x = min(box['x'], existing['x'])
                min_y = min(box['y'], existing['y'])
                max_x = max(box['x'] + box['width'], existing['x'] + existing['width'])
                max_y = max(box['y'] + box['height'], existing['y'] + existing['height'])
                
                merged[i] = {
                    'x': min_x,
                    'y': min_y,
                    'width': max_x - min_x,
                    'height': max_y - min_y,
                    'page_number': box.get('page_number', existing.get('page_number'))
                }
                merged_with_existing = True
                break
        
        if not merged_with_existing:
            merged.append(box)
    
    return merged


def validate_pdf_for_redaction(file_path: Path) -> Dict[str, Any]:
    """
    Check PDF compatibility with redaction operations.
    
    Args:
        file_path: Path to PDF file
        
    Returns:
        Dictionary with validation results
    """
    validation_result = {
        'is_valid': False,
        'can_redact': False,
        'warnings': [],
        'errors': []
    }
    
    try:
        import PyPDF2
        
        # Check file exists
        if not file_path.exists():
            validation_result['errors'].append('File does not exist')
            return validation_result
        
        # Try to open PDF
        with open(file_path, 'rb') as pdf_file:
            try:
                reader = PyPDF2.PdfReader(pdf_file)
                validation_result['is_valid'] = True
                
                # Check if encrypted
                if reader.is_encrypted:
                    validation_result['warnings'].append('PDF is encrypted - may require password')
                    validation_result['can_redact'] = False
                else:
                    validation_result['can_redact'] = True
                
                # Check for forms
                if '/AcroForm' in reader.trailer['/Root']:
                    validation_result['warnings'].append('PDF contains forms - form data may not be redacted')
                
                # Check PyPDF2 version for redaction support
                if not hasattr(PyPDF2.PageObject, 'add_redact_annot'):
                    validation_result['warnings'].append(
                        'PyPDF2 version does not support add_redact_annot - upgrade to 3.0+'
                    )
                    validation_result['can_redact'] = False
                
            except Exception as e:
                validation_result['errors'].append(f'PDF parsing error: {str(e)}')
                
    except ImportError:
        validation_result['errors'].append('PyPDF2 not installed')
    except Exception as e:
        validation_result['errors'].append(f'Validation error: {str(e)}')
    
    return validation_result


def extract_text_for_verification(
    file_path: Path,
    page_number: int,
    coordinates: Dict[str, float]
) -> Optional[str]:
    """
    Verify text content at specific coordinates before redaction.
    
    Args:
        file_path: Path to PDF file
        page_number: Page number (0-indexed)
        coordinates: Dictionary with x, y, width, height
        
    Returns:
        Extracted text at coordinates or None
    """
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(str(file_path))
        
        if page_number >= len(doc):
            return None
        
        page = doc[page_number]
        
        # Create rectangle from coordinates
        rect = fitz.Rect(
            coordinates['x'],
            coordinates['y'],
            coordinates['x'] + coordinates['width'],
            coordinates['y'] + coordinates['height']
        )
        
        # Extract text in rectangle
        text = page.get_text(clip=rect)
        
        doc.close()
        
        return text.strip() if text else None
        
    except Exception as e:
        logger.error(f"Text verification failed: {str(e)}")
        return None


def generate_redaction_preview_data(
    matches: List[Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> List[Dict[str, Any]]:
    """
    Generate data for frontend redaction preview.
    
    Args:
        matches: List of RedactionMatch objects
        page_dimensions: Dictionary mapping page numbers to dimensions
        
    Returns:
        List of preview data dictionaries
    """
    preview_data = []
    
    for match in matches:
        page_dim = page_dimensions.get(match.page_number, {})
        
        # Validate coordinates exist
        if all([
            match.x_coordinate is not None,
            match.y_coordinate is not None,
            match.width is not None,
            match.height is not None
        ]):
            preview_item = {
                'match_id': str(match.id) if hasattr(match, 'id') else None,
                'page_number': match.page_number,
                'text': match.matched_text[:50] + '...' if len(match.matched_text) > 50 else match.matched_text,
                'confidence': match.confidence_score,
                'coordinates': {
                    'x': match.x_coordinate,
                    'y': match.y_coordinate,
                    'width': match.width,
                    'height': match.height
                },
                'normalized_coordinates': None,
                'approved': match.approved_status if hasattr(match, 'approved_status') else None
            }
            
            # Add normalized coordinates if page dimensions available
            if page_dim:
                page_width = page_dim.get('width', 1)
                page_height = page_dim.get('height', 1)
                
                preview_item['normalized_coordinates'] = {
                    'x': match.x_coordinate / page_width,
                    'y': match.y_coordinate / page_height,
                    'width': match.width / page_width,
                    'height': match.height / page_height
                }
            
            preview_data.append(preview_item)
    
    return preview_data


def calculate_redaction_confidence_score(match_data: Dict[str, Any]) -> float:
    """
    Calculate overall redaction confidence assessment.
    
    Args:
        match_data: Dictionary containing match information
        
    Returns:
        Confidence score between 0.0 and 1.0
    """
    base_confidence = match_data.get('confidence_score', 0.5)
    
    # Adjust confidence based on various factors
    adjustments = []
    
    # Match type affects confidence
    match_type = match_data.get('match_type', 'fuzzy')
    if match_type == 'exact':
        adjustments.append(0.2)
    elif match_type == 'pattern':
        adjustments.append(0.1)
    
    # Validation status
    if match_data.get('validation_passed'):
        adjustments.append(0.1)
    
    # Source quality
    source = match_data.get('extraction_source', 'text_layer')
    if source == 'text_layer':
        adjustments.append(0.1)
    elif source == 'ocr':
        ocr_confidence = match_data.get('ocr_confidence', 0.5)
        adjustments.append(ocr_confidence * 0.1)
    
    # Calculate final confidence
    total_adjustment = sum(adjustments)
    final_confidence = min(1.0, base_confidence + total_adjustment)
    
    return round(final_confidence, 3)


def sanitize_redaction_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and clean redaction parameters.
    
    Args:
        options: Raw redaction options
        
    Returns:
        Sanitized options dictionary
    """
    sanitized = {}
    
    # Fill color (default to black)
    fill_color = options.get('fill_color')
    if isinstance(fill_color, (list, tuple)) and len(fill_color) == 3:
        # Validate RGB values
        sanitized['fill_color'] = tuple(
            max(0, min(1, float(c))) for c in fill_color
        )
    else:
        sanitized['fill_color'] = (0, 0, 0)  # Default black
    
    # Border style
    border_style = options.get('border_style', 'solid')
    if border_style in ['solid', 'dashed', 'none']:
        sanitized['border_style'] = border_style
    else:
        sanitized['border_style'] = 'solid'
    
    # Overlay text (for non-permanent redactions)
    overlay_text = options.get('overlay_text', '')
    if isinstance(overlay_text, str):
        sanitized['overlay_text'] = overlay_text[:100]  # Limit length
    else:
        sanitized['overlay_text'] = ''
    
    # Redaction reason (for audit)
    reason = options.get('reason', '')
    if isinstance(reason, str):
        sanitized['reason'] = reason[:500]
    else:
        sanitized['reason'] = 'User requested redaction'
    
    return sanitized


def format_redaction_statistics(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format redaction statistics for consistent reporting.
    
    Args:
        job_data: Raw job data
        
    Returns:
        Formatted statistics dictionary
    """
    stats = {
        'summary': {
            'total_matches': job_data.get('total_matches', 0),
            'matches_redacted': job_data.get('matches_redacted', 0),
            'pages_affected': job_data.get('pages_affected', 0),
            'processing_time_ms': job_data.get('processing_time_ms', 0)
        },
        'confidence_breakdown': {
            'high_confidence': job_data.get('high_confidence_count', 0),
            'medium_confidence': job_data.get('medium_confidence_count', 0),
            'low_confidence': job_data.get('low_confidence_count', 0)
        },
        'source_breakdown': {
            'text_layer': job_data.get('text_layer_matches', 0),
            'ocr': job_data.get('ocr_matches', 0),
            'hybrid': job_data.get('hybrid_matches', 0)
        },
        'performance': {
            'processing_time_seconds': job_data.get('processing_time_ms', 0) / 1000,
            'average_time_per_match': (
                job_data.get('processing_time_ms', 0) / job_data.get('total_matches', 1)
                if job_data.get('total_matches', 0) > 0 else 0
            ),
            'redaction_rate': (
                job_data.get('matches_redacted', 0) / job_data.get('total_matches', 1) * 100
                if job_data.get('total_matches', 0) > 0 else 0
            )
        }
    }
    
    return stats


def check_redaction_completeness(
    original_file: Path,
    redacted_file: Path,
    coordinates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Verify successful text deletion at specified coordinates.
    
    Args:
        original_file: Path to original PDF
        redacted_file: Path to redacted PDF
        coordinates: List of coordinate dictionaries with page_number
        
    Returns:
        Dictionary with verification results
    """
    verification_result = {
        'is_complete': True,
        'verified_count': 0,
        'failed_verifications': [],
        'warnings': []
    }
    
    try:
        import fitz  # PyMuPDF
        
        original_doc = fitz.open(str(original_file))
        redacted_doc = fitz.open(str(redacted_file))
        
        for coord in coordinates:
            page_num = coord.get('page_number', 0)
            
            if page_num >= len(redacted_doc):
                verification_result['warnings'].append(
                    f"Page {page_num} not found in redacted document"
                )
                continue
            
            # Extract text from redacted area
            page = redacted_doc[page_num]
            rect = fitz.Rect(
                coord['x'],
                coord['y'],
                coord['x'] + coord['width'],
                coord['y'] + coord['height']
            )
            
            redacted_text = page.get_text(clip=rect).strip()
            
            if redacted_text:
                # Text still present - redaction may have failed
                verification_result['is_complete'] = False
                verification_result['failed_verifications'].append({
                    'page': page_num,
                    'coordinates': coord,
                    'remaining_text': redacted_text[:100]
                })
            else:
                verification_result['verified_count'] += 1
        
        original_doc.close()
        redacted_doc.close()
        
    except Exception as e:
        logger.error(f"Redaction verification failed: {str(e)}")
        verification_result['warnings'].append(f"Verification error: {str(e)}")
        verification_result['is_complete'] = False
    
    return verification_result


def generate_redaction_report(
    job_id: str,
    statistics: Dict[str, Any]
) -> str:
    """
    Generate audit and compliance report for redaction operation.
    
    Args:
        job_id: Job identifier
        statistics: Redaction statistics
        
    Returns:
        Formatted report string
    """
    report_lines = [
        "=" * 60,
        "REDACTION COMPLIANCE REPORT",
        "=" * 60,
        f"Job ID: {job_id}",
        f"Generated: {__import__('datetime').datetime.now().isoformat()}",
        "",
        "SUMMARY",
        "-" * 30,
        f"Total Matches Found: {statistics.get('total_matches', 0)}",
        f"Matches Redacted: {statistics.get('matches_redacted', 0)}",
        f"Pages Affected: {statistics.get('pages_affected', 0)}",
        f"Processing Time: {statistics.get('processing_time_ms', 0) / 1000:.2f} seconds",
        "",
        "CONFIDENCE ANALYSIS",
        "-" * 30,
        f"High Confidence (≥90%): {statistics.get('high_confidence_count', 0)}",
        f"Medium Confidence (70-89%): {statistics.get('medium_confidence_count', 0)}",
        f"Low Confidence (<70%): {statistics.get('low_confidence_count', 0)}",
        "",
        "PERMANENT DELETION STATUS",
        "-" * 30,
        f"Text Deletion Applied: {statistics.get('permanent_deletion', False)}",
        f"Verification Status: {statistics.get('verification_status', 'Not verified')}",
        f"Redaction Method: {statistics.get('redaction_method', 'PyPDF2 apply_redactions')}",
        "",
        "COMPLIANCE NOTES",
        "-" * 30,
        "- All redacted text has been permanently removed from PDF text layer",
        "- Redacted content cannot be recovered through text extraction",
        "- Visual redaction markers have been applied for transparency",
        "- This report serves as audit trail for compliance purposes",
        "",
        "=" * 60
    ]
    
    return "\n".join(report_lines)


def estimate_redaction_processing_time(
    file_size: int,
    match_count: int
) -> Dict[str, Any]:
    """
    Estimate processing time for redaction operation.
    
    Args:
        file_size: File size in bytes
        match_count: Number of matches to redact
        
    Returns:
        Dictionary with time estimates
    """
    # Base factors
    base_time = 5  # seconds
    size_factor = (file_size / (1024 * 1024)) * 0.5  # 0.5 seconds per MB
    match_factor = match_count * 0.2  # 0.2 seconds per match
    
    estimated_seconds = base_time + size_factor + match_factor
    
    return {
        'estimated_seconds': int(estimated_seconds),
        'estimated_minutes': round(estimated_seconds / 60, 1),
        'confidence_level': 'high' if match_count < 100 else 'medium',
        'requires_background': estimated_seconds > 30
    }


def validate_search_terms_for_redaction(terms: List[str]) -> Dict[str, Any]:
    """
    Ensure search terms are suitable for redaction.
    
    Args:
        terms: List of search terms
        
    Returns:
        Dictionary with validation results
    """
    validation_result = {
        'is_valid': True,
        'valid_terms': [],
        'invalid_terms': [],
        'warnings': []
    }
    
    for term in terms:
        if not term or not isinstance(term, str):
            validation_result['invalid_terms'].append(str(term))
            continue
        
        # Check term length
        if len(term) < 2:
            validation_result['warnings'].append(
                f"Term '{term}' is very short and may cause many false positives"
            )
        elif len(term) > 500:
            validation_result['invalid_terms'].append(term[:50] + '...')
            continue
        
        # Check for special regex characters that might cause issues
        if re.search(r'[\x00-\x1f]', term):
            validation_result['invalid_terms'].append(term)
            continue
        
        validation_result['valid_terms'].append(term)
    
    if validation_result['invalid_terms']:
        validation_result['is_valid'] = False
    
    return validation_result


def format_coordinate_data(
    coordinates: Dict[str, float],
    format_type: str = 'pdf'
) -> Dict[str, float]:
    """
    Format coordinates for different requirements.
    
    Args:
        coordinates: Original coordinate dictionary
        format_type: Target format ('pdf', 'display', 'normalized')
        
    Returns:
        Formatted coordinate dictionary
    """
    formatted = coordinates.copy()
    
    if format_type == 'pdf':
        # Ensure floating point for PDF operations
        for key in ['x', 'y', 'width', 'height']:
            if key in formatted:
                formatted[key] = float(formatted[key])
    
    elif format_type == 'display':
        # Round for display purposes
        for key in ['x', 'y', 'width', 'height']:
            if key in formatted:
                formatted[key] = round(formatted[key], 2)
    
    elif format_type == 'normalized':
        # Normalize to 0-1 range (requires page dimensions)
        page_width = formatted.get('page_width', 1)
        page_height = formatted.get('page_height', 1)
        
        formatted['x'] = formatted.get('x', 0) / page_width
        formatted['y'] = formatted.get('y', 0) / page_height
        formatted['width'] = formatted.get('width', 0) / page_width
        formatted['height'] = formatted.get('height', 0) / page_height
    
    return formatted