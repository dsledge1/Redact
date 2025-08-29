"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { usePDFStore } from '../store/pdfStore';
import { PageRangeSelector } from './PageRangeSelector';
import { OperationProgressBar } from './OperationProgressBar';
import { ResultPreview } from './ResultPreview';
import { PDFService } from '../services/pdfService';
import { parsePageRanges, validatePageRanges, formatPageRanges } from '../utils/operationUtils';
import type { SplitMethod, PageRange, SplitOptions, SplitFormData } from '../types';

export interface SplitInterfaceProps {
  documentRef?: React.RefObject<HTMLDivElement>;
  onSplitComplete?: (results: any) => void;
  className?: string;
}

export const SplitInterface: React.FC<SplitInterfaceProps> = ({
  documentRef,
  onSplitComplete,
  className = ''
}) => {
  const {
    currentFile,
    totalPages,
    splitting,
    setSplitMethod,
    setSplitPageRanges,
    setSplitOptions,
    initiateSplit
  } = usePDFStore();

  const [splitMethod, setSplitMethodLocal] = useState<SplitMethod>('page_ranges');
  const [pageRanges, setPageRanges] = useState<PageRange[]>([]);
  const [pageRangeInput, setPageRangeInput] = useState<string>('');
  const [pageCount, setPageCount] = useState<number>(1);
  const [pattern, setPattern] = useState<string>('');
  const [splitOptions, setSplitOptionsLocal] = useState<SplitOptions>({
    preserve_metadata: true,
    preserve_bookmarks: true,
    custom_naming: false,
    naming_pattern: 'page_{start}-{end}'
  });
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [previewData, setPreviewData] = useState<any>(null);

  const handleMethodChange = useCallback((method: SplitMethod) => {
    setSplitMethodLocal(method);
    setSplitMethod(method);
    setValidationErrors([]);
    setPreviewData(null);
  }, [setSplitMethod]);

  const handlePageRangeChange = useCallback((input: string) => {
    setPageRangeInput(input);
    try {
      const ranges = parsePageRanges(input);
      const validation = validatePageRanges(ranges, totalPages);
      
      if (validation.isValid) {
        setPageRanges(ranges);
        setSplitPageRanges(ranges);
        setValidationErrors([]);
        generatePreview(ranges, splitMethod);
      } else {
        setValidationErrors(validation.errors);
        setPageRanges([]);
        setPreviewData(null);
      }
    } catch (error) {
      setValidationErrors(['Invalid page range format. Use format like: 1-5, 8, 10-12']);
      setPageRanges([]);
      setPreviewData(null);
    }
  }, [totalPages, setSplitPageRanges, splitMethod]);

  const handlePageRangeSelection = useCallback((ranges: PageRange[]) => {
    setPageRanges(ranges);
    setSplitPageRanges(ranges);
    setPageRangeInput(formatPageRanges(ranges));
    generatePreview(ranges, splitMethod);
  }, [setSplitPageRanges, splitMethod]);

  const handleOptionsChange = useCallback((newOptions: Partial<SplitOptions>) => {
    const updatedOptions = { ...splitOptions, ...newOptions };
    setSplitOptionsLocal(updatedOptions);
    setSplitOptions(updatedOptions);
  }, [splitOptions, setSplitOptions]);

  const generatePreview = useCallback((ranges: PageRange[], method: SplitMethod) => {
    if (!ranges.length && method === 'page_ranges') return;

    const estimatedFiles = method === 'page_ranges' 
      ? ranges.length
      : method === 'page_count'
      ? Math.ceil(totalPages / pageCount)
      : method === 'bookmarks'
      ? 1 // Would be calculated from actual bookmarks
      : 1;

    setPreviewData({
      estimatedFiles,
      totalPages: totalPages,
      estimatedSizePerFile: currentFile ? Math.ceil(currentFile.size / estimatedFiles) : 0,
      outputFormat: 'PDF',
      preserveBookmarks: splitOptions.preserve_bookmarks,
      preserveMetadata: splitOptions.preserve_metadata
    });
  }, [totalPages, pageCount, currentFile, splitOptions]);

  const handleStartSplit = useCallback(async () => {
    if (!currentFile) return;

    try {
      let formData: SplitFormData;

      switch (splitMethod) {
        case 'page_ranges':
          if (!pageRanges.length) {
            setValidationErrors(['Please select page ranges to split']);
            return;
          }
          formData = {
            method: 'page_ranges',
            page_ranges: pageRanges,
            options: splitOptions
          };
          break;
        case 'page_count':
          formData = {
            method: 'page_count',
            pages_per_split: pageCount,
            options: splitOptions
          };
          break;
        case 'bookmarks':
          formData = {
            method: 'bookmarks',
            bookmark_level: 1,
            options: splitOptions
          };
          break;
        case 'pattern':
          formData = {
            method: 'pattern',
            pattern: pattern,
            options: splitOptions
          };
          break;
        default:
          throw new Error('Invalid split method');
      }

      await initiateSplit(currentFile, formData);
    } catch (error) {
      console.error('Split initiation failed:', error);
      setValidationErrors(['Failed to start split operation. Please try again.']);
    }
  }, [currentFile, splitMethod, pageRanges, pageCount, pattern, splitOptions, initiateSplit]);

  useEffect(() => {
    if (splitting.results && onSplitComplete) {
      onSplitComplete(splitting.results);
    }
  }, [splitting.results, onSplitComplete]);

  if (!currentFile) {
    return (
      <div className={`split-interface ${className}`}>
        <div className="text-center py-8 text-gray-500">
          Please upload a PDF file to begin splitting.
        </div>
      </div>
    );
  }

  return (
    <div className={`split-interface space-y-6 ${className}`}>
      {/* Split Method Selection */}
      <div className="method-selection">
        <h3 className="text-lg font-semibold mb-4">Split Method</h3>
        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => handleMethodChange('page_ranges')}
            className={`p-4 border rounded-lg text-left ${
              splitMethod === 'page_ranges'
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
          >
            <div className="font-medium">Page Ranges</div>
            <div className="text-sm text-gray-600">Split by specific page ranges</div>
          </button>
          <button
            onClick={() => handleMethodChange('page_count')}
            className={`p-4 border rounded-lg text-left ${
              splitMethod === 'page_count'
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
          >
            <div className="font-medium">Page Count</div>
            <div className="text-sm text-gray-600">Split by number of pages</div>
          </button>
          <button
            onClick={() => handleMethodChange('bookmarks')}
            className={`p-4 border rounded-lg text-left ${
              splitMethod === 'bookmarks'
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
          >
            <div className="font-medium">Bookmarks</div>
            <div className="text-sm text-gray-600">Split by bookmark structure</div>
          </button>
          <button
            onClick={() => handleMethodChange('pattern')}
            className={`p-4 border rounded-lg text-left ${
              splitMethod === 'pattern'
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
          >
            <div className="font-medium">Pattern</div>
            <div className="text-sm text-gray-600">Split by text pattern</div>
          </button>
        </div>
      </div>

      {/* Split Configuration */}
      <div className="split-config">
        {splitMethod === 'page_ranges' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Page Ranges (e.g., 1-5, 8, 10-12)
              </label>
              <input
                type="text"
                value={pageRangeInput}
                onChange={(e) => handlePageRangeChange(e.target.value)}
                placeholder="Enter page ranges..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <PageRangeSelector
              totalPages={totalPages}
              selectedRanges={pageRanges}
              onRangeChange={handlePageRangeSelection}
              documentRef={documentRef}
            />
          </div>
        )}

        {splitMethod === 'page_count' && (
          <div>
            <label className="block text-sm font-medium mb-2">
              Pages per Split
            </label>
            <input
              type="number"
              value={pageCount}
              onChange={(e) => setPageCount(Math.max(1, parseInt(e.target.value) || 1))}
              min="1"
              max={totalPages}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        )}

        {splitMethod === 'bookmarks' && (
          <div className="text-sm text-gray-600">
            Split will be performed based on the document's bookmark structure.
          </div>
        )}

        {splitMethod === 'pattern' && (
          <div>
            <label className="block text-sm font-medium mb-2">
              Text Pattern
            </label>
            <input
              type="text"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="Enter text pattern to split on..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        )}
      </div>

      {/* Split Options */}
      <div className="split-options">
        <h4 className="text-md font-medium mb-3">Split Options</h4>
        <div className="space-y-3">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={splitOptions.preserve_metadata}
              onChange={(e) => handleOptionsChange({ preserve_metadata: e.target.checked })}
              className="mr-2"
            />
            Preserve document metadata
          </label>
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={splitOptions.preserve_bookmarks}
              onChange={(e) => handleOptionsChange({ preserve_bookmarks: e.target.checked })}
              className="mr-2"
            />
            Preserve bookmarks
          </label>
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={splitOptions.custom_naming}
              onChange={(e) => handleOptionsChange({ custom_naming: e.target.checked })}
              className="mr-2"
            />
            Use custom file naming
          </label>
          {splitOptions.custom_naming && (
            <div className="ml-6">
              <input
                type="text"
                value={splitOptions.naming_pattern}
                onChange={(e) => handleOptionsChange({ naming_pattern: e.target.value })}
                placeholder="e.g., page_{start}-{end}"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}
        </div>
      </div>

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

      {/* Split Preview */}
      {previewData && (
        <div className="bg-gray-50 border rounded-md p-4">
          <h4 className="font-medium mb-3">Split Preview</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-600">Estimated files:</span>
              <span className="ml-2 font-medium">{previewData.estimatedFiles}</span>
            </div>
            <div>
              <span className="text-gray-600">Total pages:</span>
              <span className="ml-2 font-medium">{previewData.totalPages}</span>
            </div>
            <div>
              <span className="text-gray-600">Avg. size per file:</span>
              <span className="ml-2 font-medium">
                {Math.round(previewData.estimatedSizePerFile / 1024)} KB
              </span>
            </div>
            <div>
              <span className="text-gray-600">Output format:</span>
              <span className="ml-2 font-medium">{previewData.outputFormat}</span>
            </div>
          </div>
        </div>
      )}

      {/* Action Button */}
      <div className="action-section">
        <button
          onClick={handleStartSplit}
          disabled={!previewData || validationErrors.length > 0 || splitting.jobId !== undefined}
          className="w-full bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {splitting.jobId ? 'Splitting...' : 'Start Split'}
        </button>
      </div>

      {/* Progress and Results */}
      {splitting.jobId && (
        <OperationProgressBar
          operationType="splitting"
          jobId={splitting.jobId}
          onComplete={() => {}}
        />
      )}

      {splitting.results && (
        <ResultPreview
          operationType="splitting"
          results={splitting.results}
          onDownload={() => {}}
        />
      )}
    </div>
  );
};