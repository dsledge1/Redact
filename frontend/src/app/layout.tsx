import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export const metadata: Metadata = {
  title: 'Ultimate PDF - Advanced PDF Processing Tools',
  description: 'Professional PDF processing platform with redaction, splitting, merging, and extraction capabilities.',
  keywords: 'PDF, redaction, splitting, merging, extraction, OCR, document processing',
  authors: [{ name: 'Ultimate PDF Team' }],
  creator: 'Ultimate PDF',
  publisher: 'Ultimate PDF',
  robots: 'index, follow',
  viewport: 'width=device-width, initial-scale=1',
  themeColor: '#3b82f6',
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000',
    title: 'Ultimate PDF - Advanced PDF Processing Tools',
    description: 'Professional PDF processing platform with redaction, splitting, merging, and extraction capabilities.',
    siteName: 'Ultimate PDF',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Ultimate PDF - Advanced PDF Processing Tools',
    description: 'Professional PDF processing platform with redaction, splitting, merging, and extraction capabilities.',
  },
  icons: {
    icon: '/favicon.ico',
    shortcut: '/favicon-16x16.png',
    apple: '/apple-touch-icon.png',
  },
};

interface RootLayoutProps {
  children: React.ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps): JSX.Element {
  return (
    <html lang="en" className={inter.variable}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <div className="flex min-h-screen flex-col">
          <header className="sticky top-0 z-40 w-full border-b bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60">
            <div className="container mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
              <div className="flex items-center space-x-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600">
                  <svg
                    className="h-5 w-5 text-white"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                </div>
                <h1 className="text-xl font-bold text-gray-900">Ultimate PDF</h1>
              </div>
              <nav className="flex items-center space-x-6">
                <a
                  href="#features"
                  className="text-sm font-medium text-gray-700 transition-colors hover:text-primary-600"
                >
                  Features
                </a>
                <a
                  href="#about"
                  className="text-sm font-medium text-gray-700 transition-colors hover:text-primary-600"
                >
                  About
                </a>
                <button
                  type="button"
                  className="inline-flex items-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                  aria-label="Get started with PDF processing"
                >
                  Get Started
                </button>
              </nav>
            </div>
          </header>

          <main className="flex-1" role="main">
            {children}
          </main>

          <footer className="border-t bg-white">
            <div className="container mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
              <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Product</h3>
                  <ul className="mt-4 space-y-2">
                    <li>
                      <a href="#redaction" className="text-sm text-gray-600 hover:text-gray-900">
                        PDF Redaction
                      </a>
                    </li>
                    <li>
                      <a href="#splitting" className="text-sm text-gray-600 hover:text-gray-900">
                        PDF Splitting
                      </a>
                    </li>
                    <li>
                      <a href="#merging" className="text-sm text-gray-600 hover:text-gray-900">
                        PDF Merging
                      </a>
                    </li>
                    <li>
                      <a href="#extraction" className="text-sm text-gray-600 hover:text-gray-900">
                        Data Extraction
                      </a>
                    </li>
                  </ul>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Support</h3>
                  <ul className="mt-4 space-y-2">
                    <li>
                      <a href="#documentation" className="text-sm text-gray-600 hover:text-gray-900">
                        Documentation
                      </a>
                    </li>
                    <li>
                      <a href="#contact" className="text-sm text-gray-600 hover:text-gray-900">
                        Contact
                      </a>
                    </li>
                  </ul>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Security</h3>
                  <ul className="mt-4 space-y-2">
                    <li>
                      <a href="#privacy" className="text-sm text-gray-600 hover:text-gray-900">
                        Privacy Policy
                      </a>
                    </li>
                    <li>
                      <a href="#terms" className="text-sm text-gray-600 hover:text-gray-900">
                        Terms of Service
                      </a>
                    </li>
                  </ul>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Ultimate PDF</h3>
                  <p className="mt-4 text-sm text-gray-600">
                    Professional PDF processing tools for modern workflows.
                  </p>
                </div>
              </div>
              <div className="mt-8 border-t pt-8">
                <p className="text-center text-sm text-gray-500">
                  © {new Date().getFullYear()} Ultimate PDF. All rights reserved.
                </p>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}