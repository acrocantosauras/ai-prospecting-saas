'use client';

import { useAuth, useRequireAuth } from '@/lib/hooks/useAuth';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  // Protect the whole (app) group: unauthenticated users get redirected to /login.
  useRequireAuth();
  // These are consumed by child components via useAuth().
  useAuth();

  return (
    <div className="flex flex-1 flex-col min-h-screen">
      {children}
    </div>
  );
}
