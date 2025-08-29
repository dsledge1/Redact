import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';

import FileUpload from '@/components/FileUpload';
import type { APIError, UploadProgress } from '@/types';

// Mock the store
jest.mock('@/store', () => ({
  useUpload: jest.fn(),
  useUploadActions: jest.fn(),
}));

// Mock file utilities
jest.mock('@/utils/fileUtils', () => ({
  validateFile: jest.fn(),
  formatBytes: jest.fn((bytes: number) => `${bytes} bytes`),
  createFilePreview: jest.fn(),
}));

import { useUpload, useUploadActions } from '@/store';
import { validateFile, createFilePreview } from '@/utils/fileUtils';

const mockUseUpload = useUpload as jest.MockedFunction<typeof useUpload>;
const mockUseUploadActions = useUploadActions as jest.MockedFunction<typeof useUploadActions>;
const mockValidateFile = validateFile as jest.MockedFunction<typeof validateFile>;
const mockCreateFilePreview = createFilePreview as jest.MockedFunction<typeof createFilePreview>;

describe('FileUpload Component', () => {
  const defaultProps = {
    onFileUploaded: jest.fn(),
    onError: jest.fn(),
    onProgress: jest.fn(),
  };

  const mockUploadState = {
    isUploading: false,
    progress: null,
    error: undefined,
  };

  const mockUploadActions = {
    uploadFile: jest.fn(),
    cancelUpload: jest.fn(),
    clearUploadError: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    
    mockUseUpload.mockReturnValue(mockUploadState);
    mockUseUploadActions.mockReturnValue(mockUploadActions);
    
    mockValidateFile.mockReturnValue({
      isValid: true,
      errors: [],
      warnings: [],
    });
    
    mockCreateFilePreview.mockResolvedValue('data:image/png;base64,preview');
  });

  describe('Initial Render', () => {
    it('renders upload dropzone correctly', () => {
      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByText('Upload a PDF File')).toBeInTheDocument();
      expect(screen.getByText(/Drag and drop your PDF file here/)).toBeInTheDocument();
      expect(screen.getByText('Supported format: PDF')).toBeInTheDocument();
    });

    it('displays correct file size limit', () => {
      render(<FileUpload {...defaultProps} maxSize={50 * 1024 * 1024} />);
      
      expect(screen.getByText('Maximum file size: 52428800 bytes')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(<FileUpload {...defaultProps} className="custom-class" />);
      
      const dropzone = container.querySelector('.dropzone');
      expect(dropzone).toHaveClass('custom-class');
    });
  });

  describe('File Validation', () => {
    it('shows error when file validation fails', async () => {
      const user = userEvent.setup();
      const mockError: APIError = {
        code: 'INVALID_FILE_TYPE',
        message: 'Invalid file type',
        timestamp: new Date().toISOString(),
      };

      mockValidateFile.mockReturnValue({
        isValid: false,
        errors: [mockError],
        warnings: [],
      });

      render(<FileUpload {...defaultProps} />);
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
      const input = screen.getByRole('button');
      
      await act(async () => {
        fireEvent.drop(input, {
          dataTransfer: {
            files: [file],
          },
        });
      });

      expect(defaultProps.onError).toHaveBeenCalledWith(mockError);
    });

    it('validates file and shows preview on success', async () => {
      const user = userEvent.setup();
      
      mockValidateFile.mockReturnValue({
        isValid: true,
        errors: [],
        warnings: [],
      });

      render(<FileUpload {...defaultProps} />);
      
      const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
      const input = screen.getByRole('button');
      
      await act(async () => {
        fireEvent.drop(input, {
          dataTransfer: {
            files: [file],
          },
        });
      });

      await waitFor(() => {
        expect(mockValidateFile).toHaveBeenCalledWith(file);
        expect(mockCreateFilePreview).toHaveBeenCalledWith(file);
      });
    });
  });

  describe('Upload Process', () => {
    it('shows uploading state during upload', () => {
      mockUseUpload.mockReturnValue({
        isUploading: true,
        progress: { loaded: 50, total: 100, percentage: 50 },
        error: undefined,
      });

      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByText('Uploading PDF...')).toBeInTheDocument();
      expect(screen.getByText('50% complete')).toBeInTheDocument();
    });

    it('displays progress bar during upload', () => {
      mockUseUpload.mockReturnValue({
        isUploading: true,
        progress: { loaded: 30, total: 100, percentage: 30 },
        error: undefined,
      });

      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByText('30 bytes / 100 bytes')).toBeInTheDocument();
    });

    it('allows canceling upload', async () => {
      const user = userEvent.setup();
      
      mockUseUpload.mockReturnValue({
        isUploading: true,
        progress: { loaded: 30, total: 100, percentage: 30 },
        error: undefined,
      });

      render(<FileUpload {...defaultProps} />);
      
      const cancelButton = screen.getByText('Cancel Upload');
      await user.click(cancelButton);
      
      expect(mockUploadActions.cancelUpload).toHaveBeenCalled();
    });

    it('calls onProgress callback during upload', async () => {
      const mockProgress: UploadProgress = {
        loaded: 50,
        total: 100,
        percentage: 50,
        speed: 1024,
      };

      mockUploadActions.uploadFile.mockImplementation(async (file, onProgressCallback) => {
        if (onProgressCallback) {
          onProgressCallback(mockProgress);
        }
      });

      render(<FileUpload {...defaultProps} />);
      
      const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
      const input = screen.getByRole('button');
      
      await act(async () => {
        fireEvent.drop(input, {
          dataTransfer: {
            files: [file],
          },
        });
      });

      await waitFor(() => {
        expect(defaultProps.onProgress).toHaveBeenCalledWith(mockProgress);
      });
    });
  });

  describe('Error Handling', () => {
    it('displays error state when upload fails', () => {
      const mockError: APIError = {
        code: 'UPLOAD_FAILED',
        message: 'Upload failed due to network error',
        timestamp: new Date().toISOString(),
      };

      mockUseUpload.mockReturnValue({
        isUploading: false,
        progress: null,
        error: mockError,
      });

      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByText('Upload Failed')).toBeInTheDocument();
      expect(screen.getByText(mockError.message)).toBeInTheDocument();
      expect(screen.getByText('Try Again')).toBeInTheDocument();
    });

    it('allows retrying after error', async () => {
      const user = userEvent.setup();
      const mockError: APIError = {
        code: 'UPLOAD_FAILED',
        message: 'Upload failed',
        timestamp: new Date().toISOString(),
      };

      mockUseUpload.mockReturnValue({
        isUploading: false,
        progress: null,
        error: mockError,
      });

      render(<FileUpload {...defaultProps} />);
      
      const retryButton = screen.getByText('Try Again');
      await user.click(retryButton);
      
      expect(mockUploadActions.clearUploadError).toHaveBeenCalled();
    });

    it('shows error details in error section', () => {
      const mockError: APIError = {
        code: 'FILE_TOO_LARGE',
        message: 'File size exceeds the maximum limit',
        timestamp: new Date().toISOString(),
      };

      mockUseUpload.mockReturnValue({
        isUploading: false,
        progress: null,
        error: mockError,
      });

      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByText('Upload Error')).toBeInTheDocument();
      expect(screen.getByText(mockError.message)).toBeInTheDocument();
    });
  });

  describe('Drag and Drop', () => {
    it('shows drag active state when dragging files', () => {
      // Mock useDropzone to return drag active state
      const mockUseDropzone = jest.requireMock('react-dropzone').useDropzone;
      mockUseDropzone.mockReturnValue({
        getRootProps: () => ({ role: 'button' }),
        getInputProps: () => ({ type: 'file' }),
        isDragActive: true,
        isDragReject: false,
      });

      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByText('Drop PDF Here')).toBeInTheDocument();
      expect(screen.getByText('Release to upload your PDF file')).toBeInTheDocument();
    });

    it('shows drag reject state when dragging invalid files', () => {
      const mockUseDropzone = jest.requireMock('react-dropzone').useDropzone;
      mockUseDropzone.mockReturnValue({
        getRootProps: () => ({ role: 'button' }),
        getInputProps: () => ({ type: 'file' }),
        isDragActive: false,
        isDragReject: true,
      });

      render(<FileUpload {...defaultProps} />);
      
      expect(screen.getByText('Invalid File Type')).toBeInTheDocument();
      expect(screen.getByText('Only PDF files are supported. Please select a valid PDF file.')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<FileUpload {...defaultProps} />);
      
      const dropzone = screen.getByRole('button');
      expect(dropzone).toBeInTheDocument();
    });

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup();
      
      render(<FileUpload {...defaultProps} />);
      
      const dropzone = screen.getByRole('button');
      
      // Should be focusable
      await user.tab();
      expect(dropzone).toHaveFocus();
    });
  });

  describe('Props Configuration', () => {
    it('respects disabled prop', () => {
      render(<FileUpload {...defaultProps} disabled={true} />);
      
      const dropzone = screen.getByRole('button');
      expect(dropzone).toHaveClass('cursor-not-allowed', 'opacity-50');
    });

    it('respects multiple files prop', () => {
      render(<FileUpload {...defaultProps} multiple={true} />);
      
      const input = screen.getByRole('button').querySelector('input');
      expect(input).toHaveAttribute('multiple');
    });

    it('respects accept prop', () => {
      render(<FileUpload {...defaultProps} accept="application/pdf,.pdf" />);
      
      const input = screen.getByRole('button').querySelector('input');
      expect(input).toHaveAttribute('accept', 'application/pdf,.pdf');
    });
  });

  describe('File Preview', () => {
    it('shows preview after successful file selection', async () => {
      mockCreateFilePreview.mockResolvedValue('data:image/png;base64,mockpreview');
      
      render(<FileUpload {...defaultProps} />);
      
      const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
      const input = screen.getByRole('button');
      
      await act(async () => {
        fireEvent.drop(input, {
          dataTransfer: {
            files: [file],
          },
        });
      });

      await waitFor(() => {
        expect(screen.getByText('Ready to upload! Click or drag another file to replace.')).toBeInTheDocument();
      });
    });
  });
});