'use client';

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import clsx from 'clsx';

import type { PDFViewerProps, ViewerState, ZoomLevel, SearchResult } from '@/types';
import { useDocument, useUI, useUIActions } from '@/store';
import LoadingSpinner from './LoadingSpinner';
import RedactionOverlay from './RedactionOverlay';
import ManualRedactionTool from './ManualRedactionTool';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

const PDFViewer = ({
  documentId,
  file,
  onPageChange,
  onScaleChange,
  onError,
  initialPage = 1,
  initialScale = 1.0,
  showControls = true,
  showThumbnails = false,
  className,
  ...props
}: PDFViewerProps): JSX.Element => {
  const currentDoc = useDocument();
  const { viewer } = useUI();
  const { setScale, setRotation, setCurrentPage, setDisplayMode, setPageDimensions } = useUIActions();
  
  // Local state for PDF-specific properties not in the store
  const [totalPages, setTotalPages] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [currentSearchIndex, setCurrentSearchIndex] = useState(-1);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [pageWidth, setPageWidth] = useState(0);
  const [pageHeight, setPageHeight] = useState(0);
  
  const pageContainerRef = useRef<HTMLDivElement>(null);

  // Get PDF source
  const pdfSource = useMemo(() => {
    if (file) return typeof file === 'string' ? file : URL.createObjectURL(file);
    if (documentId) return `/api/documents/${documentId}/download/`;
    return null;
  }, [file, documentId]);

  // Handle PDF load success
  const onDocumentLoadSuccess = useCallback((pdf: any) => {
    setTotalPages(pdf.numPages);
    setLoading(false);
    setError(null);
  }, []);

  // Handle page render success to capture dimensions
  const onPageRenderSuccess = useCallback((page: any) => {
    const { width, height, originalWidth, originalHeight } = page;
    // Store the scaled dimensions returned by react-pdf
    setPageWidth(width);
    setPageHeight(height);
    
    // Store page dimensions for coordinate conversion
    if (setPageDimensions) {
      setPageDimensions(viewer.currentPage, {
        width,
        height,
        originalWidth,
        originalHeight,
      });
    }
  }, [viewer.currentPage, setPageDimensions]);

  // Handle PDF load error
  const onDocumentLoadError = useCallback((error: Error) => {
    setError(error.message);
    setLoading(false);
    onError?.(error as any);
  }, [onError]);

  // Page navigation
  const goToPage = useCallback((page: number) => {
    const newPage = Math.max(1, Math.min(page, totalPages));
    setCurrentPage(newPage);
    onPageChange?.(newPage);
  }, [totalPages, onPageChange, setCurrentPage]);

  const nextPage = useCallback(() => {
    goToPage(viewer.currentPage + 1);
  }, [goToPage, viewer.currentPage]);

  const previousPage = useCallback(() => {
    goToPage(viewer.currentPage - 1);
  }, [goToPage, viewer.currentPage]);

  // Zoom controls
  const setZoom = useCallback((zoom: ZoomLevel) => {
    let newScale: number;
    
    if (typeof zoom === 'number') {
      newScale = zoom;
    } else {
      switch (zoom) {
        case 'fit-width':
          newScale = 1.0; // Will be calculated based on container width
          break;
        case 'fit-height':
          newScale = 1.2;
          break;
        case 'fit-page':
          newScale = 0.8;
          break;
        case 'actual-size':
          newScale = 1.0;
          break;
        default:
          newScale = 1.0;
      }
    }
    
    setScale(newScale);
    onScaleChange?.(newScale);
  }, [onScaleChange, setScale]);

  const zoomIn = useCallback(() => {
    const newScale = Math.min(viewer.scale * 1.25, 3.0);
    setZoom(newScale);
  }, [viewer.scale, setZoom]);

  const zoomOut = useCallback(() => {
    const newScale = Math.max(viewer.scale / 1.25, 0.25);
    setZoom(newScale);
  }, [viewer.scale, setZoom]);

  // Rotation
  const rotate = useCallback(() => {
    setRotation((viewer.rotation + 90) % 360);
  }, [viewer.rotation, setRotation]);

  // Fullscreen
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return;
      
      switch (event.key) {
        case 'ArrowLeft':
        case 'ArrowUp':
          event.preventDefault();
          previousPage();
          break;
        case 'ArrowRight':
        case 'ArrowDown':
          event.preventDefault();
          nextPage();
          break;
        case '=':
        case '+':
          if (event.ctrlKey || event.metaKey) {
            event.preventDefault();
            zoomIn();
          }
          break;
        case '-':
          if (event.ctrlKey || event.metaKey) {
            event.preventDefault();
            zoomOut();
          }
          break;
        case 'f':
          if (event.ctrlKey || event.metaKey) {
            event.preventDefault();
            toggleFullscreen();
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [previousPage, nextPage, zoomIn, zoomOut, toggleFullscreen]);

  // Search functionality (placeholder)
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
    // TODO: Implement actual PDF text search
    // This would require extracting text content from the PDF
    // and finding matching positions
  }, []);

  const containerClasses = useMemo(() => {
    return clsx(
      'relative flex h-full flex-col bg-gray-100',
      {
        'fixed inset-0 z-50': isFullscreen,
      },
      className
    );
  }, [isFullscreen, className]);

  if (!pdfSource) {
    return (
      <div className={containerClasses} {...props}>
        <div className="flex flex-1 items-center justify-center">
          <p className="text-gray-500">No PDF to display</p>
        </div>
      </div>
    );
  }

  return (
    <div className={containerClasses} {...props}>
      {/* Controls */}
      {showControls && (
        <div className="flex items-center justify-between border-b bg-white px-4 py-3">
          {/* Navigation Controls */}
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={previousPage}
              disabled={viewer.currentPage <= 1}
              className="rounded bg-gray-100 p-2 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Previous page"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            
            <div className="flex items-center space-x-2">
              <input
                type="number"
                min={1}
                max={totalPages}
                value={viewer.currentPage}
                onChange={(e) => goToPage(parseInt(e.target.value, 10))}
                className="w-16 rounded border border-gray-300 px-2 py-1 text-center text-sm"
                aria-label="Current page"
              />
              <span className="text-sm text-gray-500">
                of {totalPages}
              </span>
            </div>
            
            <button
              type="button"
              onClick={nextPage}
              disabled={viewer.currentPage >= totalPages}
              className="rounded bg-gray-100 p-2 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Next page"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={zoomOut}
              className="rounded bg-gray-100 p-2 hover:bg-gray-200"
              aria-label="Zoom out"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
              </svg>
            </button>
            
            <span className="text-sm font-medium">
              {Math.round(viewer.scale * 100)}%
            </span>
            
            <button
              type="button"
              onClick={zoomIn}
              className="rounded bg-gray-100 p-2 hover:bg-gray-200"
              aria-label="Zoom in"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
            
            <select
              value={viewer.scale}
              onChange={(e) => setZoom(parseFloat(e.target.value) as ZoomLevel)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
              aria-label="Zoom level"
            >
              <option value={0.5}>50%</option>
              <option value={0.75}>75%</option>
              <option value={1.0}>100%</option>
              <option value={1.25}>125%</option>
              <option value={1.5}>150%</option>
              <option value={2.0}>200%</option>
            </select>
          </div>

          {/* Additional Controls */}
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={rotate}
              className="rounded bg-gray-100 p-2 hover:bg-gray-200"
              aria-label="Rotate"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            
            <button
              type="button"
              onClick={toggleFullscreen}
              className="rounded bg-gray-100 p-2 hover:bg-gray-200"
              aria-label="Toggle fullscreen"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Search Bar (if enabled) */}
      <div className="border-b bg-gray-50 px-4 py-2">
        <div className="flex items-center space-x-2">
          <svg className="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search in PDF..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="flex-1 rounded border border-gray-300 px-3 py-1 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>
      </div>

      {/* PDF Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Thumbnails Sidebar */}
        {showThumbnails && totalPages > 0 && (
          <div className="w-48 border-r bg-gray-50 overflow-y-auto">
            <div className="p-4 space-y-2">
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNumber) => (
                <button
                  key={pageNumber}
                  onClick={() => goToPage(pageNumber)}
                  className={clsx(
                    'block w-full rounded border-2 p-2 text-xs transition-colors',
                    {
                      'border-primary-500 bg-primary-50': pageNumber === viewer.currentPage,
                      'border-gray-200 hover:border-gray-300': pageNumber !== viewer.currentPage,
                    }
                  )}
                >
                  <div className="aspect-[8.5/11] bg-white border rounded mb-1">
                    {/* Thumbnail would be rendered here */}
                    <div className="flex h-full items-center justify-center text-gray-400">
                      <span>{pageNumber}</span>
                    </div>
                  </div>
                  Page {pageNumber}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Main PDF Display */}
        <div className="flex-1 overflow-auto bg-gray-200 p-4">
          <div className="mx-auto max-w-fit">
            {loading && (
              <div className="flex h-96 items-center justify-center">
                <LoadingSpinner size="lg" text="Loading PDF..." />
              </div>
            )}

            {error && (
              <div className="flex h-96 items-center justify-center">
                <div className="text-center">
                  <svg className="mx-auto h-12 w-12 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  <h3 className="mt-2 text-sm font-medium text-gray-900">Error loading PDF</h3>
                  <p className="mt-1 text-sm text-gray-500">{error}</p>
                </div>
              </div>
            )}

            {!loading && !error && (
              <Document
                file={pdfSource}
                onLoadSuccess={onDocumentLoadSuccess}
                onLoadError={onDocumentLoadError}
                loading={<LoadingSpinner size="lg" text="Loading PDF..." />}
                className="pdf-document"
              >
                <div 
                  ref={pageContainerRef}
                  className="relative inline-block"
                  style={{
                    width: pageWidth,
                    height: pageHeight,
                  }}
                >
                  <Page
                    pageNumber={viewer.currentPage}
                    scale={viewer.scale}
                    rotate={viewer.rotation}
                    loading={<LoadingSpinner />}
                    className="pdf-page shadow-lg"
                    onRenderSuccess={onPageRenderSuccess}
                  />
                  
                  {/* Redaction Overlay */}
                  {pageWidth > 0 && pageHeight > 0 && (
                    <>
                      <RedactionOverlay
                        pageNumber={viewer.currentPage}
                        pageWidth={pageWidth}
                        pageHeight={pageHeight}
                        scale={1}
                        rotation={viewer.rotation}
                      />
                      
                      <ManualRedactionTool
                        pageNumber={viewer.currentPage}
                        pageWidth={pageWidth}
                        pageHeight={pageHeight}
                        scale={1}
                        rotation={viewer.rotation}
                        containerRef={pageContainerRef}
                      />
                    </>
                  )}
                </div>
              </Document>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PDFViewer;