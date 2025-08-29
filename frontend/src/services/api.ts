/**
 * Main API service for Django backend integration
 */

import axios, { 
  AxiosInstance, 
  AxiosRequestConfig, 
  AxiosResponse, 
  AxiosError,
  InternalAxiosRequestConfig
} from 'axios';
import type { APIResponse, APIError } from '@/types';
import { generateSessionId, getStoredSessionInfo, storeSessionInfo } from '@/utils/sessionUtils';

// API Configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api';
const DEFAULT_TIMEOUT = 30000; // 30 seconds
const UPLOAD_TIMEOUT = parseInt(process.env.NEXT_PUBLIC_UPLOAD_TIMEOUT || '300000', 10); // 5 minutes

// Rate limiting
const RATE_LIMIT_DELAY = 1000;
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;

/**
 * Utility to read cookie value
 */
function getCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()!.split(';').shift();
}

/**
 * Creates axios instance with default configuration
 */
function createAPIInstance(): AxiosInstance {
  const instance = axios.create({
    baseURL: API_BASE_URL,
    timeout: DEFAULT_TIMEOUT,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    withCredentials: true,
  });

  // Request interceptor
  instance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      // Add session ID to requests
      const sessionInfo = getStoredSessionInfo();
      if (sessionInfo?.sessionId) {
        config.headers['X-Session-ID'] = sessionInfo.sessionId;
      }

      // Add CSRF token if available
      const csrf = getCookie('csrftoken');
      if (csrf) {
        config.headers['X-CSRFToken'] = csrf;
      }
      config.headers['X-Requested-With'] = 'XMLHttpRequest';

      // Add request timestamp for debugging
      config.metadata = { startTime: Date.now() };

      // Log requests in development
      if (process.env.NODE_ENV === 'development') {
        console.log(`🚀 API Request: ${config.method?.toUpperCase()} ${config.url}`);
      }

      return config;
    },
    (error: AxiosError) => {
      console.error('❌ Request interceptor error:', error);
      return Promise.reject(error);
    }
  );

  // Response interceptor
  instance.interceptors.response.use(
    (response: AxiosResponse) => {
      // Calculate request duration
      const duration = Date.now() - (response.config.metadata?.startTime || 0);

      // Log responses in development
      if (process.env.NODE_ENV === 'development') {
        console.log(
          `✅ API Response: ${response.config.method?.toUpperCase()} ${response.config.url} (${duration}ms)`
        );
      }

      // Update session info if provided
      const sessionId = response.headers['x-session-id'];
      if (sessionId) {
        updateSessionFromResponse(sessionId);
      }

      return response;
    },
    (error: AxiosError) => {
      const duration = Date.now() - (error.config?.metadata?.startTime || 0);
      
      // Log errors in development
      if (process.env.NODE_ENV === 'development') {
        console.error(
          `❌ API Error: ${error.config?.method?.toUpperCase()} ${error.config?.url} (${duration}ms)`,
          error.response?.status,
          error.message
        );
      }

      // Transform error to our API error format
      const apiError = transformAxiosError(error);
      return Promise.reject(apiError);
    }
  );

  return instance;
}

/**
 * Main API instance
 */
export const api = createAPIInstance();

/**
 * API instance for file uploads with longer timeout
 */
export const uploadAPI = axios.create({
  baseURL: API_BASE_URL,
  timeout: UPLOAD_TIMEOUT,
  headers: {
    'Accept': 'application/json',
  },
  withCredentials: true,
});

// Apply same interceptors to upload API
uploadAPI.interceptors.request.use(api.interceptors.request.handlers[0]?.fulfilled);
uploadAPI.interceptors.response.use(
  api.interceptors.response.handlers[0]?.fulfilled,
  api.interceptors.response.handlers[0]?.rejected
);

/**
 * Transforms axios errors to our API error format
 */
function transformAxiosError(error: AxiosError): APIError {
  const timestamp = new Date().toISOString();

  // Network error
  if (!error.response) {
    return {
      code: 'NETWORK_ERROR',
      message: 'Network error occurred. Please check your connection.',
      timestamp,
    };
  }

  // Server error response
  const response = error.response;
  const status = response.status;
  const data = response.data as any;

  // Extract error information from response
  let code = `HTTP_${status}`;
  let message = error.message;
  let details = {};
  let field: string | undefined;

  if (data && typeof data === 'object') {
    // Django REST framework error format
    if (data.detail) {
      message = data.detail;
    } else if (data.error) {
      message = data.error;
      code = data.code || code;
    } else if (data.message) {
      message = data.message;
      code = data.code || code;
    }

    // Field-specific errors
    if (data.field) {
      field = data.field;
    }

    // Additional details
    if (data.details) {
      details = data.details;
    }
  }

  // Common HTTP status codes
  switch (status) {
    case 400:
      code = 'BAD_REQUEST';
      message = message || 'Invalid request data';
      break;
    case 401:
      code = 'UNAUTHORIZED';
      message = message || 'Authentication required';
      break;
    case 403:
      code = 'FORBIDDEN';
      message = message || 'Access forbidden';
      break;
    case 404:
      code = 'NOT_FOUND';
      message = message || 'Resource not found';
      break;
    case 413:
      code = 'FILE_TOO_LARGE';
      message = message || 'File size exceeds limit';
      break;
    case 429:
      code = 'RATE_LIMITED';
      message = message || 'Too many requests';
      break;
    case 500:
      code = 'SERVER_ERROR';
      message = message || 'Internal server error';
      break;
    case 502:
      code = 'BAD_GATEWAY';
      message = message || 'Server temporarily unavailable';
      break;
    case 503:
      code = 'SERVICE_UNAVAILABLE';
      message = message || 'Service temporarily unavailable';
      break;
  }

  return {
    code,
    message,
    details,
    field,
    timestamp,
  };
}

