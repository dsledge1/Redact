"""URL routing configuration for Ultimate PDF app with enhanced API endpoints."""

import re
from django.urls import path
from . import views

# UUID pattern for validation
UUID_PATTERN = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

urlpatterns = [
    # Core API endpoints - Main operations
    path('upload/', views.FileUploadView.as_view(), name='file_upload'),
    path('redact/', views.RedactionAPIView.as_view(), name='redact_pdf'),
    path('redact/preview/', views.RedactionPreviewView.as_view(), name='redact_preview'),
    path('redact/approve/', views.RedactionApprovalView.as_view(), name='redact_approve'),
    path('split/', views.SplitAPIView.as_view(), name='split_pdf'),
    path('merge/', views.MergeAPIView.as_view(), name='merge_pdf'),
    path('extract/', views.ExtractAPIView.as_view(), name='extract_data'),
    
    # Job management endpoints with UUID validation
    # Use DELETE method on /status/ endpoint for cancellation
    path('job/<uuid:job_id>/status/', views.JobStatusView.as_view(), name='job_status'),
    path('job/<uuid:job_id>/download/', views.FileDownloadView.as_view(), name='file_download'),
    
    # Legacy endpoints for backward compatibility
    path('status/<uuid:job_id>/', views.JobStatusView.as_view(), name='job_status_legacy'),
    path('redact/status/<uuid:job_id>/', views.JobStatusView.as_view(), name='redact_status'),
    path('redact/download/<uuid:job_id>/', views.RedactionDownloadView.as_view(), name='redact_download'),
    
    # API monitoring and management endpoints
    path('health/', views.HealthCheckView.as_view(), name='health_check'),
    path('docs/', views.APIDocumentationView.as_view(), name='api_docs'),
    path('metrics/', views.APIMetricsView.as_view(), name='api_metrics'),
    
    # Session management endpoints
    path('session/create/', views.SessionCreateView.as_view(), name='session_create'),
    path('session/<uuid:session_id>/status/', views.SessionStatusView.as_view(), name='session_status'),
    path('session/<uuid:session_id>/cleanup/', views.SessionCleanupView.as_view(), name='session_cleanup'),
    
    # Batch operations endpoint (future enhancement)
    # path('batch/', views.BatchOperationView.as_view(), name='batch_operations'),
]