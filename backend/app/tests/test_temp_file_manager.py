"""Unit tests for TempFileManager class."""

import pytest
import tempfile
import shutil
import hashlib
from pathlib import Path
from unittest.mock import patch, Mock, call
import uuid

from app.services.temp_file_manager import TempFileManager


class TestTempFileManager:
    """Test cases for TempFileManager class."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        # Create a temporary directory for testing
        self.temp_test_dir = Path(tempfile.mkdtemp())
        
        # Patch the BASE_DIR to use our test directory
        self.base_dir_patcher = patch.object(TempFileManager, 'BASE_DIR', self.temp_test_dir)
        self.base_dir_patcher.start()
        
        self.test_session_id = "test_session_123"
    
    def teardown_method(self):
        """Clean up after each test."""
        self.base_dir_patcher.stop()
        # Clean up test directory
        if self.temp_test_dir.exists():
            shutil.rmtree(self.temp_test_dir, ignore_errors=True)
    
    def test_get_session_path_valid_inputs(self):
        """Test get_session_path with valid inputs."""
        session_id = "valid_session_123"
        
        # Test all valid subdirectories
        for subdir in ["uploads", "processing", "downloads"]:
            path = TempFileManager.get_session_path(session_id, subdir)
            
            expected_path = self.temp_test_dir / subdir / session_id
            assert path == expected_path
            assert path.exists()  # Directory should be created
            assert path.is_dir()
    
    def test_get_session_path_creates_directories(self):
        """Test that get_session_path creates the full directory structure."""
        session_id = "new_session_456"
        subdir = "uploads"
        
        # Verify directory doesn't exist initially
        expected_path = self.temp_test_dir / subdir / session_id
        assert not expected_path.exists()
        
        # Call method
        result_path = TempFileManager.get_session_path(session_id, subdir)
        
        # Verify directory was created
        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.is_dir()
        
        # Verify parent directories exist
        assert (self.temp_test_dir / subdir).exists()
    
    def test_get_session_path_invalid_session_id(self):
        """Test get_session_path with invalid session IDs."""
        # Empty session ID
        with pytest.raises(ValueError, match="Session ID cannot be empty"):
            TempFileManager.get_session_path("", "uploads")
        
        # Whitespace-only session ID
        with pytest.raises(ValueError, match="Session ID cannot be empty"):
            TempFileManager.get_session_path("   ", "uploads")
        
        # None session ID
        with pytest.raises(ValueError, match="Session ID cannot be empty"):
            TempFileManager.get_session_path(None, "uploads")
    
    def test_get_session_path_invalid_subdir(self):
        """Test get_session_path with invalid subdirectories."""
        session_id = "valid_session"
        
        invalid_subdirs = ["invalid", "documents", "", "upload", "download"]
        
        for invalid_subdir in invalid_subdirs:
            with pytest.raises(ValueError, match=f"Invalid subdirectory: {invalid_subdir}"):
                TempFileManager.get_session_path(session_id, invalid_subdir)
    
    def test_cleanup_session_success(self):
        """Test successful session cleanup."""
        session_id = "cleanup_test_session"
        
        # Create session directories with test files
        for subdir in ["uploads", "processing", "downloads"]:
            session_path = TempFileManager.get_session_path(session_id, subdir)
            
            # Create test files
            test_file = session_path / f"test_file_{subdir}.txt"
            test_file.write_text(f"Test content for {subdir}")
            
            # Create subdirectories with files
            sub_folder = session_path / "subfolder"
            sub_folder.mkdir()
            (sub_folder / "nested_file.txt").write_text("Nested content")
        
        # Verify files exist before cleanup
        for subdir in ["uploads", "processing", "downloads"]:
            session_path = self.temp_test_dir / subdir / session_id
            assert session_path.exists()
            assert len(list(session_path.rglob("*"))) > 0  # Has files
        
        # Perform cleanup
        result = TempFileManager.cleanup_session(session_id)
        
        # Verify cleanup was successful
        assert result is True
        
        # Verify directories are removed
        for subdir in ["uploads", "processing", "downloads"]:
            session_path = self.temp_test_dir / subdir / session_id
            assert not session_path.exists()
    
    def test_cleanup_session_nonexistent(self):
        """Test cleanup of non-existent session."""
        nonexistent_session = "nonexistent_session"
        
        # Cleanup should succeed even if session doesn't exist
        result = TempFileManager.cleanup_session(nonexistent_session)
        assert result is True
    
    def test_cleanup_session_partial_directories(self):
        """Test cleanup when only some session directories exist."""
        session_id = "partial_session"
        
        # Create only uploads directory
        uploads_path = TempFileManager.get_session_path(session_id, "uploads")
        test_file = uploads_path / "test.txt"
        test_file.write_text("test content")
        
        # Verify only uploads exists
        assert (self.temp_test_dir / "uploads" / session_id).exists()
        assert not (self.temp_test_dir / "processing" / session_id).exists()
        assert not (self.temp_test_dir / "downloads" / session_id).exists()
        
        # Cleanup should succeed
        result = TempFileManager.cleanup_session(session_id)
        assert result is True
        
        # Verify cleanup completed
        assert not (self.temp_test_dir / "uploads" / session_id).exists()
    
    @patch('app.services.temp_file_manager.shutil.rmtree')
    def test_cleanup_session_failure(self, mock_rmtree):
        """Test cleanup failure handling."""
        session_id = "failing_session"
        
        # Create a session directory
        TempFileManager.get_session_path(session_id, "uploads")
        
        # Mock rmtree to raise an exception
        mock_rmtree.side_effect = PermissionError("Access denied")
        
        # Cleanup should return False on failure
        result = TempFileManager.cleanup_session(session_id)
        assert result is False
    
    @patch('tasks.cleanup_abandoned_files.apply_async')
    def test_schedule_cleanup_success(self, mock_apply_async):
        """Test successful cleanup scheduling."""
        session_id = "schedule_test_session"
        
        # Schedule cleanup
        TempFileManager.schedule_cleanup(session_id)
        
        # Verify Celery task was scheduled
        mock_apply_async.assert_called_once()
        call_args = mock_apply_async.call_args
        assert call_args[1]['args'] == [session_id]
        assert 'eta' in call_args[1]  # ETA should be set
    
    @patch('tasks.cleanup_abandoned_files')
    def test_schedule_cleanup_import_error(self, mock_tasks_import):
        """Test cleanup scheduling when Celery is not available."""
        session_id = "no_celery_session"
        
        # Mock import error
        mock_tasks_import.side_effect = ImportError("No module named 'tasks'")
        
        # Should handle gracefully without raising exception
        with patch('builtins.print') as mock_print:
            TempFileManager.schedule_cleanup(session_id)
            mock_print.assert_called_once()
            assert "Warning" in mock_print.call_args[0][0]
    
    def test_generate_session_id(self):
        """Test session ID generation."""
        # Generate multiple session IDs
        session_ids = [TempFileManager.generate_session_id() for _ in range(10)]
        
        # Verify all are unique
        assert len(set(session_ids)) == 10
        
        # Verify format (32 character hex)
        for session_id in session_ids:
            assert isinstance(session_id, str)
            assert len(session_id) == 32
            assert all(c in '0123456789abcdef' for c in session_id)
            
            # Verify it's a valid UUID hex
            uuid.UUID(hex=session_id)  # Should not raise exception
    
    def test_calculate_file_hash_valid_file(self):
        """Test file hash calculation with valid file."""
        # Create test file
        test_file = self.temp_test_dir / "test_hash_file.txt"
        test_content = "Test content for hashing"
        test_file.write_text(test_content)
        
        # Calculate hash
        result_hash = TempFileManager.calculate_file_hash(test_file)
        
        # Verify hash format
        assert isinstance(result_hash, str)
        assert len(result_hash) == 64  # SHA-256 hex length
        assert all(c in '0123456789abcdef' for c in result_hash)
        
        # Verify hash consistency
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()
        assert result_hash == expected_hash
    
    def test_calculate_file_hash_nonexistent_file(self):
        """Test file hash calculation with non-existent file."""
        nonexistent_file = self.temp_test_dir / "does_not_exist.txt"
        
        with pytest.raises(FileNotFoundError, match="File not found"):
            TempFileManager.calculate_file_hash(nonexistent_file)
    
    @patch('builtins.open')
    def test_calculate_file_hash_io_error(self, mock_open):
        """Test file hash calculation with IO error."""
        test_file = self.temp_test_dir / "test_file.txt"
        test_file.write_text("test")
        
        # Mock open to raise IOError
        mock_open.side_effect = IOError("Permission denied")
        
        with pytest.raises(IOError, match="Could not read file"):
            TempFileManager.calculate_file_hash(test_file)
    
    def test_calculate_file_hash_with_path_string(self):
        """Test file hash calculation with string path."""
        # Create test file
        test_file = self.temp_test_dir / "string_path_test.txt"
        test_content = "String path test"
        test_file.write_text(test_content)
        
        # Calculate hash using string path
        result_hash = TempFileManager.calculate_file_hash(str(test_file))
        
        # Verify result
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()
        assert result_hash == expected_hash
    
    @patch('psutil.disk_usage')
    def test_check_disk_usage_success(self, mock_disk_usage):
        """Test disk usage checking with mock data."""
        # Mock disk usage data
        mock_usage = Mock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 60 * (1024**3)    # 60 GB
        mock_usage.free = 40 * (1024**3)    # 40 GB
        mock_disk_usage.return_value = mock_usage
        
        result = TempFileManager.check_disk_usage()
        
        expected_result = {
            'total_gb': 100.0,
            'used_gb': 60.0,
            'free_gb': 40.0,
            'usage_percent': 60.0,
            'needs_cleanup': False  # 60% < 85% threshold
        }
        
        assert result == expected_result
    
    @patch('psutil.disk_usage')
    def test_check_disk_usage_high_usage(self, mock_disk_usage):
        """Test disk usage checking with high usage requiring cleanup."""
        # Mock high disk usage
        mock_usage = Mock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 90 * (1024**3)    # 90 GB
        mock_usage.free = 10 * (1024**3)    # 10 GB
        mock_disk_usage.return_value = mock_usage
        
        result = TempFileManager.check_disk_usage()
        
        assert result['usage_percent'] == 90.0
        assert result['needs_cleanup'] is True  # 90% > 85% threshold
    
    @patch('psutil.disk_usage')
    def test_check_disk_usage_error(self, mock_disk_usage):
        """Test disk usage checking with error."""
        mock_disk_usage.side_effect = Exception("Disk access error")
        
        result = TempFileManager.check_disk_usage()
        
        expected_result = {
            'total_gb': 0,
            'used_gb': 0,
            'free_gb': 0,
            'usage_percent': 0,
            'needs_cleanup': False
        }
        
        assert result == expected_result
    
    def test_emergency_cleanup_no_base_dir(self):
        """Test emergency cleanup when base directory doesn't exist."""
        # Remove base directory
        if self.temp_test_dir.exists():
            shutil.rmtree(self.temp_test_dir)
        
        result = TempFileManager.emergency_cleanup()
        assert result == 0
    
    def test_emergency_cleanup_with_sessions(self):
        """Test emergency cleanup with existing session directories."""
        # Create multiple sessions with different ages
        session_ids = ["old_session_1", "old_session_2", "new_session"]
        
        for i, session_id in enumerate(session_ids):
            for subdir in ["uploads", "processing", "downloads"]:
                session_path = TempFileManager.get_session_path(session_id, subdir)
                test_file = session_path / "test.txt"
                test_file.write_text(f"Content for {session_id}")
        
        # Mock high disk usage to trigger cleanup
        with patch.object(TempFileManager, 'check_disk_usage') as mock_check, \
             patch.object(TempFileManager, 'cleanup_session', return_value=True) as mock_cleanup:
            
            # First call returns needs_cleanup=True, subsequent calls return False
            mock_check.side_effect = [
                {'needs_cleanup': True},
                {'needs_cleanup': True}, 
                {'needs_cleanup': False}
            ]
            
            result = TempFileManager.emergency_cleanup()
            
            # Should clean up sessions until disk usage is acceptable
            assert result >= 1  # At least one session cleaned
            assert mock_cleanup.call_count >= 1
    
    def test_get_session_info_existing_session(self):
        """Test getting session info for existing session."""
        session_id = "info_test_session"
        
        # Create files in different directories
        uploads_path = TempFileManager.get_session_path(session_id, "uploads")
        downloads_path = TempFileManager.get_session_path(session_id, "downloads")
        
        # Create test files with known sizes
        upload_file = uploads_path / "upload.pdf"
        upload_file.write_bytes(b"x" * 1024)  # 1 KB
        
        download_file = downloads_path / "result.pdf"
        download_file.write_bytes(b"y" * 2048)  # 2 KB
        
        # Get session info
        info = TempFileManager.get_session_info(session_id)
        
        # Verify structure
        assert info['session_id'] == session_id
        assert info['uploads']['count'] == 1
        assert info['downloads']['count'] == 1
        assert info['processing']['count'] == 0
        
        # Verify sizes (approximately, allowing for rounding)
        assert info['uploads']['size_mb'] > 0
        assert info['downloads']['size_mb'] > 0
        assert info['total_size_mb'] > 0
    
    def test_get_session_info_nonexistent_session(self):
        """Test getting session info for non-existent session."""
        session_id = "nonexistent_session"
        
        info = TempFileManager.get_session_info(session_id)
        
        expected_info = {
            'session_id': session_id,
            'uploads': {'count': 0, 'size_mb': 0},
            'processing': {'count': 0, 'size_mb': 0},
            'downloads': {'count': 0, 'size_mb': 0},
            'total_size_mb': 0
        }
        
        assert info == expected_info
    
    @patch('app.services.temp_file_manager.Path.rglob')
    def test_get_session_info_error(self, mock_rglob):
        """Test getting session info with error."""
        session_id = "error_session"
        mock_rglob.side_effect = Exception("File system error")
        
        info = TempFileManager.get_session_info(session_id)
        
        assert info['session_id'] == session_id
        assert 'error' in info
        assert info['total_size_mb'] == 0


