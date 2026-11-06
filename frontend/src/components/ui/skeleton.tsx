import * as React from 'react';
import { cn } from '@/lib/utils';

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
}

function Skeleton({
  className,
  variant = 'text',
  width,
  height,
  style,
  ...props
}: SkeletonProps) {
  const variants = {
    text: 'rounded-md',
    circular: 'rounded-full',
    rectangular: 'rounded-lg',
  };
  return (
    <div
      className={cn('animate-pulse bg-muted', variants[variant], className)}
      style={{
        width: width,
        height: height,
        ...style,
      }}
      {...props}
    />
  );
}

const SkeletonCard = ({ className }: { className?: string }) => (
  <div className={cn('rounded-xl border border-border bg-card p-6', className)}>
    <div className="flex items-start justify-between mb-4">
      <div className="space-y-2">
        <Skeleton width="60%" height={20} />
        <Skeleton width="40%" height={14} />
      </div>
      <Skeleton variant="circular" width={40} height={40} />
    </div>
    <Skeleton height={60} className="mb-3" />
    <Skeleton height={14} width="80%" />
  </div>
);

const SkeletonTable = ({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) => (
  <div className="rounded-xl border border-border bg-card overflow-hidden">
    <div className="p-4 border-b border-border space-y-2">
      <Skeleton width="30%" height={20} />
      <Skeleton width="20%" height={14} />
    </div>
    <div className="divide-y divide-border">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="p-4 grid grid-cols-12 gap-3 items-center">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} width="100%" height={16} className="col-span-1" />
          ))}
        </div>
      ))}
    </div>
  </div>
);

const SkeletonPage = ({ className }: { className?: string }) => (
  <div className={cn('space-y-6 p-6', className)}>
    <div className="flex items-center justify-between">
      <div className="space-y-2">
        <Skeleton width="25%" height={28} />
        <Skeleton width="15%" height={14} />
      </div>
      <Skeleton width={120} height={36} />
    </div>
    <div className="grid grid-cols-12 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <SkeletonCard key={i} className="col-span-12 sm:col-span-6 lg:col-span-3" />
      ))}
    </div>
    <SkeletonTable rows={6} cols={5} />
  </div>
);

export { Skeleton, SkeletonCard, SkeletonTable, SkeletonPage };
