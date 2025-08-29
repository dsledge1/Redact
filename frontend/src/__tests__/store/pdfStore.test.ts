import { renderHook, act } from '@testing-library/react';
import { usePDFStore } from '@/store/pdfStore';

// Mock the PDF service
jest.mock('@/services/pdfService', () => ({
  PDFService: {
    FileUpload: {
      uploadFile: jest.fn(),
    },
    Document: {
      getDocument: jest.fn(),
    },
    Redaction: {
      initiateRedaction: jest.fn(),
      getRedactionMatches: jest.fn(),
      approveMatches: jest.fn(),
      rejectMatches: jest.fn(),
      finalizeRedaction: jest.fn(),
    },
    Job: {
      pollJobStatus: jest.fn(),
      cancelJob: jest.fn(),
      stopPolling: jest.fn(),
    },
    Session: {
      getSessionInfo: jest.fn(),
      extendSession: jest.fn(),
      cleanupSession: jest.fn(),
    },
  },
}));

// Mock session utils
jest.mock('@/utils/sessionUtils', () => ({
  getStoredSessionInfo: jest.fn(),
  storeSessionInfo: jest.fn(),
  createNewSession: jest.fn(),
  isSessionValid: jest.fn(),
}));

import { PDFService } from '@/services/pdfService';
import { getStoredSessionInfo, createNewSession, isSessionValid } from '@/utils/sessionUtils';

const mockPDFService = PDFService as jest.Mocked<typeof PDFService>;
const mockGetStoredSessionInfo = getStoredSessionInfo as jest.MockedFunction<typeof getStoredSessionInfo>;
const mockCreateNewSession = createNewSession as jest.MockedFunction<typeof createNewSession>;
const mockIsSessionValid = isSessionValid as jest.MockedFunction<typeof isSessionValid>;

