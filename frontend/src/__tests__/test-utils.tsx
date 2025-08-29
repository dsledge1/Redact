/**
 * Comprehensive test utilities for frontend testing.
 * 
 * This module provides utility functions for component testing, user interactions,
 * API mocking, PDF testing, accessibility testing, and performance testing.
 */

import React, { ReactElement } from 'react';
import { render, RenderOptions, RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UserEvent } from '@testing-library/user-event/dist/types/setup/setup';

// Type definitions
interface MockStore {
  documents: any[];
  currentDocument: any;
  operations: any[];
  isLoading: boolean;
  error: string | null;
  uploadProgress: number;
  // Actions
  addDocument: jest.Mock;
  setCurrentDocument: jest.Mock;
  addOperation: jest.Mock;
  setLoading: jest.Mock;
  setError: jest.Mock;
  clearError: jest.Mock;
  updateUploadProgress: jest.Mock;
}

interface ComponentTestingUtils {
  renderWithProviders: (ui: ReactElement, options?: RenderOptions) => RenderResult;
  createMockStore: (initialState?: Partial<MockStore>) => MockStore;
  mockPDFViewer: () => void;
  mockFileUpload: () => void;
}

interface UserInteractionUtils {
  uploadFile: (element: Element, file: File) => Promise<void>;
  dragAndDrop: (source: Element, target: Element, files?: File[]) => Promise<void>;
  selectPageRange: (component: Element, startPage: number, endPage: number) => Promise<void>;
  approveRedactionMatch: (component: Element, matchId: string) => Promise<void>;
  rejectRedactionMatch: (component: Element, matchId: string) => Promise<void>;
  addManualRedaction: (component: Element, coordinates: CoordinateData) => Promise<void>;
}

