/**
 * PDF-specific API service for all PDF operations
 */

import type {
  PDFDocument,
  UploadResult,
  ProcessingJob,
  ExtractedData,
  RedactionMatch,
  SplitInfo,
  MergeInfo,
  ProcessingResult,
  APIResponse,
  SessionInfo,
  CleanupStatus,
} from '@/types';

import { 
  get, 
  post, 
  put, 
  del, 
  upload, 
  download, 
  createCancelToken 
} from './api';

/**
 * File Upload Service
 */
export class FileUploadService {
  /**
   * Uploads a PDF file with progress tracking
   */
  static async uploadFile(
    file: File,
    onProgress?: (progress: number) => void,
    signal?: AbortSignal
  ): Promise<APIResponse<UploadResult>> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('original_name', file.name);
    formData.append('file_size', file.size.toString());

    return upload<UploadResult>('/upload/', formData, onProgress, { signal });
  }

  /**
   * Gets upload status
   */
  static async getUploadStatus(uploadId: string): Promise<APIResponse<{ status: string; progress: number }>> {
    return get<{ status: string; progress: number }>(`/upload/${uploadId}/status/`);
  }

  /**
   * Cancels an ongoing upload
   */
  static async cancelUpload(uploadId: string): Promise<APIResponse<void>> {
    return del<void>(`/upload/${uploadId}/`);
  }
}

/**
 * Document Management Service
 */
export class DocumentService {
  /**
   * Gets document information
   */
  static async getDocument(documentId: string): Promise<APIResponse<PDFDocument>> {
    return get<PDFDocument>(`/documents/${documentId}/`);
  }

  /**
   * Lists documents for current session
   */
  static async listDocuments(): Promise<APIResponse<PDFDocument[]>> {
    return get<PDFDocument[]>('/documents/');
  }

  /**
   * Deletes a document
   */
  static async deleteDocument(documentId: string): Promise<APIResponse<void>> {
    return del<void>(`/documents/${documentId}/`);
  }

  /**
   * Downloads original document
   */
  static async downloadDocument(documentId: string): Promise<Blob> {
    return download(`/documents/${documentId}/download/`);
  }

  /**
   * Gets document metadata
   */
  static async getDocumentMetadata(documentId: string): Promise<APIResponse<any>> {
    return get<any>(`/documents/${documentId}/metadata/`);
  }
}

/**
 * PDF Redaction Service
 */
