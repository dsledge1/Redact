import { describe, it, expect } from 'vitest';
import {
  pdfToViewport,
  viewportToPdf,
  validateCoordinates,
  normalizeRectangle,
  scaleCoordinates,
  mergeOverlappingRectangles,
  calculateRectangleArea,
  snapToGrid,
  expandRectangle,
} from '../../utils/coordinateUtils';

describe('coordinateUtils', () => {
  describe('pdfToViewport', () => {
    it('converts PDF coordinates to viewport coordinates correctly', () => {
      const pdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 0;

      const result = pdfToViewport(pdfCoords, pageWidth, pageHeight, scale, rotation);

      expect(result).toEqual({
        x: 100,
        y: 780, // pageHeight - pdfCoords.y - pdfCoords.height = 1000 - 200 - 20 = 780
        width: 80,
        height: 20,
      });
    });

    it('applies scaling correctly', () => {
      const pdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 2;
      const rotation = 0;

      const result = pdfToViewport(pdfCoords, pageWidth, pageHeight, scale, rotation);

      expect(result).toEqual({
        x: 200,
        y: 1560, // (1000 - 200 - 20) * 2
        width: 160,
        height: 40,
      });
    });

    it('handles 90-degree rotation correctly', () => {
      const pdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 90;

      const result = pdfToViewport(pdfCoords, pageWidth, pageHeight, scale, rotation);

      // For 90-degree rotation: x' = y, y' = pageWidth - x - width, dimensions swap
      expect(result.x).toBe(780); // pageHeight - pdfCoords.y - pdfCoords.height = 1000 - 200 - 20 = 780
      expect(result.y).toBe(620); // pageWidth - (pdfCoords.x + pdfCoords.width) = 800 - (100 + 80) = 620
      expect(result.width).toBe(20); // height becomes width
      expect(result.height).toBe(80); // width becomes height
    });

    it('handles 180-degree rotation correctly', () => {
      const pdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 180;

      const result = pdfToViewport(pdfCoords, pageWidth, pageHeight, scale, rotation);

      // For 180-degree rotation: x' = pageWidth - x - width, y' = pageHeight - y - height
      expect(result.x).toBe(620); // pageWidth - (pdfCoords.x + pdfCoords.width) = 800 - (100 + 80) = 620
      expect(result.y).toBe(220); // pageHeight - (original y + height) = 1000 - (780 + 20) = 200, but we need viewport coords
      expect(result.width).toBe(80); // dimensions unchanged
      expect(result.height).toBe(20);
    });

    it('handles 270-degree rotation correctly', () => {
      const pdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 270;

      const result = pdfToViewport(pdfCoords, pageWidth, pageHeight, scale, rotation);

      // For 270-degree rotation: x' = pageHeight - y - height, y' = x, dimensions swap
      expect(result.x).toBe(780); // pageHeight - (pdfCoords.y + pdfCoords.height) = 1000 - (200 + 20) = 780
      expect(result.y).toBe(100); // pdfCoords.x
      expect(result.width).toBe(20); // height becomes width
      expect(result.height).toBe(80); // width becomes height
    });

    it('uses default values when parameters are not provided', () => {
      const pdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;

      const result = pdfToViewport(pdfCoords, pageWidth, pageHeight);

      expect(result).toEqual({
        x: 100,
        y: 780,
        width: 80,
        height: 20,
      });
    });
  });

  describe('viewportToPdf', () => {
    it('converts viewport coordinates to PDF coordinates correctly', () => {
      const viewportCoords = { x: 100, y: 780, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 0;

      const result = viewportToPdf(viewportCoords, pageWidth, pageHeight, scale, rotation);

      expect(result).toEqual({
        x: 100,
        y: 200, // pageHeight - (viewportCoords.y + viewportCoords.height) = 1000 - (780 + 20) = 200
        width: 80,
        height: 20,
      });
    });

    it('handles scaling correctly in reverse', () => {
      const viewportCoords = { x: 200, y: 1560, width: 160, height: 40 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 2;
      const rotation = 0;

      const result = viewportToPdf(viewportCoords, pageWidth, pageHeight, scale, rotation);

      expect(result).toEqual({
        x: 100,
        y: 200,
        width: 80,
        height: 20,
      });
    });

    it('is inverse of pdfToViewport without rotation', () => {
      const originalPdfCoords = { x: 150, y: 300, width: 100, height: 25 };
      const pageWidth = 800;
      const pageHeight = 1200;
      const scale = 1.5;

      const viewportCoords = pdfToViewport(originalPdfCoords, pageWidth, pageHeight, scale, 0);
      const backToPdfCoords = viewportToPdf(viewportCoords, pageWidth, pageHeight, scale, 0);

      expect(backToPdfCoords).toEqual(originalPdfCoords);
    });

    it('handles round-trip conversion with 90-degree rotation', () => {
      const originalPdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 90;

      const viewportCoords = pdfToViewport(originalPdfCoords, pageWidth, pageHeight, scale, rotation);
      const backToPdfCoords = viewportToPdf(viewportCoords, pageWidth, pageHeight, scale, rotation);

      expect(backToPdfCoords.x).toBeCloseTo(originalPdfCoords.x, 10);
      expect(backToPdfCoords.y).toBeCloseTo(originalPdfCoords.y, 10);
      expect(backToPdfCoords.width).toBeCloseTo(originalPdfCoords.width, 10);
      expect(backToPdfCoords.height).toBeCloseTo(originalPdfCoords.height, 10);
    });

    it('handles round-trip conversion with 180-degree rotation', () => {
      const originalPdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 180;

      const viewportCoords = pdfToViewport(originalPdfCoords, pageWidth, pageHeight, scale, rotation);
      const backToPdfCoords = viewportToPdf(viewportCoords, pageWidth, pageHeight, scale, rotation);

      expect(backToPdfCoords.x).toBeCloseTo(originalPdfCoords.x, 10);
      expect(backToPdfCoords.y).toBeCloseTo(originalPdfCoords.y, 10);
      expect(backToPdfCoords.width).toBeCloseTo(originalPdfCoords.width, 10);
      expect(backToPdfCoords.height).toBeCloseTo(originalPdfCoords.height, 10);
    });

    it('handles round-trip conversion with 270-degree rotation', () => {
      const originalPdfCoords = { x: 100, y: 200, width: 80, height: 20 };
      const pageWidth = 800;
      const pageHeight = 1000;
      const scale = 1;
      const rotation = 270;

      const viewportCoords = pdfToViewport(originalPdfCoords, pageWidth, pageHeight, scale, rotation);
      const backToPdfCoords = viewportToPdf(viewportCoords, pageWidth, pageHeight, scale, rotation);

      expect(backToPdfCoords.x).toBeCloseTo(originalPdfCoords.x, 10);
      expect(backToPdfCoords.y).toBeCloseTo(originalPdfCoords.y, 10);
      expect(backToPdfCoords.width).toBeCloseTo(originalPdfCoords.width, 10);
      expect(backToPdfCoords.height).toBeCloseTo(originalPdfCoords.height, 10);
    });
  });

  describe('validateCoordinates', () => {
    it('validates coordinates within page bounds', () => {
      const coords = { x: 50, y: 100, width: 200, height: 50 };
      const pageWidth = 800;
      const pageHeight = 1000;

      const result = validateCoordinates(coords, pageWidth, pageHeight);

      expect(result).toBe(true);
    });

    it('rejects coordinates outside page bounds', () => {
      const coords = { x: 750, y: 100, width: 200, height: 50 };
      const pageWidth = 800;
      const pageHeight = 1000;

      const result = validateCoordinates(coords, pageWidth, pageHeight);

      expect(result).toBe(false);
    });

    it('rejects negative coordinates', () => {
      const coords = { x: -10, y: 100, width: 200, height: 50 };
      const pageWidth = 800;
      const pageHeight = 1000;

      const result = validateCoordinates(coords, pageWidth, pageHeight);

      expect(result).toBe(false);
    });

    it('rejects zero or negative dimensions', () => {
      const coords = { x: 100, y: 100, width: 0, height: 50 };
      const pageWidth = 800;
      const pageHeight = 1000;

      const result = validateCoordinates(coords, pageWidth, pageHeight);

      expect(result).toBe(false);
    });

    it('validates coordinates exactly at page bounds', () => {
      const coords = { x: 0, y: 0, width: 800, height: 1000 };
      const pageWidth = 800;
      const pageHeight = 1000;

      const result = validateCoordinates(coords, pageWidth, pageHeight);

      expect(result).toBe(true);
    });
  });

  describe('normalizeRectangle', () => {
    it('normalizes rectangle drawn from top-left to bottom-right', () => {
      const startPoint = { x: 100, y: 100 };
      const endPoint = { x: 200, y: 150 };

      const result = normalizeRectangle(startPoint, endPoint);

      expect(result).toEqual({
        x: 100,
        y: 100,
        width: 100,
        height: 50,
      });
    });

    it('normalizes rectangle drawn from bottom-right to top-left', () => {
      const startPoint = { x: 200, y: 150 };
      const endPoint = { x: 100, y: 100 };

      const result = normalizeRectangle(startPoint, endPoint);

      expect(result).toEqual({
        x: 100,
        y: 100,
        width: 100,
        height: 50,
      });
    });

    it('normalizes rectangle drawn from top-right to bottom-left', () => {
      const startPoint = { x: 200, y: 100 };
      const endPoint = { x: 100, y: 150 };

      const result = normalizeRectangle(startPoint, endPoint);

      expect(result).toEqual({
        x: 100,
        y: 100,
        width: 100,
        height: 50,
      });
    });

    it('handles zero-size rectangles', () => {
      const startPoint = { x: 100, y: 100 };
      const endPoint = { x: 100, y: 100 };

      const result = normalizeRectangle(startPoint, endPoint);

      expect(result).toEqual({
        x: 100,
        y: 100,
        width: 0,
        height: 0,
      });
    });
  });

  describe('scaleCoordinates', () => {
    it('scales coordinates up correctly', () => {
      const coords = { x: 100, y: 200, width: 80, height: 20 };
      const fromScale = 1;
      const toScale = 2;

      const result = scaleCoordinates(coords, fromScale, toScale);

      expect(result).toEqual({
        x: 200,
        y: 400,
        width: 160,
        height: 40,
      });
    });

    it('scales coordinates down correctly', () => {
      const coords = { x: 200, y: 400, width: 160, height: 40 };
      const fromScale = 2;
      const toScale = 1;

      const result = scaleCoordinates(coords, fromScale, toScale);

      expect(result).toEqual({
        x: 100,
        y: 200,
        width: 80,
        height: 20,
      });
    });

    it('handles same scale factor', () => {
      const coords = { x: 100, y: 200, width: 80, height: 20 };
      const fromScale = 1.5;
      const toScale = 1.5;

      const result = scaleCoordinates(coords, fromScale, toScale);

      expect(result).toEqual(coords);
    });

    it('handles fractional scale factors', () => {
      const coords = { x: 100, y: 200, width: 80, height: 20 };
      const fromScale = 2;
      const toScale = 1.5;

      const result = scaleCoordinates(coords, fromScale, toScale);

      expect(result).toEqual({
        x: 75,
        y: 150,
        width: 60,
        height: 15,
      });
    });
  });

  describe('mergeOverlappingRectangles', () => {
    it('merges overlapping rectangles', () => {
      const rectangles = [
        { x: 100, y: 100, width: 100, height: 50 },
        { x: 150, y: 120, width: 100, height: 50 },
      ];

      const result = mergeOverlappingRectangles(rectangles);

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        x: 100,
        y: 100,
        width: 150, // merged width
        height: 70,  // merged height
      });
    });

    it('does not merge non-overlapping rectangles', () => {
      const rectangles = [
        { x: 100, y: 100, width: 50, height: 50 },
        { x: 200, y: 200, width: 50, height: 50 },
      ];

      const result = mergeOverlappingRectangles(rectangles);

      expect(result).toHaveLength(2);
      expect(result).toEqual(rectangles);
    });

    it('handles empty array', () => {
      const rectangles: any[] = [];

      const result = mergeOverlappingRectangles(rectangles);

      expect(result).toEqual([]);
    });

    it('handles single rectangle', () => {
      const rectangles = [
        { x: 100, y: 100, width: 50, height: 50 },
      ];

      const result = mergeOverlappingRectangles(rectangles);

      expect(result).toEqual(rectangles);
    });

    it('applies tolerance correctly', () => {
      const rectangles = [
        { x: 100, y: 100, width: 50, height: 50 },
        { x: 152, y: 100, width: 50, height: 50 }, // 2px gap
      ];

      const resultWithoutTolerance = mergeOverlappingRectangles(rectangles, 0);
      const resultWithTolerance = mergeOverlappingRectangles(rectangles, 5);

      expect(resultWithoutTolerance).toHaveLength(2);
      expect(resultWithTolerance).toHaveLength(1);
    });
  });

  describe('calculateRectangleArea', () => {
    it('calculates area correctly', () => {
      const rectangle = { x: 100, y: 100, width: 80, height: 20 };

      const result = calculateRectangleArea(rectangle);

      expect(result).toBe(1600);
    });

    it('handles zero area rectangles', () => {
      const rectangle = { x: 100, y: 100, width: 0, height: 20 };

      const result = calculateRectangleArea(rectangle);

      expect(result).toBe(0);
    });

    it('works with fractional dimensions', () => {
      const rectangle = { x: 100, y: 100, width: 10.5, height: 20.5 };

      const result = calculateRectangleArea(rectangle);

      expect(result).toBe(215.25);
    });
  });

  describe('snapToGrid', () => {
    it('snaps coordinates to grid correctly', () => {
      const coords = { x: 103, y: 197, width: 78, height: 23 };
      const gridSize = 10;

      const result = snapToGrid(coords, gridSize);

      expect(result).toEqual({
        x: 100,
        y: 200,
        width: 80,
        height: 20,
      });
    });

    it('handles coordinates already on grid', () => {
      const coords = { x: 100, y: 200, width: 80, height: 20 };
      const gridSize = 10;

      const result = snapToGrid(coords, gridSize);

      expect(result).toEqual(coords);
    });

    it('works with different grid sizes', () => {
      const coords = { x: 107, y: 213, width: 86, height: 29 };
      const gridSize = 25;

      const result = snapToGrid(coords, gridSize);

      expect(result).toEqual({
        x: 100,
        y: 200,
        width: 100,
        height: 25,
      });
    });

    it('handles fractional grid sizes', () => {
      const coords = { x: 10.3, y: 20.7, width: 8.1, height: 2.4 };
      const gridSize = 2.5;

      const result = snapToGrid(coords, gridSize);

      expect(result).toEqual({
        x: 10,
        y: 20,
        width: 7.5,
        height: 2.5,
      });
    });
  });

  describe('expandRectangle', () => {
    it('expands rectangle by margin correctly', () => {
      const rectangle = { x: 100, y: 200, width: 80, height: 20 };
      const margin = 5;

      const result = expandRectangle(rectangle, margin);

      expect(result).toEqual({
        x: 95,
        y: 195,
        width: 90,
        height: 30,
      });
    });

    it('handles zero margin', () => {
      const rectangle = { x: 100, y: 200, width: 80, height: 20 };
      const margin = 0;

      const result = expandRectangle(rectangle, margin);

      expect(result).toEqual(rectangle);
    });

    it('handles negative margin (shrinking)', () => {
      const rectangle = { x: 100, y: 200, width: 80, height: 20 };
      const margin = -5;

      const result = expandRectangle(rectangle, margin);

      expect(result).toEqual({
        x: 105,
        y: 205,
        width: 70,
        height: 10,
      });
    });

    it('works with fractional margins', () => {
      const rectangle = { x: 100, y: 200, width: 80, height: 20 };
      const margin = 2.5;

      const result = expandRectangle(rectangle, margin);

      expect(result).toEqual({
        x: 97.5,
        y: 197.5,
        width: 85,
        height: 25,
      });
    });
  });

  describe('edge cases and integration', () => {
    it('handles very small rectangles', () => {
      const coords = { x: 0.1, y: 0.1, width: 0.1, height: 0.1 };

      const area = calculateRectangleArea(coords);
      const expanded = expandRectangle(coords, 1);
      const scaled = scaleCoordinates(coords, 1, 10);

      expect(area).toBe(0.01);
      expect(expanded.width).toBe(2.1);
      expect(scaled.width).toBe(1);
    });

    it('handles very large rectangles', () => {
      const coords = { x: 0, y: 0, width: 10000, height: 10000 };

      const area = calculateRectangleArea(coords);
      const scaled = scaleCoordinates(coords, 1, 0.1);

      expect(area).toBe(100000000);
      expect(scaled.width).toBe(1000);
    });

    it('handles coordinate system round-trip with complex transformations', () => {
      const originalPdf = { x: 123.456, y: 789.012, width: 87.654, height: 21.098 };
      const pageWidth = 800;
      const pageHeight = 1200;
      const scale = 1.73;
      const rotation = 0;

      const viewport = pdfToViewport(originalPdf, pageWidth, pageHeight, scale, rotation);
      const backToPdf = viewportToPdf(viewport, pageWidth, pageHeight, scale, rotation);

      // Allow for small floating point differences
      expect(backToPdf.x).toBeCloseTo(originalPdf.x, 10);
      expect(backToPdf.y).toBeCloseTo(originalPdf.y, 10);
      expect(backToPdf.width).toBeCloseTo(originalPdf.width, 10);
      expect(backToPdf.height).toBeCloseTo(originalPdf.height, 10);
    });

    it('handles coordinate validation edge cases', () => {
      const pageWidth = 800;
      const pageHeight = 1000;

      // Rectangle exactly at boundaries
      expect(validateCoordinates({ x: 0, y: 0, width: 800, height: 1000 }, pageWidth, pageHeight)).toBe(true);
      
      // Rectangle one pixel too wide
      expect(validateCoordinates({ x: 0, y: 0, width: 801, height: 1000 }, pageWidth, pageHeight)).toBe(false);
      
      // Rectangle with floating point precision issues
      expect(validateCoordinates({ x: 0, y: 0, width: 799.9999, height: 999.9999 }, pageWidth, pageHeight)).toBe(true);
    });
  });
});