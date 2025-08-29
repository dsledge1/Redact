/**
 * Utility functions for PDF operation interfaces
 * Provides common functionality for page range validation, file management, and operation processing
 */

import type {
  PageRange,
  ValidationResult,
  FileValidation,
  ExtractionFormData,
  PDFDocument
} from '../types';

// Page Range Utilities

/**
 * Parse page range string into PageRange array
 * Supports formats like "1-5", "1,3,5", "1-5,8,10-12"
 */
export function parsePageRanges(input: string): PageRange[] {
  if (!input || !input.trim()) {
    return [];
  }

  const ranges: PageRange[] = [];
  const parts = input.split(',').map(part => part.trim());

  for (const part of parts) {
    if (!part) continue;

    if (part.includes('-')) {
      // Range format: "1-5"
      const [startStr, endStr] = part.split('-', 2);
      const start = parseInt(startStr.trim(), 10);
      const end = parseInt(endStr.trim(), 10);

      if (isNaN(start) || isNaN(end)) {
        throw new Error(`Invalid range format: "${part}"`);
      }

      if (start > end) {
        throw new Error(`Invalid range: start page (${start}) cannot be greater than end page (${end})`);
      }

      ranges.push({ start, end });
    } else {
      // Single page: "5"
      const page = parseInt(part, 10);
      if (isNaN(page)) {
        throw new Error(`Invalid page number: "${part}"`);
      }
      ranges.push({ start: page, end: page });
    }
  }

  return ranges;
}

/**
 * Validate page ranges against total page count
 */
export function validatePageRanges(ranges: PageRange[], totalPages: number): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (ranges.length === 0) {
    errors.push('At least one page range must be specified');
    return { isValid: false, errors, warnings };
  }

  for (const range of ranges) {
    // Check if pages are positive
    if (range.start < 1 || range.end < 1) {
      errors.push(`Page numbers must be positive (found: ${range.start}-${range.end})`);
    }

    // Check if pages don't exceed total
    if (range.start > totalPages || range.end > totalPages) {
      errors.push(`Page range ${range.start}-${range.end} exceeds document length (${totalPages} pages)`);
    }

    // Check for invalid ranges
    if (range.start > range.end) {
      errors.push(`Invalid range: ${range.start}-${range.end} (start > end)`);
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
    warnings
  };
}

/**
 * Format page ranges for user-friendly display
 */
export function formatPageRanges(ranges: PageRange[]): string {
  if (ranges.length === 0) return '';

  return ranges
    .map(range => range.start === range.end ? `${range.start}` : `${range.start}-${range.end}`)
    .join(', ');
}

/**
 * Format file size for human-readable display
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/**
 * Format processing time for display
 */
export function formatProcessingTime(milliseconds: number): string {
  if (milliseconds < 1000) {
    return `${milliseconds}ms`;
  }
  
  const seconds = Math.floor(milliseconds / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

/**
 * Validate files for merge operation
 */
export function validateMergeFiles(files: File[]): FileValidation[] {
  return files.map((file) => {
    const validation: FileValidation = {
      isValid: true,
      size: file.size,
      error: undefined,
      pageCount: undefined
    };

    // Check file type
    if (file.type !== 'application/pdf') {
      validation.isValid = false;
      validation.error = 'Only PDF files are supported';
      return validation;
    }

    // Check file size (100MB limit)
    if (file.size > 100 * 1024 * 1024) {
      validation.isValid = false;
      validation.error = 'File size exceeds 100MB limit';
      return validation;
    }

    // Check if file is readable
    if (file.size === 0) {
      validation.isValid = false;
      validation.error = 'File appears to be empty';
      return validation;
    }

    return validation;
  });
}

/**
 * Check operation compatibility with document
 */
export function checkOperationCompatibility(document: PDFDocument | null, operation: string): boolean {
  if (!document) return false;

  switch (operation) {
    case 'splitting':
      return document.pageCount > 1;
    case 'merging':
      return true; // Always compatible
    case 'extraction':
      return document.pageCount > 0;
    case 'redaction':
      return document.pageCount > 0;
    default:
      return false;
  }
}