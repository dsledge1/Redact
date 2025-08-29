/**
 * File utility functions for PDF processing
 */

import type { FileValidation, ValidationError, ValidationWarning } from '@/types';

// Constants
export const SUPPORTED_MIME_TYPES = [
  'application/pdf',
] as const;

export const MAX_FILE_SIZE = parseInt(process.env.NEXT_PUBLIC_MAX_FILE_SIZE || '104857600', 10); // 100MB
export const MAX_FILE_NAME_LENGTH = 255;
export const UNSAFE_FILE_PATTERNS = [
  /\.(exe|bat|cmd|com|pif|scr|vbs|js)$/i,
  /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i,
];

/**
 * Validates if a file is a PDF based on MIME type and extension
 */
export function isPDF(file: File): boolean {
  const mimeType = file.type.toLowerCase();
  const extension = getFileExtension(file.name).toLowerCase();
  
  return mimeType === 'application/pdf' || extension === 'pdf';
}

/**
 * Validates file size against maximum allowed size
 */
export function validateFileSize(file: File, maxSize: number = MAX_FILE_SIZE): boolean {
  return file.size <= maxSize;
}

/**
 * Validates file name for security and length constraints
 */
export function validateFileName(fileName: string): { isValid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  if (!fileName || fileName.trim().length === 0) {
    errors.push('File name cannot be empty');
  }
  
  if (fileName.length > MAX_FILE_NAME_LENGTH) {
    errors.push(`File name cannot exceed ${MAX_FILE_NAME_LENGTH} characters`);
  }
  
  // Check for unsafe file patterns
  for (const pattern of UNSAFE_FILE_PATTERNS) {
    if (pattern.test(fileName)) {
      errors.push('File name contains unsafe characters or reserved names');
      break;
    }
  }
  
  // Check for control characters and path traversal
  if (/[\x00-\x1f\x7f-\x9f]/.test(fileName) || fileName.includes('..') || fileName.includes('/') || fileName.includes('\\')) {
    errors.push('File name contains invalid characters');
  }
  
  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Comprehensive file validation
 */
export function validateFile(file: File): FileValidation {
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];
  
  // Validate file type
  if (!isPDF(file)) {
    errors.push({
      code: 'INVALID_FILE_TYPE',
      message: 'Only PDF files are supported',
      field: 'file',
    });
  }
  
  // Validate file size
  if (!validateFileSize(file)) {
    errors.push({
      code: 'FILE_TOO_LARGE',
      message: `File size cannot exceed ${formatBytes(MAX_FILE_SIZE)}`,
      field: 'file',
    });
  }
  
  // Validate file name
  const nameValidation = validateFileName(file.name);
  if (!nameValidation.isValid) {
    errors.push({
      code: 'INVALID_FILE_NAME',
      message: nameValidation.errors.join(', '),
      field: 'fileName',
    });
  }
  
  // Check for empty file
  if (file.size === 0) {
    errors.push({
      code: 'EMPTY_FILE',
      message: 'File appears to be empty',
      field: 'file',
    });
  }
  
  // Add warnings for large files
  if (file.size > MAX_FILE_SIZE * 0.8) {
    warnings.push({
      code: 'LARGE_FILE',
      message: 'Large files may take longer to process',
      severity: 'medium',
    });
  }
  
  // Check for potentially corrupted files (very small PDFs)
  if (file.size < 1024 && isPDF(file)) {
    warnings.push({
      code: 'SUSPICIOUSLY_SMALL',
      message: 'File is unusually small for a PDF document',
      severity: 'low',
    });
  }
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings,
  };
}

/**
 * Formats file size in human-readable format
 */
