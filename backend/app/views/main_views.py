"""Django views for Ultimate PDF application."""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils.text import get_valid_filename
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from datetime import timedelta
from pathlib import Path
import logging
import os

from ..models import PDFDocument, ProcessingJob
from ..utils.validators import validate_pdf_file, validate_session_id, validate_split_pattern, validate_merge_parameters
from ..utils.errors import APIError, ERROR_MAPPINGS, ValidationError
from ..utils.response_formatters import APIResponseFormatter
from ..utils.api_decorators import (
    log_api_call, timeout_handler, rate_limit, require_session_id, 
    validate_request_data, handle_file_upload, monitor_performance, require_content_type
)
from ..services.temp_file_manager import TempFileManager
from ..services.pdf_processor import PDFProcessor
from ..services.ocr_service import OCRService
from ..services.unified_search_service import UnifiedSearchService
from ..services.redaction_service import RedactionService
from ..services.bounding_box_calculator import BoundingBoxCalculator
from ..models import RedactionMatch
from ..utils.extraction_utils import validate_extraction_parameters

logger = logging.getLogger(__name__)


class FileUploadView(APIView):
    """Handle PDF file uploads with validation and comprehensive processing."""
    
    def _estimate_processing_time(self, file_size: int, page_count: int) -> dict:
        """Estimate OCR processing time based on file size and page count.
        
        Args:
            file_size: File size in bytes
            page_count: Number of pages in the PDF
            
        Returns:
            Dictionary with time estimates in seconds
        """
        # Base processing time per page (seconds)
        base_time_per_page = 15
        
        # Size factor (larger files take longer)
        size_factor = min(file_size / (10 * 1024 * 1024), 2.0)  # Max 2x multiplier for 10MB+
        
        estimated_seconds = int(page_count * base_time_per_page * (1 + size_factor))
        
        return {
            'estimated_seconds': estimated_seconds,
            'estimated_minutes': round(estimated_seconds / 60, 1),
            'page_count': page_count,
            'size_mb': round(file_size / (1024 * 1024), 2)
        }
    
    @require_session_id
    def post(self, request):
        """Upload and validate PDF file."""
        try:
            if 'file' not in request.FILES:
                raise APIError("No file provided", "MISSING_FILE", status.HTTP_400_BAD_REQUEST)
            
            uploaded_file = request.FILES['file']
            # Use session ID from decorator validation or generate new one
            session_id = getattr(request, 'validated_session_id', None) or request.data.get('session_id') or TempFileManager.generate_session_id()
            
            # Session ID is already validated by decorator if present
            if not hasattr(request, 'validated_session_id'):
                validate_session_id(session_id)
            
            # Validate file
            validate_pdf_file(uploaded_file)
            
            # Create upload directory and initialize storage
            upload_path = TempFileManager.get_session_path(session_id, 'uploads')
            upload_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize FileSystemStorage rooted at upload path
            storage = FileSystemStorage(location=str(upload_path))
            
            # Save file using Django Storage API
            sanitized_filename = get_valid_filename(Path(uploaded_file.name).name)
            uploaded_file.seek(0)  # Rewind file pointer after validation
            saved_filename = storage.save(sanitized_filename, uploaded_file)
            file_path = upload_path / saved_filename
            
            # Initialize PDF processor for comprehensive analysis
            pdf_processor = PDFProcessor(session_id)
            
            # Validate and analyze PDF structure
            pdf_validation = pdf_processor.validate_pdf(file_path)
            if not pdf_validation['is_valid']:
                raise APIError(
                    f"PDF validation failed: {pdf_validation['error']}", 
                    "INVALID_PDF", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate file hash for integrity verification
            file_hash = TempFileManager.calculate_file_hash(file_path)
            
            # Check if PDF requires OCR processing
            needs_ocr = not pdf_validation.get('has_text_layer', False)
            
            # Create database record with comprehensive metadata
            document = PDFDocument.objects.create(
                filename=sanitized_filename,
                file_size=uploaded_file.size,
                session_id=session_id,
                content_hash=file_hash,
                file_hash=file_hash,
                processing_metadata={
                    'validation_result': pdf_validation,
                    'needs_ocr': needs_ocr,
                    'upload_timestamp': timezone.now().isoformat(),
                    'file_hash': file_hash
                }
            )
            
            # Schedule background OCR processing if needed
            processing_job = None
            if needs_ocr:
                try:
                    from tasks import process_ocr_batch
                    processing_job = ProcessingJob.objects.create(
                        document=document,
                        job_type='ocr',
                        status='queued'
                    )
                    process_ocr_batch.delay(str(document.id), str(processing_job.id))
                except ImportError:
                    logger.warning("Celery not available, OCR processing will be skipped")
            
            # Schedule automatic cleanup
            TempFileManager.schedule_cleanup(session_id)
            
            # Prepare comprehensive response
            response_data = {
                'success': True,
                'document_id': str(document.id),
                'session_id': session_id,
                'filename': sanitized_filename,
                'size': uploaded_file.size,
                'file_hash': file_hash,
                'pdf_metadata': {
                    'page_count': pdf_validation.get('page_count', 0),
                    'has_text_layer': pdf_validation.get('has_text_layer', False),
                    'is_encrypted': pdf_validation.get('is_encrypted', False),
                    'metadata': pdf_validation.get('metadata', {})
                },
                'processing_status': {
                    'needs_ocr': needs_ocr,
                    'ocr_job_id': str(processing_job.id) if processing_job else None,
                    'estimated_processing_time': self._estimate_processing_time(uploaded_file.size, pdf_validation.get('page_count', 1)) if needs_ocr else None
                },
                'cleanup_scheduled': True
            }
            
            return Response(response_data)
            
        except APIError as e:
            return Response(e.to_dict(), status=e.status)
        except ValidationError as e:
            return Response(
                {'error': str(e), 'field': getattr(e, 'field', None)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"File upload error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['UPLOAD_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RedactionAPIView(APIView):
    """Handle PDF redaction requests with permanent text deletion."""
    
    def _estimate_redaction_time(self, file_size: int, match_count: int) -> dict:
        """Estimate redaction processing time.
        
        Args:
            file_size: File size in bytes
            match_count: Number of matches to redact
            
        Returns:
            Dictionary with time estimates
        """
        # Base time factors
        base_time = 10  # seconds
        size_factor = file_size / (1024 * 1024)  # MB
        match_factor = match_count * 0.5  # 0.5 seconds per match
        
        estimated_seconds = int(base_time + size_factor + match_factor)
        
        return {
            'estimated_seconds': estimated_seconds,
            'estimated_minutes': round(estimated_seconds / 60, 1),
            'requires_background': estimated_seconds > 30
        }
    
    @log_api_call()
    @require_session_id
    @require_content_type('application/json')
    @timeout_handler(sync_timeout=30, background_threshold=25)
    @rate_limit(requests_per_minute=60)
    @validate_request_data(required_fields=['document_id', 'search_terms'])
    @monitor_performance
    def post(self, request):
        """Start PDF redaction process with search and permanent text deletion."""
        try:
            document_id = request.data.get('document_id')
            search_terms = request.data.get('search_terms', [])
            fuzzy_threshold = request.data.get('fuzzy_threshold', 80)
            confidence_threshold = request.data.get('confidence_threshold', 95)
            redaction_options = request.data.get('redaction_options', {})
            
            if not document_id or not search_terms:
                raise APIError(
                    "Document ID and search terms are required", 
                    "MISSING_PARAMETERS", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            document = PDFDocument.objects.get(id=document_id)
            file_path = TempFileManager.get_session_path(document.session_id, 'uploads') / document.filename
            
            if not file_path.exists():
                raise APIError(
                    "Document file not found",
                    "FILE_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND
                )
            
            # Use UnifiedSearchService to find matches
            search_service = UnifiedSearchService(document.session_id)
            search_results = search_service.search_document(
                str(file_path),
                search_terms,
                fuzzy_threshold=fuzzy_threshold
            )
            
            # Filter matches by confidence for automatic approval
            high_confidence_matches = []
            low_confidence_matches = []
            
            for match in search_results.get('matches', []):
                if match.confidence_score >= confidence_threshold:
                    high_confidence_matches.append(match)
                else:
                    low_confidence_matches.append(match)
            
            # If there are low confidence matches, return them for approval
            if low_confidence_matches and not request.data.get('approve_all', False):
                request_id = getattr(request, 'api_request_id', '')
                approval_data = {
                    'requires_approval': True,
                    'high_confidence_matches': len(high_confidence_matches),
                    'low_confidence_matches': [
                        {
                            'id': str(m.id),
                            'matched_text': m.matched_text,
                            'page_number': m.page_number,
                            'confidence_score': m.confidence_score,
                            'search_term': m.search_term
                        } for m in low_confidence_matches
                    ]
                }
                
                response_data = APIResponseFormatter.format_success_response(
                    approval_data,
                    message=f'Found {len(low_confidence_matches)} matches below {confidence_threshold}% confidence requiring approval',
                    request_id=request_id
                )
                return APIResponseFormatter.create_json_response(response_data)
            
            # All matches approved or high confidence - proceed with redaction
            all_matches = high_confidence_matches + low_confidence_matches
            
            # Create processing job
            job = ProcessingJob.objects.create(
                document=document,
                job_type='redact',
                processing_parameters={
                    'search_terms': search_terms,
                    'match_count': len(all_matches),
                    'confidence_threshold': confidence_threshold,
                    'redaction_options': redaction_options
                }
            )
            
            # Check if background processing is needed
            estimated_time = self._estimate_redaction_time(document.file_size, len(all_matches))
            
            # Check for timeout hint from middleware or size-based decision
            should_queue = getattr(request, 'timeout_hint', False) or estimated_time['requires_background']
            
            # Queue background task for processing (consistent with other views)
            if should_queue:
                try:
                    from tasks import apply_text_redactions
                    apply_text_redactions.delay(
                        str(job.id),
                        str(file_path),
                        [m.id for m in all_matches],
                        redaction_options
                    )
                    job.status = 'queued'
                    job.save()
                except ImportError:
                    logger.warning("Celery not available, processing will be synchronous")
                    job.status = 'pending'
                    job.save()
                    should_queue = False  # Reset since we can't queue
            else:
                job.status = 'pending'
                job.save()
            
            request_id = getattr(request, 'api_request_id', '')
            redaction_data = {
                'job_id': str(job.id),
                'status': job.status,
                'redaction_info': {
                    'total_matches': len(all_matches),
                    'high_confidence_matches': len(high_confidence_matches),
                    'pages_affected': len(set(m.page_number for m in all_matches)),
                    'estimated_processing_time': estimated_time,
                    'redaction_options': redaction_options
                }
            }
            
            response_data = APIResponseFormatter.format_success_response(
                redaction_data,
                message='Redaction job queued for processing',
                request_id=request_id
            )
            
            # Return 202 for queued background jobs, 200 for pending jobs
            status_code = 202 if job.status == 'queued' else 200
            return APIResponseFormatter.create_json_response(response_data, status_code=status_code)
            
        except PDFDocument.DoesNotExist:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_404_NOT_FOUND)
        except APIError as e:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(e, request_id)
            return APIResponseFormatter.create_json_response(error_response, e.status)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Redaction error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['PROCESSING_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)
    


class RedactionApprovalView(APIView):
    """Handle approval of low-confidence redaction matches."""
    
    def post(self, request):
        """Approve or reject low-confidence matches and continue redaction."""
        try:
            document_id = request.data.get('document_id')
            approved_match_ids = request.data.get('approved_match_ids', [])
            rejected_match_ids = request.data.get('rejected_match_ids', [])
            redaction_options = request.data.get('redaction_options', {})
            
            if not document_id:
                raise APIError(
                    "Document ID is required",
                    "MISSING_PARAMETERS",
                    status.HTTP_400_BAD_REQUEST
                )
            
            document = PDFDocument.objects.get(id=document_id)
            file_path = TempFileManager.get_session_path(document.session_id, 'uploads') / document.filename
            
            # Get approved matches
            approved_matches = RedactionMatch.objects.filter(
                id__in=approved_match_ids,
                document=document
            )
            
            if not approved_matches:
                raise APIError(
                    "No matches approved for redaction",
                    "NO_MATCHES",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Create processing job
            job = ProcessingJob.objects.create(
                document=document,
                job_type='redact',
                processing_parameters={
                    'approved_count': len(approved_match_ids),
                    'rejected_count': len(rejected_match_ids),
                    'redaction_options': redaction_options
                }
            )
            
            # Initialize RedactionService
            redaction_service = RedactionService(document.session_id)
            
            # Apply permanent text redactions
            result = redaction_service.redact_pdf(
                file_path,
                list(approved_matches),
                **redaction_options
            )
            
            if result['success']:
                job.status = 'completed'
                job.results = result
                job.progress = 100
            else:
                job.status = 'failed'
                job.error_messages = result.get('errors', ['Unknown error'])
            
            job.save()
            
            request_id = getattr(request, 'api_request_id', '')
            approval_data = {
                'job_id': str(job.id),
                'status': job.status,
                'output_path': result.get('output_path'),
                'statistics': result.get('statistics')
            }
            
            response_data = APIResponseFormatter.format_success_response(
                approval_data,
                message='Redaction completed with permanent text deletion',
                request_id=request_id
            )
            
            return APIResponseFormatter.create_json_response(response_data)
            
        except PDFDocument.DoesNotExist:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_404_NOT_FOUND)
        except APIError as e:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(e, request_id)
            return APIResponseFormatter.create_json_response(error_response, e.status)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Redaction approval error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['PROCESSING_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)


class RedactionPreviewView(APIView):
    """Generate redaction preview without permanent deletion."""
    
    def post(self, request):
        """Generate preview of redaction areas."""
        try:
            document_id = request.data.get('document_id')
            match_ids = request.data.get('match_ids', [])
            
            if not document_id:
                raise APIError(
                    "Document ID is required",
                    "MISSING_PARAMETERS",
                    status.HTTP_400_BAD_REQUEST
                )
            
            document = PDFDocument.objects.get(id=document_id)
            
            # Get matches
            matches = RedactionMatch.objects.filter(
                id__in=match_ids,
                document=document
            )
            
            # Initialize BoundingBoxCalculator for coordinate validation
            bbox_calculator = BoundingBoxCalculator()
            
            # Prepare preview data
            preview_data = []
            for match in matches:
                # Ensure coordinates exist
                if all([
                    match.x_coordinate is not None,
                    match.y_coordinate is not None,
                    match.width is not None,
                    match.height is not None
                ]):
                    preview_data.append({
                        'page_number': match.page_number,
                        'x': match.x_coordinate,
                        'y': match.y_coordinate,
                        'width': match.width,
                        'height': match.height,
                        'text': match.matched_text,
                        'confidence': match.confidence_score
                    })
            
            return Response({
                'success': True,
                'preview_data': preview_data,
                'total_redactions': len(preview_data),
                'pages_affected': len(set(m['page_number'] for m in preview_data))
            })
            
        except PDFDocument.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Preview generation error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['PROCESSING_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SplitAPIView(APIView):
    """Handle PDF splitting requests with pattern-based and page-based splitting."""
    
    def _estimate_processing_time(self, file_size: int, page_count: int, split_type: str) -> dict:
        """Estimate processing time for split operations."""
        base_time = 5  # seconds
        size_factor = file_size / (1024 * 1024)  # MB
        page_factor = page_count * 0.5  # 0.5 seconds per page
        
        if split_type == 'pattern':
            # Pattern-based splitting requires text extraction
            pattern_overhead = page_count * 2  # Extra time for pattern detection
            estimated_seconds = int(base_time + size_factor + page_factor + pattern_overhead)
        else:
            estimated_seconds = int(base_time + size_factor + page_factor)
        
        return {
            'estimated_seconds': estimated_seconds,
            'estimated_minutes': round(estimated_seconds / 60, 1)
        }
    
    @log_api_call()
    @require_session_id
    @require_content_type('application/json')
    @timeout_handler(sync_timeout=30, background_threshold=25) 
    @rate_limit(requests_per_minute=60)
    @validate_request_data(required_fields=['document_id'])
    @monitor_performance
    def post(self, request):
        """Start PDF splitting process with pattern-based or page-based splitting."""
        try:
            document_id = request.data.get('document_id')
            split_strategy = request.data.get('split_strategy', 'pages')
            
            # Pattern-based splitting parameters
            pattern = request.data.get('pattern')
            pattern_type = request.data.get('pattern_type', 'regex')
            fuzzy_threshold = request.data.get('fuzzy_threshold', 80)
            split_position = request.data.get('split_position', 'before')
            
            # Page-based splitting parameters
            split_pages = request.data.get('split_pages', [])
            
            # Common parameters
            preserve_metadata = request.data.get('preserve_metadata', True)
            
            if not document_id:
                raise APIError(
                    "Document ID is required", 
                    "MISSING_PARAMETERS", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Validate split strategy
            if split_strategy not in ['pages', 'pattern']:
                raise APIError(
                    "Split strategy must be 'pages' or 'pattern'",
                    "INVALID_SPLIT_STRATEGY",
                    status.HTTP_400_BAD_REQUEST
                )
            
            document = PDFDocument.objects.get(id=document_id)
            
            # Initialize PDF processor and validate document
            pdf_processor = PDFProcessor(document.session_id)
            file_path = TempFileManager.get_session_path(document.session_id, 'uploads') / document.filename
            
            if not file_path.exists():
                raise APIError(
                    "Document file not found",
                    "FILE_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND
                )
            
            # Get PDF info for validation
            pdf_info = pdf_processor.validate_pdf(file_path)
            if not pdf_info['is_valid']:
                raise APIError(
                    f"PDF processing error: {pdf_info['error']}",
                    "PDF_ERROR",
                    status.HTTP_400_BAD_REQUEST
                )
            
            max_page = pdf_info.get('page_count', 1)
            
            # Validate parameters based on split strategy
            if split_strategy == 'pattern':
                if not pattern:
                    raise APIError(
                        "Pattern is required for pattern-based splitting",
                        "MISSING_PATTERN",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                # Validate pattern
                pattern_validation = validate_split_pattern(pattern, pattern_type)
                if not pattern_validation['valid']:
                    raise APIError(
                        f"Invalid pattern: {pattern_validation['error']}",
                        "INVALID_PATTERN",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                # Validate fuzzy threshold
                if not (1 <= fuzzy_threshold <= 100):
                    raise APIError(
                        "Fuzzy threshold must be between 1 and 100",
                        "INVALID_FUZZY_THRESHOLD",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                # Validate split position
                if split_position not in ['before', 'after']:
                    raise APIError(
                        "Split position must be 'before' or 'after'",
                        "INVALID_SPLIT_POSITION",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                # Test pattern against document
                pattern_test = pdf_processor.validate_split_pattern(file_path, pattern, pattern_type)
                if not pattern_test['valid']:
                    raise APIError(
                        f"Pattern validation failed: {pattern_test['error']}",
                        "PATTERN_TEST_FAILED",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                estimated_output_files = pattern_test.get('test_matches', 1) + 1
                
            else:  # pages strategy
                if not split_pages:
                    raise APIError(
                        "Split pages are required for page-based splitting",
                        "MISSING_SPLIT_PAGES",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                # Validate split pages
                if not all(isinstance(p, int) and p > 0 for p in split_pages):
                    raise APIError(
                        "Split pages must be positive integers",
                        "INVALID_SPLIT_PAGES",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                # Validate split points against page count
                if max(split_pages) > max_page:
                    raise APIError(
                        f"Split page {max(split_pages)} exceeds document page count ({max_page})",
                        "INVALID_PAGE_NUMBER",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                estimated_output_files = len(split_pages) + 1
            
            # Create processing job with comprehensive parameters
            split_params = {
                'split_strategy': split_strategy,
                'preserve_metadata': preserve_metadata,
                'document_path': str(file_path),
                'total_pages': max_page
            }
            
            if split_strategy == 'pattern':
                split_params.update({
                    'pattern': pattern,
                    'pattern_type': pattern_type,
                    'fuzzy_threshold': fuzzy_threshold,
                    'split_position': split_position
                })
            else:
                split_params['split_pages'] = split_pages
            
            job = ProcessingJob.objects.create(
                document=document,
                job_type='split',
                processing_parameters=split_params
            )
            
            # Check for timeout hint from middleware
            should_queue = getattr(request, 'timeout_hint', False) or True  # Default to queuing for splits
            
            # Queue background task for processing
            if should_queue:
                try:
                    from tasks import process_pdf_split
                    process_pdf_split.delay(str(document.id), str(job.id), split_params)
                    job.status = 'queued'
                    job.save()
                except ImportError:
                    logger.warning("Celery not available, processing will be synchronous")
                    job.status = 'pending'
                    job.save()
                    should_queue = False  # Reset since we can't queue
            else:
                job.status = 'pending'
                job.save()
            
            # Calculate processing time estimate
            processing_estimate = self._estimate_processing_time(
                document.file_size, max_page, split_strategy
            )
            
            request_id = getattr(request, 'api_request_id', '')
            split_data = {
                'job_id': str(job.id),
                'status': job.status,
                'split_info': {
                    'strategy': split_strategy,
                    'total_pages': max_page,
                    'estimated_output_files': estimated_output_files,
                    'preserve_metadata': preserve_metadata,
                    'processing_estimate': processing_estimate
                }
            }
            
            # Add strategy-specific info to response
            if split_strategy == 'pattern':
                split_data['split_info']['pattern_info'] = {
                    'pattern': pattern,
                    'pattern_type': pattern_type,
                    'fuzzy_threshold': fuzzy_threshold,
                    'split_position': split_position,
                    'test_matches_found': pattern_test.get('test_matches', 0)
                }
            else:
                split_data['split_info']['split_pages'] = split_pages
            
            response_data = APIResponseFormatter.format_success_response(
                split_data,
                message=f'{split_strategy.title()}-based split job queued for processing',
                request_id=request_id
            )
            
            # Return 202 for queued background jobs, 200 for pending jobs
            status_code = 202 if job.status == 'queued' else 200
            return APIResponseFormatter.create_json_response(response_data, status_code=status_code)
            
        except PDFDocument.DoesNotExist:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_404_NOT_FOUND)
        except APIError as e:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(e, request_id)
            return APIResponseFormatter.create_json_response(error_response, e.status)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Split error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['PROCESSING_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)


class MergeAPIView(APIView):
    """Handle PDF merging requests with enhanced metadata preservation and validation."""
    
    def _estimate_processing_time(self, total_size: int, total_pages: int, document_count: int) -> dict:
        """Estimate processing time for merge operations."""
        base_time = 5  # seconds
        size_factor = total_size / (1024 * 1024)  # MB
        page_factor = total_pages * 0.3  # 0.3 seconds per page
        document_factor = document_count * 2  # 2 seconds per document
        
        estimated_seconds = int(base_time + size_factor + page_factor + document_factor)
        
        return {
            'estimated_seconds': estimated_seconds,
            'estimated_minutes': round(estimated_seconds / 60, 1)
        }
    
    @log_api_call()
    @require_session_id
    @require_content_type('application/json')
    @timeout_handler(sync_timeout=30, background_threshold=25)
    @rate_limit(requests_per_minute=60)
    @validate_request_data(required_fields=['document_ids'])
    @monitor_performance
    def post(self, request):
        """Start PDF merging process with enhanced parameters."""
        try:
            document_ids = request.data.get('document_ids', [])
            output_filename = request.data.get('output_filename', None)
            preserve_metadata = request.data.get('preserve_metadata', True)
            merge_strategy = request.data.get('merge_strategy', 'sequential')
            custom_order = request.data.get('custom_order', None)
            
            if not document_ids or len(document_ids) < 2:
                raise APIError(
                    "At least two document IDs are required", 
                    "MISSING_PARAMETERS", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Validate merge parameters
            merge_validation = validate_merge_parameters(document_ids, merge_strategy, custom_order)
            if not merge_validation['valid']:
                raise APIError(
                    f"Invalid merge parameters: {merge_validation['error']}",
                    "INVALID_MERGE_PARAMETERS",
                    status.HTTP_400_BAD_REQUEST
                )
            
            documents = PDFDocument.objects.filter(id__in=document_ids)
            if documents.count() != len(document_ids):
                raise APIError(
                    "One or more documents not found", 
                    "DOCUMENT_NOT_FOUND", 
                    status.HTTP_404_NOT_FOUND
                )
            
            # Validate all documents exist as files and collect metadata
            document_info = []
            total_pages = 0
            total_size = 0
            
            for doc in documents:
                file_path = TempFileManager.get_session_path(doc.session_id, 'uploads') / doc.filename
                if not file_path.exists():
                    raise APIError(
                        f"Document file not found: {doc.filename}",
                        "FILE_NOT_FOUND",
                        status.HTTP_404_NOT_FOUND
                    )
                
                # Get PDF metadata
                pdf_processor = PDFProcessor(doc.session_id)
                pdf_info = pdf_processor.validate_pdf(file_path)
                
                if not pdf_info['is_valid']:
                    raise APIError(
                        f"Invalid PDF document: {doc.filename} - {pdf_info['error']}",
                        "INVALID_PDF",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                document_info.append({
                    'id': str(doc.id),
                    'filename': doc.filename,
                    'page_count': pdf_info.get('page_count', 0),
                    'file_size': doc.file_size,
                    'session_id': doc.session_id
                })
                
                total_pages += pdf_info.get('page_count', 0)
                total_size += doc.file_size
            
            # Use first document for job creation
            first_doc = documents.first()
            job = ProcessingJob.objects.create(
                document=first_doc,
                job_type='merge',
                processing_parameters={
                    'document_ids': document_ids,
                    'output_filename': output_filename,
                    'document_info': document_info,
                    'total_pages': total_pages,
                    'total_size': total_size
                }
            )
            
            # Validate total combined file size
            if total_size > 100 * 1024 * 1024:  # 100MB limit
                raise APIError(
                    f"Total file size ({round(total_size/(1024*1024), 2)}MB) exceeds 100MB limit",
                    "FILE_SIZE_LIMIT_EXCEEDED",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Create comprehensive merge parameters
            merge_params = {
                'document_ids': document_ids,
                'output_filename': output_filename,
                'preserve_metadata': preserve_metadata,
                'merge_strategy': merge_strategy,
                'custom_order': custom_order,
                'document_info': document_info,
                'total_pages': total_pages,
                'total_size': total_size
            }
            
            # Update job with enhanced parameters
            job.processing_parameters = merge_params
            job.save()
            
            # Check for timeout hint from middleware
            should_queue = getattr(request, 'timeout_hint', False) or True  # Default to queuing for merges
            
            # Queue background task for processing
            if should_queue:
                try:
                    from tasks import process_pdf_merge
                    process_pdf_merge.delay(document_ids, str(job.id), merge_params)
                    job.status = 'queued'
                    job.save()
                except ImportError:
                    logger.warning("Celery not available, processing will be synchronous")
                    job.status = 'pending'
                    job.save()
                    should_queue = False  # Reset since we can't queue
            else:
                job.status = 'pending'
                job.save()
            
            # Calculate processing time estimate
            processing_estimate = self._estimate_processing_time(total_size, total_pages, len(documents))
            
            request_id = getattr(request, 'api_request_id', '')
            merge_data = {
                'job_id': str(job.id),
                'status': job.status,
                'merge_info': {
                    'total_documents': len(documents),
                    'total_pages': total_pages,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'merge_strategy': merge_strategy,
                    'preserve_metadata': preserve_metadata,
                    'processing_estimate': processing_estimate,
                    'document_list': document_info,
                    'output_filename': output_filename,
                    'custom_order': custom_order if merge_strategy == 'custom' else None
                }
            }
            
            response_data = APIResponseFormatter.format_success_response(
                merge_data,
                message='Enhanced merge job queued for processing',
                request_id=request_id
            )
            
            # Return 202 for queued background jobs, 200 for pending jobs
            status_code = 202 if job.status == 'queued' else 200
            return APIResponseFormatter.create_json_response(response_data, status_code=status_code)
            
        except APIError as e:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(e, request_id)
            return APIResponseFormatter.create_json_response(error_response, e.status)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Merge error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['PROCESSING_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExtractAPIView(APIView):
    """Handle PDF data extraction requests with comprehensive processing."""
    
    @log_api_call()
    @require_session_id
    @require_content_type('application/json')
    @timeout_handler(sync_timeout=30, background_threshold=25)
    @rate_limit(requests_per_minute=60)
    @validate_request_data(required_fields=['document_id'])
    @monitor_performance
    def post(self, request):
        """Start PDF data extraction process."""
        try:
            document_id = request.data.get('document_id')
            extraction_type = request.data.get('extraction_type', 'text')
            page_range = request.data.get('page_range', None)  # [start, end] or None for all
            
            # Additional extraction parameters
            csv_delimiter = request.data.get('csv_delimiter', ',')
            image_format = request.data.get('image_format', 'PNG')
            image_quality = request.data.get('image_quality', 95)
            output_format = request.data.get('output_format', 'json')
            include_formatting = request.data.get('include_formatting', False)
            table_extraction_method = request.data.get('table_extraction_method', 'auto')
            include_headers = request.data.get('include_headers', None)
            dpi = request.data.get('dpi', 300)
            
            if not document_id:
                raise APIError(
                    "Document ID is required", 
                    "MISSING_PARAMETERS", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Validate extraction type
            valid_types = ['text', 'metadata', 'images', 'tables', 'all']
            if extraction_type not in valid_types:
                raise APIError(
                    f"Invalid extraction type. Must be one of: {', '.join(valid_types)}",
                    "INVALID_EXTRACTION_TYPE",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Use centralized parameter validation
            extraction_parameters = {
                'page_range': page_range,
                'csv_delimiter': csv_delimiter,
                'image_format': image_format,
                'image_quality': image_quality,
                'output_format': output_format,
                'include_formatting': include_formatting,
                'table_extraction_method': table_extraction_method,
                'include_headers': include_headers,
                'dpi': dpi
            }
            
            validation_result = validate_extraction_parameters(extraction_type, extraction_parameters)
            
            if not validation_result['valid']:
                error_messages = validation_result['errors']
                raise APIError(
                    f"Parameter validation failed: {'; '.join(error_messages)}",
                    "INVALID_EXTRACTION_PARAMETERS",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Use sanitized parameters from validation
            sanitized_params = validation_result['sanitized_parameters']
            csv_delimiter = sanitized_params.get('csv_delimiter', csv_delimiter)
            image_format = sanitized_params.get('image_format', image_format)
            image_quality = sanitized_params.get('image_quality', image_quality)
            output_format = sanitized_params.get('output_format', output_format)
            include_formatting = sanitized_params.get('include_formatting', include_formatting)
            table_extraction_method = sanitized_params.get('table_extraction_method', table_extraction_method)
            include_headers = sanitized_params.get('include_headers', include_headers)
            dpi = sanitized_params.get('dpi', dpi)
            
            document = PDFDocument.objects.get(id=document_id)
            
            # Validate document file exists
            file_path = TempFileManager.get_session_path(document.session_id, 'uploads') / document.filename
            if not file_path.exists():
                raise APIError(
                    "Document file not found",
                    "FILE_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND
                )
            
            # Initialize PDF processor and validate document
            pdf_processor = PDFProcessor(document.session_id)
            pdf_info = pdf_processor.validate_pdf(file_path)
            
            if not pdf_info['is_valid']:
                raise APIError(
                    f"PDF processing error: {pdf_info['error']}",
                    "PDF_ERROR",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Validate page range if provided
            max_pages = pdf_info.get('page_count', 1)
            if page_range:
                if not isinstance(page_range, list) or len(page_range) != 2:
                    raise APIError(
                        "Page range must be [start, end] format",
                        "INVALID_PAGE_RANGE",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                start_page, end_page = page_range
                if not all(isinstance(p, int) and 1 <= p <= max_pages for p in [start_page, end_page]):
                    raise APIError(
                        f"Page range [{start_page}, {end_page}] is invalid. Pages must be 1-{max_pages}",
                        "INVALID_PAGE_RANGE",
                        status.HTTP_400_BAD_REQUEST
                    )
                
                if start_page > end_page:
                    raise APIError(
                        "Start page must be less than or equal to end page",
                        "INVALID_PAGE_RANGE",
                        status.HTTP_400_BAD_REQUEST
                    )
            
            # Create processing job with enhanced parameters
            processing_parameters = {
                'extraction_type': extraction_type,
                'page_range': page_range,
                'document_path': str(file_path),
                'total_pages': max_pages,
                'has_text_layer': pdf_info.get('has_text_layer', False),
                'csv_delimiter': csv_delimiter,
                'image_format': image_format,
                'image_quality': image_quality,
                'output_format': output_format,
                'include_formatting': include_formatting,
                'table_extraction_method': table_extraction_method,
                'include_headers': include_headers,
                'dpi': dpi
            }
            
            job = ProcessingJob.objects.create(
                document=document,
                job_type='extract',
                processing_parameters=processing_parameters
            )
            
            # Check for timeout hint from middleware
            should_queue = getattr(request, 'timeout_hint', False) or True  # Default to queuing for extractions
            
            # Queue background task for processing
            if should_queue:
                try:
                    from tasks import process_pdf_extraction
                    # Pass extraction options as additional parameter
                    extraction_options = {
                        'csv_delimiter': csv_delimiter,
                        'image_format': image_format,
                        'image_quality': image_quality,
                        'output_format': output_format,
                        'include_formatting': include_formatting,
                        'table_extraction_method': table_extraction_method,
                        'include_headers': include_headers,
                        'dpi': dpi
                    }
                    process_pdf_extraction.delay(str(document.id), str(job.id), extraction_type, page_range, extraction_options)
                    job.status = 'queued'
                    job.save()
                except ImportError:
                    logger.warning("Celery not available, processing will be synchronous")
                    job.status = 'pending'
                    job.save()
                    should_queue = False  # Reset since we can't queue
            else:
                job.status = 'pending'
                job.save()
            
            # Add extraction capability assessment
            extraction_capabilities = self._assess_extraction_capabilities(
                pdf_info, extraction_type, max_pages
            )
            
            request_id = getattr(request, 'api_request_id', '')
            extraction_data = {
                'job_id': str(job.id),
                'status': job.status,
                'extraction_info': {
                    'extraction_type': extraction_type,
                    'page_range': page_range or f"1-{max_pages}",
                    'total_pages': max_pages,
                    'has_text_layer': pdf_info.get('has_text_layer', False),
                    'requires_ocr': not pdf_info.get('has_text_layer', False) and extraction_type in ['text', 'all'],
                    'extraction_parameters': {
                        'csv_delimiter': csv_delimiter if extraction_type in ['tables', 'all'] else None,
                        'image_format': image_format if extraction_type in ['images', 'all'] else None,
                        'image_quality': image_quality if extraction_type in ['images', 'all'] else None,
                        'output_format': output_format,
                        'include_formatting': include_formatting,
                        'table_extraction_method': table_extraction_method if extraction_type in ['tables', 'all'] else None,
                        'include_headers': include_headers if extraction_type in ['tables', 'all'] else None,
                        'dpi': dpi
                    },
                    'capabilities_assessment': extraction_capabilities
                }
            }
            
            response_data = APIResponseFormatter.format_success_response(
                extraction_data,
                message='Enhanced extraction job queued for processing',
                request_id=request_id
            )
            
            # Return 202 for queued background jobs, 200 for pending jobs
            status_code = 202 if job.status == 'queued' else 200
            return APIResponseFormatter.create_json_response(response_data, status_code=status_code)
            
        except PDFDocument.DoesNotExist:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_404_NOT_FOUND)
        except APIError as e:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(e, request_id)
            return APIResponseFormatter.create_json_response(error_response, e.status)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Extraction error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['PROCESSING_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _assess_extraction_capabilities(self, pdf_info: dict, extraction_type: str, page_count: int) -> dict:
        """Assess PDF's suitability for different extraction types.
        
        Args:
            pdf_info: PDF validation information
            extraction_type: Type of extraction requested
            page_count: Number of pages in PDF
            
        Returns:
            Dictionary with capability assessment
        """
        try:
            assessment = {
                'text_extraction': {
                    'feasible': True,
                    'confidence': 'high' if pdf_info.get('has_text_layer', False) else 'medium',
                    'method': 'text_layer' if pdf_info.get('has_text_layer', False) else 'ocr_required',
                    'estimated_quality': 'excellent' if pdf_info.get('has_text_layer', False) else 'good'
                },
                'table_extraction': {
                    'feasible': True,
                    'confidence': 'medium',
                    'method': 'auto_detection',
                    'estimated_tables': 'unknown',
                    'note': 'Will use intelligent method selection based on PDF structure'
                },
                'image_extraction': {
                    'feasible': True,
                    'confidence': 'high',
                    'method': 'embedded_extraction',
                    'estimated_images': 'unknown',
                    'note': 'Will extract embedded images and optionally render pages'
                },
                'metadata_extraction': {
                    'feasible': True,
                    'confidence': 'high',
                    'method': 'comprehensive_analysis',
                    'estimated_completeness': 'high'
                }
            }
            
            # Adjust assessments based on document characteristics
            if page_count > 100:
                assessment['text_extraction']['note'] = 'Large document - text layer extraction recommended for performance'
                assessment['table_extraction']['confidence'] = 'medium-high'
                assessment['table_extraction']['note'] += ' (optimized for large documents)'
            
            if page_count > 50:
                assessment['image_extraction']['note'] += ' (page rendering disabled for performance)'
            
            # Filter assessment based on extraction type
            if extraction_type == 'text':
                return {'text_extraction': assessment['text_extraction']}
            elif extraction_type == 'tables':
                return {'table_extraction': assessment['table_extraction']}
            elif extraction_type == 'images':
                return {'image_extraction': assessment['image_extraction']}
            elif extraction_type == 'metadata':
                return {'metadata_extraction': assessment['metadata_extraction']}
            else:  # 'all'
                return assessment
                
        except Exception as e:
            logger.warning(f"Error assessing extraction capabilities: {e}")
            return {
                'assessment_error': 'Could not assess extraction capabilities',
                'default_confidence': 'medium',
                'note': 'Extraction will proceed with default settings'
            }


class JobStatusView(APIView):
    """Check processing job status with comprehensive progress tracking."""
    
    @log_api_call()
    @rate_limit(requests_per_minute=120)
    @monitor_performance
    def get(self, request, job_id):
        """Get detailed job status, progress, and results."""
        try:
            job = ProcessingJob.objects.get(id=job_id)
            
            # Calculate estimated completion time for running jobs
            estimated_completion = None
            if job.status == 'processing' and job.progress > 0:
                elapsed_time = (timezone.now() - job.updated_at).total_seconds()
                if elapsed_time > 0:
                    estimated_total_time = elapsed_time / (job.progress / 100.0)
                    remaining_time = estimated_total_time - elapsed_time
                    estimated_completion = {
                        'remaining_seconds': max(0, int(remaining_time)),
                        'estimated_finish': (timezone.now() + timedelta(seconds=remaining_time)).isoformat()
                    }
            
            # Prepare job info for APIResponseFormatter
            job_info = {
                'job_id': str(job.id),
                'status': job.status,
                'progress': job.progress,
                'operation_type': job.job_type,
                'document_id': str(job.document.id),
                'document_filename': job.document.filename,
                'created_at': job.created_at.isoformat(),
                'updated_at': job.updated_at.isoformat(),
                'processing_parameters': getattr(job, 'processing_parameters', {}),
                'estimated_completion': estimated_completion,
                'result': getattr(job, 'results', None) if job.status == 'completed' else None,
                'error_message': job.error_messages if job.status == 'failed' else None,
                'resource_usage': self._get_resource_usage_info(job),
                'can_cancel': job.status in ['queued', 'processing']
            }
            
            request_id = getattr(request, 'api_request_id', '')
            response_data = APIResponseFormatter.format_job_status_response(
                job_info,
                include_details=True,
                request_id=request_id
            )
            
            return APIResponseFormatter.create_json_response(response_data)
            
        except ProcessingJob.DoesNotExist:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['JOB_NOT_FOUND'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Status check error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['SERVER_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_resource_usage_info(self, job):
        """Get resource usage information for the job."""
        try:
            # Get session disk usage
            session_info = TempFileManager.get_session_info(job.document.session_id)
            return {
                'session_disk_usage_mb': session_info.get('total_size_mb', 0),
                'session_file_count': sum(
                    session_info.get(subdir, {}).get('count', 0) 
                    for subdir in ['uploads', 'processing', 'downloads']
                )
            }
        except Exception:
            return {'session_disk_usage_mb': 0, 'session_file_count': 0}
            
    def delete(self, request, job_id):
        """Cancel a processing job if it's still queued or processing."""
        try:
            job = ProcessingJob.objects.get(id=job_id)
            
            if job.status not in ['queued', 'processing']:
                raise APIError(
                    f"Cannot cancel job with status: {job.status}",
                    "INVALID_JOB_STATE",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Attempt to cancel the Celery task
            try:
                from celery import current_app
                if hasattr(job, 'celery_task_id'):
                    current_app.control.revoke(job.celery_task_id, terminate=True)
            except ImportError:
                pass  # Celery not available
            
            # Update job status
            job.status = 'cancelled'
            job.error_messages = ['Job cancelled by user request']
            job.save()
            
            request_id = getattr(request, 'api_request_id', '')
            success_data = {
                'job_id': str(job.id),
                'status': 'cancelled'
            }
            response_data = APIResponseFormatter.format_success_response(
                success_data,
                message='Job cancelled successfully',
                request_id=request_id
            )
            
            return APIResponseFormatter.create_json_response(response_data)
            
        except ProcessingJob.DoesNotExist:
            request_id = getattr(request, 'api_request_id', '')
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['JOB_NOT_FOUND'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            request_id = getattr(request, 'api_request_id', '')
            logger.error(f"Status check error: {str(e)}")
            error_response = APIResponseFormatter.format_error_response(
                ERROR_MAPPINGS['SERVER_ERROR'], request_id
            )
            return APIResponseFormatter.create_json_response(error_response, status.HTTP_500_INTERNAL_SERVER_ERROR)


class RedactionDownloadView(APIView):
    """Handle redacted PDF downloads."""
    
    @log_api_call()
    @rate_limit(requests_per_minute=120)
    @monitor_performance
    def get(self, request, job_id):
        """Download the redacted PDF file."""
        try:
            job = ProcessingJob.objects.get(id=job_id)
            
            # Validate job is completed
            if job.status != 'completed':
                raise APIError(
                    f"Job is not completed. Current status: {job.status}",
                    "JOB_NOT_COMPLETED",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Check if results contain output_path
            if not job.results or not job.results.get('output_path'):
                raise APIError(
                    "No output file available for download",
                    "NO_OUTPUT_FILE",
                    status.HTTP_404_NOT_FOUND
                )
            
            output_path = job.results['output_path']
            
            # Verify file exists
            if not os.path.exists(output_path):
                raise APIError(
                    "Output file not found on disk",
                    "FILE_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND
                )
            
            # Get filename for download
            filename = os.path.basename(output_path)
            
            # Return file as download
            return FileResponse(
                open(output_path, 'rb'),
                as_attachment=True,
                filename=filename
            )
            
        except ProcessingJob.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['JOB_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except APIError as e:
            return Response(e.to_dict(), status=e.status)
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['SERVER_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Create alias for the generic file download view
FileDownloadView = RedactionDownloadView