'use client';

import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  title?: string;
  description?: string;
}

export function Modal({ open, onClose, children, className, title, description }: ModalProps) {
  React.useEffect(() => {
    if (open) {
      const handleEsc = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      };
      document.addEventListener('keydown', handleEsc);
      document.body.style.overflow = 'hidden';
      return () => {
        document.removeEventListener('keydown', handleEsc);
        document.body.style.overflow = '';
      };
    }
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose} />
      <div
        className={cn(
          'relative z-10 mx-auto max-w-lg w-full rounded-xl border border-border bg-card p-6 shadow-xl animate-in fade-in zoom-in-95 duration-200',
          className,
        )}
        onClick={e => e.stopPropagation()}
      >
        {(title || description) && (
          <div className="mb-5">
            {title && <h2 className="text-lg font-semibold">{title}</h2>}
            {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
          </div>
        )}
        {children}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1 text-muted-foreground opacity-70 transition-opacity hover:opacity-100 hover:bg-secondary"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger';
  loading?: boolean;
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  loading,
}: ConfirmModalProps) {
  return (
    <Modal open={open} onClose={onClose} title={title} description={description}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <button
            onClick={onConfirm}
            disabled={loading}
            className={cn(
              'flex w-full justify-center rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              variant === 'danger'
                ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                : 'bg-primary text-primary-foreground hover:bg-primary/90',
              loading && 'opacity-50 pointer-events-none',
            )}
          >
            {loading ? 'Processing...' : confirmLabel}
          </button>
          <button
            onClick={onClose}
            className="flex w-full justify-center rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-secondary transition-colors"
          >
            {cancelLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
