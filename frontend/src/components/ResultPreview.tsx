"use client";

import React, { useState, useCallback, useEffect } from 'react';
import type { ProcessingOperation, SplitInfo, MergeInfo, ExtractedData, RedactionResults } from '../types';

export interface ResultPreviewProps {
  operationType: ProcessingOperation;
  results: any;
  onDownload?: (fileId?: string) => void;
  onDownloadAll?: () => void;
  className?: string;
  showStatistics?: boolean;
}

interface FilePreview {
  id: string;
  name: string;
  size: number;
  type: string;
  downloadUrl: string;
  thumbnail?: string;
  pageCount?: number;
  description?: string;
}

interface ExtractionPreview {
  type: string;
  format: string;
  content: any;
  size: number;
  downloadUrl: string;
  preview?: string;
}

const OPERATION_ICONS = {
  splitting: '✂️',
  merging: '📋',
  extraction: '📤',
  redaction: '🖍️'
};

export const ResultPreview: React.FC<ResultPreviewProps> = ({
  operationType,
  results,
  onDownload,
  onDownloadAll,
  className = '',
  showStatistics = true
}) => {
  const [activeTab, setActiveTab] = useState<string>('files');
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [previewContent, setPreviewContent] = useState<{ [key: string]: any }>({});

  const toggleExpanded = useCallback((itemId: string) => {
    setExpandedItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  }, []);

  const formatFileSize = useCallback((bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  }, []);

  const handleDownload = useCallback((fileId?: string) => {
    if (onDownload) {
      onDownload(fileId);
    }
  }, [onDownload]);

  const handleDownloadAll = useCallback(() => {
    if (onDownloadAll) {
      onDownloadAll();
    }
  }, [onDownloadAll]);

  const renderSplitResults = () => {
    const splitResults = results as SplitInfo;
    const files: FilePreview[] = splitResults.files.map((file, index) => ({
      id: `split-${index}`,
      name: file.filename,
      size: file.size,
      type: 'application/pdf',
      downloadUrl: file.download_url,
      pageCount: file.page_range ? (file.page_range.end - file.page_range.start + 1) : undefined,
      description: file.page_range ? 
        `Pages ${file.page_range.start}-${file.page_range.end}` : 
        `Part ${index + 1}`
    }));

    return (
      <div className="split-results">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-lg">{OPERATION_ICONS.splitting}</span>
            <h3 className="text-lg font-semibold">Split Results</h3>
            <span className="text-sm text-gray-500">({files.length} files)</span>
          </div>
          
          {files.length > 1 && (
            <button
              onClick={handleDownloadAll}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
            >
              Download All (ZIP)
            </button>
          )}
        </div>

        {/* Statistics */}
        {showStatistics && (
          <div className="bg-gray-50 border rounded p-4 mb-4">
            <h4 className="font-medium mb-2">Statistics</h4>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Files created:</span>
                <span className="ml-2 font-medium">{files.length}</span>
              </div>
              <div>
                <span className="text-gray-600">Total pages:</span>
                <span className="ml-2 font-medium">
                  {files.reduce((sum, f) => sum + (f.pageCount || 0), 0)}
                </span>
              </div>
              <div>
                <span className="text-gray-600">Total size:</span>
                <span className="ml-2 font-medium">
                  {formatFileSize(files.reduce((sum, f) => sum + f.size, 0))}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* File List */}
        <div className="space-y-2">
          {files.map((file, index) => (
            <div key={file.id} className="border rounded p-4 bg-white">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="font-medium text-sm">{file.name}</div>
                  <div className="text-xs text-gray-600 mt-1">
                    {file.description} • {formatFileSize(file.size)}
                  </div>
                </div>
                <button
                  onClick={() => handleDownload(file.id)}
                  className="px-3 py-1 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200"
                >
                  Download
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderMergeResults = () => {
    const mergeResults = results as MergeInfo;
    
    return (
      <div className="merge-results">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-lg">{OPERATION_ICONS.merging}</span>
            <h3 className="text-lg font-semibold">Merge Results</h3>
          </div>
          
          <button
            onClick={() => handleDownload('merged')}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
          >
            Download Merged PDF
          </button>
        </div>

        {/* Statistics */}
        {showStatistics && (
          <div className="bg-gray-50 border rounded p-4 mb-4">
            <h4 className="font-medium mb-2">Merge Statistics</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Source files:</span>
                <span className="ml-2 font-medium">{mergeResults.source_files?.length || 0}</span>
              </div>
              <div>
                <span className="text-gray-600">Total pages:</span>
                <span className="ml-2 font-medium">{mergeResults.total_pages}</span>
              </div>
              <div>
                <span className="text-gray-600">File size:</span>
                <span className="ml-2 font-medium">{formatFileSize(mergeResults.file_size)}</span>
              </div>
              <div>
                <span className="text-gray-600">Bookmarks:</span>
                <span className="ml-2 font-medium">
                  {mergeResults.bookmark_count || 0} preserved
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Merged File Preview */}
        <div className="border rounded p-4 bg-white">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium">{mergeResults.filename}</div>
              <div className="text-sm text-gray-600 mt-1">
                {mergeResults.total_pages} pages • {formatFileSize(mergeResults.file_size)}
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-green-600 text-sm">✓ Ready</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderExtractionResults = () => {
    const extractionResults = results as ExtractedData;
    const extractionPreviews: ExtractionPreview[] = [];
    
    // Build extraction previews from results
    if (extractionResults.text_content) {
      Object.entries(extractionResults.text_content).forEach(([format, content]) => {
        extractionPreviews.push({
          type: 'text',
          format,
          content,
          size: typeof content === 'string' ? content.length : 0,
          downloadUrl: extractionResults.download_urls?.text?.[format] || '',
          preview: typeof content === 'string' ? content.substring(0, 200) + '...' : ''
        });
      });
    }

    if (extractionResults.images) {
      extractionResults.images.forEach((image, index) => {
        extractionPreviews.push({
          type: 'image',
          format: image.format,
          content: image,
          size: image.size || 0,
          downloadUrl: image.download_url || '',
          preview: image.preview_url
        });
      });
    }

    if (extractionResults.tables) {
      extractionResults.tables.forEach((table, index) => {
        extractionPreviews.push({
          type: 'table',
          format: 'csv', // or determine from table data
          content: table,
          size: 0, // calculate if needed
          downloadUrl: table.download_url || '',
          preview: `Table ${index + 1} (${table.rows}×${table.columns})`
        });
      });
    }

    if (extractionResults.metadata) {
      extractionPreviews.push({
        type: 'metadata',
        format: 'json',
        content: extractionResults.metadata,
        size: JSON.stringify(extractionResults.metadata).length,
        downloadUrl: extractionResults.download_urls?.metadata?.json || '',
        preview: JSON.stringify(extractionResults.metadata, null, 2).substring(0, 200) + '...'
      });
    }

    const tabs = [
      { id: 'files', label: 'Extracted Files', count: extractionPreviews.length },
      { id: 'preview', label: 'Content Preview', count: 0 },
      { id: 'stats', label: 'Statistics', count: 0 }
    ];

    return (
      <div className="extraction-results">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-lg">{OPERATION_ICONS.extraction}</span>
            <h3 className="text-lg font-semibold">Extraction Results</h3>
            <span className="text-sm text-gray-500">({extractionPreviews.length} items)</span>
          </div>
          
          <button
            onClick={handleDownloadAll}
            className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
          >
            Download All
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b mb-4">
          <div className="flex space-x-6">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`pb-2 px-1 border-b-2 text-sm font-medium ${
                  activeTab === tab.id
                    ? 'border-purple-500 text-purple-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span className="ml-2 bg-gray-100 text-gray-600 rounded-full px-2 py-0.5 text-xs">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === 'files' && (
          <div className="space-y-3">
            {extractionPreviews.map((item, index) => (
              <div key={`${item.type}-${index}`} className="border rounded p-4 bg-white">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2">
                      <span className="capitalize font-medium text-sm">
                        {item.type} ({item.format.toUpperCase()})
                      </span>
                      <span className="text-xs text-gray-500">
                        {formatFileSize(item.size)}
                      </span>
                    </div>
                    
                    {item.preview && (
                      <div className="mt-2">
                        <button
                          onClick={() => toggleExpanded(`${item.type}-${index}`)}
                          className="text-xs text-blue-600 hover:text-blue-800"
                        >
                          {expandedItems.has(`${item.type}-${index}`) ? 'Hide' : 'Show'} Preview
                        </button>
                        
                        {expandedItems.has(`${item.type}-${index}`) && (
                          <div className="mt-2 p-2 bg-gray-50 rounded text-xs font-mono">
                            {item.type === 'image' ? (
                              <img 
                                src={item.preview} 
                                alt="Preview" 
                                className="max-w-full h-32 object-contain"
                              />
                            ) : (
                              <pre className="whitespace-pre-wrap">{item.preview}</pre>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <button
                    onClick={() => handleDownload(`${item.type}-${index}`)}
                    className="px-3 py-1 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200"
                  >
                    Download
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'stats' && showStatistics && (
          <div className="bg-gray-50 border rounded p-4">
            <h4 className="font-medium mb-3">Extraction Statistics</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Text extracted:</span>
                <span className="ml-2 font-medium">
                  {extractionResults.text_content ? 
                    Object.keys(extractionResults.text_content).length + ' formats' : 
                    'None'
                  }
                </span>
              </div>
              <div>
                <span className="text-gray-600">Images extracted:</span>
                <span className="ml-2 font-medium">
                  {extractionResults.images?.length || 0}
                </span>
              </div>
              <div>
                <span className="text-gray-600">Tables extracted:</span>
                <span className="ml-2 font-medium">
                  {extractionResults.tables?.length || 0}
                </span>
              </div>
              <div>
                <span className="text-gray-600">Total files:</span>
                <span className="ml-2 font-medium">{extractionPreviews.length}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderRedactionResults = () => {
    const redactionResults = results as RedactionResults;
    
    return (
      <div className="redaction-results">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-lg">{OPERATION_ICONS.redaction}</span>
            <h3 className="text-lg font-semibold">Redaction Results</h3>
          </div>
          
          <button
            onClick={() => handleDownload('redacted')}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Download Redacted PDF
          </button>
        </div>

        {showStatistics && (
          <div className="bg-gray-50 border rounded p-4">
            <h4 className="font-medium mb-2">Redaction Statistics</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Total redactions:</span>
                <span className="ml-2 font-medium">{redactionResults.total_redactions}</span>
              </div>
              <div>
                <span className="text-gray-600">Pages affected:</span>
                <span className="ml-2 font-medium">{redactionResults.pages_with_redactions}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderResults = () => {
    switch (operationType) {
      case 'splitting':
        return renderSplitResults();
      case 'merging':
        return renderMergeResults();
      case 'extraction':
        return renderExtractionResults();
      case 'redaction':
        return renderRedactionResults();
      default:
        return (
          <div className="text-center py-8 text-gray-500">
            Results preview not available for this operation type.
          </div>
        );
    }
  };

  if (!results) {
    return (
      <div className={`result-preview ${className}`}>
        <div className="text-center py-8 text-gray-500">
          No results available.
        </div>
      </div>
    );
  }

  return (
    <div className={`result-preview ${className}`}>
      {renderResults()}
    </div>
  );
};