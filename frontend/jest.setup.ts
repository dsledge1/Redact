import '@testing-library/jest-dom';
import { TextEncoder, TextDecoder } from 'util';

// Add missing globals for Node.js environment
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder as any;

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
} as any;

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  constructor(callback: ResizeObserverCallback) {}
  disconnect() {}
  observe() {}
  unobserve() {}
} as any;

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

// Mock window.URL.createObjectURL and revokeObjectURL
global.URL.createObjectURL = jest.fn(() => 'mock-object-url');
global.URL.revokeObjectURL = jest.fn();

// Mock canvas context for PDF rendering
const mockCanvasContext = {
  fillRect: jest.fn(),
  clearRect: jest.fn(),
  getImageData: jest.fn(() => ({ data: new Uint8ClampedArray() })),
  putImageData: jest.fn(),
  createImageData: jest.fn(() => ({ data: new Uint8ClampedArray() })),
  setTransform: jest.fn(),
  drawImage: jest.fn(),
  save: jest.fn(),
  restore: jest.fn(),
  beginPath: jest.fn(),
  moveTo: jest.fn(),
  lineTo: jest.fn(),
  closePath: jest.fn(),
  stroke: jest.fn(),
  fill: jest.fn(),
  measureText: jest.fn(() => ({ width: 10 })),
  transform: jest.fn(),
  translate: jest.fn(),
  scale: jest.fn(),
  rotate: jest.fn(),
  arc: jest.fn(),
  fillText: jest.fn(),
  strokeText: jest.fn(),
};

HTMLCanvasElement.prototype.getContext = jest.fn(() => mockCanvasContext) as any;

// Mock PDF.js worker
jest.mock('pdfjs-dist/build/pdf.worker.entry', () => 'mock-pdf-worker');

// Mock react-pdf with comprehensive functionality
jest.mock('react-pdf', () => ({
  Document: ({ children, onLoadSuccess, onLoadError, file, options }: any) => {
    // Simulate successful PDF loading
    setTimeout(() => {
      if (onLoadSuccess) {
        onLoadSuccess({ 
          numPages: 3,
          fingerprint: 'mock-fingerprint',
          getMetadata: () => Promise.resolve({
            info: { Title: 'Mock PDF', Author: 'Test Author' },
            metadata: new Map()
          })
        });
      }
    }, 10);
    
    return (
      <div data-testid="mock-pdf-document" data-file={file}>
        {children}
      </div>
    );
  },
  Page: ({ pageNumber, onLoadSuccess, onRenderSuccess, canvasRef, children }: any) => {
    // Simulate page loading
    setTimeout(() => {
      if (onLoadSuccess) {
        onLoadSuccess({
          pageNumber,
          width: 595,
          height: 842,
          originalWidth: 595,
          originalHeight: 842
        });
      }
      if (onRenderSuccess) {
        onRenderSuccess();
      }
    }, 5);

    return (
      <div data-testid="mock-pdf-page" data-page-number={pageNumber}>
        <canvas ref={canvasRef} width={595} height={842} />
        {children}
      </div>
    );
  },
  Outline: ({ children }: any) => (
    <div data-testid="mock-pdf-outline">{children}</div>
  ),
  pdfjs: {
    GlobalWorkerOptions: {
      workerSrc: 'mock-worker-src'
    },
    version: '3.0.279'
  },
}));

// Mock react-dropzone with advanced functionality
jest.mock('react-dropzone', () => ({
  useDropzone: (options: any = {}) => ({
    getRootProps: () => ({
      role: 'button',
      'aria-label': 'File upload area',
      tabIndex: 0,
    }),
    getInputProps: () => ({
      type: 'file',
      multiple: options.multiple || false,
      accept: options.accept || undefined,
    }),
    isDragActive: false,
    isDragReject: false,
    isDragAccept: false,
    acceptedFiles: [],
    rejectedFiles: [],
    fileRejections: [],
    isFocused: false,
    open: jest.fn(),
  }),
}));

// Mock File and FileReader APIs
global.File = class File {
  constructor(public chunks: any[], public name: string, public options: any = {}) {
    this.size = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
    this.type = options.type || '';
    this.lastModified = options.lastModified || Date.now();
  }
  size: number;
  type: string;
  lastModified: number;
  
  arrayBuffer(): Promise<ArrayBuffer> {
    return Promise.resolve(new ArrayBuffer(this.size));
  }
  
  text(): Promise<string> {
    return Promise.resolve(this.chunks.join(''));
  }
  
  slice(start?: number, end?: number): Blob {
    return new Blob(this.chunks.slice(start, end));
  }
} as any;

