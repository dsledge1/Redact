'use client';

import { useMemo } from 'react';
import clsx from 'clsx';
import type { BaseComponentProps } from '@/types';

interface LoadingSpinnerProps extends BaseComponentProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'default' | 'primary' | 'white';
  text?: string;
  overlay?: boolean;
  timeout?: number;
}

const LoadingSpinner = ({
  size = 'md',
  variant = 'default',
  text,
  overlay = false,
  className,
  children,
  ...props
}: LoadingSpinnerProps): JSX.Element => {
  const spinnerClasses = useMemo(() => {
    return clsx(
      'animate-spin rounded-full border-2 border-solid',
      {
        // Sizes
        'h-4 w-4': size === 'sm',
        'h-6 w-6': size === 'md',
        'h-8 w-8': size === 'lg',
        'h-12 w-12': size === 'xl',
        
        // Variants
        'border-gray-300 border-t-gray-900': variant === 'default',
        'border-primary-200 border-t-primary-600': variant === 'primary',
        'border-white/30 border-t-white': variant === 'white',
      },
      className
    );
  }, [size, variant, className]);

  const containerClasses = useMemo(() => {
    return clsx(
      'flex flex-col items-center justify-center',
      {
        // Overlay styles
        'fixed inset-0 z-50 bg-black/20 backdrop-blur-sm': overlay,
        'space-y-3': text || children,
        'p-4': overlay,
      }
    );
  }, [overlay, text, children]);

  const textClasses = useMemo(() => {
    return clsx(
      'text-sm font-medium',
      {
        'text-gray-700': variant === 'default',
        'text-primary-700': variant === 'primary',
        'text-white': variant === 'white',
      }
    );
  }, [variant]);

  const spinnerElement = (
    <div className={spinnerClasses} role="status" aria-label="Loading">
      <span className="sr-only">Loading...</span>
    </div>
  );

  const content = (
    <>
      {spinnerElement}
      {text && <p className={textClasses}>{text}</p>}
      {children}
    </>
  );

  if (overlay) {
    return (
      <div className={containerClasses} {...props}>
        <div className="bg-white rounded-lg p-6 shadow-xl">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className={containerClasses} {...props}>
      {content}
    </div>
  );
};

// Preset configurations for common use cases
export const LoadingSpinners = {
  Small: (props: Omit<LoadingSpinnerProps, 'size'>) => (
    <LoadingSpinner size="sm" {...props} />
  ),
  
  Medium: (props: Omit<LoadingSpinnerProps, 'size'>) => (
    <LoadingSpinner size="md" {...props} />
  ),
  
  Large: (props: Omit<LoadingSpinnerProps, 'size'>) => (
    <LoadingSpinner size="lg" {...props} />
  ),
  
  Overlay: (props: Omit<LoadingSpinnerProps, 'overlay'>) => (
    <LoadingSpinner overlay={true} {...props} />
  ),
  
  Primary: (props: Omit<LoadingSpinnerProps, 'variant'>) => (
    <LoadingSpinner variant="primary" {...props} />
  ),
  
  White: (props: Omit<LoadingSpinnerProps, 'variant'>) => (
    <LoadingSpinner variant="white" {...props} />
  ),
};

export default LoadingSpinner;