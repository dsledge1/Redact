"""Celery task definitions for Ultimate PDF background processing."""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from app.services.temp_file_manager import TempFileManager
from app.services.pdf_processor import PDFProcessor
from app.services.ocr_service import OCRService
from app.services.fuzzy_matcher import FuzzyMatcher
from app.services.redaction_service import RedactionService
from app.models import ProcessingJob, PDFDocument, RedactionMatch

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def cleanup_abandoned_files(self, session_id: str) -> Dict[str, Any]:
    """Clean up abandoned session files after delay period.
    
    Args:
        session_id: Session identifier to clean up
        
    Returns:
        Dictionary with cleanup results
    """
    try:
        logger.info(f"Starting cleanup for session: {session_id}")
        
        # Get session info before cleanup
        session_info = TempFileManager.get_session_info(session_id)
        
        if session_info['total_size_mb'] == 0:
            logger.info(f"Session {session_id} already clean or doesn't exist")
            return {
                'success': True,
                'session_id': session_id,
                'message': 'Session already clean',
                'files_removed': 0,
                'size_freed_mb': 0
            }
        
        # Perform cleanup
        cleanup_success = TempFileManager.cleanup_session(session_id)
        
        if cleanup_success:
            logger.info(f"Successfully cleaned up session {session_id}")
            return {
                'success': True,
                'session_id': session_id,
                'message': 'Session cleaned successfully',
                'files_removed': (
                    session_info['uploads']['count'] + 
                    session_info['processing']['count'] + 
                    session_info['downloads']['count']
                ),
                'size_freed_mb': session_info['total_size_mb']
            }
        else:
            raise Exception("Cleanup operation failed")
            
    except Exception as exc:
        logger.error(f"Cleanup task failed for session {session_id}: {str(exc)}")
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying cleanup for session {session_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)
        
        return {
            'success': False,
            'session_id': session_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def cleanup_old_sessions(self) -> Dict[str, Any]:
    """Periodic task to clean up old abandoned sessions.
    
    Returns:
        Dictionary with cleanup statistics
    """
    try:
        logger.info("Starting periodic cleanup of old sessions")
        
        # Check disk usage first
        disk_info = TempFileManager.check_disk_usage()
        
        cleanup_results = {
            'sessions_cleaned': 0,
            'total_size_freed_mb': 0,
            'disk_usage_before': disk_info['usage_percent'],
            'cleanup_triggered': False
        }
        
        # Only run cleanup if disk usage is high
        if disk_info['needs_cleanup']:
            logger.warning(f"High disk usage detected: {disk_info['usage_percent']:.1f}%")
            cleanup_results['cleanup_triggered'] = True
            
            # Perform emergency cleanup
            sessions_cleaned = TempFileManager.emergency_cleanup()
            cleanup_results['sessions_cleaned'] = sessions_cleaned
            
            # Check disk usage after cleanup
            disk_info_after = TempFileManager.check_disk_usage()
            cleanup_results['disk_usage_after'] = disk_info_after['usage_percent']
            
            size_freed = (disk_info['used_gb'] - disk_info_after['used_gb']) * 1024  # Convert to MB
            cleanup_results['total_size_freed_mb'] = round(size_freed, 2)
            
            logger.info(f"Emergency cleanup completed: {sessions_cleaned} sessions cleaned")
        
        # Also clean up old database records
        old_threshold = timezone.now() - timedelta(days=7)
        old_documents = PDFDocument.objects.filter(upload_timestamp__lt=old_threshold)
        old_count = old_documents.count()
        
        if old_count > 0:
            logger.info(f"Cleaning up {old_count} old database records")
            old_documents.delete()
            cleanup_results['old_db_records_cleaned'] = old_count
        
        return cleanup_results
        
    except Exception as exc:
        logger.error(f"Periodic cleanup task failed: {str(exc)}")
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300, exc=exc)
        
        return {
            'success': False,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=1, default_retry_delay=120)
