'use client';

import { useRequireAuth } from '@/lib/hooks/useAuth';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  // Protect the whole (app) group: unauthenticated users get redirected to /login.
  const { session, checking, workspaces } = useRequireAuth();

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground" role="status">
        Checking your session…
      </div>
    );
  }

  if (!session) return null;

  if (workspaces.length === 0) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-lg rounded-xl border border-border bg-card p-6">
          <h1 className="text-lg font-semibold">No workspace access</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Your account is signed in, but it has no active workspace membership.
            Ask a workspace owner to grant access, then sign in again.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-screen">
      {children}
    </div>
  );
}
