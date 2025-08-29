'use client';

import { useCallback, useMemo, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import clsx from 'clsx';

import type { FileUploadProps, APIError, UploadProgress } from '@/types';
import { validateFile, formatBytes, createFilePreview } from '@/utils/fileUtils';
import { useUpload, useUploadActions } from '@/store';
import ProgressBar from './ProgressBar';
import LoadingSpinner from './LoadingSpinner';

const FileUpload = ({
  onFileUploaded,
  onFilesUploaded,
  onError,
  onProgress,
  accept = 'application/pdf',
  maxSize = 104857600, // 100MB
  multiple = false,
  disabled = false,
  className,
  ...props
}: FileUploadProps): JSX.Element => {
  const [dragActive, setDragActive] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  
  const upload = useUpload();
  const { uploadFile, cancelUpload, clearUploadError } = useUploadActions();

  // Convert accept string to dropzone format
  const computedAccept = useMemo(() => {
    if (!accept) {
      return { 'application/pdf': ['.pdf'] };
    }
    // If it's already an object, use as-is
    if (typeof accept === 'object') {
      return accept;
    }
    // Convert string to object (basic support for MIME types)
    if (accept === 'application/pdf') {
      return { 'application/pdf': ['.pdf'] };
    }
    // For other string formats, try to parse
    const mimeTypes: Record<string, string[]> = {};
    const types = accept.split(',').map(s => s.trim());
    types.forEach(type => {
      if (type.startsWith('.')) {
        // File extension
        mimeTypes['*/*'] = mimeTypes['*/*'] || [];
        mimeTypes['*/*'].push(type);
      } else {
        // MIME type
        mimeTypes[type] = mimeTypes[type] || [];
      }
    });
    return Object.keys(mimeTypes).length > 0 ? mimeTypes : { 'application/pdf': ['.pdf'] };
  }, [accept]);

  const onDrop = useCallback(async (acceptedFiles: File[], rejectedFiles: any[]) => {
    setDragActive(false);

    // Handle rejected files
    if (rejectedFiles.length > 0) {
      const errors = rejectedFiles.flatMap((rejected: any) => 
        rejected.errors.map((error: any) => ({
          code: error.code,
          message: error.message,
          field: 'file',
          timestamp: new Date().toISOString(),
        }))
      );

      if (errors.length > 0) {
        onError(errors[0]);
        return;
      }
    }

    if (acceptedFiles.length === 0) return;

    // Handle multiple files
    if (multiple && acceptedFiles.length > 1) {
      // Validate all files
      for (const f of acceptedFiles) {
        const validation = validateFile(f);
        if (!validation.isValid) {
          onError(validation.errors[0]);
          return;
        }
      }
      
      // Call the multiple files handler
      onFilesUploaded?.(acceptedFiles);
      
      // For now, still upload the first file
      // TODO: Consider implementing batch upload in store
      const file = acceptedFiles[0];
      try {
        await uploadFile(file, (progress: UploadProgress) => {
          onProgress?.(progress);
        });
        onFileUploaded?.(file);
      } catch (error) {
        const uploadError: APIError = {
          code: 'UPLOAD_FAILED',
          message: error instanceof Error ? error.message : 'Upload failed',
          timestamp: new Date().toISOString(),
        };
        onError(uploadError);
      }
    } else {
      // Single file handling
      const file = acceptedFiles[0];
      
      // Validate file
      const validation = validateFile(file);
      if (!validation.isValid) {
        onError(validation.errors[0]);
        return;
      }

      // Create preview
      try {
        const preview = await createFilePreview(file);
        setPreviewUrl(preview);
      } catch (error) {
        console.warn('Failed to create file preview:', error);
      }

      // Start upload
      try {
        await uploadFile(file, (progress: UploadProgress) => {
          onProgress?.(progress);
        });
        
        onFileUploaded?.(file);
      } catch (error) {
        const uploadError: APIError = {
          code: 'UPLOAD_FAILED',
          message: error instanceof Error ? error.message : 'Upload failed',
          timestamp: new Date().toISOString(),
        };
        onError(uploadError);
      }
    }
  }, [uploadFile, onFileUploaded, onFilesUploaded, onError, onProgress, multiple]);

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    onDragEnter: () => setDragActive(true),
    onDragLeave: () => setDragActive(false),
    accept: computedAccept,
    maxSize,
    multiple,
    disabled: disabled || upload.isUploading,
  });

  const dropzoneClasses = useMemo(() => {
    return clsx(
      'dropzone relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-all duration-300',
      {
        // Base styles
        'border-gray-300 bg-gray-50/50': !isDragActive && !isDragReject && !upload.error,
        'hover:border-primary-400 hover:bg-primary-50/50': !disabled && !upload.isUploading,
        
        // Active drag states
        'border-primary-500 bg-primary-50': isDragActive && !isDragReject,
        'border-red-500 bg-red-50': isDragReject,
        
        // Upload states
        'border-blue-400 bg-blue-50': upload.isUploading,
        'border-red-400 bg-red-50': upload.error,
        
        // Disabled state
        'opacity-50 cursor-not-allowed': disabled,
        'cursor-pointer': !disabled && !upload.isUploading,
      },
      className
    );
  }, [isDragActive, isDragReject, disabled, upload.isUploading, upload.error, className]);

  const handleCancelUpload = useCallback(() => {
    cancelUpload();
    setPreviewUrl(null);
  }, [cancelUpload]);

  const handleRetry = useCallback(() => {
    clearUploadError();
    setPreviewUrl(null);
  }, [clearUploadError]);

  return (
    <div {...props}>
      <div {...getRootProps()} className={dropzoneClasses}>
        <input {...getInputProps()} />
        
        {upload.isUploading ? (
          <UploadingContent 
            progress={upload.progress}
            onCancel={handleCancelUpload}
          />
        ) : upload.error ? (
          <ErrorContent 
            error={upload.error}
            onRetry={handleRetry}
          />
        ) : (
          <IdleContent 
            isDragActive={isDragActive}
            isDragReject={isDragReject}
            accept={accept}
            maxSize={maxSize}
            previewUrl={previewUrl}
          />
        )}
      </div>

      {/* Upload Progress Details */}
      {upload.isUploading && upload.progress && (
        <div className="mt-4 space-y-2">
          <ProgressBar
            progress={upload.progress.percentage}
            label="Uploading PDF..."
            showPercentage={true}
            variant="default"
          />
          <div className="flex justify-between text-sm text-gray-500">
            <span>{formatBytes(upload.progress.loaded)} / {formatBytes(upload.progress.total)}</span>
            {upload.progress.speed && (
              <span>{formatBytes(upload.progress.speed)}/s</span>
            )}
          </div>
        </div>
      )}

      {/* Validation Warnings */}
      {upload.error && (
        <div className="mt-4 rounded-lg bg-red-50 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Upload Error</h3>
              <div className="mt-2 text-sm text-red-700">
                {upload.error.message}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * Content shown when upload is idle/ready
 */
const IdleContent = ({ 
  isDragActive, 
  isDragReject, 
  accept, 
  maxSize,
  previewUrl 
}: {
  isDragActive: boolean;
  isDragReject: boolean;
  accept: string;
  maxSize: number;
  previewUrl: string | null;
}) => {
  if (isDragReject) {
    return (
      <>
        <svg
          className="mx-auto h-16 w-16 text-red-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
        <h3 className="mt-4 text-lg font-semibold text-red-900">Invalid File Type</h3>
        <p className="mt-2 text-sm text-red-700">
          Only PDF files are supported. Please select a valid PDF file.
        </p>
      </>
    );
  }

  if (isDragActive) {
    return (
      <>
        <svg
          className="mx-auto h-16 w-16 text-primary-400 animate-bounce"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"
          />
        </svg>
        <h3 className="mt-4 text-lg font-semibold text-primary-900">Drop PDF Here</h3>
        <p className="mt-2 text-sm text-primary-700">
          Release to upload your PDF file
        </p>
      </>
    );
  }

  return (
    <>
      {previewUrl ? (
        <div className="flex flex-col items-center space-y-4">
          <img
            src={previewUrl}
            alt="PDF Preview"
            className="h-24 w-20 rounded border object-cover shadow-sm"
          />
          <p className="text-sm font-medium text-green-700">
            Ready to upload! Click or drag another file to replace.
          </p>
        </div>
      ) : (
        <>
          <svg
            className="mx-auto h-16 w-16 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <h3 className="mt-4 text-lg font-semibold text-gray-900">
            Upload a PDF File
          </h3>
          <p className="mt-2 text-sm text-gray-600">
            Drag and drop your PDF file here, or{' '}
            <span className="font-medium text-primary-600">click to browse</span>
          </p>
          <div className="mt-4 space-y-1 text-xs text-gray-500">
            <p>Supported format: PDF</p>
            <p>Maximum file size: {formatBytes(maxSize)}</p>
          </div>
        </>
      )}
    </>
  );
};

/**
 * Content shown during upload
 */
const UploadingContent = ({ 
  progress, 
  onCancel 
}: {
  progress: UploadProgress | null;
  onCancel: () => void;
}) => (
  <>
    <LoadingSpinner size="lg" variant="primary" />
    <h3 className="mt-4 text-lg font-semibold text-gray-900">
      Uploading PDF...
    </h3>
    <p className="mt-2 text-sm text-gray-600">
      {progress ? `${progress.percentage.toFixed(0)}% complete` : 'Please wait...'}
    </p>
    <button
      type="button"
      onClick={onCancel}
      className="mt-4 text-sm font-medium text-red-600 hover:text-red-700"
    >
      Cancel Upload
    </button>
  </>
);

/**
 * Content shown when there's an error
 */
const ErrorContent = ({ 
  error, 
  onRetry 
}: {
  error: APIError;
  onRetry: () => void;
}) => (
  <>
    <svg
      className="mx-auto h-16 w-16 text-red-400"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
      />
    </svg>
    <h3 className="mt-4 text-lg font-semibold text-red-900">Upload Failed</h3>
    <p className="mt-2 text-sm text-red-700">{error.message}</p>
    <button
      type="button"
      onClick={onRetry}
      className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
    >
      Try Again
    </button>
  </>
);

export default FileUpload;