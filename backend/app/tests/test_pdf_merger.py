import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter

from app.services.pdf_merger import PDFMerger
from app.services.temp_file_manager import TempFileManager


class TestPDFMerger:
    """Test suite for PDFMerger with comprehensive metadata preservation and integrity testing."""
    
    @pytest.fixture
    def temp_session_dir(self):
        """Create temporary session directory for tests."""
        temp_dir = tempfile.mkdtemp()
        session_id = "test_session_merger_123"
        session_path = Path(temp_dir) / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        downloads_path = session_path / "downloads"
        downloads_path.mkdir(parents=True, exist_ok=True)
        
        with patch.object(TempFileManager, 'get_session_path', return_value=downloads_path):
            yield session_id, downloads_path
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_pdf_files(self):
        """Create multiple mock PDF files for testing."""
        temp_files = []
        for i in range(3):
            temp_file = tempfile.NamedTemporaryFile(suffix=f'_test_{i}.pdf', delete=False)
            temp_path = Path(temp_file.name)
            temp_file.close()
            temp_files.append(temp_path)
        
        yield temp_files
        
        for temp_path in temp_files:
            if temp_path.exists():
                temp_path.unlink()
    
    @pytest.fixture
    def merger(self, temp_session_dir):
        """Create PDFMerger instance with test session."""
        session_id, _ = temp_session_dir
        return PDFMerger(session_id)
    
    def test_init_creates_merger_with_session_id(self):
        """Test PDFMerger initialization with session ID."""
        session_id = "test_session_789"
        merger = PDFMerger(session_id)
        
        assert merger.session_id == session_id
    
    @patch('app.services.pdf_merger.validate_pdf_file')
    def test_merge_documents_basic_functionality(self, mock_validate_pdf, merger, mock_pdf_files, temp_session_dir):
        """Test basic document merging functionality."""
        session_id, downloads_path = temp_session_dir
        
        # Mock PDF readers with different page counts
        mock_readers = []
        for i, pages in enumerate([3, 5, 2]):  # 3 PDFs with 3, 5, 2 pages
            mock_reader = Mock()
            mock_reader.pages = [Mock() for _ in range(pages)]
            mock_reader.is_encrypted = False
            mock_reader.metadata = {'/Title': f'Document {i+1}', '/Author': f'Author {i+1}'}
            mock_readers.append(mock_reader)
        
        mock_validate_pdf.return_value = {'is_valid': True}
        
        with patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter') as mock_writer_class, \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='merged123'):
            
            mock_writer = Mock()
            mock_writer_class.return_value = mock_writer
            
            # Mock file stats
            for i, file_path in enumerate(mock_pdf_files):
                with patch.object(file_path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = (i + 1) * 1000  # Different file sizes
            
            result = merger.merge_documents(mock_pdf_files, preserve_metadata=True)
            
            assert result['success'] is True
            assert result['source_count'] == 3
            assert result['total_pages'] == 10  # 3 + 5 + 2
            assert result['metadata_preserved'] is True
            assert result['merge_strategy'] == 'sequential'
            
            # Verify all pages were added to writer
            expected_add_page_calls = 10
            assert mock_writer.add_page.call_count == expected_add_page_calls
    
    def test_merge_documents_custom_filename(self, merger, mock_pdf_files):
        """Test merging with custom output filename."""
        custom_filename = "my_merged_document.pdf"
        
        mock_readers = [Mock() for _ in range(2)]
        for reader in mock_readers:
            reader.pages = [Mock()]
            reader.is_encrypted = False
            reader.metadata = {}
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='custom123'):
            
            result = merger.merge_documents(mock_pdf_files[:2], output_filename=custom_filename)
            
            assert result['success'] is True
            assert result['output_filename'] == custom_filename
    
    def test_merge_documents_encrypted_pdf_error(self, merger, mock_pdf_files):
        """Test error handling when merging encrypted PDFs."""
        mock_reader_encrypted = Mock()
        mock_reader_encrypted.pages = [Mock()]
        mock_reader_encrypted.is_encrypted = True
        
        mock_reader_normal = Mock()
        mock_reader_normal.pages = [Mock()]
        mock_reader_normal.is_encrypted = False
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=[mock_reader_encrypted, mock_reader_normal]):
            
            with pytest.raises(ValueError, match="Cannot merge encrypted PDF"):
                merger.merge_documents(mock_pdf_files[:2])
    
    def test_merge_documents_metadata_sequential_strategy(self, merger, mock_pdf_files):
        """Test metadata preservation with sequential strategy."""
        mock_readers = []
        for i in range(2):
            mock_reader = Mock()
            mock_reader.pages = [Mock()]
            mock_reader.is_encrypted = False
            mock_reader.metadata = {
                '/Title': f'Document {i+1}',
                '/Author': f'Author {i+1}',
                '/Subject': f'Subject {i+1}'
            }
            mock_readers.append(mock_reader)
        
        mock_writer = Mock()
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter', return_value=mock_writer), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='seq123'), \
             patch('app.services.pdf_merger.datetime') as mock_datetime:
            
            mock_datetime.now.return_value.strftime.return_value = "20240101120000"
            
            result = merger.merge_documents(
                mock_pdf_files[:2], 
                merge_strategy="sequential",
                preserve_metadata=True
            )
            
            assert result['success'] is True
            assert result['merge_strategy'] == 'sequential'
            
            # Verify metadata was added (should use first document's metadata as base)
            mock_writer.add_metadata.assert_called_once()
            added_metadata = mock_writer.add_metadata.call_args[0][0]
            assert '/Title' in added_metadata
            assert 'Merged from 2 documents' in added_metadata['/Subject']
            assert added_metadata['/ModDate'] == 'D:20240101120000'
    
    def test_merge_documents_metadata_aggregate_strategy(self, merger, mock_pdf_files):
        """Test metadata preservation with aggregate strategy."""
        mock_readers = []
        metadata_list = [
            {'/Title': 'First Doc', '/Author': 'Author A', '/Subject': 'Math'},
            {'/Title': 'Second Doc', '/Author': 'Author B', '/Subject': 'Science'},
            {'/Title': 'Third Doc', '/Author': 'Author A', '/Subject': 'History'}
        ]
        
        for i, metadata in enumerate(metadata_list):
            mock_reader = Mock()
            mock_reader.pages = [Mock()]
            mock_reader.is_encrypted = False
            mock_reader.metadata = metadata
            mock_readers.append(mock_reader)
        
        mock_writer = Mock()
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter', return_value=mock_writer), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='agg123'), \
             patch('app.services.pdf_merger.datetime') as mock_datetime:
            
            mock_datetime.now.return_value.strftime.return_value = "20240101120000"
            
            result = merger.merge_documents(
                mock_pdf_files,
                merge_strategy="aggregate",
                preserve_metadata=True
            )
            
            assert result['success'] is True
            
            # Verify aggregated metadata
            mock_writer.add_metadata.assert_called_once()
            added_metadata = mock_writer.add_metadata.call_args[0][0]
            
            # Should combine titles
            assert added_metadata['/Title'] == 'First Doc + Second Doc + Third Doc'
            # Should deduplicate authors
            assert 'Author A' in added_metadata['/Author']
            assert 'Author B' in added_metadata['/Author']
            # Should combine subjects
            assert 'Math' in added_metadata['/Subject']
            assert 'Science' in added_metadata['/Subject']
            assert 'History' in added_metadata['/Subject']
            assert added_metadata['/Creator'] == 'PDF Merger Service'
    
    def test_merge_documents_no_metadata_preservation(self, merger, mock_pdf_files):
        """Test merging without metadata preservation."""
        mock_readers = [Mock() for _ in range(2)]
        for reader in mock_readers:
            reader.pages = [Mock()]
            reader.is_encrypted = False
            reader.metadata = {'/Title': 'Test'}
        
        mock_writer = Mock()
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter', return_value=mock_writer), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='nometa123'):
            
            result = merger.merge_documents(mock_pdf_files[:2], preserve_metadata=False)
            
            assert result['success'] is True
            assert result['metadata_preserved'] is False
            
            # Should not call metadata methods
            mock_writer.add_metadata.assert_not_called()
    
    def test_validate_merge_inputs_insufficient_files(self, merger):
        """Test validation error for insufficient files."""
        single_file = [Path("single.pdf")]
        
        with pytest.raises(ValueError, match="At least 2 files required"):
            merger._validate_merge_inputs(single_file)
    
    def test_validate_merge_inputs_too_many_files(self, merger):
        """Test validation error for too many files."""
        many_files = [Path(f"file{i}.pdf") for i in range(25)]  # 25 files > 20 limit
        
        with pytest.raises(ValueError, match="Too many files for merging"):
            merger._validate_merge_inputs(many_files)
    
    def test_validate_merge_inputs_nonexistent_file(self, merger):
        """Test validation error for nonexistent files."""
        files = [Path("nonexistent1.pdf"), Path("nonexistent2.pdf")]
        
        with pytest.raises(ValueError, match="File not found"):
            merger._validate_merge_inputs(files)
    
    def test_validate_merge_inputs_invalid_pdf(self, merger, mock_pdf_files):
        """Test validation error for invalid PDF files."""
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': False, 'error': 'Corrupted PDF'}):
            with pytest.raises(ValueError, match="Invalid PDF file"):
                merger._validate_merge_inputs(mock_pdf_files[:2])
    
    def test_validate_merge_inputs_file_too_large(self, merger, mock_pdf_files):
        """Test validation error for files that are too large."""
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}):
            # Mock file size > 50MB
            with patch.object(mock_pdf_files[0], 'stat') as mock_stat:
                mock_stat.return_value.st_size = 60 * 1024 * 1024  # 60MB
                
                with pytest.raises(ValueError, match="File too large"):
                    merger._validate_merge_inputs(mock_pdf_files[:2])
    
    def test_validate_merge_inputs_total_size_too_large(self, merger, mock_pdf_files):
        """Test validation error when total size exceeds limit."""
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}):
            # Mock each file as 40MB (3 files = 120MB > 100MB limit)
            for file_path in mock_pdf_files:
                with patch.object(file_path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 40 * 1024 * 1024  # 40MB each
            
            with pytest.raises(ValueError, match="Total file size too large"):
                merger._validate_merge_inputs(mock_pdf_files)
    
    def test_analyze_source_documents_comprehensive(self, merger, mock_pdf_files):
        """Test comprehensive source document analysis."""
        mock_readers = []
        expected_metadata = [
            {'/Title': 'Doc 1', '/Author': 'Author 1'},
            {'/Title': 'Doc 2', '/Author': 'Author 2'},
            {}  # No metadata
        ]
        
        for i, metadata in enumerate(expected_metadata):
            mock_reader = Mock()
            mock_reader.pages = [Mock() for _ in range(i + 2)]  # 2, 3, 4 pages
            mock_reader.is_encrypted = i == 1  # Second PDF encrypted
            mock_reader.metadata = metadata
            mock_reader.pdf_header = f'%PDF-1.{4 + i}'
            mock_reader.outline = [Mock()] if i == 0 else None
            mock_reader.xmp_metadata = Mock() if i < 2 else None
            mock_readers.append(mock_reader)
        
        with patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', side_effect=['hash1', 'hash2', 'hash3']):
            
            # Mock file stats
            for i, file_path in enumerate(mock_pdf_files):
                with patch.object(file_path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = (i + 1) * 1000
            
            analysis = merger._analyze_source_documents(mock_pdf_files)
            
            assert len(analysis) == 3
            
            # Check first document analysis
            doc1 = analysis[0]
            assert doc1['page_count'] == 2
            assert doc1['encrypted'] is False
            assert doc1['metadata'] == {'/Title': 'Doc 1', '/Author': 'Author 1'}
            assert doc1['pdf_version'] == '%PDF-1.4'
            assert doc1['has_outline'] is True
            assert doc1['has_xmp_metadata'] is True
            assert doc1['sha256_hash'] == 'hash1'
            assert doc1['file_size'] == 1000
            
            # Check encrypted document
            doc2 = analysis[1]
            assert doc2['encrypted'] is True
            
            # Check document without metadata
            doc3 = analysis[2]
            assert doc3['metadata'] == {}
            assert doc3['has_outline'] is False
            assert doc3['has_xmp_metadata'] is False
    
    def test_analyze_source_documents_error_handling(self, merger, mock_pdf_files):
        """Test error handling during source document analysis."""
        with patch('app.services.pdf_merger.PdfReader', side_effect=Exception("Cannot read PDF")):
            analysis = merger._analyze_source_documents(mock_pdf_files[:1])
            
            assert len(analysis) == 1
            assert 'error' in analysis[0]
            assert analysis[0]['error'] == "Cannot read PDF"
    
    def test_calculate_output_integrity_comprehensive(self, merger, mock_pdf_files, temp_session_dir):
        """Test comprehensive output integrity calculation."""
        session_id, downloads_path = temp_session_dir
        output_path = downloads_path / "merged_output.pdf"
        
        # Mock output file
        with patch.object(output_path, 'stat') as mock_stat:
            mock_stat.return_value.st_size = 5000
        
        # Mock source info
        source_info = [
            {'file_size': 1000, 'page_count': 2},
            {'file_size': 2000, 'page_count': 3},
            {'file_size': 1500, 'page_count': 2}
        ]
        
        # Mock output PDF reader
        mock_output_reader = Mock()
        mock_output_reader.pages = [Mock() for _ in range(7)]  # Total expected pages
        
        with patch('app.services.pdf_merger.PdfReader', return_value=mock_output_reader), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='output_hash_123'):
            
            statistics = merger._calculate_output_integrity(output_path, source_info)
            
            assert statistics['output_size'] == 5000
            assert statistics['output_hash'] == 'output_hash_123'
            assert statistics['total_source_size'] == 4500  # 1000 + 2000 + 1500
            assert statistics['size_change'] == 500  # 5000 - 4500
            assert statistics['expected_pages'] == 7  # 2 + 3 + 2
            assert statistics['actual_pages'] == 7
            assert statistics['page_integrity'] is True
            assert statistics['size_efficiency'] == pytest.approx(111.11, rel=0.01)  # 5000/4500 * 100
            assert statistics['compression_ratio'] == pytest.approx(0.9, rel=0.01)  # 4500/5000
    
    def test_calculate_output_integrity_page_mismatch(self, merger, mock_pdf_files, temp_session_dir):
        """Test integrity calculation when page counts don't match."""
        session_id, downloads_path = temp_session_dir
        output_path = downloads_path / "merged_output.pdf"
        
        with patch.object(output_path, 'stat') as mock_stat:
            mock_stat.return_value.st_size = 3000
        
        source_info = [
            {'file_size': 1000, 'page_count': 2},
            {'file_size': 1000, 'page_count': 3}
        ]
        
        # Mock output with fewer pages than expected
        mock_output_reader = Mock()
        mock_output_reader.pages = [Mock() for _ in range(4)]  # Expected 5, got 4
        
        with patch('app.services.pdf_merger.PdfReader', return_value=mock_output_reader), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='mismatch_hash'):
            
            statistics = merger._calculate_output_integrity(output_path, source_info)
            
            assert statistics['expected_pages'] == 5
            assert statistics['actual_pages'] == 4
            assert statistics['page_integrity'] is False
    
    def test_calculate_output_integrity_error_handling(self, merger, mock_pdf_files, temp_session_dir):
        """Test error handling in output integrity calculation."""
        session_id, downloads_path = temp_session_dir
        output_path = downloads_path / "merged_output.pdf"
        
        with patch.object(output_path, 'stat', side_effect=Exception("Cannot stat file")):
            statistics = merger._calculate_output_integrity(output_path, [])
            
            assert 'error' in statistics
            assert statistics['error'] == "Cannot stat file"
    
    def test_generate_merge_report_comprehensive(self, merger, mock_pdf_files, temp_session_dir):
        """Test comprehensive merge report generation."""
        session_id, downloads_path = temp_session_dir
        output_path = downloads_path / "test_merged.pdf"
        
        merge_statistics = {
            'total_source_size': 5000,
            'output_size': 4800,
            'size_change': -200,
            'expected_pages': 10,
            'actual_pages': 10,
            'page_integrity': True,
            'size_efficiency': 96.0,
            'compression_ratio': 1.04
        }
        
        with patch('app.services.pdf_merger.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            
            report = merger._generate_merge_report(mock_pdf_files, output_path, merge_statistics)
            
            # Check merge summary
            assert report['merge_summary']['source_count'] == 3
            assert report['merge_summary']['merge_timestamp'] == "2024-01-01T12:00:00"
            assert report['merge_summary']['output_file'] == "test_merged.pdf"
            
            # Check size analysis
            assert report['size_analysis']['total_input_size'] == 5000
            assert report['size_analysis']['output_size'] == 4800
            assert report['size_analysis']['size_change'] == -200
            assert report['size_analysis']['compression_achieved'] is True
            
            # Check page analysis
            assert report['page_analysis']['expected_pages'] == 10
            assert report['page_analysis']['actual_pages'] == 10
            assert report['page_analysis']['page_integrity'] is True
            
            # Check quality metrics
            assert report['quality_metrics']['size_efficiency'] == 96.0
            assert report['quality_metrics']['compression_ratio'] == 1.04
            assert report['quality_metrics']['integrity_verified'] is True
    
    def test_generate_output_filename_two_files(self, merger, mock_pdf_files):
        """Test filename generation for two files."""
        mock_pdf_files[0] = mock_pdf_files[0].with_name("document_one.pdf")
        mock_pdf_files[1] = mock_pdf_files[1].with_name("document_two.pdf")
        
        with patch.object(mock_pdf_files[0], 'stem', 'document_one'), \
             patch.object(mock_pdf_files[1], 'stem', 'document_two'):
            
            filename = merger._generate_output_filename(mock_pdf_files[:2])
            expected = "document_one_document_two_merged.pdf"
            assert filename == expected
    
    def test_generate_output_filename_multiple_files(self, merger, mock_pdf_files):
        """Test filename generation for multiple files."""
        with patch('app.services.pdf_merger.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
            
            filename = merger._generate_output_filename(mock_pdf_files)  # 3 files
            expected = "merged_3_files_20240101_120000.pdf"
            assert filename == expected
    
    @patch('builtins.open')
    @patch('hashlib.sha256')
    def test_calculate_file_hash_success(self, mock_sha256, mock_open, merger, mock_pdf_files):
        """Test successful file hash calculation."""
        mock_hash = Mock()
        mock_hash.hexdigest.return_value = "file_hash_abc123"
        mock_sha256.return_value = mock_hash
        
        mock_file = Mock()
        mock_file.read.side_effect = [b"data1", b"data2", b""]  # EOF
        mock_open.return_value.__enter__.return_value = mock_file
        
        result = merger._calculate_file_hash(mock_pdf_files[0])
        
        assert result == "file_hash_abc123"
        mock_hash.update.assert_any_call(b"data1")
        mock_hash.update.assert_any_call(b"data2")
    
    def test_calculate_file_hash_error_handling(self, merger, mock_pdf_files):
        """Test file hash calculation error handling."""
        with patch('builtins.open', side_effect=IOError("Permission denied")), \
             patch('app.services.pdf_merger.logger') as mock_logger:
            
            result = merger._calculate_file_hash(mock_pdf_files[0])
            
            assert result == ""
            mock_logger.error.assert_called_once()
    
    def test_merge_metadata_error_handling(self, merger):
        """Test metadata merging error handling."""
        mock_readers = [Mock()]
        mock_readers[0].metadata = None  # No metadata
        
        mock_writer = Mock()
        mock_writer.add_metadata.side_effect = Exception("Metadata error")
        
        with patch('app.services.pdf_merger.logger') as mock_logger:
            # Should not raise exception, just log warning
            merger._merge_metadata(mock_readers, mock_writer, 'sequential')
            mock_logger.warning.assert_called_once()
    
    def test_preserve_document_structure_with_outline(self, merger):
        """Test document structure preservation with outline."""
        mock_reader = Mock()
        mock_reader.outline = [Mock()]  # Has outline
        
        mock_writer = Mock()
        
        with patch('app.services.pdf_merger.logger') as mock_logger:
            merger._preserve_document_structure([mock_reader], mock_writer)
            # Currently just passes, but should not raise error
            mock_logger.warning.assert_not_called()
    
    def test_preserve_document_structure_error_handling(self, merger):
        """Test document structure preservation error handling."""
        mock_reader = Mock()
        mock_reader.outline = Exception("Outline error")  # Simulate error accessing outline
        
        mock_writer = Mock()
        
        with patch('app.services.pdf_merger.logger') as mock_logger:
            merger._preserve_document_structure([mock_reader], mock_writer)
            # Should handle error gracefully
            mock_logger.warning.assert_called_once()
    
    def test_merge_documents_processing_time_tracking(self, merger, mock_pdf_files):
        """Test that processing time can be tracked externally."""
        mock_readers = [Mock() for _ in range(2)]
        for reader in mock_readers:
            reader.pages = [Mock()]
            reader.is_encrypted = False
            reader.metadata = {}
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='time123'):
            
            result = merger.merge_documents(mock_pdf_files[:2])
            
            # Processing time should be None (set by caller)
            assert result['processing_time'] is None
            assert 'processing_time' in result
    
    def test_merge_documents_file_integrity_verification(self, merger, mock_pdf_files, temp_session_dir):
        """Test that file integrity is properly verified after merge."""
        session_id, downloads_path = temp_session_dir
        
        mock_readers = [Mock() for _ in range(2)]
        for i, reader in enumerate(mock_readers):
            reader.pages = [Mock() for _ in range(i + 2)]  # 2 and 3 pages
            reader.is_encrypted = False
            reader.metadata = {}
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=mock_readers), \
             patch('app.services.pdf_merger.PdfWriter') as mock_writer_class, \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_merger.PDFMerger._calculate_output_integrity') as mock_integrity:
            
            mock_integrity.return_value = {
                'output_size': 3000,
                'output_hash': 'integrity_hash',
                'page_integrity': True,
                'total_source_size': 2000,
                'size_change': 1000,
                'size_efficiency': 150.0,
                'expected_pages': 5,
                'actual_pages': 5,
                'compression_ratio': 0.67
            }
            
            result = merger.merge_documents(mock_pdf_files[:2])
            
            assert result['success'] is True
            assert 'statistics' in result
            assert result['statistics']['page_integrity'] is True
            assert result['statistics']['output_hash'] == 'integrity_hash'
            
            # Verify integrity calculation was called
            mock_integrity.assert_called_once()