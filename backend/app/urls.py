"""Simplified URL routing configuration."""

from django.urls import path
from . import views_simple as views

urlpatterns = [
    # Core API endpoints
    path('upload/', views.FileUploadView.as_view(), name='file_upload'),
    path('documents/<str:document_id>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('documents/<str:document_id>/download/', views.DocumentDownloadView.as_view(), name='document_download'),
    path('redact/', views.RedactionAPIView.as_view(), name='redact_pdf'),
    path('split/', views.SplitAPIView.as_view(), name='split_pdf'),
    path('merge/', views.MergeAPIView.as_view(), name='merge_pdf'),
    path('extract/', views.ExtractAPIView.as_view(), name='extract_data'),
    
    # Job management endpoints
    path('job/<str:job_id>/status/', views.JobStatusView.as_view(), name='job_status'),
    path('job/<str:job_id>/download/', views.FileDownloadView.as_view(), name='file_download'),
    
    # Health check
    path('health/', views.HealthCheckView.as_view(), name='health_check'),
]