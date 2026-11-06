import * as React from 'react';
import { cn } from '@/lib/utils';

interface ProgressRingProps {
  progress: number; // 0-100
  size?: number;
  strokeWidth?: number;
  className?: string;
  showLabel?: boolean;
  color?: string;
}

export function ProgressRing({
  progress,
  size = 48,
  strokeWidth = 4,
  className,
  showLabel = false,
  color,
}: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const clamped = Math.min(100, Math.max(0, progress));
  const offset = circumference - (clamped / 100) * circumference;

  const strokeColor = color || (clamped >= 100 ? 'stroke-green-500' : 'stroke-primary');

  return (
    <div className={cn('relative inline-flex', className)}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-border"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          stroke={`currentColor`}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={cn(strokeColor, 'transition-all duration-500 ease-out')}
        />
      </svg>
      {showLabel && (
        <div className="absolute inset-0 flex items-center justify-center text-xs font-semibold">
          {Math.round(clamped)}
        </div>
      )}
    </div>
  );
}
