'use client';

import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Toast {
  id: string;
  type: 'default' | 'success' | 'error' | 'warning' | 'info';
  title: string;
  description?: string;
  duration?: number;
}

interface ToastContextValue {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

export function ToastProviderInner({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const addToast = React.useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).slice(2);
    const t: Toast = { ...toast, id };
    setToasts(prev => [...prev, t]);
    const duration = toast.duration ?? 5000;
    if (duration > 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, duration);
    }
  }, []);

  const removeToast = React.useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  );
}

export { ToastProviderInner as ToastProvider };

const ToastContainer = ({
  toasts,
  removeToast,
}: {
  toasts: Toast[];
  removeToast: (id: string) => void;
}) => {
  if (toasts.length === 0) return null;
  return (
    <div
      role="region"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full"
    >
      {toasts.map(t => (
        <ToastItem key={t.id} toast={t} onDismiss={() => removeToast(t.id)} />
      ))}
    </div>
  );
};
const ToastItem = ({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) => {
  const variants = {
    default: 'bg-card border-border text-card-foreground',
    success: 'bg-green-50 border-green-200 text-green-900',
    error: 'bg-red-50 border-red-200 text-red-900',
    warning: 'bg-amber-50 border-amber-200 text-amber-900',
    info: 'bg-blue-50 border-blue-200 text-blue-900',
  };
  const icons = {
    default: 'text-muted-foreground',
    success: 'text-green-600',
    error: 'text-red-600',
    warning: 'text-amber-600',
    info: 'text-blue-600',
  };
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-4 shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200',
        variants[toast.type],
      )}
      role="alert"
    >
      <span className={cn('mt-0.5 flex h-4 w-4 shrink-0', icons[toast.type])}>
        {toast.type === 'success' && (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        {toast.type === 'error' && (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <circle cx="12" cy="12" r="10" />
            <path d="M15 9l-6 6M9 9l6 6" strokeLinecap="round" />
          </svg>
        )}
        {toast.type === 'warning' && (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        {toast.type === 'info' && (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
          </svg>
        )}
        {toast.type === 'default' && (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
          </svg>
        )}
      </span>
      <div className="flex-1 space-y-1">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description && <p className="text-sm opacity-80">{toast.description}</p>}
      </div>
      <button
        onClick={onDismiss}
        className="flex h-4 w-4 shrink-0 cursor-pointer items-center justify-center rounded transition-colors hover:bg-black/10"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};
