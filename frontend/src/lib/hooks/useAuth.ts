'use client';

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import {
  login as apiLogin,
  logout as apiLogout,
  getAuthMe,
  getAuthStatus,
} from '@/lib/api';
import type { AuthSession, AuthUser, WorkspaceInfo } from '@/lib/types';
import { ApiError } from '@/lib/api/client';

const AUTH_CSRF_COOKIE = 'prospect_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

interface AuthContextValue {
  user: AuthUser | null;
  session: AuthSession | null;
  csrfToken: string | null;
  workspaces: WorkspaceInfo[];
  workspace: WorkspaceInfo | null;
  selectedWorkspaceSlug: string | null;
  selectedWorkspace: WorkspaceInfo | null;
  loading: boolean;
  checking: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  setWorkspace: (slug: string) => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshRef = useRef<(() => void) | null>(null);

  const user = session?.user ?? null;
  const csrfToken = session?.csrf_token ?? null;
  const workspaces = session?.workspaces ?? [];
  const workspace = session?.workspace ?? null;

  const [selectedWorkspaceSlug, setSelectedWorkspaceSlug] = useState<string | null>(null);
  const [selectedWorkspace, setSelectedWorkspace] = useState<WorkspaceInfo | null>(null);

  const resolveSelectedWorkspace = useCallback(
    (slug: string | null, list: WorkspaceInfo[]) => {
      if (!slug) return list[0] ?? null;
      return list.find((w) => w.slug === slug) ?? null;
    },
    [],
  );

  const setWorkspace = useCallback(
    (slug: string) => {
      setSelectedWorkspaceSlug(slug);
      setSelectedWorkspace(resolveSelectedWorkspace(slug, workspaces));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const refreshSession = useCallback(async () => {
    try {
      const me = await getAuthMe(selectedWorkspaceSlug ?? undefined);
      setSession(me);
      setSelectedWorkspaceSlug(me.workspace?.slug ?? selectedWorkspaceSlug);
      const resolvedWs = me.workspace ?? (me.workspaces?.[0] ?? null);
      setSelectedWorkspace(resolvedWs);
      // eslint-disable-next-line react-hooks/exhaustive-deps
      setError(null);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : 'Session check failed';
      setError(message);
      setSession(null);
      setSelectedWorkspaceSlug(null);
      setSelectedWorkspace(null);
    }
  }, [selectedWorkspaceSlug, resolveSelectedWorkspace]);

  const login = useCallback(async (email: string, password: string): Promise<void> => {
    setError(null);
    const result = await apiLogin(email, password);
    setSession(result);
    // Auto-select workspace: first one, or the one the backend defaulted to.
    const pick = result.workspace ?? result.workspaces[0] ?? null;
    setSelectedWorkspaceSlug(pick?.slug ?? null);
    setSelectedWorkspace(pick);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setSession(null);
      setSelectedWorkspaceSlug(null);
      setSelectedWorkspace(null);
      setError(null);
    }
  }, []);

  // Restore session on mount / reload.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setChecking(true);
      try {
        const status = await getAuthStatus();
        if (!status.authentication_available) {
          setSession(null);
          setChecking(false);
          return;
        }
        await refreshSession();
      } catch (e) {
        // Not authenticated (401) or backend unavailable: start unauthenticated.
        setSession(null);
        setError(e instanceof ApiError ? e.message : null);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Re-resolve selected workspace when the session list changes (e.g. after login).
  useEffect(() => {
    if (session) {
      setSelectedWorkspaceSlug(
        selectedWorkspaceSlug ?? session.workspace?.slug ?? session.workspaces[0]?.slug ?? null,
      );
      setSelectedWorkspace(resolveSelectedWorkspace(selectedWorkspaceSlug, session.workspaces));
    }
  }, [session]);

  const value: AuthContextValue = {
    user,
    session,
    csrfToken,
    workspaces,
    workspace,
    selectedWorkspaceSlug,
    selectedWorkspace,
    loading: checking && session === null,
    checking,
    error,
    login,
    logout,
    refreshSession,
    setWorkspace,
    clearError: () => setError(null),
  };

  // Store refreshSession in a ref for external access (e.g., manual refresh buttons).
  // eslint-disable-next-line react-hooks/refs
  refreshRef.current = refreshSession;
  return React.createElement(AuthContext.Provider, { value }, children);
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // During SSR or before AuthProvider mounts, return a safe default.
    if (typeof window === 'undefined') {
      return {
        user: null,
        session: null,
        csrfToken: null,
        workspaces: [],
        workspace: null,
        selectedWorkspaceSlug: null,
        selectedWorkspace: null,
        loading: true,
        checking: true,
        error: null,
        login: async () => {},
        logout: async () => {},
        refreshSession: async () => {},
        setWorkspace: () => {},
        clearError: () => {},
      };
    }
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}

/** CSRF token from the readable cookie, falling back to context (set by login). */
export function useCsrfToken(): string | null {
  const csrf = useAuth().csrfToken;
  if (csrf) return csrf;
  try {
    const raw = document.cookie;
    const re = new RegExp('(?:^|;\\s*)' + AUTH_CSRF_COOKIE + '=([^;]+)');
    const m = raw.match(re);
    return m?.[1] ?? null;
  } catch {
    return null;
  }
}

/** True when the user is signed in and has at least one workspace. */
export function useAuthenticated(): boolean {
  const session = useAuth().session;
  return Boolean(session?.workspaces?.length);
}

/** Redirect to /login when unauthenticated. Call at the top of protected pages. */
export function useRequireAuth() {
  const { session, checking, workspaces, refreshSession } = useAuth();
  const ready = useRef(false);

  useEffect(() => {
    if (!checking) ready.current = true;
  }, [checking]);

  if (!checking && !session) {
    const search = typeof window !== 'undefined' ? window.location.search : '';
    const params = new URLSearchParams(search);
    params.delete('workspace_slug');
    const target = `/login${search ? `?${params.toString()}` : ''}`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, react-hooks/immutability
    window.location.href = target;
  }

  return { session, checking, workspaces };
}

/** Current selected workspace slug. Throws if no workspace selected and multiple exist. */
export function useWorkspaceSlug(): string {
  // Guard against server-side rendering where auth state is not available.
  if (typeof window === 'undefined') return '';
  const { selectedWorkspaceSlug, selectedWorkspace, workspaces, setWorkspace } = useAuth();
  const slug = selectedWorkspaceSlug ?? selectedWorkspace?.slug ?? workspaces[0]?.slug ?? null;
  if (!slug) {
    if (workspaces.length === 0) {
      // Will be caught by useRequireAuth redirect.
      throw new Error('No workspace available');
    }
    // Auto-select first workspace when none chosen.
    setWorkspace(workspaces[0].slug);
    return workspaces[0].slug;
  }
  // Ensure selection still valid.
  if (!workspaces.some((w) => w.slug === slug)) {
    // Selection was revoked: pick the first available.
    if (workspaces.length > 0) {
      setWorkspace(workspaces[0].slug);
      return workspaces[0].slug;
    }
    throw new Error('Workspace revoked');
  }
  return slug;
}
