import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from PyPDF2 import PdfReader, PdfWriter

from app.services.pdf_splitter import PDFSplitter
from app.services.temp_file_manager import TempFileManager


class TestPDFSplitter:
    """Test suite for PDFSplitter with comprehensive edge case coverage."""
    
    @pytest.fixture
    def temp_session_dir(self):
        """Create temporary session directory for tests."""
        temp_dir = tempfile.mkdtemp()
        session_id = "test_session_123"
        session_path = Path(temp_dir) / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        downloads_path = session_path / "downloads"
        downloads_path.mkdir(parents=True, exist_ok=True)
        
        with patch.object(TempFileManager, 'get_session_path', return_value=downloads_path):
            yield session_id, downloads_path
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_pdf_file(self):
        """Create mock PDF file for testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()
        
        yield temp_path
        
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def splitter(self, temp_session_dir):
        """Create PDFSplitter instance with test session."""
        session_id, _ = temp_session_dir
        return PDFSplitter(session_id)
    
    def test_init_creates_splitter_with_session_id(self):
        """Test PDFSplitter initialization with session ID."""
        session_id = "test_session_456"
        splitter = PDFSplitter(session_id)
        
        assert splitter.session_id == session_id
        assert splitter.text_extractor is not None
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    @patch('app.services.pdf_splitter.validate_pdf_structure')
    def test_split_by_pages_basic_functionality(self, mock_validate_structure, mock_validate_file, 
                                              splitter, mock_pdf_file, temp_session_dir):
        """Test basic page splitting functionality."""
        session_id, downloads_path = temp_session_dir
        
        # Mock PDF reader with 10 pages
        mock_pages = [Mock() for _ in range(10)]
        mock_reader = Mock()
        mock_reader.pages = mock_pages
        mock_reader.metadata = {'Title': 'Test PDF'}
        
        mock_validate_file.return_value = True
        mock_validate_structure.return_value = {'valid': True}
        
        with patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch('app.services.pdf_splitter.PdfWriter') as mock_writer_class, \
             patch('app.services.pdf_splitter.preserve_pdf_metadata') as mock_preserve, \
             patch('builtins.open', create=True) as mock_open, \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', return_value='abc123'):
            
            mock_writer = Mock()
            mock_writer_class.return_value = mock_writer
            
            result = splitter.split_by_pages(mock_pdf_file, [3, 7], preserve_metadata=True)
            
            assert result['success'] is True
            assert result['split_type'] == 'pages'
            assert result['source_pages'] == 10
            assert len(result['output_files']) == 3  # Pages 1-2, 3-6, 7-10
            assert result['metadata_preserved'] is True
            
            # Verify split ranges
            expected_ranges = [(1, 2), (3, 6), (7, 10)]
            for i, output_file in enumerate(result['output_files']):
                start, end = expected_ranges[i]
                assert output_file['page_range'] == f"{start}-{end}"
                assert output_file['page_count'] == end - start + 1
    
    def test_split_by_pages_invalid_page_one(self, splitter, mock_pdf_file):
        """Test error when trying to split on page 1."""
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader') as mock_reader_class:
            
            mock_reader = Mock()
            mock_reader.pages = [Mock() for _ in range(10)]
            mock_reader_class.return_value = mock_reader
            
            with pytest.raises(ValueError, match="Cannot split on page 1"):
                splitter.split_by_pages(mock_pdf_file, [1, 5])
    
    def test_split_by_pages_too_many_splits(self, splitter, mock_pdf_file):
        """Test error when too many split points provided."""
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader') as mock_reader_class:
            
            mock_reader = Mock()
            mock_reader.pages = [Mock() for _ in range(200)]
            mock_reader_class.return_value = mock_reader
            
            split_pages = list(range(2, 103))  # 101 split points
            
            with pytest.raises(ValueError, match="Too many split points"):
                splitter.split_by_pages(mock_pdf_file, split_pages)
    
    def test_split_by_pages_nonexistent_file(self, splitter):
        """Test error handling for nonexistent file."""
        nonexistent_file = Path("/nonexistent/file.pdf")
        
        with patch('app.services.pdf_splitter.validate_file_exists', side_effect=Exception("File not found")):
            with pytest.raises(Exception, match="File not found"):
                splitter.split_by_pages(nonexistent_file, [2, 5])
    
    def test_split_by_pages_encrypted_pdf(self, splitter, mock_pdf_file):
        """Test handling of encrypted PDF files."""
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader') as mock_reader_class:
            
            mock_reader = Mock()
            mock_reader.pages = [Mock() for _ in range(10)]
            mock_reader.is_encrypted = True
            mock_reader_class.return_value = mock_reader
            
            # Should still work since PyPDF2 can handle some encrypted files
            result = splitter.split_by_pages(mock_pdf_file, [3, 7])
            assert result['success'] is True
    
    def test_split_by_pages_corrupted_pdf_structure(self, splitter, mock_pdf_file):
        """Test handling of corrupted PDF structure."""
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', 
                   return_value={'valid': False, 'error': 'Corrupted structure'}), \
             patch('app.services.pdf_splitter.PdfReader') as mock_reader_class:
            
            mock_reader = Mock()
            mock_reader.pages = [Mock() for _ in range(5)]
            mock_reader_class.return_value = mock_reader
            
            with patch('app.services.pdf_splitter.logger') as mock_logger:
                result = splitter.split_by_pages(mock_pdf_file, [3])
                
                # Should log warning but continue
                mock_logger.warning.assert_called_once()
                assert result['success'] is True
    
    def test_split_by_pages_preserve_metadata_disabled(self, splitter, mock_pdf_file, temp_session_dir):
        """Test splitting without metadata preservation."""
        session_id, downloads_path = temp_session_dir
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(5)]
        mock_reader.metadata = {'Title': 'Test PDF'}
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch('app.services.pdf_splitter.PdfWriter') as mock_writer_class, \
             patch('app.services.pdf_splitter.preserve_pdf_metadata') as mock_preserve, \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', return_value='def456'):
            
            result = splitter.split_by_pages(mock_pdf_file, [3], preserve_metadata=False)
            
            assert result['success'] is True
            assert result['metadata_preserved'] is False
            mock_preserve.assert_not_called()
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    def test_split_by_pattern_exact_match(self, mock_validate_file, splitter, mock_pdf_file):
        """Test pattern splitting with exact text matching."""
        mock_validate_file.return_value = True
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(8)]
        
        # Mock text extraction result
        mock_extraction_result = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Chapter 1 Introduction'},
                {'page_number': 2, 'text': 'Some content here'},
                {'page_number': 3, 'text': 'Chapter 2 Methods'},
                {'page_number': 4, 'text': 'More content'},
                {'page_number': 5, 'text': 'Chapter 3 Results'},
                {'page_number': 6, 'text': 'Data and analysis'},
                {'page_number': 7, 'text': 'Chapter 4 Discussion'},
                {'page_number': 8, 'text': 'Final thoughts'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result), \
             patch('app.services.pdf_splitter.PdfWriter') as mock_writer_class, \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', return_value='pattern123'):
            
            result = splitter.split_by_pattern(mock_pdf_file, "Chapter", pattern_type="exact")
            
            assert result['success'] is True
            assert result['split_type'] == 'pattern'
            assert result['pattern'] == 'Chapter'
            assert result['pattern_type'] == 'exact'
            assert result['pattern_matches_found'] == 4
            # Should create 4 sections: pages 1-2, 3-4, 5-6, 7-8
            assert len(result['output_files']) == 4
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    def test_split_by_pattern_regex_match(self, mock_validate_file, splitter, mock_pdf_file):
        """Test pattern splitting with regex matching."""
        mock_validate_file.return_value = True
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(6)]
        
        mock_extraction_result = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Section 1.1 Overview'},
                {'page_number': 2, 'text': 'Some content'},
                {'page_number': 3, 'text': 'Section 2.1 Analysis'},
                {'page_number': 4, 'text': 'Data here'},
                {'page_number': 5, 'text': 'Section 3.2 Results'},
                {'page_number': 6, 'text': 'Conclusion'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result), \
             patch('app.services.pdf_splitter.PdfWriter'), \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', return_value='regex123'):
            
            result = splitter.split_by_pattern(mock_pdf_file, r"Section\s+\d+\.\d+", pattern_type="regex")
            
            assert result['success'] is True
            assert result['pattern_type'] == 'regex'
            assert result['pattern_matches_found'] == 3
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    def test_split_by_pattern_fuzzy_match(self, mock_validate_file, splitter, mock_pdf_file):
        """Test pattern splitting with fuzzy matching."""
        mock_validate_file.return_value = True
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(4)]
        
        mock_extraction_result = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Introduction section'},
                {'page_number': 2, 'text': 'Metodology chapter'},  # Misspelled "Methodology"
                {'page_number': 3, 'text': 'Results and analysis'},
                {'page_number': 4, 'text': 'Conclusive remarks'}   # Similar to "Conclusion"
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result), \
             patch('app.services.pdf_splitter.PdfWriter'), \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', return_value='fuzzy123'):
            
            result = splitter.split_by_pattern(
                mock_pdf_file, 
                "Methodology", 
                pattern_type="fuzzy", 
                fuzzy_threshold=80
            )
            
            assert result['success'] is True
            assert result['pattern_type'] == 'fuzzy'
            # Should find "Metodology" as fuzzy match
            assert result['pattern_matches_found'] >= 1
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    def test_split_by_pattern_no_matches_found(self, mock_validate_file, splitter, mock_pdf_file):
        """Test pattern splitting when no matches are found."""
        mock_validate_file.return_value = True
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(3)]
        
        mock_extraction_result = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Some random content'},
                {'page_number': 2, 'text': 'More random text'},
                {'page_number': 3, 'text': 'Nothing matching here'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result):
            
            result = splitter.split_by_pattern(mock_pdf_file, "NonexistentPattern")
            
            assert result['success'] is False
            assert result['error'] == 'No pattern matches found'
            assert result['pattern'] == 'NonexistentPattern'
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    def test_split_by_pattern_text_extraction_failure(self, mock_validate_file, splitter, mock_pdf_file):
        """Test pattern splitting when text extraction fails."""
        mock_validate_file.return_value = True
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(3)]
        
        mock_extraction_result = {
            'success': False,
            'error': 'Text extraction failed'
        }
        
        with patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result):
            
            with pytest.raises(Exception, match="Failed to extract text for pattern matching"):
                splitter.split_by_pattern(mock_pdf_file, "SomePattern")
    
    @patch('app.services.pdf_splitter.validate_file_exists')
    def test_split_by_pattern_split_after_position(self, mock_validate_file, splitter, mock_pdf_file):
        """Test pattern splitting with 'after' split position."""
        mock_validate_file.return_value = True
        
        mock_reader = Mock()
        mock_reader.pages = [Mock() for _ in range(6)]
        
        mock_extraction_result = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Content'},
                {'page_number': 2, 'text': 'Chapter 1'},  # Split after this
                {'page_number': 3, 'text': 'Content'},
                {'page_number': 4, 'text': 'Chapter 2'},  # Split after this  
                {'page_number': 5, 'text': 'Content'},
                {'page_number': 6, 'text': 'End'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=mock_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result), \
             patch('app.services.pdf_splitter.PdfWriter'), \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', return_value='after123'):
            
            result = splitter.split_by_pattern(
                mock_pdf_file, 
                "Chapter", 
                pattern_type="exact",
                split_position="after"
            )
            
            assert result['success'] is True
            # Should create splits after pages 2 and 4: pages 1-2, 3-4, 5-6
            assert len(result['output_files']) == 3
    
    def test_calculate_page_ranges_basic(self, splitter):
        """Test page range calculation with basic split points."""
        ranges = splitter._calculate_page_ranges([3, 7], 10)
        expected = [(1, 2), (3, 6), (7, 10)]
        assert ranges == expected
    
    def test_calculate_page_ranges_no_splits(self, splitter):
        """Test page range calculation with no split points."""
        ranges = splitter._calculate_page_ranges([], 10)
        expected = [(1, 10)]
        assert ranges == expected
    
    def test_calculate_page_ranges_single_split(self, splitter):
        """Test page range calculation with single split point."""
        ranges = splitter._calculate_page_ranges([5], 10)
        expected = [(1, 4), (5, 10)]
        assert ranges == expected
    
    def test_calculate_split_points_before_position(self, splitter):
        """Test split point calculation with 'before' position."""
        pattern_matches = [
            {'page': 3, 'text': 'Chapter 1'},
            {'page': 7, 'text': 'Chapter 2'},
            {'page': 1, 'text': 'Title'}  # Should be ignored (can't split before page 1)
        ]
        
        split_points = splitter._calculate_split_points(pattern_matches, 'before', 10)
        expected = [3, 7]  # Page 1 ignored
        assert sorted(split_points) == sorted(expected)
    
    def test_calculate_split_points_after_position(self, splitter):
        """Test split point calculation with 'after' position."""
        pattern_matches = [
            {'page': 3, 'text': 'Chapter 1'},
            {'page': 7, 'text': 'Chapter 2'},
            {'page': 10, 'text': 'End'}  # Should be ignored (can't split after last page)
        ]
        
        split_points = splitter._calculate_split_points(pattern_matches, 'after', 10)
        expected = [4, 8]  # Page 10+1 ignored
        assert sorted(split_points) == sorted(expected)
    
    def test_generate_split_filenames_pages_strategy(self, splitter):
        """Test filename generation for page-based splits."""
        page_ranges = [(1, 3), (4, 4), (5, 10)]
        filenames = splitter._generate_split_filenames("test_doc", "pages", page_ranges)
        
        expected = [
            "test_doc_pages_1-3.pdf",
            "test_doc_page_4.pdf", 
            "test_doc_pages_5-10.pdf"
        ]
        assert filenames == expected
    
    def test_generate_split_filenames_pattern_strategy(self, splitter):
        """Test filename generation for pattern-based splits."""
        page_ranges = [(1, 2), (3, 5)]
        pattern_matches = ["Chapter 1 Introduction", "Chapter 2 Methods"]
        
        filenames = splitter._generate_split_filenames(
            "test_doc", "pattern", page_ranges, pattern_matches
        )
        
        # Should sanitize pattern text in filenames
        assert "test_doc_match_1_Chapter_1_Intro" in filenames[0]
        assert "test_doc_match_2_Chapter_2_Metho" in filenames[1]
    
    @patch('builtins.open')
    @patch('hashlib.sha256')
    def test_calculate_file_hash(self, mock_sha256, mock_open, splitter, mock_pdf_file):
        """Test file hash calculation for integrity verification."""
        mock_hash = Mock()
        mock_hash.hexdigest.return_value = "abcd1234567890"
        mock_sha256.return_value = mock_hash
        
        mock_file = Mock()
        mock_file.read.side_effect = [b"chunk1", b"chunk2", b""]  # EOF
        mock_open.return_value.__enter__.return_value = mock_file
        
        result = splitter._calculate_file_hash(mock_pdf_file)
        
        assert result == "abcd1234567890"
        mock_hash.update.assert_any_call(b"chunk1")
        mock_hash.update.assert_any_call(b"chunk2")
    
    def test_calculate_file_hash_error_handling(self, splitter, mock_pdf_file):
        """Test file hash calculation error handling."""
        with patch('builtins.open', side_effect=IOError("Cannot read file")), \
             patch('app.services.pdf_splitter.logger') as mock_logger:
            
            result = splitter._calculate_file_hash(mock_pdf_file)
            
            assert result == ""
            mock_logger.error.assert_called_once()
    
    def test_match_pattern_exact_case_insensitive(self, splitter):
        """Test exact pattern matching (case insensitive behavior)."""
        text = "This is a TEST document with various content"
        result = splitter._match_pattern(text, "test", "exact", 80)
        
        # Should find "TEST" in text
        assert result['found'] is True
        assert result['matched_text'] == "test"
        assert result['confidence'] == 100
    
    def test_match_pattern_regex_multiline(self, splitter):
        """Test regex pattern matching with multiline content."""
        text = "Line 1: Introduction\nLine 2: Chapter 1\nLine 3: Content"
        result = splitter._match_pattern(text, r"Chapter\s+\d+", "regex", 80)
        
        assert result['found'] is True
        assert result['matched_text'] == "Chapter 1"
        assert result['confidence'] == 100
    
    def test_match_pattern_fuzzy_threshold(self, splitter):
        """Test fuzzy pattern matching with threshold boundaries."""
        text = "Metodology section with detailed analysis"
        
        # Should match with low threshold
        result_low = splitter._match_pattern(text, "Methodology", "fuzzy", 70)
        assert result_low['found'] is True
        
        # Should not match with high threshold
        result_high = splitter._match_pattern(text, "Methodology", "fuzzy", 95)
        assert result_high['found'] is False
    
    def test_match_pattern_error_handling(self, splitter):
        """Test pattern matching error handling for invalid regex."""
        text = "Some text content"
        result = splitter._match_pattern(text, "[invalid regex", "regex", 80)
        
        assert result['found'] is False
        assert result['confidence'] == 0
        assert 'error' in result