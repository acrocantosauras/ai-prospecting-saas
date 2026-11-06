'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
  siblingCount?: number;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  className,
  siblingCount = 1,
}: PaginationProps) {
  const pages = React.useMemo(() => {
    const total = totalPages;
    const result: (number | 'ellipsis')[] = [];
    const start = Math.max(1, page - siblingCount);
    const end = Math.min(total, page + siblingCount);

    result.push(1);
    if (start > 2) result.push('ellipsis');
    for (let i = start; i <= end; i++) {
      if (i !== 1) result.push(i);
    }
    if (end < total - 1) result.push('ellipsis');
    if (total > 1) result.push(total);

    return result;
  }, [page, totalPages, siblingCount]);

  if (totalPages <= 1) return null;

  return (
    <nav className={cn('flex items-center justify-center gap-1', className)} aria-label="Pagination">
      <Button
        variant="outline"
        size="sm"
        disabled={page === 1}
        onClick={() => onPageChange(page - 1)}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      {pages.map((p, idx) =>
        p === 'ellipsis' ? (
          <span key={`ellipsis-${idx}`} className="px-2 text-muted-foreground text-sm">…</span>
        ) : (
          <Button
            key={p}
            variant={p === page ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => onPageChange(p as number)}
            aria-label={`Page ${p}`}
            aria-current={p === page ? 'page' : undefined}
          >
            {p}
          </Button>
        )
      )}
      <Button
        variant="outline"
        size="sm"
        disabled={page === totalPages}
        onClick={() => onPageChange(page + 1)}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}