class TestTempFileManagerIntegration:
    """Integration tests for TempFileManager."""
    
    def setup_method(self):
        """Set up integration test environment."""
        self.temp_test_dir = Path(tempfile.mkdtemp())
        self.base_dir_patcher = patch.object(TempFileManager, 'BASE_DIR', self.temp_test_dir)
        self.base_dir_patcher.start()
    
    def teardown_method(self):
        """Clean up integration test environment."""
        self.base_dir_patcher.stop()
        if self.temp_test_dir.exists():
            shutil.rmtree(self.temp_test_dir, ignore_errors=True)
    
    def test_full_session_lifecycle(self):
        """Test complete session lifecycle: create, use, cleanup."""
        # Generate session ID
        session_id = TempFileManager.generate_session_id()
        
        # Create session directories and files
        for subdir in ["uploads", "processing", "downloads"]:
            session_path = TempFileManager.get_session_path(session_id, subdir)
            
            # Create test files
            for i in range(3):
                test_file = session_path / f"file_{i}.txt"
                test_file.write_text(f"Content for {subdir} file {i}")
        
        # Verify session info
        info = TempFileManager.get_session_info(session_id)
        assert info['uploads']['count'] == 3
        assert info['processing']['count'] == 3
        assert info['downloads']['count'] == 3
        
        # Calculate file hashes
        test_file = self.temp_test_dir / "uploads" / session_id / "file_0.txt"
        file_hash = TempFileManager.calculate_file_hash(test_file)
        assert len(file_hash) == 64
        
        # Check disk usage
        usage_info = TempFileManager.check_disk_usage()
        assert 'usage_percent' in usage_info
        
        # Schedule cleanup
        with patch('tasks.cleanup_abandoned_files.apply_async') as mock_schedule:
            TempFileManager.schedule_cleanup(session_id)
            mock_schedule.assert_called_once()
        
        # Perform cleanup
        cleanup_result = TempFileManager.cleanup_session(session_id)
        assert cleanup_result is True
        
        # Verify cleanup
        for subdir in ["uploads", "processing", "downloads"]:
            session_path = self.temp_test_dir / subdir / session_id
            assert not session_path.exists()
        
        # Verify session info after cleanup
        info_after = TempFileManager.get_session_info(session_id)
        assert info_after['total_size_mb'] == 0