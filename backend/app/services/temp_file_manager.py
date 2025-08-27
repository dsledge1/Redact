"""Temporary file management for Ultimate PDF processing."""

import tempfile
import hashlib
import shutil
import uuid
import psutil
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Union, Dict, List, Any
from datetime import timedelta, datetime
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)


class TempFileManager:
    """Manages temporary files for PDF processing operations.
    
    Handles session-based file organization with automatic cleanup
    and disk usage monitoring for the Ultimate PDF application.
    """
    
    BASE_DIR = Path(tempfile.gettempdir()) / "ultimate_pdf"
    CLEANUP_DELAY_HOURS = 8
    MAX_DISK_USAGE_PERCENT = 85
    EMERGENCY_CLEANUP_THRESHOLD = 95
    SESSION_CACHE_PREFIX = "session_info"
    MONITORING_INTERVAL = 300  # 5 minutes
    
    # File size limits (bytes)
    MAX_SESSION_SIZE = 1024 * 1024 * 1024  # 1 GB per session
    WARNING_SESSION_SIZE = 500 * 1024 * 1024  # 500 MB warning threshold
    
    # Session lifecycle tracking
    _active_sessions = set()
    _session_lock = threading.Lock()
    
    @classmethod
    def get_session_path(
        cls, 
        session_id: str, 
        subdir: str = "uploads"
    ) -> Path:
        """Get the path for a specific session and subdirectory.
        
        Creates directory structure: /tmp/ultimate_pdf/{subdir}/{session_id}/
        
        Args:
            session_id: Unique session identifier
            subdir: Subdirectory type ('uploads', 'processing', 'downloads')
            
        Returns:
            Path object for the session directory
            
        Raises:
            ValueError: If session_id is empty or subdir is invalid
        """
        if not session_id or not session_id.strip():
            raise ValueError("Session ID cannot be empty")
        
        if subdir not in ["uploads", "processing", "downloads"]:
            raise ValueError(f"Invalid subdirectory: {subdir}")
        
        session_path = cls.BASE_DIR / subdir / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        
        return session_path
    
    @classmethod
    def cleanup_session(cls, session_id: str) -> bool:
        """Remove all files for a specific session.
        
        Removes files from uploads, processing, and downloads directories
        for the given session ID.
        
        Args:
            session_id: Session identifier to cleanup
            
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            cleanup_successful = True
            
            for subdir in ["uploads", "processing", "downloads"]:
                session_path = cls.BASE_DIR / subdir / session_id
                if session_path.exists():
                    shutil.rmtree(session_path, ignore_errors=False)
            
            return cleanup_successful
            
        except Exception as e:
            # Log error in production
            print(f"Cleanup failed for session {session_id}: {str(e)}")
            return False
    
    @classmethod
    def schedule_cleanup(cls, session_id: str) -> None:
        """Schedule delayed cleanup for a session using Celery.
        
        Queues a background task to clean up session files after
        the configured delay period.
        
        Args:
            session_id: Session identifier to schedule for cleanup
        """
        try:
            # Import here to avoid circular imports
            from tasks import cleanup_abandoned_files
            
            cleanup_time = timezone.now() + timedelta(hours=cls.CLEANUP_DELAY_HOURS)
            cleanup_abandoned_files.apply_async(
                args=[session_id],
                eta=cleanup_time
            )
        except ImportError:
            # Fallback for when Celery is not available
            print(f"Warning: Could not schedule cleanup for session {session_id}")
    
    @classmethod
    def generate_session_id(cls) -> str:
        """Generate a new unique session identifier.
        
        Returns:
            32-character hexadecimal session ID
        """
        return uuid.uuid4().hex
    
    @classmethod
    def calculate_file_hash(cls, file_path: Union[str, Path]) -> str:
        """Calculate SHA-256 hash of a file.
        
        Args:
            file_path: Path to the file to hash
            
        Returns:
            Hexadecimal SHA-256 hash string
            
        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file cannot be read
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        hash_sha256 = hashlib.sha256()
        
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
                    
            return hash_sha256.hexdigest()
            
        except IOError as e:
            raise IOError(f"Could not read file {file_path}: {str(e)}")
    
    @classmethod
    def check_disk_usage(cls) -> dict:
        """Check current disk usage and available space.
        
        Returns:
            Dictionary with disk usage statistics including:
            - total_gb: Total disk space in GB
            - used_gb: Used disk space in GB  
            - free_gb: Free disk space in GB
            - usage_percent: Percentage of disk space used
            - needs_cleanup: Boolean indicating if emergency cleanup needed
        """
        try:
            # Get disk usage for the temp directory
            usage = psutil.disk_usage(cls.BASE_DIR.parent)
            
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            usage_percent = (usage.used / usage.total) * 100
            
            return {
                'total_gb': round(total_gb, 2),
                'used_gb': round(used_gb, 2),
                'free_gb': round(free_gb, 2),
                'usage_percent': round(usage_percent, 2),
                'needs_cleanup': usage_percent > cls.MAX_DISK_USAGE_PERCENT
            }
            
        except Exception as e:
            print(f"Error checking disk usage: {str(e)}")
            return {
                'total_gb': 0,
                'used_gb': 0,
                'free_gb': 0,
                'usage_percent': 0,
                'needs_cleanup': False
            }
    
    @classmethod
    def emergency_cleanup(cls) -> int:
        """Perform emergency cleanup of old session files.
        
        Removes the oldest session directories when disk usage is high.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            cleaned_sessions = 0
            
            if not cls.BASE_DIR.exists():
                return 0
            
            # Get all session directories sorted by modification time
            session_dirs = []
            for subdir in ["uploads", "processing", "downloads"]:
                subdir_path = cls.BASE_DIR / subdir
                if subdir_path.exists():
                    for session_dir in subdir_path.iterdir():
                        if session_dir.is_dir():
                            session_dirs.append((session_dir.stat().st_mtime, session_dir.name))
            
            # Remove duplicates and sort by age (oldest first)
            unique_sessions = list(set(session_id for _, session_id in session_dirs))
            session_ages = {}
            for mtime, session_id in session_dirs:
                if session_id not in session_ages or mtime < session_ages[session_id]:
                    session_ages[session_id] = mtime
            
            sorted_sessions = sorted(session_ages.items(), key=lambda x: x[1])
            
            # Clean up oldest sessions until disk usage is acceptable
            for session_id, _ in sorted_sessions:
                if cls.check_disk_usage()['needs_cleanup']:
                    if cls.cleanup_session(session_id):
                        cleaned_sessions += 1
                else:
                    break
            
            return cleaned_sessions
            
        except Exception as e:
            print(f"Emergency cleanup failed: {str(e)}")
            return 0
    
    @classmethod
    def get_session_info(cls, session_id: str) -> dict:
        """Get information about a session's files and disk usage.
        
        Args:
            session_id: Session identifier to analyze
            
        Returns:
            Dictionary with session statistics including file counts and sizes
        """
        try:
            info = {
                'session_id': session_id,
                'uploads': {'count': 0, 'size_mb': 0},
                'processing': {'count': 0, 'size_mb': 0},
                'downloads': {'count': 0, 'size_mb': 0},
                'total_size_mb': 0
            }
            
            total_size = 0
            
            for subdir in ["uploads", "processing", "downloads"]:
                session_path = cls.BASE_DIR / subdir / session_id
                if session_path.exists():
                    files = list(session_path.rglob('*'))
                    file_count = len([f for f in files if f.is_file()])
                    subdir_size = sum(f.stat().st_size for f in files if f.is_file())
                    
                    info[subdir]['count'] = file_count
                    info[subdir]['size_mb'] = round(subdir_size / (1024**2), 2)
                    total_size += subdir_size
            
            info['total_size_mb'] = round(total_size / (1024**2), 2)
            return info
            
        except Exception as e:
            print(f"Error getting session info: {str(e)}")
            return {
                'session_id': session_id,
                'uploads': {'count': 0, 'size_mb': 0},
                'processing': {'count': 0, 'size_mb': 0},
                'downloads': {'count': 0, 'size_mb': 0},
                'total_size_mb': 0,
                'error': str(e)
            }
    
    @classmethod
    def register_session(cls, session_id: str) -> Dict[str, Any]:
        """Register a new active session with lifecycle tracking.
        
        Args:
            session_id: Session identifier to register
            
        Returns:
            Dictionary with registration results and session info
        """
        try:
            with cls._session_lock:
                cls._active_sessions.add(session_id)
            
            # Cache session creation time
            session_key = f"{cls.SESSION_CACHE_PREFIX}_{session_id}"
            session_data = {
                'created_at': timezone.now().isoformat(),
                'last_accessed': timezone.now().isoformat(),
                'status': 'active',
                'file_operations': 0
            }
            
            try:
                cache.set(session_key, session_data, timeout=cls.CLEANUP_DELAY_HOURS * 3600)
            except Exception as cache_error:
                logger.warning(f"Failed to cache session data: {cache_error}")
            
            logger.info(f"Registered new session: {session_id}")
            
            return {
                'success': True,
                'session_id': session_id,
                'registration_time': session_data['created_at'],
                'active_sessions_count': len(cls._active_sessions),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Session registration error for {session_id}: {str(e)}")
            return {
                'success': False,
                'session_id': session_id,
                'error': str(e)
            }
    
    @classmethod
    def update_session_access(cls, session_id: str) -> bool:
        """Update session last access time.
        
        Args:
            session_id: Session identifier to update
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            session_key = f"{cls.SESSION_CACHE_PREFIX}_{session_id}"
            session_data = cache.get(session_key)
            
            if session_data:
                session_data['last_accessed'] = timezone.now().isoformat()
                session_data['file_operations'] = session_data.get('file_operations', 0) + 1
                cache.set(session_key, session_data, timeout=cls.CLEANUP_DELAY_HOURS * 3600)
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Failed to update session access for {session_id}: {str(e)}")
            return False
    
    @classmethod
    def get_session_lifecycle_info(cls, session_id: str) -> Dict[str, Any]:
        """Get comprehensive session lifecycle information.
        
        Args:
            session_id: Session identifier to analyze
            
        Returns:
            Dictionary with session lifecycle data
        """
        try:
            session_key = f"{cls.SESSION_CACHE_PREFIX}_{session_id}"
            session_data = cache.get(session_key, {})
            
            # Get filesystem info
            filesystem_info = cls.get_session_info(session_id)
            
            # Calculate session age
            created_at = session_data.get('created_at')
            age_hours = 0
            if created_at:
                created_time = timezone.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                age_hours = (timezone.now() - created_time).total_seconds() / 3600
            
            # Determine cleanup status
            cleanup_due = age_hours >= cls.CLEANUP_DELAY_HOURS
            
            return {
                'session_id': session_id,
                'created_at': session_data.get('created_at'),
                'last_accessed': session_data.get('last_accessed'),
                'age_hours': round(age_hours, 2),
                'file_operations': session_data.get('file_operations', 0),
                'status': session_data.get('status', 'unknown'),
                'is_active': session_id in cls._active_sessions,
                'cleanup_due': cleanup_due,
                'cleanup_scheduled_at': created_at and (timezone.datetime.fromisoformat(created_at.replace('Z', '+00:00')) + timedelta(hours=cls.CLEANUP_DELAY_HOURS)).isoformat(),
                'filesystem_info': filesystem_info,
                'size_warning': filesystem_info.get('total_size_mb', 0) * 1024 * 1024 > cls.WARNING_SESSION_SIZE
            }
            
        except Exception as e:
            logger.error(f"Error getting session lifecycle info for {session_id}: {str(e)}")
            return {
                'session_id': session_id,
                'error': str(e)
            }
    
    @classmethod
    def get_all_active_sessions(cls) -> Dict[str, Any]:
        """Get information about all active sessions.
        
        Returns:
            Dictionary with active session information
        """
        try:
            active_sessions_info = []
            
            with cls._session_lock:
                active_sessions = cls._active_sessions.copy()
            
            for session_id in active_sessions:
                session_info = cls.get_session_lifecycle_info(session_id)
                active_sessions_info.append(session_info)
            
            # Calculate totals
            total_size_mb = sum(
                session.get('filesystem_info', {}).get('total_size_mb', 0) 
                for session in active_sessions_info
            )
            
            cleanup_due_count = sum(
                1 for session in active_sessions_info 
                if session.get('cleanup_due', False)
            )
            
            return {
                'success': True,
                'active_sessions_count': len(active_sessions_info),
                'total_size_mb': round(total_size_mb, 2),
                'cleanup_due_count': cleanup_due_count,
                'sessions': active_sessions_info,
                'system_disk_usage': cls.check_disk_usage(),
                'timestamp': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting active sessions: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @classmethod
    def intelligent_cleanup(cls, force_emergency: bool = False) -> Dict[str, Any]:
        """Perform intelligent cleanup based on session age, size, and disk usage.
        
        Args:
            force_emergency: Force emergency cleanup regardless of disk usage
            
        Returns:
            Dictionary with cleanup results
        """
        try:
            cleanup_results = {
                'cleanup_triggered': timezone.now().isoformat(),
                'sessions_analyzed': 0,
                'sessions_cleaned': 0,
                'space_freed_mb': 0,
                'cleanup_details': [],
                'disk_usage_before': cls.check_disk_usage(),
                'emergency_mode': force_emergency
            }
            
            disk_usage = cleanup_results['disk_usage_before']
            emergency_cleanup_needed = (
                force_emergency or 
                disk_usage.get('usage_percent', 0) > cls.EMERGENCY_CLEANUP_THRESHOLD
            )
            
            # Get all sessions (both active and inactive)
            all_sessions = cls._discover_all_sessions()
            cleanup_results['sessions_analyzed'] = len(all_sessions)
            
            # Sort sessions by priority for cleanup
            sessions_by_priority = cls._prioritize_sessions_for_cleanup(all_sessions)
            
            for session_data in sessions_by_priority:
                session_id = session_data['session_id']
                
                # Determine if session should be cleaned up
                should_cleanup = (
                    emergency_cleanup_needed or
                    session_data.get('age_hours', 0) >= cls.CLEANUP_DELAY_HOURS or
                    session_data.get('size_mb', 0) > cls.MAX_SESSION_SIZE / (1024 * 1024) or
                    session_data.get('status') == 'abandoned'
                )
                
                if should_cleanup:
                    size_before = session_data.get('size_mb', 0)
                    
                    if cls.cleanup_session(session_id):
                        cleanup_results['sessions_cleaned'] += 1
                        cleanup_results['space_freed_mb'] += size_before
                        
                        cleanup_results['cleanup_details'].append({
                            'session_id': session_id,
                            'reason': session_data.get('cleanup_reason', 'age_threshold'),
                            'size_freed_mb': size_before,
                            'age_hours': session_data.get('age_hours', 0)
                        })
                        
                        # Remove from active sessions
                        with cls._session_lock:
                            cls._active_sessions.discard(session_id)
                        
                        logger.info(f"Cleaned up session {session_id}: {size_before:.2f} MB freed")
                
                # Stop if we've freed enough space (unless in emergency mode)
                if not emergency_cleanup_needed:
                    current_disk_usage = cls.check_disk_usage()
                    if current_disk_usage.get('usage_percent', 100) < cls.MAX_DISK_USAGE_PERCENT:
                        break
            
            cleanup_results['disk_usage_after'] = cls.check_disk_usage()
            
            logger.info(f"Cleanup completed: {cleanup_results['sessions_cleaned']} sessions, "
                       f"{cleanup_results['space_freed_mb']:.2f} MB freed")
            
            return cleanup_results
            
        except Exception as e:
            logger.error(f"Intelligent cleanup error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'cleanup_triggered': timezone.now().isoformat()
            }
    
    @classmethod
    def _discover_all_sessions(cls) -> List[Dict[str, Any]]:
        """Discover all sessions from filesystem and cache."""
        sessions = {}
        
        try:
            # Scan filesystem for sessions
            if cls.BASE_DIR.exists():
                for subdir in ["uploads", "processing", "downloads"]:
                    subdir_path = cls.BASE_DIR / subdir
                    if subdir_path.exists():
                        for session_dir in subdir_path.iterdir():
                            if session_dir.is_dir():
                                session_id = session_dir.name
                                if session_id not in sessions:
                                    sessions[session_id] = {
                                        'session_id': session_id,
                                        'discovered_in': [subdir],
                                        'last_modified': session_dir.stat().st_mtime
                                    }
                                else:
                                    sessions[session_id]['discovered_in'].append(subdir)
                                    sessions[session_id]['last_modified'] = max(
                                        sessions[session_id]['last_modified'],
                                        session_dir.stat().st_mtime
                                    )
            
            # Enhance with cached session data
            for session_id, session_info in sessions.items():
                lifecycle_info = cls.get_session_lifecycle_info(session_id)
                filesystem_info = cls.get_session_info(session_id)
                
                session_info.update({
                    'age_hours': lifecycle_info.get('age_hours', 0),
                    'size_mb': filesystem_info.get('total_size_mb', 0),
                    'file_count': sum(
                        filesystem_info.get(subdir, {}).get('count', 0) 
                        for subdir in ['uploads', 'processing', 'downloads']
                    ),
                    'status': lifecycle_info.get('status', 'unknown'),
                    'is_active': lifecycle_info.get('is_active', False),
                    'cleanup_due': lifecycle_info.get('cleanup_due', False)
                })
            
            return list(sessions.values())
            
        except Exception as e:
            logger.error(f"Session discovery error: {str(e)}")
            return []
    
    @classmethod
    def _prioritize_sessions_for_cleanup(cls, sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prioritize sessions for cleanup based on various factors."""
        
        def cleanup_priority(session):
            score = 0
            
            # Age factor (older = higher priority)
            age_hours = session.get('age_hours', 0)
            if age_hours > cls.CLEANUP_DELAY_HOURS * 2:
                score += 1000  # Very old
            elif age_hours > cls.CLEANUP_DELAY_HOURS:
                score += 500   # Due for cleanup
            
            # Size factor (larger = higher priority in emergency)
            size_mb = session.get('size_mb', 0)
            if size_mb > cls.MAX_SESSION_SIZE / (1024 * 1024):
                score += 800   # Oversized
                session['cleanup_reason'] = 'oversized'
            elif size_mb > cls.WARNING_SESSION_SIZE / (1024 * 1024):
                score += 200   # Large
            
            # Activity factor (inactive = higher priority)
            if not session.get('is_active', True):
                score += 300
                if 'cleanup_reason' not in session:
                    session['cleanup_reason'] = 'inactive'
            
            # Status factor
            if session.get('status') == 'abandoned':
                score += 600
                session['cleanup_reason'] = 'abandoned'
            elif session.get('cleanup_due', False):
                score += 400
                if 'cleanup_reason' not in session:
                    session['cleanup_reason'] = 'age_threshold'
            
            # File count factor
            file_count = session.get('file_count', 0)
            if file_count == 0:
                score += 100  # Empty sessions
                session['cleanup_reason'] = 'empty'
            
            return score
        
        # Sort by cleanup priority (highest first)
        return sorted(sessions, key=cleanup_priority, reverse=True)
    
    @classmethod
    def monitor_disk_usage(cls) -> Dict[str, Any]:
        """Continuous monitoring of disk usage with alerts.
        
        Returns:
            Dictionary with monitoring results
        """
        try:
            disk_usage = cls.check_disk_usage()
            usage_percent = disk_usage.get('usage_percent', 0)
            
            monitoring_result = {
                'timestamp': timezone.now().isoformat(),
                'disk_usage': disk_usage,
                'alerts': [],
                'recommendations': [],
                'actions_taken': []
            }
            
            # Generate alerts based on usage thresholds
            if usage_percent >= cls.EMERGENCY_CLEANUP_THRESHOLD:
                monitoring_result['alerts'].append({
                    'level': 'critical',
                    'message': f'Disk usage critical: {usage_percent}%',
                    'threshold': cls.EMERGENCY_CLEANUP_THRESHOLD
                })
                monitoring_result['recommendations'].append('Immediate emergency cleanup required')
                
                # Trigger emergency cleanup
                cleanup_result = cls.intelligent_cleanup(force_emergency=True)
                monitoring_result['actions_taken'].append({
                    'action': 'emergency_cleanup',
                    'result': cleanup_result
                })
                
            elif usage_percent >= cls.MAX_DISK_USAGE_PERCENT:
                monitoring_result['alerts'].append({
                    'level': 'warning',
                    'message': f'Disk usage high: {usage_percent}%',
                    'threshold': cls.MAX_DISK_USAGE_PERCENT
                })
                monitoring_result['recommendations'].append('Schedule cleanup of old sessions')
                
            elif usage_percent >= cls.MAX_DISK_USAGE_PERCENT - 10:
                monitoring_result['alerts'].append({
                    'level': 'info',
                    'message': f'Disk usage approaching threshold: {usage_percent}%',
                    'threshold': cls.MAX_DISK_USAGE_PERCENT - 10
                })
            
            # Check for sessions needing cleanup
            active_sessions_info = cls.get_all_active_sessions()
            if active_sessions_info.get('cleanup_due_count', 0) > 0:
                monitoring_result['recommendations'].append(
                    f"{active_sessions_info['cleanup_due_count']} sessions due for cleanup"
                )
            
            return monitoring_result
            
        except Exception as e:
            logger.error(f"Disk usage monitoring error: {str(e)}")
            return {
                'timestamp': timezone.now().isoformat(),
                'error': str(e),
                'alerts': [{
                    'level': 'error',
                    'message': f'Monitoring failed: {str(e)}'
                }]
            }
    
    @classmethod
    def archive_session(cls, session_id: str, archive_path: Optional[Path] = None) -> Dict[str, Any]:
        """Archive a session before cleanup for potential recovery.
        
        Args:
            session_id: Session to archive
            archive_path: Optional custom archive location
            
        Returns:
            Dictionary with archive results
        """
        try:
            if not archive_path:
                archive_path = cls.BASE_DIR / "archives"
                archive_path.mkdir(exist_ok=True)
            
            archive_file = archive_path / f"session_{session_id}_{int(time.time())}.tar.gz"
            
            # Create archive of session files
            import tarfile
            
            with tarfile.open(archive_file, "w:gz") as tar:
                for subdir in ["uploads", "processing", "downloads"]:
                    session_path = cls.BASE_DIR / subdir / session_id
                    if session_path.exists():
                        tar.add(session_path, arcname=f"{subdir}/{session_id}")
            
            # Get session metadata
            session_info = cls.get_session_lifecycle_info(session_id)
            metadata_file = archive_path / f"session_{session_id}_metadata.json"
            
            import json
            with open(metadata_file, 'w') as f:
                json.dump(session_info, f, indent=2)
            
            return {
                'success': True,
                'session_id': session_id,
                'archive_file': str(archive_file),
                'metadata_file': str(metadata_file),
                'archive_size': archive_file.stat().st_size,
                'archived_at': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Session archiving error for {session_id}: {str(e)}")
            return {
                'success': False,
                'session_id': session_id,
                'error': str(e)
            }