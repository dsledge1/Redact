// Polyfills for testing environment

// Mock crypto.subtle if not available
if (typeof global.crypto === 'undefined') {
  global.crypto = {
    subtle: {
      digest: jest.fn(),
    } as any,
  } as any;
}

// Mock URL.createObjectURL
if (typeof URL.createObjectURL === 'undefined') {
  URL.createObjectURL = jest.fn((blob: Blob) => {
    return `blob:${Math.random().toString(36).substr(2, 9)}`;
  });
}

// Mock URL.revokeObjectURL
if (typeof URL.revokeObjectURL === 'undefined') {
  URL.revokeObjectURL = jest.fn();
}