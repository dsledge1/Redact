"use client";

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { parsePageRanges, formatPageRanges, validatePageRanges } from '../utils/operationUtils';
import type { PageRange } from '../types';

export interface PageRangeSelectorProps {
  totalPages: number;
  selectedRanges: PageRange[];
  onRangeChange: (ranges: PageRange[]) => void;
  documentRef?: React.RefObject<HTMLDivElement>;
  className?: string;
  maxSelectableRanges?: number;
  allowSinglePageSelection?: boolean;
}

interface PageThumbnail {
  pageNumber: number;
  isSelected: boolean;
  isRangeStart: boolean;
  isRangeEnd: boolean;
  inRange: boolean;
}

export const PageRangeSelector: React.FC<PageRangeSelectorProps> = ({
  totalPages,
  selectedRanges,
  onRangeChange,
  documentRef,
  className = '',
  maxSelectableRanges = 10,
  allowSinglePageSelection = true
}) => {
  const [thumbnails, setThumbnails] = useState<PageThumbnail[]>([]);
  const [isSelecting, setIsSelecting] = useState<boolean>(false);
  const [selectionStart, setSelectionStart] = useState<number | null>(null);
  const [currentHover, setCurrentHover] = useState<number | null>(null);
  const [provisionalSelection, setProvisionalSelection] = useState<PageRange | null>(null);
  const [presetRanges] = useState([
    { label: 'All Pages', value: `1-${totalPages}` },
    { label: 'First Half', value: `1-${Math.ceil(totalPages / 2)}` },
    { label: 'Second Half', value: `${Math.ceil(totalPages / 2) + 1}-${totalPages}` },
    { label: 'Odd Pages', value: generateOddPages(totalPages) },
    { label: 'Even Pages', value: generateEvenPages(totalPages) },
    { label: 'First 5 Pages', value: `1-${Math.min(5, totalPages)}` },
    { label: 'Last 5 Pages', value: `${Math.max(1, totalPages - 4)}-${totalPages}` }
  ]);
  const selectorRef = useRef<HTMLDivElement>(null);

  // Generate thumbnails data
  useEffect(() => {
    const newThumbnails: PageThumbnail[] = [];
    const selectedPages = new Set<number>();
    
    // Collect all selected pages
    selectedRanges.forEach(range => {
      for (let i = range.start; i <= range.end; i++) {
        selectedPages.add(i);
      }
    });
    
    for (let i = 1; i <= totalPages; i++) {
      const isSelected = selectedPages.has(i);
      const isRangeStart = selectedRanges.some(range => range.start === i);
      const isRangeEnd = selectedRanges.some(range => range.end === i);
      const inRange = selectedPages.has(i);
      
      newThumbnails.push({
        pageNumber: i,
        isSelected,
        isRangeStart,
        isRangeEnd,
        inRange
      });
    }
    
    setThumbnails(newThumbnails);
  }, [selectedRanges, totalPages]);

  const handlePageClick = useCallback((pageNumber: number, event: React.MouseEvent) => {
    event.preventDefault();
    
    if (event.shiftKey && selectionStart !== null) {
      // Range selection
      const start = Math.min(selectionStart, pageNumber);
      const end = Math.max(selectionStart, pageNumber);
      const newRange: PageRange = { start, end };
      
      if (selectedRanges.length >= maxSelectableRanges) {
        return; // Max ranges reached
      }
      
      // Check for overlaps and merge if necessary
      const mergedRanges = mergeRangeWithExisting([...selectedRanges, newRange]);
      onRangeChange(mergedRanges);
      setSelectionStart(null);
    } else if (event.ctrlKey || event.metaKey) {
      // Toggle individual page
      const existingRangeIndex = selectedRanges.findIndex(
        range => range.start <= pageNumber && range.end >= pageNumber
      );
      
      if (existingRangeIndex >= 0) {
        // Remove page from existing range
        const updatedRanges = removePageFromRanges(selectedRanges, pageNumber);
        onRangeChange(updatedRanges);
      } else {
        // Add single page
        if (allowSinglePageSelection) {
          const newRange: PageRange = { start: pageNumber, end: pageNumber };
          const mergedRanges = mergeRangeWithExisting([...selectedRanges, newRange]);
          onRangeChange(mergedRanges);
        }
      }
    } else {
      // Start new selection
      setSelectionStart(pageNumber);
      if (allowSinglePageSelection) {
        const newRange: PageRange = { start: pageNumber, end: pageNumber };
        onRangeChange([newRange]);
      }
    }
  }, [selectedRanges, onRangeChange, selectionStart, maxSelectableRanges, allowSinglePageSelection]);

  const handleMouseDown = useCallback((pageNumber: number, event: React.MouseEvent) => {
    if (event.button === 0) { // Left mouse button
      setIsSelecting(true);
      setSelectionStart(pageNumber);
    }
  }, []);

  const handleMouseMove = useCallback((pageNumber: number) => {
    setCurrentHover(pageNumber);
    
    if (isSelecting && selectionStart !== null) {
      // Show provisional selection during drag
      const start = Math.min(selectionStart, pageNumber);
      const end = Math.max(selectionStart, pageNumber);
      
      // Validate that adding this range won't exceed maxSelectableRanges
      const tempRanges = [...selectedRanges, { start, end }];
      const mergedRanges = mergeRangeWithExisting(tempRanges);
      
      if (mergedRanges.length <= maxSelectableRanges) {
        setProvisionalSelection({ start, end });
      } else {
        setProvisionalSelection(null);
      }
    } else {
      setProvisionalSelection(null);
    }
  }, [isSelecting, selectionStart, selectedRanges, maxSelectableRanges]);

  const handleMouseUp = useCallback((pageNumber: number, event: React.MouseEvent) => {
    if (isSelecting && selectionStart !== null && selectionStart !== pageNumber) {
      const start = Math.min(selectionStart, pageNumber);
      const end = Math.max(selectionStart, pageNumber);
      const newRange: PageRange = { start, end };
      
      if (selectedRanges.length < maxSelectableRanges) {
        const mergedRanges = mergeRangeWithExisting([...selectedRanges, newRange]);
        onRangeChange(mergedRanges);
      }
    }
    
    setIsSelecting(false);
    setSelectionStart(null);
    setProvisionalSelection(null);
  }, [isSelecting, selectionStart, selectedRanges, onRangeChange, maxSelectableRanges]);

  const handlePresetSelection = useCallback((presetValue: string) => {
    try {
      const ranges = parsePageRanges(presetValue);
      const validation = validatePageRanges(ranges, totalPages);
      
      if (validation.isValid) {
        onRangeChange(ranges);
      }
    } catch (error) {
      console.error('Failed to apply preset:', error);
    }
  }, [totalPages, onRangeChange]);

  const clearSelection = useCallback(() => {
    onRangeChange([]);
  }, [onRangeChange]);

  // Keyboard navigation
  const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>, pageNumber: number) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      // Simulate click
      const mockEvent = {
        preventDefault: () => {},
        shiftKey: event.shiftKey,
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey
      } as React.MouseEvent;
      handlePageClick(pageNumber, mockEvent);
    } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft' || event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault();
      
      const currentIndex = thumbnails.findIndex(t => t.pageNumber === pageNumber);
      let targetIndex: number;
      
      switch (event.key) {
        case 'ArrowRight':
          targetIndex = Math.min(currentIndex + 1, thumbnails.length - 1);
          break;
        case 'ArrowLeft':
          targetIndex = Math.max(currentIndex - 1, 0);
          break;
        case 'ArrowUp':
          targetIndex = Math.max(currentIndex - 10, 0); // Assuming 10 columns
          break;
        case 'ArrowDown':
          targetIndex = Math.min(currentIndex + 10, thumbnails.length - 1);
          break;
        default:
          return;
      }
      
      const targetElement = selectorRef.current?.querySelector(`[data-page="${thumbnails[targetIndex].pageNumber}"]`) as HTMLElement;
      if (targetElement) {
        targetElement.focus();
      }
    }
  }, [handlePageClick, thumbnails]);

  const getPageClassName = useCallback((thumbnail: PageThumbnail) => {
    const baseClass = "page-thumbnail w-12 h-16 border-2 rounded cursor-pointer flex items-center justify-center text-xs font-medium transition-all duration-150";
    
    if (thumbnail.inRange) {
      if (thumbnail.isRangeStart || thumbnail.isRangeEnd) {
        return `${baseClass} border-blue-600 bg-blue-600 text-white`;
      } else {
        return `${baseClass} border-blue-400 bg-blue-100 text-blue-800`;
      }
    } else if (provisionalSelection && 
               thumbnail.pageNumber >= provisionalSelection.start && 
               thumbnail.pageNumber <= provisionalSelection.end) {
      // Show provisional selection with different highlighting
      if (thumbnail.pageNumber === provisionalSelection.start || thumbnail.pageNumber === provisionalSelection.end) {
        return `${baseClass} border-blue-400 bg-blue-200 text-blue-900`;
      } else {
        return `${baseClass} border-blue-300 bg-blue-50 text-blue-700`;
      }
    } else if (currentHover === thumbnail.pageNumber && isSelecting && selectionStart !== null) {
      const start = Math.min(selectionStart, currentHover);
      const end = Math.max(selectionStart, currentHover);
      if (thumbnail.pageNumber >= start && thumbnail.pageNumber <= end) {
        return `${baseClass} border-blue-300 bg-blue-50 text-blue-700`;
      }
    }
    
    return `${baseClass} border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50`;
  }, [currentHover, isSelecting, selectionStart, provisionalSelection]);

  return (
    <div className={`page-range-selector ${className}`}>
      {/* Preset Buttons */}
      <div className="preset-buttons mb-4">
        <div className="flex flex-wrap gap-2 mb-2">
          {presetRanges.map((preset, index) => (
            <button
              key={index}
              onClick={() => handlePresetSelection(preset.value)}
              className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 text-gray-700"
            >
              {preset.label}
            </button>
          ))}
          <button
            onClick={clearSelection}
            className="px-3 py-1 text-sm border border-red-300 rounded hover:bg-red-50 text-red-700"
          >
            Clear All
          </button>
        </div>
      </div>

      {/* Selection Summary */}
      {selectedRanges.length > 0 && (
        <div className="selection-summary mb-4 p-3 bg-blue-50 border border-blue-200 rounded">
          <div className="text-sm font-medium text-blue-800 mb-1">
            Selected: {formatPageRanges(selectedRanges)}
          </div>
          <div className="text-xs text-blue-600">
            {selectedRanges.reduce((total, range) => total + (range.end - range.start + 1), 0)} pages selected
          </div>
        </div>
      )}

      {/* Page Thumbnails Grid */}
      <div 
        ref={selectorRef}
        className="page-grid max-h-96 overflow-y-auto border border-gray-200 rounded p-4"
        style={{ backgroundColor: '#fafafa' }}
        role="grid"
        aria-label="Page selection grid"
      >
        <div className="grid grid-cols-10 gap-2 sm:grid-cols-12 md:grid-cols-15 lg:grid-cols-20">
          {thumbnails.map((thumbnail, index) => (
            <div
              key={thumbnail.pageNumber}
              data-page={thumbnail.pageNumber}
              className={getPageClassName(thumbnail)}
              onClick={(e) => handlePageClick(thumbnail.pageNumber, e)}
              onMouseDown={(e) => handleMouseDown(thumbnail.pageNumber, e)}
              onMouseMove={() => handleMouseMove(thumbnail.pageNumber)}
              onMouseUp={(e) => handleMouseUp(thumbnail.pageNumber, e)}
              onKeyDown={(e) => handleKeyDown(e, thumbnail.pageNumber)}
              title={`Page ${thumbnail.pageNumber}${thumbnail.inRange ? ' (selected)' : ''}`}
              role="gridcell"
              tabIndex={index === 0 ? 0 : -1}
              aria-selected={thumbnail.inRange}
              aria-label={`Page ${thumbnail.pageNumber}${thumbnail.inRange ? ', selected' : ''}`}
            >
              {thumbnail.pageNumber}
            </div>
          ))}
        </div>
      </div>

      {/* Instructions */}
      <div className="instructions mt-4 text-sm text-gray-600">
        <div className="space-y-1">
          <div>• Click to select individual pages</div>
          <div>• Shift+click to select page ranges</div>
          <div>• Ctrl/Cmd+click to add/remove pages from selection</div>
          <div>• Drag to select multiple pages</div>
        </div>
      </div>

      {/* Range Validation */}
      {selectedRanges.length >= maxSelectableRanges && (
        <div className="validation-warning mt-3 p-2 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
          Maximum number of ranges ({maxSelectableRanges}) reached. Please merge or remove existing ranges to add more.
        </div>
      )}
    </div>
  );
};