export function formatBytes(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

/**
 * Gets file extension from filename
 */
export function getFileExtension(fileName: string): string {
  const lastDot = fileName.lastIndexOf('.');
  return lastDot === -1 ? '' : fileName.slice(lastDot + 1);
}

/**
 * Sanitizes filename for safe storage and display
 */
export function sanitizeFileName(fileName: string): string {
  // Remove or replace unsafe characters
  let sanitized = fileName
    .replace(/[<>:"/\\|?*\x00-\x1f\x7f-\x9f]/g, '_')
    .replace(/\s+/g, '_')
    .replace(/_{2,}/g, '_')
    .replace(/^_+|_+$/g, '');
  
  // Ensure it doesn't exceed max length
  if (sanitized.length > MAX_FILE_NAME_LENGTH) {
    const extension = getFileExtension(sanitized);
    const nameWithoutExt = sanitized.slice(0, sanitized.lastIndexOf('.'));
    const maxNameLength = MAX_FILE_NAME_LENGTH - extension.length - 1;
    sanitized = `${nameWithoutExt.slice(0, maxNameLength)}.${extension}`;
  }
  
  return sanitized;
}

/**
 * Calculates file hash for integrity checking (simple hash)
 */
export async function calculateFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Generates unique file name by appending timestamp
 */
export function generateUniqueFileName(originalName: string): string {
  const timestamp = Date.now();
  const extension = getFileExtension(originalName);
  const nameWithoutExt = originalName.slice(0, originalName.lastIndexOf('.'));
  return `${sanitizeFileName(nameWithoutExt)}_${timestamp}.${extension}`;
}

/**
 * Creates a File object from base64 data
 */
export function base64ToFile(base64Data: string, fileName: string, mimeType: string = 'application/pdf'): File {
  const byteCharacters = atob(base64Data);
  const byteNumbers = new Array(byteCharacters.length);
  
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  
  const byteArray = new Uint8Array(byteNumbers);
  return new File([byteArray], fileName, { type: mimeType });
}

/**
 * Converts File to base64 string
 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(',')[1]; // Remove data:mime;base64, prefix
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Downloads a file using blob URL
 */
export function downloadFile(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Creates a download link for a file
 */
export function createDownloadLink(data: Blob | string, fileName: string, mimeType: string = 'application/pdf'): string {
  let blob: Blob;
  
  if (typeof data === 'string') {
    blob = new Blob([data], { type: mimeType });
  } else {
    blob = data;
  }
  
  return URL.createObjectURL(blob);
}

/**
 * Validates drag and drop files
 */
export function validateDroppedFiles(fileList: FileList | File[]): {
  validFiles: File[];
  invalidFiles: Array<{ file: File; errors: ValidationError[] }>;
} {
  const validFiles: File[] = [];
  const invalidFiles: Array<{ file: File; errors: ValidationError[] }> = [];
  
  const files = Array.from(fileList);
  
  for (const file of files) {
    const validation = validateFile(file);
    if (validation.isValid) {
      validFiles.push(file);
    } else {
      invalidFiles.push({
        file,
        errors: validation.errors,
      });
    }
  }
  
  return { validFiles, invalidFiles };
}

/**
 * Estimates upload time based on file size and connection speed
 */
export function estimateUploadTime(fileSize: number, speedBps: number = 1024 * 1024): number {
  // Speed in bytes per second, default to 1 Mbps
  return Math.ceil(fileSize / speedBps);
}

/**
 * Formats upload speed in human-readable format
 */
export function formatSpeed(bytesPerSecond: number): string {
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
  let speed = bytesPerSecond;
  let unitIndex = 0;
  
  while (speed >= 1024 && unitIndex < units.length - 1) {
    speed /= 1024;
    unitIndex++;
  }
  
  return `${speed.toFixed(1)} ${units[unitIndex]}`;
}

/**
 * Creates a preview thumbnail for PDF (placeholder implementation)
 */
export function createFilePreview(file: File): Promise<string> {
  return new Promise((resolve) => {
    // For now, return a placeholder icon
    // In a full implementation, this would generate a thumbnail from the first page
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 260;
    const ctx = canvas.getContext('2d');
    
    if (ctx) {
      // Draw a simple PDF icon
      ctx.fillStyle = '#f3f4f6';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#d1d5db';
      ctx.strokeRect(0, 0, canvas.width, canvas.height);
      
      // Draw PDF text
      ctx.fillStyle = '#374151';
      ctx.font = '20px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('PDF', canvas.width / 2, canvas.height / 2);
    }
    
    resolve(canvas.toDataURL());
  });
}