export class RedactionService {
  /**
   * Initiates redaction process
   */
  static async initiateRedaction(
    documentId: string,
    searchTerms: string[],
    options: {
      fuzzyThreshold?: number;
      caseSensitive?: boolean;
      wholeWordsOnly?: boolean;
      patterns?: string[];
      excludeTerms?: string[];
    } = {}
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/redact/`, {
      search_terms: searchTerms,
      fuzzy_threshold: options.fuzzyThreshold || 0.8,
      case_sensitive: options.caseSensitive || false,
      whole_words_only: options.wholeWordsOnly || false,
      patterns: options.patterns || [],
      exclude_terms: options.excludeTerms || [],
    });
  }

  /**
   * Gets redaction matches for preview
   */
  static async getRedactionMatches(
    documentId: string,
    jobId: string
  ): Promise<APIResponse<RedactionMatch[]>> {
    return get<RedactionMatch[]>(`/documents/${documentId}/redact/${jobId}/matches/`);
  }

  /**
   * Approves specific redaction matches
   */
  static async approveMatches(
    documentId: string,
    jobId: string,
    matchIds: string[]
  ): Promise<APIResponse<void>> {
    return post<void>(`/documents/${documentId}/redact/${jobId}/approve/`, {
      match_ids: matchIds,
    });
  }

  /**
   * Rejects specific redaction matches
   */
  static async rejectMatches(
    documentId: string,
    jobId: string,
    matchIds: string[]
  ): Promise<APIResponse<void>> {
    return post<void>(`/documents/${documentId}/redact/${jobId}/reject/`, {
      match_ids: matchIds,
    });
  }

  /**
   * Updates single match status
   */
  static async updateMatchStatus(
    documentId: string,
    matchId: string,
    status: 'approved' | 'rejected'
  ): Promise<APIResponse<void>> {
    return put<void>(`/documents/${documentId}/redact/matches/${matchId}/`, {
      status,
    });
  }

  /**
   * Bulk updates match statuses
   */
  static async bulkUpdateMatches(
    documentId: string,
    matchIds: string[],
    status: 'approved' | 'rejected'
  ): Promise<APIResponse<void>> {
    return post<void>(`/documents/${documentId}/redact/matches/bulk-update/`, {
      match_ids: matchIds,
      status,
    });
  }

  /**
   * Adds manual redaction
   */
  static async addManualRedaction(
    documentId: string,
    jobId: string,
    redaction: {
      pageNumber: number;
      x: number;
      y: number;
      width: number;
      height: number;
      reason?: string;
    }
  ): Promise<APIResponse<{ redactionId: string }>> {
    return post<{ redactionId: string }>(`/documents/${documentId}/redact/${jobId}/manual/`, {
      page_number: redaction.pageNumber,
      bounding_box: {
        x: redaction.x,
        y: redaction.y,
        width: redaction.width,
        height: redaction.height,
      },
      reason: redaction.reason,
    });
  }

  /**
   * Finalizes redaction and generates final PDF
   */
  static async finalizeRedaction(
    documentId: string,
    jobId: string,
    options: {
      approvedMatchIds?: string[];
      manualRedactions?: Array<{
        page: number;
        x: number;
        y: number;
        width: number;
        height: number;
      }>;
    } = {}
  ): Promise<APIResponse<{ downloadUrl: string }>> {
    return post<{ downloadUrl: string }>(`/documents/${documentId}/redact/${jobId}/finalize/`, {
      approved_match_ids: options.approvedMatchIds || [],
      manual_redactions: options.manualRedactions || [],
    });
  }

  /**
   * Gets redaction preview without permanent deletion
   */
  static async getRedactionPreview(
    documentId: string,
    matchIds: string[],
    manualRedactions: Array<{
      page: number;
      x: number;
      y: number;
      width: number;
      height: number;
    }> = []
  ): Promise<APIResponse<{ previewUrl: string }>> {
    return post<{ previewUrl: string }>(`/documents/${documentId}/redact/preview/`, {
      match_ids: matchIds,
      manual_redactions: manualRedactions,
    });
  }

  /**
   * Validates redaction coordinates
   */
  static async validateRedactionCoordinates(
    documentId: string,
    coordinates: Array<{
      page: number;
      x: number;
      y: number;
      width: number;
      height: number;
    }>
  ): Promise<APIResponse<{ valid: boolean; errors: string[] }>> {
    return post<{ valid: boolean; errors: string[] }>(
      `/documents/${documentId}/redact/validate-coordinates/`,
      { coordinates }
    );
  }

  /**
   * Downloads redacted PDF
   */
  static async downloadRedactedPDF(
    documentId: string,
    jobId: string
  ): Promise<Blob> {
    return download(`/documents/${documentId}/redact/${jobId}/download/`);
  }
}

/**
 * PDF Splitting Service
 */
export class SplittingService {
  /**
   * Splits PDF by page ranges
   */
  static async splitByPageRanges(
    documentId: string,
    ranges: Array<{ start: number; end: number }>
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/split/`, {
      method: 'page_ranges',
      page_ranges: ranges.map(range => `${range.start}-${range.end}`),
    });
  }

  /**
   * Splits PDF by page count
   */
  static async splitByPageCount(
    documentId: string,
    pagesPerSplit: number
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/split/`, {
      method: 'page_count',
      pages_per_split: pagesPerSplit,
    });
  }

  /**
   * Splits PDF by bookmarks
   */
  static async splitByBookmarks(
    documentId: string,
    bookmarkLevel: number = 1
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/split/`, {
      method: 'bookmarks',
      bookmark_level: bookmarkLevel,
    });
  }

  /**
   * Splits PDF by pattern detection
   */
  static async splitByPattern(
    documentId: string,
    pattern: string
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/split/`, {
      method: 'pattern',
      pattern: pattern,
    });
  }

  /**
   * Gets splitting results
   */
  static async getSplitResults(
    documentId: string,
    jobId: string
  ): Promise<APIResponse<SplitInfo>> {
    return get<SplitInfo>(`/documents/${documentId}/split/${jobId}/results/`);
  }

  /**
   * Downloads split PDF parts
   */
  static async downloadSplitPart(
    documentId: string,
    jobId: string,
    partIndex: number
  ): Promise<Blob> {
    return download(`/documents/${documentId}/split/${jobId}/download/${partIndex}/`);
  }

  /**
   * Downloads all split parts as ZIP
   */
  static async downloadAllSplitParts(
    documentId: string,
    jobId: string
  ): Promise<Blob> {
    return download(`/documents/${documentId}/split/${jobId}/download/all/`);
  }
}

/**
 * PDF Merging Service
 */
export class MergingService {
  /**
   * Merges multiple PDF files
   */
  static async mergeFiles(
    files: File[],
    options: {
      preserveBookmarks?: boolean;
      preserveMetadata?: boolean;
      bookmarkStrategy?: 'preserve-all' | 'merge-top-level' | 'create-new' | 'none';
    } = {}
  ): Promise<APIResponse<{ jobId: string }>> {
    const formData = new FormData();
    
    files.forEach((file, index) => {
      formData.append(`files[${index}]`, file);
    });
    
    formData.append('preserve_bookmarks', String(options.preserveBookmarks ?? true));
    formData.append('preserve_metadata', String(options.preserveMetadata ?? true));
    formData.append('bookmark_strategy', options.bookmarkStrategy || 'preserve-all');

    return upload<{ jobId: string }>('/merge/', formData);
  }

  /**
   * Merges documents by IDs
   */
  static async mergeDocuments(
    documentIds: string[],
    options: {
      preserveBookmarks?: boolean;
      preserveMetadata?: boolean;
      bookmarkStrategy?: string;
    } = {}
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>('/merge/', {
      document_ids: documentIds,
      preserve_bookmarks: options.preserveBookmarks ?? true,
      preserve_metadata: options.preserveMetadata ?? true,
      bookmark_strategy: options.bookmarkStrategy || 'preserve-all',
    });
  }

  /**
   * Gets merge results
   */
  static async getMergeResults(jobId: string): Promise<APIResponse<MergeInfo>> {
    return get<MergeInfo>(`/merge/${jobId}/results/`);
  }

  /**
   * Downloads merged PDF
   */
  static async downloadMergedPDF(jobId: string): Promise<Blob> {
    return download(`/merge/${jobId}/download/`);
  }
}

/**
 * Data Extraction Service
 */
export class ExtractionService {
  /**
   * Extracts all data types from PDF
   */
  static async extractData(
    documentId: string,
    options: {
      extractText?: boolean;
      extractImages?: boolean;
      extractTables?: boolean;
      extractMetadata?: boolean;
      extractForms?: boolean;
      imageFormat?: 'png' | 'jpg' | 'webp';
      textFormat?: 'plain' | 'markdown' | 'html';
    } = {}
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/extract/`, {
      extract_text: options.extractText ?? true,
      extract_images: options.extractImages ?? true,
      extract_tables: options.extractTables ?? true,
      extract_metadata: options.extractMetadata ?? true,
      extract_forms: options.extractForms ?? true,
      image_format: options.imageFormat || 'png',
      text_format: options.textFormat || 'plain',
    });
  }

  /**
   * Gets extraction results
   */
  static async getExtractionResults(
    documentId: string,
    jobId: string
  ): Promise<APIResponse<ExtractedData>> {
    return get<ExtractedData>(`/documents/${documentId}/extract/${jobId}/results/`);
  }

  /**
   * Downloads extracted data as ZIP
   */
  static async downloadExtractedData(
    documentId: string,
    jobId: string
  ): Promise<Blob> {
    return download(`/documents/${documentId}/extract/${jobId}/download/`);
  }

  /**
   * Downloads specific extracted images
   */
  static async downloadExtractedImage(
    documentId: string,
    jobId: string,
    imageId: string
  ): Promise<Blob> {
    return download(`/documents/${documentId}/extract/${jobId}/images/${imageId}/`);
  }
}

