'use client';

import { useMemo } from 'react';
import clsx from 'clsx';
import type { ProgressBarProps } from '@/types';
import { formatPercentage, formatTimeRemaining } from '@/utils/formatUtils';

const ProgressBar = ({
  progress,
  indeterminate = false,
  label,
  showPercentage = true,
  variant = 'default',
  size = 'md',
  className,
  ...props
}: ProgressBarProps): JSX.Element => {
  const progressValue = useMemo(() => {
    if (indeterminate) return 0;
    return Math.min(Math.max(progress, 0), 100);
  }, [progress, indeterminate]);

  const progressBarClasses = useMemo(() => {
    return clsx(
      'relative overflow-hidden rounded-full bg-gray-200',
      {
        // Sizes
        'h-1': size === 'sm',
        'h-2': size === 'md',
        'h-3': size === 'lg',
      },
      className
    );
  }, [size, className]);

  const progressFillClasses = useMemo(() => {
    return clsx(
      'h-full rounded-full transition-all duration-300 ease-out',
      {
        // Variants
        'bg-primary-600': variant === 'default',
        'bg-green-600': variant === 'success',
        'bg-yellow-600': variant === 'warning',
        'bg-red-600': variant === 'error',
        
        // Indeterminate animation
        'animate-progress': indeterminate,
      }
    );
  }, [variant, indeterminate]);

  const labelClasses = useMemo(() => {
    return clsx(
      'flex items-center justify-between text-sm font-medium text-gray-700',
      {
        'mb-1': size === 'sm',
        'mb-2': size === 'md' || size === 'lg',
      }
    );
  }, [size]);

  return (
    <div {...props}>
      {(label || showPercentage) && (
        <div className={labelClasses}>
          <span>{label || ''}</span>
          {showPercentage && !indeterminate && (
            <span className="text-xs text-gray-500">
              {formatPercentage(progressValue, 0)}
            </span>
          )}
        </div>
      )}
      
      <div className={progressBarClasses} role="progressbar" aria-valuenow={progressValue} aria-valuemin={0} aria-valuemax={100}>
        <div
          className={progressFillClasses}
          style={indeterminate ? undefined : { width: `${progressValue}%` }}
        >
          {indeterminate && (
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-progress" />
          )}
        </div>
      </div>
      
      {indeterminate && (
        <div className="mt-1 text-xs text-gray-500 text-center">
          Processing...
        </div>
      )}
    </div>
  );
};

export default ProgressBar;