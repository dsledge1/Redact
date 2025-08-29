const nextJest = require('next/jest');

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files
  dir: './',
});

// Add any custom config to be passed to Jest
/** @type {import('jest').Config} */
const customJestConfig = {
  // Add more setup options before each test is run
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],

  // Setup files (removed non-existent jest.polyfills.ts)

  // Test environment
  testEnvironment: 'jsdom',

  // Module name mapping for absolute imports and CSS modules
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
    // React PDF and worker mocks handled in jest.setup.ts
    // Canvas and image mocks
    '\\.(jpg|jpeg|png|gif|svg)$': '<rootDir>/src/__tests__/__mocks__/fileMock.ts',
    // Audio/video file mocks
    '\\.(mp4|webm|wav|mp3|m4a|aac|oga)$': '<rootDir>/src/__tests__/__mocks__/fileMock.ts',
  },

  // Collect coverage from
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
    '!src/app/layout.tsx',
    '!src/app/page.tsx',
    '!src/**/__tests__/**',
    '!src/**/__mocks__/**',
    '!src/**/*.stories.{js,jsx,ts,tsx}',
  ],

  // Coverage thresholds - enforcing >= 80% as per project requirements
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },

  // Test patterns
  testMatch: [
    '<rootDir>/src/**/__tests__/**/*.[jt]s?(x)',
    '<rootDir>/src/**/?(*.)+(spec|test).[tj]s?(x)'
  ],

  // Transform ignore patterns
  transformIgnorePatterns: [
    '/node_modules/(?!(@pdf-lib|pdfjs-dist|react-pdf)/)',
    '^.+\\.module\\.(css|sass|scss)$',
  ],

  // Module file extensions
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],

  // Test timeout - increased for PDF processing tests
  testTimeout: 15000,

  // Mock specific modules
  modulePathIgnorePatterns: ['<rootDir>/.next/', '<rootDir>/dist/'],

  // Globals for PDF.js and Canvas testing
  testEnvironmentOptions: {
    customExportConditions: ['node', 'node-addons'],
  },

  // Test reporters
  reporters: ['default'],

  // Coverage reporters
  coverageReporters: ['text', 'lcov', 'html', 'json', 'clover'],

  // Coverage directory
  coverageDirectory: '<rootDir>/coverage',

  // Clear mocks between tests
  clearMocks: true,

  // Restore mocks after each test
  restoreMocks: true,

  // Reset modules before each test
  resetModules: false,

  // Verbose output for debugging
  verbose: false,

  // Detect open handles
  detectOpenHandles: true,

  // Force exit after tests complete
  forceExit: false,

  // Max workers for parallel testing
  maxWorkers: '50%',

  // Cache directory
  cacheDirectory: '<rootDir>/.jest-cache',

  // Error on deprecated features
  errorOnDeprecated: true,

  // Notify on test completion
  notify: false,

  // Test results processor
  testResultsProcessor: undefined,

  // Watch plugins
  watchPlugins: [],

  // Extension to look for
  testPathIgnorePatterns: [
    '<rootDir>/.next/',
    '<rootDir>/node_modules/',
    '<rootDir>/dist/',
    '<rootDir>/out/',
  ],
};

// Create and export the Jest config
module.exports = createJestConfig(customJestConfig);