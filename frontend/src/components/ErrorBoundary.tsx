'use client';

import React from 'react';
import type { BaseComponentProps, APIError } from '@/types';

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: React.ErrorInfo;
  errorId: string;
}

interface ErrorBoundaryProps extends BaseComponentProps {
  fallback?: React.ComponentType<ErrorFallbackProps>;
  onError?: (error: Error, errorInfo: React.ErrorInfo, errorId: string) => void;
  showDetails?: boolean;
}

interface ErrorFallbackProps {
  error: Error;
  errorInfo?: React.ErrorInfo;
  errorId: string;
  retry: () => void;
  showDetails?: boolean;
}

/**
 * Default error fallback component
 */
const DefaultErrorFallback: React.FC<ErrorFallbackProps> = ({
  error,
  errorInfo,
  errorId,
  retry,
  showDetails = false,
}) => {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md rounded-lg bg-white p-8 shadow-lg">
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0">
            <svg
              className="h-8 w-8 text-red-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Something went wrong</h3>
            <p className="mt-1 text-sm text-gray-600">
              An unexpected error occurred while processing your request.
            </p>
          </div>
        </div>

        <div className="mt-6 space-y-4">
          <button
            type="button"
            onClick={retry}
            className="w-full rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            Try Again
          </button>

          <button
            type="button"
            onClick={() => window.location.reload()}
            className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            Refresh Page
          </button>

          <button
            type="button"
            onClick={() => window.location.href = '/'}
            className="w-full text-sm text-gray-500 hover:text-gray-700"
          >
            Return to Home
          </button>
        </div>

        {showDetails && (
          <details className="mt-6">
            <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900">
              Error Details
            </summary>
            <div className="mt-3 space-y-2 rounded bg-gray-50 p-3 text-xs">
              <div>
                <strong className="text-gray-700">Error ID:</strong>
                <code className="ml-2 text-gray-600">{errorId}</code>
              </div>
              <div>
                <strong className="text-gray-700">Message:</strong>
                <p className="mt-1 text-gray-600">{error.message}</p>
              </div>
              {error.stack && (
                <div>
                  <strong className="text-gray-700">Stack Trace:</strong>
                  <pre className="mt-1 whitespace-pre-wrap text-gray-600">{error.stack}</pre>
                </div>
              )}
              {errorInfo?.componentStack && (
                <div>
                  <strong className="text-gray-700">Component Stack:</strong>
                  <pre className="mt-1 whitespace-pre-wrap text-gray-600">{errorInfo.componentStack}</pre>
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </div>
  );
};

/**
 * React Error Boundary component for graceful error handling
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);

    this.state = {
      hasError: false,
      errorId: '',
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
      errorId: `error_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log the error
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Update state with error info
    this.setState({
      errorInfo,
    });

    // Call the onError callback if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo, this.state.errorId);
    }

    // Send error to logging service in production
    if (process.env.NODE_ENV === 'production') {
      this.logErrorToService(error, errorInfo, this.state.errorId);
    }
  }

  private logErrorToService(error: Error, errorInfo: React.ErrorInfo, errorId: string) {
    // In a real application, you would send this to your error tracking service
    // e.g., Sentry, Rollbar, Bugsnag, etc.
    try {
      const errorData = {
        id: errorId,
        message: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        userAgent: navigator.userAgent,
      };

      // Example: Send to your logging API
      // fetch('/api/errors', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify(errorData),
      // });

      console.log('Error logged with ID:', errorId, errorData);
    } catch (loggingError) {
      console.error('Failed to log error:', loggingError);
    }
  }

  private handleRetry = () => {
    this.setState({
      hasError: false,
      error: undefined,
      errorInfo: undefined,
      errorId: '',
    });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      const FallbackComponent = this.props.fallback || DefaultErrorFallback;

      return (
        <FallbackComponent
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          errorId={this.state.errorId}
          retry={this.handleRetry}
          showDetails={this.props.showDetails || process.env.NODE_ENV === 'development'}
        />
      );
    }

    return this.props.children;
  }
}

/**
 * Hook for handling async errors that don't trigger error boundaries
 */
export const useErrorHandler = () => {
  const [, setError] = React.useState<Error | null>(null);

  return React.useCallback((error: Error | APIError | unknown) => {
    console.error('Async error:', error);
    
    // Convert APIError to Error if needed
    if (error && typeof error === 'object' && 'code' in error) {
      const apiError = error as APIError;
      setError(new Error(apiError.message));
    } else if (error instanceof Error) {
      setError(error);
    } else {
      setError(new Error(String(error)));
    }
  }, []);
};

/**
 * Higher-order component for wrapping components with error boundary
 */
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryProps?: Omit<ErrorBoundaryProps, 'children'>
) {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ErrorBoundary>
  );

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`;
  
  return WrappedComponent;
}

export default ErrorBoundary;