import * as React from 'react';
import { cn } from '@/lib/utils';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'secondary' | 'outline' | 'success' | 'warning' | 'destructive' | 'info';
}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    const variants = {
      default: 'bg-primary text-primary-foreground',
      secondary: 'bg-secondary text-secondary-foreground',
      outline: 'border border-border bg-background text-muted-foreground',
      success: 'bg-green-50 text-green-700 border border-green-200',
      warning: 'bg-amber-50 text-amber-700 border border-amber-200',
      destructive: 'bg-red-50 text-red-700 border border-red-200',
      info: 'bg-blue-50 text-blue-700 border border-blue-200',
    };
    return (
      <span ref={ref} className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors', variants[variant], className)} {...props} />
    );
  },
);
Badge.displayName = 'Badge';

export { Badge };
