"""URL routing configuration for Ultimate PDF app."""

from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.FileUploadView.as_view(), name='file_upload'),
    path('redact/', views.RedactionAPIView.as_view(), name='redact_pdf'),
    path('split/', views.SplitAPIView.as_view(), name='split_pdf'),
    path('merge/', views.MergeAPIView.as_view(), name='merge_pdf'),
    path('extract/', views.ExtractAPIView.as_view(), name='extract_data'),
    path('status/<uuid:job_id>/', views.JobStatusView.as_view(), name='job_status'),
]