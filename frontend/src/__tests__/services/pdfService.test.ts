import { PDFService } from '@/services/pdfService';
import type { APIResponse } from '@/types';

// Mock the base API service
jest.mock('@/services/api', () => ({
  get: jest.fn(),
  post: jest.fn(),
  put: jest.fn(),
  del: jest.fn(),
  upload: jest.fn(),
  download: jest.fn(),
}));

import { get, post, put, del, upload, download } from '@/services/api';

const mockGet = get as jest.MockedFunction<typeof get>;
const mockPost = post as jest.MockedFunction<typeof post>;
const mockPut = put as jest.MockedFunction<typeof put>;
const mockDel = del as jest.MockedFunction<typeof del>;
const mockUpload = upload as jest.MockedFunction<typeof upload>;
const mockDownload = download as jest.MockedFunction<typeof download>;

describe('PDF Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('FileUploadService', () => {
    describe('uploadFile', () => {
      it('uploads file successfully', async () => {
        const mockFile = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
        const mockResponse: APIResponse<any> = {
          success: true,
          data: {
            documentId: 'doc-123',
            fileName: 'test.pdf',
            fileSize: 1024,
            pageCount: 1,
            sessionId: 'session-123',
          },
          timestamp: new Date().toISOString(),
        };

        mockUpload.mockResolvedValue(mockResponse);

        const result = await PDFService.FileUpload.uploadFile(mockFile);

        expect(mockUpload).toHaveBeenCalledWith(
          '/upload/',
          expect.any(FormData),
          undefined
        );
        expect(result).toEqual(mockResponse);
      });

      it('uploads file with progress callback', async () => {
        const mockFile = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
        const progressCallback = jest.fn();
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { documentId: 'doc-123' },
          timestamp: new Date().toISOString(),
        };

        mockUpload.mockResolvedValue(mockResponse);

        await PDFService.FileUpload.uploadFile(mockFile, progressCallback);

        expect(mockUpload).toHaveBeenCalledWith(
          '/upload/',
          expect.any(FormData),
          progressCallback
        );
      });
    });

    describe('getUploadStatus', () => {
      it('gets upload status', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { status: 'uploading', progress: 50 },
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.FileUpload.getUploadStatus('upload-123');

        expect(mockGet).toHaveBeenCalledWith('/upload/upload-123/status/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('cancelUpload', () => {
      it('cancels upload', async () => {
        const mockResponse: APIResponse<void> = {
          success: true,
          timestamp: new Date().toISOString(),
        };

        mockDel.mockResolvedValue(mockResponse);

        const result = await PDFService.FileUpload.cancelUpload('upload-123');

        expect(mockDel).toHaveBeenCalledWith('/upload/upload-123/');
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('DocumentService', () => {
    describe('getDocument', () => {
      it('retrieves document information', async () => {
        const mockDocument = {
          id: 'doc-123',
          fileName: 'test.pdf',
          originalName: 'test.pdf',
          fileSize: 1024,
          pageCount: 1,
          uploadedAt: new Date().toISOString(),
          sessionId: 'session-123',
          mimeType: 'application/pdf',
          status: 'ready',
          processingHistory: [],
        };

        const mockResponse: APIResponse<any> = {
          success: true,
          data: mockDocument,
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.Document.getDocument('doc-123');

        expect(mockGet).toHaveBeenCalledWith('/documents/doc-123/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('listDocuments', () => {
      it('lists all documents for session', async () => {
        const mockDocuments = [
          {
            id: 'doc-123',
            fileName: 'test1.pdf',
            fileSize: 1024,
          },
          {
            id: 'doc-456',
            fileName: 'test2.pdf',
            fileSize: 2048,
          },
        ];

        const mockResponse: APIResponse<any[]> = {
          success: true,
          data: mockDocuments,
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.Document.listDocuments();

        expect(mockGet).toHaveBeenCalledWith('/documents/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('deleteDocument', () => {
      it('deletes a document', async () => {
        const mockResponse: APIResponse<void> = {
          success: true,
          timestamp: new Date().toISOString(),
        };

        mockDel.mockResolvedValue(mockResponse);

        const result = await PDFService.Document.deleteDocument('doc-123');

        expect(mockDel).toHaveBeenCalledWith('/documents/doc-123/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('downloadDocument', () => {
      it('downloads document', async () => {
        const mockBlob = new Blob(['pdf content'], { type: 'application/pdf' });
        mockDownload.mockResolvedValue(mockBlob);

        const result = await PDFService.Document.downloadDocument('doc-123');

        expect(mockDownload).toHaveBeenCalledWith('/documents/doc-123/download/');
        expect(result).toEqual(mockBlob);
      });
    });
  });

  describe('RedactionService', () => {
    describe('initiateRedaction', () => {
      it('initiates redaction process', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'job-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Redaction.initiateRedaction(
          'doc-123',
          ['sensitive', 'confidential'],
          { fuzzyThreshold: 0.9, caseSensitive: true }
        );

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/redact/', {
          search_terms: ['sensitive', 'confidential'],
          fuzzy_threshold: 0.9,
          case_sensitive: true,
          whole_words_only: false,
          patterns: [],
          exclude_terms: [],
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('getRedactionMatches', () => {
      it('retrieves redaction matches', async () => {
        const mockMatches = [
          {
            id: 'match-123',
            text: 'sensitive',
            pageNumber: 1,
            boundingBox: { x: 0, y: 0, width: 100, height: 20 },
            confidence: 0.9,
            pattern: 'sensitive',
            type: 'custom',
            status: 'pending',
          },
        ];

        const mockResponse: APIResponse<any[]> = {
          success: true,
          data: mockMatches,
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.Redaction.getRedactionMatches('doc-123', 'job-123');

        expect(mockGet).toHaveBeenCalledWith('/documents/doc-123/redact/job-123/matches/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('approveMatches', () => {
      it('approves redaction matches', async () => {
        const mockResponse: APIResponse<void> = {
          success: true,
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Redaction.approveMatches(
          'doc-123',
          'job-123',
          ['match-1', 'match-2']
        );

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/redact/job-123/approve/', {
          match_ids: ['match-1', 'match-2'],
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('addManualRedaction', () => {
      it('adds manual redaction', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { redactionId: 'redaction-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const redaction = {
          pageNumber: 1,
          x: 10,
          y: 10,
          width: 100,
          height: 20,
          reason: 'Contains PII',
        };

        const result = await PDFService.Redaction.addManualRedaction('doc-123', 'job-123', redaction);

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/redact/job-123/manual/', {
          page_number: 1,
          bounding_box: { x: 10, y: 10, width: 100, height: 20 },
          reason: 'Contains PII',
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('finalizeRedaction', () => {
      it('finalizes redaction', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { downloadUrl: '/download/redacted-doc.pdf' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Redaction.finalizeRedaction('doc-123', 'job-123');

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/redact/job-123/finalize/');
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('SplittingService', () => {
    describe('splitByPageRanges', () => {
      it('splits PDF by page ranges', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'split-job-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const ranges = [{ start: 1, end: 3 }, { start: 4, end: 6 }];
        const result = await PDFService.Splitting.splitByPageRanges('doc-123', ranges);

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/split/', {
          method: 'page_ranges',
          page_ranges: ['1-3', '4-6'],
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('splitByPageCount', () => {
      it('splits PDF by page count', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'split-job-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Splitting.splitByPageCount('doc-123', 5);

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/split/', {
          method: 'page_count',
          pages_per_split: 5,
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('downloadSplitPart', () => {
      it('downloads specific split part', async () => {
        const mockBlob = new Blob(['split part content'], { type: 'application/pdf' });
        mockDownload.mockResolvedValue(mockBlob);

        const result = await PDFService.Splitting.downloadSplitPart('doc-123', 'job-123', 0);

        expect(mockDownload).toHaveBeenCalledWith('/documents/doc-123/split/job-123/download/0/');
        expect(result).toEqual(mockBlob);
      });
    });
  });

  describe('MergingService', () => {
    describe('mergeFiles', () => {
      it('merges multiple files', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'merge-job-123' },
          timestamp: new Date().toISOString(),
        };

        mockUpload.mockResolvedValue(mockResponse);

        const files = [
          new File(['pdf1'], 'file1.pdf', { type: 'application/pdf' }),
          new File(['pdf2'], 'file2.pdf', { type: 'application/pdf' }),
        ];

        const result = await PDFService.Merging.mergeFiles(files, {
          preserveBookmarks: true,
          bookmarkStrategy: 'merge-top-level',
        });

        expect(mockUpload).toHaveBeenCalledWith('/merge/', expect.any(FormData));
        expect(result).toEqual(mockResponse);
      });
    });

    describe('mergeDocuments', () => {
      it('merges existing documents', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'merge-job-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Merging.mergeDocuments(['doc-1', 'doc-2'], {
          preserveMetadata: true,
        });

        expect(mockPost).toHaveBeenCalledWith('/merge/', {
          document_ids: ['doc-1', 'doc-2'],
          preserve_bookmarks: true,
          preserve_metadata: true,
          bookmark_strategy: 'preserve-all',
        });
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('ExtractionService', () => {
    describe('extractData', () => {
      it('extracts data from PDF', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'extract-job-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Extraction.extractData('doc-123', {
          extractText: true,
          extractImages: false,
          extractTables: true,
          imageFormat: 'png',
          textFormat: 'markdown',
        });

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/extract/', {
          extract_text: true,
          extract_images: false,
          extract_tables: true,
          extract_metadata: true,
          extract_forms: true,
          image_format: 'png',
          text_format: 'markdown',
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('getExtractionResults', () => {
      it('gets extraction results', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: {
            text: { content: 'Extracted text', wordCount: 2 },
            images: [],
            tables: [],
            metadata: { title: 'Test PDF' },
          },
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.Extraction.getExtractionResults('doc-123', 'job-123');

        expect(mockGet).toHaveBeenCalledWith('/documents/doc-123/extract/job-123/results/');
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('JobService', () => {
    describe('getJobStatus', () => {
      it('gets job status', async () => {
        const mockJob = {
          id: 'job-123',
          documentId: 'doc-123',
          operation: 'redaction',
          status: 'running',
          progress: 50,
          currentStep: 'Processing pages',
          totalSteps: 3,
          startedAt: new Date().toISOString(),
        };

        const mockResponse: APIResponse<any> = {
          success: true,
          data: mockJob,
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.Job.getJobStatus('job-123');

        expect(mockGet).toHaveBeenCalledWith('/jobs/job-123/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('cancelJob', () => {
      it('cancels a job', async () => {
        const mockResponse: APIResponse<void> = {
          success: true,
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Job.cancelJob('job-123');

        expect(mockPost).toHaveBeenCalledWith('/jobs/job-123/cancel/');
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('SessionService', () => {
    describe('getSessionInfo', () => {
      it('gets current session info', async () => {
        const mockSession = {
          sessionId: 'session-123',
          createdAt: new Date().toISOString(),
          expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
          isActive: true,
          documentsCount: 2,
          storageUsed: 2048,
        };

        const mockResponse: APIResponse<any> = {
          success: true,
          data: mockSession,
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.Session.getSessionInfo();

        expect(mockGet).toHaveBeenCalledWith('/session/');
        expect(result).toEqual(mockResponse);
      });
    });

    describe('extendSession', () => {
      it('extends current session', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: {
            sessionId: 'session-123',
            expiresAt: new Date(Date.now() + 16 * 60 * 60 * 1000).toISOString(),
          },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Session.extendSession(8);

        expect(mockPost).toHaveBeenCalledWith('/session/extend/', {
          additional_hours: 8,
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('cleanupSession', () => {
      it('cleans up session data', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: {
            scheduled: true,
            executeAt: new Date().toISOString(),
            documentsToCleanup: 3,
            estimatedSize: 1024,
          },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.Session.cleanupSession();

        expect(mockPost).toHaveBeenCalledWith('/session/cleanup/');
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('OCRService', () => {
    describe('performOCR', () => {
      it('performs OCR on document', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: { jobId: 'ocr-job-123' },
          timestamp: new Date().toISOString(),
        };

        mockPost.mockResolvedValue(mockResponse);

        const result = await PDFService.OCR.performOCR('doc-123', {
          language: 'en',
          dpi: 300,
          preserveLayout: true,
        });

        expect(mockPost).toHaveBeenCalledWith('/documents/doc-123/ocr/', {
          language: 'en',
          dpi: 300,
          preserve_layout: true,
        });
        expect(result).toEqual(mockResponse);
      });
    });

    describe('getOCRResults', () => {
      it('gets OCR results', async () => {
        const mockResponse: APIResponse<any> = {
          success: true,
          data: {
            text: 'OCR extracted text',
            confidence: 0.95,
            pages: [{ pageNumber: 1, text: 'Page 1 text', confidence: 0.95 }],
          },
          timestamp: new Date().toISOString(),
        };

        mockGet.mockResolvedValue(mockResponse);

        const result = await PDFService.OCR.getOCRResults('doc-123', 'job-123');

        expect(mockGet).toHaveBeenCalledWith('/documents/doc-123/ocr/job-123/results/');
        expect(result).toEqual(mockResponse);
      });
    });
  });
});