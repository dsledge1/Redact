import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import RedactionOverlay from '../../components/RedactionOverlay';
import { useRedaction, useRedactionActions, useUI } from '../../store/pdfStore';
import * as coordinateUtils from '../../utils/coordinateUtils';

// Mock the store hooks
vi.mock('../../store/pdfStore');
vi.mock('../../utils/coordinateUtils');

const mockUseRedaction = vi.mocked(useRedaction);
const mockUseRedactionActions = vi.mocked(useRedactionActions);
const mockUseUI = vi.mocked(useUI);
const mockPdfToViewport = vi.mocked(coordinateUtils.pdfToViewport);

describe('RedactionOverlay', () => {
  const mockProps = {
    pageNumber: 1,
    pageWidth: 800,
    pageHeight: 1000,
    scale: 1,
    rotation: 0,
  };

  const mockRedactionMatch = {
    id: 'match-1',
    original_text: 'John Doe',
    matched_text: 'John Doe',
    page_number: 1,
    x_coordinate: 100,
    y_coordinate: 200,
    width: 80,
    height: 20,
    confidence_score: 0.95,
    is_approved: null,
    context: 'Name: John Doe',
  };

  const mockManualRedaction = {
    id: 'manual-1',
    page: 1,
    x: 150,
    y: 250,
    width: 100,
    height: 25,
    createdAt: '2023-01-01T00:00:00Z',
  };

  const mockActions = {
    approveMatch: vi.fn(),
    rejectMatch: vi.fn(),
  };

  beforeEach(() => {
    mockUseRedaction.mockReturnValue({
      matches: [mockRedactionMatch],
      manualRedactions: [mockManualRedaction],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    mockUseRedactionActions.mockReturnValue(mockActions);

    mockUseUI.mockReturnValue({
      currentPage: 1,
      sidebarOpen: true,
      currentView: 'redaction',
      showProgress: false,
      manualToolActive: false,
      pageDimensions: new Map(),
      viewer: {
        scale: 1,
        rotation: 0,
        currentPage: 1,
        displayMode: 'single',
      },
    });

    mockPdfToViewport.mockImplementation((pdfCoords) => ({
      x: pdfCoords.x,
      y: pdfCoords.y,
      width: pdfCoords.width,
      height: pdfCoords.height,
    }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing when no matches or manual redactions exist', () => {
    mockUseRedaction.mockReturnValue({
      matches: [],
      manualRedactions: [],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    const { container } = render(<RedactionOverlay {...mockProps} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders SVG overlay when matches exist', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const svgElement = screen.getByLabelText('Redaction overlay');
    expect(svgElement).toBeInTheDocument();
    expect(svgElement).toHaveAttribute('width', '800');
    expect(svgElement).toHaveAttribute('height', '1000');
  });

  it('renders redaction rectangles for matches on current page', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe.*95% confidence/);
    expect(matchRectangle).toBeInTheDocument();
    expect(matchRectangle).toHaveAttribute('x', '100');
    expect(matchRectangle).toHaveAttribute('y', '200');
    expect(matchRectangle).toHaveAttribute('width', '80');
    expect(matchRectangle).toHaveAttribute('height', '20');
  });

  it('renders manual redaction rectangles with dashed border', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const manualRectangle = screen.getByLabelText('Manual redaction area');
    expect(manualRectangle).toBeInTheDocument();
    expect(manualRectangle).toHaveAttribute('stroke-dasharray', '4 2');
    expect(manualRectangle).toHaveAttribute('fill', '#3b82f6');
  });

  it('applies correct colors based on match approval status', () => {
    const approvedMatch = { ...mockRedactionMatch, id: 'match-2', is_approved: true };
    const rejectedMatch = { ...mockRedactionMatch, id: 'match-3', is_approved: false };

    mockUseRedaction.mockReturnValue({
      matches: [mockRedactionMatch, approvedMatch, rejectedMatch],
      manualRedactions: [],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    render(<RedactionOverlay {...mockProps} />);
    
    const pendingRect = screen.getByLabelText(/Pending redaction.*John Doe/);
    const approvedRect = screen.getByLabelText(/Approved redaction/);
    const rejectedRect = screen.getByLabelText(/Rejected redaction/);

    expect(pendingRect).toHaveAttribute('fill', '#f59e0b'); // amber
    expect(approvedRect).toHaveAttribute('fill', '#10b981'); // green
    expect(rejectedRect).toHaveAttribute('fill', '#ef4444'); // red
  });

  it('filters matches by current page number', () => {
    const matchPage2 = { ...mockRedactionMatch, id: 'match-page2', page_number: 2 };

    mockUseRedaction.mockReturnValue({
      matches: [mockRedactionMatch, matchPage2],
      manualRedactions: [],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    render(<RedactionOverlay {...mockProps} pageNumber={1} />);
    
    expect(screen.getByLabelText(/Pending redaction.*John Doe/)).toBeInTheDocument();
    expect(screen.queryByText('match-page2')).not.toBeInTheDocument();
  });

  it('calls coordinate conversion utility with correct parameters', () => {
    render(<RedactionOverlay {...mockProps} scale={1.5} rotation={90} />);
    
    expect(mockPdfToViewport).toHaveBeenCalledWith(
      {
        x: 100,
        y: 200,
        width: 80,
        height: 20,
      },
      1000,
      1.5,
      90
    );
  });

  it('handles click events on pending matches', () => {
    const mockOnClick = vi.fn();
    render(<RedactionOverlay {...mockProps} onClick={mockOnClick} />);
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe/);
    fireEvent.click(matchRectangle);
    
    expect(mockOnClick).toHaveBeenCalledWith(mockRedactionMatch);
  });

  it('does not handle click events on approved/rejected matches', () => {
    const approvedMatch = { ...mockRedactionMatch, is_approved: true };
    mockUseRedaction.mockReturnValue({
      matches: [approvedMatch],
      manualRedactions: [],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    const mockOnClick = vi.fn();
    render(<RedactionOverlay {...mockProps} onClick={mockOnClick} />);
    
    const matchRectangle = screen.getByLabelText(/Approved redaction/);
    fireEvent.click(matchRectangle);
    
    expect(mockOnClick).not.toHaveBeenCalled();
  });

  it('handles double click to approve pending matches', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe/);
    fireEvent.doubleClick(matchRectangle);
    
    expect(mockActions.approveMatch).toHaveBeenCalledWith('match-1');
  });

  it('shows tooltip on mouse hover', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe/);
    fireEvent.mouseEnter(matchRectangle);
    
    expect(screen.getByText('John Doe (95%)')).toBeInTheDocument();
  });

  it('hides tooltip on mouse leave', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe/);
    fireEvent.mouseEnter(matchRectangle);
    fireEvent.mouseLeave(matchRectangle);
    
    expect(screen.queryByText('John Doe (95%)')).not.toBeInTheDocument();
  });

  it('supports keyboard navigation for pending matches', () => {
    render(<RedactionOverlay {...mockProps} />);
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe/);
    expect(matchRectangle).toHaveAttribute('tabIndex', '0');
    expect(matchRectangle).toHaveAttribute('role', 'button');
  });

  it('does not support keyboard navigation for approved/rejected matches', () => {
    const approvedMatch = { ...mockRedactionMatch, is_approved: true };
    mockUseRedaction.mockReturnValue({
      matches: [approvedMatch],
      manualRedactions: [],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    render(<RedactionOverlay {...mockProps} />);
    
    const matchRectangle = screen.getByLabelText(/Approved redaction/);
    expect(matchRectangle).toHaveAttribute('tabIndex', '-1');
  });

  it('handles edge case with zero dimensions gracefully', () => {
    const zeroMatch = { 
      ...mockRedactionMatch, 
      width: 0, 
      height: 0 
    };

    mockUseRedaction.mockReturnValue({
      matches: [zeroMatch],
      manualRedactions: [],
      searchTerms: [],
      fuzzyThreshold: 0.8,
      confidenceThreshold: 95,
      settings: {
        searchTerms: [],
        fuzzyThreshold: 0.8,
        caseSensitive: false,
        wholeWordsOnly: false,
        patterns: [],
      },
      processingStatus: 'completed',
      errors: [],
    });

    expect(() => {
      render(<RedactionOverlay {...mockProps} />);
    }).not.toThrow();
  });

  it('prevents event propagation on click events', () => {
    const mockOnClick = vi.fn();
    const mockParentClick = vi.fn();

    const { container } = render(
      <div onClick={mockParentClick}>
        <RedactionOverlay {...mockProps} onClick={mockOnClick} />
      </div>
    );
    
    const matchRectangle = screen.getByLabelText(/Pending redaction.*John Doe/);
    fireEvent.click(matchRectangle);
    
    expect(mockOnClick).toHaveBeenCalled();
    expect(mockParentClick).not.toHaveBeenCalled();
  });
});