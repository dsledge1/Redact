"use client";

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { usePDFStore } from '../store/pdfStore';
import FileUpload from './FileUpload';
import { OperationProgressBar } from './OperationProgressBar';
import { ResultPreview } from './ResultPreview';
import { PDFService } from '../services/pdfService';
import { validateMergeFiles, calculateMergeSize, generateMergePreview } from '../utils/operationUtils';
import type { MergeOptions, MergeFormData, FileValidation } from '../types';

export interface MergeInterfaceProps {
  onMergeComplete?: (results: any) => void;
  className?: string;
}

interface MergeFile {
  id: string;
  file: File;
  preview?: string;
  pageCount?: number;
  isValid: boolean;
  error?: string;
}

export const MergeInterface: React.FC<MergeInterfaceProps> = ({
  onMergeComplete,
  className = ''
}) => {
  const {
    merging,
    addMergeFiles,
    removeMergeFile,
    reorderMergeFiles,
    setMergeOptions,
    initiateMerge
  } = usePDFStore();

  const [files, setFiles] = useState<MergeFile[]>([]);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [mergeOptions, setMergeOptionsLocal] = useState<MergeOptions>({
    preserve_bookmarks: true,
    preserve_metadata: true,
    bookmark_strategy: 'merge_top_level'
  });
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [previewData, setPreviewData] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFilesSelected = useCallback(async (selectedFiles: File[]) => {
    const newFiles: MergeFile[] = [];
    
    for (const file of selectedFiles) {
      const id = `${file.name}-${Date.now()}-${Math.random()}`;
      const mergeFile: MergeFile = {
        id,
        file,
        isValid: file.type === 'application/pdf',
        error: file.type !== 'application/pdf' ? 'Only PDF files are supported' : undefined
      };
      
      // Generate preview and get page count
      if (mergeFile.isValid) {
        try {
          // This would typically use a PDF library to get page count
          // For now, we'll estimate based on file size
          const estimatedPages = Math.max(1, Math.round(file.size / 50000)); // Rough estimate
          mergeFile.pageCount = estimatedPages;
        } catch (error) {
          mergeFile.isValid = false;
          mergeFile.error = 'Failed to read PDF file';
        }
      }
      
      newFiles.push(mergeFile);
    }
    
    const updatedFiles = [...files, ...newFiles];
    setFiles(updatedFiles);
    addMergeFiles(newFiles.map(f => f.file));
    
    // Validate and generate preview
    validateAndPreview(updatedFiles);
  }, [files, addMergeFiles]);

  const validateAndPreview = useCallback((filesToValidate: MergeFile[]) => {
    const validFiles = filesToValidate.filter(f => f.isValid);
    const errors: string[] = [];
    
    if (validFiles.length < 2) {
      errors.push('At least 2 PDF files are required for merging');
    }
    
    if (validFiles.length > 100) {
      errors.push('Maximum 100 files can be merged at once');
    }
    
    const totalSize = validFiles.reduce((sum, f) => sum + f.file.size, 0);
    if (totalSize > 100 * 1024 * 1024) { // 100MB limit
      errors.push('Total file size cannot exceed 100MB');
    }
    
    const invalidFiles = filesToValidate.filter(f => !f.isValid);
    if (invalidFiles.length > 0) {
      errors.push(`${invalidFiles.length} invalid file(s) found`);
    }
    
    setValidationErrors(errors);
    
    if (errors.length === 0 && validFiles.length >= 2) {
      const totalPages = validFiles.reduce((sum, f) => sum + (f.pageCount || 0), 0);
      setPreviewData({
        fileCount: validFiles.length,
        totalPages,
        estimatedSize: totalSize,
        bookmarkStrategy: mergeOptions.bookmark_strategy,
        preserveMetadata: mergeOptions.preserve_metadata,
        preserveBookmarks: mergeOptions.preserve_bookmarks
      });
    } else {
      setPreviewData(null);
    }
  }, [mergeOptions]);

  const handleRemoveFile = useCallback((fileId: string) => {
    const updatedFiles = files.filter(f => f.id !== fileId);
    setFiles(updatedFiles);
    
    const fileToRemove = files.find(f => f.id === fileId);
    if (fileToRemove) {
      removeMergeFile(fileToRemove.file);
    }
    
    validateAndPreview(updatedFiles);
  }, [files, removeMergeFile]);

  const handleDragStart = useCallback((index: number) => {
    setDraggedIndex(index);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    
    if (draggedIndex === null || draggedIndex === dropIndex) return;
    
    const reorderedFiles = [...files];
    const draggedFile = reorderedFiles[draggedIndex];
    reorderedFiles.splice(draggedIndex, 1);
    reorderedFiles.splice(dropIndex, 0, draggedFile);
    
    setFiles(reorderedFiles);
    setDraggedIndex(null);
    
    const fileOrder = reorderedFiles.map(f => f.id);
    reorderMergeFiles(fileOrder);
    validateAndPreview(reorderedFiles);
  }, [files, draggedIndex, reorderMergeFiles]);

  const handleOptionsChange = useCallback((newOptions: Partial<MergeOptions>) => {
    const updatedOptions = { ...mergeOptions, ...newOptions };
    setMergeOptionsLocal(updatedOptions);
    setMergeOptions(updatedOptions);
    validateAndPreview(files);
  }, [mergeOptions, setMergeOptions, files]);

  const handleStartMerge = useCallback(async () => {
    const validFiles = files.filter(f => f.isValid);
    if (validFiles.length < 2) {
      setValidationErrors(['At least 2 valid PDF files are required']);
      return;
    }
    
    try {
      const formData: MergeFormData = {
        files: validFiles.map(f => f.file),
        options: mergeOptions
      };
      
      await initiateMerge(formData);
    } catch (error) {
      console.error('Merge initiation failed:', error);
      setValidationErrors(['Failed to start merge operation. Please try again.']);
    }
  }, [files, mergeOptions, initiateMerge]);

  const moveFileUp = useCallback((index: number) => {
    if (index <= 0) return;
    const reorderedFiles = [...files];
    [reorderedFiles[index - 1], reorderedFiles[index]] = [reorderedFiles[index], reorderedFiles[index - 1]];
    setFiles(reorderedFiles);
    validateAndPreview(reorderedFiles);
  }, [files]);

  const moveFileDown = useCallback((index: number) => {
    if (index >= files.length - 1) return;
    const reorderedFiles = [...files];
    [reorderedFiles[index], reorderedFiles[index + 1]] = [reorderedFiles[index + 1], reorderedFiles[index]];
    setFiles(reorderedFiles);
    validateAndPreview(reorderedFiles);
  }, [files]);

  useEffect(() => {
    if (merging.results && onMergeComplete) {
      onMergeComplete(merging.results);
    }
  }, [merging.results, onMergeComplete]);

  return (
    <div className={`merge-interface space-y-6 ${className}`}>
      {/* File Upload Section */}
      <div className="file-upload-section">
        <h3 className="text-lg font-semibold mb-4">Select PDF Files to Merge</h3>
        <FileUpload
          accept=".pdf"
          multiple={true}
          onFilesSelected={handleFilesSelected}
          maxFiles={100}
          className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center"
        />
        <div className="mt-2 text-sm text-gray-600">
          Select multiple PDF files (max 100 files, 100MB total)
        </div>
      </div>

      {/* File List and Reordering */}
      {files.length > 0 && (
        <div className="file-list">
          <h4 className="text-md font-medium mb-3">
            Files to Merge ({files.length})
          </h4>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {files.map((mergeFile, index) => (
              <div
                key={mergeFile.id}
                draggable
                onDragStart={() => handleDragStart(index)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, index)}
                className={`file-item p-4 border rounded-lg bg-white ${
                  mergeFile.isValid
                    ? 'border-gray-200 hover:border-gray-300'
                    : 'border-red-200 bg-red-50'
                } cursor-move`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="drag-handle text-gray-400">
                      ⋮⋮
                    </div>
                    <div className="file-info flex-1">
                      <div className="font-medium text-sm">
                        {index + 1}. {mergeFile.file.name}
                      </div>
                      <div className="text-xs text-gray-600">
                        {Math.round(mergeFile.file.size / 1024)} KB
                        {mergeFile.pageCount && ` • ${mergeFile.pageCount} pages`}
                      </div>
                      {mergeFile.error && (
                        <div className="text-xs text-red-600 mt-1">
                          {mergeFile.error}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => moveFileUp(index)}
                      disabled={index === 0}
                      className="text-gray-400 hover:text-gray-600 disabled:opacity-30"
                      title="Move up"
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => moveFileDown(index)}
                      disabled={index === files.length - 1}
                      className="text-gray-400 hover:text-gray-600 disabled:opacity-30"
                      title="Move down"
                    >
                      ↓
                    </button>
                    <button
                      onClick={() => handleRemoveFile(mergeFile.id)}
                      className="text-red-400 hover:text-red-600 ml-2"
                      title="Remove file"
                    >
                      ×
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-gray-500 mt-2">
            Drag files to reorder • Files will be merged in the order shown
          </div>
        </div>
      )}

      {/* Merge Options */}
      {files.length > 0 && (
        <div className="merge-options">
          <h4 className="text-md font-medium mb-3">Merge Options</h4>
          <div className="space-y-3">
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={mergeOptions.preserve_metadata}
                onChange={(e) => handleOptionsChange({ preserve_metadata: e.target.checked })}
                className="mr-2"
              />
              Preserve document metadata
            </label>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={mergeOptions.preserve_bookmarks}
                onChange={(e) => handleOptionsChange({ preserve_bookmarks: e.target.checked })}
                className="mr-2"
              />
              Preserve bookmarks
            </label>
            <div>
              <label className="block text-sm font-medium mb-2">
                Bookmark Strategy
              </label>
              <select
                value={mergeOptions.bookmark_strategy}
                onChange={(e) => handleOptionsChange({ 
                  bookmark_strategy: e.target.value as MergeOptions['bookmark_strategy']
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="merge_top_level">Merge at top level</option>
                <option value="preserve_all">Preserve all bookmarks</option>
                <option value="create_new">Create new bookmarks for each file</option>
                <option value="none">Remove all bookmarks</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <h4 className="text-red-800 font-medium mb-2">Validation Errors:</h4>
          <ul className="text-red-700 text-sm space-y-1">
            {validationErrors.map((error, index) => (
              <li key={index}>• {error}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Merge Preview */}
      {previewData && (
        <div className="bg-gray-50 border rounded-md p-4">
          <h4 className="font-medium mb-3">Merge Preview</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-600">Files to merge:</span>
              <span className="ml-2 font-medium">{previewData.fileCount}</span>
            </div>
            <div>
              <span className="text-gray-600">Total pages:</span>
              <span className="ml-2 font-medium">{previewData.totalPages}</span>
            </div>
            <div>
              <span className="text-gray-600">Estimated size:</span>
              <span className="ml-2 font-medium">
                {Math.round(previewData.estimatedSize / 1024)} KB
              </span>
            </div>
            <div>
              <span className="text-gray-600">Bookmark strategy:</span>
              <span className="ml-2 font-medium">
                {previewData.bookmarkStrategy.replace('_', ' ')}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Action Button */}
      <div className="action-section">
        <button
          onClick={handleStartMerge}
          disabled={!previewData || validationErrors.length > 0 || merging.jobId !== undefined}
          className="w-full bg-green-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {merging.jobId ? 'Merging...' : 'Start Merge'}
        </button>
      </div>

      {/* Progress and Results */}
      {merging.jobId && (
        <OperationProgressBar
          operationType="merging"
          jobId={merging.jobId}
          onComplete={() => {}}
        />
      )}

      {merging.results && (
        <ResultPreview
          operationType="merging"
          results={merging.results}
          onDownload={() => {}}
        />
      )}
    </div>
  );
};