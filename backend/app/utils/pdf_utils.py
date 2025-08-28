"""PDF utility functions for splitting and merging operations."""

import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import re
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def calculate_split_statistics(
    source_file: Path, 
    output_files: List[Path]
) -> Dict[str, Any]:
    """Generate comprehensive split statistics.
    
    Args:
        source_file: Path to original source file
        output_files: List of output file paths from split operation
        
    Returns:
        Dictionary with comprehensive split statistics
    """
    try:
        if not source_file.exists():
            raise FileNotFoundError(f"Source file not found: {source_file}")
        
        source_size = source_file.stat().st_size
        source_reader = PdfReader(str(source_file))
        source_pages = len(source_reader.pages)
        
        # Analyze each output file
        output_stats = []
        total_output_size = 0
        total_output_pages = 0
        
        for i, output_file in enumerate(output_files):
            if not output_file.exists():
                logger.warning(f"Output file not found: {output_file}")
                continue
                
            try:
                output_size = output_file.stat().st_size
                output_reader = PdfReader(str(output_file))
                output_pages = len(output_reader.pages)
                
                # Calculate integrity hash
                file_hash = calculate_file_hash(output_file)
                
                # Calculate size efficiency
                size_ratio = (output_size / source_size) * 100 if source_size > 0 else 0
                page_ratio = (output_pages / source_pages) * 100 if source_pages > 0 else 0
                
                output_stats.append({
                    'file_index': i,
                    'filename': output_file.name,
                    'file_size': output_size,
                    'file_size_mb': round(output_size / (1024 * 1024), 2),
                    'page_count': output_pages,
                    'size_ratio_percent': round(size_ratio, 2),
                    'page_ratio_percent': round(page_ratio, 2),
                    'sha256_hash': file_hash,
                    'compression_efficiency': _calculate_compression_efficiency(
                        source_size, output_size, source_pages, output_pages
                    )
                })
                
                total_output_size += output_size
                total_output_pages += output_pages
                
            except Exception as e:
                logger.error(f"Error analyzing output file {output_file}: {str(e)}")
                output_stats.append({
                    'file_index': i,
                    'filename': output_file.name,
                    'error': str(e)
                })
        
        # Calculate overall statistics
        size_change = total_output_size - source_size
        size_change_percent = (size_change / source_size) * 100 if source_size > 0 else 0
        
        # Page integrity check
        page_integrity = total_output_pages == source_pages
        
        # Calculate split efficiency metrics
        split_efficiency = _calculate_split_efficiency(
            source_size, total_output_size, source_pages, total_output_pages, len(output_files)
        )
        
        statistics = {
            'source_file': {
                'path': str(source_file),
                'filename': source_file.name,
                'size': source_size,
                'size_mb': round(source_size / (1024 * 1024), 2),
                'pages': source_pages,
                'hash': calculate_file_hash(source_file)
            },
            'split_results': {
                'total_files_created': len(output_files),
                'successful_files': len([f for f in output_stats if 'error' not in f]),
                'failed_files': len([f for f in output_stats if 'error' in f]),
                'total_output_size': total_output_size,
                'total_output_size_mb': round(total_output_size / (1024 * 1024), 2),
                'total_output_pages': total_output_pages
            },
            'size_analysis': {
                'size_change_bytes': size_change,
                'size_change_mb': round(size_change / (1024 * 1024), 2),
                'size_change_percent': round(size_change_percent, 2),
                'size_increased': size_change > 0,
                'average_file_size': total_output_size // len(output_files) if output_files else 0
            },
            'integrity_analysis': {
                'page_integrity': page_integrity,
                'page_count_matches': total_output_pages == source_pages,
                'all_files_valid': all('error' not in f for f in output_stats),
                'integrity_score': _calculate_integrity_score(output_stats, page_integrity)
            },
            'efficiency_metrics': split_efficiency,
            'output_files': output_stats,
            'recommendations': _generate_split_recommendations(
                source_size, total_output_size, len(output_files), split_efficiency
            )
        }
        
        return statistics
        
    except Exception as e:
        logger.error(f"Error calculating split statistics: {str(e)}")
        return {
            'error': str(e),
            'source_file': str(source_file),
            'statistics_available': False
        }


