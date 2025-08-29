"""Temporary file manager for handling temporary PDF files and processing."""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Union
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class TempFileManager:
    """Manages temporary files for PDF processing operations."""
    
    def __init__(self, session_id: str):
        """Initialize temporary file manager.
        
        Args:
            session_id: Session identifier for organizing temp files
        """
        self.session_id = session_id
        self.temp_dir = Path(tempfile.gettempdir()) / 'pdf_processor' / session_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized temp file manager for session {session_id}")
    
    @contextmanager
    def temp_file(self, suffix: str = '.pdf', prefix: str = 'temp_'):
        """Context manager for creating temporary files.
        
        Args:
            suffix: File suffix (e.g., '.pdf')
            prefix: File prefix (e.g., 'temp_')
            
        Yields:
            Path to temporary file
        """
        temp_file = None
        try:
            # Create temporary file in session directory
            fd, temp_path = tempfile.mkstemp(
                suffix=suffix, 
                prefix=prefix, 
                dir=str(self.temp_dir)
            )
            os.close(fd)  # Close file descriptor
            temp_file = Path(temp_path)
            
            logger.debug(f"Created temporary file: {temp_file}")
            yield temp_file
            
        finally:
            # Clean up temporary file
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                    logger.debug(f"Deleted temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file}: {e}")
    
    def create_temp_copy(self, source_path: Union[str, Path]) -> Path:
        """Create a temporary copy of a file.
        
        Args:
            source_path: Path to source file
            
        Returns:
            Path to temporary copy
        """
        source_path = Path(source_path)
        suffix = source_path.suffix
        temp_path = self.temp_dir / f"copy_{source_path.stem}{suffix}"
        
        shutil.copy2(source_path, temp_path)
        logger.debug(f"Created temp copy: {source_path} -> {temp_path}")
        
        return temp_path
    
    def cleanup(self):
        """Clean up all temporary files for this session."""
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory for session {self.session_id}")
            except Exception as e:
                logger.error(f"Failed to clean up temp directory: {e}")
    
    def get_temp_path(self, filename: str) -> Path:
        """Get path for a temporary file.
        
        Args:
            filename: Name of temporary file
            
        Returns:
            Full path to temporary file
        """
        return self.temp_dir / filename
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()