// Utility functions
function generateOddPages(totalPages: number): string {
  const oddPages: number[] = [];
  for (let i = 1; i <= totalPages; i += 2) {
    oddPages.push(i);
  }
  return oddPages.join(',');
}

function generateEvenPages(totalPages: number): string {
  const evenPages: number[] = [];
  for (let i = 2; i <= totalPages; i += 2) {
    evenPages.push(i);
  }
  return evenPages.join(',');
}

function mergeRangeWithExisting(ranges: PageRange[]): PageRange[] {
  if (ranges.length <= 1) return ranges;
  
  // Sort ranges by start page
  const sorted = [...ranges].sort((a, b) => a.start - b.start);
  const merged: PageRange[] = [sorted[0]];
  
  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i];
    const last = merged[merged.length - 1];
    
    // Check if ranges overlap or are adjacent
    if (current.start <= last.end + 1) {
      // Merge ranges
      last.end = Math.max(last.end, current.end);
    } else {
      // Add as new range
      merged.push(current);
    }
  }
  
  return merged;
}

function removePageFromRanges(ranges: PageRange[], pageNumber: number): PageRange[] {
  const result: PageRange[] = [];
  
  for (const range of ranges) {
    if (pageNumber < range.start || pageNumber > range.end) {
      // Page not in this range, keep as is
      result.push(range);
    } else if (range.start === range.end) {
      // Single page range, remove entirely
      continue;
    } else if (pageNumber === range.start) {
      // Remove from start
      result.push({ start: range.start + 1, end: range.end });
    } else if (pageNumber === range.end) {
      // Remove from end
      result.push({ start: range.start, end: range.end - 1 });
    } else {
      // Split range
      result.push({ start: range.start, end: pageNumber - 1 });
      result.push({ start: pageNumber + 1, end: range.end });
    }
  }
  
  return result;
}