def calculate_merge_statistics(
    source_files: List[Path], 
    output_file: Path
) -> Dict[str, Any]:
    """Generate comprehensive merge statistics and quality assessment.
    
    Args:
        source_files: List of source file paths
        output_file: Path to merged output file
        
    Returns:
        Dictionary with comprehensive merge statistics
    """
    try:
        if not output_file.exists():
            raise FileNotFoundError(f"Output file not found: {output_file}")
        
        # Analyze source files
        source_stats = []
        total_source_size = 0
        total_source_pages = 0
        
        for i, source_file in enumerate(source_files):
            if not source_file.exists():
                logger.warning(f"Source file not found: {source_file}")
                source_stats.append({
                    'file_index': i,
                    'filename': source_file.name,
                    'error': 'File not found'
                })
                continue
                
            try:
                source_size = source_file.stat().st_size
                source_reader = PdfReader(str(source_file))
                source_pages = len(source_reader.pages)
                
                source_stats.append({
                    'file_index': i,
                    'filename': source_file.name,
                    'file_size': source_size,
                    'file_size_mb': round(source_size / (1024 * 1024), 2),
                    'page_count': source_pages,
                    'sha256_hash': calculate_file_hash(source_file),
                    'has_metadata': bool(source_reader.metadata),
                    'is_encrypted': source_reader.is_encrypted
                })
                
                total_source_size += source_size
                total_source_pages += source_pages
                
            except Exception as e:
                logger.error(f"Error analyzing source file {source_file}: {str(e)}")
                source_stats.append({
                    'file_index': i,
                    'filename': source_file.name,
                    'error': str(e)
                })
        
        # Analyze output file
        output_size = output_file.stat().st_size
        output_reader = PdfReader(str(output_file))
        output_pages = len(output_reader.pages)
        
        # Calculate merge metrics
        size_change = output_size - total_source_size
        size_efficiency = (output_size / total_source_size) * 100 if total_source_size > 0 else 0
        compression_ratio = total_source_size / output_size if output_size > 0 else 1
        
        # Page integrity check
        page_integrity = output_pages == total_source_pages
        
        # Calculate merge quality metrics
        merge_quality = _calculate_merge_quality(
            source_stats, output_size, output_pages, total_source_size, total_source_pages
        )
        
        statistics = {
            'source_analysis': {
                'total_files': len(source_files),
                'valid_files': len([f for f in source_stats if 'error' not in f]),
                'failed_files': len([f for f in source_stats if 'error' in f]),
                'total_source_size': total_source_size,
                'total_source_size_mb': round(total_source_size / (1024 * 1024), 2),
                'total_source_pages': total_source_pages,
                'average_file_size': total_source_size // len(source_files) if source_files else 0,
                'files_with_metadata': len([f for f in source_stats if f.get('has_metadata', False)]),
                'encrypted_files': len([f for f in source_stats if f.get('is_encrypted', False)])
            },
            'output_analysis': {
                'filename': output_file.name,
                'file_size': output_size,
                'file_size_mb': round(output_size / (1024 * 1024), 2),
                'page_count': output_pages,
                'sha256_hash': calculate_file_hash(output_file),
                'has_metadata': bool(output_reader.metadata),
                'metadata_preserved': bool(output_reader.metadata) if any(f.get('has_metadata', False) for f in source_stats) else None
            },
            'merge_efficiency': {
                'size_change_bytes': size_change,
                'size_change_mb': round(size_change / (1024 * 1024), 2),
                'size_efficiency_percent': round(size_efficiency, 2),
                'compression_ratio': round(compression_ratio, 2),
                'compression_achieved': compression_ratio > 1.05,  # 5% threshold
                'space_saved_mb': round((total_source_size - output_size) / (1024 * 1024), 2) if size_change < 0 else 0
            },
            'integrity_analysis': {
                'page_integrity': page_integrity,
                'expected_pages': total_source_pages,
                'actual_pages': output_pages,
                'page_difference': output_pages - total_source_pages,
                'all_sources_valid': all('error' not in f for f in source_stats),
                'integrity_score': _calculate_merge_integrity_score(page_integrity, source_stats)
            },
            'quality_metrics': merge_quality,
            'source_files': source_stats,
            'recommendations': _generate_merge_recommendations(
                total_source_size, output_size, len(source_files), merge_quality
            )
        }
        
        return statistics
        
    except Exception as e:
        logger.error(f"Error calculating merge statistics: {str(e)}")
        return {
            'error': str(e),
            'output_file': str(output_file),
            'statistics_available': False
        }


