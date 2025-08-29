"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { PDFService } from '../services/pdfService';
import type { ProcessingJob, ProcessingOperation } from '../types';

export interface OperationProgressBarProps {
  operationType: ProcessingOperation;
  jobId: string;
  onComplete: (results: any) => void;
  onError?: (error: string) => void;
  onCancel?: () => void;
  className?: string;
  showCancelButton?: boolean;
  showTimeRemaining?: boolean;
  showDetails?: boolean;
}

interface ProgressState {
  percentage: number;
  currentStep: string;
  estimatedTimeRemaining: number | null;
  processingSpeed: string | null;
  dataProcessed: string | null;
  error: string | null;
  isCompleted: boolean;
  isCancelled: boolean;
  canCancel: boolean;
  results: any;
}

const OPERATION_ICONS = {
  splitting: '✂️',
  merging: '📋',
  extraction: '📤',
  redaction: '🖍️'
};

const OPERATION_COLORS = {
  splitting: 'blue',
  merging: 'green',
  extraction: 'purple',
  redaction: 'red'
};

const OPERATION_STEPS = {
  splitting: [
    'Analyzing document structure',
    'Processing page ranges',
    'Splitting document',
    'Generating output files',
    'Finalizing results'
  ],
  merging: [
    'Validating input files',
    'Analyzing document structure',
    'Merging documents',
    'Processing bookmarks',
    'Finalizing merged document'
  ],
  extraction: [
    'Analyzing document content',
    'Extracting text data',
    'Processing images',
    'Analyzing tables',
    'Generating output files'
  ],
  redaction: [
    'Scanning for sensitive content',
    'Applying redactions',
    'Processing document',
    'Generating redacted file'
  ]
};

