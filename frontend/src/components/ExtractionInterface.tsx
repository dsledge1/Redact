"use client";

import React, { useState, useCallback, useEffect } from 'react';
import { usePDFStore } from '../store/pdfStore';
import { PageRangeSelector } from './PageRangeSelector';
import { OperationProgressBar } from './OperationProgressBar';
import { ResultPreview } from './ResultPreview';
import { PDFService } from '../services/pdfService';
import { assessExtractionCapabilities, estimateExtractionSize, parsePageRanges } from '../utils/operationUtils';
import type { ExtractionType, ExtractionFormats, ExtractionOptions, ExtractionFormData, PageRange } from '../types';

export interface ExtractionInterfaceProps {
  documentRef?: React.RefObject<HTMLDivElement>;
  onExtractionComplete?: (results: any) => void;
  className?: string;
}

export const ExtractionInterface: React.FC<ExtractionInterfaceProps> = ({
  documentRef,
  onExtractionComplete,
  className = ''
}) => {
  const {
    currentFile,
    totalPages,
    extraction,
    setExtractionTypes,
    setExtractionFormats,
    setExtractionPageRange,
    initiateExtraction
  } = usePDFStore();

  const [selectedTypes, setSelectedTypes] = useState<ExtractionType[]>(['text']);
  const [extractionFormats, setExtractionFormatsLocal] = useState<ExtractionFormats>({
    text: 'plain',
    images: 'png',
    tables: 'csv',
    metadata: 'json'
  });
  const [pageRange, setPageRange] = useState<PageRange | null>(null);
  const [usePageRange, setUsePageRange] = useState<boolean>(false);
  const [pageRangeInput, setPageRangeInput] = useState<string>('');
  const [extractionOptions, setExtractionOptionsLocal] = useState<ExtractionOptions>({
    image_dpi: 300,
    table_detection_sensitivity: 'medium',
    ocr_confidence_threshold: 0.8,
    preserve_formatting: true,
    include_coordinates: false
  });
  const [capabilities, setCapabilities] = useState<any>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [previewData, setPreviewData] = useState<any>(null);

  // Available extraction types with descriptions
  const extractionTypeOptions = [
    {
      type: 'text' as ExtractionType,
      label: 'Text Content',
      description: 'Extract text content from the PDF',
      formats: [
        { value: 'plain', label: 'Plain Text' },
        { value: 'markdown', label: 'Markdown' },
        { value: 'html', label: 'HTML' }
      ]
    },
    {
      type: 'images' as ExtractionType,
      label: 'Images',
      description: 'Extract embedded images and graphics',
      formats: [
        { value: 'png', label: 'PNG' },
        { value: 'jpg', label: 'JPEG' },
        { value: 'webp', label: 'WebP' }
      ]
    },
    {
      type: 'tables' as ExtractionType,
      label: 'Tables',
      description: 'Extract and structure table data',
      formats: [
        { value: 'csv', label: 'CSV' },
        { value: 'json', label: 'JSON' },
        { value: 'xlsx', label: 'Excel' }
      ]
    },
    {
      type: 'metadata' as ExtractionType,
      label: 'Metadata',
      description: 'Extract document properties and metadata',
      formats: [
        { value: 'json', label: 'JSON' },
        { value: 'xml', label: 'XML' }
      ]
    },
    {
      type: 'forms' as ExtractionType,
      label: 'Form Fields',
      description: 'Extract form fields and their values',
      formats: [
        { value: 'json', label: 'JSON' },
        { value: 'csv', label: 'CSV' }
      ]
    }
  ];

  const handleTypeChange = useCallback((type: ExtractionType, checked: boolean) => {
    let updatedTypes: ExtractionType[];
    
    if (checked) {
      updatedTypes = [...selectedTypes, type];
    } else {
      updatedTypes = selectedTypes.filter(t => t !== type);
    }
    
    setSelectedTypes(updatedTypes);
    setExtractionTypes(updatedTypes);
    
    // Validate and generate preview
    validateAndPreview(updatedTypes, extractionFormats, pageRange);
  }, [selectedTypes, setExtractionTypes, extractionFormats, pageRange]);

  const handleFormatChange = useCallback((type: ExtractionType, format: string) => {
    const updatedFormats = {
      ...extractionFormats,
      [type]: format
    };
    
    setExtractionFormatsLocal(updatedFormats);
    setExtractionFormats(updatedFormats);
    
    validateAndPreview(selectedTypes, updatedFormats, pageRange);
  }, [extractionFormats, setExtractionFormats, selectedTypes, pageRange]);

  const handlePageRangeChange = useCallback((input: string) => {
    setPageRangeInput(input);
    
    if (!input.trim() || !usePageRange) {
      setPageRange(null);
      setExtractionPageRange(null);
      validateAndPreview(selectedTypes, extractionFormats, null);
      return;
    }
    
    try {
      const ranges = parsePageRanges(input);
      if (ranges.length > 0) {
        const combinedRange: PageRange = {
          start: Math.min(...ranges.map(r => r.start)),
          end: Math.max(...ranges.map(r => r.end))
        };
        setPageRange(combinedRange);
        setExtractionPageRange(combinedRange);
        validateAndPreview(selectedTypes, extractionFormats, combinedRange);
      }
    } catch (error) {
      setValidationErrors(['Invalid page range format. Use format like: 1-5, 8, 10-12']);
      setPageRange(null);
    }
  }, [usePageRange, setExtractionPageRange, selectedTypes, extractionFormats]);

  const handleOptionsChange = useCallback((newOptions: Partial<ExtractionOptions>) => {
    const updatedOptions = { ...extractionOptions, ...newOptions };
    setExtractionOptionsLocal(updatedOptions);
  }, [extractionOptions]);

  const validateAndPreview = useCallback((types: ExtractionType[], formats: ExtractionFormats, range: PageRange | null) => {
    const errors: string[] = [];
    
    if (types.length === 0) {
      errors.push('Please select at least one extraction type');
    }
    
    // Check capabilities against selected types
    if (capabilities) {
      if (types.includes('text') && !capabilities.hasTextLayer) {
        errors.push('Document may not have extractable text. OCR will be used.');
      }
      
      if (types.includes('images') && capabilities.imageCount === 0) {
        errors.push('No images detected in document');
      }
      
      if (types.includes('tables') && capabilities.tableCount === 0) {
        errors.push('No tables detected in document');
      }
      
      if (types.includes('forms') && capabilities.formFieldCount === 0) {
        errors.push('No form fields detected in document');
      }
    }
    
    // Separate warnings from blocking errors
    const warningMessages = errors.filter(e => e.includes('detected'));
    const blockingErrors = errors.filter(e => !e.includes('detected'));
    
    setValidationErrors(blockingErrors);
    setWarnings(warningMessages);
    
    if (types.length > 0) {
      const targetPages = range ? (range.end - range.start + 1) : totalPages;
      const estimatedData = capabilities ? {
        textLength: Math.round((capabilities.textLength || 0) * (targetPages / totalPages)),
        imageCount: Math.round((capabilities.imageCount || 0) * (targetPages / totalPages)),
        tableCount: Math.round((capabilities.tableCount || 0) * (targetPages / totalPages)),
        formFieldCount: Math.round((capabilities.formFieldCount || 0) * (targetPages / totalPages))
      } : {
        textLength: targetPages * 500, // Rough estimate
        imageCount: targetPages * 2,
        tableCount: targetPages * 1,
        formFieldCount: targetPages * 3
      };
      
      setPreviewData({
        extractionTypes: types,
        extractionFormats: formats,
        targetPages,
        estimatedData,
        capabilities: capabilities || {},
        warnings: errors.filter(e => e.includes('detected'))
      });
    } else {
      setPreviewData(null);
    }
  }, [capabilities, totalPages]);

  const handleStartExtraction = useCallback(async () => {
    if (!currentFile || selectedTypes.length === 0) {
      setValidationErrors(['Please select at least one extraction type']);
      return;
    }
    
    try {
      const formData: ExtractionFormData = {
        types: selectedTypes,
        formats: extractionFormats,
        page_range: pageRange,
        options: extractionOptions
      };
      
      await initiateExtraction(currentFile, formData);
    } catch (error) {
      console.error('Extraction initiation failed:', error);
      setValidationErrors(['Failed to start extraction operation. Please try again.']);
    }
  }, [currentFile, selectedTypes, extractionFormats, pageRange, extractionOptions, initiateExtraction]);

  // Assess document capabilities when file changes
  useEffect(() => {
    if (currentFile) {
      // This would typically analyze the PDF to determine capabilities
      // For now, we'll simulate capability assessment
      const simulatedCapabilities = {
        hasTextLayer: Math.random() > 0.3, // 70% chance of having text layer
        imageCount: Math.floor(Math.random() * 20),
        tableCount: Math.floor(Math.random() * 10),
        formFieldCount: Math.floor(Math.random() * 15),
        textLength: Math.floor(Math.random() * 10000) + 1000,
        hasBookmarks: Math.random() > 0.5,
        isScanned: Math.random() < 0.2 // 20% chance of being scanned
      };
      
      setCapabilities(simulatedCapabilities);
      validateAndPreview(selectedTypes, extractionFormats, pageRange);
    }
  }, [currentFile, selectedTypes, extractionFormats, pageRange]);

  useEffect(() => {
    if (extraction.results && onExtractionComplete) {
      onExtractionComplete(extraction.results);
    }
  }, [extraction.results, onExtractionComplete]);

  if (!currentFile) {
    return (
      <div className={`extraction-interface ${className}`}>
        <div className="text-center py-8 text-gray-500">
          Please upload a PDF file to begin extraction.
        </div>
      </div>
    );
  }

  return (
    <div className={`extraction-interface space-y-6 ${className}`}>
      {/* Document Capabilities Assessment */}
      {capabilities && (
        <div className="capabilities-assessment bg-blue-50 border border-blue-200 rounded-md p-4">
          <h4 className="font-medium mb-3 text-blue-800">Document Assessment</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="flex items-center">
              <span className={`inline-block w-2 h-2 rounded-full mr-2 ${
                capabilities.hasTextLayer ? 'bg-green-500' : 'bg-yellow-500'
              }`}></span>
              Text Layer: {capabilities.hasTextLayer ? 'Available' : 'OCR Required'}
            </div>
            <div className="flex items-center">
              <span className="text-gray-600">Images:</span>
              <span className="ml-2 font-medium">{capabilities.imageCount}</span>
            </div>
            <div className="flex items-center">
              <span className="text-gray-600">Tables:</span>
              <span className="ml-2 font-medium">{capabilities.tableCount}</span>
            </div>
            <div className="flex items-center">
              <span className="text-gray-600">Form Fields:</span>
              <span className="ml-2 font-medium">{capabilities.formFieldCount}</span>
            </div>
          </div>
        </div>
      )}

      {/* Extraction Type Selection */}
      <div className="extraction-types">
        <h3 className="text-lg font-semibold mb-4">Select Content to Extract</h3>
        <div className="space-y-4">
          {extractionTypeOptions.map(({ type, label, description, formats }) => (
            <div key={type} className="extraction-type-item border rounded-lg p-4">
              <div className="flex items-start space-x-3">
                <input
                  type="checkbox"
                  id={`type-${type}`}
                  checked={selectedTypes.includes(type)}
                  onChange={(e) => handleTypeChange(type, e.target.checked)}
                  className="mt-1"
                />
                <div className="flex-1">
                  <label htmlFor={`type-${type}`} className="font-medium cursor-pointer">
                    {label}
                  </label>
                  <div className="text-sm text-gray-600 mt-1">{description}</div>
                  
                  {selectedTypes.includes(type) && (
                    <div className="mt-3">
                      <label className="block text-sm font-medium mb-2">Output Format:</label>
                      <select
                        value={extractionFormats[type] || formats[0].value}
                        onChange={(e) => handleFormatChange(type, e.target.value)}
                        className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {formats.map(format => (
                          <option key={format.value} value={format.value}>
                            {format.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Page Range Selection */}
      <div className="page-range-section">
        <div className="flex items-center mb-3">
          <input
            type="checkbox"
            id="use-page-range"
            checked={usePageRange}
            onChange={(e) => setUsePageRange(e.target.checked)}
            className="mr-2"
          />
          <label htmlFor="use-page-range" className="font-medium">
            Extract from specific pages only
          </label>
        </div>
        
        {usePageRange && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Page Range (e.g., 1-5, 8, 10-12)
              </label>
              <input
                type="text"
                value={pageRangeInput}
                onChange={(e) => handlePageRangeChange(e.target.value)}
                placeholder="Enter page ranges..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {pageRange && (
              <PageRangeSelector
                totalPages={totalPages}
                selectedRanges={[pageRange]}
                onRangeChange={(ranges) => {
                  if (ranges.length > 0) {
                    const combined = {
                      start: Math.min(...ranges.map(r => r.start)),
                      end: Math.max(...ranges.map(r => r.end))
                    };
                    setPageRange(combined);
                    setExtractionPageRange(combined);
                  }
                }}
                documentRef={documentRef}
              />
            )}
          </div>
        )}
      </div>

      {/* Advanced Options */}
      {selectedTypes.length > 0 && (
        <div className="advanced-options">
          <h4 className="text-md font-medium mb-3">Advanced Options</h4>
          <div className="grid grid-cols-2 gap-4">
            {selectedTypes.includes('images') && (
              <div>
                <label className="block text-sm font-medium mb-2">Image DPI</label>
                <select
                  value={extractionOptions.image_dpi}
                  onChange={(e) => handleOptionsChange({ image_dpi: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value={150}>150 DPI (Low)</option>
                  <option value={300}>300 DPI (Standard)</option>
                  <option value={600}>600 DPI (High)</option>
                </select>
              </div>
            )}
            
            {selectedTypes.includes('tables') && (
              <div>
                <label className="block text-sm font-medium mb-2">Table Detection</label>
                <select
                  value={extractionOptions.table_detection_sensitivity}
                  onChange={(e) => handleOptionsChange({ 
                    table_detection_sensitivity: e.target.value as 'low' | 'medium' | 'high'
                  })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="low">Low Sensitivity</option>
                  <option value="medium">Medium Sensitivity</option>
                  <option value="high">High Sensitivity</option>
                </select>
              </div>
            )}
            
            <div className="col-span-2">
              <div className="space-y-3">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={extractionOptions.preserve_formatting}
                    onChange={(e) => handleOptionsChange({ preserve_formatting: e.target.checked })}
                    className="mr-2"
                  />
                  Preserve original formatting
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={extractionOptions.include_coordinates}
                    onChange={(e) => handleOptionsChange({ include_coordinates: e.target.checked })}
                    className="mr-2"
                  />
                  Include coordinate information
                </label>
              </div>
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

      {warnings.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
          <h4 className="text-yellow-800 font-medium mb-2">Warnings:</h4>
          <ul className="text-yellow-700 text-sm space-y-1">
            {warnings.map((warning, index) => (
              <li key={index}>• {warning}</li>
            ))}
          </ul>
          <p className="text-yellow-600 text-xs mt-2">
            These warnings won't prevent extraction but may result in limited output for the selected content types.
          </p>
        </div>
      )}

      {/* Extraction Preview */}
      {previewData && (
        <div className="bg-gray-50 border rounded-md p-4">
          <h4 className="font-medium mb-3">Extraction Preview</h4>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Target pages:</span>
                <span className="ml-2 font-medium">{previewData.targetPages}</span>
              </div>
              <div>
                <span className="text-gray-600">Content types:</span>
                <span className="ml-2 font-medium">{previewData.extractionTypes.length}</span>
              </div>
            </div>
            
            <div className="text-sm">
              <div className="font-medium mb-2">Estimated Content:</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {previewData.extractionTypes.includes('text') && (
                  <div>Text: ~{previewData.estimatedData.textLength} characters</div>
                )}
                {previewData.extractionTypes.includes('images') && (
                  <div>Images: ~{previewData.estimatedData.imageCount} items</div>
                )}
                {previewData.extractionTypes.includes('tables') && (
                  <div>Tables: ~{previewData.estimatedData.tableCount} items</div>
                )}
                {previewData.extractionTypes.includes('forms') && (
                  <div>Form Fields: ~{previewData.estimatedData.formFieldCount} items</div>
                )}
              </div>
            </div>
            
            {previewData.warnings.length > 0 && (
              <div className="text-sm text-yellow-700">
                <div className="font-medium">Warnings:</div>
                <ul className="list-disc list-inside">
                  {previewData.warnings.map((warning: string, index: number) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Action Button */}
      <div className="action-section">
        <button
          onClick={handleStartExtraction}
          disabled={!previewData || validationErrors.length > 0 || extraction.jobId !== undefined}
          className="w-full bg-purple-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {extraction.jobId ? 'Extracting...' : 'Start Extraction'}
        </button>
      </div>

      {/* Progress and Results */}
      {extraction.jobId && (
        <OperationProgressBar
          operationType="extraction"
          jobId={extraction.jobId}
          onComplete={() => {}}
        />
      )}

      {extraction.results && (
        <ResultPreview
          operationType="extraction"
          results={extraction.results}
          onDownload={() => {}}
        />
      )}
    </div>
  );
};