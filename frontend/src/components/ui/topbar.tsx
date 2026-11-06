'use client';

import * as React from 'react';
import { ChevronRight, RefreshCw, Bell, HelpCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';

interface TopBarProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
  loading?: boolean;
  onRetry?: () => void;
  className?: string;
}

export function TopBar({
  title,
  subtitle,
  actions,
  breadcrumbs,
  loading,
  onRetry,
  className,
}: TopBarProps) {
  return (
    <div className={cn('flex h-16 items-center gap-4 border-b border-border bg-card px-6 shrink-0', className)}>
      <div className="flex flex-1 flex-col min-w-0">
        <div className="flex items-center gap-2">
          {breadcrumbs && breadcrumbs.length > 0 && (
            <>
              {breadcrumbs.map((b, i) => (
                <span key={i} className="flex items-center gap-1 text-sm">
                  {i > 0 && (
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  {i < breadcrumbs.length - 1 ? (
                    <a href={b.href} className="text-muted-foreground hover:text-foreground transition-colors">
                      {b.label}
                    </a>
                  ) : (
                    <span className="font-semibold">{b.label}</span>
                  )}
                </span>
              ))}
            </>
          )}
          {!breadcrumbs && (
            <>
              <h1 className="shrink-0 text-lg font-semibold truncate">{title}</h1>
              {subtitle && <p className="hidden text-sm text-muted-foreground truncate sm:block">{subtitle}</p>}
            </>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
      {loading && onRetry && (
        <Button variant="ghost" size="sm" onClick={onRetry} className="text-muted-foreground">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          Retry
        </Button>
      )}
    </div>
  );
}
