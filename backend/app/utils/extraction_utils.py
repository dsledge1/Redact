"""
Utility functions to support extraction services and provide common functionality.

This module provides shared utilities for parameter validation, result formatting,
file organization, and error handling across all extraction services.
"""

import logging
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from app.utils.temp_file_manager import TempFileManager

logger = logging.getLogger(__name__)


def validate_extraction_parameters(
    extraction_type: str, 
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate all extraction parameters for consistency and correctness.
    
    Args:
        extraction_type: Type of extraction being performed
        parameters: Dictionary of extraction parameters to validate
        
    Returns:
        Dictionary containing validation results and sanitized parameters
    """
    validation_result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'sanitized_parameters': parameters.copy()
    }
    
    try:
        # Validate common parameters
        if 'page_range' in parameters and parameters['page_range']:
            page_range = parameters['page_range']
            if not isinstance(page_range, (list, tuple)) or len(page_range) != 2:
                validation_result['errors'].append("Page range must be [start, end] format")
                validation_result['valid'] = False
            elif not all(isinstance(p, int) and p > 0 for p in page_range):
                validation_result['errors'].append("Page range values must be positive integers")
                validation_result['valid'] = False
            elif page_range[0] > page_range[1]:
                validation_result['errors'].append("Start page must be <= end page")
                validation_result['valid'] = False
        
        # Validate extraction-type specific parameters
        if extraction_type == 'tables':
            # Validate CSV delimiter
            csv_delimiter = parameters.get('csv_delimiter', ',')
            if not isinstance(csv_delimiter, str) or len(csv_delimiter) != 1:
                validation_result['errors'].append("CSV delimiter must be a single character")
                validation_result['valid'] = False
            else:
                validation_result['sanitized_parameters']['csv_delimiter'] = csv_delimiter
            
            # Validate table extraction method
            table_method = parameters.get('table_extraction_method', 'auto')
            if table_method not in ['auto', 'camelot', 'tabula']:
                validation_result['errors'].append("Table extraction method must be 'auto', 'camelot', or 'tabula'")
                validation_result['valid'] = False
            
            # Validate include_headers parameter
            include_headers = parameters.get('include_headers', None)
            if include_headers is not None and not isinstance(include_headers, bool):
                validation_result['errors'].append("include_headers must be a boolean value (true/false) or null")
                validation_result['valid'] = False
        
        elif extraction_type == 'images':
            # Validate image format
            image_format = parameters.get('image_format', 'PNG')
            if image_format.upper() not in ['PNG', 'JPEG', 'TIFF', 'WEBP']:
                validation_result['errors'].append("Image format must be PNG, JPEG, TIFF, or WEBP")
                validation_result['valid'] = False
            else:
                validation_result['sanitized_parameters']['image_format'] = image_format.upper()
            
            # Validate image quality
            image_quality = parameters.get('image_quality', 95)
            if not isinstance(image_quality, int) or not (1 <= image_quality <= 100):
                validation_result['errors'].append("Image quality must be an integer between 1 and 100")
                validation_result['valid'] = False
        
        elif extraction_type == 'text':
            # Validate output format
            output_format = parameters.get('output_format', 'json')
            if output_format not in ['json', 'txt', 'structured']:
                validation_result['errors'].append("Text output format must be 'json', 'txt', or 'structured'")
                validation_result['valid'] = False
            
            # Validate include_formatting
            include_formatting = parameters.get('include_formatting', False)
            if not isinstance(include_formatting, bool):
                validation_result['warnings'].append("include_formatting should be boolean, converting")
                validation_result['sanitized_parameters']['include_formatting'] = bool(include_formatting)
        
        elif extraction_type == 'metadata':
            # Validate metadata output format
            output_format = parameters.get('output_format', 'json')
            if output_format not in ['json']:
                validation_result['errors'].append("Metadata output format must be 'json'")
                validation_result['valid'] = False
        
        # Validate universal parameters
        if 'dpi' in parameters:
            dpi = parameters.get('dpi')
            if not isinstance(dpi, int) or not (72 <= dpi <= 600):
                validation_result['warnings'].append("DPI should be between 72 and 600, using default")
                validation_result['sanitized_parameters']['dpi'] = 300
        
        logger.info(f"Parameter validation for {extraction_type}: {'PASSED' if validation_result['valid'] else 'FAILED'}")
        
    except Exception as e:
        logger.error(f"Error during parameter validation: {e}")
        validation_result['valid'] = False
        validation_result['errors'].append(f"Validation error: {str(e)}")
    
    return validation_result


def format_extraction_results(
    results: Dict[str, Any], 
    extraction_type: str
) -> Dict[str, Any]:
    """Format extraction results for consistent API responses.
    
    Args:
        results: Raw extraction results from services
        extraction_type: Type of extraction performed
        
    Returns:
        Dictionary with formatted, standardized results
    """
    try:
        formatted_results = {
            'success': results.get('success', False),
            'extraction_type': extraction_type,
            'timestamp': datetime.utcnow().isoformat(),
            'files_created': [],
            'statistics': {},
            'metadata': {}
        }
        
        # Add extraction-specific formatting
        if extraction_type == 'tables':
            formatted_results['statistics'] = {
                'tables_found': len(results.get('tables', [])),
                'pages_processed': results.get('total_pages_processed', 0),
                'extraction_method': results.get('statistics', {}).get('extraction_method', 'unknown'),
                'csv_files_created': len([f for f in results.get('files', []) if f.get('filename', '').endswith('.csv')])
            }
            formatted_results['tables'] = results.get('tables', [])
            
        elif extraction_type == 'images':
            formatted_results['statistics'] = {
                'images_found': len(results.get('images', [])),
                'pages_processed': results.get('total_pages_processed', 0),
                'embedded_images': results.get('statistics', {}).get('embedded_images_extracted', 0),
                'format_conversions': results.get('statistics', {}).get('format_conversions', 0)
            }
            formatted_results['images'] = results.get('images', [])
            
        elif extraction_type == 'text':
            text_stats = results.get('text_statistics', {})
            formatted_results['statistics'] = {
                'total_characters': text_stats.get('total_characters', 0),
                'total_words': text_stats.get('total_words', 0),
                'pages_processed': text_stats.get('total_pages', 0),
                'reading_time_minutes': text_stats.get('reading_time_minutes', 0),
                'language_detected': results.get('language_info', {}).get('primary_language', 'unknown')
            }
            formatted_results['structured_data'] = results.get('structured_data', {})
            
        elif extraction_type == 'metadata':
            validation = results.get('validation', {})
            formatted_results['statistics'] = {
                'completeness_score': validation.get('completeness_score', 0.0),
                'extraction_sections': len(results.get('metadata', {}).keys()),
                'data_quality_issues': len(validation.get('data_quality_issues', []))
            }
            formatted_results['metadata'] = results.get('metadata', {})
            
        elif extraction_type == 'all':
            # Aggregate statistics from all extraction types
            all_stats = {}
            extraction_summary = results.get('extraction_summary', {})
            
            all_stats['services_used'] = extraction_summary.get('services_used', [])
            all_stats['services_successful'] = extraction_summary.get('services_successful', 0)
            all_stats['total_files_created'] = extraction_summary.get('total_files_created', 0)
            
            formatted_results['statistics'] = all_stats
            formatted_results['comprehensive_results'] = results.get('results', {})
        
        # Add file information
        if 'files' in results:
            formatted_results['files_created'] = results['files']
        elif 'all_files' in results:
            formatted_results['files_created'] = results['all_files']
        
        # Add error information if present
        if not results.get('success', False) and 'error' in results:
            formatted_results['error'] = results['error']
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error formatting extraction results: {e}")
        return {
            'success': False,
            'extraction_type': extraction_type,
            'error': f"Result formatting error: {str(e)}",
            'timestamp': datetime.utcnow().isoformat()
        }


def calculate_extraction_statistics(results: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate comprehensive extraction statistics.
    
    Args:
        results: Extraction results dictionary
        
    Returns:
        Dictionary with calculated statistics
    """
    try:
        statistics = {
            'overall_success': results.get('success', False),
            'processing_time': None,
            'file_metrics': {
                'total_files_created': 0,
                'total_size_bytes': 0,
                'file_types': {}
            },
            'content_metrics': {},
            'quality_metrics': {}
        }
        
        # Calculate file metrics
        files = results.get('files', []) or results.get('files_created', [])
        for file_info in files:
            statistics['file_metrics']['total_files_created'] += 1
            
            if 'file_size' in file_info:
                statistics['file_metrics']['total_size_bytes'] += file_info['file_size']
            
            filename = file_info.get('filename', '')
            if filename:
                extension = Path(filename).suffix.lower()
                statistics['file_metrics']['file_types'][extension] = statistics['file_metrics']['file_types'].get(extension, 0) + 1
        
        # Calculate content metrics based on extraction type
        if 'text_statistics' in results:
            text_stats = results['text_statistics']
            statistics['content_metrics'].update({
                'total_text_characters': text_stats.get('total_characters', 0),
                'total_words': text_stats.get('total_words', 0),
                'average_words_per_sentence': text_stats.get('average_words_per_sentence', 0),
                'complexity_score': text_stats.get('complexity_score', 0)
            })
        
        if 'tables' in results:
            tables = results['tables']
            statistics['content_metrics'].update({
                'total_tables': len(tables),
                'total_table_rows': sum(t.get('rows', 0) for t in tables),
                'total_table_columns': sum(t.get('columns', 0) for t in tables)
            })
        
        if 'images' in results:
            images = results['images']
            statistics['content_metrics'].update({
                'total_images': len(images),
                'total_image_size_mb': sum(img.get('file_size', 0) for img in images) / (1024 * 1024),
                'image_formats': list(set(img.get('format', '') for img in images))
            })
        
        # Calculate quality metrics
        if 'validation' in results:
            validation = results['validation']
            statistics['quality_metrics'].update({
                'completeness_score': validation.get('completeness_score', 0),
                'data_quality_issues': len(validation.get('data_quality_issues', [])),
                'missing_fields': len(validation.get('missing_fields', []))
            })
        
        # Calculate average confidence scores
        confidence_scores = []
        
        if 'tables' in results:
            confidence_scores.extend([t.get('confidence', 0) for t in results['tables']])
        
        if 'language_info' in results:
            confidence_scores.append(results['language_info'].get('confidence', 0))
        
        if confidence_scores:
            statistics['quality_metrics']['average_confidence'] = sum(confidence_scores) / len(confidence_scores)
        
        logger.info(f"Calculated extraction statistics: {statistics['file_metrics']['total_files_created']} files, "
                   f"{statistics['file_metrics']['total_size_bytes']} bytes")
        
        return statistics
        
    except Exception as e:
        logger.error(f"Error calculating extraction statistics: {e}")
        return {
            'overall_success': False,
            'error': f"Statistics calculation error: {str(e)}"
        }


def organize_extraction_files(
    session_id: str, 
    extraction_type: str, 
    files: List[Path]
) -> Dict[str, Any]:
    """Organize extraction files in the downloads directory.
    
    Args:
        session_id: Session identifier
        extraction_type: Type of extraction
        files: List of file paths to organize
        
    Returns:
        Dictionary with file organization results
    """
    try:
        temp_file_manager = TempFileManager(session_id)
        downloads_dir = temp_file_manager.downloads_dir
        
        # Create extraction-type subdirectory
        extraction_dir = downloads_dir / extraction_type
        extraction_dir.mkdir(exist_ok=True)
        
        organized_files = []
        
        for i, file_path in enumerate(files):
            try:
                if not file_path.exists():
                    logger.warning(f"File not found for organization: {file_path}")
                    continue
                
                # Generate organized filename
                original_name = file_path.name
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                organized_name = f"{extraction_type}_{timestamp}_{i+1:03d}_{original_name}"
                
                organized_path = extraction_dir / organized_name
                
                # Move file to organized location with exception handling
                try:
                    shutil.move(str(file_path), str(organized_path))
                except Exception as move_error:
                    logger.error(f"Failed to move file {file_path} to {organized_path}: {move_error}")
                    raise move_error
                
                organized_files.append({
                    'original_path': str(file_path),
                    'organized_path': str(organized_path),
                    'filename': organized_name,
                    'file_size': organized_path.stat().st_size,
                    'extraction_type': extraction_type,
                    'organization_timestamp': datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Failed to organize file {file_path}: {e}")
                continue
        
        logger.info(f"Organized {len(organized_files)} files for {extraction_type} extraction")
        
        return {
            'success': True,
            'organized_files': organized_files,
            'extraction_directory': str(extraction_dir),
            'total_files_organized': len(organized_files)
        }
        
    except Exception as e:
        logger.error(f"Error organizing extraction files: {e}")
        return {
            'success': False,
            'error': f"File organization error: {str(e)}",
            'organized_files': []
        }


def validate_output_format(format_type: str, extraction_type: str) -> bool:
    """Ensure output format is compatible with extraction type.
    
    Args:
        format_type: Requested output format
        extraction_type: Type of extraction
        
    Returns:
        True if format is compatible, False otherwise
    """
    format_compatibility = {
        'text': ['json', 'txt', 'structured'],
        'metadata': ['json'],
        'images': ['png', 'jpeg', 'tiff', 'webp'],
        'tables': ['csv', 'json'],
        'all': ['json', 'mixed']
    }
    
    compatible_formats = format_compatibility.get(extraction_type, [])
    return format_type.lower() in compatible_formats


def estimate_extraction_time(
    file_size: int, 
    page_count: int, 
    extraction_type: str
) -> int:
    """Estimate processing time for extraction based on file characteristics.
    
    Args:
        file_size: File size in bytes
        page_count: Number of pages
        extraction_type: Type of extraction
        
    Returns:
        Estimated processing time in seconds
    """
    try:
        # Base time factors (seconds)
        base_times = {
            'text': 2,
            'metadata': 1,
            'images': 3,
            'tables': 10,  # Table detection is more complex
            'all': 15
        }
        
        base_time = base_times.get(extraction_type, 5)
        
        # Size factor (MB)
        size_mb = file_size / (1024 * 1024)
        size_factor = size_mb * 0.5
        
        # Page factor
        page_factor = page_count * {
            'text': 1,
            'metadata': 0.5,
            'images': 2,
            'tables': 5,  # Tables require more processing per page
            'all': 8
        }.get(extraction_type, 2)
        
        # Complexity multiplier for certain types
        complexity_multiplier = {
            'tables': 1.5,  # Table detection has variable complexity
            'all': 1.3,     # Comprehensive extraction has overhead
        }.get(extraction_type, 1.0)
        
        estimated_seconds = int((base_time + size_factor + page_factor) * complexity_multiplier)
        
        # Add minimum and maximum bounds
        estimated_seconds = max(5, min(estimated_seconds, 1800))  # 5 seconds to 30 minutes
        
        return estimated_seconds
        
    except Exception as e:
        logger.error(f"Error estimating extraction time: {e}")
        return 60  # Default to 1 minute


def sanitize_extraction_filenames(
    base_name: str, 
    extraction_type: str, 
    index: int = None
) -> str:
    """Generate safe filenames for extraction output.
    
    Args:
        base_name: Base filename
        extraction_type: Type of extraction
        index: Optional index for multiple files
        
    Returns:
        Sanitized filename
    """
    try:
        # Remove or replace unsafe characters
        import re
        safe_base = re.sub(r'[<>:"/\\|?*]', '_', base_name)
        safe_base = safe_base[:100]  # Limit length
        
        # Add extraction type prefix
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if index is not None:
            filename = f"{extraction_type}_{timestamp}_{index:03d}_{safe_base}"
        else:
            filename = f"{extraction_type}_{timestamp}_{safe_base}"
        
        return filename
        
    except Exception as e:
        logger.error(f"Error sanitizing filename: {e}")
        return f"{extraction_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_output"


def compress_extraction_results(
    file_paths: List[Path], 
    output_path: Path
) -> Dict[str, Any]:
    """Compress extraction results into a single archive.
    
    Args:
        file_paths: List of files to compress
        output_path: Path for the output archive
        
    Returns:
        Dictionary with compression results
    """
    try:
        import zipfile
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_original_size = 0
            files_added = 0
            
            for file_path in file_paths:
                if file_path.exists():
                    # Add file to archive with relative path
                    arcname = file_path.name
                    zipf.write(file_path, arcname)
                    total_original_size += file_path.stat().st_size
                    files_added += 1
        
        compressed_size = output_path.stat().st_size
        compression_ratio = compressed_size / total_original_size if total_original_size > 0 else 0
        
        logger.info(f"Compressed {files_added} files from {total_original_size} to {compressed_size} bytes "
                   f"(ratio: {compression_ratio:.2f})")
        
        return {
            'success': True,
            'archive_path': str(output_path),
            'files_compressed': files_added,
            'original_size_bytes': total_original_size,
            'compressed_size_bytes': compressed_size,
            'compression_ratio': compression_ratio
        }
        
    except Exception as e:
        logger.error(f"Error compressing extraction results: {e}")
        return {
            'success': False,
            'error': f"Compression error: {str(e)}"
        }


def validate_extraction_output(
    output_files: List[Path], 
    extraction_type: str
) -> Dict[str, Any]:
    """Validate extraction output files for completeness and integrity.
    
    Args:
        output_files: List of output file paths
        extraction_type: Type of extraction
        
    Returns:
        Dictionary with validation results
    """
    try:
        validation_results = {
            'valid': True,
            'issues': [],
            'file_checks': [],
            'total_files': len(output_files),
            'valid_files': 0
        }
        
        for file_path in output_files:
            file_check = {
                'file_path': str(file_path),
                'exists': file_path.exists(),
                'size_bytes': file_path.stat().st_size if file_path.exists() else 0,
                'readable': False,
                'format_valid': False
            }
            
            if file_check['exists']:
                try:
                    # Check if file is readable
                    with open(file_path, 'rb') as f:
                        f.read(1024)  # Try to read first 1KB
                    file_check['readable'] = True
                    
                    # Check format based on extraction type
                    if extraction_type == 'tables' and file_path.suffix.lower() == '.csv':
                        # Validate CSV format
                        with open(file_path, 'r', encoding='utf-8') as f:
                            f.readline()  # Try to read first line
                        file_check['format_valid'] = True
                        
                    elif extraction_type == 'images' and file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.tiff']:
                        # Validate image format
                        from PIL import Image
                        try:
                            with Image.open(file_path) as img:
                                img.verify()
                            file_check['format_valid'] = True
                        except:
                            file_check['format_valid'] = False
                            
                    elif file_path.suffix.lower() == '.json':
                        # Validate JSON format
                        with open(file_path, 'r', encoding='utf-8') as f:
                            json.load(f)
                        file_check['format_valid'] = True
                        
                    elif file_path.suffix.lower() == '.txt':
                        # Text files are generally valid if readable
                        file_check['format_valid'] = True
                    
                    if file_check['readable'] and file_check['format_valid']:
                        validation_results['valid_files'] += 1
                        
                except Exception as e:
                    file_check['error'] = str(e)
                    validation_results['issues'].append(f"File {file_path.name}: {str(e)}")
            else:
                validation_results['issues'].append(f"File not found: {file_path.name}")
                validation_results['valid'] = False
            
            validation_results['file_checks'].append(file_check)
        
        # Overall validation
        if validation_results['valid_files'] == 0:
            validation_results['valid'] = False
            validation_results['issues'].append("No valid output files found")
        
        success_rate = validation_results['valid_files'] / validation_results['total_files'] if validation_results['total_files'] > 0 else 0
        validation_results['success_rate'] = success_rate
        
        logger.info(f"Output validation: {validation_results['valid_files']}/{validation_results['total_files']} files valid "
                   f"({success_rate:.1%} success rate)")
        
        return validation_results
        
    except Exception as e:
        logger.error(f"Error validating extraction output: {e}")
        return {
            'valid': False,
            'error': f"Validation error: {str(e)}",
            'total_files': len(output_files),
            'valid_files': 0
        }


def generate_extraction_manifest(
    results: Dict[str, Any], 
    output_dir: Path
) -> Path:
    """Generate a manifest file documenting extraction results.
    
    Args:
        results: Extraction results dictionary
        output_dir: Directory to save manifest
        
    Returns:
        Path to the generated manifest file
    """
    try:
        manifest_data = {
            'extraction_manifest': {
                'version': '1.0',
                'generated_at': datetime.utcnow().isoformat(),
                'extraction_type': results.get('extraction_type', 'unknown'),
                'extraction_success': results.get('success', False),
                'files_created': results.get('files', []),
                'statistics': results.get('statistics', {}),
                'parameters_used': results.get('extraction_options', {}),
                'processing_metadata': {
                    'total_processing_time': results.get('processing_time'),
                    'extraction_method': results.get('extraction_method'),
                    'quality_scores': results.get('quality_metrics', {})
                }
            }
        }
        
        # Add extraction-specific metadata
        if results.get('extraction_type') == 'tables':
            manifest_data['extraction_manifest']['table_metadata'] = {
                'tables_detected': len(results.get('tables', [])),
                'csv_files_created': len([f for f in results.get('files', []) if f.get('filename', '').endswith('.csv')]),
                'detection_methods_used': results.get('statistics', {}).get('extraction_method', 'unknown')
            }
        
        elif results.get('extraction_type') == 'images':
            manifest_data['extraction_manifest']['image_metadata'] = {
                'images_extracted': len(results.get('images', [])),
                'formats_converted': results.get('statistics', {}).get('format_conversions', 0),
                'total_image_size_mb': sum(img.get('file_size', 0) for img in results.get('images', [])) / (1024 * 1024)
            }
        
        # Generate manifest filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        manifest_filename = f"extraction_manifest_{timestamp}.json"
        manifest_path = output_dir / manifest_filename
        
        # Write manifest to file
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Generated extraction manifest: {manifest_path}")
        
        return manifest_path
        
    except Exception as e:
        logger.error(f"Error generating extraction manifest: {e}")
        # Return a default path even if generation fails
        return output_dir / f"manifest_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def cleanup_failed_extraction(session_id: str, extraction_type: str) -> bool:
    """Clean up files from failed extraction attempts.
    
    Args:
        session_id: Session identifier
        extraction_type: Type of extraction that failed
        
    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        temp_file_manager = TempFileManager(session_id)
        
        # Clean up processing directory
        processing_dir = temp_file_manager.processing_dir
        if processing_dir.exists():
            # Remove temporary files related to this extraction
            for file_path in processing_dir.glob(f"{extraction_type}_*"):
                try:
                    file_path.unlink()
                    logger.debug(f"Removed failed extraction file: {file_path}")
                except Exception as e:
                    logger.warning(f"Could not remove file {file_path}: {e}")
        
        # Clean up partial downloads
        downloads_dir = temp_file_manager.downloads_dir
        if downloads_dir.exists():
            extraction_subdir = downloads_dir / extraction_type
            if extraction_subdir.exists():
                import shutil
                shutil.rmtree(extraction_subdir, ignore_errors=True)
                logger.info(f"Removed failed extraction directory: {extraction_subdir}")
        
        logger.info(f"Completed cleanup for failed {extraction_type} extraction in session {session_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error during failed extraction cleanup: {e}")
        return False


def format_extraction_errors(
    errors: List[Exception], 
    extraction_type: str
) -> Dict[str, Any]:
    """Format extraction errors for consistent error reporting.
    
    Args:
        errors: List of exceptions that occurred
        extraction_type: Type of extraction that failed
        
    Returns:
        Dictionary with formatted error information
    """
    try:
        formatted_errors = {
            'extraction_type': extraction_type,
            'error_count': len(errors),
            'errors': [],
            'error_summary': '',
            'recovery_suggestions': []
        }
        
        # Process individual errors
        for i, error in enumerate(errors):
            error_info = {
                'error_index': i + 1,
                'error_type': type(error).__name__,
                'error_message': str(error),
                'severity': 'high'  # Default severity
            }
            
            # Categorize error severity
            error_msg = str(error).lower()
            if 'warning' in error_msg or 'skip' in error_msg:
                error_info['severity'] = 'low'
            elif 'failed' in error_msg or 'error' in error_msg:
                error_info['severity'] = 'high'
            elif 'timeout' in error_msg or 'memory' in error_msg:
                error_info['severity'] = 'critical'
            
            formatted_errors['errors'].append(error_info)
        
        # Generate error summary
        high_severity_count = len([e for e in formatted_errors['errors'] if e['severity'] == 'high'])
        critical_count = len([e for e in formatted_errors['errors'] if e['severity'] == 'critical'])
        
        if critical_count > 0:
            formatted_errors['error_summary'] = f"{critical_count} critical errors prevented {extraction_type} extraction"
        elif high_severity_count > 0:
            formatted_errors['error_summary'] = f"{high_severity_count} errors occurred during {extraction_type} extraction"
        else:
            formatted_errors['error_summary'] = f"Minor issues during {extraction_type} extraction"
        
        # Add recovery suggestions based on extraction type and error patterns
        error_messages = [str(e) for e in errors]
        combined_errors = ' '.join(error_messages).lower()
        
        if 'dependency' in combined_errors or 'import' in combined_errors:
            formatted_errors['recovery_suggestions'].append("Install required dependencies for extraction")
        
        if 'memory' in combined_errors:
            formatted_errors['recovery_suggestions'].append("Try processing smaller page ranges or reduce quality settings")
        
        if 'timeout' in combined_errors:
            formatted_errors['recovery_suggestions'].append("Increase timeout limits or process document in smaller chunks")
        
        if extraction_type == 'tables' and 'detection' in combined_errors:
            formatted_errors['recovery_suggestions'].append("Try different table detection method (camelot vs tabula)")
        
        if extraction_type == 'images' and 'format' in combined_errors:
            formatted_errors['recovery_suggestions'].append("Try different image output format or quality settings")
        
        return formatted_errors
        
    except Exception as e:
        logger.error(f"Error formatting extraction errors: {e}")
        return {
            'extraction_type': extraction_type,
            'error_count': len(errors),
            'error_summary': f'Error formatting failed: {str(e)}',
            'errors': [{'error_message': str(err)} for err in errors],
            'recovery_suggestions': ['Check system logs for detailed error information']
        }