/**
 * Updates session information from API response
 */
function updateSessionFromResponse(sessionId: string): void {
  const currentSession = getStoredSessionInfo();
  
  if (!currentSession || currentSession.sessionId !== sessionId) {
    // Create or update session info
    const sessionInfo = {
      sessionId,
      createdAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(), // 8 hours
      isActive: true,
      documentsCount: currentSession?.documentsCount || 0,
      storageUsed: currentSession?.storageUsed || 0,
    };
    
    storeSessionInfo(sessionInfo);
  }
}

/**
 * Generic API request wrapper with retry logic
 */
export async function apiRequest<T>(
  config: AxiosRequestConfig,
  retries: number = MAX_RETRIES
): Promise<APIResponse<T>> {
  try {
    const response = await api.request<APIResponse<T>>(config);
    return response.data;
  } catch (error) {
    const apiError = error as APIError;
    
    // Retry on certain errors
    if (retries > 0 && isRetryableError(apiError)) {
      await delay(RETRY_DELAY);
      return apiRequest<T>(config, retries - 1);
    }
    
    // Return error response format
    return {
      success: false,
      error: apiError,
      timestamp: new Date().toISOString(),
    };
  }
}

/**
 * Determines if an error is retryable
 */
function isRetryableError(error: APIError): boolean {
  const retryableCodes = [
    'NETWORK_ERROR',
    'HTTP_502',
    'HTTP_503',
    'HTTP_504',
    'RATE_LIMITED',
  ];
  
  return retryableCodes.includes(error.code);
}

/**
 * Delay utility for retries
 */
function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * GET request helper
 */
export async function get<T>(
  url: string,
  config?: AxiosRequestConfig
): Promise<APIResponse<T>> {
  return apiRequest<T>({ ...config, method: 'GET', url });
}

/**
 * POST request helper
 */
export async function post<T>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<APIResponse<T>> {
  return apiRequest<T>({ ...config, method: 'POST', url, data });
}

/**
 * PUT request helper
 */
export async function put<T>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<APIResponse<T>> {
  return apiRequest<T>({ ...config, method: 'PUT', url, data });
}

/**
 * PATCH request helper
 */
export async function patch<T>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<APIResponse<T>> {
  return apiRequest<T>({ ...config, method: 'PATCH', url, data });
}

/**
 * DELETE request helper
 */
export async function del<T>(
  url: string,
  config?: AxiosRequestConfig
): Promise<APIResponse<T>> {
  return apiRequest<T>({ ...config, method: 'DELETE', url });
}

/**
 * Upload request helper with progress tracking
 */
export async function upload<T>(
  url: string,
  formData: FormData,
  onProgress?: (progress: number) => void,
  config: AxiosRequestConfig = {}
): Promise<APIResponse<T>> {
  try {
    const response = await uploadAPI.post<APIResponse<T>>(url, formData, {
      ...config,
      signal: config.signal,
      headers: {
        'Content-Type': 'multipart/form-data',
        ...(config.headers || {}),
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percentage = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percentage);
        }
      },
    });
    
    return response.data;
  } catch (error) {
    const apiError = error as APIError;
    return {
      success: false,
      error: apiError,
      timestamp: new Date().toISOString(),
    };
  }
}

/**
 * Download request helper
 */
export async function download(
  url: string,
  config?: AxiosRequestConfig
): Promise<Blob> {
  const response = await api.get(url, {
    ...config,
    responseType: 'blob',
  });
  
  return response.data;
}

/**
 * Health check endpoint
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const response = await get<{ status: string }>('/health/');
    return response.success && response.data?.status === 'ok';
  } catch {
    return false;
  }
}

/**
 * Initialize session
 */
export async function initializeSession(): Promise<string> {
  let sessionInfo = getStoredSessionInfo();
  
  if (!sessionInfo) {
    const sessionId = generateSessionId();
    sessionInfo = {
      sessionId,
      createdAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
      isActive: true,
      documentsCount: 0,
      storageUsed: 0,
    };
    
    storeSessionInfo(sessionInfo);
  }
  
  return sessionInfo.sessionId;
}

/**
 * Rate limiting utility
 */
let lastRequestTime = 0;

export function enforceRateLimit(): Promise<void> {
  const now = Date.now();
  const timeSinceLastRequest = now - lastRequestTime;
  
  if (timeSinceLastRequest < RATE_LIMIT_DELAY) {
    const delayNeeded = RATE_LIMIT_DELAY - timeSinceLastRequest;
    lastRequestTime = now + delayNeeded;
    return delay(delayNeeded);
  }
  
  lastRequestTime = now;
  return Promise.resolve();
}

/**
 * Cancel token source for request cancellation
 */
export function createCancelToken() {
  return axios.CancelToken.source();
}

/**
 * Create AbortController for request cancellation
 */
export function createAbortController() {
  return new AbortController();
}

/**
 * Check if error is a cancellation
 */
export function isCancelError(error: any): boolean {
  return axios.isCancel(error);
}

// Export types for use in components
export type { AxiosRequestConfig, AxiosResponse, AxiosError };