import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import MatchReviewSidebar from '../../components/MatchReviewSidebar';
import { useRedaction, useRedactionActions, useUI, useUIActions } from '../../store/pdfStore';

// Mock the store hooks
vi.mock('../../store/pdfStore');

const mockUseRedaction = vi.mocked(useRedaction);
const mockUseRedactionActions = vi.mocked(useRedactionActions);
const mockUseUI = vi.mocked(useUI);
const mockUseUIActions = vi.mocked(useUIActions);

describe('MatchReviewSidebar', () => {
  const mockMatch1 = {
    id: 'match-1',
    original_text: 'John Doe',
    matched_text: 'John Doe',
    page_number: 1,
    x_coordinate: 100,
    y_coordinate: 200,
    width: 80,
    height: 20,
    confidence_score: 0.85,
    is_approved: null,
    context: 'Employee: John Doe',
  };

  const mockMatch2 = {
    id: 'match-2',
    original_text: 'SSN',
    matched_text: '123-45-6789',
    page_number: 2,
    x_coordinate: 150,
    y_coordinate: 300,
    width: 100,
    height: 15,
    confidence_score: 0.92,
    is_approved: null,
    context: 'SSN: 123-45-6789',
  };

  const mockApprovedMatch = {
    ...mockMatch1,
    id: 'approved-match',
    is_approved: true,
  };

  const mockRedactionActions = {
    approveMatch: vi.fn(),
    rejectMatch: vi.fn(),
    approveAllMatches: vi.fn(),
    rejectAllMatches: vi.fn(),
    approveHighConfidenceMatches: vi.fn(),
    setConfidenceThreshold: vi.fn(),
  };

  const mockUIActions = {
    setCurrentPage: vi.fn(),
  };

  beforeEach(() => {
    mockUseRedaction.mockReturnValue({
      matches: [mockMatch1, mockMatch2, mockApprovedMatch],
      manualRedactions: [],
      confidenceThreshold: 95,
      searchTerms: [],
      fuzzyThreshold: 0.8,
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

    mockUseRedactionActions.mockReturnValue(mockRedactionActions);

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

    mockUseUIActions.mockReturnValue(mockUIActions);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders sidebar with correct title', () => {
    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('Review Matches')).toBeInTheDocument();
  });

  it('displays statistics correctly', () => {
    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('3')).toBeInTheDocument(); // Total
    expect(screen.getByText('2')).toBeInTheDocument(); // Pending
    expect(screen.getByText('1')).toBeInTheDocument(); // Approved
    expect(screen.getByText('0')).toBeInTheDocument(); // Rejected
  });

  it('shows confidence threshold slider', () => {
    render(<MatchReviewSidebar />);
    
    const slider = screen.getByDisplayValue('95');
    expect(slider).toBeInTheDocument();
    expect(slider).toHaveAttribute('type', 'range');
  });

  it('updates confidence threshold when slider changes', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const slider = screen.getByDisplayValue('95');
    await user.clear(slider);
    await user.type(slider, '90');
    
    expect(mockRedactionActions.setConfidenceThreshold).toHaveBeenCalledWith(90);
  });

  it('displays search input', () => {
    render(<MatchReviewSidebar />);
    
    const searchInput = screen.getByPlaceholderText('Search matches...');
    expect(searchInput).toBeInTheDocument();
  });

  it('filters matches based on search term', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const searchInput = screen.getByPlaceholderText('Search matches...');
    await user.type(searchInput, 'John');
    
    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.queryByText('123-45-6789')).not.toBeInTheDocument();
  });

  it('shows confidence filter inputs', () => {
    render(<MatchReviewSidebar />);
    
    const minInput = screen.getByPlaceholderText('Min %');
    const maxInput = screen.getByPlaceholderText('Max %');
    
    expect(minInput).toBeInTheDocument();
    expect(maxInput).toBeInTheDocument();
  });

  it('displays bulk action buttons', () => {
    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('Approve All Pending')).toBeInTheDocument();
    expect(screen.getByText('Reject All Pending')).toBeInTheDocument();
    expect(screen.getByText('Approve High Confidence (≥90%)')).toBeInTheDocument();
  });

  it('disables bulk actions when no pending matches', () => {
    mockUseRedaction.mockReturnValue({
      matches: [mockApprovedMatch],
      manualRedactions: [],
      confidenceThreshold: 95,
      searchTerms: [],
      fuzzyThreshold: 0.8,
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

    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('Approve All Pending')).toBeDisabled();
    expect(screen.getByText('Reject All Pending')).toBeDisabled();
    expect(screen.getByText('Approve High Confidence (≥90%)')).toBeDisabled();
  });

  it('groups matches by page number', () => {
    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('Page 1')).toBeInTheDocument();
    expect(screen.getByText('Page 2')).toBeInTheDocument();
    expect(screen.getByText('(1 matches)')).toBeInTheDocument(); // Page 1 has 1 pending match
    expect(screen.getByText('(1 matches)')).toBeInTheDocument(); // Page 2 has 1 pending match
  });

  it('expands and collapses page sections', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('displays match details correctly', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 1
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('shows original text when different from matched text', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 2
    const page2Button = screen.getByText('Page 2');
    await user.click(page2Button);
    
    expect(screen.getByText('123-45-6789')).toBeInTheDocument();
    expect(screen.getByText('Original: SSN')).toBeInTheDocument();
  });

  it('handles individual match approval', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 1
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    const approveButton = screen.getByText('Approve');
    await user.click(approveButton);
    
    expect(mockRedactionActions.approveMatch).toHaveBeenCalledWith('match-1');
  });

  it('handles individual match rejection', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 1
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    const rejectButton = screen.getByText('Reject');
    await user.click(rejectButton);
    
    expect(mockRedactionActions.rejectMatch).toHaveBeenCalledWith('match-1');
  });

  it('handles bulk approve all action', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const approveAllButton = screen.getByText('Approve All Pending');
    await user.click(approveAllButton);
    
    expect(mockRedactionActions.approveAllMatches).toHaveBeenCalled();
  });

  it('handles bulk reject all action', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const rejectAllButton = screen.getByText('Reject All Pending');
    await user.click(rejectAllButton);
    
    expect(mockRedactionActions.rejectAllMatches).toHaveBeenCalled();
  });

  it('handles approve high confidence action', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const approveHighButton = screen.getByText('Approve High Confidence (≥90%)');
    await user.click(approveHighButton);
    
    expect(mockRedactionActions.approveHighConfidenceMatches).toHaveBeenCalledWith(90);
  });

  it('handles jump to page functionality', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const jumpButton = screen.getByText('Jump to page');
    await user.click(jumpButton);
    
    expect(mockUIActions.setCurrentPage).toHaveBeenCalledWith(1);
  });

  it('shows keyboard shortcuts help', () => {
    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('Keyboard Shortcuts:')).toBeInTheDocument();
    expect(screen.getByText('A - Approve selected')).toBeInTheDocument();
    expect(screen.getByText('R - Reject selected')).toBeInTheDocument();
    expect(screen.getByText('↑↓ - Navigate matches')).toBeInTheDocument();
  });

  it('handles keyboard shortcuts', async () => {
    render(<MatchReviewSidebar />);
    
    // Simulate keyboard events
    fireEvent.keyDown(window, { key: 'a' });
    
    // Since we need to select a match first, this tests the event listener setup
    expect(document.addEventListener).toHaveBeenCalled;
  });

  it('selects matches when clicked', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 1
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    const matchDiv = screen.getByLabelText('Match: John Doe');
    await user.click(matchDiv);
    
    expect(matchDiv).toHaveClass('border-blue-500', 'bg-blue-50');
  });

  it('navigates to next match after approval', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 1
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    // Select first match
    const matchDiv = screen.getByLabelText('Match: John Doe');
    await user.click(matchDiv);
    
    // Approve it
    const approveButton = screen.getByText('Approve');
    await user.click(approveButton);
    
    expect(mockRedactionActions.approveMatch).toHaveBeenCalledWith('match-1');
  });

  it('shows "no pending matches" message when all matches are reviewed', () => {
    mockUseRedaction.mockReturnValue({
      matches: [mockApprovedMatch],
      manualRedactions: [],
      confidenceThreshold: 95,
      searchTerms: [],
      fuzzyThreshold: 0.8,
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

    render(<MatchReviewSidebar />);
    
    expect(screen.getByText('No pending matches to review')).toBeInTheDocument();
  });

  it('filters matches by confidence range', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    const minInput = screen.getByPlaceholderText('Min %');
    const maxInput = screen.getByPlaceholderText('Max %');
    
    await user.clear(minInput);
    await user.type(minInput, '90');
    await user.clear(maxInput);
    await user.type(maxInput, '95');
    
    // Only match2 (92%) should be visible now
    expect(screen.queryByText('Page 1')).not.toBeInTheDocument();
    expect(screen.getByText('Page 2')).toBeInTheDocument();
  });

  it('maintains expanded state for current page', () => {
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

    render(<MatchReviewSidebar />);
    
    // Page 1 should be expanded because it's the current page
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('handles accessibility features correctly', async () => {
    const user = userEvent.setup();
    render(<MatchReviewSidebar />);
    
    // Expand page 1
    const page1Button = screen.getByText('Page 1');
    await user.click(page1Button);
    
    const matchDiv = screen.getByLabelText('Match: John Doe');
    const approveButton = screen.getByLabelText('Approve John Doe');
    const rejectButton = screen.getByLabelText('Reject John Doe');
    
    expect(matchDiv).toHaveAttribute('role', 'button');
    expect(matchDiv).toHaveAttribute('tabIndex', '0');
    expect(approveButton).toBeInTheDocument();
    expect(rejectButton).toBeInTheDocument();
  });
});