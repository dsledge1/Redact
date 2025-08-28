"""
Table extraction service for detecting and extracting tables from PDFs.

This service provides comprehensive table detection and extraction capabilities,
supporting both text-based and image-based PDFs with multiple extraction methods.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from django.conf import settings

from app.utils.temp_file_manager import TempFileManager
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)


class TableExtractionService:
    """Service for extracting tables from PDF documents."""
    
    def __init__(self, session_id: str):
        """Initialize the table extraction service.
        
        Args:
            session_id: Unique session identifier for file management
        """
        self.session_id = session_id
        self.temp_file_manager = TempFileManager(session_id)
    
    @handle_errors
    def extract_tables(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None,
        extraction_method: str = 'auto',
        csv_delimiter: str = ',',
        encoding: str = 'utf-8',
        include_headers: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Extract tables from PDF file.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional tuple of (start_page, end_page) (1-indexed)
            extraction_method: Method to use ('auto', 'camelot', 'tabula')
            csv_delimiter: Delimiter for CSV export
            encoding: Text encoding for output files
            include_headers: Whether to include headers in CSV. If None, auto-detect headers.
            
        Returns:
            Dictionary containing extraction results and statistics
        """
        logger.info(f"Starting table extraction from {file_path}")
        
        try:
            # Import here to avoid import errors if dependencies are not installed
            import camelot
            import tabula
        except ImportError as e:
            logger.error(f"Required table extraction libraries not available: {e}")
            return {
                'success': False,
                'error': 'Table extraction dependencies not installed',
                'tables': [],
                'files': []
            }
        
        # Check for Java runtime (required for tabula-py)
        java_available = shutil.which('java') is not None
        if not java_available:
            logger.warning("Java runtime not found. Tabula-py will be unavailable. Install Java JRE for full functionality.")
        
        # Determine pages to process
        pages = self._get_pages_to_process(file_path, page_range)
        if not pages:
            return {
                'success': False,
                'error': 'No valid pages to process',
                'tables': [],
                'files': []
            }
        
        # Extract tables using selected method
        tables = []
        extraction_stats = {
            'pages_processed': 0,
            'tables_detected': 0,
            'tables_validated': 0,
            'extraction_method': extraction_method
        }
        
        if extraction_method in ['auto', 'camelot']:
            camelot_tables = self._detect_tables_camelot(file_path, pages)
            if camelot_tables or extraction_method == 'camelot':
                tables.extend(camelot_tables)
                extraction_stats['extraction_method'] = 'camelot'
        
        # Use tabula as fallback or primary method (if Java is available)
        if ((not tables and extraction_method == 'auto') or extraction_method == 'tabula') and java_available:
            tabula_tables = self._detect_tables_tabula(file_path, pages)
            tables.extend(tabula_tables)
            if extraction_method == 'auto':
                extraction_stats['extraction_method'] = 'tabula'
        elif extraction_method == 'tabula' and not java_available:
            logger.error("Tabula extraction requested but Java runtime not available")
            return {
                'success': False,
                'error': 'Java runtime required for tabula extraction but not found',
                'tables': [],
                'files': []
            }
        
        extraction_stats['pages_processed'] = len(pages)
        extraction_stats['tables_detected'] = len(tables)
        
        # Validate and filter tables
        valid_tables = self._validate_table_data(tables)
        extraction_stats['tables_validated'] = len(valid_tables)
        
        # Export tables to CSV
        output_files = []
        if valid_tables:
            output_files = self._export_tables_to_csv(
                valid_tables, 
                csv_delimiter, 
                encoding,
                include_headers
            )
        
        # Calculate confidence scores
        table_metadata = []
        for i, table in enumerate(valid_tables):
            metadata = self._format_table_metadata(table, pages[i % len(pages)], i)
            metadata['confidence'] = self._calculate_table_confidence(table['dataframe'])
            table_metadata.append(metadata)
        
        logger.info(f"Table extraction completed: {len(valid_tables)} tables extracted")
        
        return {
            'success': True,
            'tables': table_metadata,
            'files': output_files,
            'statistics': extraction_stats,
            'page_range': page_range,
            'total_pages_processed': len(pages)
        }
    
    def _get_pages_to_process(self, file_path: Path, page_range: Optional[Tuple[int, int]]) -> List[int]:
        """Determine which pages to process for table extraction.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional page range tuple
            
        Returns:
            List of page numbers to process (1-indexed)
        """
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            doc.close()
            
            if page_range:
                start, end = page_range
                start = max(1, start)
                end = min(total_pages, end)
                if start > end:
                    return []
                return list(range(start, end + 1))
            else:
                return list(range(1, total_pages + 1))
                
        except Exception as e:
            logger.error(f"Error determining pages to process: {e}")
            return []
    
    def _detect_tables_camelot(self, file_path: Path, pages: List[int]) -> List[Dict[str, Any]]:
        """Detect tables using camelot-py.
        
        Args:
            file_path: Path to the PDF file
            pages: List of page numbers to process
            
        Returns:
            List of detected tables with metadata
        """
        tables = []
        
        try:
            import camelot
            
            # Try lattice method first (for tables with borders)
            page_str = ','.join(map(str, pages))
            
            try:
                camelot_tables = camelot.read_pdf(
                    str(file_path),
                    pages=page_str,
                    flavor='lattice',
                    line_scale=40
                )
                
                for i, table in enumerate(camelot_tables):
                    if not table.df.empty:
                        tables.append({
                            'dataframe': table.df,
                            'page': table.page,
                            'method': 'camelot_lattice',
                            'accuracy': getattr(table, 'accuracy', 0.0),
                            'bbox': getattr(table, '_bbox', []),
                            'table_index': i
                        })
                        
            except Exception as e:
                logger.warning(f"Camelot lattice method failed: {e}")
            
            # Try stream method if lattice didn't work well
            if len(tables) == 0:
                try:
                    camelot_tables = camelot.read_pdf(
                        str(file_path),
                        pages=page_str,
                        flavor='stream',
                        edge_tol=500
                    )
                    
                    for i, table in enumerate(camelot_tables):
                        if not table.df.empty:
                            tables.append({
                                'dataframe': table.df,
                                'page': table.page,
                                'method': 'camelot_stream',
                                'accuracy': getattr(table, 'accuracy', 0.0),
                                'bbox': getattr(table, '_bbox', []),
                                'table_index': i
                            })
                            
                except Exception as e:
                    logger.warning(f"Camelot stream method failed: {e}")
        
        except ImportError:
            logger.error("Camelot library not available")
        except Exception as e:
            logger.error(f"Error in camelot table detection: {e}")
        
        return tables
    
    def _detect_tables_tabula(self, file_path: Path, pages: List[int]) -> List[Dict[str, Any]]:
        """Detect tables using tabula-py as fallback.
        
        Args:
            file_path: Path to the PDF file
            pages: List of page numbers to process
            
        Returns:
            List of detected tables with metadata
        """
        tables = []
        
        try:
            import tabula
            
            for page in pages:
                try:
                    # Extract tables from single page
                    dfs = tabula.read_pdf(
                        str(file_path),
                        pages=page,
                        multiple_tables=True,
                        pandas_options={'header': None}
                    )
                    
                    for i, df in enumerate(dfs):
                        if not df.empty:
                            tables.append({
                                'dataframe': df,
                                'page': page,
                                'method': 'tabula',
                                'accuracy': 0.0,  # Tabula doesn't provide accuracy
                                'bbox': [],
                                'table_index': i
                            })
                            
                except Exception as e:
                    logger.warning(f"Tabula failed on page {page}: {e}")
                    continue
        
        except ImportError:
            logger.error("Tabula library not available")
        except Exception as e:
            logger.error(f"Error in tabula table detection: {e}")
        
        return tables
    
    def _validate_table_data(self, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and filter table data.
        
        Args:
            tables: List of detected tables
            
        Returns:
            List of validated tables
        """
        valid_tables = []
        
        for table in tables:
            df = table['dataframe']
            
            # Check minimum dimensions
            if df.shape[0] < 2 or df.shape[1] < 2:
                continue
            
            # Check for mostly empty table
            non_null_ratio = df.count().sum() / (df.shape[0] * df.shape[1])
            if non_null_ratio < 0.1:  # Less than 10% filled
                continue
            
            # Calculate confidence based on data quality
            confidence = self._calculate_table_confidence(df)
            if confidence < 0.3:  # Low confidence threshold
                continue
            
            table['confidence'] = confidence
            valid_tables.append(table)
        
        return valid_tables
    
    def _calculate_table_confidence(self, df: pd.DataFrame) -> float:
        """Calculate confidence score for table quality.
        
        Args:
            df: DataFrame containing table data
            
        Returns:
            Confidence score between 0 and 1
        """
        if df.empty:
            return 0.0
        
        # Factors for confidence calculation
        factors = []
        
        # Data density (ratio of non-null values)
        non_null_ratio = df.count().sum() / (df.shape[0] * df.shape[1])
        factors.append(min(non_null_ratio * 2, 1.0))
        
        # Size factor (larger tables are often more reliable)
        size_factor = min((df.shape[0] * df.shape[1]) / 50, 1.0)
        factors.append(size_factor)
        
        # Consistency factor (similar column lengths)
        col_lengths = [len(str(val)) for col in df.columns for val in df[col] if pd.notna(val)]
        if col_lengths:
            series = pd.Series(col_lengths)
            mean_len = series.mean()
            if not mean_len:
                factors.append(0.0)
            else:
                factors.append(max(1.0 - (series.std()/mean_len), 0.0))
        else:
            factors.append(0.5)
        
        return sum(factors) / len(factors)
    
    def _export_tables_to_csv(
        self,
        tables: List[Dict[str, Any]],
        delimiter: str = ',',
        encoding: str = 'utf-8',
        include_headers: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Export tables to CSV files.
        
        Args:
            tables: List of validated tables
            delimiter: CSV delimiter
            encoding: File encoding
            include_headers: Whether to include headers in CSV. If None, auto-detect headers.
            
        Returns:
            List of exported file information
        """
        exported_files = []
        downloads_dir = self.temp_file_manager.downloads_dir
        
        for i, table in enumerate(tables):
            try:
                df = table['dataframe']
                page = table.get('page', i + 1)
                
                # Generate safe filename
                filename = f"table_page_{page}_{i + 1}.csv"
                file_path = downloads_dir / filename
                
                # Determine whether to include headers
                if include_headers is None:
                    use_headers = self._detect_headers(df)
                else:
                    use_headers = include_headers
                
                # Export to CSV
                df.to_csv(
                    file_path,
                    sep=delimiter,
                    encoding=encoding,
                    index=False,
                    header=use_headers
                )
                
                file_info = {
                    'filename': filename,
                    'file_path': str(file_path),
                    'file_size': file_path.stat().st_size,
                    'page': page,
                    'table_index': i,
                    'rows': df.shape[0],
                    'columns': df.shape[1],
                    'method': table.get('method', 'unknown')
                }
                
                exported_files.append(file_info)
                logger.info(f"Exported table to {filename}")
                
            except Exception as e:
                logger.error(f"Error exporting table {i}: {e}")
                continue
        
        return exported_files
    
    def _format_table_metadata(
        self,
        table: Dict[str, Any],
        page_num: int,
        table_index: int
    ) -> Dict[str, Any]:
        """Format table metadata for response.
        
        Args:
            table: Table data dictionary
            page_num: Page number
            table_index: Table index on page
            
        Returns:
            Formatted table metadata
        """
        df = table['dataframe']
        
        return {
            'page': page_num,
            'table_index': table_index,
            'rows': df.shape[0],
            'columns': df.shape[1],
            'method': table.get('method', 'unknown'),
            'accuracy': table.get('accuracy', 0.0),
            'data_density': df.count().sum() / (df.shape[0] * df.shape[1]),
            'has_headers': self._detect_headers(df),
            'bbox': table.get('bbox', [])
        }
    
    def _detect_headers(self, df: pd.DataFrame) -> bool:
        """Detect if table likely has headers.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            True if headers are likely present
        """
        if df.empty or df.shape[0] < 2:
            return False
        
        # Check if first row has different characteristics than others
        first_row = df.iloc[0]
        rest_rows = df.iloc[1:]
        
        # Simple heuristic: check if first row has more text content
        first_row_text_ratio = sum(isinstance(val, str) and len(str(val)) > 3 for val in first_row) / len(first_row)
        rest_rows_text_ratio = sum(isinstance(val, str) and len(str(val)) > 3 for val in rest_rows.values.flatten()) / rest_rows.size
        
        return first_row_text_ratio > rest_rows_text_ratio * 1.5