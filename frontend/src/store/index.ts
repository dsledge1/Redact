/**
 * Store index file for clean exports
 */

// Main store exports
export { 
  usePDFStore,
  useDocument,
  useProcessing,
  useUpload,
  useRedaction,
  useSession,
  useUI,
  useUploadActions,
  useDocumentActions,
  useRedactionActions,
  useSessionActions,
  useUIActions,
} from './pdfStore';

// Re-export types for convenience
export type {
  PDFDocument,
  RedactionMatch,
  ManualRedaction,
  RedactionSettings,
  ProcessingJob,
  APIError,
  SessionInfo,
  JobStatus,
  UploadProgress,
} from '@/types';

// Store debugging utilities for development
export const storeDebug = {
  getState: () => {
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
      return (window as any).__ZUSTAND_STORES__ || {};
    }
    return {};
  },
  
  logState: (storeName: string = 'PDFStore') => {
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
      const stores = (window as any).__ZUSTAND_STORES__;
      if (stores && stores[storeName]) {
        console.log(`${storeName} State:`, stores[storeName]);
      }
    }
  },
  
  resetStore: () => {
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
      const { usePDFStore } = require('./pdfStore');
      usePDFStore.getState().reset();
      console.log('Store reset to initial state');
    }
  },
};