import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import PDFViewer from '@/components/PDFViewer';
import type { PDFViewerProps } from '@/types';

// Mock the store
jest.mock('@/store', () => ({
  useDocument: jest.fn(),
}));

import { useDocument } from '@/store';

const mockUseDocument = useDocument as jest.MockedFunction<typeof useDocument>;

describe('PDFViewer Component', () => {
  const defaultProps: PDFViewerProps = {
    onPageChange: jest.fn(),
    onScaleChange: jest.fn(),
    onError: jest.fn(),
  };

  const mockDocument = {
    id: 'doc-123',
    fileName: 'test.pdf',
    originalName: 'test.pdf',
    fileSize: 1024,
    pageCount: 5,
    uploadedAt: new Date().toISOString(),
    sessionId: 'session-123',
    mimeType: 'application/pdf',
    status: 'ready' as const,
    processingHistory: [],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseDocument.mockReturnValue(null);
  });

  describe('Initial Render', () => {
    it('renders "No PDF to display" when no source provided', () => {
      render(<PDFViewer {...defaultProps} />);
      
      expect(screen.getByText('No PDF to display')).toBeInTheDocument();
    });

    it('renders PDF viewer with file prop', async () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} />);
      
      await waitFor(() => {
        expect(screen.getByTestId('mock-pdf-document')).toBeInTheDocument();
      });
    });

    it('renders PDF viewer with documentId prop', async () => {
      mockUseDocument.mockReturnValue(mockDocument);
      
      render(<PDFViewer {...defaultProps} documentId="doc-123" />);
      
      await waitFor(() => {
        expect(screen.getByTestId('mock-pdf-document')).toBeInTheDocument();
      });
    });

    it('shows controls when showControls is true', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} showControls={true} />);
      
      expect(screen.getByLabelText('Previous page')).toBeInTheDocument();
      expect(screen.getByLabelText('Next page')).toBeInTheDocument();
      expect(screen.getByLabelText('Zoom in')).toBeInTheDocument();
      expect(screen.getByLabelText('Zoom out')).toBeInTheDocument();
    });

    it('hides controls when showControls is false', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} showControls={false} />);
      
      expect(screen.queryByLabelText('Previous page')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Next page')).not.toBeInTheDocument();
    });
  });

  describe('PDF Loading', () => {
    it('shows loading spinner initially', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} />);
      
      expect(screen.getByText('Loading PDF...')).toBeInTheDocument();
    });

    it('handles PDF load success', async () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} />);
      
      // The mock automatically calls onLoadSuccess after 100ms
      await waitFor(() => {
        expect(screen.getByTestId('mock-pdf-page')).toBeInTheDocument();
      });
    });

    it('handles PDF load error', async () => {
      const file = new File(['invalid content'], 'test.pdf', { type: 'application/pdf' });
      const consoleError = jest.spyOn(console, 'error').mockImplementation();
      
      // Mock the PDF library to throw an error
      jest.requireMock('react-pdf').Document = ({ onLoadError }) => {
        const error = new Error('Failed to load PDF');
        if (onLoadError) {
          setTimeout(() => onLoadError(error), 100);
        }
        return <div>Error loading document</div>;
      };
      
      render(<PDFViewer {...defaultProps} file={file} />);
      
      await waitFor(() => {
        expect(screen.getByText('Error loading PDF')).toBeInTheDocument();
        expect(screen.getByText('Failed to load PDF')).toBeInTheDocument();
      });
      
      consoleError.mockRestore();
    });
  });

  describe('Navigation Controls', () => {
    beforeEach(() => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      render(<PDFViewer {...defaultProps} file={file} showControls={true} />);
    });

    it('navigates to next page', async () => {
      const user = userEvent.setup();
      
      const nextButton = screen.getByLabelText('Next page');
      await user.click(nextButton);
      
      expect(defaultProps.onPageChange).toHaveBeenCalledWith(2);
    });

    it('navigates to previous page', async () => {
      const user = userEvent.setup();
      
      // First go to page 2
      const nextButton = screen.getByLabelText('Next page');
      await user.click(nextButton);
      
      // Then go back to page 1
      const prevButton = screen.getByLabelText('Previous page');
      await user.click(prevButton);
      
      expect(defaultProps.onPageChange).toHaveBeenCalledWith(1);
    });

    it('allows direct page input', async () => {
      const user = userEvent.setup();
      
      const pageInput = screen.getByLabelText('Current page');
      await user.clear(pageInput);
      await user.type(pageInput, '3');
      
      expect(defaultProps.onPageChange).toHaveBeenCalledWith(3);
    });

    it('disables previous button on first page', () => {
      const prevButton = screen.getByLabelText('Previous page');
      expect(prevButton).toBeDisabled();
    });

    it('prevents navigation beyond page limits', async () => {
      const user = userEvent.setup();
      
      const pageInput = screen.getByLabelText('Current page');
      await user.clear(pageInput);
      await user.type(pageInput, '999');
      
      // Should clamp to maximum available pages (1 in mock)
      expect(defaultProps.onPageChange).toHaveBeenCalledWith(1);
    });
  });

  describe('Zoom Controls', () => {
    beforeEach(() => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      render(<PDFViewer {...defaultProps} file={file} showControls={true} />);
    });

    it('zooms in when zoom in button is clicked', async () => {
      const user = userEvent.setup();
      
      const zoomInButton = screen.getByLabelText('Zoom in');
      await user.click(zoomInButton);
      
      expect(defaultProps.onScaleChange).toHaveBeenCalledWith(1.25);
    });

    it('zooms out when zoom out button is clicked', async () => {
      const user = userEvent.setup();
      
      const zoomOutButton = screen.getByLabelText('Zoom out');
      await user.click(zoomOutButton);
      
      expect(defaultProps.onScaleChange).toHaveBeenCalledWith(0.8);
    });

    it('changes zoom via dropdown', async () => {
      const user = userEvent.setup();
      
      const zoomSelect = screen.getByLabelText('Zoom level');
      await user.selectOptions(zoomSelect, '1.5');
      
      expect(defaultProps.onScaleChange).toHaveBeenCalledWith(1.5);
    });

    it('displays current zoom percentage', () => {
      expect(screen.getByText('100%')).toBeInTheDocument();
    });
  });

  describe('Additional Controls', () => {
    beforeEach(() => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      render(<PDFViewer {...defaultProps} file={file} showControls={true} />);
    });

    it('has rotate button', () => {
      expect(screen.getByLabelText('Rotate')).toBeInTheDocument();
    });

    it('has fullscreen toggle button', () => {
      expect(screen.getByLabelText('Toggle fullscreen')).toBeInTheDocument();
    });

    it('toggles fullscreen mode', async () => {
      const user = userEvent.setup();
      
      // Mock fullscreen API
      const mockRequestFullscreen = jest.fn();
      const mockExitFullscreen = jest.fn();
      
      Object.defineProperty(document, 'fullscreenElement', {
        value: null,
        writable: true,
      });
      
      Object.defineProperty(document.documentElement, 'requestFullscreen', {
        value: mockRequestFullscreen,
      });
      
      Object.defineProperty(document, 'exitFullscreen', {
        value: mockExitFullscreen,
      });
      
      const fullscreenButton = screen.getByLabelText('Toggle fullscreen');
      await user.click(fullscreenButton);
      
      expect(mockRequestFullscreen).toHaveBeenCalled();
    });
  });

  describe('Search Functionality', () => {
    beforeEach(() => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      render(<PDFViewer {...defaultProps} file={file} />);
    });

    it('renders search input', () => {
      expect(screen.getByPlaceholderText('Search in PDF...')).toBeInTheDocument();
    });

    it('accepts search input', async () => {
      const user = userEvent.setup();
      
      const searchInput = screen.getByPlaceholderText('Search in PDF...');
      await user.type(searchInput, 'test search');
      
      expect(searchInput).toHaveValue('test search');
    });
  });

  describe('Keyboard Shortcuts', () => {
    beforeEach(() => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      render(<PDFViewer {...defaultProps} file={file} />);
    });

    it('navigates with arrow keys', () => {
      fireEvent.keyDown(window, { key: 'ArrowRight' });
      expect(defaultProps.onPageChange).toHaveBeenCalledWith(2);
      
      fireEvent.keyDown(window, { key: 'ArrowLeft' });
      expect(defaultProps.onPageChange).toHaveBeenCalledWith(1);
    });

    it('zooms with keyboard shortcuts', () => {
      fireEvent.keyDown(window, { key: '=', ctrlKey: true });
      expect(defaultProps.onScaleChange).toHaveBeenCalledWith(1.25);
      
      fireEvent.keyDown(window, { key: '-', ctrlKey: true });
      expect(defaultProps.onScaleChange).toHaveBeenCalledWith(0.8);
    });

    it('ignores shortcuts when focused on input', async () => {
      const user = userEvent.setup();
      
      const searchInput = screen.getByPlaceholderText('Search in PDF...');
      await user.click(searchInput);
      
      fireEvent.keyDown(searchInput, { key: 'ArrowRight' });
      
      // Should not trigger navigation when input is focused
      expect(defaultProps.onPageChange).not.toHaveBeenCalled();
    });
  });

  describe('Thumbnails', () => {
    it('shows thumbnails sidebar when showThumbnails is true', async () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} showThumbnails={true} />);
      
      // Wait for document to load first
      await waitFor(() => {
        expect(screen.getByTestId('mock-pdf-document')).toBeInTheDocument();
      });
      
      // Then check for thumbnail (page 1 should be visible)
      expect(screen.getByText('Page 1')).toBeInTheDocument();
    });

    it('hides thumbnails when showThumbnails is false', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} showThumbnails={false} />);
      
      expect(screen.queryByText('Page 1')).not.toBeInTheDocument();
    });
  });

  describe('Props and Configuration', () => {
    it('applies custom className', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      const { container } = render(<PDFViewer {...defaultProps} file={file} className="custom-viewer" />);
      
      expect(container.firstChild).toHaveClass('custom-viewer');
    });

    it('starts at initial page', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} initialPage={3} showControls={true} />);
      
      const pageInput = screen.getByLabelText('Current page');
      expect(pageInput).toHaveValue(3);
    });

    it('starts at initial scale', () => {
      const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' });
      
      render(<PDFViewer {...defaultProps} file={file} initialScale={1.5} showControls={true} />);
      
      expect(screen.getByText('150%')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('calls onError callback when PDF fails to load', async () => {
      const file = new File(['invalid content'], 'test.pdf', { type: 'application/pdf' });
      
      // Mock PDF error
      jest.requireMock('react-pdf').Document = ({ onLoadError }) => {
        const error = new Error('PDF parsing error');
        if (onLoadError) {
          setTimeout(() => onLoadError(error), 100);
        }
        return <div>Error</div>;
      };
      
      render(<PDFViewer {...defaultProps} file={file} />);
      
      await waitFor(() => {
        expect(defaultProps.onError).toHaveBeenCalledWith(
          expect.objectContaining({
            message: 'PDF parsing error'
          })
        );
      });
    });
  });
});