def preserve_pdf_metadata(
    source_reader: PdfReader, 
    target_writer: PdfWriter, 
    preservation_strategy: str = 'comprehensive'
) -> Dict[str, Any]:
    """Preserve PDF metadata from source to target with different strategies.
    
    Args:
        source_reader: Source PDF reader
        target_writer: Target PDF writer
        preservation_strategy: Strategy for metadata preservation
        
    Returns:
        Dictionary with preservation results
    """
    try:
        preserved_items = []
        
        if preservation_strategy == 'comprehensive':
            # Copy document info dictionary
            if source_reader.metadata:
                target_writer.add_metadata(source_reader.metadata)
                preserved_items.append('document_info')
            
            # Copy viewer preferences if available
            if hasattr(source_reader, 'viewer_preferences'):
                try:
                    target_writer.viewer_preferences = source_reader.viewer_preferences
                    preserved_items.append('viewer_preferences')
                except Exception as e:
                    logger.warning(f"Could not preserve viewer preferences: {str(e)}")
            
            # Copy page layout and display preferences
            if hasattr(source_reader, 'page_layout'):
                try:
                    target_writer.page_layout = source_reader.page_layout
                    preserved_items.append('page_layout')
                except Exception as e:
                    logger.warning(f"Could not preserve page layout: {str(e)}")
                    
        elif preservation_strategy == 'basic':
            # Only copy basic document info
            if source_reader.metadata:
                basic_metadata = {}
                for key in ['/Title', '/Author', '/Subject', '/Creator', '/Producer']:
                    if key in source_reader.metadata:
                        basic_metadata[key] = source_reader.metadata[key]
                
                if basic_metadata:
                    target_writer.add_metadata(basic_metadata)
                    preserved_items.append('basic_document_info')
                    
        elif preservation_strategy == 'custom':
            # Custom preservation logic (could be extended)
            if source_reader.metadata:
                # Preserve only specific metadata fields
                custom_metadata = {}
                preserve_fields = ['/Title', '/Author', '/CreationDate', '/ModDate']
                
                for field in preserve_fields:
                    if field in source_reader.metadata:
                        custom_metadata[field] = source_reader.metadata[field]
                
                # Add processing timestamp
                custom_metadata['/ModDate'] = f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}"
                custom_metadata['/Producer'] = 'PDF Processing Service'
                
                target_writer.add_metadata(custom_metadata)
                preserved_items.append('custom_metadata')
        
        return {
            'success': True,
            'strategy_used': preservation_strategy,
            'items_preserved': preserved_items,
            'preservation_count': len(preserved_items),
            'source_had_metadata': bool(source_reader.metadata)
        }
        
    except Exception as e:
        logger.error(f"Error preserving PDF metadata: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'strategy_used': preservation_strategy,
            'items_preserved': []
        }


