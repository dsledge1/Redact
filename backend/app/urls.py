"""URL routing configuration for Ultimate PDF app."""

from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.FileUploadView.as_view(), name='file_upload'),
    path('redact/', views.RedactionAPIView.as_view(), name='redact_pdf'),
    path('redact/preview/', views.RedactionPreviewView.as_view(), name='redact_preview'),
    path('redact/approve/', views.RedactionApprovalView.as_view(), name='redact_approve'),
    path('redact/status/<uuid:job_id>/', views.JobStatusView.as_view(), name='redact_status'),
    path('redact/download/<uuid:job_id>/', views.RedactionDownloadView.as_view(), name='redact_download'),
    path('redact/cancel/<uuid:job_id>/', views.JobStatusView.as_view(), name='redact_cancel'),
    path('split/', views.SplitAPIView.as_view(), name='split_pdf'),
    path('merge/', views.MergeAPIView.as_view(), name='merge_pdf'),
    path('extract/', views.ExtractAPIView.as_view(), name='extract_data'),
    path('status/<uuid:job_id>/', views.JobStatusView.as_view(), name='job_status'),
]