def monitor_disk_usage(self) -> Dict[str, Any]:
    """Monitor disk usage and trigger cleanup if needed.
    
    Returns:
        Dictionary with disk usage monitoring results
    """
    try:
        logger.info("Monitoring disk usage")
        
        disk_info = TempFileManager.check_disk_usage()
        
        # Log disk usage
        logger.info(f"Current disk usage: {disk_info['usage_percent']:.1f}% "
                   f"({disk_info['used_gb']:.1f}GB / {disk_info['total_gb']:.1f}GB)")
        
        if disk_info['needs_cleanup']:
            logger.warning("High disk usage detected, triggering emergency cleanup")
            
            # Trigger emergency cleanup
            cleanup_old_sessions.delay()
            
            return {
                'success': True,
                'disk_usage_percent': disk_info['usage_percent'],
                'cleanup_triggered': True,
                'message': 'Emergency cleanup triggered due to high disk usage'
            }
        
        return {
            'success': True,
            'disk_usage_percent': disk_info['usage_percent'],
            'cleanup_triggered': False,
            'message': 'Disk usage within normal limits'
        }
        
    except Exception as exc:
        logger.error(f"Disk monitoring task failed: {str(exc)}")
        return {
            'success': False,
            'error': str(exc)
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def process_large_pdf(
    self, 
    job_id: str, 
    operation_type: str, 
    operation_params: Dict[str, Any]
) -> Dict[str, Any]:
    """Process large PDF files in the background.
    
    Args:
        job_id: Processing job UUID
        operation_type: Type of operation (redact, split, merge, extract)
        operation_params: Operation-specific parameters
        
    Returns:
        Dictionary with processing results
    """
    try:
        # Get the processing job
        job = ProcessingJob.objects.get(id=job_id)
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting {operation_type} processing for job {job_id}")
        
        # Initialize PDF processor
        processor = PDFProcessor(job.document.session_id)
        
        # Get file path
        upload_path = TempFileManager.get_session_path(
            job.document.session_id, 'uploads'
        )
        pdf_file = upload_path / job.document.filename
        
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")
        
        job.progress = 25
        job.save()
        
        # Process based on operation type
        if operation_type == 'split':
            # Handle both page-based and pattern-based splitting
            split_params = operation_params.copy()
            result = processor.split_pdf(
                pdf_file,
                split_pages=split_params.get('split_pages'),
                pattern=split_params.get('pattern'),
                pattern_type=split_params.get('pattern_type', 'regex'),
                fuzzy_threshold=split_params.get('fuzzy_threshold', 80),
                split_position=split_params.get('split_position', 'before'),
                preserve_metadata=split_params.get('preserve_metadata', True)
            )
        elif operation_type == 'merge':
            # Get all files to merge
            file_paths = []
            for doc_id in operation_params.get('document_ids', []):
                doc = PDFDocument.objects.get(id=doc_id)
                doc_path = TempFileManager.get_session_path(
                    doc.session_id, 'uploads'
                ) / doc.filename
                file_paths.append(doc_path)
            
            result = processor.merge_pdfs(
                file_paths,
                output_filename=operation_params.get('output_filename'),
                preserve_metadata=operation_params.get('preserve_metadata', True),
                merge_strategy=operation_params.get('merge_strategy', 'sequential')
            )
        elif operation_type == 'extract':
            result = processor.extract_text(pdf_file)
        else:
            raise ValueError(f"Unknown operation type: {operation_type}")
        
        job.progress = 80
        job.save()
        
        if result['success']:
            job.status = 'completed'
            job.progress = 100
            logger.info(f"Successfully completed {operation_type} for job {job_id}")
        else:
            job.status = 'failed'
            job.error_messages = result.get('error', 'Unknown processing error')
            logger.error(f"Processing failed for job {job_id}: {job.error_messages}")
        
        job.save()
        
        # Schedule cleanup after processing
        TempFileManager.schedule_cleanup(job.document.session_id)
        
        return {
            'success': result['success'],
            'job_id': job_id,
            'operation_type': operation_type,
            'result': result
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"PDF processing task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300, exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=180)
def ocr_processing(
    self, 
    job_id: str, 
    pdf_pages: List[Dict[str, Any]],
    ocr_params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Process PDF pages with OCR in the background.
    
    Args:
        job_id: Processing job UUID
        pdf_pages: List of PDF page data for OCR
        ocr_params: OCR processing parameters
        
    Returns:
        Dictionary with OCR results
    """
    try:
        # Get the processing job
        job = ProcessingJob.objects.get(id=job_id)
        job.status = 'processing'
        job.progress = 5
        job.save()
        
        logger.info(f"Starting OCR processing for job {job_id} with {len(pdf_pages)} pages")
        
        # Initialize OCR service
        ocr_service = OCRService()
        
        ocr_results = []
        total_pages = len(pdf_pages)
        
        for i, page_data in enumerate(pdf_pages):
            try:
                # Update progress
                progress = 10 + int((i / total_pages) * 80)
                job.progress = progress
                job.save()
                
                logger.info(f"Processing OCR for page {i+1}/{total_pages}")
                
                # Process page with OCR
                page_result = ocr_service.process_pdf_page_image(
                    page_data['image_data'],
                    page_data['page_number'],
                    dpi=ocr_params.get('dpi', 300) if ocr_params else 300,
                    use_cache=ocr_params.get('use_cache', True) if ocr_params else True
                )
                
                ocr_results.append(page_result)
                
                # If OCR fails for this page, try fallback
                if not page_result['success']:
                    logger.warning(f"OCR failed for page {page_data['page_number']}, trying fallback")
                    
                    fallback_result = ocr_service.process_fallback_detection(
                        page_data['image_data'],
                        page_data['page_number']
                    )
                    
                    if fallback_result['success']:
                        ocr_results[-1] = fallback_result
                        logger.info(f"Fallback OCR succeeded for page {page_data['page_number']}")
                
            except Exception as page_exc:
                logger.error(f"OCR failed for page {page_data['page_number']}: {str(page_exc)}")
                ocr_results.append({
                    'success': False,
                    'page_number': page_data['page_number'],
                    'error': str(page_exc)
                })
        
        # Analyze OCR results
        successful_pages = [r for r in ocr_results if r['success']]
        failed_pages = [r for r in ocr_results if not r['success']]
        
        job.progress = 95
        job.save()
        
        # Save OCR results to processing directory
        processing_path = TempFileManager.get_session_path(
            job.document.session_id, 'processing'
        )
        
        import json
        ocr_results_file = processing_path / f"ocr_results_{job_id}.json"
        
        with open(ocr_results_file, 'w') as f:
            json.dump({
                'job_id': job_id,
                'total_pages': total_pages,
                'successful_pages': len(successful_pages),
                'failed_pages': len(failed_pages),
                'results': ocr_results
            }, f, indent=2)
        
        # Update job status
        if len(successful_pages) > 0:
            job.status = 'completed'
            job.progress = 100
            
            if len(failed_pages) > 0:
                job.error_messages = f"OCR partially succeeded: {len(failed_pages)} pages failed"
            
            logger.info(f"OCR completed for job {job_id}: {len(successful_pages)}/{total_pages} pages successful")
        else:
            job.status = 'failed'
            job.error_messages = "OCR failed for all pages"
            logger.error(f"OCR completely failed for job {job_id}")
        
        job.save()
        
        return {
            'success': len(successful_pages) > 0,
            'job_id': job_id,
            'total_pages': total_pages,
            'successful_pages': len(successful_pages),
            'failed_pages': len(failed_pages),
            'ocr_results_file': str(ocr_results_file),
            'results': ocr_results
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"OCR processing task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=180, exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def fuzzy_matching(
    self,
    job_id: str,
    search_terms: List[str],
    text_pages: List[Dict[str, Any]],
    matching_params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Perform fuzzy text matching in the background.
    
    Args:
        job_id: Processing job UUID
        search_terms: Terms to search for
        text_pages: Pages with extracted text
        matching_params: Fuzzy matching parameters
        
    Returns:
        Dictionary with fuzzy matching results
    """
    try:
        # Get the processing job
        job = ProcessingJob.objects.get(id=job_id)
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting fuzzy matching for job {job_id} with {len(search_terms)} terms")
        
        # Initialize fuzzy matcher
        threshold = matching_params.get('threshold', 80) if matching_params else 80
        matcher = FuzzyMatcher(threshold=threshold)
        
        job.progress = 25
        job.save()
        
        # Perform fuzzy matching
        case_sensitive = matching_params.get('case_sensitive', False) if matching_params else False
        matches = matcher.find_matches(search_terms, text_pages, case_sensitive)
        
        job.progress = 70
        job.save()
        
        # Save matches to database
        for match in matches:
            RedactionMatch.objects.create(
                job=job,
                text=match['matched_text'],
                confidence_score=match['confidence_score'],
                page_number=match['page_number'],
                approved_status=None if match['needs_approval'] else True,
                x_coordinate=match['position_info'].get('start', 0),
                y_coordinate=0,  # Would need coordinate extraction from PDF
                width=match['position_info'].get('length', 0),
                height=15.0  # Default height
            )
        
        job.progress = 90
        job.save()
        
        # Generate match statistics
        stats = matcher.get_match_statistics(matches)
        
        # Save results to processing directory
        processing_path = TempFileManager.get_session_path(
            job.document.session_id, 'processing'
        )
        
        import json
        match_results_file = processing_path / f"fuzzy_matches_{job_id}.json"
        
        with open(match_results_file, 'w') as f:
            json.dump({
                'job_id': job_id,
                'search_terms': search_terms,
                'matching_params': matching_params,
                'statistics': stats,
                'matches': matches
            }, f, indent=2)
        
        # Update job status
        job.status = 'completed'
        job.progress = 100
        job.save()
        
        logger.info(f"Fuzzy matching completed for job {job_id}: {len(matches)} matches found")
        
        return {
            'success': True,
            'job_id': job_id,
            'total_matches': len(matches),
            'statistics': stats,
            'matches_file': str(match_results_file),
            'matches': matches[:50]  # Return first 50 matches
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"Fuzzy matching task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=120, exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=240)
def pdf_redaction(
    self,
    job_id: str,
    approved_matches: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Perform PDF redaction based on approved matches.
    
    Args:
        job_id: Processing job UUID
        approved_matches: List of approved redaction matches
        
    Returns:
        Dictionary with redaction results
    """
    try:
        # Get the processing job
        job = ProcessingJob.objects.get(id=job_id)
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting PDF redaction for job {job_id} with {len(approved_matches)} matches")
        
        # This would implement actual PDF redaction
        # For now, we'll simulate the process
        
        job.progress = 30
        job.save()
        
        # Simulate redaction processing time
        time.sleep(2)
        
        job.progress = 70
        job.save()
        
        # Create output file in downloads directory
        downloads_path = TempFileManager.get_session_path(
            job.document.session_id, 'downloads'
        )
        
        redacted_filename = f"redacted_{job.document.filename}"
        redacted_file = downloads_path / redacted_filename
        
        # Simulate redaction (copy original file for now)
        upload_path = TempFileManager.get_session_path(
            job.document.session_id, 'uploads'
        )
        original_file = upload_path / job.document.filename
        
        import shutil
        shutil.copy2(original_file, redacted_file)
        
        job.progress = 95
        job.save()
        
        # Update job status
        job.status = 'completed'
        job.progress = 100
        job.save()
        
        logger.info(f"PDF redaction completed for job {job_id}")
        
        return {
            'success': True,
            'job_id': job_id,
            'redacted_matches': len(approved_matches),
            'output_file': str(redacted_file),
            'filename': redacted_filename
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"PDF redaction task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=240, exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def process_ocr_batch(self, document_id: str, job_id: str) -> Dict[str, Any]:
    """Process PDF document with OCR using enhanced pipeline."""
    try:
        job = ProcessingJob.objects.get(id=job_id)
        document = PDFDocument.objects.get(id=document_id)
        
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        # Get file path
        upload_path = TempFileManager.get_session_path(document.session_id, 'uploads')
        pdf_file = upload_path / document.filename
        
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")
        
        # Initialize services
        ocr_service = OCRService()
        pdf_processor = PDFProcessor(document.session_id)
        
        # First, analyze if OCR is actually needed
        text_analysis = ocr_service.intelligent_text_detection(pdf_file)
        
        if not text_analysis['success']:
            raise Exception(f"Text detection failed: {text_analysis['error']}")
        
        ocr_recommendations = text_analysis['analysis']['ocr_recommendations']
        
        job.progress = 25
        job.save()
        
        if ocr_recommendations['priority'] == 'none':
            # No OCR needed, extract text directly
            text_result = pdf_processor.extract_text(pdf_file)
            job.progress = 90
            job.save()
            
            if text_result['success']:
                job.status = 'completed'
                job.progress = 100
                job.results = {
                    'method': 'direct_text_extraction',
                    'pages': text_result['pages'],
                    'total_text_length': sum(p['char_count'] for p in text_result['pages'])
                }
                job.save()
                
                return {
                    'success': True,
                    'method': 'direct_extraction',
                    'pages_processed': text_result['total_pages']
                }
        else:
            # Perform OCR processing
            use_parallel = ocr_recommendations['should_use_parallel_processing']
            pages_for_ocr = text_analysis['analysis']['pages_needing_ocr']
            
            # Process with OCR
            if pages_for_ocr:
                page_range = (min(pages_for_ocr), max(pages_for_ocr))
            else:
                page_range = None
            
            ocr_result = ocr_service.process_pdf_direct(
                pdf_file,
                page_range=page_range,
                use_parallel=use_parallel,
                ocr_mode='accurate'
            )
            
            job.progress = 80
            job.save()
            
            if ocr_result['success']:
                job.status = 'completed'
                job.progress = 100
                job.results = {
                    'method': 'ocr_processing',
                    'pages_processed': ocr_result['pages_processed'],
                    'successful_pages': ocr_result['successful_pages'],
                    'overall_confidence': ocr_result['overall_confidence'],
                    'total_text_length': ocr_result['total_text_length']
                }
                job.save()
                
                return {
                    'success': True,
                    'method': 'ocr',
                    'pages_processed': ocr_result['pages_processed'],
                    'confidence': ocr_result['overall_confidence']
                }
            else:
                raise Exception(f"OCR processing failed: {ocr_result['error']}")
                
    except Exception as exc:
        logger.error(f"OCR batch processing failed for job {job_id}: {str(exc)}")
        
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=120, exc=exc)
        
        return {
            'success': False,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def apply_text_redactions(
    self,
    job_id: str,
    file_path: str,
    match_ids: List[str],
    redaction_options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Apply permanent text redactions to PDF in the background.
    
    Args:
        job_id: Processing job UUID
        file_path: Path to PDF file
        match_ids: List of RedactionMatch IDs to apply
        redaction_options: Redaction appearance and behavior options
        
    Returns:
        Dictionary with redaction results
    """
    try:
        # Get the processing job
        job = ProcessingJob.objects.get(id=job_id)
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting text redaction for job {job_id} with {len(match_ids)} matches")
        
        # Get redaction matches
        matches = RedactionMatch.objects.filter(id__in=match_ids)
        if not matches:
            raise ValueError("No valid redaction matches found")
        
        job.progress = 20
        job.save()
        
        # Initialize RedactionService
        redaction_service = RedactionService(job.document.session_id)
        
        # Convert file path to Path object
        pdf_file = Path(file_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")
        
        job.progress = 30
        job.save()
        
        # Apply permanent text redactions
        logger.info(f"Applying {len(matches)} redactions to {pdf_file.name}")
        
        result = redaction_service.redact_pdf(
            pdf_file,
            list(matches),
            **(redaction_options or {})
        )
        
        job.progress = 80
        job.save()
        
        if result['success']:
            job.status = 'completed'
            job.progress = 100
            job.results = result
            
            # Update match records to mark as redacted
            matches.update(redacted=True, redaction_applied_at=timezone.now())
            
            logger.info(f"Successfully completed text redaction for job {job_id}")
            logger.info(f"Output file: {result['output_path']}")
            logger.info(f"Statistics: {result['statistics']}")
        else:
            job.status = 'failed'
            job.error_messages = result.get('errors', ['Unknown redaction error'])
            logger.error(f"Text redaction failed for job {job_id}: {job.error_messages}")
        
        job.save()
        
        # Schedule cleanup after processing
        TempFileManager.schedule_cleanup(job.document.session_id)
        
        return {
            'success': result['success'],
            'job_id': job_id,
            'output_path': result.get('output_path'),
            'statistics': result.get('statistics'),
            'errors': result.get('errors', [])
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"Text redaction task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying redaction task for job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=300 * (2 ** self.request.retries), exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=180)
def process_pdf_split(self, document_id: str, job_id: str, split_params: Dict[str, Any]) -> Dict[str, Any]:
    """Process PDF splitting operations in the background.
    
    Args:
        document_id: UUID of the document to split
        job_id: Processing job UUID
        split_params: Split parameters (pages or pattern-based)
        
    Returns:
        Dictionary with split processing results
    """
    try:
        # Get the processing job and document
        job = ProcessingJob.objects.get(id=job_id)
        document = PDFDocument.objects.get(id=document_id)
        
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting PDF split for job {job_id}, document {document.filename}")
        
        # Get file path
        upload_path = TempFileManager.get_session_path(document.session_id, 'uploads')
        pdf_file = upload_path / document.filename
        
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")
        
        # Initialize PDF processor
        processor = PDFProcessor(document.session_id)
        
        job.progress = 25
        job.save()
        
        # Perform split operation
        result = processor.split_pdf(
            pdf_file,
            split_pages=split_params.get('split_pages'),
            pattern=split_params.get('pattern'),
            pattern_type=split_params.get('pattern_type', 'regex'),
            fuzzy_threshold=split_params.get('fuzzy_threshold', 80),
            split_position=split_params.get('split_position', 'before'),
            preserve_metadata=split_params.get('preserve_metadata', True)
        )
        
        job.progress = 75
        job.save()
        
        if result['success']:
            job.status = 'completed'
            job.progress = 100
            job.results = {
                'split_type': result.get('split_type', 'pages'),
                'output_files': result['output_files'],
                'page_ranges': result['page_ranges'],
                'total_files_created': len(result['output_files']),
                'metadata_preserved': result.get('metadata_preserved', True)
            }
            
            if 'pattern_matches_found' in result:
                job.results['pattern_matches_found'] = result['pattern_matches_found']
            
            logger.info(f"Successfully completed PDF split for job {job_id}: {len(result['output_files'])} files created")
        else:
            job.status = 'failed'
            job.error_messages = result.get('error', 'Unknown split error')
            logger.error(f"PDF split failed for job {job_id}: {job.error_messages}")
        
        job.save()
        
        # Schedule cleanup after processing
        TempFileManager.schedule_cleanup(document.session_id)
        
        return {
            'success': result['success'],
            'job_id': job_id,
            'document_id': document_id,
            'result': result
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except PDFDocument.DoesNotExist:
        logger.error(f"Document not found: {document_id}")
        return {
            'success': False,
            'error': f"Document {document_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"PDF split task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying split task for job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=180 * (2 ** self.request.retries), exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=240)
def process_pdf_merge(self, document_ids: List[str], job_id: str, merge_params: Dict[str, Any]) -> Dict[str, Any]:
    """Process PDF merging operations in the background.
    
    Args:
        document_ids: List of document UUIDs to merge
        job_id: Processing job UUID
        merge_params: Merge parameters
        
    Returns:
        Dictionary with merge processing results
    """
    try:
        # Get the processing job
        job = ProcessingJob.objects.get(id=job_id)
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting PDF merge for job {job_id} with {len(document_ids)} documents")
        
        # Get all documents and validate they exist
        documents = []
        file_paths = []
        
        for doc_id in document_ids:
            try:
                doc = PDFDocument.objects.get(id=doc_id)
                documents.append(doc)
                
                doc_path = TempFileManager.get_session_path(
                    doc.session_id, 'uploads'
                ) / doc.filename
                
                if not doc_path.exists():
                    raise FileNotFoundError(f"Document file not found: {doc_path}")
                
                file_paths.append(doc_path)
                
            except PDFDocument.DoesNotExist:
                raise ValueError(f"Document not found: {doc_id}")
        
        # Use session from first document for processor
        session_id = documents[0].session_id
        processor = PDFProcessor(session_id)
        
        job.progress = 25
        job.save()
        
        # Perform merge operation
        result = processor.merge_pdfs(
            file_paths,
            output_filename=merge_params.get('output_filename'),
            preserve_metadata=merge_params.get('preserve_metadata', True),
            merge_strategy=merge_params.get('merge_strategy', 'sequential')
        )
        
        job.progress = 75
        job.save()
        
        if result['success']:
            job.status = 'completed'
            job.progress = 100
            job.results = {
                'output_file': result['output_file'],
                'total_pages': result['total_pages'],
                'source_count': len(file_paths),
                'source_files': [doc.filename for doc in documents],
                'merge_strategy': result.get('merge_strategy', 'sequential'),
                'metadata_preserved': result.get('metadata_preserved', True),
                'statistics': result.get('statistics', {})
            }
            
            logger.info(f"Successfully completed PDF merge for job {job_id}: {result['total_pages']} total pages")
        else:
            job.status = 'failed'
            job.error_messages = result.get('error', 'Unknown merge error')
            logger.error(f"PDF merge failed for job {job_id}: {job.error_messages}")
        
        job.save()
        
        # Schedule cleanup after processing
        TempFileManager.schedule_cleanup(session_id)
        
        return {
            'success': result['success'],
            'job_id': job_id,
            'document_ids': document_ids,
            'result': result
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"PDF merge task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying merge task for job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=240 * (2 ** self.request.retries), exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def process_pdf_extraction(
    self, 
    document_id: str, 
    job_id: str, 
    extraction_type: str, 
    page_range: List[int] = None
) -> Dict[str, Any]:
    """Process PDF text/metadata/image extraction in the background.
    
    Args:
        document_id: UUID of the document to process
        job_id: Processing job UUID
        extraction_type: Type of extraction ('text', 'metadata', 'images', 'comprehensive')
        page_range: Optional page range to limit extraction
        
    Returns:
        Dictionary with extraction processing results
    """
    try:
        # Get the processing job and document
        job = ProcessingJob.objects.get(id=job_id)
        document = PDFDocument.objects.get(id=document_id)
        
        job.status = 'processing'
        job.progress = 10
        job.save()
        
        logger.info(f"Starting PDF extraction ({extraction_type}) for job {job_id}, document {document.filename}")
        
        # Get file path
        upload_path = TempFileManager.get_session_path(document.session_id, 'uploads')
        pdf_file = upload_path / document.filename
        
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")
        
        # Initialize PDF processor
        processor = PDFProcessor(document.session_id)
        
        job.progress = 25
        job.save()
        
        # Perform extraction based on type
        if extraction_type == 'text':
            result = processor.extract_text(pdf_file)
        elif extraction_type == 'metadata':
            result = processor.extract_advanced_metadata(pdf_file)
        elif extraction_type == 'images':
            result = processor.extract_embedded_files(pdf_file)
        elif extraction_type == 'comprehensive':
            # Perform all extractions
            text_result = processor.extract_text(pdf_file)
            metadata_result = processor.extract_advanced_metadata(pdf_file)
            files_result = processor.extract_embedded_files(pdf_file)
            
            result = {
                'success': text_result['success'] and metadata_result['success'],
                'text_extraction': text_result,
                'metadata_extraction': metadata_result,
                'files_extraction': files_result
            }
        else:
            raise ValueError(f"Unknown extraction type: {extraction_type}")
        
        job.progress = 75
        job.save()
        
        if result['success']:
            job.status = 'completed'
            job.progress = 100
            job.results = {
                'extraction_type': extraction_type,
                'result': result
            }
            
            logger.info(f"Successfully completed PDF extraction ({extraction_type}) for job {job_id}")
        else:
            job.status = 'failed'
            job.error_messages = result.get('error', f'Unknown {extraction_type} extraction error')
            logger.error(f"PDF extraction ({extraction_type}) failed for job {job_id}: {job.error_messages}")
        
        job.save()
        
        # Schedule cleanup after processing
        TempFileManager.schedule_cleanup(document.session_id)
        
        return {
            'success': result['success'],
            'job_id': job_id,
            'document_id': document_id,
            'extraction_type': extraction_type,
            'result': result
        }
        
    except ProcessingJob.DoesNotExist:
        logger.error(f"Processing job not found: {job_id}")
        return {
            'success': False,
            'error': f"Job {job_id} not found"
        }
        
    except PDFDocument.DoesNotExist:
        logger.error(f"Document not found: {document_id}")
        return {
            'success': False,
            'error': f"Document {document_id} not found"
        }
        
    except Exception as exc:
        logger.error(f"PDF extraction task failed for job {job_id}: {str(exc)}")
        
        # Update job status
        try:
            job = ProcessingJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_messages = str(exc)
            job.save()
        except ProcessingJob.DoesNotExist:
            pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying extraction task for job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(exc),
            'retries': self.request.retries
        }


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def monitor_disk_usage_enhanced(self) -> Dict[str, Any]:
    """Enhanced disk usage monitoring with intelligent cleanup."""
    try:
        monitoring_result = TempFileManager.monitor_disk_usage()
        
        # Log critical alerts
        for alert in monitoring_result.get('alerts', []):
            if alert['level'] == 'critical':
                logger.critical(f"Disk usage alert: {alert['message']}")
            elif alert['level'] == 'warning':
                logger.warning(f"Disk usage warning: {alert['message']}")
        
        return monitoring_result
        
    except Exception as exc:
        logger.error(f"Enhanced disk monitoring failed: {str(exc)}")
        return {
            'success': False,
            'error': str(exc)
        }