describe('PDF Store', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Reset localStorage
    localStorage.clear();
    
    // Mock session utilities
    mockGetStoredSessionInfo.mockReturnValue(null);
    mockCreateNewSession.mockReturnValue({
      sessionId: 'test-session',
      createdAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
      isActive: true,
      documentsCount: 0,
      storageUsed: 0,
    });
    mockIsSessionValid.mockReturnValue(true);
  });

  describe('Initial State', () => {
    it('has correct initial state', () => {
      const { result } = renderHook(() => usePDFStore());
      
      expect(result.current.document).toBeNull();
      expect(result.current.processing.status).toBe('pending');
      expect(result.current.processing.progress).toBe(0);
      expect(result.current.upload.isUploading).toBe(false);
      expect(result.current.redaction.searchTerms).toEqual([]);
      expect(result.current.redaction.fuzzyThreshold).toBe(0.8);
      expect(result.current.ui.currentView).toBe('upload');
      expect(result.current.ui.sidebarOpen).toBe(true);
    });
  });

  describe('File Upload', () => {
    it('uploads file successfully', async () => {
      const mockFile = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
      const mockUploadResponse = {
        success: true,
        data: {
          documentId: 'doc-123',
          fileName: 'test.pdf',
          fileSize: 1024,
          pageCount: 1,
          sessionId: 'test-session',
        },
        timestamp: new Date().toISOString(),
      };
      
      const mockDocument = {
        id: 'doc-123',
        fileName: 'test.pdf',
        originalName: 'test.pdf',
        fileSize: 1024,
        pageCount: 1,
        uploadedAt: new Date().toISOString(),
        sessionId: 'test-session',
        mimeType: 'application/pdf',
        status: 'ready' as const,
        processingHistory: [],
      };

      mockPDFService.FileUpload.uploadFile.mockResolvedValue(mockUploadResponse);
      mockPDFService.Document.getDocument.mockResolvedValue({
        success: true,
        data: mockDocument,
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.uploadFile(mockFile);
      });

      expect(result.current.upload.isUploading).toBe(false);
      expect(result.current.document).toEqual(mockDocument);
      expect(result.current.ui.currentView).toBe('viewer');
    });

    it('handles upload progress', async () => {
      const mockFile = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
      const progressCallback = jest.fn();

      mockPDFService.FileUpload.uploadFile.mockImplementation(async (file, onProgress) => {
        if (onProgress) {
          onProgress(50);
        }
        return {
          success: true,
          data: {
            documentId: 'doc-123',
            fileName: 'test.pdf',
            fileSize: 1024,
            pageCount: 1,
            sessionId: 'test-session',
          },
          timestamp: new Date().toISOString(),
        };
      });

      mockPDFService.Document.getDocument.mockResolvedValue({
        success: true,
        data: {
          id: 'doc-123',
          fileName: 'test.pdf',
          originalName: 'test.pdf',
          fileSize: 1024,
          pageCount: 1,
          uploadedAt: new Date().toISOString(),
          sessionId: 'test-session',
          mimeType: 'application/pdf',
          status: 'ready' as const,
          processingHistory: [],
        },
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.uploadFile(mockFile, progressCallback);
      });

      expect(progressCallback).toHaveBeenCalled();
    });

    it('handles upload errors', async () => {
      const mockFile = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
      const error = new Error('Upload failed');

      mockPDFService.FileUpload.uploadFile.mockRejectedValue(error);

      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.uploadFile(mockFile);
      });

      expect(result.current.upload.error).toEqual(
        expect.objectContaining({
          code: 'UPLOAD_ERROR',
          message: 'Upload failed',
        })
      );
      expect(result.current.upload.isUploading).toBe(false);
    });

    it('cancels upload', async () => {
      const { result } = renderHook(() => usePDFStore());

      act(() => {
        result.current.cancelUpload();
      });

      expect(result.current.upload.isUploading).toBe(false);
      expect(result.current.upload.progress).toBeNull();
    });
  });

  describe('Document Management', () => {
    it('loads document successfully', async () => {
      const mockDocument = {
        id: 'doc-123',
        fileName: 'test.pdf',
        originalName: 'test.pdf',
        fileSize: 1024,
        pageCount: 1,
        uploadedAt: new Date().toISOString(),
        sessionId: 'test-session',
        mimeType: 'application/pdf',
        status: 'ready' as const,
        processingHistory: [],
      };

      mockPDFService.Document.getDocument.mockResolvedValue({
        success: true,
        data: mockDocument,
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.loadDocument('doc-123');
      });

      expect(result.current.document).toEqual(mockDocument);
      expect(result.current.ui.currentView).toBe('viewer');
    });

    it('handles document load errors', async () => {
      mockPDFService.Document.getDocument.mockResolvedValue({
        success: false,
        error: {
          code: 'NOT_FOUND',
          message: 'Document not found',
          timestamp: new Date().toISOString(),
        },
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.loadDocument('invalid-id');
      });

      expect(result.current.processing.errors).toHaveLength(1);
      expect(result.current.processing.errors[0]).toEqual(
        expect.objectContaining({
          code: 'LOAD_DOCUMENT_ERROR',
          message: 'Document not found',
        })
      );
    });

    it('clears document', () => {
      const { result } = renderHook(() => usePDFStore());

      // Set some initial state
      act(() => {
        result.current.addManualRedaction({
          pageNumber: 1,
          boundingBox: { x: 0, y: 0, width: 100, height: 20 },
        });
      });

      act(() => {
        result.current.clearDocument();
      });

      expect(result.current.document).toBeNull();
      expect(result.current.redaction.manualRedactions).toHaveLength(0);
      expect(result.current.ui.currentView).toBe('upload');
    });
  });

  describe('Redaction Management', () => {
    it('initiates redaction successfully', async () => {
      const mockDocument = {
        id: 'doc-123',
        fileName: 'test.pdf',
        originalName: 'test.pdf',
        fileSize: 1024,
        pageCount: 1,
        uploadedAt: new Date().toISOString(),
        sessionId: 'test-session',
        mimeType: 'application/pdf',
        status: 'ready' as const,
        processingHistory: [],
      };

      mockPDFService.Redaction.initiateRedaction.mockResolvedValue({
        success: true,
        data: { jobId: 'job-123' },
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      // Set document first
      act(() => {
        result.current.document = mockDocument;
      });

      await act(async () => {
        await result.current.initiateRedaction(['sensitive data']);
      });

      expect(result.current.redaction.searchTerms).toEqual(['sensitive data']);
      expect(result.current.processing.status).toBe('running');
      expect(result.current.processing.jobId).toBe('job-123');
      expect(result.current.ui.currentView).toBe('processing');
    });

    it('approves redaction match', () => {
      const { result } = renderHook(() => usePDFStore());

      const mockMatch = {
        id: 'match-123',
        text: 'sensitive',
        pageNumber: 1,
        boundingBox: { x: 0, y: 0, width: 100, height: 20 },
        confidence: 0.9,
        pattern: 'sensitive',
        type: 'custom' as const,
        status: 'pending' as const,
      };

      // Add match first
      act(() => {
        result.current.redaction.matches = [mockMatch];
      });

      act(() => {
        result.current.approveMatch('match-123');
      });

      expect(result.current.redaction.matches[0].status).toBe('approved');
    });

    it('rejects redaction match', () => {
      const { result } = renderHook(() => usePDFStore());

      const mockMatch = {
        id: 'match-123',
        text: 'sensitive',
        pageNumber: 1,
        boundingBox: { x: 0, y: 0, width: 100, height: 20 },
        confidence: 0.9,
        pattern: 'sensitive',
        type: 'custom' as const,
        status: 'pending' as const,
      };

      // Add match first
      act(() => {
        result.current.redaction.matches = [mockMatch];
      });

      act(() => {
        result.current.rejectMatch('match-123');
      });

      expect(result.current.redaction.matches[0].status).toBe('rejected');
    });

    it('adds manual redaction', () => {
      const { result } = renderHook(() => usePDFStore());

      const redaction = {
        pageNumber: 1,
        boundingBox: { x: 10, y: 10, width: 100, height: 20 },
        reason: 'Contains sensitive information',
      };

      act(() => {
        result.current.addManualRedaction(redaction);
      });

      expect(result.current.redaction.manualRedactions).toHaveLength(1);
      expect(result.current.redaction.manualRedactions[0]).toEqual(
        expect.objectContaining({
          ...redaction,
          id: expect.any(String),
          createdAt: expect.any(String),
        })
      );
    });

    it('removes manual redaction', () => {
      const { result } = renderHook(() => usePDFStore());

      // Add redaction first
      act(() => {
        result.current.addManualRedaction({
          pageNumber: 1,
          boundingBox: { x: 0, y: 0, width: 100, height: 20 },
        });
      });

      const redactionId = result.current.redaction.manualRedactions[0].id;

      act(() => {
        result.current.removeManualRedaction(redactionId);
      });

      expect(result.current.redaction.manualRedactions).toHaveLength(0);
    });

    it('updates redaction settings', () => {
      const { result } = renderHook(() => usePDFStore());

      const newSettings = {
        fuzzyThreshold: 0.9,
        caseSensitive: true,
      };

      act(() => {
        result.current.updateRedactionSettings(newSettings);
      });

      expect(result.current.redaction.settings.fuzzyThreshold).toBe(0.9);
      expect(result.current.redaction.settings.caseSensitive).toBe(true);
    });
  });

  describe('Session Management', () => {
    it('initializes session', async () => {
      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.initializeSession();
      });

      expect(result.current.session.isValid).toBe(true);
      expect(result.current.session.info).toEqual(
        expect.objectContaining({
          sessionId: 'test-session',
          isActive: true,
        })
      );
    });

    it('checks session validity', async () => {
      mockPDFService.Session.getSessionInfo.mockResolvedValue({
        success: true,
        data: {
          sessionId: 'test-session',
          createdAt: new Date().toISOString(),
          expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
          isActive: true,
          documentsCount: 1,
          storageUsed: 1024,
        },
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      let isValid: boolean = false;
      await act(async () => {
        isValid = await result.current.checkSession();
      });

      expect(isValid).toBe(true);
      expect(result.current.session.isValid).toBe(true);
    });

    it('extends session', async () => {
      const extendedSessionInfo = {
        sessionId: 'test-session',
        createdAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 16 * 60 * 60 * 1000).toISOString(),
        isActive: true,
        documentsCount: 1,
        storageUsed: 1024,
      };

      mockPDFService.Session.extendSession.mockResolvedValue({
        success: true,
        data: extendedSessionInfo,
        timestamp: new Date().toISOString(),
      });

      const { result } = renderHook(() => usePDFStore());

      await act(async () => {
        await result.current.extendSession();
      });

      expect(result.current.session.info).toEqual(extendedSessionInfo);
      expect(result.current.session.showWarning).toBe(false);
    });
  });

  describe('UI State Management', () => {
    it('toggles sidebar', () => {
      const { result } = renderHook(() => usePDFStore());

      act(() => {
        result.current.setSidebarOpen(false);
      });

      expect(result.current.ui.sidebarOpen).toBe(false);

      act(() => {
        result.current.setSidebarOpen(true);
      });

      expect(result.current.ui.sidebarOpen).toBe(true);
    });

    it('changes current view', () => {
      const { result } = renderHook(() => usePDFStore());

      act(() => {
        result.current.setCurrentView('redaction');
      });

      expect(result.current.ui.currentView).toBe('redaction');
    });

    it('toggles progress display', () => {
      const { result } = renderHook(() => usePDFStore());

      act(() => {
        result.current.setShowProgress(true);
      });

      expect(result.current.ui.showProgress).toBe(true);

      act(() => {
        result.current.setShowProgress(false);
      });

      expect(result.current.ui.showProgress).toBe(false);
    });
  });

  describe('Store Reset', () => {
    it('resets store to initial state', () => {
      const { result } = renderHook(() => usePDFStore());

      // Modify some state
      act(() => {
        result.current.setSidebarOpen(false);
        result.current.setCurrentView('redaction');
        result.current.addManualRedaction({
          pageNumber: 1,
          boundingBox: { x: 0, y: 0, width: 100, height: 20 },
        });
      });

      // Verify state is modified
      expect(result.current.ui.sidebarOpen).toBe(false);
      expect(result.current.ui.currentView).toBe('redaction');
      expect(result.current.redaction.manualRedactions).toHaveLength(1);

      // Reset
      act(() => {
        result.current.reset();
      });

      // Verify state is reset
      expect(result.current.ui.sidebarOpen).toBe(true);
      expect(result.current.ui.currentView).toBe('upload');
      expect(result.current.redaction.manualRedactions).toHaveLength(0);
      expect(result.current.document).toBeNull();
    });
  });
});