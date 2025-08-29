/**
 * Formatting utility functions
 */

import { format, formatDistanceToNow, isValid, parseISO } from 'date-fns';

/**
 * Formats a date string or Date object in a human-readable format
 */
export function formatDate(date: string | Date, formatString: string = 'PPP'): string {
  try {
    const dateObj = typeof date === 'string' ? parseISO(date) : date;
    return isValid(dateObj) ? format(dateObj, formatString) : 'Invalid date';
  } catch {
    return 'Invalid date';
  }
}

/**
 * Formats a date as a relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(date: string | Date): string {
  try {
    const dateObj = typeof date === 'string' ? parseISO(date) : date;
    return isValid(dateObj) ? formatDistanceToNow(dateObj, { addSuffix: true }) : 'Unknown time';
  } catch {
    return 'Unknown time';
  }
}

/**
 * Formats a number as a percentage
 */
export function formatPercentage(value: number, decimals: number = 1): string {
  return `${value.toFixed(decimals)}%`;
}

/**
 * Formats a duration in milliseconds to human-readable format
 */
export function formatDuration(milliseconds: number): string {
  if (milliseconds < 1000) {
    return `${milliseconds}ms`;
  }
  
  const seconds = Math.floor(milliseconds / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

/**
 * Formats a number with thousand separators
 */
export function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat('en-US', options).format(value);
}

/**
 * Formats a currency value
 */
export function formatCurrency(value: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(value);
}

/**
 * Truncates text to a specified length with ellipsis
 */
export function truncateText(text: string, maxLength: number, suffix: string = '...'): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.slice(0, maxLength - suffix.length) + suffix;
}

/**
 * Capitalizes the first letter of a string
 */
export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

/**
 * Capitalizes the first letter of each word
 */
export function capitalizeWords(text: string): string {
  return text.replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Converts camelCase to kebab-case
 */
export function camelToKebab(text: string): string {
  return text.replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
}

/**
 * Converts kebab-case to camelCase
 */
export function kebabToCamel(text: string): string {
  return text.replace(/-([a-z])/g, (_, char) => char.toUpperCase());
}

/**
 * Sanitizes text for display (removes HTML tags and encodes entities)
 */
export function sanitizeText(text: string): string {
  // Remove HTML tags
  const withoutTags = text.replace(/<[^>]*>/g, '');
  
  // Create a temporary element to decode HTML entities
  const element = document.createElement('div');
  element.innerHTML = withoutTags;
  
  return element.textContent || element.innerText || '';
}

/**
 * Formats processing progress with estimated time remaining
 */
export function formatProgress(
  progress: number,
  startTime: number = Date.now(),
  showTimeRemaining: boolean = true
): string {
  const percentage = formatPercentage(progress);
  
  if (!showTimeRemaining || progress <= 0 || progress >= 100) {
    return percentage;
  }
  
  const elapsed = Date.now() - startTime;
  const estimated = (elapsed / progress) * (100 - progress);
  const timeRemaining = formatDuration(estimated);
  
  return `${percentage} (${timeRemaining} remaining)`;
}

/**
 * Formats processing speed (pages per second, MB per second, etc.)
 */
export function formatProcessingSpeed(
  processed: number,
  unit: string,
  elapsedMs: number
): string {
  if (elapsedMs <= 0) return `0 ${unit}/s`;
  
  const speed = (processed / elapsedMs) * 1000; // Convert to per second
  
  if (speed < 1) {
    return `${(speed * 60).toFixed(1)} ${unit}/min`;
  }
  
  return `${speed.toFixed(1)} ${unit}/s`;
}

/**
 * Formats error messages for display
 */
export function formatErrorMessage(error: unknown): string {
  if (typeof error === 'string') {
    return error;
  }
  
  if (error instanceof Error) {
    return error.message;
  }
  
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message: unknown }).message);
  }
  
  return 'An unknown error occurred';
}

/**
 * Formats validation error messages
 */
export function formatValidationErrors(errors: Array<{ field?: string; message: string }>): string {
  if (errors.length === 0) {
    return '';
  }
  
  if (errors.length === 1) {
    const error = errors[0];
    return error.field ? `${capitalize(error.field)}: ${error.message}` : error.message;
  }
  
  return errors
    .map((error) => (error.field ? `${capitalize(error.field)}: ${error.message}` : error.message))
    .join('\n');
}

/**
 * Formats file size with appropriate units
 */
export function formatFileSize(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

/**
 * Formats page count (e.g., "1 page", "5 pages")
 */
export function formatPageCount(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? 'page' : 'pages'}`;
}

/**
 * Formats word count
 */
export function formatWordCount(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? 'word' : 'words'}`;
}

/**
 * Formats match count for redaction
 */
export function formatMatchCount(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? 'match' : 'matches'}`;
}

/**
 * Formats confidence score as percentage
 */
export function formatConfidence(confidence: number): string {
  return formatPercentage(confidence * 100, 0);
}

/**
 * Formats a list of items with proper grammar
 */
export function formatList(items: string[], conjunction: string = 'and'): string {
  if (items.length === 0) return '';
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} ${conjunction} ${items[1]}`;
  
  const allButLast = items.slice(0, -1);
  const last = items[items.length - 1];
  
  return `${allButLast.join(', ')}, ${conjunction} ${last}`;
}

/**
 * Formats processing status messages
 */
export function formatStatusMessage(
  status: string,
  currentStep?: string,
  totalSteps?: number,
  stepNumber?: number
): string {
  const statusFormatted = capitalize(status.replace(/[-_]/g, ' '));
  
  if (!currentStep) {
    return statusFormatted;
  }
  
  const stepFormatted = capitalize(currentStep.replace(/[-_]/g, ' '));
  
  if (totalSteps && stepNumber) {
    return `${statusFormatted}: ${stepFormatted} (${stepNumber}/${totalSteps})`;
  }
  
  return `${statusFormatted}: ${stepFormatted}`;
}

/**
 * Formats time remaining estimate
 */
export function formatTimeRemaining(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)} seconds`;
  }
  
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  
  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes} minutes`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours} hours`;
}

/**
 * Formats session timeout warnings
 */
export function formatSessionWarning(timeRemaining: number): string {
  const formatted = formatTimeRemaining(timeRemaining / 1000);
  return `Session expires in ${formatted}`;
}

/**
 * Formats responsive text based on screen size
 */
export function formatResponsiveText(
  text: string,
  maxLength: { mobile: number; tablet: number; desktop: number },
  currentBreakpoint: 'mobile' | 'tablet' | 'desktop'
): string {
  const length = maxLength[currentBreakpoint];
  return truncateText(text, length);
}

/**
 * Formats accessibility text for screen readers
 */
export function formatAriaLabel(baseText: string, context?: Record<string, string | number>): string {
  if (!context) {
    return baseText;
  }
  
  const contextText = Object.entries(context)
    .map(([key, value]) => `${key}: ${value}`)
    .join(', ');
  
  return `${baseText}, ${contextText}`;
}