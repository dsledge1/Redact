import React, { useMemo, useCallback, useState } from 'react';
import { useRedaction, useRedactionActions, useUI } from '../store/pdfStore';
import { pdfToViewport } from '../utils/coordinateUtils';
import { RedactionMatch, ManualRedaction } from '../types';

interface RedactionOverlayProps {
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  scale?: number;
  rotation?: number;
  onClick?: (match: RedactionMatch) => void;
}

const RedactionOverlay: React.FC<RedactionOverlayProps> = ({
  pageNumber,
  pageWidth,
  pageHeight,
  scale = 1,
  rotation = 0,
  onClick,
}) => {
  const { matches, manualRedactions } = useRedaction();
  const { approveMatch, rejectMatch } = useRedactionActions();
  const { currentPage } = useUI();
  const [hoveredMatch, setHoveredMatch] = useState<string | null>(null);

  const pageMatches = useMemo(() => {
    return matches.filter((match) => match.page_number === pageNumber);
  }, [matches, pageNumber]);

  const pageManualRedactions = useMemo(() => {
    return manualRedactions.filter((redaction) => redaction.page === pageNumber);
  }, [manualRedactions, pageNumber]);

  const getMatchColor = useCallback((match: RedactionMatch) => {
    if (match.is_approved === true) return '#10b981';
    if (match.is_approved === false) return '#ef4444';
    return '#f59e0b';
  }, []);

  const getMatchOpacity = useCallback((match: RedactionMatch) => {
    return hoveredMatch === match.id ? 0.5 : 0.3;
  }, [hoveredMatch]);

  const handleMatchClick = useCallback(
    (event: React.MouseEvent, match: RedactionMatch) => {
      event.stopPropagation();
      
      if (match.is_approved === null) {
        if (onClick) {
          onClick(match);
        }
      }
    },
    [onClick]
  );

  const handleMatchDoubleClick = useCallback(
    (event: React.MouseEvent, match: RedactionMatch) => {
      event.stopPropagation();
      
      if (match.is_approved === null) {
        approveMatch(match.id);
      }
    },
    [approveMatch]
  );

  const renderRedactionRectangle = useCallback(
    (match: RedactionMatch) => {
      const viewportCoords = pdfToViewport(
        {
          x: match.x_coordinate,
          y: match.y_coordinate,
          width: match.width,
          height: match.height,
        },
        pageWidth,
        pageHeight,
        scale,
        rotation
      );

      const color = getMatchColor(match);
      const opacity = getMatchOpacity(match);
      const isPending = match.is_approved === null;

      return (
        <g key={match.id}>
          <rect
            x={viewportCoords.x}
            y={viewportCoords.y}
            width={viewportCoords.width}
            height={viewportCoords.height}
            fill={color}
            fillOpacity={opacity}
            stroke={color}
            strokeWidth={2}
            strokeOpacity={0.8}
            cursor={isPending ? 'pointer' : 'default'}
            onClick={(e) => handleMatchClick(e, match)}
            onDoubleClick={(e) => handleMatchDoubleClick(e, match)}
            onMouseEnter={() => setHoveredMatch(match.id)}
            onMouseLeave={() => setHoveredMatch(null)}
            role="button"
            tabIndex={isPending ? 0 : -1}
            aria-label={`${
              match.is_approved === true
                ? 'Approved'
                : match.is_approved === false
                ? 'Rejected'
                : 'Pending'
            } redaction: ${match.matched_text} (${Math.round(match.confidence_score * 100)}% confidence)`}
          />
          {hoveredMatch === match.id && (
            <foreignObject
              x={viewportCoords.x}
              y={viewportCoords.y - 30}
              width={200}
              height={30}
              pointerEvents="none"
            >
              <div
                style={{
                  background: 'rgba(0, 0, 0, 0.8)',
                  color: 'white',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {match.matched_text} ({Math.round(match.confidence_score * 100)}%)
              </div>
            </foreignObject>
          )}
        </g>
      );
    },
    [
      pageWidth,
      pageHeight,
      scale,
      rotation,
      getMatchColor,
      getMatchOpacity,
      handleMatchClick,
      handleMatchDoubleClick,
      hoveredMatch,
    ]
  );

  const renderManualRedaction = useCallback(
    (redaction: ManualRedaction, index: number) => {
      const viewportCoords = pdfToViewport(
        {
          x: redaction.x,
          y: redaction.y,
          width: redaction.width,
          height: redaction.height,
        },
        pageWidth,
        pageHeight,
        scale,
        rotation
      );

      return (
        <rect
          key={`manual-${index}`}
          x={viewportCoords.x}
          y={viewportCoords.y}
          width={viewportCoords.width}
          height={viewportCoords.height}
          fill="#3b82f6"
          fillOpacity={0.3}
          stroke="#3b82f6"
          strokeWidth={2}
          strokeOpacity={0.8}
          strokeDasharray="4 2"
          aria-label="Manual redaction area"
        />
      );
    },
    [pageWidth, pageHeight, scale, rotation]
  );

  if (pageMatches.length === 0 && pageManualRedactions.length === 0) {
    return null;
  }

  return (
    <svg
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: pageWidth * scale,
        height: pageHeight * scale,
        pointerEvents: 'auto',
        zIndex: 10,
      }}
      width={pageWidth * scale}
      height={pageHeight * scale}
      aria-label="Redaction overlay"
    >
      {pageMatches.map(renderRedactionRectangle)}
      {pageManualRedactions.map(renderManualRedaction)}
    </svg>
  );
};

export default RedactionOverlay;