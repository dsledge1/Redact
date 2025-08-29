/**
 * Main Zustand store for PDF processing application
 * Follows the exact structure specified in project conventions
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  PDFDocument,
  RedactionMatch,
  ManualRedaction,
  RedactionSettings,
  ProcessingJob,
  APIError,
  SessionInfo,
  JobStatus,
  UploadProgress,
  SplitMethod,
  PageRange,
  SplitOptions,
  SplitFormData,
  SplitInfo,
  MergeOptions,
  MergeFormData,
  MergeInfo,
  ExtractionType,
  ExtractionFormats,
  ExtractionOptions,
  ExtractionFormData,
  ExtractedData,
  ProcessingOperation,
} from '@/types';

import { PDFService } from '@/services/pdfService';
import { createAbortController } from '@/services/api';
import { 
  getStoredSessionInfo, 
  storeSessionInfo, 
  createNewSession,
  isSessionValid 
} from '@/utils/sessionUtils';

// Store State Interface
interface PDFStoreState {
  // Document state
  document: PDFDocument | null;
  
  // Processing state
  processing: {
    status: JobStatus;
    progress: number;
    currentStep: string;
    totalSteps: number;
    errors: APIError[];
    jobId?: string;
    startTime?: number;
  };

  // Upload state
  upload: {
    isUploading: boolean;
    progress: UploadProgress | null;
    error?: APIError;
  };

  // Redaction state
  redaction: {
    searchTerms: string[];
    fuzzyThreshold: number;
    confidenceThreshold: number;
    matches: RedactionMatch[];
    manualRedactions: ManualRedaction[];
    settings: RedactionSettings;
    processingStatus: 'pending' | 'processing' | 'completed' | 'failed';
    downloadUrl?: string;
    errors: string[];
  };

  // Session state
  session: {
    info: SessionInfo | null;
    isValid: boolean;
    timeRemaining: number;
    showWarning: boolean;
  };

  // Splitting state
  splitting: {
    method: SplitMethod;
    pageRanges: PageRange[];
    options: SplitOptions;
    jobId?: string;
    results?: SplitInfo;
  };

  // Merging state
  merging: {
    files: File[];
    fileOrder: string[];
    options: MergeOptions;
    jobId?: string;
    results?: MergeInfo;
  };

  // Extraction state
  extraction: {
    types: ExtractionType[];
    formats: ExtractionFormats;
    pageRange?: PageRange;
    options: ExtractionOptions;
    jobId?: string;
    results?: ExtractedData;
  };

  // UI state
  ui: {
    sidebarOpen: boolean;
    currentView: 'upload' | 'viewer' | 'redaction' | 'processing' | 'splitting' | 'merging' | 'extraction';
    currentOperation: ProcessingOperation | null;
    showProgress: boolean;
    manualToolActive: boolean;
    pageDimensions: Map<number, { width: number; height: number; originalWidth?: number; originalHeight?: number }>;
    viewer: {
      scale: number;
      rotation: number;
      currentPage: number;
      displayMode: 'single' | 'continuous' | 'two-page';
    };
  };
}

// Store Actions Interface
interface PDFStoreActions {
  // File upload actions
  uploadFile: (file: File, onProgress?: (progress: UploadProgress) => void) => Promise<void>;
  cancelUpload: () => void;
  clearUploadError: () => void;

  // Document actions
  loadDocument: (documentId: string) => Promise<void>;
  clearDocument: () => void;

  // Redaction actions
  initiateRedaction: (searchTerms: string[], settings?: Partial<RedactionSettings>) => Promise<void>;
  approveMatch: (matchId: string) => void;
  rejectMatch: (matchId: string) => void;
  approveMatches: (matchIds: string[]) => Promise<void>;
  rejectMatches: (matchIds: string[]) => Promise<void>;
  approveAllMatches: () => Promise<void>;
  rejectAllMatches: () => Promise<void>;
  approveHighConfidenceMatches: (threshold: number) => Promise<void>;
  addManualRedaction: (pageNumber: number, coordinates: { x: number; y: number; width: number; height: number }) => void;
  removeManualRedaction: (redactionId: string) => void;
  removeAllManualRedactions: () => void;
  undoLastManualRedaction: () => void;
  updateRedactionSettings: (settings: Partial<RedactionSettings>) => void;
  setConfidenceThreshold: (threshold: number) => void;
  finalizeRedaction: (approvedMatchIds: string[], manualRedactions: ManualRedaction[]) => Promise<void>;

  // Processing actions
  pollJobStatus: (jobId: string) => void;
  cancelJob: () => Promise<void>;
  clearProcessingErrors: () => void;

  // Session management
  initializeSession: () => Promise<void>;
  checkSession: () => Promise<boolean>;
  extendSession: () => Promise<void>;
  cleanupSession: () => Promise<void>;
  setSessionWarning: (show: boolean) => void;

  // Splitting actions
  setSplitMethod: (method: SplitMethod) => void;
  setSplitPageRanges: (ranges: PageRange[]) => void;
  setSplitOptions: (options: SplitOptions) => void;
  initiateSplit: (file: File, formData: SplitFormData) => Promise<void>;

  // Merging actions
  addMergeFiles: (files: File[]) => void;
  removeMergeFile: (file: File) => void;
  reorderMergeFiles: (fileOrder: string[]) => void;
  setMergeOptions: (options: MergeOptions) => void;
  initiateMerge: (formData: MergeFormData) => Promise<void>;

  // Extraction actions
  setExtractionTypes: (types: ExtractionType[]) => void;
  setExtractionFormats: (formats: ExtractionFormats) => void;
  setExtractionPageRange: (range: PageRange | null) => void;
  setExtractionOptions: (options: ExtractionOptions) => void;
  initiateExtraction: (file: File, formData: ExtractionFormData) => Promise<void>;

  // UI actions
  setSidebarOpen: (open: boolean) => void;
  setCurrentView: (view: PDFStoreState['ui']['currentView']) => void;
  setCurrentOperation: (operation: ProcessingOperation | null) => void;
  setShowProgress: (show: boolean) => void;
  toggleManualTool: () => void;
  setPageDimensions: (pageNumber: number, dimensions: { width: number; height: number; originalWidth?: number; originalHeight?: number }) => void;
  setScale: (scale: number) => void;
  setRotation: (rotation: number) => void;
  setCurrentPage: (page: number) => void;
  setDisplayMode: (mode: PDFStoreState['ui']['viewer']['displayMode']) => void;

  // Utility actions
  reset: () => void;
}

// Combined store type
type PDFStore = PDFStoreState & PDFStoreActions;

// Store upload controller for cancellation
let uploadController: AbortController | undefined;

// Default state
const defaultState: PDFStoreState = {
  document: null,
  processing: {
    status: 'pending',
    progress: 0,
    currentStep: '',
    totalSteps: 0,
    errors: [],
  },
  upload: {
    isUploading: false,
    progress: null,
  },
  redaction: {
    searchTerms: [],
    fuzzyThreshold: 0.8,
    confidenceThreshold: 95,
    matches: [],
    manualRedactions: [],
    settings: {
      searchTerms: [],
      fuzzyThreshold: 0.8,
      caseSensitive: false,
      wholeWordsOnly: false,
      patterns: [],
    },
    processingStatus: 'pending',
    errors: [],
  },
  session: {
    info: null,
    isValid: false,
    timeRemaining: 0,
    showWarning: false,
  },
  splitting: {
    method: 'page_ranges',
    pageRanges: [],
    options: {
      preserve_metadata: true,
      preserve_bookmarks: true,
      custom_naming: false,
      naming_pattern: 'page_{start}-{end}'
    },
  },
  merging: {
    files: [],
    fileOrder: [],
    options: {
      preserve_bookmarks: true,
      preserve_metadata: true,
      bookmark_strategy: 'merge_top_level'
    },
  },
  extraction: {
    types: [],
    formats: {
      text: 'plain',
      images: 'png',
      tables: 'csv',
      metadata: 'json'
    },
    options: {
      image_dpi: 300,
      table_detection_sensitivity: 'medium',
      ocr_confidence_threshold: 0.8,
      preserve_formatting: true,
      include_coordinates: false
    },
  },
  ui: {
    sidebarOpen: true,
    currentView: 'upload',
    currentOperation: null,
    showProgress: false,
    manualToolActive: false,
    pageDimensions: new Map(),
    viewer: {
      scale: 1,
      rotation: 0,
      currentPage: 1,
      displayMode: 'single',
    },
  },
};

/**
 * Main PDF store using Zustand
 */
