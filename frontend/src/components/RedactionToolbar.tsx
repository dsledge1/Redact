import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  useRedaction,
  useRedactionActions,
  useUI,
  useUIActions,
} from '../store/pdfStore';
import {
  Settings,
  Square,
  Check,
  X,
  Download,
  RotateCcw,
  HelpCircle,
  Play,
  AlertCircle,
  Loader,
} from 'lucide-react';

const RedactionToolbar: React.FC = () => {
  const {
    matches,
    manualRedactions,
    confidenceThreshold,
    processingStatus,
    downloadUrl,
    errors,
  } = useRedaction();
  
  const {
    approveAllMatches,
    rejectAllMatches,
    removeAllManualRedactions,
    finalizeRedaction,
    setConfidenceThreshold,
    undoLastManualRedaction,
  } = useRedactionActions();
  
  const { manualToolActive } = useUI();
  const { toggleManualTool } = useUIActions();

  const [showConfirmDialog, setShowConfirmDialog] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [tempConfidenceThreshold, setTempConfidenceThreshold] = useState(confidenceThreshold);
  
  const debounceTimeout = useRef<NodeJS.Timeout | null>(null);

  const statistics = useMemo(() => {
    const totalMatches = matches.length;
    const approvedMatches = matches.filter((m) => m.is_approved === true).length;
    const rejectedMatches = matches.filter((m) => m.is_approved === false).length;
    const pendingMatches = matches.filter((m) => m.is_approved === null).length;
    const autoApprovedMatches = matches.filter(
      (m) => m.confidence_score >= confidenceThreshold / 100
    ).length;
    const manualCount = manualRedactions.length;
    const totalPages = new Set([
      ...matches.map((m) => m.page_number),
      ...manualRedactions.map((r) => r.page),
    ]).size;

    const completionPercentage = totalMatches > 0 
      ? Math.round(((approvedMatches + rejectedMatches) / totalMatches) * 100)
      : 0;

    return {
      totalMatches,
      approvedMatches,
      rejectedMatches,
      pendingMatches,
      autoApprovedMatches,
      manualCount,
      totalPages,
      completionPercentage,
    };
  }, [matches, manualRedactions, confidenceThreshold]);

  const canFinalize = useMemo(() => {
    const hasApprovedOrManual = 
      statistics.approvedMatches > 0 || statistics.manualCount > 0;
    // Only gate finalization on pending matches below threshold
    const pendingBelowThreshold = matches.filter(
      m => m.is_approved === null && (m.confidence_score * 100) < confidenceThreshold
    ).length;
    
    return hasApprovedOrManual && pendingBelowThreshold === 0 && processingStatus !== 'processing';
  }, [statistics, matches, confidenceThreshold, processingStatus]);

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

  const handleConfirmAction = useCallback((action: string, callback: () => void) => {
    setShowConfirmDialog(action);
    const confirmed = window.confirm(
      `Are you sure you want to ${action.toLowerCase()}? This action cannot be undone.`
    );
    
    if (confirmed) {
      callback();
    }
    setShowConfirmDialog(null);
  }, []);

  const handleFinalize = useCallback(() => {
    const approvedMatchIds = matches
      .filter((m) => m.is_approved === true)
      .map((m) => m.id);

    const finalizeWithData = () => {
      finalizeRedaction(approvedMatchIds, manualRedactions);
    };

    handleConfirmAction('Finalize Redaction', finalizeWithData);
  }, [matches, manualRedactions, finalizeRedaction, handleConfirmAction]);

  const handleClearAllManual = useCallback(() => {
    handleConfirmAction('Clear All Manual Redactions', removeAllManualRedactions);
  }, [removeAllManualRedactions, handleConfirmAction]);

  const renderHelpDialog = () => {
    if (!showHelp) return null;

    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center">
              <HelpCircle className="w-5 h-5 mr-2" />
              Redaction Workflow Help
            </h3>
            <button
              onClick={() => setShowHelp(false)}
              className="text-gray-500 hover:text-gray-700"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          
          <div className="space-y-3 text-sm">
            <div>
              <h4 className="font-medium mb-1">1. Review Matches</h4>
              <p className="text-gray-600">
                Approve or reject fuzzy matches in the sidebar. Use keyboard shortcuts A (approve) and R (reject).
              </p>
            </div>
            
            <div>
              <h4 className="font-medium mb-1">2. Manual Redaction</h4>
              <p className="text-gray-600">
                Toggle manual mode and draw rectangles over sensitive content by clicking and dragging.
              </p>
            </div>
            
            <div>
              <h4 className="font-medium mb-1">3. Finalize</h4>
              <p className="text-gray-600">
                Once all matches are reviewed, click "Finalize" to permanently redact the document.
              </p>
            </div>
            
            <div>
              <h4 className="font-medium mb-1">Keyboard Shortcuts</h4>
              <ul className="text-gray-600 space-y-1">
                <li>A - Approve selected match</li>
                <li>R - Reject selected match</li>
                <li>Esc - Cancel manual drawing</li>
                <li>Ctrl+Z - Undo last manual redaction</li>
                <li>↑↓ - Navigate matches</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    );
  };

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
    <>
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <div className="flex items-center space-x-2">
              <Settings className="w-5 h-5 text-gray-600" />
              <span className="font-medium">Redaction Tools</span>
            </div>

            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700">
                Confidence: {tempConfidenceThreshold}%
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={tempConfidenceThreshold}
                onChange={(e) => handleConfidenceThresholdChange(Number(e.target.value))}
                className="w-24"
                title="Confidence threshold for auto-approval"
              />
            </div>

            <button
              onClick={toggleManualTool}
              className={`flex items-center space-x-2 px-3 py-2 rounded transition-colors ${
                manualToolActive
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
              title="Toggle manual redaction tool"
            >
              <Square className="w-4 h-4" />
              <span>Manual</span>
            </button>

            {manualRedactions.length > 0 && (
              <button
                onClick={() => undoLastManualRedaction()}
                className="flex items-center space-x-2 px-3 py-2 text-orange-600 hover:bg-orange-50 rounded transition-colors"
                title="Undo last manual redaction (Ctrl+Z)"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Undo</span>
              </button>
            )}
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-sm text-gray-600">
              Progress: {statistics.completionPercentage}%
              {statistics.pendingMatches > 0 && (
                <span className="ml-2 text-amber-600">
                  ({statistics.pendingMatches} pending)
                </span>
              )}
            </div>

            <div className="w-32 bg-gray-200 rounded-full h-2">
              <div
                className="bg-green-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${statistics.completionPercentage}%` }}
              />
            </div>

            <button
              onClick={() => setShowHelp(true)}
              className="p-2 text-gray-600 hover:bg-gray-100 rounded transition-colors"
              title="Show help"
            >
              <HelpCircle className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center space-x-6 text-sm">
            <div className="flex items-center space-x-4">
              <span className="text-gray-600">
                Total: <span className="font-medium">{statistics.totalMatches}</span>
              </span>
              <span className="text-green-600">
                Approved: <span className="font-medium">{statistics.approvedMatches}</span>
              </span>
              <span className="text-red-600">
                Rejected: <span className="font-medium">{statistics.rejectedMatches}</span>
              </span>
              <span className="text-blue-600">
                Manual: <span className="font-medium">{statistics.manualCount}</span>
              </span>
              <span className="text-gray-600">
                Pages: <span className="font-medium">{statistics.totalPages}</span>
              </span>
            </div>

            {statistics.autoApprovedMatches > 0 && (
              <span className="text-gray-600">
                Auto-approved: <span className="font-medium">{statistics.autoApprovedMatches}</span>
              </span>
            )}
          </div>

          <div className="flex items-center space-x-2">
            {statistics.pendingMatches > 0 && (
              <>
                <button
                  onClick={approveAllMatches}
                  className="flex items-center space-x-1 px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 text-sm transition-colors"
                  title="Approve all pending matches"
                >
                  <Check className="w-4 h-4" />
                  <span>Approve All</span>
                </button>

                <button
                  onClick={rejectAllMatches}
                  className="flex items-center space-x-1 px-3 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 text-sm transition-colors"
                  title="Reject all pending matches"
                >
                  <X className="w-4 h-4" />
                  <span>Reject All</span>
                </button>
              </>
            )}

            {statistics.manualCount > 0 && (
              <button
                onClick={handleClearAllManual}
                className="flex items-center space-x-1 px-3 py-1.5 bg-gray-600 text-white rounded hover:bg-gray-700 text-sm transition-colors"
                title="Clear all manual redactions"
              >
                <X className="w-4 h-4" />
                <span>Clear Manual</span>
              </button>
            )}

            <button
              onClick={handleFinalize}
              disabled={!canFinalize}
              className={`flex items-center space-x-1 px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                canFinalize
                  ? 'bg-purple-600 text-white hover:bg-purple-700'
                  : 'bg-gray-300 text-gray-500 cursor-not-allowed'
              }`}
              title={
                !canFinalize
                  ? 'Complete all reviews before finalizing'
                  : 'Finalize redaction and generate final document'
              }
            >
              {processingStatus === 'processing' ? (
                <Loader className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              <span>Finalize</span>
            </button>
          </div>
        </div>

        {errors.length > 0 && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
            <div className="flex items-center">
              <AlertCircle className="w-5 h-5 text-red-600 mr-2" />
              <div className="text-sm text-red-700">
                <div className="font-medium">Redaction Errors:</div>
                <ul className="mt-1 list-disc list-inside">
                  {errors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {downloadUrl && (
          <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-md">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <Download className="w-5 h-5 text-green-600 mr-2" />
                <div className="text-sm text-green-700">
                  <div className="font-medium">Redaction Complete!</div>
                  <div>Your redacted document is ready for download.</div>
                </div>
              </div>
              <a
                href={downloadUrl}
                download
                className="flex items-center space-x-1 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                <Download className="w-4 h-4" />
                <span>Download</span>
              </a>
            </div>
          </div>
        )}
      </div>

      {renderHelpDialog()}
    </>
  );
};

export default RedactionToolbar;