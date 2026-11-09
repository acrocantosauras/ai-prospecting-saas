'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from './useAuth';
import { getBatches, getBatch, getProspects, ApiError } from '@/lib/api';
import type { ProspectBatch, ProspectList } from '@/lib/types';

const MAX_POLL_ATTEMPTS = 150; // ~5 minutes at 2s intervals

/** Resolve the current workspace slug from auth context. Must be called inside a React component or hook. */
export function useWorkspaceSlugFromAuth(): string {
  const { selectedWorkspaceSlug, selectedWorkspace, workspaces } = useAuth();
  return selectedWorkspaceSlug ?? selectedWorkspace?.slug ?? workspaces[0]?.slug ?? 'unknown';
}

/** Resolve the current workspace slug from auth context. Must be called inside a React component or hook. */
export function useBatches() {
  const slug = useWorkspaceSlugFromAuth();
  const [batches, setBatches] = useState<ProspectBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchBatchList(s: string): Promise<ProspectBatch[]> {
    if (s === 'unknown') return [];
    const data = await getBatches(s);
    return data.items || [];
  }

  const refresh = useCallback(async () => {
    try {
      const list = await fetchBatchList(slug);
      setBatches(list);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load batches');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchBatchList(slug)
      .then(list => {
        if (cancelled) return;
        setBatches(list);
        setError(null);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : 'Failed to load batches');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { batches, loading, error, refresh };
}

export function useLatestBatch() {
  const { batches, loading, error, refresh } = useBatches();
  const latest = batches[0];
  return { batch: latest, loading, error, refresh };
}

interface UseBatchPollOptions {
  onComplete?: (batch: ProspectBatch) => void;
  onError?: (error: string) => void;
  intervalMs?: number;
}

/**
 * Polls a single batch until it reaches a terminal state.
 * `start(batchId)` begins polling; polling always stops on completion, failure,
 * unmount, or after MAX_POLL_ATTEMPTS.
 */
export function useBatchPoll({
  onComplete,
  onError,
  intervalMs = 2000,
}: UseBatchPollOptions) {
  const [batch, setBatch] = useState<ProspectBatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(false);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRef = useRef(false);
  const inFlightRef = useRef(false);
  const idRef = useRef<string | null>(null);
  const attemptsRef = useRef(0);
  const notifiedRef = useRef<string | null>(null);
  const callbacksRef = useRef({ onComplete, onError });

  useEffect(() => {
    callbacksRef.current = { onComplete, onError };
  }, [onComplete, onError]);

  const clearTimer = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearTimer();
    activeRef.current = false;
    idRef.current = null;
    setActive(false);
    setLoading(false);
  }, [clearTimer]);

  const finish = useCallback((done: ProspectBatch) => {
    clearTimer();
    // Guard the interval callback: no request may be issued after a terminal
    // state, even if a tick was already queued.
    activeRef.current = false;
    setActive(false);
    setLoading(false);
    const key = `${done.id}:${done.status}`;
    if (notifiedRef.current === key) return;
    notifiedRef.current = key;
    if (done.status === 'completed') {
      callbacksRef.current.onComplete?.(done);
    } else if (done.status === 'failed') {
      callbacksRef.current.onError?.(done.error_message || 'Pipeline failed');
    }
  }, [clearTimer]);

  const poll = useCallback(async (id: string) => {
    if (!id || inFlightRef.current) return;
    inFlightRef.current = true;
    attemptsRef.current += 1;
    try {
      const slug = useWorkspaceSlugFromAuth();
      if (slug === 'unknown') {
        setError('No workspace selected');
        setLoading(false);
        return;
      }
      const found = await getBatch(id, slug);
      if (idRef.current !== id) return;
      setBatch(found);
      setError(null);
      if (found.status === 'completed' || found.status === 'failed') {
        finish(found);
      } else if (attemptsRef.current >= MAX_POLL_ATTEMPTS) {
        clearTimer();
        activeRef.current = false;
        setActive(false);
        setLoading(false);
        setError('Batch is taking longer than expected. Refresh to check the latest status.');
      } else {
        setLoading(false);
      }
    } catch (e) {
      if (idRef.current !== id) return;
      setError(e instanceof ApiError ? e.message : 'Failed to fetch batch');
      setLoading(false);
      if (attemptsRef.current >= MAX_POLL_ATTEMPTS) clearTimer();
    } finally {
      inFlightRef.current = false;
    }
  }, [clearTimer, finish]);

  const start = useCallback((id: string) => {
    clearTimer();
    idRef.current = id;
    attemptsRef.current = 0;
    notifiedRef.current = null;
    setBatch(null);
    setError(null);
    setLoading(true);
    setActive(true);
    activeRef.current = true;
    poll(id);
    intervalRef.current = setInterval(() => {
      if (idRef.current && activeRef.current) poll(idRef.current);
    }, intervalMs);
  }, [clearTimer, intervalMs, poll]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
    };
  }, []);

  return { batch, loading, error, active, start, stop };
}

