import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  useRedaction,
  useRedactionActions,
  useUI,
  useUIActions,
} from '../store/pdfStore';
import { RedactionMatch } from '../types';
import {
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Search,
  Filter,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';

interface GroupedMatches {
  [pageNumber: number]: RedactionMatch[];
}

const MatchReviewSidebar: React.FC = () => {
  const { matches, confidenceThreshold } = useRedaction();
  const {
    approveMatch,
    rejectMatch,
    approveAllMatches,
    rejectAllMatches,
    approveHighConfidenceMatches,
    setConfidenceThreshold,
  } = useRedactionActions();
  const { currentPage } = useUI();
  const { setCurrentPage } = useUIActions();

  const [searchTerm, setSearchTerm] = useState('');
  const [expandedPages, setExpandedPages] = useState<Set<number>>(new Set());
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [filterConfidenceMin, setFilterConfidenceMin] = useState(0);
  const [filterConfidenceMax, setFilterConfidenceMax] = useState(100);
  const [tempConfidenceThreshold, setTempConfidenceThreshold] = useState(confidenceThreshold);
  
  const debounceTimeout = useRef<NodeJS.Timeout | null>(null);

  const pendingMatches = useMemo(() => {
    return matches.filter(
      (match) =>
        match.is_approved === null &&
        match.confidence_score < confidenceThreshold / 100
    );
  }, [matches, confidenceThreshold]);

  const filteredMatches = useMemo(() => {
    return pendingMatches.filter((match) => {
      const confidencePercent = match.confidence_score * 100;
      const matchesSearch =
        !searchTerm ||
        match.matched_text.toLowerCase().includes(searchTerm.toLowerCase()) ||
        match.original_text.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesConfidence =
        confidencePercent >= filterConfidenceMin &&
        confidencePercent <= filterConfidenceMax;

      return matchesSearch && matchesConfidence;
    });
  }, [pendingMatches, searchTerm, filterConfidenceMin, filterConfidenceMax]);

  const groupedMatches = useMemo(() => {
    const grouped: GroupedMatches = {};
    filteredMatches.forEach((match) => {
      if (!grouped[match.page_number]) {
        grouped[match.page_number] = [];
      }
      grouped[match.page_number].push(match);
    });
    return grouped;
  }, [filteredMatches]);

  const statistics = useMemo(() => {
    const total = matches.length;
    const approved = matches.filter((m) => m.is_approved === true).length;
    const rejected = matches.filter((m) => m.is_approved === false).length;
    const pending = matches.filter((m) => m.is_approved === null).length;
    const autoApproved = matches.filter(
      (m) => m.confidence_score >= confidenceThreshold / 100
    ).length;

    return { total, approved, rejected, pending, autoApproved };
  }, [matches, confidenceThreshold]);

  // Debounced confidence threshold handler
  const debouncedSetConfidenceThreshold = useCallback((value: number) => {
    if (debounceTimeout.current) {
      clearTimeout(debounceTimeout.current);
    }
    
    debounceTimeout.current = setTimeout(() => {
      setConfidenceThreshold(value);
    }, 300);
  }, [setConfidenceThreshold]);

  const handleConfidenceThresholdChange = useCallback((value: number) => {
    setTempConfidenceThreshold(value);
    debouncedSetConfidenceThreshold(value);
  }, [debouncedSetConfidenceThreshold]);

  const togglePageExpansion = useCallback((pageNumber: number) => {
    setExpandedPages((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(pageNumber)) {
        newSet.delete(pageNumber);
      } else {
        newSet.add(pageNumber);
      }
      return newSet;
    });
  }, []);

  const handleApprove = useCallback(
    (matchId: string) => {
      approveMatch(matchId);
      const index = filteredMatches.findIndex((m) => m.id === matchId);
      if (index < filteredMatches.length - 1) {
        setSelectedMatchId(filteredMatches[index + 1].id);
      }
    },
    [approveMatch, filteredMatches]
  );

  const handleReject = useCallback(
    (matchId: string) => {
      rejectMatch(matchId);
      const index = filteredMatches.findIndex((m) => m.id === matchId);
      if (index < filteredMatches.length - 1) {
        setSelectedMatchId(filteredMatches[index + 1].id);
      }
    },
    [rejectMatch, filteredMatches]
  );

  const handleJumpToPage = useCallback(
    (pageNumber: number) => {
      setCurrentPage(pageNumber);
    },
    [setCurrentPage]
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!selectedMatchId) return;

      const currentIndex = filteredMatches.findIndex(
        (m) => m.id === selectedMatchId
      );

      switch (event.key) {
        case 'a':
        case 'A':
          if (!event.ctrlKey && !event.metaKey) {
            event.preventDefault();
            handleApprove(selectedMatchId);
          }
          break;
        case 'r':
        case 'R':
          if (!event.ctrlKey && !event.metaKey) {
            event.preventDefault();
            handleReject(selectedMatchId);
          }
          break;
        case 'ArrowUp':
          event.preventDefault();
          if (currentIndex > 0) {
            setSelectedMatchId(filteredMatches[currentIndex - 1].id);
          }
          break;
        case 'ArrowDown':
          event.preventDefault();
          if (currentIndex < filteredMatches.length - 1) {
            setSelectedMatchId(filteredMatches[currentIndex + 1].id);
          }
          break;
      }
    },
    [selectedMatchId, filteredMatches, handleApprove, handleReject]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    setExpandedPages(new Set([currentPage]));
  }, [currentPage]);

  // Cleanup debounce timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceTimeout.current) {
        clearTimeout(debounceTimeout.current);
      }
    };
  }, []);

  // Sync temp threshold with actual threshold when it changes externally
  useEffect(() => {
    setTempConfidenceThreshold(confidenceThreshold);
  }, [confidenceThreshold]);

  return (
    <div className="w-80 bg-white border-l border-gray-200 overflow-hidden flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold mb-4">Review Matches</h2>

        <div className="mb-4 p-3 bg-gray-50 rounded-lg">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-gray-600">Total:</span>
              <span className="ml-2 font-medium">{statistics.total}</span>
            </div>
            <div>
              <span className="text-gray-600">Pending:</span>
              <span className="ml-2 font-medium text-amber-600">
                {statistics.pending}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Approved:</span>
              <span className="ml-2 font-medium text-green-600">
                {statistics.approved}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Rejected:</span>
              <span className="ml-2 font-medium text-red-600">
                {statistics.rejected}
              </span>
            </div>
          </div>
          {statistics.autoApproved > 0 && (
            <div className="mt-2 text-sm text-gray-600">
              Auto-approved: {statistics.autoApproved}
            </div>
          )}
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Confidence Threshold: {tempConfidenceThreshold}%
          </label>
          <input
            type="range"
            min="0"
            max="100"
            value={tempConfidenceThreshold}
            onChange={(e) => handleConfidenceThresholdChange(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Search matches..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
        </div>

        <div className="mb-4">
          <div className="flex items-center mb-2">
            <Filter className="w-4 h-4 mr-2 text-gray-600" />
            <span className="text-sm font-medium">Confidence Filter</span>
          </div>
          <div className="flex gap-2">
            <input
              type="number"
              min="0"
              max="100"
              value={filterConfidenceMin}
              onChange={(e) => setFilterConfidenceMin(Number(e.target.value))}
              className="w-1/2 px-2 py-1 border border-gray-300 rounded text-sm"
              placeholder="Min %"
            />
            <input
              type="number"
              min="0"
              max="100"
              value={filterConfidenceMax}
              onChange={(e) => setFilterConfidenceMax(Number(e.target.value))}
              className="w-1/2 px-2 py-1 border border-gray-300 rounded text-sm"
              placeholder="Max %"
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <button
            onClick={() => approveAllMatches()}
            className="px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
            disabled={pendingMatches.length === 0}
          >
            Approve All Pending
          </button>
          <button
            onClick={() => rejectAllMatches()}
            className="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
            disabled={pendingMatches.length === 0}
          >
            Reject All Pending
          </button>
          <button
            onClick={() => approveHighConfidenceMatches(90)}
            className="px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
            disabled={pendingMatches.length === 0}
          >
            Approve High Confidence (≥90%)
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {Object.keys(groupedMatches).length === 0 ? (
          <div className="p-4 text-center text-gray-500">
            No pending matches to review
          </div>
        ) : (
          Object.entries(groupedMatches)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([pageNumberStr, pageMatches]) => {
              const pageNumber = Number(pageNumberStr);
              const isExpanded = expandedPages.has(pageNumber);

              return (
                <div key={pageNumber} className="border-b border-gray-200">
                  <button
                    onClick={() => togglePageExpansion(pageNumber)}
                    className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50"
                  >
                    <div className="flex items-center">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 mr-2" />
                      ) : (
                        <ChevronRight className="w-4 h-4 mr-2" />
                      )}
                      <span className="font-medium">Page {pageNumber}</span>
                      <span className="ml-2 text-sm text-gray-500">
                        ({pageMatches.length} matches)
                      </span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleJumpToPage(pageNumber);
                      }}
                      className="text-sm text-blue-600 hover:text-blue-800"
                    >
                      Jump to page
                    </button>
                  </button>

                  {isExpanded && (
                    <div className="px-4 pb-2">
                      {pageMatches.map((match) => (
                        <div
                          key={match.id}
                          className={`mb-2 p-3 border rounded-lg cursor-pointer transition-colors ${
                            selectedMatchId === match.id
                              ? 'border-blue-500 bg-blue-50'
                              : 'border-gray-200 hover:bg-gray-50'
                          }`}
                          onClick={() => setSelectedMatchId(match.id)}
                          role="button"
                          tabIndex={0}
                          aria-label={`Match: ${match.matched_text}`}
                        >
                          <div className="flex justify-between items-start mb-2">
                            <div className="flex-1">
                              <div className="text-sm font-medium">
                                {match.matched_text}
                              </div>
                              {match.original_text !== match.matched_text && (
                                <div className="text-xs text-gray-500 mt-1">
                                  Original: {match.original_text}
                                </div>
                              )}
                            </div>
                            <div className="text-sm font-medium">
                              {Math.round(match.confidence_score * 100)}%
                            </div>
                          </div>

                          <div className="flex gap-2">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleApprove(match.id);
                              }}
                              className="flex-1 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 flex items-center justify-center"
                              aria-label={`Approve ${match.matched_text}`}
                            >
                              <Check className="w-4 h-4 mr-1" />
                              Approve
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleReject(match.id);
                              }}
                              className="flex-1 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 flex items-center justify-center"
                              aria-label={`Reject ${match.matched_text}`}
                            >
                              <X className="w-4 h-4 mr-1" />
                              Reject
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
        )}
      </div>

      <div className="p-4 border-t border-gray-200 text-xs text-gray-600">
        <div className="mb-2 font-semibold">Keyboard Shortcuts:</div>
        <div>A - Approve selected</div>
        <div>R - Reject selected</div>
        <div>↑↓ - Navigate matches</div>
      </div>
    </div>
  );
};

export default MatchReviewSidebar;