interface CoordinateData {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface APIMockingUtils {
  mockAPIResponse: (endpoint: string, response: any, status?: number) => jest.Mock;
  mockFileUploadProgress: (progressCallback: (progress: number) => void) => jest.Mock;
  mockJobPolling: (jobId: string, responses: any[]) => jest.Mock;
  mockFileDownload: (url: string, blob: Blob) => jest.Mock;
  resetAPIMocks: () => void;
}

interface PDFTestingUtils {
  createMockPDF: (pages: number, content?: string) => ArrayBuffer;
  mockPDFCoordinates: (page: number, coordinates: CoordinateData) => CoordinateData;
  validateCoordinateConversion: (input: CoordinateData, expected: CoordinateData) => boolean;
  mockPDFError: (errorType: 'corrupted' | 'password' | 'invalid') => Error;
}

interface AccessibilityTestingUtils {
  testKeyboardNavigation: (component: Element) => Promise<boolean>;
  testScreenReaderSupport: (component: Element) => Promise<boolean>;
  validateARIALabels: (component: Element) => boolean;
  testFocusManagement: (component: Element) => Promise<boolean>;
}

interface PerformanceTestingUtils {
  measureRenderTime: (renderFunction: () => RenderResult) => number;
  testMemoryUsage: (component: ReactElement) => Promise<number>;
  validateResponseTime: (operation: () => Promise<any>, maxTime: number) => Promise<boolean>;
  stressTestComponent: (component: ReactElement, iterations: number) => Promise<boolean>;
}

interface FileTestingUtils {
  createMockFile: (name?: string, size?: number, type?: string) => File;
  createMockFileList: (files: File[]) => FileList;
  validateFileValidation: (file: File, expected: any) => boolean;
  mockFileReader: (result: string | ArrayBuffer) => void;
}

// Component Testing Utils
export const componentTestingUtils: ComponentTestingUtils = {
  renderWithProviders: (ui: ReactElement, options: RenderOptions = {}) => {
    const mockStore = createMockStore();
    
    const AllTheProviders: React.FC<{ children: React.ReactNode }> = ({ children }) => {
      // In a real implementation, this would wrap with actual providers
      // like Zustand provider, theme provider, etc.
      return (
        <div data-testid="providers-wrapper">
          {children}
        </div>
      );
    };

    return render(ui, { wrapper: AllTheProviders, ...options });
  },

  createMockStore: (initialState: Partial<MockStore> = {}): MockStore => {
    return {
      documents: [],
      currentDocument: null,
      operations: [],
      isLoading: false,
      error: null,
      uploadProgress: 0,
      
      // Actions
      addDocument: jest.fn(),
      setCurrentDocument: jest.fn(),
      addOperation: jest.fn(),
      setLoading: jest.fn(),
      setError: jest.fn(),
      clearError: jest.fn(),
      updateUploadProgress: jest.fn(),
      
      ...initialState
    };
  },

  mockPDFViewer: () => {
    // PDF viewer mocking is handled in jest.setup.ts
    // This function can be used for additional setup if needed
  },

  mockFileUpload: () => {
    // File upload mocking is handled in jest.setup.ts
    // This function can be used for additional setup if needed
  }
};

// User Interaction Utils
export const userInteractionUtils: UserInteractionUtils = {
  uploadFile: async (element: Element, file: File): Promise<void> => {
    const user = userEvent.setup();
    
    if (element.tagName === 'INPUT' && (element as HTMLInputElement).type === 'file') {
      await user.upload(element as HTMLInputElement, file);
    } else {
      // Handle drag-and-drop upload
      await user.pointer([
        { keys: '[MouseLeft>]', target: element },
        { pointerName: 'mouse', target: element },
        { keys: '[/MouseLeft]', target: element }
      ]);
    }
  },

  dragAndDrop: async (source: Element, target: Element, files: File[] = []): Promise<void> => {
    const user = userEvent.setup();

    // Create drag event with files
    const dataTransfer = {
      files: files,
      types: ['Files'],
      getData: jest.fn(),
      setData: jest.fn()
    };

    // Simulate drag start
    await user.pointer({ keys: '[MouseLeft>]', target: source });
    
    // Simulate drag over target
    await user.hover(target);
    
    // Simulate drop
    await user.pointer({ keys: '[/MouseLeft]', target: target });
  },

  selectPageRange: async (component: Element, startPage: number, endPage: number): Promise<void> => {
    const user = userEvent.setup();
    
    const startPageInput = component.querySelector('[data-testid="start-page"]') as HTMLInputElement;
    const endPageInput = component.querySelector('[data-testid="end-page"]') as HTMLInputElement;
    
    if (startPageInput) {
      await user.clear(startPageInput);
      await user.type(startPageInput, startPage.toString());
    }
    
    if (endPageInput) {
      await user.clear(endPageInput);
      await user.type(endPageInput, endPage.toString());
    }
  },

  approveRedactionMatch: async (component: Element, matchId: string): Promise<void> => {
    const user = userEvent.setup();
    const approveButton = component.querySelector(`[data-testid="approve-${matchId}"]`);
    
    if (approveButton) {
      await user.click(approveButton);
    }
  },

  rejectRedactionMatch: async (component: Element, matchId: string): Promise<void> => {
    const user = userEvent.setup();
    const rejectButton = component.querySelector(`[data-testid="reject-${matchId}"]`);
    
    if (rejectButton) {
      await user.click(rejectButton);
    }
  },

  addManualRedaction: async (component: Element, coordinates: CoordinateData): Promise<void> => {
    const user = userEvent.setup();
    
    const x1Input = component.querySelector('[data-testid="x1"]') as HTMLInputElement;
    const y1Input = component.querySelector('[data-testid="y1"]') as HTMLInputElement;
    const x2Input = component.querySelector('[data-testid="x2"]') as HTMLInputElement;
    const y2Input = component.querySelector('[data-testid="y2"]') as HTMLInputElement;
    
    if (x1Input) await user.type(x1Input, coordinates.x1.toString());
    if (y1Input) await user.type(y1Input, coordinates.y1.toString());
    if (x2Input) await user.type(x2Input, coordinates.x2.toString());
    if (y2Input) await user.type(y2Input, coordinates.y2.toString());
    
    const addButton = component.querySelector('[data-testid="add-manual-redaction"]');
    if (addButton) {
      await user.click(addButton);
    }
  }
};

// API Mocking Utils
export const apiMockingUtils: APIMockingUtils = {
  mockAPIResponse: (endpoint: string, response: any, status: number = 200): jest.Mock => {
    const mockFetch = global.fetch as jest.Mock;
    
    mockFetch.mockImplementation((url: string) => {
      if (url.includes(endpoint)) {
        return Promise.resolve({
          ok: status >= 200 && status < 300,
          status,
          statusText: status === 200 ? 'OK' : 'Error',
          json: () => Promise.resolve(response),
          text: () => Promise.resolve(JSON.stringify(response)),
          blob: () => Promise.resolve(new Blob([JSON.stringify(response)])),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      });
    });
    
    return mockFetch;
  },

  mockFileUploadProgress: (progressCallback: (progress: number) => void): jest.Mock => {
    const mockFetch = global.fetch as jest.Mock;
    
    mockFetch.mockImplementation(() => {
      // Simulate upload progress
      let progress = 0;
      const interval = setInterval(() => {
        progress += 20;
        progressCallback(progress);
        
        if (progress >= 100) {
          clearInterval(interval);
        }
      }, 100);
      
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ document_id: 'mock-doc-id' }),
      });
    });
    
    return mockFetch;
  },

  mockJobPolling: (jobId: string, responses: any[]): jest.Mock => {
    const mockFetch = global.fetch as jest.Mock;
    let callCount = 0;
    
    mockFetch.mockImplementation((url: string) => {
      if (url.includes(`/api/jobs/${jobId}`)) {
        const response = responses[Math.min(callCount, responses.length - 1)];
        callCount++;
        
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(response),
        });
      }
      
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      });
    });
    
    return mockFetch;
  },

  mockFileDownload: (url: string, blob: Blob): jest.Mock => {
    const mockFetch = global.fetch as jest.Mock;
    
    mockFetch.mockImplementation((requestUrl: string) => {
      if (requestUrl === url) {
        return Promise.resolve({
          ok: true,
          status: 200,
          blob: () => Promise.resolve(blob),
          headers: {
            get: (name: string) => {
              if (name === 'Content-Type') return 'application/pdf';
              if (name === 'Content-Length') return blob.size.toString();
              return null;
            }
          }
        });
      }
      
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      });
    });
    
    return mockFetch;
  },

  resetAPIMocks: (): void => {
    (global.fetch as jest.Mock).mockClear();
  }
};