/**
 * Job Management Service
 */
export class JobService {
  private static pollingIntervals = new Map<string, NodeJS.Timeout>();
  private static cancelTokens = new Map<string, any>();

  /**
   * Gets job status
   */
  static async getJobStatus(jobId: string): Promise<APIResponse<ProcessingJob>> {
    return get<ProcessingJob>(`/jobs/${jobId}/`);
  }

  /**
   * Polls job status until completion
   */
  static async pollJobStatus(
    jobId: string,
    onProgress: (job: ProcessingJob) => void,
    onComplete: (job: ProcessingJob) => void,
    onError: (error: any) => void,
    intervalMs: number = 2000
  ): Promise<void> {
    // Clear existing polling for this job
    this.stopPolling(jobId);

    const poll = async (): Promise<void> => {
      try {
        const response = await this.getJobStatus(jobId);
        
        if (!response.success || !response.data) {
          throw new Error(response.error?.message || 'Failed to get job status');
        }

        const job = response.data;
        onProgress(job);

        if (job.status === 'completed') {
          this.stopPolling(jobId);
          onComplete(job);
        } else if (job.status === 'failed') {
          this.stopPolling(jobId);
          onError(new Error(job.errorMessage || 'Job failed'));
        } else if (job.status === 'cancelled') {
          this.stopPolling(jobId);
          onError(new Error('Job was cancelled'));
        }
      } catch (error) {
        this.stopPolling(jobId);
        onError(error);
      }
    };

    // Start polling
    const interval = setInterval(poll, intervalMs);
    this.pollingIntervals.set(jobId, interval);

    // Initial poll
    await poll();
  }

