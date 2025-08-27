"""Django admin configuration for Ultimate PDF application."""

from django.contrib import admin
from .models import PDFDocument, ProcessingJob, RedactionMatch


@admin.register(PDFDocument)
class PDFDocumentAdmin(admin.ModelAdmin):
    """Admin interface for PDFDocument model."""
    
    list_display = ['filename', 'session_id', 'file_size', 'upload_timestamp']
    list_filter = ['upload_timestamp']
    search_fields = ['filename', 'session_id', 'content_hash']
    readonly_fields = ['id', 'upload_timestamp', 'content_hash']
    ordering = ['-upload_timestamp']
    
    fieldsets = [
        ('File Information', {
            'fields': ['filename', 'file_size', 'content_hash']
        }),
        ('Session Details', {
            'fields': ['session_id', 'upload_timestamp']
        }),
        ('System', {
            'fields': ['id'],
            'classes': ['collapse']
        })
    ]


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    """Admin interface for ProcessingJob model."""
    
    list_display = ['document', 'job_type', 'status', 'progress', 'created_at']
    list_filter = ['job_type', 'status', 'created_at']
    search_fields = ['document__filename', 'document__session_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = [
        ('Job Information', {
            'fields': ['document', 'job_type', 'status', 'progress']
        }),
        ('Error Details', {
            'fields': ['error_messages'],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
        ('System', {
            'fields': ['id'],
            'classes': ['collapse']
        })
    ]


@admin.register(RedactionMatch)
class RedactionMatchAdmin(admin.ModelAdmin):
    """Admin interface for RedactionMatch model."""
    
    list_display = ['truncated_text', 'confidence_score', 'page_number', 'approved_status', 'created_at']
    list_filter = ['approved_status', 'page_number', 'created_at']
    search_fields = ['text', 'job__document__filename']
    readonly_fields = ['created_at']
    ordering = ['-confidence_score', 'page_number']
    
    def truncated_text(self, obj):
        """Return truncated text for list display."""
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    truncated_text.short_description = 'Text'
    
    fieldsets = [
        ('Match Information', {
            'fields': ['job', 'text', 'confidence_score', 'approved_status']
        }),
        ('Position', {
            'fields': ['page_number', 'x_coordinate', 'y_coordinate', 'width', 'height']
        }),
        ('Timestamps', {
            'fields': ['created_at'],
            'classes': ['collapse']
        })
    ]