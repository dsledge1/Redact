'use client';

import { useState, useEffect } from 'react';
import { useUI, useUIActions, useRedaction, useDocument } from '@/store/pdfStore';
import FileUpload from '@/components/FileUpload';
import PDFViewer from '@/components/PDFViewer';
import RedactionToolbar from '@/components/RedactionToolbar';
import MatchReviewSidebar from '@/components/MatchReviewSidebar';
import { SplitInterface } from '@/components/SplitInterface';
import { MergeInterface } from '@/components/MergeInterface';
import { ExtractionInterface } from '@/components/ExtractionInterface';

export default function HomePage(): JSX.Element {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [activeOperation, setActiveOperation] = useState<'split' | 'merge' | 'extract' | 'redact' | null>(null);
  const { currentView } = useUI();
  const { setCurrentView, setCurrentOperation } = useUIActions();
  const { matches, manualRedactions } = useRedaction();
  const document = useDocument();

  // Show different layouts based on current view
  const isOperationView = ['redaction', 'splitting', 'merging', 'extraction'].includes(currentView);
  const isRedactionView = currentView === 'redaction';
  const hasRedactionData = matches.length > 0 || manualRedactions.length > 0;

  const handleOperationSelect = (operation: 'split' | 'merge' | 'extract' | 'redact') => {
    if (!uploadedFile) {
      // Scroll to upload section if no file is uploaded
      const uploadSection = document.getElementById('upload-section');
      uploadSection?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    
    setActiveOperation(operation);
    setCurrentOperation(operation === 'redact' ? 'redaction' : operation === 'split' ? 'splitting' : operation === 'merge' ? 'merging' : 'extraction');
    
    const viewMap = {
      'split': 'splitting',
      'merge': 'merging', 
      'extract': 'extraction',
      'redact': 'redaction'
    } as const;
    
    setCurrentView(viewMap[operation]);
  };

  return (
    <div className={isOperationView ? "h-screen flex flex-col" : "container mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8"}>
      {isOperationView ? (
        // Operation Interface Layout
        <>
          {/* Operation Header */}
          <div className="bg-white border-b border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <button
                  onClick={() => {
                    setActiveOperation(null);
                    setCurrentOperation(null);
                    setCurrentView('viewer');
                  }}
                  className="text-gray-500 hover:text-gray-700"
                >
                  ← Back to Document
                </button>
                <div className="h-6 w-px bg-gray-300"></div>
                <h1 className="text-lg font-semibold capitalize">
                  {activeOperation === 'redact' ? 'PDF Redaction' : 
                   activeOperation === 'split' ? 'PDF Splitting' :
                   activeOperation === 'merge' ? 'PDF Merging' :
                   activeOperation === 'extract' ? 'Data Extraction' : 'PDF Processing'}
                </h1>
              </div>
              <div className="text-sm text-gray-600">
                {uploadedFile?.name}
              </div>
            </div>
          </div>

          {/* Operation Content */}
          <div className="flex-1 flex overflow-hidden">
            {isRedactionView ? (
              // Redaction Interface
              <>
                <RedactionToolbar />
                <div className="flex-1 flex overflow-hidden">
                  <div className="flex-1 flex">
                    <PDFViewer documentId={document?.id} />
                  </div>
                  {hasRedactionData && <MatchReviewSidebar />}
                </div>
              </>
            ) : (
              // Other Operations Interface
              <div className="flex-1 flex overflow-hidden">
                {/* PDF Viewer */}
                <div className="flex-1 flex">
                  <PDFViewer documentId={document?.id} />
                </div>
                
                {/* Operation Panel */}
                <div className="w-96 bg-white border-l border-gray-200 overflow-y-auto">
                  <div className="p-6">
                    {currentView === 'splitting' && (
                      <SplitInterface 
                        onSplitComplete={(results) => {
                          console.log('Split completed:', results);
                        }}
                      />
                    )}
                    
                    {currentView === 'merging' && (
                      <MergeInterface 
                        onMergeComplete={(results) => {
                          console.log('Merge completed:', results);
                        }}
                      />
                    )}
                    
                    {currentView === 'extraction' && (
                      <ExtractionInterface 
                        onExtractionComplete={(results) => {
                          console.log('Extraction completed:', results);
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </>
      ) : (
        // Landing Page Layout
        <>
          {/* Hero Section */}
          <section className="text-center">
            <div className="mx-auto max-w-3xl">
              <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-6xl">
                Ultimate PDF
                <span className="block text-primary-600">Processing Tools</span>
              </h1>
              <p className="mt-6 text-lg leading-8 text-gray-600">
                Professional-grade PDF processing platform with advanced redaction, intelligent splitting,
                seamless merging, and comprehensive data extraction capabilities.
              </p>
              <div className="mt-10 flex items-center justify-center gap-x-6">
                <button
                  type="button"
                  className="rounded-lg bg-primary-600 px-6 py-3 text-sm font-semibold text-white shadow hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                  onClick={() => {
                    const uploadSection = document.getElementById('upload-section');
                    uploadSection?.scrollIntoView({ behavior: 'smooth' });
                  }}
                >
                  Start Processing
                </button>
                <a href="#features" className="text-sm font-semibold leading-6 text-gray-900">
                  Learn more <span aria-hidden="true">→</span>
                </a>
              </div>
            </div>
          </section>

      {/* Upload Section */}
      <section id="upload-section" className="mt-16">
        <div className="mx-auto max-w-2xl">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900">
              Upload Your PDF
            </h2>
            <p className="mt-4 text-lg text-gray-600">
              Drag and drop your PDF file or click to browse. Files are processed securely and automatically deleted after 8 hours.
            </p>
          </div>
          <div className="mt-8">
            <FileUpload
              onFileUploaded={(file) => {
                setUploadedFile(file);
              }}
              onError={(error) => {
                console.error('Upload error:', error);
              }}
            />
          </div>
        </div>
      </section>

          {/* PDF Viewer Section */}
          {uploadedFile && (
            <section className="mt-8">
              <div className="mx-auto max-w-7xl">
                {/* Operation Selection */}
                <div className="mb-6 text-center">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Choose an operation for your PDF:
                  </h3>
                  <div className="flex justify-center space-x-4">
                    <button
                      onClick={() => handleOperationSelect('redact')}
                      className="flex flex-col items-center p-4 border-2 border-red-200 rounded-lg hover:border-red-400 hover:bg-red-50 transition-colors"
                    >
                      <div className="w-8 h-8 bg-red-100 rounded-lg flex items-center justify-center mb-2">
                        🖍️
                      </div>
                      <span className="text-sm font-medium text-red-700">Redact</span>
                    </button>
                    
                    <button
                      onClick={() => handleOperationSelect('split')}
                      className="flex flex-col items-center p-4 border-2 border-blue-200 rounded-lg hover:border-blue-400 hover:bg-blue-50 transition-colors"
                    >
                      <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center mb-2">
                        ✂️
                      </div>
                      <span className="text-sm font-medium text-blue-700">Split</span>
                    </button>
                    
                    <button
                      onClick={() => handleOperationSelect('merge')}
                      className="flex flex-col items-center p-4 border-2 border-green-200 rounded-lg hover:border-green-400 hover:bg-green-50 transition-colors"
                    >
                      <div className="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center mb-2">
                        📋
                      </div>
                      <span className="text-sm font-medium text-green-700">Merge</span>
                    </button>
                    
                    <button
                      onClick={() => handleOperationSelect('extract')}
                      className="flex flex-col items-center p-4 border-2 border-purple-200 rounded-lg hover:border-purple-400 hover:bg-purple-50 transition-colors"
                    >
                      <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center mb-2">
                        📤
                      </div>
                      <span className="text-sm font-medium text-purple-700">Extract</span>
                    </button>
                  </div>
                </div>
                
                {/* PDF Viewer */}
                <PDFViewer documentId={document?.id} />
              </div>
            </section>
          )}

      {/* Features Section */}
      <section id="features" className="mt-24">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              Powerful PDF Processing Features
            </h2>
            <p className="mt-4 text-lg text-gray-600">
              Everything you need to process, secure, and extract value from your PDF documents.
            </p>
          </div>

          <div className="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {/* Redaction Feature */}
            <div className="relative rounded-xl border border-gray-200 bg-white p-8 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-red-100">
                <svg
                  className="h-6 w-6 text-red-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">PDF Redaction</h3>
              <p className="mt-2 text-sm text-gray-600">
                Intelligently identify and redact sensitive information with OCR and fuzzy matching capabilities.
              </p>
              <ul className="mt-4 space-y-2 text-sm text-gray-500">
                <li>• OCR text recognition</li>
                <li>• Fuzzy pattern matching</li>
                <li>• Manual redaction tools</li>
                <li>• Batch processing</li>
              </ul>
            </div>

            {/* Splitting Feature */}
            <div className="relative rounded-xl border border-gray-200 bg-white p-8 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-100">
                <svg
                  className="h-6 w-6 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                  />
                </svg>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">Smart Splitting</h3>
              <p className="mt-2 text-sm text-gray-600">
                Split PDFs by page ranges, bookmarks, or custom patterns with intelligent content detection.
              </p>
              <ul className="mt-4 space-y-2 text-sm text-gray-500">
                <li>• Page range splitting</li>
                <li>• Bookmark-based splits</li>
                <li>• Pattern recognition</li>
                <li>• Batch operations</li>
              </ul>
            </div>

            {/* Merging Feature */}
            <div className="relative rounded-xl border border-gray-200 bg-white p-8 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-green-100">
                <svg
                  className="h-6 w-6 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">PDF Merging</h3>
              <p className="mt-2 text-sm text-gray-600">
                Combine multiple PDFs with custom ordering, bookmarks, and metadata preservation.
              </p>
              <ul className="mt-4 space-y-2 text-sm text-gray-500">
                <li>• Drag & drop ordering</li>
                <li>• Bookmark management</li>
                <li>• Metadata preservation</li>
                <li>• Quality optimization</li>
              </ul>
            </div>

            {/* Extraction Feature */}
            <div className="relative rounded-xl border border-gray-200 bg-white p-8 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-purple-100">
                <svg
                  className="h-6 w-6 text-purple-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">Data Extraction</h3>
              <p className="mt-2 text-sm text-gray-600">
                Extract structured data, tables, images, and metadata with advanced parsing algorithms.
              </p>
              <ul className="mt-4 space-y-2 text-sm text-gray-500">
                <li>• Table extraction</li>
                <li>• Image extraction</li>
                <li>• Metadata analysis</li>
                <li>• Text parsing</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Getting Started Section */}
      <section className="mt-24 bg-primary-50 rounded-2xl">
        <div className="px-8 py-16 sm:px-16">
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900">
              How It Works
            </h2>
            <p className="mt-4 text-lg text-gray-600">
              Get started with our simple three-step process.
            </p>
          </div>

          <div className="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-3">
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary-600 text-white">
                <span className="text-xl font-bold">1</span>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">Upload</h3>
              <p className="mt-2 text-sm text-gray-600">
                Upload your PDF file using our secure drag-and-drop interface or file browser.
              </p>
            </div>

            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary-600 text-white">
                <span className="text-xl font-bold">2</span>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">Process</h3>
              <p className="mt-2 text-sm text-gray-600">
                Choose your processing operation: redact, split, merge, or extract data from your PDF.
              </p>
            </div>

            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary-600 text-white">
                <span className="text-xl font-bold">3</span>
              </div>
              <h3 className="mt-6 text-lg font-semibold text-gray-900">Download</h3>
              <p className="mt-2 text-sm text-gray-600">
                Download your processed PDF with all modifications applied securely.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Security & Privacy Section */}
      <section className="mt-24">
        <div className="mx-auto max-w-4xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-gray-900">
            Security & Privacy First
          </h2>
          <p className="mt-4 text-lg text-gray-600">
            Your documents are processed securely and automatically deleted after processing.
          </p>

          <div className="mt-12 grid grid-cols-1 gap-8 sm:grid-cols-3">
            <div className="flex flex-col items-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-green-100">
                <svg
                  className="h-6 w-6 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-gray-900">Secure Processing</h3>
              <p className="mt-2 text-sm text-gray-600">
                All files are processed server-side with enterprise-grade security protocols.
              </p>
            </div>

            <div className="flex flex-col items-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-100">
                <svg
                  className="h-6 w-6 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-gray-900">Auto-Deletion</h3>
              <p className="mt-2 text-sm text-gray-600">
                Files are automatically deleted after 8 hours for maximum privacy protection.
              </p>
            </div>

            <div className="flex flex-col items-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-purple-100">
                <svg
                  className="h-6 w-6 text-purple-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                  />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-gray-900">Privacy Compliant</h3>
              <p className="mt-2 text-sm text-gray-600">
                GDPR and CCPA compliant with no data retention beyond processing needs.
              </p>
            </div>
          </div>
        </div>
      </section>
        </>
      )}
    </div>
  );
}