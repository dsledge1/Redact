"""
Simple views for basic API functionality
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json


class HealthCheckView(View):
    """Basic health check endpoint"""
    
    def get(self, request):
        return JsonResponse({'status': 'ok', 'message': 'API is running'})


@method_decorator(csrf_exempt, name='dispatch')
class FileUploadView(View):
    """Basic file upload endpoint"""
    
    def post(self, request):
        try:
            # Check if file was uploaded
            if 'file' not in request.FILES:
                return JsonResponse({
                    'success': False,
                    'error': 'No file provided'
                }, status=400)
            
            uploaded_file = request.FILES['file']
            
            # Basic validation
            if not uploaded_file.name.lower().endswith('.pdf'):
                return JsonResponse({
                    'success': False,
                    'error': 'Only PDF files are supported'
                }, status=400)
            
            # Return response matching frontend's UploadResult interface
            import uuid
            from datetime import datetime
            return JsonResponse({
                'success': True,
                'data': {
                    'documentId': str(uuid.uuid4()),
                    'fileName': uploaded_file.name,
                    'fileSize': uploaded_file.size,
                    'pageCount': 1,  # Mock value for now
                    'sessionId': request.META.get('HTTP_X_SESSION_ID', str(uuid.uuid4()))
                },
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class DocumentDetailView(View):
    """Get document details"""
    
    def get(self, request, document_id):
        # Mock document response matching PDFDocument interface
        from datetime import datetime
        return JsonResponse({
            'success': True,
            'data': {
                'id': document_id,
                'fileName': 'document.pdf',
                'originalName': 'document.pdf',
                'fileSize': 40000,
                'pageCount': 5,
                'uploadedAt': datetime.now().isoformat(),
                'sessionId': request.META.get('HTTP_X_SESSION_ID', 'mock-session'),
                'mimeType': 'application/pdf',
                'status': 'ready',
                'processingHistory': []
            },
            'timestamp': datetime.now().isoformat()
        })


@method_decorator(csrf_exempt, name='dispatch')
class DocumentDownloadView(View):
    """Download document file"""
    
    def get(self, request, document_id):
        # For now, return a simple PDF response  
        # In a real implementation, you'd retrieve the stored file
        from django.http import HttpResponse
        import io
        
        # Create a simple PDF content (this would normally be retrieved from storage)
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
50 750 Td
(Sample PDF Document) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000074 00000 n 
0000000120 00000 n 
0000000213 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
310
%%EOF"""
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="document.pdf"'
        response['Content-Length'] = str(len(pdf_content))
        return response


@method_decorator(csrf_exempt, name='dispatch')  
class RedactionAPIView(View):
    """Basic redaction endpoint"""
    
    def post(self, request):
        return JsonResponse({
            'success': True,
            'message': 'Redaction endpoint - not yet implemented',
            'job_id': 'mock-redaction-job'
        })


@method_decorator(csrf_exempt, name='dispatch')
class SplitAPIView(View):
    """Basic split endpoint"""
    
    def post(self, request):
        return JsonResponse({
            'success': True,
            'message': 'Split endpoint - not yet implemented',
            'job_id': 'mock-split-job'
        })


@method_decorator(csrf_exempt, name='dispatch') 
class MergeAPIView(View):
    """Basic merge endpoint"""
    
    def post(self, request):
        return JsonResponse({
            'success': True,
            'message': 'Merge endpoint - not yet implemented', 
            'job_id': 'mock-merge-job'
        })


@method_decorator(csrf_exempt, name='dispatch')
class ExtractAPIView(View):
    """Basic extract endpoint"""
    
    def post(self, request):
        return JsonResponse({
            'success': True,
            'message': 'Extract endpoint - not yet implemented',
            'job_id': 'mock-extract-job'
        })


class JobStatusView(View):
    """Basic job status endpoint"""
    
    def get(self, request, job_id):
        return JsonResponse({
            'success': True,
            'job_id': job_id,
            'status': 'completed',
            'progress': 100,
            'message': 'Mock job completed successfully'
        })


class FileDownloadView(View):
    """Basic file download endpoint"""
    
    def get(self, request, job_id):
        return JsonResponse({
            'success': True,
            'message': 'Download endpoint - not yet implemented',
            'download_url': f'/api/download/{job_id}/file.pdf'
        })