export const OperationProgressBar: React.FC<OperationProgressBarProps> = ({
  operationType,
  jobId,
  onComplete,
  onError,
  onCancel,
  className = '',
  showCancelButton = true,
  showTimeRemaining = true,
  showDetails = true
}) => {
  const [progress, setProgress] = useState<ProgressState>({
    percentage: 0,
    currentStep: OPERATION_STEPS[operationType]?.[0] || 'Initializing...',
    estimatedTimeRemaining: null,
    processingSpeed: null,
    dataProcessed: null,
    error: null,
    isCompleted: false,
    isCancelled: false,
    canCancel: true,
    results: null
  });

  const [startTime] = useState<number>(Date.now());
  const [lastUpdate, setLastUpdate] = useState<number>(Date.now());
  // Helper function to normalize job data from ProcessingJob
  const fromJob = useCallback((job: ProcessingJob) => {
    const now = Date.now();
    const elapsedTime = now - startTime;
    
    // Calculate processing speed
    let processingSpeed = null;
    if (job.progress > 0 && elapsedTime > 0) {
      const pagesPerSecond = (job.progress * 100) / (elapsedTime / 1000);
      processingSpeed = `${pagesPerSecond.toFixed(1)} items/sec`;
    }
    
    // Estimate time remaining
    let estimatedTimeRemaining = null;
    if (job.progress > 0 && job.progress < 100) {
      const remainingProgress = 100 - job.progress;
      const progressRate = job.progress / (elapsedTime / 1000);
      estimatedTimeRemaining = Math.round(remainingProgress / progressRate);
    }
    
    // Determine current step based on progress
    const steps = OPERATION_STEPS[operationType] || [];
    let currentStep = job.currentStep || steps[0] || 'Processing...';
    
    if (steps.length > 0 && !job.currentStep) {
      const stepIndex = Math.floor((job.progress / 100) * steps.length);
      currentStep = steps[Math.min(stepIndex, steps.length - 1)];
    }
    
    // Format data processed
    let dataProcessed = null;
    const result = job.result as any;
    if (result?.data_processed) {
      if (typeof result.data_processed === 'number') {
        dataProcessed = `${(result.data_processed / 1024 / 1024).toFixed(1)} MB`;
      } else {
        dataProcessed = result.data_processed;
      }
    }

    return {
      percentage: job.progress,
      currentStep,
      estimatedTimeRemaining,
      processingSpeed,
      dataProcessed,
      error: job.errorMessage || null,
      isCompleted: job.status === 'completed',
      isCancelled: job.status === 'cancelled',
      canCancel: job.status === 'running' || job.status === 'pending',
      results: job.result || null
    };
  }, [operationType, startTime]);

  const handleCancel = useCallback(async () => {
    if (!progress.canCancel) return;
    
    try {
      await PDFService.Job.cancelJob(jobId);
      PDFService.Job.stopPolling(jobId);
      setProgress(prev => ({
        ...prev,
        isCancelled: true,
        canCancel: false,
        currentStep: 'Cancelling operation...'
      }));
      
      if (onCancel) {
        onCancel();
      }
    } catch (error) {
      console.error('Error cancelling job:', error);
      setProgress(prev => ({
        ...prev,
        error: 'Failed to cancel operation'
      }));
    }
  }, [jobId, progress.canCancel, onCancel]);

  const formatTimeRemaining = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return `${minutes}m ${remainingSeconds}s`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return `${hours}h ${minutes}m`;
    }
  };

  const getProgressColor = () => {
    if (progress.error) return 'red';
    if (progress.isCancelled) return 'yellow';
    if (progress.isCompleted) return 'green';
    return OPERATION_COLORS[operationType];
  };

  // Start polling when component mounts
  useEffect(() => {
    PDFService.Job.pollJobStatus(
      jobId,
      (job: ProcessingJob) => {
        // Update progress during polling
        const progressData = fromJob(job);
        setProgress(prev => ({
          ...prev,
          ...progressData
        }));
        setLastUpdate(Date.now());
      },
      (job: ProcessingJob) => {
        // Job completed
        const progressData = fromJob(job);
        setProgress(prev => ({
          ...prev,
          ...progressData,
          isCompleted: true
        }));
        onComplete(job.result);
      },
      (err: any) => {
        // Job failed or error
        const errorMessage = err.message || 'Job processing failed';
        setProgress(prev => ({
          ...prev,
          error: errorMessage,
          canCancel: false
        }));
        if (onError) {
          onError(errorMessage);
        }
      }
    );
    
    return () => {
      // Stop polling on cleanup
      PDFService.Job.stopPolling(jobId);
    };
  }, [jobId, fromJob, onComplete, onError]);

  const progressColor = getProgressColor();
  const progressColorClass = {
    blue: 'bg-blue-600',
    green: 'bg-green-600',
    purple: 'bg-purple-600',
    red: 'bg-red-600',
    yellow: 'bg-yellow-600'
  }[progressColor];

  const backgroundColorClass = {
    blue: 'bg-blue-100',
    green: 'bg-green-100',
    purple: 'bg-purple-100',
    red: 'bg-red-100',
    yellow: 'bg-yellow-100'
  }[progressColor];

  return (
    <div className={`operation-progress-bar ${className}`}>
      <div className={`border rounded-lg p-4 ${backgroundColorClass}`}>
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2">
            <span className="text-lg">{OPERATION_ICONS[operationType]}</span>
            <span className="font-medium capitalize text-gray-800">
              {operationType} in Progress
            </span>
            {progress.isCancelled && (
              <span className="text-sm text-yellow-700 font-medium">(Cancelled)</span>
            )}
          </div>
          
          {showCancelButton && progress.canCancel && (
            <button
              onClick={handleCancel}
              className="text-sm px-3 py-1 border border-gray-300 rounded hover:bg-white text-gray-700"
            >
              Cancel
            </button>
          )}
        </div>

        {/* Progress Bar */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-sm mb-1">
            <span className="text-gray-700">{progress.currentStep}</span>
            <span className="font-medium text-gray-800">
              {Math.round(progress.percentage)}%
            </span>
          </div>
          
          <div className="w-full bg-gray-200 rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all duration-300 ${progressColorClass}`}
              style={{ width: `${Math.min(progress.percentage, 100)}%` }}
            >
              {/* Animated stripe effect for active progress */}
              {!progress.isCompleted && !progress.error && !progress.isCancelled && (
                <div className="h-full w-full rounded-full bg-gradient-to-r from-transparent via-white to-transparent opacity-30 animate-pulse"></div>
              )}
            </div>
          </div>
        </div>

        {/* Details */}
        {showDetails && (
          <div className="grid grid-cols-2 gap-4 text-sm text-gray-600">
            {showTimeRemaining && progress.estimatedTimeRemaining !== null && (
              <div>
                <span>Time remaining: </span>
                <span className="font-medium">
                  {formatTimeRemaining(progress.estimatedTimeRemaining)}
                </span>
              </div>
            )}
            
            {progress.processingSpeed && (
              <div>
                <span>Speed: </span>
                <span className="font-medium">{progress.processingSpeed}</span>
              </div>
            )}
            
            {progress.dataProcessed && (
              <div>
                <span>Processed: </span>
                <span className="font-medium">{progress.dataProcessed}</span>
              </div>
            )}
            
            <div>
              <span>Elapsed: </span>
              <span className="font-medium">
                {formatTimeRemaining(Math.floor((Date.now() - startTime) / 1000))}
              </span>
            </div>
          </div>
        )}

        {/* Error Display */}
        {progress.error && (
          <div className="mt-3 p-3 bg-red-100 border border-red-300 rounded text-sm text-red-700">
            <div className="font-medium">Error:</div>
            <div>{progress.error}</div>
          </div>
        )}

        {/* Success Message */}
        {progress.isCompleted && !progress.error && (
          <div className="mt-3 p-3 bg-green-100 border border-green-300 rounded text-sm text-green-700">
            <div className="font-medium">✓ Operation completed successfully!</div>
          </div>
        )}

        {/* Cancelled Message */}
        {progress.isCancelled && (
          <div className="mt-3 p-3 bg-yellow-100 border border-yellow-300 rounded text-sm text-yellow-700">
            <div className="font-medium">⚠ Operation was cancelled</div>
          </div>
        )}
      </div>
    </div>
  );
};