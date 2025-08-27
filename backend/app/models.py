"""Django models for Ultimate PDF application."""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q, Count, Avg, Sum
import uuid
import json


class PDFDocument(models.Model):
    """Model for tracking uploaded PDF documents."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    upload_timestamp = models.DateTimeField(default=timezone.now)
    session_id = models.CharField(max_length=64, db_index=True)
    content_hash = models.CharField(max_length=64, help_text="SHA-256 hash of file content")
    file_hash = models.CharField(max_length=64, db_index=True, help_text="File integrity hash")
    processing_metadata = models.JSONField(default=dict, help_text="PDF processing metadata and validation results")
    
    class Meta:
        ordering = ['-upload_timestamp']
        db_table = 'pdf_documents'
        indexes = [
            models.Index(fields=['session_id', 'upload_timestamp']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['file_size']),
        ]
        
    def __str__(self) -> str:
        return f"{self.filename} ({self.session_id})"
    
    def get_file_size_mb(self) -> float:
        """Get file size in megabytes."""
        return round(self.file_size / (1024 * 1024), 2)
    
    def get_processing_cost(self) -> dict:
        """Calculate estimated processing cost based on file characteristics."""
        base_cost = 0.01  # Base cost per document
        size_factor = self.file_size / (1024 * 1024)  # Size in MB
        page_count = self.processing_metadata.get('validation_result', {}).get('page_count', 1)
        
        # Cost factors
        size_cost = size_factor * 0.001  # $0.001 per MB
        page_cost = page_count * 0.005   # $0.005 per page
        
        total_cost = base_cost + size_cost + page_cost
        
        return {
            'base_cost': base_cost,
            'size_cost': round(size_cost, 4),
            'page_cost': round(page_cost, 4),
            'total_cost': round(total_cost, 4),
            'currency': 'USD'
        }
    
    def needs_ocr(self) -> bool:
        """Check if document needs OCR processing."""
        return self.processing_metadata.get('needs_ocr', False)
    
    def get_page_count(self) -> int:
        """Get number of pages in the document."""
        return self.processing_metadata.get('validation_result', {}).get('page_count', 0)
    
    @classmethod
    def get_by_hash(cls, file_hash: str):
        """Find documents by file hash to detect duplicates."""
        return cls.objects.filter(file_hash=file_hash)
    
    @classmethod
    def get_session_documents(cls, session_id: str):
        """Get all documents for a session."""
        return cls.objects.filter(session_id=session_id).order_by('-upload_timestamp')


class ProcessingJob(models.Model):
    """Model for tracking PDF processing job status."""
    
    JOB_TYPES = [
        ('redact', 'Redaction'),
        ('split', 'Split'),
        ('merge', 'Merge'),
        ('extract', 'Extract'),
        ('ocr', 'OCR Processing'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, related_name='jobs')
    job_type = models.CharField(max_length=15, choices=JOB_TYPES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    progress = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], help_text="Progress percentage (0-100)")
    error_messages = models.TextField(blank=True, help_text="Error details if job failed")
    processing_parameters = models.JSONField(default=dict, help_text="Job-specific processing parameters")
    results = models.JSONField(default=dict, help_text="Job processing results and output")
    estimated_completion_time = models.DateTimeField(null=True, blank=True, help_text="Estimated completion time")
    resource_usage = models.JSONField(default=dict, help_text="Resource usage metrics")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    celery_task_id = models.CharField(max_length=255, blank=True, help_text="Celery task ID for background processing")
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'processing_jobs'
        indexes = [
            models.Index(fields=['status', 'job_type']),
            models.Index(fields=['document', 'created_at']),
            models.Index(fields=['celery_task_id']),
        ]
        
    def __str__(self) -> str:
        return f"{self.job_type} job for {self.document.filename} ({self.status})"
    
    def get_duration(self):
        """Get job processing duration."""
        if self.status in ['completed', 'failed', 'cancelled']:
            return self.updated_at - self.created_at
        return timezone.now() - self.created_at
    
    def get_processing_rate(self) -> float:
        """Get processing rate (progress per minute)."""
        duration = self.get_duration()
        if duration.total_seconds() > 0:
            return self.progress / (duration.total_seconds() / 60)
        return 0.0
    
    def estimate_remaining_time(self):
        """Estimate remaining processing time."""
        if self.progress > 0 and self.status == 'processing':
            rate = self.get_processing_rate()
            if rate > 0:
                remaining_progress = 100 - self.progress
                remaining_minutes = remaining_progress / rate
                return timezone.timedelta(minutes=remaining_minutes)
        return None
    
    @classmethod
    def get_active_jobs(cls):
        """Get all active (non-completed) jobs."""
        return cls.objects.filter(status__in=['pending', 'queued', 'processing'])
    
    @classmethod
    def get_job_statistics(cls):
        """Get job processing statistics."""
        return cls.objects.aggregate(
            total_jobs=Count('id'),
            completed_jobs=Count('id', filter=Q(status='completed')),
            failed_jobs=Count('id', filter=Q(status='failed')),
            average_progress=Avg('progress'),
            total_processing_time=Sum('updated_at') - Sum('created_at')
        )


class TextExtractionResult(models.Model):
    """Model for storing text extraction results with source attribution."""
    
    EXTRACTION_METHODS = [
        ('text_layer', 'PDF Text Layer'),
        ('ocr', 'OCR Processing'),
        ('hybrid', 'Hybrid (Text Layer + OCR)'),
    ]
    
    document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, related_name='text_extractions')
    page_number = models.PositiveIntegerField()
    extraction_method = models.CharField(max_length=20, choices=EXTRACTION_METHODS)
    text_content = models.TextField(help_text="Extracted text content")
    confidence_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Extraction confidence (0.0-1.0)"
    )
    quality_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Text quality assessment (0.0-1.0)"
    )
    extraction_metadata = models.JSONField(default=dict, help_text="Extraction metadata and source information")
    processing_time = models.FloatField(help_text="Processing time in seconds")
    word_count = models.PositiveIntegerField(default=0)
    char_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['document', 'page_number']
        db_table = 'text_extraction_results'
        unique_together = ['document', 'page_number', 'extraction_method']
        indexes = [
            models.Index(fields=['document', 'page_number']),
            models.Index(fields=['extraction_method']),
            models.Index(fields=['confidence_score']),
        ]
    
    def clean(self):
        """Validate confidence and quality scores are within valid range."""
        from django.core.exceptions import ValidationError
        
        if self.confidence_score is not None and not (0.0 <= self.confidence_score <= 1.0):
            raise ValidationError({'confidence_score': 'Confidence score must be between 0.0 and 1.0'})
        
        if self.quality_score is not None and not (0.0 <= self.quality_score <= 1.0):
            raise ValidationError({'quality_score': 'Quality score must be between 0.0 and 1.0'})
    
    def save(self, *args, **kwargs):
        """Override save to ensure clean is called."""
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self) -> str:
        return f"Text extraction for {self.document.filename} page {self.page_number} ({self.extraction_method})"


class SearchConfiguration(models.Model):
    """Model for storing user search preferences and configurations."""
    
    SEARCH_STRATEGIES = [
        ('fuzzy_only', 'Fuzzy Matching Only'),
        ('pattern_only', 'Pattern Matching Only'),
        ('combined', 'Combined (Fuzzy + Pattern)'),
        ('hierarchical', 'Hierarchical (Exact → Fuzzy → Pattern)'),
        ('adaptive', 'Adaptive Strategy'),
    ]
    
    user_session = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=100, help_text="Configuration name")
    strategy = models.CharField(max_length=20, choices=SEARCH_STRATEGIES, default='combined')
    fuzzy_threshold = models.PositiveSmallIntegerField(
        default=80, 
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Fuzzy matching threshold (0-100)"
    )
    confidence_threshold = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Confidence threshold for matches (0.0-1.0)"
    )
    regex_patterns = models.JSONField(default=list, help_text="Custom regex patterns to use")
    pattern_types = models.JSONField(default=list, help_text="Pattern types to search for")
    search_algorithms = models.JSONField(default=dict, help_text="Algorithm-specific settings")
    enable_validation = models.BooleanField(default=True, help_text="Enable pattern validation")
    enable_clustering = models.BooleanField(default=True, help_text="Enable result clustering")
    context_window = models.PositiveSmallIntegerField(default=100, help_text="Context characters around matches")
    max_results_per_page = models.PositiveSmallIntegerField(default=1000, help_text="Maximum results per page")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        db_table = 'search_configurations'
        indexes = [
            models.Index(fields=['user_session', 'name']),
        ]
    
    def __str__(self) -> str:
        return f"Search config '{self.name}' for session {self.user_session}"


class RedactionMatch(models.Model):
    """Enhanced model for storing text matching results for redaction."""
    
    MATCH_TYPES = [
        ('fuzzy', 'Fuzzy Match'),
        ('exact', 'Exact Match'),
        ('pattern', 'Pattern Match'),
        ('hybrid', 'Hybrid Match'),
    ]
    
    EXTRACTION_SOURCES = [
        ('text_layer', 'PDF Text Layer'),
        ('ocr', 'OCR Processing'),
        ('hybrid', 'Hybrid Source'),
    ]
    
    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name='matches')
    search_term = models.CharField(max_length=500, help_text="Original search term")
    matched_text = models.TextField(help_text="Matched text from PDF")
    confidence_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Overall matching confidence (0.0-1.0)"
    )
    page_number = models.PositiveIntegerField()
    match_type = models.CharField(max_length=10, choices=MATCH_TYPES, default='fuzzy')
    extraction_source = models.CharField(max_length=15, choices=EXTRACTION_SOURCES, default='text_layer')
    pattern_type = models.CharField(max_length=50, blank=True, help_text="Pattern type for pattern matches")
    
    # Position information
    x_coordinate = models.FloatField(help_text="X coordinate of match on page")
    y_coordinate = models.FloatField(help_text="Y coordinate of match on page")
    width = models.FloatField(help_text="Width of matched text area")
    height = models.FloatField(help_text="Height of matched text area")
    
    # Approval workflow
    approved_status = models.BooleanField(
        null=True, 
        blank=True, 
        help_text="True=approved, False=rejected, None=pending"
    )
    
    # Enhanced metadata
    confidence_breakdown = models.JSONField(
        default=dict, 
        help_text="Detailed confidence scoring breakdown"
    )
    context_metadata = models.JSONField(
        default=dict, 
        help_text="Context and surrounding text information"
    )
    validation_passed = models.BooleanField(
        null=True, blank=True, 
        help_text="Pattern validation result"
    )
    user_feedback = models.JSONField(
        default=dict, 
        help_text="User feedback for machine learning"
    )
    cluster_id = models.CharField(max_length=64, blank=True, help_text="Match cluster identifier")
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-confidence_score', 'page_number']
        db_table = 'redaction_matches'
        indexes = [
            models.Index(fields=['job', 'page_number']),
            models.Index(fields=['match_type', 'confidence_score']),
            models.Index(fields=['approved_status']),
            models.Index(fields=['cluster_id']),
        ]
        
    def __str__(self) -> str:
        return f"Match '{self.matched_text[:50]}...' ({self.confidence_score:.3f} confidence)"
    
    def needs_approval(self) -> bool:
        """Check if match needs manual approval."""
        return self.approved_status is None
    
    def clean(self):
        """Validate confidence score is within valid range."""
        from django.core.exceptions import ValidationError
        
        if self.confidence_score is not None and not (0.0 <= self.confidence_score <= 1.0):
            raise ValidationError({'confidence_score': 'Confidence score must be between 0.0 and 1.0'})
    
    def save(self, *args, **kwargs):
        """Override save to ensure clean is called."""
        self.clean()
        super().save(*args, **kwargs)
    
    def is_high_confidence(self) -> bool:
        """Check if match has high confidence."""
        return self.confidence_score >= 0.9


class OCRResult(models.Model):
    """Model for storing OCR processing results with confidence scores."""
    
    document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, related_name='ocr_results')
    page_number = models.PositiveIntegerField()
    extracted_text = models.TextField(help_text="OCR extracted text")
    confidence_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Overall OCR confidence (0.0-1.0)"
    )
    processing_time = models.FloatField(help_text="Processing time in seconds")
    ocr_engine = models.CharField(max_length=50, default='pytesseract')
    preprocessing_applied = models.JSONField(default=list, help_text="List of preprocessing steps applied")
    text_regions = models.JSONField(default=list, help_text="Text regions with bounding boxes")
    language = models.CharField(max_length=10, default='eng', help_text="OCR language code")
    dpi_used = models.PositiveIntegerField(default=300, help_text="DPI setting used for OCR")
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['document', 'page_number']
        db_table = 'ocr_results'
        unique_together = ['document', 'page_number']
        indexes = [
            models.Index(fields=['document', 'page_number']),
            models.Index(fields=['confidence_score']),
        ]
    
    def __str__(self) -> str:
        return f"OCR result for {self.document.filename} page {self.page_number} ({self.confidence_score:.1f}%)"
    
    def get_word_count(self) -> int:
        """Get word count of extracted text."""
        return len(self.extracted_text.split())
    
    def clean(self):
        """Validate confidence score is within valid range."""
        from django.core.exceptions import ValidationError
        
        if self.confidence_score is not None and not (0.0 <= self.confidence_score <= 1.0):
            raise ValidationError({'confidence_score': 'Confidence score must be between 0.0 and 1.0'})
    
    def save(self, *args, **kwargs):
        """Override save to ensure clean is called."""
        self.clean()
        super().save(*args, **kwargs)
    
    def has_high_confidence(self) -> bool:
        """Check if OCR result has high confidence."""
        return self.confidence_score >= 0.8


class SessionInfo(models.Model):
    """Model for tracking session lifecycle and cleanup status."""
    
    SESSION_STATUS = [
        ('active', 'Active'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cleaned', 'Cleaned'),
    ]
    
    session_id = models.CharField(max_length=64, primary_key=True)
    status = models.CharField(max_length=15, choices=SESSION_STATUS, default='active')
    created_at = models.DateTimeField(default=timezone.now)
    last_accessed = models.DateTimeField(auto_now=True)
    cleanup_scheduled_at = models.DateTimeField(null=True, blank=True)
    cleanup_completed_at = models.DateTimeField(null=True, blank=True)
    file_count = models.PositiveIntegerField(default=0, help_text="Total files in session")
    total_size_bytes = models.PositiveBigIntegerField(default=0, help_text="Total session size in bytes")
    processing_jobs_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'session_info'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['cleanup_scheduled_at']),
        ]
    
    def __str__(self) -> str:
        return f"Session {self.session_id} ({self.status})"
    
    def get_age_hours(self) -> float:
        """Get session age in hours."""
        delta = timezone.now() - self.created_at
        return delta.total_seconds() / 3600
    
    def get_size_mb(self) -> float:
        """Get session size in MB."""
        return round(self.total_size_bytes / (1024 * 1024), 2)
    
    def is_cleanup_due(self, cleanup_hours: int = 8) -> bool:
        """Check if session cleanup is due."""
        return self.get_age_hours() >= cleanup_hours
    
    def update_stats(self):
        """Update session statistics from related documents."""
        documents = PDFDocument.objects.filter(session_id=self.session_id)
        self.file_count = documents.count()
        self.total_size_bytes = documents.aggregate(
            total=Sum('file_size')
        )['total'] or 0
        self.processing_jobs_count = ProcessingJob.objects.filter(
            document__session_id=self.session_id
        ).count()
        self.save()
    
    @classmethod
    def cleanup_old_sessions(cls, hours_threshold: int = 8):
        """Mark old sessions for cleanup."""
        from datetime import timedelta
        cutoff_time = timezone.now() - timedelta(hours=hours_threshold)
        return cls.objects.filter(
            created_at__lt=cutoff_time,
            status='active'
        ).update(status='expired')


class ProcessingJobManager(models.Manager):
    """Custom manager for ProcessingJob model."""
    
    def active(self):
        """Get active jobs."""
        return self.filter(status__in=['pending', 'queued', 'processing'])
    
    def completed_today(self):
        """Get jobs completed today."""
        from datetime import date
        return self.filter(
            status='completed',
            updated_at__date=date.today()
        )
    
    def failed_recently(self, hours: int = 24):
        """Get jobs that failed in the last N hours."""
        from datetime import timedelta
        cutoff_time = timezone.now() - timedelta(hours=hours)
        return self.filter(
            status='failed',
            updated_at__gte=cutoff_time
        )


# Add custom manager to ProcessingJob
ProcessingJob.add_to_class('objects', ProcessingJobManager())


class MatchScoring(models.Model):
    """Model for storing confidence calculation details."""
    
    match = models.OneToOneField(RedactionMatch, on_delete=models.CASCADE, related_name='scoring_details')
    scoring_factors = models.JSONField(default=dict, help_text="Individual scoring factor contributions")
    confidence_components = models.JSONField(default=dict, help_text="Breakdown of confidence components")
    final_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Final calculated confidence score (0.0-1.0)"
    )
    scoring_algorithm = models.CharField(max_length=50, help_text="Algorithm used for scoring")
    calibration_applied = models.BooleanField(default=False, help_text="Whether calibration was applied")
    processing_time = models.FloatField(help_text="Scoring processing time in seconds")
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'match_scoring'
        indexes = [
            models.Index(fields=['final_score']),
            models.Index(fields=['scoring_algorithm']),
        ]
    
    def clean(self):
        """Validate final score is within valid range."""
        from django.core.exceptions import ValidationError
        
        if self.final_score is not None and not (0.0 <= self.final_score <= 1.0):
            raise ValidationError({'final_score': 'Final score must be between 0.0 and 1.0'})
    
    def save(self, *args, **kwargs):
        """Override save to ensure clean is called."""
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self) -> str:
        return f"Scoring for match {self.match.id} ({self.final_score:.3f})"


class SearchSession(models.Model):
    """Model for tracking search operations and sessions."""
    
    SEARCH_STATUSES = [
        ('active', 'Active'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, related_name='search_sessions')
    search_terms = models.JSONField(default=list, help_text="Search terms used")
    search_type = models.CharField(max_length=20, help_text="Type of search performed")
    configuration = models.ForeignKey(
        SearchConfiguration, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='sessions'
    )
    status = models.CharField(max_length=15, choices=SEARCH_STATUSES, default='active')
    total_matches = models.PositiveIntegerField(default=0)
    pages_processed = models.PositiveIntegerField(default=0)
    processing_time = models.FloatField(default=0.0, help_text="Total processing time in seconds")
    
    # Search parameters (JSON serialized)
    search_parameters = models.JSONField(default=dict, help_text="Search parameters and settings")
    results_summary = models.JSONField(default=dict, help_text="Summary of search results")
    performance_metrics = models.JSONField(default=dict, help_text="Performance and timing metrics")
    error_log = models.JSONField(default=list, help_text="Processing errors and warnings")
    
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'search_sessions'
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['document', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self) -> str:
        return f"Search session {self.session_id} for {self.document.filename}"
    
    def get_duration(self):
        """Get search duration."""
        if self.completed_at:
            return self.completed_at - self.created_at
        return timezone.now() - self.created_at
    
    def get_matches_per_second(self) -> float:
        """Calculate matches found per second."""
        if self.processing_time > 0:
            return self.total_matches / self.processing_time
        return 0.0
    
    @classmethod
    def get_recent_sessions(cls, hours: int = 24):
        """Get search sessions from the last N hours."""
        from datetime import timedelta
        cutoff_time = timezone.now() - timedelta(hours=hours)
        return cls.objects.filter(created_at__gte=cutoff_time)


class DocumentProcessingStats(models.Model):
    """Model for tracking document processing statistics."""
    
    date = models.DateField(unique=True, default=timezone.now)
    documents_uploaded = models.PositiveIntegerField(default=0)
    documents_processed = models.PositiveIntegerField(default=0)
    total_processing_time_seconds = models.PositiveIntegerField(default=0)
    total_file_size_bytes = models.PositiveBigIntegerField(default=0)
    ocr_jobs_completed = models.PositiveIntegerField(default=0)
    redaction_jobs_completed = models.PositiveIntegerField(default=0)
    split_jobs_completed = models.PositiveIntegerField(default=0)
    merge_jobs_completed = models.PositiveIntegerField(default=0)
    average_confidence_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    failed_jobs_count = models.PositiveIntegerField(default=0)
    
    # Enhanced statistics for new services
    text_extraction_jobs = models.PositiveIntegerField(default=0)
    fuzzy_matches_found = models.PositiveIntegerField(default=0)
    pattern_matches_found = models.PositiveIntegerField(default=0)
    search_sessions_created = models.PositiveIntegerField(default=0)
    average_search_time_seconds = models.FloatField(default=0.0)
    total_matches_approved = models.PositiveIntegerField(default=0)
    total_matches_rejected = models.PositiveIntegerField(default=0)
    average_match_confidence = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    calibration_accuracy = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    
    class Meta:
        ordering = ['-date']
        db_table = 'processing_stats'
    
    def __str__(self) -> str:
        return f"Stats for {self.date}: {self.documents_uploaded} uploads, {self.documents_processed} processed"
    
    @classmethod
    def update_daily_stats(cls):
        """Update today's processing statistics."""
        from datetime import date
        today = date.today()
        
        stats, created = cls.objects.get_or_create(date=today)
        
        # Update document counts
        stats.documents_uploaded = PDFDocument.objects.filter(
            upload_timestamp__date=today
        ).count()
        
        completed_jobs_today = ProcessingJob.objects.completed_today()
        stats.documents_processed = completed_jobs_today.count()
        
        # Update job type counts
        job_type_counts = completed_jobs_today.values('job_type').annotate(
            count=Count('id')
        )
        
        for job_type_data in job_type_counts:
            job_type = job_type_data['job_type']
            count = job_type_data['count']
            
            if job_type == 'ocr':
                stats.ocr_jobs_completed = count
            elif job_type == 'redact':
                stats.redaction_jobs_completed = count
            elif job_type == 'split':
                stats.split_jobs_completed = count
            elif job_type == 'merge':
                stats.merge_jobs_completed = count
        
        # Update other metrics
        stats.failed_jobs_count = ProcessingJob.objects.filter(
            updated_at__date=today,
            status='failed'
        ).count()
        
        stats.total_file_size_bytes = PDFDocument.objects.filter(
            upload_timestamp__date=today
        ).aggregate(
            total=Sum('file_size')
        )['total'] or 0
        
        # Calculate average OCR confidence
        avg_confidence = OCRResult.objects.filter(
            created_at__date=today
        ).aggregate(
            avg=Avg('confidence_score')
        )['avg']
        
        stats.average_confidence_score = avg_confidence or 0.0
        
        # Update enhanced statistics
        text_extractions_today = TextExtractionResult.objects.filter(
            created_at__date=today
        ).count()
        stats.text_extraction_jobs = text_extractions_today
        
        # Match statistics
        matches_today = RedactionMatch.objects.filter(created_at__date=today)
        fuzzy_matches = matches_today.filter(match_type='fuzzy').count()
        pattern_matches = matches_today.filter(match_type='pattern').count()
        
        stats.fuzzy_matches_found = fuzzy_matches
        stats.pattern_matches_found = pattern_matches
        
        # Approval statistics
        stats.total_matches_approved = matches_today.filter(approved_status=True).count()
        stats.total_matches_rejected = matches_today.filter(approved_status=False).count()
        
        # Average match confidence
        avg_match_confidence = matches_today.aggregate(
            avg=Avg('confidence_score')
        )['avg']
        stats.average_match_confidence = avg_match_confidence or 0.0
        
        # Search session statistics
        search_sessions_today = SearchSession.objects.filter(created_at__date=today)
        stats.search_sessions_created = search_sessions_today.count()
        
        avg_search_time = search_sessions_today.aggregate(
            avg=Avg('processing_time')
        )['avg']
        stats.average_search_time_seconds = avg_search_time or 0.0
        
        # Calibration accuracy from match scoring
        calibration_scores = MatchScoring.objects.filter(
            created_at__date=today,
            calibration_applied=True
        ).aggregate(
            avg=Avg('final_score')
        )['avg']
        stats.calibration_accuracy = calibration_scores or 0.0
        
        stats.save()
        return stats