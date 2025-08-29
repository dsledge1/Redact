interface PDFCoordinates {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ViewportCoordinates {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Point {
  x: number;
  y: number;
}

interface PageDimensions {
  width: number;
  height: number;
  originalWidth?: number;
  originalHeight?: number;
}

export function pdfToViewport(
  pdfCoords: PDFCoordinates,
  pageWidth: number,
  pageHeight: number,
  scale: number = 1,
  rotation: number = 0
): ViewportCoordinates {
  let viewportCoords: ViewportCoordinates = {
    x: pdfCoords.x * scale,
    y: (pageHeight - pdfCoords.y - pdfCoords.height) * scale,
    width: pdfCoords.width * scale,
    height: pdfCoords.height * scale,
  };

  if (rotation !== 0) {
    viewportCoords = rotateViewportCoordinates(
      viewportCoords,
      rotation,
      pageWidth * scale,
      pageHeight * scale
    );
  }

  return viewportCoords;
}

export function viewportToPdf(
  viewportCoords: ViewportCoordinates,
  pageWidth: number,
  pageHeight: number,
  scale: number = 1,
  rotation: number = 0
): PDFCoordinates {
  let coords = viewportCoords;

  if (rotation !== 0) {
    coords = rotateViewportCoordinates(
      coords,
      -rotation,
      pageWidth * scale,
      pageHeight * scale
    );
  }

  return {
    x: coords.x / scale,
    y: pageHeight - (coords.y / scale + coords.height / scale),
    width: coords.width / scale,
    height: coords.height / scale,
  };
}

export function validateCoordinates(
  coords: PDFCoordinates | ViewportCoordinates,
  pageWidth: number,
  pageHeight: number
): boolean {
  return (
    coords.x >= 0 &&
    coords.y >= 0 &&
    coords.x + coords.width <= pageWidth &&
    coords.y + coords.height <= pageHeight &&
    coords.width > 0 &&
    coords.height > 0
  );
}

export function normalizeRectangle(startPoint: Point, endPoint: Point): ViewportCoordinates {
  const x = Math.min(startPoint.x, endPoint.x);
  const y = Math.min(startPoint.y, endPoint.y);
  const width = Math.abs(endPoint.x - startPoint.x);
  const height = Math.abs(endPoint.y - startPoint.y);

  return { x, y, width, height };
}

export function scaleCoordinates(
  coords: ViewportCoordinates,
  fromScale: number,
  toScale: number
): ViewportCoordinates {
  const scaleFactor = toScale / fromScale;
  return {
    x: coords.x * scaleFactor,
    y: coords.y * scaleFactor,
    width: coords.width * scaleFactor,
    height: coords.height * scaleFactor,
  };
}

function rotateViewportCoordinates(
  coords: ViewportCoordinates,
  rotation: number,
  pageWidth: number,
  pageHeight: number
): ViewportCoordinates {
  const normalizedRotation = ((rotation % 360) + 360) % 360;
  
  switch (normalizedRotation) {
    case 0:
      return coords;
      
    case 90:
      return {
        x: coords.y,
        y: pageWidth - coords.x - coords.width,
        width: coords.height,
        height: coords.width,
      };
      
    case 180:
      return {
        x: pageWidth - coords.x - coords.width,
        y: pageHeight - coords.y - coords.height,
        width: coords.width,
        height: coords.height,
      };
      
    case 270:
      return {
        x: pageHeight - coords.y - coords.height,
        y: coords.x,
        width: coords.height,
        height: coords.width,
      };
      
    default:
      // For non-90-degree rotations, fall back to matrix rotation
      const angle = (normalizedRotation * Math.PI) / 180;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);

      const centerX = coords.x + coords.width / 2;
      const centerY = coords.y + coords.height / 2;

      const rotatedCenterX = centerX * cos - centerY * sin;
      const rotatedCenterY = centerX * sin + centerY * cos;

      return {
        x: rotatedCenterX - coords.width / 2,
        y: rotatedCenterY - coords.height / 2,
        width: coords.width,
        height: coords.height,
      };
  }
}

export function mergeOverlappingRectangles(
  rectangles: ViewportCoordinates[],
  tolerance: number = 0
): ViewportCoordinates[] {
  if (rectangles.length === 0) return [];

  const merged: ViewportCoordinates[] = [];
  const sorted = [...rectangles].sort((a, b) => a.x - b.x || a.y - b.y);

  let current = sorted[0];

  for (let i = 1; i < sorted.length; i++) {
    const rect = sorted[i];
    
    if (isOverlapping(current, rect, tolerance)) {
      current = mergeRectangles(current, rect);
    } else {
      merged.push(current);
      current = rect;
    }
  }

  merged.push(current);
  return merged;
}

function isOverlapping(
  rect1: ViewportCoordinates,
  rect2: ViewportCoordinates,
  tolerance: number
): boolean {
  return !(
    rect1.x + rect1.width + tolerance < rect2.x ||
    rect2.x + rect2.width + tolerance < rect1.x ||
    rect1.y + rect1.height + tolerance < rect2.y ||
    rect2.y + rect2.height + tolerance < rect1.y
  );
}

function mergeRectangles(
  rect1: ViewportCoordinates,
  rect2: ViewportCoordinates
): ViewportCoordinates {
  const x = Math.min(rect1.x, rect2.x);
  const y = Math.min(rect1.y, rect2.y);
  const right = Math.max(rect1.x + rect1.width, rect2.x + rect2.width);
  const bottom = Math.max(rect1.y + rect1.height, rect2.y + rect2.height);

  return {
    x,
    y,
    width: right - x,
    height: bottom - y,
  };
}

export function calculateRectangleArea(rectangle: ViewportCoordinates | PDFCoordinates): number {
  return rectangle.width * rectangle.height;
}

export function snapToGrid(coords: ViewportCoordinates, gridSize: number): ViewportCoordinates {
  return {
    x: Math.round(coords.x / gridSize) * gridSize,
    y: Math.round(coords.y / gridSize) * gridSize,
    width: Math.round(coords.width / gridSize) * gridSize,
    height: Math.round(coords.height / gridSize) * gridSize,
  };
}

export function expandRectangle(
  rectangle: ViewportCoordinates | PDFCoordinates,
  margin: number
): ViewportCoordinates | PDFCoordinates {
  return {
    x: rectangle.x - margin,
    y: rectangle.y - margin,
    width: rectangle.width + margin * 2,
    height: rectangle.height + margin * 2,
  };
}