def validate_pdf_structure(file_path: Path) -> Dict[str, Any]:
    """Perform comprehensive PDF structure validation.
    
    Args:
        file_path: Path to PDF file to validate
        
    Returns:
        Dictionary with comprehensive validation results
    """
    try:
        if not file_path.exists():
            return {
                'valid': False,
                'error': 'File does not exist',
                'file_path': str(file_path)
            }
        
        validation_results = {
            'valid': True,
            'file_path': str(file_path),
            'file_size': file_path.stat().st_size,
            'checks_performed': [],
            'warnings': [],
            'errors': []
        }
        
        # Read PDF and perform basic validation
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            
            # Check encryption status
            is_encrypted = reader.is_encrypted
            validation_results['is_encrypted'] = is_encrypted
            validation_results['checks_performed'].append('encryption_check')
            
            if is_encrypted:
                validation_results['errors'].append('PDF is encrypted and cannot be processed')
                validation_results['valid'] = False
                return validation_results
            
            # Check page count and structure
            try:
                page_count = len(reader.pages)
                validation_results['page_count'] = page_count
                validation_results['checks_performed'].append('page_count')
                
                if page_count == 0:
                    validation_results['errors'].append('PDF contains no pages')
                    validation_results['valid'] = False
                
            except Exception as e:
                validation_results['errors'].append(f'Could not determine page count: {str(e)}')
                validation_results['valid'] = False
            
            # Check PDF version compatibility
            try:
                pdf_version = getattr(reader, 'pdf_header', 'Unknown')
                validation_results['pdf_version'] = pdf_version
                validation_results['checks_performed'].append('version_check')
                
                # Check for known compatibility issues
                if '2.0' in pdf_version:
                    validation_results['warnings'].append(
                        'PDF 2.0 detected - some features may not be fully supported'
                    )
                    
            except Exception as e:
                validation_results['warnings'].append(f'Could not determine PDF version: {str(e)}')
            
            # Check document structure integrity
            try:
                # Test page access
                if page_count > 0:
                    first_page = reader.pages[0]
                    last_page = reader.pages[-1]
                    
                    # Try to extract basic page info
                    first_page.mediabox
                    last_page.mediabox
                    
                validation_results['checks_performed'].append('page_access')
                
            except Exception as e:
                validation_results['errors'].append(f'Page structure validation failed: {str(e)}')
                validation_results['valid'] = False
            
            # Check metadata integrity
            try:
                metadata = reader.metadata
                validation_results['has_metadata'] = bool(metadata)
                validation_results['checks_performed'].append('metadata_check')
                
                if metadata:
                    # Check for common metadata fields
                    standard_fields = ['/Title', '/Author', '/Subject', '/Creator', '/Producer']
                    present_fields = [field for field in standard_fields if field in metadata]
                    validation_results['metadata_fields_present'] = len(present_fields)
                    
            except Exception as e:
                validation_results['warnings'].append(f'Could not read metadata: {str(e)}')
            
            # Check for digital signatures
            try:
                has_signatures = _check_for_signatures(reader)
                validation_results['has_digital_signatures'] = has_signatures
                validation_results['checks_performed'].append('signature_check')
                
                if has_signatures:
                    validation_results['warnings'].append(
                        'Document contains digital signatures - processing may invalidate them'
                    )
                    
            except Exception as e:
                validation_results['warnings'].append(f'Could not check signatures: {str(e)}')
            
            # Check for forms and interactive elements
            try:
                has_forms = _check_for_forms(reader)
                validation_results['has_interactive_forms'] = has_forms
                validation_results['checks_performed'].append('forms_check')
                
                if has_forms:
                    validation_results['warnings'].append(
                        'Document contains interactive forms - processing may affect form functionality'
                    )
                    
            except Exception as e:
                validation_results['warnings'].append(f'Could not check forms: {str(e)}')
            
            # Analyze document complexity
            complexity_analysis = _analyze_document_complexity(reader)
            validation_results['complexity_analysis'] = complexity_analysis
            validation_results['checks_performed'].append('complexity_analysis')
            
            # Generate processing recommendations
            validation_results['processing_recommendations'] = _generate_processing_recommendations(
                validation_results, complexity_analysis
            )
        
        # Final validation summary
        validation_results['validation_summary'] = {
            'total_checks': len(validation_results['checks_performed']),
            'warnings_count': len(validation_results['warnings']),
            'errors_count': len(validation_results['errors']),
            'overall_score': _calculate_validation_score(validation_results)
        }
        
        return validation_results
        
    except Exception as e:
        logger.error(f"PDF structure validation failed: {str(e)}")
        return {
            'valid': False,
            'error': f'Validation failed: {str(e)}',
            'file_path': str(file_path)
        }


def generate_split_filenames(
    base_name: str, 
    strategy: str, 
    page_ranges: List[Tuple[int, int]], 
    pattern_matches: Optional[List[str]] = None
) -> List[str]:
    """Generate intelligent filenames for split PDF files.
    
    Args:
        base_name: Base filename without extension
        strategy: Split strategy used ('pages', 'pattern')
        page_ranges: List of (start_page, end_page) tuples
        pattern_matches: List of pattern matches (for pattern-based splits)
        
    Returns:
        List of generated filenames
    """
    try:
        filenames = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        for i, (start_page, end_page) in enumerate(page_ranges):
            if strategy == 'pages':
                if start_page == end_page:
                    filename = f"{base_name}_page_{start_page}.pdf"
                else:
                    filename = f"{base_name}_pages_{start_page}-{end_page}.pdf"
                    
            elif strategy == 'pattern':
                if pattern_matches and i < len(pattern_matches):
                    # Sanitize pattern match for filename
                    match_text = _sanitize_filename_text(pattern_matches[i])
                    filename = f"{base_name}_match_{i+1}_{match_text}.pdf"
                else:
                    filename = f"{base_name}_section_{i+1}_pages_{start_page}-{end_page}.pdf"
                    
            else:
                # Generic naming
                filename = f"{base_name}_part_{i+1}_{timestamp}.pdf"
            
            # Ensure filename is unique and valid
            filename = _ensure_valid_filename(filename)
            filenames.append(filename)
        
        return filenames
        
    except Exception as e:
        logger.error(f"Error generating split filenames: {str(e)}")
        # Fallback to simple naming
        return [f"{base_name}_part_{i+1}.pdf" for i in range(len(page_ranges))]