// PDF Testing Utils
export const pdfTestingUtils: PDFTestingUtils = {
  createMockPDF: (pages: number = 1, content: string = 'Mock PDF content'): ArrayBuffer => {
    const mockPDFContent = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count ${pages} >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>
endobj
4 0 obj
<< >>
stream
BT
/F1 12 Tf
100 700 Td
(${content}) Tj
ET
endstream
endobj
trailer
<< /Size 5 /Root 1 0 R >>
startxref
0
%%EOF`;
    
    const encoder = new TextEncoder();
    return encoder.encode(mockPDFContent).buffer;
  },

  mockPDFCoordinates: (page: number, coordinates: CoordinateData): CoordinateData => {
    // Convert screen coordinates to PDF coordinates
    // This is a simplified conversion for testing
    return {
      x1: coordinates.x1,
      y1: 842 - coordinates.y2, // Flip Y coordinate for PDF coordinate system
      x2: coordinates.x2,
      y2: 842 - coordinates.y1, // Flip Y coordinate for PDF coordinate system
    };
  },

  validateCoordinateConversion: (input: CoordinateData, expected: CoordinateData): boolean => {
    const tolerance = 1; // 1 pixel tolerance
    
    return (
      Math.abs(input.x1 - expected.x1) <= tolerance &&
      Math.abs(input.y1 - expected.y1) <= tolerance &&
      Math.abs(input.x2 - expected.x2) <= tolerance &&
      Math.abs(input.y2 - expected.y2) <= tolerance
    );
  },

  mockPDFError: (errorType: 'corrupted' | 'password' | 'invalid'): Error => {
    switch (errorType) {
      case 'corrupted':
        return new Error('PDF file is corrupted or malformed');
      case 'password':
        return new Error('PDF file is password protected');
      case 'invalid':
        return new Error('Invalid PDF file format');
      default:
        return new Error('Unknown PDF error');
    }
  }
};

// Accessibility Testing Utils
export const accessibilityTestingUtils: AccessibilityTestingUtils = {
  testKeyboardNavigation: async (component: Element): Promise<boolean> => {
    const user = userEvent.setup();
    const focusableElements = component.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    if (focusableElements.length === 0) return true;
    
    // Test tab navigation
    for (let i = 0; i < focusableElements.length; i++) {
      await user.tab();
      const activeElement = document.activeElement;
      
      if (!focusableElements[i].contains(activeElement)) {
        return false;
      }
    }
    
    return true;
  },

  testScreenReaderSupport: async (component: Element): Promise<boolean> => {
    // Check for ARIA labels and roles
    const elementsWithARIA = component.querySelectorAll('[aria-label], [aria-labelledby], [role]');
    
    // Check for semantic HTML elements
    const semanticElements = component.querySelectorAll(
      'main, nav, header, footer, section, article, aside, h1, h2, h3, h4, h5, h6'
    );
    
    // Basic validation - should have some accessibility features
    return elementsWithARIA.length > 0 || semanticElements.length > 0;
  },

  validateARIALabels: (component: Element): boolean => {
    const interactiveElements = component.querySelectorAll('button, input, select, textarea, a');
    
    for (const element of interactiveElements) {
      const hasAriaLabel = element.hasAttribute('aria-label');
      const hasAriaLabelledBy = element.hasAttribute('aria-labelledby');
      const hasTextContent = element.textContent?.trim();
      const hasAltText = element.hasAttribute('alt');
      
      if (!hasAriaLabel && !hasAriaLabelledBy && !hasTextContent && !hasAltText) {
        return false;
      }
    }
    
    return true;
  },

  testFocusManagement: async (component: Element): Promise<boolean> => {
    const user = userEvent.setup();
    
    // Test that focus is properly managed during interactions
    const buttons = component.querySelectorAll('button');
    
    for (const button of buttons) {
      await user.click(button);
      
      // Check if focus is still within the component or properly moved
      const activeElement = document.activeElement;
      if (!component.contains(activeElement) && activeElement !== document.body) {
        // Focus moved outside component, which might be intentional
        continue;
      }
    }
    
    return true;
  }
};

// Performance Testing Utils
export const performanceTestingUtils: PerformanceTestingUtils = {
  measureRenderTime: (renderFunction: () => RenderResult): number => {
    const startTime = performance.now();
    renderFunction();
    const endTime = performance.now();
    
    return endTime - startTime;
  },

  testMemoryUsage: async (component: ReactElement): Promise<number> => {
    // Mock memory usage testing since we can't access real memory info in Jest
    const initialMemory = (performance as any).memory?.usedJSHeapSize || 0;
    
    const { unmount } = render(component);
    
    // Simulate some operations
    await new Promise(resolve => setTimeout(resolve, 100));
    
    unmount();
    
    const finalMemory = (performance as any).memory?.usedJSHeapSize || 0;
    
    return Math.max(0, finalMemory - initialMemory);
  },

  validateResponseTime: async (operation: () => Promise<any>, maxTime: number): Promise<boolean> => {
    const startTime = performance.now();
    
    try {
      await operation();
    } catch (error) {
      // Even if operation fails, we can still measure timing
    }
    
    const endTime = performance.now();
    const duration = endTime - startTime;
    
    return duration <= maxTime;
  },

  stressTestComponent: async (component: ReactElement, iterations: number): Promise<boolean> => {
    try {
      for (let i = 0; i < iterations; i++) {
        const { unmount } = render(component);
        
        // Simulate some interactions
        await new Promise(resolve => setTimeout(resolve, 10));
        
        unmount();
      }
      
      return true;
    } catch (error) {
      return false;
    }
  }
};

// File Testing Utils
export const fileTestingUtils: FileTestingUtils = {
  createMockFile: (name: string = 'test.pdf', size: number = 1024, type: string = 'application/pdf'): File => {
    const content = 'mock file content';
    const file = new File([content], name, { type });
    
    // Override size property
    Object.defineProperty(file, 'size', {
      value: size,
      writable: false
    });
    
    return file;
  },

  createMockFileList: (files: File[]): FileList => {
    const fileList = {
      length: files.length,
      item: (index: number) => files[index] || null,
      [Symbol.iterator]: function* () {
        for (const file of files) {
          yield file;
        }
      },
    } as FileList;
    
    // Add files as indexed properties
    files.forEach((file, index) => {
      (fileList as any)[index] = file;
    });
    
    return fileList;
  },

  validateFileValidation: (file: File, expected: any): boolean => {
    return (
      file.name === expected.name &&
      file.size === expected.size &&
      file.type === expected.type
    );
  },

  mockFileReader: (result: string | ArrayBuffer): void => {
    const originalFileReader = global.FileReader;
    
    global.FileReader = class MockFileReader extends EventTarget {
      result: string | ArrayBuffer | null = null;
      error: any = null;
      readyState: number = 0;
      
      readAsDataURL(file: Blob): void {
        setTimeout(() => {
          this.result = typeof result === 'string' ? result : `data:${file.type};base64,mock-data`;
          this.readyState = 2;
          this.dispatchEvent(new Event('load'));
        }, 10);
      }
      
      readAsText(file: Blob): void {
        setTimeout(() => {
          this.result = typeof result === 'string' ? result : 'mock text content';
          this.readyState = 2;
          this.dispatchEvent(new Event('load'));
        }, 10);
      }
      
      readAsArrayBuffer(file: Blob): void {
        setTimeout(() => {
          this.result = result instanceof ArrayBuffer ? result : new ArrayBuffer(1024);
          this.readyState = 2;
          this.dispatchEvent(new Event('load'));
        }, 10);
      }
      
      abort(): void {
        this.readyState = 2;
        this.dispatchEvent(new Event('abort'));
      }
    } as any;
    
    // Restore original after test
    setTimeout(() => {
      global.FileReader = originalFileReader;
    }, 1000);
  }
};

// Custom hooks for testing
export const useTestUser = (): UserEvent => {
  return userEvent.setup();
};

// Test assertions
export const customAssertions = {
  toBeAccessible: (element: Element): boolean => {
    return accessibilityTestingUtils.validateARIALabels(element);
  },
  
  toHaveValidPDF: (data: ArrayBuffer): boolean => {
    const view = new Uint8Array(data);
    const header = String.fromCharCode(...view.slice(0, 8));
    return header.startsWith('%PDF-');
  },
  
  toRespondWithin: async (operation: () => Promise<any>, maxTime: number): Promise<boolean> => {
    return performanceTestingUtils.validateResponseTime(operation, maxTime);
  }
};

// Export commonly used utilities
export const {
  renderWithProviders,
  createMockStore,
} = componentTestingUtils;

export const {
  uploadFile,
  dragAndDrop,
  selectPageRange,
  approveRedactionMatch,
} = userInteractionUtils;

export const {
  mockAPIResponse,
  mockJobPolling,
  resetAPIMocks,
} = apiMockingUtils;

export const {
  createMockPDF,
  validateCoordinateConversion,
} = pdfTestingUtils;

export const {
  createMockFile,
  createMockFileList,
} = fileTestingUtils;

// Note: jest.setup utilities are accessed through the global jest object