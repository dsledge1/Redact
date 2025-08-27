"""Celery application configuration for Ultimate PDF background processing."""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ultimate_pdf.settings')

app = Celery('ultimate_pdf')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps
app.autodiscover_tasks()

# Explicitly import top-level tasks module
app.conf.imports = ('tasks',)

# Celery configuration
app.conf.update(
    # Task routing
    task_routes={
        'tasks.cleanup_abandoned_files': {'queue': 'cleanup'},
        'tasks.process_large_pdf': {'queue': 'processing'},
        'tasks.ocr_processing': {'queue': 'ocr'},
    },
    
    # Task serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task execution settings
    task_always_eager=False,
    task_eager_propagates=True,
    
    # Worker settings
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    
    # Task result settings
    result_expires=3600,  # 1 hour
    
    # Task timeout settings (in seconds)
    task_soft_time_limit=1800,  # 30 minutes soft limit
    task_time_limit=2100,       # 35 minutes hard limit
    
    # Retry policy
    task_default_retry_delay=60,     # 1 minute
    task_max_retries=3,
    
    # Queue settings
    task_default_queue='default',
    task_create_missing_queues=True,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Beat schedule (for periodic tasks)
    beat_schedule={
        'cleanup-old-sessions': {
            'task': 'tasks.cleanup_old_sessions',
            'schedule': 300.0,  # Run every 5 minutes
            'options': {'queue': 'cleanup'}
        },
        'disk-usage-check': {
            'task': 'tasks.monitor_disk_usage',
            'schedule': 600.0,  # Run every 10 minutes
            'options': {'queue': 'monitoring'}
        },
    },
)

# Task priority queues
app.conf.task_routes = {
    'tasks.cleanup_abandoned_files': {
        'queue': 'cleanup',
        'routing_key': 'cleanup.abandoned_files',
    },
    'tasks.cleanup_old_sessions': {
        'queue': 'cleanup', 
        'routing_key': 'cleanup.old_sessions',
    },
    'tasks.process_large_pdf': {
        'queue': 'processing',
        'routing_key': 'processing.large_pdf',
    },
    'tasks.ocr_processing': {
        'queue': 'ocr',
        'routing_key': 'ocr.processing',
    },
    'tasks.fuzzy_matching': {
        'queue': 'processing',
        'routing_key': 'processing.fuzzy_matching',
    },
    'tasks.pdf_redaction': {
        'queue': 'processing',
        'routing_key': 'processing.redaction',
    },
    'tasks.monitor_disk_usage': {
        'queue': 'monitoring',
        'routing_key': 'monitoring.disk_usage',
    },
}

# Queue definitions with different priorities
app.conf.task_queue_max_priority = 10
app.conf.task_default_priority = 5

# Worker pool settings
app.conf.worker_pool = 'prefork'
app.conf.worker_concurrency = 4  # Adjust based on server capacity

# Error handling
app.conf.task_reject_on_worker_lost = True
app.conf.task_acks_late = True

# Memory and resource management
app.conf.worker_max_memory_per_child = 500000  # 500MB per worker process

@app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery functionality."""
    print(f'Request: {self.request!r}')
    return 'Celery is working!'

# Celery signal handlers for logging and monitoring
from celery.signals import (
    task_prerun, task_postrun, task_failure, 
    worker_ready, worker_shutdown
)
import logging

logger = logging.getLogger(__name__)

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Log task start."""
    logger.info(f"Task {task.name} ({task_id}) started with args={args} kwargs={kwargs}")

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Log task completion."""
    logger.info(f"Task {task.name} ({task_id}) completed with state={state}")

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Log task failures."""
    logger.error(f"Task {sender.name} ({task_id}) failed: {exception}", extra={
        'task_id': task_id,
        'exception': str(exception),
        'traceback': traceback
    })

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Log worker startup."""
    logger.info(f"Celery worker {sender.hostname} is ready")

@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Log worker shutdown."""
    logger.info(f"Celery worker {sender.hostname} is shutting down")

if __name__ == '__main__':
    app.start()