global.FileReader = class FileReader extends EventTarget {
  result: string | ArrayBuffer | null = null;
  error: any = null;
  readyState: number = 0;
  
  readAsDataURL(file: Blob): void {
    setTimeout(() => {
      this.result = `data:${(file as any).type};base64,mock-data`;
      this.readyState = 2;
      this.dispatchEvent(new Event('load'));
    }, 10);
  }
  
  readAsText(file: Blob): void {
    setTimeout(() => {
      this.result = 'mock file content';
      this.readyState = 2;
      this.dispatchEvent(new Event('load'));
    }, 10);
  }
  
  readAsArrayBuffer(file: Blob): void {
    setTimeout(() => {
      this.result = new ArrayBuffer(1024);
      this.readyState = 2;
      this.dispatchEvent(new Event('load'));
    }, 10);
  }
  
  abort(): void {
    this.readyState = 2;
    this.dispatchEvent(new Event('abort'));
  }
} as any;

// Mock FormData
global.FormData = class FormData {
  private data = new Map();
  
  append(name: string, value: string | Blob, filename?: string): void {
    this.data.set(name, { value, filename });
  }
  
  get(name: string): string | File | null {
    return this.data.get(name)?.value || null;
  }
  
  has(name: string): boolean {
    return this.data.has(name);
  }
  
  delete(name: string): void {
    this.data.delete(name);
  }
  
  entries(): IterableIterator<[string, string | File]> {
    return this.data.entries();
  }
} as any;

// Mock localStorage and sessionStorage
const createStorage = () => ({
  data: {} as Record<string, string>,
  getItem(key: string): string | null {
    return this.data[key] || null;
  },
  setItem(key: string, value: string): void {
    this.data[key] = String(value);
  },
  removeItem(key: string): void {
    delete this.data[key];
  },
  clear(): void {
    this.data = {};
  },
  get length(): number {
    return Object.keys(this.data).length;
  },
  key(index: number): string | null {
    const keys = Object.keys(this.data);
    return keys[index] || null;
  }
});

Object.defineProperty(window, 'localStorage', {
  value: createStorage(),
  writable: true
});

Object.defineProperty(window, 'sessionStorage', {
  value: createStorage(),
  writable: true
});

// Mock fetch API
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Map(),
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(''),
    blob: () => Promise.resolve(new Blob()),
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)),
  })
) as jest.Mock;

// Mock axios (if used)
jest.mock('axios', () => ({
  create: jest.fn(() => ({
    get: jest.fn(() => Promise.resolve({ data: {} })),
    post: jest.fn(() => Promise.resolve({ data: {} })),
    put: jest.fn(() => Promise.resolve({ data: {} })),
    delete: jest.fn(() => Promise.resolve({ data: {} })),
    patch: jest.fn(() => Promise.resolve({ data: {} })),
  })),
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
  patch: jest.fn(() => Promise.resolve({ data: {} })),
}));

// Mock Next.js router
jest.mock('next/router', () => ({
  useRouter() {
    return {
      route: '/',
      pathname: '/',
      query: {},
      asPath: '/',
      push: jest.fn(),
      pop: jest.fn(),
      reload: jest.fn(),
      back: jest.fn(),
      prefetch: jest.fn().mockResolvedValue(undefined),
      beforePopState: jest.fn(),
      events: {
        on: jest.fn(),
        off: jest.fn(),
        emit: jest.fn(),
      },
      isFallback: false,
      isLocaleDomain: false,
      isReady: true,
      isPreview: false,
    };
  },
}));

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
      forward: jest.fn(),
      refresh: jest.fn(),
    };
  },
  usePathname: jest.fn(() => '/'),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

// Mock console methods to reduce noise in tests
const originalConsoleError = console.error;
const originalConsoleWarn = console.warn;

console.error = (...args) => {
  if (
    typeof args[0] === 'string' &&
    (args[0].includes('Warning: ReactDOM.render is no longer supported') ||
     args[0].includes('Warning: React.createFactory() is deprecated'))
  ) {
    return;
  }
  originalConsoleError.call(console, ...args);
};

console.warn = (...args) => {
  if (
    typeof args[0] === 'string' &&
    args[0].includes('componentWillReceiveProps has been renamed')
  ) {
    return;
  }
  originalConsoleWarn.call(console, ...args);
};

// Mock performance API
Object.defineProperty(window, 'performance', {
  value: {
    now: jest.fn(() => Date.now()),
    mark: jest.fn(),
    measure: jest.fn(),
    getEntriesByType: jest.fn(() => []),
    getEntriesByName: jest.fn(() => []),
  },
  writable: true
});

// Custom test utilities
export const createMockFile = (name = 'test.pdf', size = 1024, type = 'application/pdf') => {
  const file = new File(['mock content'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
};

export const createMockFileList = (files: File[]) => {
  const fileList = {
    length: files.length,
    item: (index: number) => files[index] || null,
    [Symbol.iterator]: function* () {
      for (const file of files) {
        yield file;
      }
    },
  };
  
  files.forEach((file, index) => {
    (fileList as any)[index] = file;
  });
  
  return fileList as FileList;
};

// Setup for each test
beforeEach(() => {
  // Clear all mocks
  jest.clearAllMocks();
  
  // Reset storage
  window.localStorage.clear();
  window.sessionStorage.clear();
  
  // Reset fetch mock
  (global.fetch as jest.Mock).mockClear();
});

// Cleanup after each test
afterEach(() => {
  // Clean up timers only if fake timers are active
});