def estimate_processing_time(
    operation: str, 
    file_size: int, 
    complexity_factors: Dict[str, Any]
) -> Dict[str, Any]:
    """Estimate processing time for PDF operations.
    
    Args:
        operation: Type of operation ('split', 'merge', 'extract')
        file_size: File size in bytes
        complexity_factors: Dictionary with complexity information
        
    Returns:
        Dictionary with time estimates and confidence intervals
    """
    try:
        # Base processing times (seconds)
        base_times = {
            'split': 5,
            'merge': 10,
            'extract': 15,
            'pattern_split': 20  # Pattern-based splitting takes longer
        }
        
        base_time = base_times.get(operation, 10)
        size_mb = file_size / (1024 * 1024)
        
        # Size factor (larger files take longer)
        size_factor = size_mb * 0.5  # 0.5 seconds per MB
        
        # Complexity factors
        page_count = complexity_factors.get('page_count', 1)
        has_images = complexity_factors.get('has_images', False)
        has_forms = complexity_factors.get('has_forms', False)
        is_complex = complexity_factors.get('complexity', 'low') in ['medium', 'high']
        
        # Calculate complexity multiplier
        complexity_multiplier = 1.0
        if has_images:
            complexity_multiplier += 0.3
        if has_forms:
            complexity_multiplier += 0.2
        if is_complex:
            complexity_multiplier += 0.4
        
        # Page factor
        page_factor = page_count * 0.2  # 0.2 seconds per page
        
        # Calculate estimated time
        estimated_seconds = int(base_time + size_factor + page_factor) * complexity_multiplier
        
        # Add uncertainty margins
        min_time = estimated_seconds * 0.7  # 30% faster
        max_time = estimated_seconds * 1.5  # 50% slower
        
        # Determine confidence level
        confidence = 'high' if size_mb < 10 and page_count < 50 else 'medium' if size_mb < 50 else 'low'
        
        return {
            'estimated_seconds': int(estimated_seconds),
            'estimated_minutes': round(estimated_seconds / 60, 1),
            'min_seconds': int(min_time),
            'max_seconds': int(max_time),
            'confidence_level': confidence,
            'factors_considered': {
                'file_size_mb': size_mb,
                'page_count': page_count,
                'complexity_multiplier': round(complexity_multiplier, 2),
                'has_images': has_images,
                'has_forms': has_forms,
                'is_complex_structure': is_complex
            },
            'recommendations': _generate_time_recommendations(
                operation, estimated_seconds, size_mb, complexity_factors
            )
        }
        
    except Exception as e:
        logger.error(f"Error estimating processing time: {str(e)}")
        return {
            'estimated_seconds': 60,  # Safe fallback
            'estimated_minutes': 1,
            'confidence_level': 'low',
            'error': str(e)
        }


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of file for integrity verification.
    
    Args:
        file_path: Path to file
        
    Returns:
        SHA-256 hash as hex string
    """
    try:
        hash_sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating file hash for {file_path}: {str(e)}")
        return ""


# Private helper functions

def _calculate_compression_efficiency(
    source_size: int, 
    output_size: int, 
    source_pages: int, 
    output_pages: int
) -> Dict[str, Any]:
    """Calculate compression efficiency metrics."""
    return {
        'size_ratio': (output_size / source_size) if source_size > 0 else 1,
        'compression_achieved': output_size < source_size,
        'bytes_per_page': output_size // output_pages if output_pages > 0 else 0,
        'efficiency_score': min(100, (source_size / output_size) * 50) if output_size > 0 else 0
    }


def _calculate_split_efficiency(
    source_size: int, 
    total_output_size: int, 
    source_pages: int, 
    total_output_pages: int, 
    file_count: int
) -> Dict[str, Any]:
    """Calculate split operation efficiency metrics."""
    overhead = total_output_size - source_size
    overhead_per_file = overhead / file_count if file_count > 0 else 0
    
    return {
        'split_overhead_bytes': overhead,
        'split_overhead_mb': round(overhead / (1024 * 1024), 2),
        'overhead_per_file': round(overhead_per_file, 0),
        'efficiency_rating': 'excellent' if overhead < 1024 else 'good' if overhead < 10240 else 'fair',
        'pages_per_file_avg': total_output_pages / file_count if file_count > 0 else 0
    }


def _calculate_integrity_score(output_stats: List[Dict], page_integrity: bool) -> int:
    """Calculate integrity score (0-100)."""
    base_score = 100 if page_integrity else 50
    error_penalty = len([f for f in output_stats if 'error' in f]) * 10
    return max(0, base_score - error_penalty)


def _calculate_merge_quality(
    source_stats: List[Dict], 
    output_size: int, 
    output_pages: int, 
    total_source_size: int, 
    total_source_pages: int
) -> Dict[str, Any]:
    """Calculate merge quality metrics."""
    valid_sources = len([f for f in source_stats if 'error' not in f])
    total_sources = len(source_stats)
    
    return {
        'source_validity_ratio': valid_sources / total_sources if total_sources > 0 else 0,
        'size_efficiency': (output_size / total_source_size) if total_source_size > 0 else 1,
        'page_preservation': (output_pages / total_source_pages) if total_source_pages > 0 else 1,
        'merge_success_rate': (valid_sources / total_sources) * 100 if total_sources > 0 else 0,
        'quality_grade': _assign_quality_grade(valid_sources, total_sources, output_pages, total_source_pages)
    }


def _calculate_merge_integrity_score(page_integrity: bool, source_stats: List[Dict]) -> int:
    """Calculate merge integrity score (0-100)."""
    base_score = 100 if page_integrity else 70
    valid_sources = len([f for f in source_stats if 'error' not in f])
    total_sources = len(source_stats)
    validity_ratio = valid_sources / total_sources if total_sources > 0 else 0
    
    return int(base_score * validity_ratio)


def _assign_quality_grade(valid_sources: int, total_sources: int, output_pages: int, total_source_pages: int) -> str:
    """Assign quality grade based on merge metrics."""
    success_rate = valid_sources / total_sources if total_sources > 0 else 0
    page_preservation = output_pages / total_source_pages if total_source_pages > 0 else 0
    
    if success_rate >= 0.95 and page_preservation >= 0.98:
        return 'A'
    elif success_rate >= 0.9 and page_preservation >= 0.95:
        return 'B'
    elif success_rate >= 0.8 and page_preservation >= 0.9:
        return 'C'
    elif success_rate >= 0.7:
        return 'D'
    else:
        return 'F'


def _generate_split_recommendations(
    source_size: int, 
    total_output_size: int, 
    file_count: int, 
    efficiency: Dict[str, Any]
) -> List[str]:
    """Generate recommendations for split operations."""
    recommendations = []
    
    overhead = total_output_size - source_size
    if overhead > 1024 * 1024:  # 1MB
        recommendations.append("Consider using compression to reduce file size overhead")
    
    if file_count > 20:
        recommendations.append("Large number of output files may be difficult to manage")
    
    if efficiency['efficiency_rating'] == 'fair':
        recommendations.append("Split operation created significant overhead - consider different split strategy")
    
    return recommendations


def _generate_merge_recommendations(
    total_source_size: int, 
    output_size: int, 
    file_count: int, 
    quality: Dict[str, Any]
) -> List[str]:
    """Generate recommendations for merge operations."""
    recommendations = []
    
    if quality['quality_grade'] in ['D', 'F']:
        recommendations.append("Merge quality is low - check source file integrity")
    
    compression_ratio = total_source_size / output_size if output_size > 0 else 1
    if compression_ratio > 1.2:
        recommendations.append("Good compression achieved - merged file is significantly smaller")
    elif compression_ratio < 0.95:
        recommendations.append("File size increased after merge - this may indicate processing overhead")
    
    if file_count > 10:
        recommendations.append("Merging many files - consider splitting into smaller merge operations")
    
    return recommendations


def _check_for_signatures(reader: PdfReader) -> bool:
    """Check if PDF contains digital signatures."""
    try:
        # Basic check - look for signature-related objects
        # This is a simplified implementation
        if hasattr(reader, 'trailer') and reader.trailer:
            if '/AcroForm' in reader.trailer.get('/Root', {}):
                return True
        return False
    except Exception:
        return False


def _check_for_forms(reader: PdfReader) -> bool:
    """Check if PDF contains interactive forms."""
    try:
        # Look for AcroForm dictionary
        if hasattr(reader, 'trailer') and reader.trailer:
            root = reader.trailer.get('/Root', {})
            return '/AcroForm' in root
        return False
    except Exception:
        return False


def _analyze_document_complexity(reader: PdfReader) -> Dict[str, Any]:
    """Analyze document complexity for processing estimates."""
    try:
        complexity = {
            'page_count': len(reader.pages),
            'has_metadata': bool(reader.metadata),
            'has_images': False,
            'has_fonts': False,
            'structure_complexity': 'low'
        }
        
        # Sample first few pages for complexity analysis
        sample_pages = min(3, len(reader.pages))
        for i in range(sample_pages):
            try:
                page = reader.pages[i]
                page_dict = page.get_contents()
                if page_dict and hasattr(page_dict, 'get_data'):
                    page_content = page_dict.get_data()
                    if b'/Image' in page_content or b'/Im' in page_content:
                        complexity['has_images'] = True
                    if b'/Font' in page_content or b'/F' in page_content:
                        complexity['has_fonts'] = True
            except Exception:
                continue
        
        # Determine overall complexity
        complexity_score = 0
        if complexity['page_count'] > 50:
            complexity_score += 2
        if complexity['has_images']:
            complexity_score += 2
        if complexity['has_fonts']:
            complexity_score += 1
        
        if complexity_score >= 4:
            complexity['structure_complexity'] = 'high'
        elif complexity_score >= 2:
            complexity['structure_complexity'] = 'medium'
        
        return complexity
        
    except Exception as e:
        logger.warning(f"Could not analyze document complexity: {str(e)}")
        return {'structure_complexity': 'unknown'}


def _generate_processing_recommendations(
    validation_results: Dict[str, Any], 
    complexity: Dict[str, Any]
) -> List[str]:
    """Generate processing recommendations based on validation results."""
    recommendations = []
    
    if validation_results.get('has_digital_signatures'):
        recommendations.append("Document has digital signatures - processing will invalidate them")
    
    if validation_results.get('has_interactive_forms'):
        recommendations.append("Document has interactive forms - form functionality may be affected")
    
    if complexity.get('structure_complexity') == 'high':
        recommendations.append("Complex document structure - processing may take longer")
    
    if validation_results.get('page_count', 0) > 100:
        recommendations.append("Large document - consider using background processing")
    
    return recommendations


def _calculate_validation_score(validation_results: Dict[str, Any]) -> int:
    """Calculate overall validation score (0-100)."""
    base_score = 100
    
    # Deduct points for errors and warnings
    error_penalty = len(validation_results.get('errors', [])) * 20
    warning_penalty = len(validation_results.get('warnings', [])) * 5
    
    return max(0, base_score - error_penalty - warning_penalty)


def _sanitize_filename_text(text: str, max_length: int = 15) -> str:
    """Sanitize text for use in filenames."""
    # Remove or replace invalid characters
    sanitized = re.sub(r'[^\w\s-]', '', text)
    # Replace spaces with underscores
    sanitized = re.sub(r'\s+', '_', sanitized)
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized.strip('_') or 'section'


def _ensure_valid_filename(filename: str) -> str:
    """Ensure filename is valid for filesystem."""
    # Remove invalid characters for cross-platform compatibility
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Ensure filename isn't too long
    if len(filename) > 200:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = f"{name[:195]}.{ext}" if ext else name[:200]
    
    return filename


def _generate_time_recommendations(
    operation: str, 
    estimated_seconds: int, 
    size_mb: float, 
    complexity_factors: Dict[str, Any]
) -> List[str]:
    """Generate recommendations for processing time optimization."""
    recommendations = []
    
    if estimated_seconds > 60:
        recommendations.append("Consider using background processing for this operation")
    
    if size_mb > 50:
        recommendations.append("Large file size may increase processing time significantly")
    
    if complexity_factors.get('has_images') and operation == 'pattern_split':
        recommendations.append("Pattern matching on image-heavy documents may be slower")
    
    if complexity_factors.get('page_count', 0) > 100:
        recommendations.append("High page count will increase processing time")
    
    return recommendations