export function useProspectSearch(params: {
  initialSearch?: string;
  initialIndustry?: string;
  initialCountry?: string;
  initialMinScore?: number;
  initialMaxScore?: number;
  initialReady?: boolean | null;
  initialPage?: number;
  initialPageSize?: number;
  initialBatchId?: string;
}) {
  const [search, setSearch] = useState(params.initialSearch || '');
  const [industry, setIndustry] = useState(params.initialIndustry || '');
  const [country, setCountry] = useState(params.initialCountry || '');
  const [minScore, setMinScore] = useState<number | undefined>(params.initialMinScore);
  const [maxScore, setMaxScore] = useState<number | undefined>(params.initialMaxScore);
  const [ready, setReady] = useState<boolean | null>(params.initialReady ?? null);
  const [page, setPage] = useState(params.initialPage || 1);
  const [pageSize, setPageSize] = useState(params.initialPageSize || 20);
  const [batchId, setBatchId] = useState<string | undefined>(params.initialBatchId);
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const [data, setData] = useState<ProspectList | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const queryKey = JSON.stringify([
    batchId ?? '', search, industry, country,
    minScore ?? '', maxScore ?? '', ready === null ? 'null' : String(ready),
    page, pageSize, sortBy, sortOrder,
  ]);

  // Derived: a request is in flight whenever the loaded snapshot is stale.
  const loading = loadedKey !== queryKey;

  const slug = useWorkspaceSlugFromAuth();

  useEffect(() => {
    let cancelled = false;
    const key = queryKey;
    if (slug === 'unknown') {
      setError('No workspace selected');
      setData(null);
      setLoadedKey(key);
      return;
    }
    getProspects({
      workspaceSlug: slug,
      batchId,
      search: search || undefined,
      industry: industry || undefined,
      country: country || undefined,
      minScore,
      maxScore,
      readyForOutreach: ready,
      page,
      pageSize,
      sortBy,
      sortOrder,
    })
      .then(result => {
        if (cancelled) return;
        setData(result);
        setError(null);
        setLoadedKey(key);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : 'Failed to load prospects');
        setData(null);
        setLoadedKey(key);
      });
    return () => {
      cancelled = true;
    };
  }, [queryKey, batchId, search, industry, country, minScore, maxScore, ready, page, pageSize, sortBy, sortOrder, reloadToken]);

  const resetPage = useCallback(() => setPage(1), []);
  const fetchData = useCallback(() => setReloadToken(token => token + 1), []);

  return {
    batchId,
    search,
    setSearch,
    industry,
    setIndustry,
    country,
    setCountry,
    minScore,
    setMinScore,
    maxScore,
    setMaxScore,
    ready,
    setReady,
    page,
    setPage,
    pageSize,
    setPageSize,
    sortBy,
    setSortBy,
    sortOrder,
    setSortOrder,
    setBatchId,
    data,
    loading,
    error,
    fetch: fetchData,
    resetPage,
  };
}
