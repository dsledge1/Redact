"""Django views for Ultimate PDF application."""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils.text import get_valid_filename
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from datetime import timedelta
from pathlib import Path
import logging

from .models import PDFDocument, ProcessingJob
from .utils.validators import validate_pdf_file, validate_session_id
from .utils.errors import APIError, ERROR_MAPPINGS, ValidationError
from .services.temp_file_manager import TempFileManager
from .services.pdf_processor import PDFProcessor
from .services.ocr_service import OCRService
from .services.unified_search_service import UnifiedSearchService
from .services.redaction_service import RedactionService
from .services.bounding_box_calculator import BoundingBoxCalculator
from .models import RedactionMatch

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
    
    def post(self, request):
        """Upload and validate PDF file."""
        try:
            if 'file' not in request.FILES:
                raise APIError("No file provided", "MISSING_FILE", status.HTTP_400_BAD_REQUEST)
            
            uploaded_file = request.FILES['file']
            session_id = request.data.get('session_id') or TempFileManager.generate_session_id()
            
            # Validate session ID before filesystem usage
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
                return Response({
                    'success': True,
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
                    ],
                    'message': f'Found {len(low_confidence_matches)} matches below {confidence_threshold}% confidence requiring approval'
                })
            
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
            
            if estimated_time['requires_background']:
                # Queue background task for processing
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
                    logger.warning("Celery not available, processing synchronously")
                    self._process_redaction_sync(job, file_path, all_matches, redaction_options)
            else:
                # Process immediately for small files
                self._process_redaction_sync(job, file_path, all_matches, redaction_options)
            
            return Response({
                'success': True,
                'job_id': str(job.id),
                'status': job.status,
                'message': 'Redaction job initiated with permanent text deletion',
                'statistics': {
                    'total_matches': len(all_matches),
                    'high_confidence_matches': len(high_confidence_matches),
                    'pages_affected': len(set(m.page_number for m in all_matches)),
                    'estimated_processing_time': estimated_time
                }
            })
            
        except PDFDocument.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except APIError as e:
            return Response(e.to_dict(), status=e.status)
        except Exception as e:
            logger.error(f"Redaction error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['PROCESSING_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_redaction_sync(self, job, file_path, matches, options):
        """Process redaction synchronously for small files."""
        try:
            job.status = 'processing'
            job.save()
            
            # Initialize RedactionService
            redaction_service = RedactionService(job.document.session_id)
            
            # Apply permanent text redactions
            result = redaction_service.redact_pdf(
                file_path,
                matches,
                **options
            )
            
            if result['success']:
                job.status = 'completed'
                job.results = result
                job.progress = 100
            else:
                job.status = 'failed'
                job.error_messages = result.get('errors', ['Unknown error'])
            
            job.save()
            
        except Exception as e:
            logger.error(f"Synchronous redaction failed: {str(e)}")
            job.status = 'failed'
            job.error_messages = [str(e)]
            job.save()


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
            
            return Response({
                'success': result['success'],
                'job_id': str(job.id),
                'output_path': result.get('output_path'),
                'statistics': result.get('statistics'),
                'message': 'Redaction completed with permanent text deletion'
            })
            
        except PDFDocument.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Redaction approval error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['PROCESSING_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
    """Handle PDF splitting requests."""
    
    def post(self, request):
        """Start PDF splitting process."""
        try:
            document_id = request.data.get('document_id')
            split_pages = request.data.get('split_pages', [])
            
            if not document_id:
                raise APIError(
                    "Document ID is required", 
                    "MISSING_PARAMETERS", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            document = PDFDocument.objects.get(id=document_id)
            
            # Create processing job
            job = ProcessingJob.objects.create(
                document=document,
                job_type='split'
            )
            
            # Validate split pages
            if split_pages and not all(isinstance(p, int) and p > 0 for p in split_pages):
                raise APIError(
                    "Split pages must be positive integers",
                    "INVALID_SPLIT_PAGES",
                    status.HTTP_400_BAD_REQUEST
                )
            
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
            
            # Validate split points against page count
            max_page = pdf_info.get('page_count', 1)
            if split_pages and max(split_pages) > max_page:
                raise APIError(
                    f"Split page {max(split_pages)} exceeds document page count ({max_page})",
                    "INVALID_PAGE_NUMBER",
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Update job with processing parameters
            job.processing_parameters = {
                'split_pages': split_pages,
                'document_path': str(file_path),
                'total_pages': max_page
            }
            job.save()
            
            # Queue background task for processing
            try:
                from tasks import process_pdf_split
                process_pdf_split.delay(str(document.id), str(job.id), split_pages)
                job.status = 'queued'
                job.save()
            except ImportError:
                logger.warning("Celery not available, processing will be synchronous")
                job.status = 'pending'
                job.save()
            
            return Response({
                'success': True,
                'job_id': str(job.id),
                'status': job.status,
                'message': 'Split job queued for processing',
                'document_info': {
                    'total_pages': max_page,
                    'split_pages': split_pages or [],
                    'estimated_output_files': len(split_pages) + 1 if split_pages else 1
                }
            })
            
        except PDFDocument.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Split error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['PROCESSING_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MergeAPIView(APIView):
    """Handle PDF merging requests with comprehensive validation."""
    
    def post(self, request):
        """Start PDF merging process."""
        try:
            document_ids = request.data.get('document_ids', [])
            output_filename = request.data.get('output_filename', None)
            
            if not document_ids or len(document_ids) < 2:
                raise APIError(
                    "At least two document IDs are required", 
                    "MISSING_PARAMETERS", 
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
            
            # Queue background task for processing
            try:
                from tasks import process_pdf_merge
                process_pdf_merge.delay(document_ids, str(job.id), output_filename)
                job.status = 'queued'
                job.save()
            except ImportError:
                logger.warning("Celery not available, processing will be synchronous")
                job.status = 'pending'
                job.save()
            
            return Response({
                'success': True,
                'job_id': str(job.id),
                'status': job.status,
                'message': 'Merge job queued for processing',
                'merge_info': {
                    'total_documents': len(documents),
                    'total_pages': total_pages,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'document_list': document_info,
                    'output_filename': output_filename
                }
            })
            
        except Exception as e:
            logger.error(f"Merge error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['PROCESSING_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ExtractAPIView(APIView):
    """Handle PDF data extraction requests with comprehensive processing."""
    
    def post(self, request):
        """Start PDF data extraction process."""
        try:
            document_id = request.data.get('document_id')
            extraction_type = request.data.get('extraction_type', 'text')
            page_range = request.data.get('page_range', None)  # [start, end] or None for all
            
            if not document_id:
                raise APIError(
                    "Document ID is required", 
                    "MISSING_PARAMETERS", 
                    status.HTTP_400_BAD_REQUEST
                )
            
            # Validate extraction type
            valid_types = ['text', 'metadata', 'images', 'all']
            if extraction_type not in valid_types:
                raise APIError(
                    f"Invalid extraction type. Must be one of: {', '.join(valid_types)}",
                    "INVALID_EXTRACTION_TYPE",
                    status.HTTP_400_BAD_REQUEST
                )
            
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
            
            # Create processing job
            job = ProcessingJob.objects.create(
                document=document,
                job_type='extract',
                processing_parameters={
                    'extraction_type': extraction_type,
                    'page_range': page_range,
                    'document_path': str(file_path),
                    'total_pages': max_pages,
                    'has_text_layer': pdf_info.get('has_text_layer', False)
                }
            )
            
            # Queue background task for processing
            try:
                from tasks import process_pdf_extraction
                process_pdf_extraction.delay(str(document.id), str(job.id), extraction_type, page_range)
                job.status = 'queued'
                job.save()
            except ImportError:
                logger.warning("Celery not available, processing will be synchronous")
                job.status = 'pending'
                job.save()
            
            return Response({
                'success': True,
                'job_id': str(job.id),
                'status': job.status,
                'message': 'Extraction job queued for processing',
                'extraction_info': {
                    'extraction_type': extraction_type,
                    'page_range': page_range or f"1-{max_pages}",
                    'total_pages': max_pages,
                    'has_text_layer': pdf_info.get('has_text_layer', False),
                    'requires_ocr': not pdf_info.get('has_text_layer', False) and extraction_type in ['text', 'all']
                }
            })
            
        except PDFDocument.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['DOCUMENT_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Extraction error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['PROCESSING_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class JobStatusView(APIView):
    """Check processing job status with comprehensive progress tracking."""
    
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
            
            # Prepare comprehensive response
            response_data = {
                'success': True,
                'job_id': str(job.id),
                'status': job.status,
                'progress': job.progress,
                'job_type': job.job_type,
                'document_id': str(job.document.id),
                'document_filename': job.document.filename,
                'created_at': job.created_at.isoformat(),
                'updated_at': job.updated_at.isoformat(),
                'processing_parameters': getattr(job, 'processing_parameters', {}),
                'estimated_completion': estimated_completion,
                'results': getattr(job, 'results', None) if job.status == 'completed' else None,
                'error_messages': job.error_messages if job.status == 'failed' else None,
                'resource_usage': self._get_resource_usage_info(job),
                'can_cancel': job.status in ['queued', 'processing']
            }
            
            return Response(response_data)
    
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
            
            return Response({
                'success': True,
                'job_id': str(job.id),
                'status': 'cancelled',
                'message': 'Job cancelled successfully'
            })
            
        except ProcessingJob.DoesNotExist:
            return Response(
                ERROR_MAPPINGS['JOB_NOT_FOUND'].to_dict(),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Status check error: {str(e)}")
            return Response(
                ERROR_MAPPINGS['SERVER_ERROR'].to_dict(),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )