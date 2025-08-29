/**
 * Comprehensive TypeScript type definitions for Ultimate PDF application
 */

// Document Types
export interface PDFDocument {
  id: string;
  fileName: string;
  originalName: string;
  fileSize: number;
  pageCount: number;
  uploadedAt: string;
  sessionId: string;
  mimeType: string;
  status: DocumentStatus;
  processingHistory: ProcessingOperation[];
}

export interface DocumentMetadata {
  title?: string;
  author?: string;
  subject?: string;
  creator?: string;
  producer?: string;
  creationDate?: string;
  modificationDate?: string;
  keywords?: string[];
  pageLayout?: string;
  pageMode?: string;
}

export interface PageInfo {
  pageNumber: number;
  width: number;
  height: number;
  rotation: number;
  hasText: boolean;
  hasImages: boolean;
  wordCount?: number;
}

export type DocumentStatus = 
  | 'uploading'
  | 'processing'
  | 'ready'
  | 'error'
  | 'expired';

// Processing Job Types
export interface ProcessingJob {
  id: string;
  documentId: string;
  operation: ProcessingOperation;
  status: JobStatus;
  progress: number;
  currentStep: string;
  totalSteps: number;
  startedAt: string;
  completedAt?: string;
  errorMessage?: string;
  result?: ProcessingResult;
}

export interface JobProgress {
  progress: number;
  currentStep: string;
  totalSteps: number;
  estimatedTimeRemaining?: number;
  processingSpeed?: number;
}

export type JobStatus = 
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ProcessingOperation = 
  | 'redaction'
  | 'splitting'
  | 'merging' 
  | 'extraction'
  | 'ocr'
  | 'optimization';

export interface ProcessingResult {
  outputFiles: string[];
  summary: string;
  extractedData?: ExtractedData;
  redactionStats?: RedactionStats;
  splitInfo?: SplitInfo;
  mergeInfo?: MergeInfo;
}

// Redaction Types
export interface RedactionMatch {
  id: string;
  original_text: string;
  matched_text: string;
  page_number: number;
  x_coordinate: number;
  y_coordinate: number;
  width: number;
  height: number;
  confidence_score: number;
  pattern?: string;
  type?: RedactionType;
  is_approved: boolean | null;
  context?: string;
}

export interface FuzzyMatch {
  id: string;
  original: string;
  matched: string;
  similarity: number;
  pageNumber: number;
  position: BoundingBox;
  suggested: boolean;
}

export interface ManualRedaction {
  id: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  reason?: string;
  createdAt: string;
}

export interface RedactionSettings {
  searchTerms: string[];
  fuzzyThreshold: number;
  caseSensitive: boolean;
  wholeWordsOnly: boolean;
  patterns: RedactionPattern[];
  excludeTerms?: string[];
  contextRadius?: number;
}

export interface RedactionPattern {
  id: string;
  name: string;
  regex: string;
  type: RedactionType;
  enabled: boolean;
  description?: string;
}

export interface RedactionStats {
  totalMatches: number;
  approvedMatches: number;
  rejectedMatches: number;
  manualRedactions: number;
  pagesProcessed: number;
  processingTime: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type RedactionType = 
  | 'ssn'
  | 'email'
  | 'phone'
  | 'address'
  | 'name'
  | 'custom'
  | 'manual';

export type MatchStatus = 
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'processing';

// File Upload Types
export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed?: number;
  timeRemaining?: number;
}

export interface FileValidation {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  error?: string;
  pageCount?: number;
  size?: number;
}

export interface ValidationError {
  code: string;
  message: string;
  field?: string;
}

export interface ValidationWarning {
  code: string;
  message: string;
  severity: 'low' | 'medium' | 'high';
}

export interface UploadResult {
  documentId: string;
  fileName: string;
  fileSize: number;
  pageCount: number;
  sessionId: string;
  uploadUrl?: string;
}

// API Response Types
export interface APIResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: APIError;
  message?: string;
  timestamp: string;
}

export interface APIError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  field?: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
}

// Viewer Types
export interface ViewerState {
  scale: number;
  rotation: number;
  currentPage: number;
  totalPages: number;
  displayMode: DisplayMode;
  isFullscreen: boolean;
  searchQuery?: string;
  searchResults: SearchResult[];
  currentSearchIndex: number;
}

export interface SearchResult {
  pageNumber: number;
  text: string;
  boundingBox: BoundingBox;
  context: string;
}

export type DisplayMode = 
  | 'single'
  | 'double'
  | 'continuous'
  | 'thumbnail';

export type ZoomLevel = 
  | 'fit-width'
  | 'fit-height' 
  | 'fit-page'
  | 'actual-size'
  | number;

// Session Types
export interface SessionInfo {
  sessionId: string;
  createdAt: string;
  expiresAt: string;
  isActive: boolean;
  documentsCount: number;
  storageUsed: number;
}

export interface SessionStatus {
  isValid: boolean;
  timeRemaining: number;
  warningThreshold: number;
  autoExtendEnabled: boolean;
}

export interface CleanupStatus {
  scheduled: boolean;
  executeAt: string;
  documentsToCleanup: number;
  estimatedSize: number;
}

// Extraction Types
export interface ExtractedData {
  text?: ExtractedText;
  images?: ExtractedImage[];
  tables?: ExtractedTable[];
  metadata?: DocumentMetadata;
  forms?: ExtractedForm[];
  text_content?: { [format: string]: string };
  download_urls?: {
    text?: { [format: string]: string };
    images?: string[];
    tables?: string[];
    metadata?: { [format: string]: string };
    forms?: string[];
  };
  processing_time?: number;
  total_size?: number;
}

export interface ExtractedText {
  content: string;
  pageBreaks: number[];
  wordCount: number;
  characterCount: number;
  language?: string;
  confidence?: number;
}

export interface ExtractedImage {
  id: string;
  pageNumber: number;
  page_number: number;
  boundingBox: BoundingBox;
  bounding_box: BoundingBox;
  format: string;
  size: number;
  width: number;
  height: number;
  url?: string;
  base64?: string;
  download_url?: string;
  preview_url?: string;
  confidence?: number;
}

export interface ExtractedTable {
  id: string;
  pageNumber: number;
  page_number: number;
  boundingBox: BoundingBox;
  bounding_box: BoundingBox;
  rows: TableRow[] | number;
  columns: number;
  confidence: number;
  download_url?: string;
  preview?: string;
  format?: string;
}

export interface TableRow {
  cells: TableCell[];
  rowNumber: number;
}

export interface TableCell {
  text: string;
  columnIndex: number;
  boundingBox: BoundingBox;
  confidence: number;
}

export interface ExtractedForm {
  id: string;
  pageNumber: number;
  fields: FormField[];
  type?: string;
}

export interface FormField {
  name: string;
  value: string;
  type: FormFieldType;
  boundingBox: BoundingBox;
  confidence: number;
}

export type FormFieldType = 
  | 'text'
  | 'checkbox'
  | 'radio'
  | 'dropdown'
  | 'signature';

// Splitting Types
export interface SplitInfo {
  method: SplitMethod;
  total_parts: number;
  files: SplitFile[];
  preserve_bookmarks: boolean;
  preserve_metadata: boolean;
  processing_time?: number;
  total_size?: number;
}

export interface SplitFile {
  filename: string;
  page_range: PageRange;
  size: number;
  download_url: string;
  preview_url?: string;
}

export interface SplitOptions {
  preserve_metadata: boolean;
  preserve_bookmarks: boolean;
  custom_naming: boolean;
  naming_pattern: string;
}

export type SplitMethod = 
  | 'page_ranges'
  | 'page_count'
  | 'bookmarks'
  | 'pattern'
  | 'blank_pages';

// Merging Types
export interface MergeInfo {
  filename: string;
  total_pages: number;
  file_size: number;
  source_files?: string[];
  bookmark_count?: number;
  download_url: string;
  processing_time?: number;
}

export interface MergeOptions {
  preserve_bookmarks: boolean;
  preserve_metadata: boolean;
  bookmark_strategy: BookmarkStrategy;
}

export interface PageRange {
  start: number;
  end: number;
}

export type BookmarkStrategy = 
  | 'preserve_all'
  | 'merge_top_level'
  | 'create_new'
  | 'none';


export type ExtractionType = 'text' | 'images' | 'tables' | 'metadata' | 'forms';

export interface ExtractionFormats {
  text: 'plain' | 'markdown' | 'html';
  images: 'png' | 'jpg' | 'webp';
  tables: 'csv' | 'json' | 'xlsx';
  metadata: 'json' | 'xml';
}

export interface ExtractionOptions {
  image_dpi: number;
  table_detection_sensitivity: 'low' | 'medium' | 'high';
  ocr_confidence_threshold: number;
  preserve_formatting: boolean;
  include_coordinates: boolean;
}

// Component Props for New Operations
export interface SplitInterfaceProps extends BaseComponentProps {
  documentRef?: React.RefObject<HTMLDivElement>;
  onSplitComplete?: (results: SplitInfo) => void;
}

export interface MergeInterfaceProps extends BaseComponentProps {
  onMergeComplete?: (results: MergeInfo) => void;
}

export interface ExtractionInterfaceProps extends BaseComponentProps {
  documentRef?: React.RefObject<HTMLDivElement>;
  onExtractionComplete?: (results: ExtractedData) => void;
}

export interface PageRangeSelectorProps extends BaseComponentProps {
  totalPages: number;
  selectedRanges: PageRange[];
  onRangeChange: (ranges: PageRange[]) => void;
  documentRef?: React.RefObject<HTMLDivElement>;
  maxSelectableRanges?: number;
  allowSinglePageSelection?: boolean;
}

export interface OperationProgressBarProps extends BaseComponentProps {
  operationType: ProcessingOperation;
  jobId: string;
  onComplete: (results: any) => void;
  onError?: (error: string) => void;
  onCancel?: () => void;
  showCancelButton?: boolean;
  showTimeRemaining?: boolean;
  showDetails?: boolean;
}

export interface ResultPreviewProps extends BaseComponentProps {
  operationType: ProcessingOperation;
  results: any;
  onDownload?: (fileId?: string) => void;
  onDownloadAll?: () => void;
  showStatistics?: boolean;
}

// Validation and Utility Types
export interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings?: string[];
}

export interface MergeFileValidation {
  isValid: boolean;
  error?: string;
  pageCount?: number;
  size: number;
}

export interface OperationProgress {
  percentage: number;
  currentStep: string;
  estimatedTimeRemaining?: number;
  processingSpeed?: string;
  dataProcessed?: string;
}

export interface OperationSummary {
  operationType: ProcessingOperation;
  startTime: number;
  endTime: number;
  inputFiles: number;
  outputFiles: number;
  totalSize: number;
  success: boolean;
  error?: string;
}

// Enhanced Processing Job with Operation Specifics
export interface ProcessingJobWithResults extends ProcessingJob {
  result?: SplitInfo | MergeInfo | ExtractedData | any;
  total_pages?: number;
  data_processed?: number | string;
  current_step?: string;
}

// Results Types
export interface RedactionResults {
  total_redactions: number;
  pages_with_redactions: number;
  download_url: string;
  processing_time?: number;
  redaction_summary?: string;
}

// Redaction Interface Types
export interface PageDimensions {
  width: number;
  height: number;
  originalWidth?: number;
  originalHeight?: number;
}

export interface CoordinateTransform {
  scale: number;
  rotation: number;
  pageHeight: number;
  pageWidth: number;
}

export interface RedactionOverlayProps extends BaseComponentProps {
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  scale?: number;
  rotation?: number;
  onClick?: (match: RedactionMatch) => void;
}

export interface MatchReviewSidebarProps extends BaseComponentProps {
  // Props are handled via hooks
}

export interface ManualRedactionToolProps extends BaseComponentProps {
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  scale?: number;
  rotation?: number;
  containerRef: React.RefObject<HTMLDivElement>;
}

export interface RedactionToolbarProps extends BaseComponentProps {
  // Props are handled via hooks
}

export interface DrawingState {
  isDrawing: boolean;
  startPoint: { x: number; y: number } | null;
  currentPoint: { x: number; y: number } | null;
}

export type BulkAction = 'approve-all' | 'reject-all' | 'approve-high-confidence';

export interface RedactionStatistics {
  totalMatches: number;
  approvedMatches: number;
  rejectedMatches: number;
  pendingMatches: number;
  autoApprovedMatches: number;
  manualCount: number;
  totalPages: number;
  completionPercentage: number;
}

export interface CoordinateValidation {
  valid: boolean;
  errors: string[];
  warnings?: string[];
}

export type RedactionMode = 'review' | 'manual' | 'preview';

export interface KeyboardShortcut {
  key: string;
  description: string;
  action: string;
  modifiers?: ('ctrl' | 'alt' | 'shift' | 'meta')[];
}

// Utility Types
export interface AsyncState<T> {
  data?: T;
  loading: boolean;
  error?: APIError;
  lastUpdated?: string;
}

export interface RequestState {
  pending: boolean;
  success: boolean;
  error?: string;
}

// Form Types
export interface RedactionFormData {
  searchTerms: string[];
  fuzzyThreshold: number;
  caseSensitive: boolean;
  wholeWordsOnly: boolean;
  patterns: string[];
  excludeTerms: string[];
}

export interface SplitFormData {
  method: SplitMethod;
  page_ranges?: PageRange[];
  pages_per_split?: number;
  bookmark_level?: number;
  pattern?: string;
  options: SplitOptions;
}

export interface MergeFormData {
  files: File[];
  options: MergeOptions;
}

export interface ExtractionFormData {
  types: ExtractionType[];
  formats: ExtractionFormats;
  page_range?: PageRange;
  options: ExtractionOptions;
}

// Event Types
export interface FileUploadEvent {
  type: 'upload-start' | 'upload-progress' | 'upload-complete' | 'upload-error';
  file: File;
  progress?: UploadProgress;
  error?: APIError;
  result?: UploadResult;
}

export interface ProcessingEvent {
  type: 'processing-start' | 'processing-progress' | 'processing-complete' | 'processing-error';
  jobId: string;
  progress?: JobProgress;
  error?: APIError;
  result?: ProcessingResult;
}

export interface ViewerEvent {
  type: 'page-change' | 'zoom-change' | 'search' | 'fullscreen-toggle';
  page?: number;
  scale?: number;
  query?: string;
  isFullscreen?: boolean;
}

// Component Prop Types
export interface BaseComponentProps {
  className?: string;
  children?: React.ReactNode;
  id?: string;
}

export interface FileUploadProps extends BaseComponentProps {
  onFileUploaded?: (file: File) => void;
  onFilesUploaded?: (files: File[]) => void;
  onError: (error: APIError) => void;
  onProgress?: (progress: UploadProgress) => void;
  accept?: string;
  maxSize?: number;
  multiple?: boolean;
  disabled?: boolean;
}

export interface PDFViewerProps extends BaseComponentProps {
  documentId?: string;
  file?: File | string;
  onPageChange?: (page: number) => void;
  onScaleChange?: (scale: number) => void;
  onError?: (error: APIError) => void;
  initialPage?: number;
  initialScale?: number;
  showControls?: boolean;
  showThumbnails?: boolean;
}

export interface ProgressBarProps extends BaseComponentProps {
  progress: number;
  indeterminate?: boolean;
  label?: string;
  showPercentage?: boolean;
  variant?: 'default' | 'success' | 'warning' | 'error';
  size?: 'sm' | 'md' | 'lg';
}

// Store Types (Zustand)
export interface PDFStore {
  // Document state
  document: PDFDocument | null;
  processing: {
    status: JobStatus;
    progress: number;
    currentStep: string;
    errors: APIError[];
  };

  // Redaction state
  redaction: {
    searchTerms: string[];
    fuzzyThreshold: number;
    matches: RedactionMatch[];
    manualRedactions: ManualRedaction[];
    settings: RedactionSettings;
  };

  // Actions
  uploadFile: (file: File) => Promise<void>;
  approveMatch: (matchId: string) => void;
  rejectMatch: (matchId: string) => void;
  addManualRedaction: (redaction: Omit<ManualRedaction, 'id' | 'createdAt'>) => void;
  removeManualRedaction: (redactionId: string) => void;
  updateRedactionSettings: (settings: Partial<RedactionSettings>) => void;
  finalizeRedaction: () => Promise<string>;
  clearDocument: () => void;
  
  // Session management
  sessionInfo: SessionInfo | null;
  checkSession: () => Promise<boolean>;
  extendSession: () => Promise<void>;
  cleanupSession: () => Promise<void>;
}

// Environment Types
export interface EnvironmentConfig {
  API_BASE_URL: string;
  MAX_FILE_SIZE: number;
  UPLOAD_TIMEOUT: number;
  SESSION_TIMEOUT: number;
  ENABLE_DEBUG: boolean;
  ENABLE_ANALYTICS: boolean;
}