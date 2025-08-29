/**
 * Session management utility functions
 */

import type { SessionInfo, SessionStatus } from '@/types';

// Session constants
const SESSION_STORAGE_KEY = 'ultimate_pdf_session';
const SESSION_TIMEOUT = parseInt(process.env.NEXT_PUBLIC_SESSION_TIMEOUT || '28800000', 10); // 8 hours
const WARNING_THRESHOLD = 900000; // 15 minutes
const HEARTBEAT_INTERVAL = 300000; // 5 minutes

/**
 * Generates a unique session ID
 */
export function generateSessionId(): string {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 15);
  const browser = typeof window !== 'undefined' ? 
    btoa(navigator.userAgent).substring(0, 8) : 'server';
  
  return `${timestamp}-${random}-${browser}`;
}

/**
 * Validates session ID format
 */
export function validateSessionId(sessionId: string): boolean {
  if (!sessionId || typeof sessionId !== 'string') {
    return false;
  }
  
  // Check format: timestamp-random-browser
  const parts = sessionId.split('-');
  if (parts.length !== 3) {
    return false;
  }
  
  const [timestamp, random, browser] = parts;
  
  // Validate timestamp
  const ts = parseInt(timestamp, 10);
  if (isNaN(ts) || ts <= 0) {
    return false;
  }
  
  // Validate random string
  if (!random || random.length < 10) {
    return false;
  }
  
  // Validate browser identifier
  if (!browser || browser.length < 4) {
    return false;
  }
  
  return true;
}

/**
 * Stores session information in localStorage
 */
export function storeSessionInfo(sessionInfo: SessionInfo): void {
  if (typeof window === 'undefined') return;
  
  try {
    const data = {
      ...sessionInfo,
      lastUpdated: new Date().toISOString(),
    };
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(data));
  } catch (error) {
    console.warn('Failed to store session info:', error);
  }
}

/**
 * Retrieves session information from localStorage
 */
export function getStoredSessionInfo(): SessionInfo | null {
  if (typeof window === 'undefined') return null;
  
  try {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!stored) return null;
    
    const data = JSON.parse(stored);
    
    // Validate stored data
    if (!data.sessionId || !validateSessionId(data.sessionId)) {
      removeStoredSessionInfo();
      return null;
    }
    
    return data;
  } catch (error) {
    console.warn('Failed to retrieve session info:', error);
    removeStoredSessionInfo();
    return null;
  }
}

/**
 * Removes session information from localStorage
 */
export function removeStoredSessionInfo(): void {
  if (typeof window === 'undefined') return;
  
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (error) {
    console.warn('Failed to remove session info:', error);
  }
}

/**
 * Checks if a session is still valid based on expiration time
 */
export function isSessionValid(sessionInfo: SessionInfo): boolean {
  if (!sessionInfo || !sessionInfo.expiresAt) {
    return false;
  }
  
  const expirationTime = new Date(sessionInfo.expiresAt).getTime();
  const currentTime = Date.now();
  
  return currentTime < expirationTime;
}

/**
 * Calculates time remaining until session expires
 */
export function getTimeRemaining(sessionInfo: SessionInfo): number {
  if (!sessionInfo || !sessionInfo.expiresAt) {
    return 0;
  }
  
  const expirationTime = new Date(sessionInfo.expiresAt).getTime();
  const currentTime = Date.now();
  
  return Math.max(0, expirationTime - currentTime);
}

/**
 * Gets current session status including warnings
 */
export function getSessionStatus(sessionInfo: SessionInfo | null): SessionStatus {
  if (!sessionInfo) {
    return {
      isValid: false,
      timeRemaining: 0,
      warningThreshold: WARNING_THRESHOLD,
      autoExtendEnabled: false,
    };
  }
  
  const timeRemaining = getTimeRemaining(sessionInfo);
  const isValid = timeRemaining > 0;
  
  return {
    isValid,
    timeRemaining,
    warningThreshold: WARNING_THRESHOLD,
    autoExtendEnabled: isValid && timeRemaining > WARNING_THRESHOLD,
  };
}

/**
 * Checks if session warning should be shown
 */
export function shouldShowSessionWarning(sessionInfo: SessionInfo | null): boolean {
  if (!sessionInfo) return false;
  
  const timeRemaining = getTimeRemaining(sessionInfo);
  return timeRemaining > 0 && timeRemaining <= WARNING_THRESHOLD;
}

/**
 * Creates a new session with default values
 */
export function createNewSession(sessionId?: string): SessionInfo {
  const id = sessionId || generateSessionId();
  const now = new Date();
  const expiresAt = new Date(now.getTime() + SESSION_TIMEOUT);
  
  return {
    sessionId: id,
    createdAt: now.toISOString(),
    expiresAt: expiresAt.toISOString(),
    isActive: true,
    documentsCount: 0,
    storageUsed: 0,
  };
}

/**
 * Updates session expiration time (extends session)
 */
export function extendSession(sessionInfo: SessionInfo, additionalTime?: number): SessionInfo {
  const extension = additionalTime || SESSION_TIMEOUT;
  const now = new Date();
  const newExpirationTime = new Date(now.getTime() + extension);
  
  return {
    ...sessionInfo,
    expiresAt: newExpirationTime.toISOString(),
    isActive: true,
  };
}

