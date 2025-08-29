import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useUI, useRedactionActions, useRedaction } from '../store/pdfStore';
import { viewportToPdf, pdfToViewport, normalizeRectangle, calculateRectangleArea } from '../utils/coordinateUtils';

interface ManualRedactionToolProps {
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  scale?: number;
  rotation?: number;
  containerRef: React.RefObject<HTMLDivElement>;
}

interface DrawingState {
  isDrawing: boolean;
  startPoint: { x: number; y: number } | null;
  currentPoint: { x: number; y: number } | null;
}

interface EditingState {
  isEditing: boolean;
  editType: 'move' | 'resize' | null;
  dragHandle: string | null; // 'nw', 'ne', 'sw', 'se', 'n', 's', 'e', 'w', 'center'
  startPoint: { x: number; y: number } | null;
  originalRect: { x: number; y: number; width: number; height: number } | null;
}

const ManualRedactionTool: React.FC<ManualRedactionToolProps> = ({
  pageNumber,
  pageWidth,
  pageHeight,
  scale = 1,
  rotation = 0,
  containerRef,
}) => {
  const { manualToolActive, pageDimensions } = useUI();
  const { manualRedactions } = useRedaction();
  const { addManualRedaction, removeManualRedaction, undoLastManualRedaction } = useRedactionActions();
  
  const [drawingState, setDrawingState] = useState<DrawingState>({
    isDrawing: false,
    startPoint: null,
    currentPoint: null,
  });
  
  const [editingState, setEditingState] = useState<EditingState>({
    isEditing: false,
    editType: null,
    dragHandle: null,
    startPoint: null,
    originalRect: null,
  });
  
  const [selectedRedaction, setSelectedRedaction] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Get current page manual redactions
  const pageManualRedactions = manualRedactions.filter(r => r.page === pageNumber);

  const getRelativeCoordinates = useCallback(
    (event: React.MouseEvent | MouseEvent): { x: number; y: number } => {
      if (!containerRef.current) return { x: 0, y: 0 };
      
      const rect = containerRef.current.getBoundingClientRect();
      return {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };
    },
    [containerRef]
  );

  // Check if point is inside a rectangle
  const findRedactionAtPoint = useCallback(
    (point: { x: number; y: number }) => {
      for (const redaction of pageManualRedactions) {
        const viewportRect = pdfToViewport(
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

        if (
          point.x >= viewportRect.x &&
          point.x <= viewportRect.x + viewportRect.width &&
          point.y >= viewportRect.y &&
          point.y <= viewportRect.y + viewportRect.height
        ) {
          return redaction;
        }
      }
      return null;
    },
    [pageManualRedactions, pageWidth, pageHeight, scale, rotation]
  );

  const handleMouseDown = useCallback(
    (event: React.MouseEvent) => {
      if (!manualToolActive) return;
      
      event.preventDefault();
      event.stopPropagation();
      
      const coords = getRelativeCoordinates(event);
      
      // Check if clicking on existing redaction
      const clickedRedaction = findRedactionAtPoint(coords);
      
      if (clickedRedaction) {
        setSelectedRedaction(clickedRedaction.id);
        // For now, just select. Moving/resizing can be added later
        return;
      }
      
      // Start drawing new redaction
      setSelectedRedaction(null);
      setDrawingState({
        isDrawing: true,
        startPoint: coords,
        currentPoint: coords,
      });
    },
    [manualToolActive, getRelativeCoordinates, findRedactionAtPoint]
  );

  const handleMouseMove = useCallback(
    (event: MouseEvent) => {
      if (!drawingState.isDrawing || !drawingState.startPoint) return;
      
      const coords = getRelativeCoordinates(event);
      setDrawingState((prev) => ({
        ...prev,
        currentPoint: coords,
      }));
    },
    [drawingState.isDrawing, drawingState.startPoint, getRelativeCoordinates]
  );

  const handleMouseUp = useCallback(
    (event: MouseEvent) => {
      if (!drawingState.isDrawing || !drawingState.startPoint || !drawingState.currentPoint) {
        setDrawingState({
          isDrawing: false,
          startPoint: null,
          currentPoint: null,
        });
        return;
      }
      
      const viewportRect = normalizeRectangle(
        drawingState.startPoint,
        drawingState.currentPoint
      );
      
      const minArea = 100;
      const area = calculateRectangleArea(viewportRect);
      
      if (area < minArea) {
        setDrawingState({
          isDrawing: false,
          startPoint: null,
          currentPoint: null,
        });
        return;
      }
      
      const pdfRect = viewportToPdf(
        viewportRect,
        pageWidth,
        pageHeight,
        scale,
        rotation
      );
      
      // Get PDF-unit page dimensions for validation
      const currentPageDims = pageDimensions.get(pageNumber);
      const pdfPageWidth = currentPageDims?.originalWidth || pageWidth / scale;
      const pdfPageHeight = currentPageDims?.originalHeight || pageHeight / scale;
      
      if (
        pdfRect.x >= 0 &&
        pdfRect.y >= 0 &&
        pdfRect.x + pdfRect.width <= pdfPageWidth &&
        pdfRect.y + pdfRect.height <= pdfPageHeight
      ) {
        addManualRedaction(pageNumber, {
          x: pdfRect.x,
          y: pdfRect.y,
          width: pdfRect.width,
          height: pdfRect.height,
        });
      }
      
      setDrawingState({
        isDrawing: false,
        startPoint: null,
        currentPoint: null,
      });
    },
    [
      drawingState,
      pageNumber,
      pageWidth,
      pageHeight,
      scale,
      rotation,
      addManualRedaction,
    ]
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!manualToolActive) return;
      
      if (event.key === 'Escape') {
        setDrawingState({
          isDrawing: false,
          startPoint: null,
          currentPoint: null,
        });
      } else if (event.key === 'Delete' && selectedRedaction) {
        removeManualRedaction(selectedRedaction);
        setSelectedRedaction(null);
      } else if ((event.ctrlKey || event.metaKey) && event.key === 'z') {
        event.preventDefault();
        undoLastManualRedaction();
      }
    },
    [manualToolActive, selectedRedaction, removeManualRedaction, undoLastManualRedaction]
  );

  useEffect(() => {
    if (!manualToolActive) {
      setDrawingState({
        isDrawing: false,
        startPoint: null,
        currentPoint: null,
      });
      return;
    }
    
    const handleGlobalMouseMove = (e: MouseEvent) => handleMouseMove(e);
    const handleGlobalMouseUp = (e: MouseEvent) => handleMouseUp(e);
    const handleGlobalKeyDown = (e: KeyboardEvent) => handleKeyDown(e);
    
    document.addEventListener('mousemove', handleGlobalMouseMove);
    document.addEventListener('mouseup', handleGlobalMouseUp);
    document.addEventListener('keydown', handleGlobalKeyDown);
    
    return () => {
      document.removeEventListener('mousemove', handleGlobalMouseMove);
      document.removeEventListener('mouseup', handleGlobalMouseUp);
      document.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [manualToolActive, handleMouseMove, handleMouseUp, handleKeyDown]);

  useEffect(() => {
    if (!manualToolActive && containerRef.current) {
      containerRef.current.style.cursor = '';
    } else if (manualToolActive && containerRef.current) {
      containerRef.current.style.cursor = 'crosshair';
    }
  }, [manualToolActive, containerRef]);

  if (!manualToolActive && !drawingState.isDrawing) {
    return null;
  }

  const renderDrawingRectangle = () => {
    if (!drawingState.startPoint || !drawingState.currentPoint) return null;
    
    const rect = normalizeRectangle(drawingState.startPoint, drawingState.currentPoint);
    
    return (
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        fill="rgba(59, 130, 246, 0.2)"
        stroke="#3b82f6"
        strokeWidth={2}
        strokeDasharray="5 5"
        pointerEvents="none"
      />
    );
  };

  const renderGuideLines = () => {
    if (!drawingState.currentPoint || !manualToolActive) return null;
    
    const { x, y } = drawingState.currentPoint;
    
    return (
      <>
        <line
          x1={x}
          y1={0}
          x2={x}
          y2={pageHeight * scale}
          stroke="rgba(59, 130, 246, 0.3)"
          strokeWidth={1}
          strokeDasharray="2 2"
          pointerEvents="none"
        />
        <line
          x1={0}
          y1={y}
          x2={pageWidth * scale}
          y2={y}
          stroke="rgba(59, 130, 246, 0.3)"
          strokeWidth={1}
          strokeDasharray="2 2"
          pointerEvents="none"
        />
      </>
    );
  };

  const renderDimensions = () => {
    if (!drawingState.startPoint || !drawingState.currentPoint) return null;
    
    const rect = normalizeRectangle(drawingState.startPoint, drawingState.currentPoint);
    const pdfRect = viewportToPdf(rect, pageWidth, pageHeight, scale, rotation);
    
    const widthPx = Math.round(pdfRect.width);
    const heightPx = Math.round(pdfRect.height);
    
    return (
      <foreignObject
        x={rect.x + rect.width / 2 - 50}
        y={rect.y + rect.height / 2 - 10}
        width={100}
        height={20}
        pointerEvents="none"
      >
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.7)',
            color: 'white',
            padding: '2px 6px',
            borderRadius: '3px',
            fontSize: '11px',
            textAlign: 'center',
            whiteSpace: 'nowrap',
          }}
        >
          {widthPx} × {heightPx}
        </div>
      </foreignObject>
    );
  };

  const renderExistingRedactions = () => {
    return pageManualRedactions.map((redaction) => {
      const viewportRect = pdfToViewport(
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

      const isSelected = selectedRedaction === redaction.id;

      return (
        <g key={redaction.id}>
          <rect
            x={viewportRect.x}
            y={viewportRect.y}
            width={viewportRect.width}
            height={viewportRect.height}
            fill="rgba(59, 130, 246, 0.2)"
            stroke={isSelected ? "#3b82f6" : "rgba(59, 130, 246, 0.5)"}
            strokeWidth={isSelected ? 3 : 2}
            strokeDasharray={isSelected ? "none" : "4 2"}
            pointerEvents="auto"
            style={{ cursor: 'pointer' }}
          />
          
          {isSelected && (
            <>
              {/* Corner resize handles */}
              <rect
                x={viewportRect.x - 4}
                y={viewportRect.y - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'nw-resize' }}
                data-handle="nw"
              />
              <rect
                x={viewportRect.x + viewportRect.width - 4}
                y={viewportRect.y - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'ne-resize' }}
                data-handle="ne"
              />
              <rect
                x={viewportRect.x - 4}
                y={viewportRect.y + viewportRect.height - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'sw-resize' }}
                data-handle="sw"
              />
              <rect
                x={viewportRect.x + viewportRect.width - 4}
                y={viewportRect.y + viewportRect.height - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'se-resize' }}
                data-handle="se"
              />
              
              {/* Edge resize handles */}
              <rect
                x={viewportRect.x + viewportRect.width / 2 - 4}
                y={viewportRect.y - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'n-resize' }}
                data-handle="n"
              />
              <rect
                x={viewportRect.x + viewportRect.width / 2 - 4}
                y={viewportRect.y + viewportRect.height - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 's-resize' }}
                data-handle="s"
              />
              <rect
                x={viewportRect.x - 4}
                y={viewportRect.y + viewportRect.height / 2 - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'w-resize' }}
                data-handle="w"
              />
              <rect
                x={viewportRect.x + viewportRect.width - 4}
                y={viewportRect.y + viewportRect.height / 2 - 4}
                width={8}
                height={8}
                fill="#3b82f6"
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'e-resize' }}
                data-handle="e"
              />
            </>
          )}
        </g>
      );
    });
  };

  return (
    <svg
      ref={svgRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: pageWidth * scale,
        height: pageHeight * scale,
        pointerEvents: manualToolActive ? 'auto' : 'none',
        zIndex: 20,
      }}
      width={pageWidth * scale}
      height={pageHeight * scale}
      onMouseDown={handleMouseDown}
      aria-label="Manual redaction drawing area"
    >
      {renderGuideLines()}
      {renderExistingRedactions()}
      {drawingState.isDrawing && (
        <>
          {renderDrawingRectangle()}
          {renderDimensions()}
        </>
      )}
    </svg>
  );
};

export default ManualRedactionTool;