  /**
   * Stops polling for a specific job
   */
  static stopPolling(jobId: string): void {
    const interval = this.pollingIntervals.get(jobId);
    if (interval) {
      clearInterval(interval);
      this.pollingIntervals.delete(jobId);
    }
  }

  /**
   * Cancels a job
   */
  static async cancelJob(jobId: string): Promise<APIResponse<void>> {
    this.stopPolling(jobId);
    return post<void>(`/jobs/${jobId}/cancel/`);
  }

  /**
   * Gets job results
   */
  static async getJobResults(jobId: string): Promise<APIResponse<ProcessingResult>> {
    return get<ProcessingResult>(`/jobs/${jobId}/results/`);
  }
}

/**
 * Session Management Service
 */
export class SessionService {
  /**
   * Gets current session info
   */
  static async getSessionInfo(): Promise<APIResponse<SessionInfo>> {
    return get<SessionInfo>('/session/');
  }

  /**
   * Extends current session
   */
  static async extendSession(additionalHours: number = 8): Promise<APIResponse<SessionInfo>> {
    return post<SessionInfo>('/session/extend/', {
      additional_hours: additionalHours,
    });
  }

  /**
   * Cleans up session data
   */
  static async cleanupSession(): Promise<APIResponse<CleanupStatus>> {
    return post<CleanupStatus>('/session/cleanup/');
  }

  /**
   * Gets session cleanup status
   */
  static async getCleanupStatus(): Promise<APIResponse<CleanupStatus>> {
    return get<CleanupStatus>('/session/cleanup/status/');
  }
}

/**
 * OCR Service
 */
export class OCRService {
  /**
   * Performs OCR on document
   */
  static async performOCR(
    documentId: string,
    options: {
      language?: string;
      dpi?: number;
      preserveLayout?: boolean;
    } = {}
  ): Promise<APIResponse<{ jobId: string }>> {
    return post<{ jobId: string }>(`/documents/${documentId}/ocr/`, {
      language: options.language || 'eng',
      dpi: options.dpi || 300,
      preserve_layout: options.preserveLayout ?? true,
    });
  }

  /**
   * Gets OCR results
   */
  static async getOCRResults(
    documentId: string,
    jobId: string
  ): Promise<APIResponse<{ text: string; confidence: number; pages: any[] }>> {
    return get<{ text: string; confidence: number; pages: any[] }>(
      `/documents/${documentId}/ocr/${jobId}/results/`
    );
  }
}

// Export all services as a single object for convenience
export const PDFService = {
  FileUpload: FileUploadService,
  Document: DocumentService,
  Redaction: RedactionService,
  Splitting: SplittingService,
  Merging: MergingService,
  Extraction: ExtractionService,
  Job: JobService,
  Session: SessionService,
  OCR: OCRService,
};