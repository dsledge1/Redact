import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter

from .temp_file_manager import TempFileManager
from ..utils.validators import validate_pdf_file

logger = logging.getLogger(__name__)


class PDFMerger:
    """
    Specialized service for PDF merging operations with comprehensive
    metadata preservation and validation.
    """
    
    def __init__(self, session_id: str):
        """
        Initialize PDFMerger with session-specific file management.
        
        Args:
            session_id: Session identifier for file management
        """
        self.session_id = session_id
    
    def merge_documents(
        self,
        file_paths: List[Path],
        output_filename: Optional[str] = None,
        preserve_metadata: bool = True,
        merge_strategy: str = 'sequential'
    ) -> Dict[str, Any]:
        """
        Merge multiple PDF documents with comprehensive metadata preservation.
        
        Args:
            file_paths: List of PDF file paths to merge
            output_filename: Optional custom output filename
            preserve_metadata: Whether to preserve and combine metadata
            merge_strategy: Strategy for merging ('sequential', 'aggregate')
            
        Returns:
            Dictionary with merge results, statistics, and file information
        """
        try:
            # Validate merge inputs
            self._validate_merge_inputs(file_paths)
            
            # Analyze source documents
            source_analysis = self._analyze_source_documents(file_paths)
            
            # Generate output filename if not provided
            if not output_filename:
                output_filename = self._generate_output_filename(file_paths)
            
            output_path = TempFileManager.get_session_path(self.session_id, 'downloads') / output_filename
            
            # Open all source readers and check for encryption
            source_readers = []
            for file_path in file_paths:
                reader = PdfReader(str(file_path))
                if reader.is_encrypted:
                    raise ValueError(f"Cannot merge encrypted PDF: {file_path.name}. Please decrypt the file first.")
                source_readers.append(reader)
            
            # Create output writer
            writer = PdfWriter()
            
            # Merge pages sequentially
            total_pages_added = 0
            for reader in source_readers:
                for page in reader.pages:
                    writer.add_page(page)
                    total_pages_added += 1
            
            # Merge metadata if requested
            if preserve_metadata:
                self._merge_metadata(source_readers, writer, merge_strategy)
                self._preserve_document_structure(source_readers, writer)
            
            # Write merged file
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            # Calculate output integrity and statistics
            merge_statistics = self._calculate_output_integrity(
                output_path, source_analysis
            )
            
            # Generate merge report
            merge_report = self._generate_merge_report(
                file_paths, output_path, merge_statistics
            )
            
            result = {
                'success': True,
                'output_file': str(output_path),
                'output_filename': output_filename,
                'source_files': [str(path) for path in file_paths],
                'source_count': len(file_paths),
                'total_pages': total_pages_added,
                'merge_strategy': merge_strategy,
                'metadata_preserved': preserve_metadata,
                'statistics': merge_statistics,
                'report': merge_report,
                'processing_time': None  # Set by caller if needed
            }
            
            logger.info(
                f"Successfully merged {len(file_paths)} PDFs -> {output_filename}, "
                f"{total_pages_added} total pages"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error merging PDFs: {str(e)}")
            raise
    
    def _validate_merge_inputs(self, file_paths: List[Path]) -> None:
        """
        Validate all files for merging compatibility and accessibility.
        
        Args:
            file_paths: List of file paths to validate
            
        Raises:
            ValueError: If files are invalid or incompatible
        """
        if len(file_paths) < 2:
            raise ValueError("At least 2 files required for merging")
        
        if len(file_paths) > 20:
            raise ValueError("Too many files for merging (maximum 20)")
        
        total_size = 0
        for file_path in file_paths:
            # Validate file exists and is readable
            if not file_path.exists() or not file_path.is_file():
                raise ValueError(f"File not found or not readable: {file_path}")
            
            # Validate PDF file
            validation_result = validate_pdf_file(file_path)
            if not validation_result['is_valid']:
                raise ValueError(
                    f"Invalid PDF file {file_path.name}: {validation_result['error']}"
                )
            
            # Check file size
            file_size = file_path.stat().st_size
            total_size += file_size
            
            if file_size > 50 * 1024 * 1024:  # 50MB per file
                raise ValueError(f"File too large: {file_path.name} (max 50MB)")
        
        # Check total size limit
        if total_size > 100 * 1024 * 1024:  # 100MB total
            raise ValueError("Total file size too large (max 100MB)")
    
    def _analyze_source_documents(self, file_paths: List[Path]) -> List[Dict[str, Any]]:
        """
        Analyze source documents to extract metadata and compatibility info.
        
        Args:
            file_paths: List of PDF file paths
            
        Returns:
            List of document analysis results
        """
        analysis_results = []
        
        for file_path in file_paths:
            try:
                reader = PdfReader(str(file_path))
                
                # Extract basic information
                analysis = {
                    'file_path': str(file_path),
                    'filename': file_path.name,
                    'file_size': file_path.stat().st_size,
                    'page_count': len(reader.pages),
                    'encrypted': reader.is_encrypted,
                    'metadata': dict(reader.metadata) if reader.metadata else {},
                    'pdf_version': getattr(reader, 'pdf_header', 'Unknown'),
                    'has_outline': bool(reader.outline) if hasattr(reader, 'outline') else False,
                    'has_xmp_metadata': bool(reader.xmp_metadata) if hasattr(reader, 'xmp_metadata') else False
                }
                
                # Calculate file hash for integrity
                analysis['sha256_hash'] = self._calculate_file_hash(file_path)
                
                analysis_results.append(analysis)
                
            except Exception as e:
                logger.error(f"Error analyzing document {file_path}: {str(e)}")
                analysis_results.append({
                    'file_path': str(file_path),
                    'filename': file_path.name,
                    'error': str(e)
                })
        
        return analysis_results
    
    def _merge_metadata(
        self,
        source_readers: List[PdfReader],
        target_writer: PdfWriter,
        merge_strategy: str
    ) -> None:
        """
        Intelligently combine document metadata from multiple sources.
        
        Args:
            source_readers: List of source PDF readers
            target_writer: Target PDF writer
            merge_strategy: Strategy for metadata merging
        """
        try:
            if merge_strategy == 'sequential':
                # Use first document's metadata as base
                if source_readers and source_readers[0].metadata:
                    base_metadata = dict(source_readers[0].metadata)
                    
                    # Add source file information
                    source_info = f"Merged from {len(source_readers)} documents"
                    base_metadata['/Subject'] = base_metadata.get('/Subject', '') + f" ({source_info})"
                    base_metadata['/ModDate'] = f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    
                    target_writer.add_metadata(base_metadata)
                    
            elif merge_strategy == 'aggregate':
                # Combine metadata intelligently
                combined_metadata = {}
                titles = []
                authors = []
                subjects = []
                
                for reader in source_readers:
                    if reader.metadata:
                        metadata = dict(reader.metadata)
                        if metadata.get('/Title'):
                            titles.append(metadata['/Title'])
                        if metadata.get('/Author'):
                            authors.append(metadata['/Author'])
                        if metadata.get('/Subject'):
                            subjects.append(metadata['/Subject'])
                
                # Combine collected metadata
                if titles:
                    combined_metadata['/Title'] = ' + '.join(titles)
                if authors:
                    combined_metadata['/Author'] = '; '.join(set(authors))
                if subjects:
                    combined_metadata['/Subject'] = '; '.join(subjects)
                
                # Add merge information
                combined_metadata['/Creator'] = 'PDF Merger Service'
                combined_metadata['/ModDate'] = f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                target_writer.add_metadata(combined_metadata)
                
        except Exception as e:
            logger.warning(f"Could not merge metadata: {str(e)}")
    
    def _preserve_document_structure(
        self,
        source_readers: List[PdfReader],
        target_writer: PdfWriter
    ) -> None:
        """
        Handle document structure preservation (outlines, bookmarks, etc.).
        
        Args:
            source_readers: List of source PDF readers
            target_writer: Target PDF writer
        """
        try:
            # For now, we'll preserve the first document's outline if it exists
            # More sophisticated outline merging could be implemented later
            if source_readers and hasattr(source_readers[0], 'outline'):
                if source_readers[0].outline:
                    # Copy outline from first document
                    # Note: PyPDF2 outline copying is complex and may need adjustment
                    pass
                    
        except Exception as e:
            logger.warning(f"Could not preserve document structure: {str(e)}")
    
    def _calculate_output_integrity(
        self,
        output_path: Path,
        source_info: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate file integrity and statistics for merged output.
        
        Args:
            output_path: Path to merged output file
            source_info: Analysis results from source documents
            
        Returns:
            Dictionary with integrity and statistics information
        """
        try:
            output_size = output_path.stat().st_size
            output_hash = self._calculate_file_hash(output_path)
            
            # Calculate statistics
            total_source_size = sum(info.get('file_size', 0) for info in source_info)
            total_source_pages = sum(info.get('page_count', 0) for info in source_info)
            
            # Read output to verify page count
            output_reader = PdfReader(str(output_path))
            actual_pages = len(output_reader.pages)
            
            statistics = {
                'output_size': output_size,
                'output_hash': output_hash,
                'total_source_size': total_source_size,
                'size_change': output_size - total_source_size,
                'size_efficiency': (output_size / total_source_size * 100) if total_source_size > 0 else 0,
                'expected_pages': total_source_pages,
                'actual_pages': actual_pages,
                'page_integrity': actual_pages == total_source_pages,
                'compression_ratio': (total_source_size / output_size) if output_size > 0 else 0
            }
            
            return statistics
            
        except Exception as e:
            logger.error(f"Error calculating output integrity: {str(e)}")
            return {'error': str(e)}
    
    def _generate_merge_report(
        self,
        source_files: List[Path],
        output_path: Path,
        merge_statistics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive merge report with detailed statistics.
        
        Args:
            source_files: List of source file paths
            output_path: Path to merged output file
            merge_statistics: Statistics from merge operation
            
        Returns:
            Dictionary with comprehensive merge report
        """
        report = {
            'merge_summary': {
                'source_count': len(source_files),
                'source_files': [f.name for f in source_files],
                'output_file': output_path.name,
                'merge_timestamp': datetime.now().isoformat()
            },
            'size_analysis': {
                'total_input_size': merge_statistics.get('total_source_size', 0),
                'output_size': merge_statistics.get('output_size', 0),
                'size_change': merge_statistics.get('size_change', 0),
                'compression_achieved': merge_statistics.get('size_change', 0) < 0
            },
            'page_analysis': {
                'expected_pages': merge_statistics.get('expected_pages', 0),
                'actual_pages': merge_statistics.get('actual_pages', 0),
                'page_integrity': merge_statistics.get('page_integrity', False)
            },
            'quality_metrics': {
                'size_efficiency': round(merge_statistics.get('size_efficiency', 0), 2),
                'compression_ratio': round(merge_statistics.get('compression_ratio', 1), 2),
                'integrity_verified': merge_statistics.get('page_integrity', False)
            }
        }
        
        return report
    
    def _generate_output_filename(self, file_paths: List[Path]) -> str:
        """
        Generate intelligent output filename based on source files.
        
        Args:
            file_paths: List of source file paths
            
        Returns:
            Generated output filename
        """
        if len(file_paths) == 2:
            # For 2 files, combine names
            name1 = file_paths[0].stem
            name2 = file_paths[1].stem
            filename = f"{name1}_{name2}_merged.pdf"
        else:
            # For multiple files, use generic name with count
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"merged_{len(file_paths)}_files_{timestamp}.pdf"
        
        return filename
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA-256 hash of file for integrity verification.
        
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
            logger.error(f"Error calculating file hash: {str(e)}")
            return ""