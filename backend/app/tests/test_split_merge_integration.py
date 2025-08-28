import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from PyPDF2 import PdfReader, PdfWriter

from app.services.pdf_splitter import PDFSplitter
from app.services.pdf_merger import PDFMerger
from app.services.temp_file_manager import TempFileManager


class TestSplitMergeIntegration:
    """Integration tests for PDF split/merge operations testing end-to-end workflows."""
    
    @pytest.fixture
    def temp_session_dir(self):
        """Create temporary session directory for integration tests."""
        temp_dir = tempfile.mkdtemp()
        session_id = "integration_test_session_456"
        session_path = Path(temp_dir) / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        downloads_path = session_path / "downloads"
        downloads_path.mkdir(parents=True, exist_ok=True)
        
        with patch.object(TempFileManager, 'get_session_path', return_value=downloads_path):
            yield session_id, downloads_path
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_source_pdf(self):
        """Create mock source PDF file for integration testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix='_source.pdf', delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()
        
        yield temp_path
        
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def services(self, temp_session_dir):
        """Create both splitter and merger services for integration testing."""
        session_id, _ = temp_session_dir
        splitter = PDFSplitter(session_id)
        merger = PDFMerger(session_id)
        return splitter, merger
    
    def test_split_then_merge_page_based_round_trip(self, services, mock_source_pdf, temp_session_dir):
        """Test splitting a PDF by pages then merging the results back together."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Mock original PDF with 10 pages
        original_pages = [Mock() for _ in range(10)]
        original_reader = Mock()
        original_reader.pages = original_pages
        original_reader.metadata = {
            '/Title': 'Original Document',
            '/Author': 'Test Author',
            '/Subject': 'Integration Test'
        }
        
        # Mock split files created
        split_files = [
            downloads_path / "original_pages_1-3.pdf",
            downloads_path / "original_pages_4-7.pdf", 
            downloads_path / "original_pages_8-10.pdf"
        ]
        
        # Mock readers for split files (for merge operation)
        split_readers = [
            Mock(pages=[Mock() for _ in range(3)], is_encrypted=False, metadata={'Title': 'Part 1'}),
            Mock(pages=[Mock() for _ in range(4)], is_encrypted=False, metadata={'Title': 'Part 2'}),
            Mock(pages=[Mock() for _ in range(3)], is_encrypted=False, metadata={'Title': 'Part 3'})
        ]
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=original_reader), \
             patch('app.services.pdf_splitter.PdfWriter') as mock_split_writer_class, \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', side_effect=['hash1', 'hash2', 'hash3']):
            
            # Mock file stats for split files
            for split_file in split_files:
                with patch.object(split_file, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 1000
                with patch.object(split_file, 'exists', return_value=True):
                    pass
            
            # Perform split operation
            split_result = splitter.split_by_pages(mock_source_pdf, [4, 8])
            
            assert split_result['success'] is True
            assert len(split_result['output_files']) == 3
            assert split_result['source_pages'] == 10
            
            # Extract split file paths for merge
            split_file_paths = [Path(file_info['path']) for file_info in split_result['output_files']]
            
            # Now test merge operation
            with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
                 patch('app.services.pdf_merger.PdfReader', side_effect=split_readers), \
                 patch('app.services.pdf_merger.PdfWriter') as mock_merge_writer_class, \
                 patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='merged_hash'):
                
                mock_merge_writer = Mock()
                mock_merge_writer_class.return_value = mock_merge_writer
                
                merge_result = merger.merge_documents(split_file_paths)
                
                assert merge_result['success'] is True
                assert merge_result['source_count'] == 3
                assert merge_result['total_pages'] == 10  # Should reconstruct original page count
                
                # Verify all pages were added back in sequence
                assert mock_merge_writer.add_page.call_count == 10
    
    def test_split_by_pattern_then_merge_workflow(self, services, mock_source_pdf, temp_session_dir):
        """Test splitting by pattern detection then merging selected parts."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Mock original PDF with chapter structure
        original_reader = Mock()
        original_reader.pages = [Mock() for _ in range(12)]
        original_reader.metadata = {'Title': 'Chaptered Document'}
        
        # Mock text extraction result with chapter patterns
        mock_extraction_result = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Table of Contents'},
                {'page_number': 2, 'text': 'Chapter 1: Introduction to the topic'},
                {'page_number': 3, 'text': 'Content of chapter one'},
                {'page_number': 4, 'text': 'More chapter one content'},
                {'page_number': 5, 'text': 'Chapter 2: Advanced Methods'},
                {'page_number': 6, 'text': 'Chapter two content here'},
                {'page_number': 7, 'text': 'Additional methods'},
                {'page_number': 8, 'text': 'Chapter 3: Results and Analysis'},
                {'page_number': 9, 'text': 'Results data and charts'},
                {'page_number': 10, 'text': 'Statistical analysis'},
                {'page_number': 11, 'text': 'Chapter 4: Conclusions'},
                {'page_number': 12, 'text': 'Final thoughts and references'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=original_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_result), \
             patch('app.services.pdf_splitter.PdfWriter') as mock_split_writer, \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', side_effect=['ch1', 'ch2', 'ch3', 'ch4']):
            
            # Perform pattern-based split
            split_result = splitter.split_by_pattern(mock_source_pdf, "Chapter", pattern_type="exact")
            
            assert split_result['success'] is True
            assert split_result['pattern_matches_found'] == 4
            assert len(split_result['output_files']) == 4  # TOC + 3 chapters
            
            # Select specific chapters to merge (e.g., chapters 1 and 3)
            chapters_to_merge = [
                split_result['output_files'][1],  # Chapter 1 
                split_result['output_files'][3]   # Chapter 3
            ]
            
            merge_paths = [Path(chapter['path']) for chapter in chapters_to_merge]
            
            # Mock readers for selected chapters
            selected_readers = [
                Mock(pages=[Mock() for _ in range(3)], is_encrypted=False, metadata={'Title': 'Chapter 1'}),
                Mock(pages=[Mock() for _ in range(3)], is_encrypted=False, metadata={'Title': 'Chapter 3'})
            ]
            
            with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
                 patch('app.services.pdf_merger.PdfReader', side_effect=selected_readers), \
                 patch('app.services.pdf_merger.PdfWriter') as mock_merge_writer_class, \
                 patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='selective_merge'):
                
                merge_result = merger.merge_documents(
                    merge_paths, 
                    output_filename="selected_chapters.pdf",
                    merge_strategy="aggregate"
                )
                
                assert merge_result['success'] is True
                assert merge_result['source_count'] == 2
                assert merge_result['total_pages'] == 6
                assert merge_result['output_filename'] == "selected_chapters.pdf"
                assert merge_result['merge_strategy'] == "aggregate"
    
    def test_split_merge_with_metadata_preservation(self, services, mock_source_pdf, temp_session_dir):
        """Test that metadata is properly preserved through split/merge cycle."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Rich metadata original document
        original_metadata = {
            '/Title': 'Comprehensive Research Document',
            '/Author': 'Dr. Jane Smith',
            '/Subject': 'Advanced Scientific Analysis',
            '/Keywords': 'research, analysis, science',
            '/Creator': 'Academic Publisher',
            '/Producer': 'PDF Generator v2.0'
        }
        
        original_reader = Mock()
        original_reader.pages = [Mock() for _ in range(8)]
        original_reader.metadata = original_metadata
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=original_reader), \
             patch('app.services.pdf_splitter.PdfWriter') as mock_split_writer_class, \
             patch('app.services.pdf_splitter.preserve_pdf_metadata') as mock_preserve, \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', side_effect=['split1', 'split2']):
            
            # Split with metadata preservation enabled
            split_result = splitter.split_by_pages(
                mock_source_pdf, 
                [5], 
                preserve_metadata=True
            )
            
            assert split_result['success'] is True
            assert split_result['metadata_preserved'] is True
            
            # Verify preserve_pdf_metadata was called for each split
            assert mock_preserve.call_count == 2
            
            # Mock split file readers with preserved metadata
            split_readers = [
                Mock(pages=[Mock() for _ in range(4)], is_encrypted=False, metadata=original_metadata.copy()),
                Mock(pages=[Mock() for _ in range(4)], is_encrypted=False, metadata=original_metadata.copy())
            ]
            
            split_paths = [Path(file_info['path']) for file_info in split_result['output_files']]
            
            with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
                 patch('app.services.pdf_merger.PdfReader', side_effect=split_readers), \
                 patch('app.services.pdf_merger.PdfWriter') as mock_merge_writer_class, \
                 patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='metadata_preserved'), \
                 patch('app.services.pdf_merger.datetime') as mock_datetime:
                
                mock_datetime.now.return_value.strftime.return_value = "20240101120000"
                mock_merge_writer = Mock()
                mock_merge_writer_class.return_value = mock_merge_writer
                
                # Merge with sequential metadata strategy
                merge_result = merger.merge_documents(
                    split_paths,
                    preserve_metadata=True,
                    merge_strategy="sequential"
                )
                
                assert merge_result['success'] is True
                assert merge_result['metadata_preserved'] is True
                
                # Verify metadata was added to merged document
                mock_merge_writer.add_metadata.assert_called_once()
                merged_metadata = mock_merge_writer.add_metadata.call_args[0][0]
                
                # Should preserve original metadata with merge info added
                assert merged_metadata['/Title'] == original_metadata['/Title']
                assert merged_metadata['/Author'] == original_metadata['/Author']
                assert 'Merged from 2 documents' in merged_metadata['/Subject']
    
    def test_error_handling_in_split_merge_pipeline(self, services, mock_source_pdf, temp_session_dir):
        """Test error handling throughout the split/merge pipeline."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Test split operation failure
        with patch('app.services.pdf_splitter.validate_file_exists', side_effect=Exception("File validation failed")):
            with pytest.raises(Exception, match="File validation failed"):
                splitter.split_by_pages(mock_source_pdf, [3, 6])
        
        # Test merge operation with invalid split files
        invalid_paths = [Path("nonexistent1.pdf"), Path("nonexistent2.pdf")]
        
        with pytest.raises(ValueError, match="File not found"):
            merger.merge_documents(invalid_paths)
    
    def test_file_integrity_through_split_merge_cycle(self, services, mock_source_pdf, temp_session_dir):
        """Test file integrity verification through complete split/merge cycle."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        original_size = 5000
        original_hash = "original_abc123"
        
        # Mock original file properties
        with patch.object(mock_source_pdf, 'stat') as mock_stat:
            mock_stat.return_value.st_size = original_size
        
        original_reader = Mock()
        original_reader.pages = [Mock() for _ in range(6)]
        original_reader.metadata = {'Title': 'Integrity Test'}
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=original_reader), \
             patch('app.services.pdf_splitter.PdfWriter'), \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', side_effect=['split1_hash', 'split2_hash']):
            
            # Perform split
            split_result = splitter.split_by_pages(mock_source_pdf, [4])
            
            # Verify split integrity data
            assert split_result['success'] is True
            assert split_result['source_size'] == original_size
            for split_file in split_result['output_files']:
                assert 'sha256_hash' in split_file
                assert 'file_size' in split_file
                assert split_file['sha256_hash'] != ""
            
            # Mock split file readers for merge
            split_readers = [
                Mock(pages=[Mock() for _ in range(3)], is_encrypted=False, metadata={'Title': 'Part 1'}),
                Mock(pages=[Mock() for _ in range(3)], is_encrypted=False, metadata={'Title': 'Part 2'})
            ]
            
            split_paths = [Path(file_info['path']) for file_info in split_result['output_files']]
            
            # Mock file stats for split files
            for i, split_path in enumerate(split_paths):
                with patch.object(split_path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 2000 + (i * 500)  # Different sizes
            
            merged_size = 4800
            merged_hash = "merged_xyz789"
            
            with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
                 patch('app.services.pdf_merger.PdfReader', side_effect=split_readers), \
                 patch('app.services.pdf_merger.PdfWriter') as mock_writer_class, \
                 patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value=merged_hash):
                
                # Mock merged output file
                merged_path = downloads_path / "test_merged.pdf"
                with patch.object(merged_path, 'stat') as mock_merged_stat:
                    mock_merged_stat.return_value.st_size = merged_size
                
                # Mock merged file reader for integrity check
                merged_reader = Mock()
                merged_reader.pages = [Mock() for _ in range(6)]  # All pages preserved
                
                with patch('app.services.pdf_merger.PdfReader', return_value=merged_reader):
                    merge_result = merger.merge_documents(split_paths)
                    
                    assert merge_result['success'] is True
                    
                    # Verify integrity statistics
                    stats = merge_result['statistics']
                    assert stats['output_size'] == merged_size
                    assert stats['output_hash'] == merged_hash
                    assert stats['page_integrity'] is True
                    assert stats['actual_pages'] == 6
                    assert stats['expected_pages'] == 6
                    
                    # Verify size calculations
                    assert 'size_efficiency' in stats
                    assert 'compression_ratio' in stats
    
    def test_large_document_split_merge_performance(self, services, mock_source_pdf, temp_session_dir):
        """Test split/merge operations on large documents with performance considerations."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Mock large document (100 pages)
        large_page_count = 100
        original_reader = Mock()
        original_reader.pages = [Mock() for _ in range(large_page_count)]
        original_reader.metadata = {'Title': 'Large Document'}
        
        # Split into 5 sections (20 pages each)
        split_points = [21, 41, 61, 81]  # Creates 5 sections: 1-20, 21-40, 41-60, 61-80, 81-100
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=original_reader), \
             patch('app.services.pdf_splitter.PdfWriter'), \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', side_effect=[f'section{i}' for i in range(5)]):
            
            split_result = splitter.split_by_pages(mock_source_pdf, split_points)
            
            assert split_result['success'] is True
            assert len(split_result['output_files']) == 5
            assert split_result['source_pages'] == large_page_count
            
            # Verify page count distribution
            expected_page_counts = [20, 20, 20, 20, 20]
            for i, split_file in enumerate(split_result['output_files']):
                assert split_file['page_count'] == expected_page_counts[i]
            
            # Test merging subset of sections (sections 1, 3, 5)
            selected_sections = [
                split_result['output_files'][0],  # Section 1 (pages 1-20)
                split_result['output_files'][2],  # Section 3 (pages 41-60)  
                split_result['output_files'][4]   # Section 5 (pages 81-100)
            ]
            
            merge_paths = [Path(section['path']) for section in selected_sections]
            
            # Mock readers for selected sections
            selected_readers = [
                Mock(pages=[Mock() for _ in range(20)], is_encrypted=False, metadata={'Title': 'Section 1'}),
                Mock(pages=[Mock() for _ in range(20)], is_encrypted=False, metadata={'Title': 'Section 3'}),
                Mock(pages=[Mock() for _ in range(20)], is_encrypted=False, metadata={'Title': 'Section 5'})
            ]
            
            with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
                 patch('app.services.pdf_merger.PdfReader', side_effect=selected_readers), \
                 patch('app.services.pdf_merger.PdfWriter') as mock_writer_class, \
                 patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='large_selective'):
                
                merge_result = merger.merge_documents(merge_paths, output_filename="selective_large.pdf")
                
                assert merge_result['success'] is True
                assert merge_result['source_count'] == 3
                assert merge_result['total_pages'] == 60  # 20 + 20 + 20
                assert merge_result['output_filename'] == "selective_large.pdf"
    
    def test_split_merge_with_pattern_and_encryption_edge_cases(self, services, mock_source_pdf, temp_session_dir):
        """Test edge cases including pattern matching failures and encryption handling."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Test pattern split with no matches
        no_match_reader = Mock()
        no_match_reader.pages = [Mock() for _ in range(5)]
        
        mock_extraction_no_match = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Random content without patterns'},
                {'page_number': 2, 'text': 'More random text here'},
                {'page_number': 3, 'text': 'Nothing matching the search'},
                {'page_number': 4, 'text': 'Still no matches found'},
                {'page_number': 5, 'text': 'Final page content'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=no_match_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=mock_extraction_no_match):
            
            # Should fail gracefully when no pattern matches found
            split_result = splitter.split_by_pattern(mock_source_pdf, "NonexistentPattern")
            
            assert split_result['success'] is False
            assert split_result['error'] == 'No pattern matches found'
            assert split_result['pattern'] == 'NonexistentPattern'
        
        # Test merge with mixed encryption status (should handle gracefully)
        normal_reader = Mock(pages=[Mock()], is_encrypted=False, metadata={'Title': 'Normal'})
        encrypted_reader = Mock(pages=[Mock()], is_encrypted=True, metadata={'Title': 'Encrypted'})
        
        mock_files = [Path("normal.pdf"), Path("encrypted.pdf")]
        
        with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
             patch('app.services.pdf_merger.PdfReader', side_effect=[normal_reader, encrypted_reader]):
            
            # Should fail when encountering encrypted PDF
            with pytest.raises(ValueError, match="Cannot merge encrypted PDF"):
                merger.merge_documents(mock_files)
    
    def test_end_to_end_workflow_with_realistic_document_structure(self, services, mock_source_pdf, temp_session_dir):
        """Test realistic end-to-end workflow simulating actual document processing."""
        splitter, merger = services
        session_id, downloads_path = temp_session_dir
        
        # Simulate a realistic academic paper structure
        paper_reader = Mock()
        paper_reader.pages = [Mock() for _ in range(15)]  # 15-page paper
        paper_reader.metadata = {
            '/Title': 'Machine Learning Applications in Healthcare',
            '/Author': 'Dr. Alice Johnson, Dr. Bob Smith',
            '/Subject': 'Computer Science, Healthcare',
            '/Keywords': 'machine learning, healthcare, AI',
            '/Creator': 'LaTeX'
        }
        
        # Realistic text extraction with academic paper sections
        realistic_extraction = {
            'success': True,
            'pages': [
                {'page_number': 1, 'text': 'Machine Learning Applications in Healthcare\nDr. Alice Johnson, Dr. Bob Smith'},
                {'page_number': 2, 'text': 'Abstract\nThis paper presents novel applications...'},
                {'page_number': 3, 'text': '1. Introduction\nMachine learning has revolutionized...'},
                {'page_number': 4, 'text': 'The healthcare industry faces numerous challenges...'},
                {'page_number': 5, 'text': '2. Literature Review\nPrevious work in this area includes...'},
                {'page_number': 6, 'text': 'Several studies have demonstrated...'},
                {'page_number': 7, 'text': '3. Methodology\nOur approach consists of three main phases...'},
                {'page_number': 8, 'text': 'We collected data from multiple hospitals...'},
                {'page_number': 9, 'text': '4. Results\nThe experimental results show significant improvements...'},
                {'page_number': 10, 'text': 'Figure 1 demonstrates the accuracy improvements...'},
                {'page_number': 11, 'text': '5. Discussion\nOur findings indicate several important implications...'},
                {'page_number': 12, 'text': 'The limitations of our approach include...'},
                {'page_number': 13, 'text': '6. Conclusion\nThis work presents significant advances...'},
                {'page_number': 14, 'text': 'Future work should explore additional applications...'},
                {'page_number': 15, 'text': 'References\n[1] Smith, J. et al. (2020)...'}
            ]
        }
        
        with patch('app.services.pdf_splitter.validate_file_exists'), \
             patch('app.services.pdf_splitter.validate_pdf_structure', return_value={'valid': True}), \
             patch('app.services.pdf_splitter.PdfReader', return_value=paper_reader), \
             patch.object(splitter.text_extractor, 'extract_text_unified', return_value=realistic_extraction), \
             patch('app.services.pdf_splitter.PdfWriter'), \
             patch('app.services.pdf_splitter.preserve_pdf_metadata'), \
             patch('builtins.open', create=True), \
             patch('app.services.pdf_splitter.PDFSplitter._calculate_file_hash', side_effect=[f'section_{i}' for i in range(7)]):
            
            # Split by numbered sections (1., 2., 3., etc.)
            section_split_result = splitter.split_by_pattern(
                mock_source_pdf, 
                r'\d+\.\s+\w+',  # Matches "1. Introduction", "2. Literature Review", etc.
                pattern_type="regex",
                split_position="before"
            )
            
            assert section_split_result['success'] is True
            assert section_split_result['pattern_matches_found'] == 6  # 6 numbered sections found
            
            # Create custom compilation by merging selected sections
            # Let's merge: Title/Abstract + Methodology + Results + Conclusion
            sections_to_compile = [
                section_split_result['output_files'][0],  # Title + Abstract  
                section_split_result['output_files'][3],  # Methodology
                section_split_result['output_files'][4],  # Results
                section_split_result['output_files'][6]   # Conclusion
            ]
            
            compilation_paths = [Path(section['path']) for section in sections_to_compile]
            
            # Mock readers for compilation
            compilation_readers = [
                Mock(pages=[Mock(), Mock()], is_encrypted=False, 
                     metadata={'Title': 'Title and Abstract', 'Subject': 'Introduction'}),
                Mock(pages=[Mock(), Mock()], is_encrypted=False, 
                     metadata={'Title': 'Methodology', 'Subject': 'Methods'}),
                Mock(pages=[Mock(), Mock()], is_encrypted=False, 
                     metadata={'Title': 'Results', 'Subject': 'Findings'}),
                Mock(pages=[Mock(), Mock()], is_encrypted=False, 
                     metadata={'Title': 'Conclusion', 'Subject': 'Summary'})
            ]
            
            with patch('app.services.pdf_merger.validate_pdf_file', return_value={'is_valid': True}), \
                 patch('app.services.pdf_merger.PdfReader', side_effect=compilation_readers), \
                 patch('app.services.pdf_merger.PdfWriter') as mock_writer_class, \
                 patch('app.services.pdf_merger.PDFMerger._calculate_file_hash', return_value='executive_summary_hash'), \
                 patch('app.services.pdf_merger.datetime') as mock_datetime:
                
                mock_datetime.now.return_value.strftime.return_value = "20240101120000"
                mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
                mock_writer = Mock()
                mock_writer_class.return_value = mock_writer
                
                # Create executive summary compilation
                compilation_result = merger.merge_documents(
                    compilation_paths,
                    output_filename="executive_summary.pdf", 
                    merge_strategy="aggregate",
                    preserve_metadata=True
                )
                
                assert compilation_result['success'] is True
                assert compilation_result['source_count'] == 4
                assert compilation_result['total_pages'] == 8  # 2 pages per section
                assert compilation_result['output_filename'] == "executive_summary.pdf"
                assert compilation_result['metadata_preserved'] is True
                
                # Verify comprehensive reporting
                assert 'report' in compilation_result
                report = compilation_result['report']
                
                assert report['merge_summary']['source_count'] == 4
                assert report['merge_summary']['merge_timestamp'] == "2024-01-01T12:00:00"
                assert 'page_analysis' in report
                assert 'quality_metrics' in report
                assert 'size_analysis' in report
                
                # Verify metadata aggregation was called
                mock_writer.add_metadata.assert_called_once()
                aggregated_metadata = mock_writer.add_metadata.call_args[0][0]
                
                # Should combine section titles and subjects
                assert 'Title and Abstract + Methodology + Results + Conclusion' == aggregated_metadata['/Title']
                assert 'Introduction; Methods; Findings; Summary' == aggregated_metadata['/Subject']
                assert aggregated_metadata['/Creator'] == 'PDF Merger Service'