export const usePDFStore = create<PDFStore>()(
  devtools(
    persist(
      (set, get) => ({
        ...defaultState,

        // File upload actions
        uploadFile: async (file: File, onProgress?: (progress: UploadProgress) => void) => {
          // Create new controller for this upload
          uploadController = createAbortController();
          
          set({
            upload: {
              isUploading: true,
              progress: { loaded: 0, total: file.size, percentage: 0 },
              error: undefined,
            },
            ui: { ...get().ui, currentView: 'upload', showProgress: true },
          });

          try {
            // Ensure session is initialized
            await get().initializeSession();

            const response = await PDFService.FileUpload.uploadFile(
              file,
              (percentage) => {
                const progress: UploadProgress = {
                  loaded: Math.round((file.size * percentage) / 100),
                  total: file.size,
                  percentage,
                };

                set({
                  upload: { ...get().upload, progress },
                });

                onProgress?.(progress);
              },
              uploadController.signal
            );

            // Check if upload was aborted
            if (uploadController?.signal.aborted) {
              return;
            }

            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Upload failed');
            }

            // Load the uploaded document
            await get().loadDocument(response.data.documentId);

            set({
              upload: {
                isUploading: false,
                progress: { loaded: file.size, total: file.size, percentage: 100 },
              },
              ui: { ...get().ui, currentView: 'viewer', showProgress: false },
            });

          } catch (error) {
            // Don't show error if upload was aborted
            if (uploadController?.signal.aborted) {
              return;
            }
            
            const apiError: APIError = {
              code: 'UPLOAD_ERROR',
              message: error instanceof Error ? error.message : 'Upload failed',
              timestamp: new Date().toISOString(),
            };

            set({
              upload: {
                isUploading: false,
                progress: null,
                error: apiError,
              },
              ui: { ...get().ui, showProgress: false },
            });
          } finally {
            uploadController = undefined;
          }
        },

        cancelUpload: () => {
          uploadController?.abort();
          set({
            upload: {
              isUploading: false,
              progress: null,
            },
            ui: { ...get().ui, showProgress: false },
          });
        },

        clearUploadError: () => {
          set({
            upload: { ...get().upload, error: undefined },
          });
        },

        // Document actions
        loadDocument: async (documentId: string) => {
          try {
            const response = await PDFService.Document.getDocument(documentId);
            
            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Failed to load document');
            }

            set({
              document: response.data,
              ui: { ...get().ui, currentView: 'viewer' },
            });

          } catch (error) {
            const apiError: APIError = {
              code: 'LOAD_DOCUMENT_ERROR',
              message: error instanceof Error ? error.message : 'Failed to load document',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                errors: [...get().processing.errors, apiError],
              },
            });
          }
        },

        clearDocument: () => {
          set({
            document: null,
            redaction: { ...defaultState.redaction },
            processing: { ...defaultState.processing },
            ui: { ...get().ui, currentView: 'upload' },
          });
        },

        // Redaction actions
        initiateRedaction: async (searchTerms: string[], settings?: Partial<RedactionSettings>) => {
          const { document } = get();
          if (!document) {
            throw new Error('No document loaded');
          }

          // Update settings
          const updatedSettings: RedactionSettings = {
            ...get().redaction.settings,
            searchTerms,
            ...settings,
          };

          set({
            redaction: {
              ...get().redaction,
              searchTerms,
              settings: updatedSettings,
            },
            processing: {
              status: 'running',
              progress: 0,
              currentStep: 'Initializing redaction',
              totalSteps: 3,
              errors: [],
              startTime: Date.now(),
            },
            ui: { ...get().ui, currentView: 'processing', showProgress: true },
          });

          try {
            const response = await PDFService.Redaction.initiateRedaction(
              document.id,
              searchTerms,
              {
                fuzzyThreshold: updatedSettings.fuzzyThreshold,
                caseSensitive: updatedSettings.caseSensitive,
                wholeWordsOnly: updatedSettings.wholeWordsOnly,
                patterns: updatedSettings.patterns.map(p => p.regex),
                excludeTerms: updatedSettings.excludeTerms,
              }
            );

            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Failed to initiate redaction');
            }

            set({
              processing: {
                ...get().processing,
                jobId: response.data.jobId,
                currentStep: 'Processing document',
                progress: 25,
              },
            });

            // Start polling for job status
            get().pollJobStatus(response.data.jobId);

          } catch (error) {
            const apiError: APIError = {
              code: 'REDACTION_ERROR',
              message: error instanceof Error ? error.message : 'Redaction failed',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                status: 'failed',
                errors: [apiError],
              },
              ui: { ...get().ui, showProgress: false },
            });
          }
        },

        approveMatch: async (matchId: string) => {
          const { document, processing } = get();
          if (!document) {
            throw new Error('No document loaded');
          }

          // Optimistic update
          const matches = get().redaction.matches.map(match =>
            match.id === matchId ? { ...match, is_approved: true } : match
          );

          set({
            redaction: { ...get().redaction, matches },
          });

          try {
            await PDFService.Redaction.updateMatchStatus(
              document.id,
              matchId,
              'approved'
            );
          } catch (error) {
            // Revert optimistic update on error
            const revertedMatches = get().redaction.matches.map(match =>
              match.id === matchId ? { ...match, is_approved: null } : match
            );

            set({
              redaction: { ...get().redaction, matches: revertedMatches },
            });

            const apiError: APIError = {
              code: 'APPROVE_MATCH_ERROR',
              message: error instanceof Error ? error.message : 'Failed to approve match',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                errors: [...get().processing.errors, apiError],
              },
            });

            throw error;
          }
        },

        rejectMatch: async (matchId: string) => {
          const { document, processing } = get();
          if (!document) {
            throw new Error('No document loaded');
          }

          // Optimistic update
          const matches = get().redaction.matches.map(match =>
            match.id === matchId ? { ...match, is_approved: false } : match
          );

          set({
            redaction: { ...get().redaction, matches },
          });

          try {
            await PDFService.Redaction.updateMatchStatus(
              document.id,
              matchId,
              'rejected'
            );
          } catch (error) {
            // Revert optimistic update on error
            const revertedMatches = get().redaction.matches.map(match =>
              match.id === matchId ? { ...match, is_approved: null } : match
            );

            set({
              redaction: { ...get().redaction, matches: revertedMatches },
            });

            const apiError: APIError = {
              code: 'REJECT_MATCH_ERROR',
              message: error instanceof Error ? error.message : 'Failed to reject match',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                errors: [...get().processing.errors, apiError],
              },
            });

            throw error;
          }
        },

        approveMatches: async (matchIds: string[]) => {
          const { document, processing } = get();
          if (!document || !processing.jobId) {
            throw new Error('No active redaction job');
          }

          try {
            await PDFService.Redaction.approveMatches(
              document.id,
              processing.jobId,
              matchIds
            );

            // Update local state
            const matches = get().redaction.matches.map(match =>
              matchIds.includes(match.id) ? { ...match, is_approved: true } : match
            );
            set({
              redaction: { ...get().redaction, matches },
            });

          } catch (error) {
            const apiError: APIError = {
              code: 'APPROVE_MATCHES_ERROR',
              message: error instanceof Error ? error.message : 'Failed to approve matches',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                errors: [...get().processing.errors, apiError],
              },
            });
          }
        },

        rejectMatches: async (matchIds: string[]) => {
          const { document, processing } = get();
          if (!document || !processing.jobId) {
            throw new Error('No active redaction job');
          }

          try {
            await PDFService.Redaction.rejectMatches(
              document.id,
              processing.jobId,
              matchIds
            );

            // Update local state
            const matches = get().redaction.matches.map(match =>
              matchIds.includes(match.id) ? { ...match, is_approved: false } : match
            );
            set({
              redaction: { ...get().redaction, matches },
            });

          } catch (error) {
            const apiError: APIError = {
              code: 'REJECT_MATCHES_ERROR',
              message: error instanceof Error ? error.message : 'Failed to reject matches',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                errors: [...get().processing.errors, apiError],
              },
            });
          }
        },

        approveAllMatches: async () => {
          const { redaction } = get();
          const pendingMatches = redaction.matches.filter(m => m.is_approved === null);
          
          if (pendingMatches.length === 0) return;
          
          const matchIds = pendingMatches.map(m => m.id);
          await get().approveMatches(matchIds);
        },

        rejectAllMatches: async () => {
          const { redaction } = get();
          const pendingMatches = redaction.matches.filter(m => m.is_approved === null);
          
          if (pendingMatches.length === 0) return;
          
          const matchIds = pendingMatches.map(m => m.id);
          await get().rejectMatches(matchIds);
        },

        approveHighConfidenceMatches: async (threshold: number) => {
          const { redaction } = get();
          const highConfidenceMatches = redaction.matches.filter(
            m => m.is_approved === null && (m.confidence_score * 100) >= threshold
          );
          
          if (highConfidenceMatches.length === 0) return;
          
          const matchIds = highConfidenceMatches.map(m => m.id);
          await get().approveMatches(matchIds);
        },

        addManualRedaction: (pageNumber: number, coordinates: { x: number; y: number; width: number; height: number }) => {
          const newRedaction: ManualRedaction = {
            id: `manual_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            page: pageNumber,
            x: coordinates.x,
            y: coordinates.y,
            width: coordinates.width,
            height: coordinates.height,
            createdAt: new Date().toISOString(),
          };

          set({
            redaction: {
              ...get().redaction,
              manualRedactions: [...get().redaction.manualRedactions, newRedaction],
            },
          });
        },

        removeManualRedaction: (redactionId: string) => {
          set({
            redaction: {
              ...get().redaction,
              manualRedactions: get().redaction.manualRedactions.filter(
                r => r.id !== redactionId
              ),
            },
          });
        },

        removeAllManualRedactions: () => {
          set({
            redaction: {
              ...get().redaction,
              manualRedactions: [],
            },
          });
        },

        undoLastManualRedaction: () => {
          const { manualRedactions } = get().redaction;
          if (manualRedactions.length === 0) return;

          set({
            redaction: {
              ...get().redaction,
              manualRedactions: manualRedactions.slice(0, -1),
            },
          });
        },

        updateRedactionSettings: (settings: Partial<RedactionSettings>) => {
          set({
            redaction: {
              ...get().redaction,
              settings: { ...get().redaction.settings, ...settings },
            },
          });
        },

        setConfidenceThreshold: (threshold: number) => {
          set({
            redaction: {
              ...get().redaction,
              confidenceThreshold: threshold,
            },
          });
        },

        finalizeRedaction: async (approvedMatchIds: string[], manualRedactions: ManualRedaction[]) => {
          const { document, processing } = get();
          if (!document || !processing.jobId) {
            throw new Error('No active redaction job');
          }

          set({
            redaction: {
              ...get().redaction,
              processingStatus: 'processing',
            },
          });

          try {
            const response = await PDFService.Redaction.finalizeRedaction(
              document.id,
              processing.jobId,
              {
                approvedMatchIds,
                manualRedactions: manualRedactions.map(r => ({
                  page: r.page,
                  x: r.x,
                  y: r.y,
                  width: r.width,
                  height: r.height,
                })),
              }
            );

            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Failed to finalize redaction');
            }

            set({
              redaction: {
                ...get().redaction,
                processingStatus: 'completed',
                downloadUrl: response.data.downloadUrl,
              },
            });

          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Failed to finalize redaction';

            set({
              redaction: {
                ...get().redaction,
                processingStatus: 'failed',
                errors: [...get().redaction.errors, errorMessage],
              },
            });

            throw error;
          }
        },

        // Processing actions
        pollJobStatus: (jobId: string) => {
          PDFService.Job.pollJobStatus(
            jobId,
            (job: ProcessingJob) => {
              set({
                processing: {
                  ...get().processing,
                  status: job.status,
                  progress: job.progress,
                  currentStep: job.currentStep,
                  totalSteps: job.totalSteps,
                },
              });
            },
            async (job: ProcessingJob) => {
              // Job completed - load results
              if (job.operation === 'redaction') {
                try {
                  const { document } = get();
                  if (document) {
                    const matchesResponse = await PDFService.Redaction.getRedactionMatches(
                      document.id,
                      jobId
                    );

                    if (matchesResponse.success && matchesResponse.data) {
                      // Apply auto-approval based on confidence threshold
                      const { confidenceThreshold } = get().redaction;
                      const matchesWithAutoApproval = matchesResponse.data.map(match => ({
                        ...match,
                        is_approved: match.confidence_score >= (confidenceThreshold / 100) ? true : match.is_approved
                      }));

                      set({
                        redaction: {
                          ...get().redaction,
                          matches: matchesWithAutoApproval,
                        },
                        processing: {
                          ...get().processing,
                          status: 'completed',
                          progress: 100,
                        },
                        ui: { ...get().ui, currentView: 'redaction', showProgress: false },
                      });
                    }
                  }
                } catch (error) {
                  console.error('Error loading redaction matches:', error);
                }
              } else if (job.operation === 'splitting') {
                // Load split results
                set({
                  splitting: {
                    ...get().splitting,
                    results: job.result,
                  },
                  processing: {
                    ...get().processing,
                    status: 'completed',
                    progress: 100,
                  },
                  ui: { ...get().ui, currentView: 'splitting', showProgress: false },
                });
              } else if (job.operation === 'merging') {
                // Load merge results
                set({
                  merging: {
                    ...get().merging,
                    results: job.result,
                  },
                  processing: {
                    ...get().processing,
                    status: 'completed',
                    progress: 100,
                  },
                  ui: { ...get().ui, currentView: 'merging', showProgress: false },
                });
              } else if (job.operation === 'extraction') {
                // Load extraction results
                set({
                  extraction: {
                    ...get().extraction,
                    results: job.result,
                  },
                  processing: {
                    ...get().processing,
                    status: 'completed',
                    progress: 100,
                  },
                  ui: { ...get().ui, currentView: 'extraction', showProgress: false },
                });
              } else {
                set({
                  processing: {
                    ...get().processing,
                    status: 'completed',
                    progress: 100,
                  },
                  ui: { ...get().ui, showProgress: false },
                });
              }
            },
            (error: any) => {
              const apiError: APIError = {
                code: 'JOB_ERROR',
                message: error instanceof Error ? error.message : 'Job processing failed',
                timestamp: new Date().toISOString(),
              };

              set({
                processing: {
                  ...get().processing,
                  status: 'failed',
                  errors: [...get().processing.errors, apiError],
                },
                ui: { ...get().ui, showProgress: false },
              });
            }
          );
        },

        cancelJob: async () => {
          const { processing } = get();
          if (!processing.jobId) {
            return;
          }

          try {
            await PDFService.Job.cancelJob(processing.jobId);
            PDFService.Job.stopPolling(processing.jobId);

            set({
              processing: {
                ...get().processing,
                status: 'pending',
                progress: 0,
                currentStep: '',
                jobId: undefined,
              },
              ui: { ...get().ui, showProgress: false },
            });

          } catch (error) {
            console.error('Error cancelling job:', error);
          }
        },

        clearProcessingErrors: () => {
          set({
            processing: {
              ...get().processing,
              errors: [],
            },
          });
        },

        // Session management
        initializeSession: async () => {
          let sessionInfo = getStoredSessionInfo();

          if (!sessionInfo || !isSessionValid(sessionInfo)) {
            sessionInfo = createNewSession();
            storeSessionInfo(sessionInfo);
          }

          set({
            session: {
              info: sessionInfo,
              isValid: true,
              timeRemaining: new Date(sessionInfo.expiresAt).getTime() - Date.now(),
              showWarning: false,
            },
          });
        },

        checkSession: async () => {
          try {
            const response = await PDFService.Session.getSessionInfo();
            
            if (response.success && response.data) {
              const sessionInfo = response.data;
              storeSessionInfo(sessionInfo);

              const timeRemaining = new Date(sessionInfo.expiresAt).getTime() - Date.now();
              const isValid = timeRemaining > 0;

              set({
                session: {
                  info: sessionInfo,
                  isValid,
                  timeRemaining,
                  showWarning: timeRemaining < 15 * 60 * 1000, // 15 minutes
                },
              });

              return isValid;
            }

            return false;

          } catch (error) {
            set({
              session: {
                ...get().session,
                isValid: false,
              },
            });
            return false;
          }
        },

        extendSession: async () => {
          try {
            const response = await PDFService.Session.extendSession(8);
            
            if (response.success && response.data) {
              storeSessionInfo(response.data);

              set({
                session: {
                  info: response.data,
                  isValid: true,
                  timeRemaining: new Date(response.data.expiresAt).getTime() - Date.now(),
                  showWarning: false,
                },
              });
            }

          } catch (error) {
            console.error('Error extending session:', error);
          }
        },

        cleanupSession: async () => {
          try {
            await PDFService.Session.cleanupSession();
            get().reset();
          } catch (error) {
            console.error('Error cleaning up session:', error);
          }
        },

        setSessionWarning: (show: boolean) => {
          set({
            session: { ...get().session, showWarning: show },
          });
        },

        // Splitting actions
        setSplitMethod: (method: SplitMethod) => {
          set({
            splitting: { ...get().splitting, method },
          });
        },

        setSplitPageRanges: (ranges: PageRange[]) => {
          set({
            splitting: { ...get().splitting, pageRanges: ranges },
          });
        },

        setSplitOptions: (options: SplitOptions) => {
          set({
            splitting: { ...get().splitting, options },
          });
        },

        initiateSplit: async (file: File, formData: SplitFormData) => {
          set({
            processing: {
              status: 'running',
              progress: 0,
              currentStep: 'Initiating split operation',
              totalSteps: 3,
              errors: [],
              startTime: Date.now(),
            },
            ui: { ...get().ui, currentOperation: 'splitting', showProgress: true },
          });

          try {
            const { document } = get();
            if (!document) {
              throw new Error('No document loaded');
            }

            let response: any;
            // Call appropriate service method based on split method
            switch (formData.method) {
              case 'page_ranges':
                if (!formData.page_ranges) {
                  throw new Error('Page ranges are required for page_ranges method');
                }
                response = await PDFService.Splitting.splitByPageRanges(
                  document.id, 
                  formData.page_ranges
                );
                break;
              case 'page_count':
                if (!formData.pages_per_split) {
                  throw new Error('Pages per split is required for page_count method');
                }
                response = await PDFService.Splitting.splitByPageCount(
                  document.id, 
                  formData.pages_per_split
                );
                break;
              case 'bookmarks':
                response = await PDFService.Splitting.splitByBookmarks(
                  document.id, 
                  formData.bookmark_level ?? 1
                );
                break;
              case 'pattern':
                if (!formData.pattern) {
                  throw new Error('Pattern is required for pattern method');
                }
                response = await PDFService.Splitting.splitByPattern(
                  document.id, 
                  formData.pattern
                );
                break;
              default:
                throw new Error(`Unsupported split method: ${formData.method}`);
            }

            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Failed to initiate split');
            }

            set({
              splitting: {
                ...get().splitting,
                jobId: response.data.jobId,
                options: formData.options,
              },
              processing: {
                ...get().processing,
                jobId: response.data.jobId,
                currentStep: 'Processing document split',
                progress: 25,
              },
            });

            get().pollJobStatus(response.data.jobId);

          } catch (error) {
            const apiError: APIError = {
              code: 'SPLIT_ERROR',
              message: error instanceof Error ? error.message : 'Split failed',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                status: 'failed',
                errors: [apiError],
              },
              ui: { ...get().ui, showProgress: false },
            });
          }
        },

        // Merging actions
        addMergeFiles: (files: File[]) => {
          const currentFiles = get().merging.files;
          const newFiles = [...currentFiles, ...files];
          const newFileOrder = newFiles.map((file, index) => `${file.name}-${index}`);
          
          set({
            merging: {
              ...get().merging,
              files: newFiles,
              fileOrder: newFileOrder,
            },
          });
        },

        removeMergeFile: (fileToRemove: File) => {
          const currentFiles = get().merging.files;
          const newFiles = currentFiles.filter(file => file !== fileToRemove);
          const newFileOrder = newFiles.map((file, index) => `${file.name}-${index}`);
          
          set({
            merging: {
              ...get().merging,
              files: newFiles,
              fileOrder: newFileOrder,
            },
          });
        },

        reorderMergeFiles: (fileOrder: string[]) => {
          set({
            merging: { ...get().merging, fileOrder },
          });
        },

        setMergeOptions: (options: MergeOptions) => {
          set({
            merging: { ...get().merging, options },
          });
        },

        initiateMerge: async (formData: MergeFormData) => {
          set({
            processing: {
              status: 'running',
              progress: 0,
              currentStep: 'Initiating merge operation',
              totalSteps: 4,
              errors: [],
              startTime: Date.now(),
            },
            ui: { ...get().ui, currentOperation: 'merging', showProgress: true },
          });

          try {
            // Map bookmark strategy from form data to service expected format
            const mapBookmarkStrategy = (strategy: BookmarkStrategy): 'preserve-all' | 'merge-top-level' | 'create-new' | 'none' => {
              const strategyMap: Record<BookmarkStrategy, 'preserve-all' | 'merge-top-level' | 'create-new' | 'none'> = {
                'preserve_all': 'preserve-all',
                'merge_top_level': 'merge-top-level',
                'create_new': 'create-new',
                'none': 'none'
              };
              return strategyMap[strategy] || 'preserve-all';
            };

            const response = await PDFService.Merging.mergeFiles(formData.files, {
              preserveBookmarks: formData.options.preserve_bookmarks,
              preserveMetadata: formData.options.preserve_metadata,
              bookmarkStrategy: mapBookmarkStrategy(formData.options.bookmark_strategy)
            });

            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Failed to initiate merge');
            }

            set({
              merging: {
                ...get().merging,
                jobId: response.data.jobId,
                options: formData.options,
              },
              processing: {
                ...get().processing,
                jobId: response.data.jobId,
                currentStep: 'Merging documents',
                progress: 25,
              },
            });

            get().pollJobStatus(response.data.jobId);

          } catch (error) {
            const apiError: APIError = {
              code: 'MERGE_ERROR',
              message: error instanceof Error ? error.message : 'Merge failed',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                status: 'failed',
                errors: [apiError],
              },
              ui: { ...get().ui, showProgress: false },
            });
          }
        },

        // Extraction actions
        setExtractionTypes: (types: ExtractionType[]) => {
          set({
            extraction: { ...get().extraction, types },
          });
        },

        setExtractionFormats: (formats: ExtractionFormats) => {
          set({
            extraction: { ...get().extraction, formats },
          });
        },

        setExtractionPageRange: (range: PageRange | null) => {
          set({
            extraction: { ...get().extraction, pageRange: range || undefined },
          });
        },

        setExtractionOptions: (options: ExtractionOptions) => {
          set({
            extraction: { ...get().extraction, options },
          });
        },

        initiateExtraction: async (file: File, formData: ExtractionFormData) => {
          set({
            processing: {
              status: 'running',
              progress: 0,
              currentStep: 'Initiating extraction',
              totalSteps: 5,
              errors: [],
              startTime: Date.now(),
            },
            ui: { ...get().ui, currentOperation: 'extraction', showProgress: true },
          });

          try {
            const { document } = get();
            if (!document) {
              throw new Error('No document loaded');
            }

            const response = await PDFService.Extraction.extractData(document.id, {
              extractText: formData.types.includes('text'),
              extractImages: formData.types.includes('images'),
              extractTables: formData.types.includes('tables'),
              extractMetadata: formData.types.includes('metadata'),
              extractForms: formData.types.includes('forms'),
              imageFormat: formData.formats.images,
              textFormat: formData.formats.text
            });

            if (!response.success || !response.data) {
              throw new Error(response.error?.message || 'Failed to initiate extraction');
            }

            set({
              extraction: {
                ...get().extraction,
                jobId: response.data.jobId,
                types: formData.types,
                formats: formData.formats,
                options: formData.options,
              },
              processing: {
                ...get().processing,
                jobId: response.data.jobId,
                currentStep: 'Analyzing document content',
                progress: 20,
              },
            });

            get().pollJobStatus(response.data.jobId);

          } catch (error) {
            const apiError: APIError = {
              code: 'EXTRACTION_ERROR',
              message: error instanceof Error ? error.message : 'Extraction failed',
              timestamp: new Date().toISOString(),
            };

            set({
              processing: {
                ...get().processing,
                status: 'failed',
                errors: [apiError],
              },
              ui: { ...get().ui, showProgress: false },
            });
          }
        },

        // UI actions
        setSidebarOpen: (open: boolean) => {
          set({
            ui: { ...get().ui, sidebarOpen: open },
          });
        },

        setCurrentView: (view: PDFStoreState['ui']['currentView']) => {
          set({
            ui: { ...get().ui, currentView: view },
          });
        },

        setCurrentOperation: (operation: ProcessingOperation | null) => {
          set({
            ui: { ...get().ui, currentOperation: operation },
          });
        },

        setShowProgress: (show: boolean) => {
          set({
            ui: { ...get().ui, showProgress: show },
          });
        },

        toggleManualTool: () => {
          set({
            ui: { 
              ...get().ui, 
              manualToolActive: !get().ui.manualToolActive 
            },
          });
        },

        setPageDimensions: (pageNumber: number, dimensions: { width: number; height: number; originalWidth?: number; originalHeight?: number }) => {
          const newDimensions = new Map(get().ui.pageDimensions);
          newDimensions.set(pageNumber, dimensions);
          
          set({
            ui: { 
              ...get().ui, 
              pageDimensions: newDimensions 
            },
          });
        },

        setScale: (scale: number) => {
          set({
            ui: { 
              ...get().ui, 
              viewer: { ...get().ui.viewer, scale },
            },
          });
        },

        setRotation: (rotation: number) => {
          set({
            ui: { 
              ...get().ui, 
              viewer: { ...get().ui.viewer, rotation },
            },
          });
        },

        setCurrentPage: (page: number) => {
          set({
            ui: { 
              ...get().ui, 
              viewer: { ...get().ui.viewer, currentPage: page },
            },
          });
        },

        setDisplayMode: (mode: PDFStoreState['ui']['viewer']['displayMode']) => {
          set({
            ui: { 
              ...get().ui, 
              viewer: { ...get().ui.viewer, displayMode: mode },
            },
          });
        },

        // Utility actions
        reset: () => {
          set(defaultState);
        },

        // Additional getters for convenience
        get currentFile() {
          return get().document?.file || null;
        },

        get totalPages() {
          return get().document?.totalPages || 0;
        },
      }),
      {
        name: 'pdf-store',
        partialize: (state) => ({
          // Only persist certain parts of the state
          session: state.session,
          ui: {
            sidebarOpen: state.ui.sidebarOpen,
            currentView: state.ui.currentView,
          },
          redaction: {
            settings: state.redaction.settings,
          },
        }),
      }
    ),
    { name: 'PDFStore' }
  )
);

// Selector hooks for better performance
export const useDocument = () => usePDFStore((state) => state.document);
export const useProcessing = () => usePDFStore((state) => state.processing);
export const useUpload = () => usePDFStore((state) => state.upload);
export const useRedaction = () => usePDFStore((state) => state.redaction);
export const useSplitting = () => usePDFStore((state) => state.splitting);
export const useMerging = () => usePDFStore((state) => state.merging);
export const useExtraction = () => usePDFStore((state) => state.extraction);
export const useSession = () => usePDFStore((state) => state.session);
export const useUI = () => usePDFStore((state) => state.ui);

// Action hooks
export const useUploadActions = () => usePDFStore((state) => ({
  uploadFile: state.uploadFile,
  cancelUpload: state.cancelUpload,
  clearUploadError: state.clearUploadError,
}));

export const useDocumentActions = () => usePDFStore((state) => ({
  loadDocument: state.loadDocument,
  clearDocument: state.clearDocument,
}));

export const useRedactionActions = () => usePDFStore((state) => ({
  initiateRedaction: state.initiateRedaction,
  approveMatch: state.approveMatch,
  rejectMatch: state.rejectMatch,
  approveMatches: state.approveMatches,
  rejectMatches: state.rejectMatches,
  approveAllMatches: state.approveAllMatches,
  rejectAllMatches: state.rejectAllMatches,
  approveHighConfidenceMatches: state.approveHighConfidenceMatches,
  addManualRedaction: state.addManualRedaction,
  removeManualRedaction: state.removeManualRedaction,
  removeAllManualRedactions: state.removeAllManualRedactions,
  undoLastManualRedaction: state.undoLastManualRedaction,
  updateRedactionSettings: state.updateRedactionSettings,
  setConfidenceThreshold: state.setConfidenceThreshold,
  finalizeRedaction: state.finalizeRedaction,
}));

export const useSessionActions = () => usePDFStore((state) => ({
  initializeSession: state.initializeSession,
  checkSession: state.checkSession,
  extendSession: state.extendSession,
  cleanupSession: state.cleanupSession,
  setSessionWarning: state.setSessionWarning,
}));

export const useUIActions = () => usePDFStore((state) => ({
  setSidebarOpen: state.setSidebarOpen,
  setCurrentView: state.setCurrentView,
  setCurrentOperation: state.setCurrentOperation,
  setShowProgress: state.setShowProgress,
  toggleManualTool: state.toggleManualTool,
  setPageDimensions: state.setPageDimensions,
  setScale: state.setScale,
  setRotation: state.setRotation,
  setCurrentPage: state.setCurrentPage,
  setDisplayMode: state.setDisplayMode,
}));