/**
 * Marks session as inactive
 */
export function deactivateSession(sessionInfo: SessionInfo): SessionInfo {
  return {
    ...sessionInfo,
    isActive: false,
  };
}

/**
 * Migrates session data for browser/device changes
 */
export function migrateSessionData(oldSession: SessionInfo, newSessionId: string): SessionInfo {
  return {
    ...oldSession,
    sessionId: newSessionId,
    createdAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + SESSION_TIMEOUT).toISOString(),
  };
}

/**
 * Cleans up expired session data
 */
export function cleanupExpiredSession(): void {
  const stored = getStoredSessionInfo();
  if (stored && !isSessionValid(stored)) {
    removeStoredSessionInfo();
    
    // Clear any related data
    if (typeof window !== 'undefined') {
      try {
        // Clear session-related storage
        Object.keys(localStorage).forEach(key => {
          if (key.startsWith('ultimate_pdf_')) {
            localStorage.removeItem(key);
          }
        });
      } catch (error) {
        console.warn('Failed to cleanup expired session data:', error);
      }
    }
  }
}

/**
 * Sets up automatic session monitoring
 */
export function setupSessionMonitoring(
  onWarning: (timeRemaining: number) => void,
  onExpired: () => void,
  onExtended: (newExpirationTime: string) => void
): () => void {
  if (typeof window === 'undefined') {
    return () => {}; // No-op for SSR
  }
  
  let warningShown = false;
  
  const checkSession = (): void => {
    const sessionInfo = getStoredSessionInfo();
    if (!sessionInfo) {
      onExpired();
      return;
    }
    
    const status = getSessionStatus(sessionInfo);
    
    if (!status.isValid) {
      onExpired();
      return;
    }
    
    if (shouldShowSessionWarning(sessionInfo) && !warningShown) {
      onWarning(status.timeRemaining);
      warningShown = true;
    }
    
    // Reset warning flag if we're back in safe territory
    if (status.timeRemaining > WARNING_THRESHOLD && warningShown) {
      warningShown = false;
    }
  };
  
  // Initial check
  checkSession();
  
  // Set up periodic monitoring
  const interval = setInterval(checkSession, HEARTBEAT_INTERVAL);
  
  // Set up page visibility change monitoring
  const handleVisibilityChange = (): void => {
    if (!document.hidden) {
      checkSession();
    }
  };
  
  document.addEventListener('visibilitychange', handleVisibilityChange);
  
  // Cleanup function
  return () => {
    clearInterval(interval);
    document.removeEventListener('visibilitychange', handleVisibilityChange);
  };
}

/**
 * Handles session recovery after page reload
 */
export function recoverSession(): SessionInfo | null {
  cleanupExpiredSession();
  return getStoredSessionInfo();
}

/**
 * Generates session analytics data
 */
export function getSessionAnalytics(sessionInfo: SessionInfo): Record<string, unknown> {
  const now = Date.now();
  const created = new Date(sessionInfo.createdAt).getTime();
  const duration = now - created;
  
  return {
    sessionId: sessionInfo.sessionId,
    duration,
    documentsProcessed: sessionInfo.documentsCount,
    storageUsed: sessionInfo.storageUsed,
    isActive: sessionInfo.isActive,
    remainingTime: getTimeRemaining(sessionInfo),
    createdAt: sessionInfo.createdAt,
  };
}

/**
 * Validates session security token (placeholder for future implementation)
 */
export function validateSessionToken(token: string): boolean {
  // Placeholder for token validation logic
  // In a real implementation, this would verify JWT or similar
  return token && token.length > 10;
}

/**
 * Encrypts sensitive session data (placeholder)
 */
export function encryptSessionData(data: Record<string, unknown>): string {
  // Placeholder for encryption logic
  // In a real implementation, this would use proper encryption
  return btoa(JSON.stringify(data));
}

/**
 * Decrypts sensitive session data (placeholder)
 */
export function decryptSessionData(encryptedData: string): Record<string, unknown> | null {
  try {
    // Placeholder for decryption logic
    return JSON.parse(atob(encryptedData));
  } catch {
    return null;
  }
}

/**
 * Creates session debugging information
 */
export function getSessionDebugInfo(sessionInfo: SessionInfo | null): Record<string, unknown> {
  if (!sessionInfo) {
    return {
      status: 'No session found',
      stored: !!getStoredSessionInfo(),
      timestamp: new Date().toISOString(),
    };
  }
  
  const status = getSessionStatus(sessionInfo);
  
  return {
    sessionId: sessionInfo.sessionId,
    status: status.isValid ? 'Valid' : 'Invalid',
    timeRemaining: status.timeRemaining,
    timeRemainingFormatted: Math.floor(status.timeRemaining / 1000 / 60) + ' minutes',
    warningThreshold: status.warningThreshold,
    shouldWarn: shouldShowSessionWarning(sessionInfo),
    createdAt: sessionInfo.createdAt,
    expiresAt: sessionInfo.expiresAt,
    documentsCount: sessionInfo.documentsCount,
    storageUsed: sessionInfo.storageUsed,
    isActive: sessionInfo.isActive,
    timestamp: new Date().toISOString(),
  };
}