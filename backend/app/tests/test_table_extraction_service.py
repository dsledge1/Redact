"""
Comprehensive unit tests for the TableExtractionService.

This test suite covers table detection with various PDF types, extraction method selection,
CSV export functionality, error handling, and integration scenarios.
"""

import pytest
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import pandas as pd

from app.services.table_extraction_service import TableExtractionService
from app.utils.temp_file_manager import TempFileManager


class TestTableExtractionService:
    """Test cases for TableExtractionService functionality."""
    
    @pytest.fixture
    def mock_session_id(self):
        """Generate a mock session ID for testing."""
        return "test_session_12345"
    
    @pytest.fixture
    def table_service(self, mock_session_id):
        """Create TableExtractionService instance for testing."""
        return TableExtractionService(mock_session_id)
    
    @pytest.fixture
    def sample_pdf_path(self):
        """Create a temporary PDF file path for testing."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            pdf_path = Path(f.name)
        yield pdf_path
        if pdf_path.exists():
            pdf_path.unlink()
    
    @pytest.fixture
    def sample_table_data(self):
        """Create sample table data for testing."""
        return pd.DataFrame({
            'Name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
            'Age': [30, 25, 35],
            'City': ['New York', 'Los Angeles', 'Chicago'],
            'Salary': [50000, 60000, 70000]
        })
    
    def test_table_service_initialization(self, mock_session_id):
        """Test TableExtractionService initialization."""
        service = TableExtractionService(mock_session_id)
        
        assert service.session_id == mock_session_id
        assert isinstance(service.temp_file_manager, TempFileManager)
    
    @patch('app.services.table_extraction_service.fitz')
    @patch('app.services.table_extraction_service.camelot')
    def test_extract_tables_success_camelot(self, mock_camelot, mock_fitz, table_service, sample_pdf_path, sample_table_data):
        """Test successful table extraction using camelot method."""
        # Mock PyMuPDF document
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 5  # 5 pages
        mock_doc.close.return_value = None
        
        # Mock camelot table extraction
        mock_table = Mock()
        mock_table.df = sample_table_data
        mock_table.page = 1
        mock_table.accuracy = 0.95
        mock_table._bbox = [100, 200, 400, 300]
        
        mock_camelot.read_pdf.return_value = [mock_table]
        
        # Mock TempFileManager
        with patch.object(table_service.temp_file_manager, 'downloads_dir') as mock_downloads_dir:
            mock_downloads_dir.__truediv__ = Mock(return_value=Path('/tmp/test.csv'))
            
            with patch('pandas.DataFrame.to_csv') as mock_to_csv:
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 1024
                    
                    result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is True
        assert len(result['tables']) == 1
        assert result['statistics']['extraction_method'] == 'camelot'
        assert result['statistics']['tables_detected'] == 1
        assert result['statistics']['tables_validated'] == 1
    
    @patch('app.services.table_extraction_service.fitz')
    @patch('app.services.table_extraction_service.camelot')
    @patch('app.services.table_extraction_service.tabula')
    def test_extract_tables_fallback_to_tabula(self, mock_tabula, mock_camelot, mock_fitz, table_service, sample_pdf_path, sample_table_data):
        """Test fallback to tabula when camelot fails."""
        # Mock PyMuPDF document
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 3
        
        # Mock camelot failure (empty results)
        mock_camelot.read_pdf.return_value = []
        
        # Mock tabula success
        mock_tabula.read_pdf.return_value = [sample_table_data]
        
        with patch.object(table_service.temp_file_manager, 'downloads_dir') as mock_downloads_dir:
            mock_downloads_dir.__truediv__ = Mock(return_value=Path('/tmp/test.csv'))
            
            with patch('pandas.DataFrame.to_csv'):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 1024
                    
                    result = table_service.extract_tables(sample_pdf_path, extraction_method='auto')
        
        assert result['success'] is True
        assert result['statistics']['extraction_method'] == 'tabula'
    
    @patch('app.services.table_extraction_service.fitz')
    @patch('app.services.table_extraction_service.camelot')
    def test_extract_tables_with_page_range(self, mock_camelot, mock_fitz, table_service, sample_pdf_path, sample_table_data):
        """Test table extraction with specific page range."""
        # Mock PyMuPDF document
        mock_doc = Mock()
        mock_fitz.open.return_value = mock_doc
        mock_doc.__len__.return_value = 10  # 10 pages
        
        # Mock camelot extraction
        mock_table = Mock()
        mock_table.df = sample_table_data
        mock_table.page = 3
        mock_table.accuracy = 0.90
        
        mock_camelot.read_pdf.return_value = [mock_table]
        
        with patch.object(table_service.temp_file_manager, 'downloads_dir'):
            with patch('pandas.DataFrame.to_csv'):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 512
                    
                    result = table_service.extract_tables(
                        sample_pdf_path, 
                        page_range=(2, 4)  # Pages 2-4
                    )
        
        assert result['success'] is True
        assert result['page_range'] == (2, 4)
        # Verify camelot was called with correct page range
        mock_camelot.read_pdf.assert_called()
        args, kwargs = mock_camelot.read_pdf.call_args
        assert '2,3,4' in kwargs['pages']
    
    def test_get_pages_to_process_full_document(self, table_service, sample_pdf_path):
        """Test page range determination for full document."""
        with patch('app.services.table_extraction_service.fitz') as mock_fitz:
            mock_doc = Mock()
            mock_fitz.open.return_value = mock_doc
            mock_doc.__len__.return_value = 5
            
            pages = table_service._get_pages_to_process(sample_pdf_path, None)
            
            assert pages == [1, 2, 3, 4, 5]
    
    def test_get_pages_to_process_with_range(self, table_service, sample_pdf_path):
        """Test page range determination with specified range."""
        with patch('app.services.table_extraction_service.fitz') as mock_fitz:
            mock_doc = Mock()
            mock_fitz.open.return_value = mock_doc
            mock_doc.__len__.return_value = 10
            
            pages = table_service._get_pages_to_process(sample_pdf_path, (3, 7))
            
            assert pages == [3, 4, 5, 6, 7]
    
    def test_get_pages_to_process_invalid_range(self, table_service, sample_pdf_path):
        """Test page range determination with invalid range."""
        with patch('app.services.table_extraction_service.fitz') as mock_fitz:
            mock_doc = Mock()
            mock_fitz.open.return_value = mock_doc
            mock_doc.__len__.return_value = 5
            
            # Start page greater than end page
            pages = table_service._get_pages_to_process(sample_pdf_path, (8, 3))
            
            assert pages == []
    
    @patch('app.services.table_extraction_service.camelot')
    def test_detect_tables_camelot_lattice_method(self, mock_camelot, table_service, sample_pdf_path, sample_table_data):
        """Test camelot lattice method for bordered tables."""
        mock_table = Mock()
        mock_table.df = sample_table_data
        mock_table.page = 1
        mock_table.accuracy = 0.98
        mock_table._bbox = [50, 100, 300, 200]
        
        mock_camelot.read_pdf.return_value = [mock_table]
        
        result = table_service._detect_tables_camelot(sample_pdf_path, [1, 2])
        
        assert len(result) == 1
        assert result[0]['method'] == 'camelot_lattice'
        assert result[0]['page'] == 1
        assert result[0]['accuracy'] == 0.98
        
        # Verify lattice method was used
        mock_camelot.read_pdf.assert_called_with(
            str(sample_pdf_path),
            pages='1,2',
            flavor='lattice',
            line_scale=40
        )
    
    @patch('app.services.table_extraction_service.camelot')
    def test_detect_tables_camelot_stream_fallback(self, mock_camelot, table_service, sample_pdf_path, sample_table_data):
        """Test camelot stream method fallback for borderless tables."""
        # Mock lattice method failure
        mock_camelot.read_pdf.side_effect = [
            [],  # Lattice returns empty
            [Mock(df=sample_table_data, page=1, accuracy=0.85, _bbox=[0, 0, 100, 100])]  # Stream succeeds
        ]
        
        result = table_service._detect_tables_camelot(sample_pdf_path, [1])
        
        assert len(result) == 1
        assert result[0]['method'] == 'camelot_stream'
        
        # Verify both methods were called
        assert mock_camelot.read_pdf.call_count == 2
    
    @patch('app.services.table_extraction_service.tabula')
    def test_detect_tables_tabula_method(self, mock_tabula, table_service, sample_pdf_path, sample_table_data):
        """Test tabula method for image-based PDFs."""
        mock_tabula.read_pdf.return_value = [sample_table_data]
        
        result = table_service._detect_tables_tabula(sample_pdf_path, [1, 2])
        
        assert len(result) == 2  # Two pages processed
        assert all(table['method'] == 'tabula' for table in result)
        
        # Verify tabula was called for each page
        assert mock_tabula.read_pdf.call_count == 2
    
    def test_validate_table_data_good_table(self, table_service, sample_table_data):
        """Test table validation with good quality table."""
        table_dict = {
            'dataframe': sample_table_data,
            'page': 1,
            'method': 'camelot',
            'accuracy': 0.95
        }
        
        result = table_service._validate_table_data([table_dict])
        
        assert len(result) == 1
        assert 'confidence' in result[0]
        assert result[0]['confidence'] > 0.3
    
    def test_validate_table_data_too_small(self, table_service):
        """Test table validation rejects tables that are too small."""
        small_table = pd.DataFrame({'A': [1]})  # Only 1 row, 1 column
        
        table_dict = {
            'dataframe': small_table,
            'page': 1,
            'method': 'camelot'
        }
        
        result = table_service._validate_table_data([table_dict])
        
        assert len(result) == 0  # Should be filtered out
    
    def test_validate_table_data_mostly_empty(self, table_service):
        """Test table validation rejects mostly empty tables."""
        empty_table = pd.DataFrame({
            'A': [None, None, None, None],
            'B': [None, None, None, 'data'],
            'C': [None, None, None, None]
        })
        
        table_dict = {
            'dataframe': empty_table,
            'page': 1,
            'method': 'tabula'
        }
        
        result = table_service._validate_table_data([table_dict])
        
        assert len(result) == 0  # Should be filtered out due to low data density
    
    def test_calculate_table_confidence_high_quality(self, table_service, sample_table_data):
        """Test confidence calculation for high-quality table."""
        confidence = table_service._calculate_table_confidence(sample_table_data)
        
        assert 0.7 <= confidence <= 1.0  # Should be high confidence
    
    def test_calculate_table_confidence_empty_table(self, table_service):
        """Test confidence calculation for empty table."""
        empty_table = pd.DataFrame()
        
        confidence = table_service._calculate_table_confidence(empty_table)
        
        assert confidence == 0.0
    
    def test_calculate_table_confidence_empty_string_cells(self, table_service):
        """Test confidence calculation for table with empty string cells (division by zero case)."""
        empty_string_table = pd.DataFrame({
            'A': ['', '', ''],
            'B': ['', '', ''],
            'C': ['', '', '']
        })
        
        confidence = table_service._calculate_table_confidence(empty_string_table)
        
        # Should handle division by zero gracefully and return a valid confidence score
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0
    
    def test_export_tables_to_csv_success(self, table_service, sample_table_data):
        """Test successful CSV export of tables."""
        tables = [{
            'dataframe': sample_table_data,
            'page': 1,
            'method': 'camelot'
        }]
        
        with patch.object(table_service.temp_file_manager, 'downloads_dir') as mock_downloads_dir:
            mock_file_path = Path('/tmp/table_page_1_1.csv')
            mock_downloads_dir.__truediv__.return_value = mock_file_path
            
            with patch('pandas.DataFrame.to_csv') as mock_to_csv:
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 2048
                    
                    result = table_service._export_tables_to_csv(tables, delimiter=';')
        
        assert len(result) == 1
        assert result[0]['filename'] == 'table_page_1_1.csv'
        assert result[0]['file_size'] == 2048
        
        # Verify CSV was written with correct delimiter
        mock_to_csv.assert_called_once()
        args, kwargs = mock_to_csv.call_args
        assert kwargs['sep'] == ';'
        assert kwargs['encoding'] == 'utf-8'
        assert kwargs['index'] is False
        assert kwargs['header'] is False
    
    def test_export_tables_to_csv_with_encoding(self, table_service, sample_table_data):
        """Test CSV export with different encoding."""
        tables = [{
            'dataframe': sample_table_data,
            'page': 2,
            'method': 'tabula'
        }]
        
        with patch.object(table_service.temp_file_manager, 'downloads_dir'):
            with patch('pandas.DataFrame.to_csv') as mock_to_csv:
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value.st_size = 1536
                    
                    table_service._export_tables_to_csv(tables, encoding='latin-1')
        
        # Verify encoding was used
        args, kwargs = mock_to_csv.call_args
        assert kwargs['encoding'] == 'latin-1'
    
    def test_format_table_metadata(self, table_service, sample_table_data):
        """Test table metadata formatting."""
        table_dict = {
            'dataframe': sample_table_data,
            'method': 'camelot_lattice',
            'accuracy': 0.92,
            'bbox': [100, 200, 400, 500]
        }
        
        metadata = table_service._format_table_metadata(table_dict, 3, 1)
        
        assert metadata['page'] == 3
        assert metadata['table_index'] == 1
        assert metadata['rows'] == 3  # sample_table_data has 3 rows
        assert metadata['columns'] == 4  # sample_table_data has 4 columns
        assert metadata['method'] == 'camelot_lattice'
        assert metadata['accuracy'] == 0.92
        assert metadata['bbox'] == [100, 200, 400, 500]
        assert 'data_density' in metadata
        assert 'has_headers' in metadata
    
    def test_detect_headers_with_headers(self, table_service):
        """Test header detection for table with headers."""
        table_with_headers = pd.DataFrame({
            'Full Name': ['John Doe', 'Jane Smith'],
            'Email Address': ['john@email.com', 'jane@email.com'],
            'Phone Number': ['123-456-7890', '098-765-4321']
        })
        
        has_headers = table_service._detect_headers(table_with_headers)
        
        assert has_headers is True
    
    def test_detect_headers_without_headers(self, table_service):
        """Test header detection for table without headers."""
        table_no_headers = pd.DataFrame({
            0: [1, 2, 3],
            1: [4, 5, 6],
            2: [7, 8, 9]
        })
        
        has_headers = table_service._detect_headers(table_no_headers)
        
        assert has_headers is False
    
    def test_detect_headers_empty_table(self, table_service):
        """Test header detection for empty table."""
        empty_table = pd.DataFrame()
        
        has_headers = table_service._detect_headers(empty_table)
        
        assert has_headers is False
    
    @patch('app.services.table_extraction_service.camelot')
    @patch('app.services.table_extraction_service.tabula')
    def test_extract_tables_missing_dependencies(self, mock_tabula, mock_camelot, table_service, sample_pdf_path):
        """Test handling of missing dependencies."""
        # Remove the import patches to simulate ImportError
        with patch('app.services.table_extraction_service.camelot', side_effect=ImportError("No module named 'camelot'")):
            result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is False
        assert 'dependencies not installed' in result['error']
    
    def test_extract_tables_with_custom_delimiter(self, table_service, sample_pdf_path, sample_table_data):
        """Test table extraction with custom CSV delimiter."""
        with patch('app.services.table_extraction_service.fitz'):
            with patch('app.services.table_extraction_service.camelot') as mock_camelot:
                mock_table = Mock()
                mock_table.df = sample_table_data
                mock_table.page = 1
                mock_camelot.read_pdf.return_value = [mock_table]
                
                with patch.object(table_service.temp_file_manager, 'downloads_dir'):
                    with patch('pandas.DataFrame.to_csv') as mock_to_csv:
                        with patch('pathlib.Path.stat') as mock_stat:
                            mock_stat.return_value.st_size = 1024
                            
                            result = table_service.extract_tables(
                                sample_pdf_path,
                                csv_delimiter='|'
                            )
        
        assert result['success'] is True
        mock_to_csv.assert_called_once()
        args, kwargs = mock_to_csv.call_args
        assert kwargs['sep'] == '|'
    
    def test_extract_tables_file_not_found(self, table_service):
        """Test error handling when PDF file doesn't exist."""
        non_existent_file = Path('/non/existent/file.pdf')
        
        # This should be handled by the error decorator and file validation
        with patch('app.services.table_extraction_service.fitz') as mock_fitz:
            mock_fitz.open.side_effect = Exception("File not found")
            
            result = table_service.extract_tables(non_existent_file)
        
        assert result['success'] is False
        assert 'error' in result
    
    def test_extract_tables_corrupted_pdf(self, table_service, sample_pdf_path):
        """Test handling of corrupted PDF files."""
        with patch('app.services.table_extraction_service.fitz') as mock_fitz:
            mock_fitz.open.side_effect = Exception("Invalid PDF structure")
            
            result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is False
        assert 'error' in result
    
    @patch('app.services.table_extraction_service.camelot')
    def test_extract_tables_camelot_exception(self, mock_camelot, table_service, sample_pdf_path):
        """Test handling of camelot processing exceptions."""
        with patch('app.services.table_extraction_service.fitz'):
            mock_camelot.read_pdf.side_effect = Exception("Camelot processing error")
            
            with patch('app.services.table_extraction_service.tabula') as mock_tabula:
                mock_tabula.read_pdf.return_value = []  # Empty fallback
                
                result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is True  # Should succeed with tabula fallback
        assert result['statistics']['extraction_method'] == 'tabula'
    
    def test_extract_tables_large_document_performance(self, table_service, sample_pdf_path):
        """Test performance considerations for large documents."""
        with patch('app.services.table_extraction_service.fitz') as mock_fitz:
            # Mock a large document (100 pages)
            mock_doc = Mock()
            mock_fitz.open.return_value = mock_doc
            mock_doc.__len__.return_value = 100
            
            with patch('app.services.table_extraction_service.camelot') as mock_camelot:
                # Mock many tables
                mock_tables = [Mock(df=pd.DataFrame({'A': [1, 2], 'B': [3, 4]}), page=i, accuracy=0.9) 
                              for i in range(1, 21)]  # 20 tables
                mock_camelot.read_pdf.return_value = mock_tables
                
                with patch.object(table_service.temp_file_manager, 'downloads_dir'):
                    with patch('pandas.DataFrame.to_csv'):
                        with patch('pathlib.Path.stat') as mock_stat:
                            mock_stat.return_value.st_size = 1024
                            
                            result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is True
        assert result['statistics']['tables_detected'] == 20
        # Verify that processing was attempted for all pages
        mock_camelot.read_pdf.assert_called()
    
    def test_memory_management_multiple_large_tables(self, table_service, sample_pdf_path):
        """Test memory management when processing multiple large tables."""
        # Create a large table
        large_table_data = pd.DataFrame({
            f'col_{i}': list(range(1000)) for i in range(10)
        })
        
        with patch('app.services.table_extraction_service.fitz'):
            with patch('app.services.table_extraction_service.camelot') as mock_camelot:
                # Mock multiple large tables
                mock_tables = [Mock(df=large_table_data, page=1, accuracy=0.9) for _ in range(5)]
                mock_camelot.read_pdf.return_value = mock_tables
                
                with patch.object(table_service.temp_file_manager, 'downloads_dir'):
                    with patch('pandas.DataFrame.to_csv'):
                        with patch('pathlib.Path.stat') as mock_stat:
                            mock_stat.return_value.st_size = 50000
                            
                            result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is True
        assert len(result['files']) == 5  # All tables should be exported
    
    def test_unicode_and_special_characters(self, table_service, sample_pdf_path):
        """Test handling of Unicode and special characters in tables."""
        unicode_table = pd.DataFrame({
            'Name': ['Müller', 'José', 'François'],
            'City': ['München', 'São Paulo', 'Montréal'],
            'Notes': ['Special chars: ©®™', '数字: 12345', 'Symbols: →←↑↓']
        })
        
        with patch('app.services.table_extraction_service.fitz'):
            with patch('app.services.table_extraction_service.camelot') as mock_camelot:
                mock_table = Mock(df=unicode_table, page=1, accuracy=0.9)
                mock_camelot.read_pdf.return_value = [mock_table]
                
                with patch.object(table_service.temp_file_manager, 'downloads_dir'):
                    with patch('pandas.DataFrame.to_csv') as mock_to_csv:
                        with patch('pathlib.Path.stat') as mock_stat:
                            mock_stat.return_value.st_size = 2048
                            
                            result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is True
        # Verify UTF-8 encoding was used for CSV export
        mock_to_csv.assert_called_once()
        args, kwargs = mock_to_csv.call_args
        assert kwargs['encoding'] == 'utf-8'
    
    def test_extract_tables_no_tables_found(self, table_service, sample_pdf_path):
        """Test handling when no tables are found in the PDF."""
        with patch('app.services.table_extraction_service.fitz'):
            with patch('app.services.table_extraction_service.camelot') as mock_camelot:
                mock_camelot.read_pdf.return_value = []  # No tables found
                
                with patch('app.services.table_extraction_service.tabula') as mock_tabula:
                    mock_tabula.read_pdf.return_value = []  # No tables found
                    
                    result = table_service.extract_tables(sample_pdf_path)
        
        assert result['success'] is True  # Success even with no tables
        assert len(result['tables']) == 0
        assert len(result['files']) == 0
        assert result['statistics']['tables_detected'] == 0
        assert result['statistics']['tables_validated'] == 0
    
    @pytest.mark.parametrize("extraction_method", ['auto', 'camelot', 'tabula'])
    def test_extract_tables_different_methods(self, table_service, sample_pdf_path, sample_table_data, extraction_method):
        """Test extraction with different methods specified."""
        with patch('app.services.table_extraction_service.fitz'):
            with patch('app.services.table_extraction_service.camelot') as mock_camelot:
                mock_table = Mock(df=sample_table_data, page=1, accuracy=0.9)
                mock_camelot.read_pdf.return_value = [mock_table]
                
                with patch('app.services.table_extraction_service.tabula') as mock_tabula:
                    mock_tabula.read_pdf.return_value = [sample_table_data]
                    
                    with patch.object(table_service.temp_file_manager, 'downloads_dir'):
                        with patch('pandas.DataFrame.to_csv'):
                            with patch('pathlib.Path.stat') as mock_stat:
                                mock_stat.return_value.st_size = 1024
                                
                                result = table_service.extract_tables(
                                    sample_pdf_path,
                                    extraction_method=extraction_method
                                )
        
        assert result['success'] is True
        
        if extraction_method == 'camelot':
            assert result['statistics']['extraction_method'] == 'camelot'
        elif extraction_method == 'tabula':
            assert result['statistics']['extraction_method'] == 'tabula'
        else:  # auto
            assert result['statistics']['extraction_method'] in ['camelot', 'tabula']