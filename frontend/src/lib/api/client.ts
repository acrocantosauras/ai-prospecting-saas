import type {
  ClientProfile,
  ClientProfileCreate,
  ClientProfileUpdate,
  ICPProfile,
  ICPProfileCreate,
  ICPProfileUpdate,
  ProspectBatch,
  ProspectBatchList,
  ProspectBatchCreate,
  ProspectList,
  ProspectDetail,
  Prospect,
  LeadExportRow,
  AuthSession,
  AuthStatus,
  WorkspaceInfo,
  EngineBatchSnapshot,
  StageRun,
  QualificationDecision,
  ProspectVerification,
  CompanyEvidence,
  DemoReadiness,
  ProviderOverview,
  UsageTotals,
} from '@/lib/types';

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
const AUTH_CSRF_COOKIE = 'prospect_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

/** Try to read the readable CSRF cookie (`prospect_csrf`) from document.cookie. */
function getCsrfFromCookie(): string | null {
  try {
    const raw = document.cookie;
    if (!raw) return null;
    const m = raw.match(new RegExp(String.raw`(?:^|;\s*)${AUTH_CSRF_COOKIE}=([^;]+)`));
    return m?.[1] ?? null;
  } catch {
    return null;
  }
}

async function fetcher<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(options?.headers);
  // Attach CSRF token on non-safe methods when authenticated via cookie.
  if (!headers.has('X-CSRF-Token')) {
    const method = (options?.method ?? 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      const m = getCsrfFromCookie();
      if (m) headers.set(CSRF_HEADER, m);
    }
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try {
      const json = JSON.parse(text);
      detail = json.detail || json.message || text;
    } catch {
      // keep raw text
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  if (res.headers.get('content-type')?.includes('text/csv')) {
    return (await res.text()) as unknown as T;
  }
  return res.json();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

// Health
export async function getHealth(): Promise<{ status: string }> {
  return fetcher<{ status: string }>('/health');
}

// Business Profile
export async function getClientProfiles(workspaceSlug: string): Promise<ClientProfile[]> {
  return fetcher(`/api/v1/business-profile/?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function getClientProfile(
  profileId: string,
  workspaceSlug: string,
): Promise<ClientProfile | null> {
  return fetcher(`/api/v1/business-profile/${profileId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function createClientProfile(
  data: ClientProfileCreate,
): Promise<ClientProfile> {
  return fetcher('/api/v1/business-profile/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateClientProfile(
  profileId: string,
  data: ClientProfileUpdate,
  workspaceSlug: string,
): Promise<ClientProfile> {
  return fetcher(`/api/v1/business-profile/${profileId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// ICP
export async function getICPProfiles(workspaceSlug: string): Promise<ICPProfile[]> {
  return fetcher(`/api/v1/icp/?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function getICPProfile(
  icpId: string,
  workspaceSlug: string,
): Promise<ICPProfile | null> {
  return fetcher(`/api/v1/icp/${icpId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function createICPProfile(
  data: ICPProfileCreate,
): Promise<ICPProfile> {
  return fetcher('/api/v1/icp/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateICPProfile(
  icpId: string,
  data: ICPProfileUpdate,
  workspaceSlug: string,
): Promise<ICPProfile> {
  return fetcher(`/api/v1/icp/${icpId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// Batches
export async function getBatches(workspaceSlug: string): Promise<ProspectBatchList> {
  return fetcher(`/api/v1/batches/?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function getBatch(
  batchId: string,
  workspaceSlug: string,
): Promise<ProspectBatch> {
  return fetcher(`/api/v1/batches/${batchId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function createBatch(data: ProspectBatchCreate): Promise<ProspectBatch> {
  return fetcher('/api/v1/batches/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Prospects
export async function getProspects(params: {
  workspaceSlug: string;
  batchId?: string;
  search?: string;
  industry?: string;
  country?: string;
  minScore?: number;
  maxScore?: number;
  emailStatus?: string;
  readyForOutreach?: boolean | null;
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortOrder?: string;
}): Promise<ProspectList> {
  const q = new URLSearchParams();
  q.set('workspace_slug', params.workspaceSlug);
  if (params.batchId) q.set('batch_id', params.batchId);
  if (params.search) q.set('search', params.search);
  if (params.industry) q.set('industry', params.industry);
  if (params.country) q.set('country', params.country);
  if (params.minScore !== undefined) q.set('min_score', String(params.minScore));
  if (params.maxScore !== undefined) q.set('max_score', String(params.maxScore));
  if (params.emailStatus) q.set('email_status', params.emailStatus);
  if (params.readyForOutreach !== undefined && params.readyForOutreach !== null) {
    q.set('ready_for_outreach', String(params.readyForOutreach));
  }
  if (params.page !== undefined) q.set('page', String(params.page));
  if (params.pageSize !== undefined) q.set('page_size', String(params.pageSize));
  if (params.sortBy) q.set('sort_by', params.sortBy);
  if (params.sortOrder) q.set('sort_order', params.sortOrder);
  return fetcher(`/api/v1/prospects/?${q.toString()}`);
}

export async function getProspect(
  prospectId: string,
  workspaceSlug: string,
): Promise<ProspectDetail> {
  return fetcher(`/api/v1/prospects/${prospectId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function updateProspect(
  prospectId: string,
  data: Partial<Prospect>,
  workspaceSlug: string,
): Promise<Prospect> {
  return fetcher(`/api/v1/prospects/${prospectId}?workspace_slug=${encodeURIComponent(workspaceSlug)}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// Exports
export async function downloadCsv(
  batchId: string,
  workspaceSlug: string,
  includeAll?: boolean,
): Promise<string> {
  const q = new URLSearchParams({ workspace_slug: workspaceSlug });
  if (includeAll) q.set('include_all', 'true');
  const csrf = getCsrfFromCookie();
  const headers: Record<string, string> = {};
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const res = await fetch(`${BASE_URL}/api/v1/exports/csv/${batchId}?${q.toString()}`, {
    credentials: 'include',
    headers,
  });
  if (!res.ok) {
    let detail = `Export failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // keep default message
    }
    throw new ApiError(res.status, detail);
  }
  return res.text();
}

/** Stage-by-stage progress, counts and measured provider cost for a batch. */
export async function getBatchProgress(
  batchId: string,
  workspaceSlug: string,
): Promise<{
  batch: EngineBatchSnapshot;
  progress_percent: number;
  stages: StageRun[];
  usage: UsageTotals;
  qualified_companies: number;
  rejected_companies: number;
  recheck_companies: number;
}> {
  return fetcher(`/api/v1/engine/batches/${encodeURIComponent(batchId)}/progress?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

/** Request cancellation of a pending or running batch. */
export async function cancelBatch(
  batchId: string,
  workspaceSlug: string,
): Promise<EngineBatchSnapshot> {
  return fetcher(
    `/api/v1/engine/batches/${encodeURIComponent(batchId)}/cancel?workspace_slug=${encodeURIComponent(workspaceSlug)}`,
    { method: 'POST' },
  );
}

/** Qualification decisions (including rejections) for a batch. */
export async function getQualifications(
  batchId: string,
  workspaceSlug: string,
  params?: {
    status?: string;
    scope?: string;
    limit?: number;
  },
): Promise<QualificationDecision[]> {
  const q = new URLSearchParams({ workspace_slug: workspaceSlug });
  if (params?.status) q.set('status', params.status);
  if (params?.scope) q.set('scope', params.scope);
  if (params?.limit) q.set('limit', String(params.limit));
  return fetcher(`/api/v1/engine/batches/${encodeURIComponent(batchId)}/qualifications?${q.toString()}`);
}

/** Verification, enrichment and evidence detail for a prospect. */
export async function getProspectVerification(
  prospectId: string,
  workspaceSlug: string,
): Promise<ProspectVerification> {
  return fetcher(`/api/v1/engine/prospects/${encodeURIComponent(prospectId)}/verification?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

/** Research findings and evidence for a company. */
export async function getCompanyEvidence(
  companyId: string,
  workspaceSlug: string,
): Promise<CompanyEvidence> {
  return fetcher(`/api/v1/engine/companies/${encodeURIComponent(companyId)}/evidence?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

/** Queue a safe research refresh for a company. */
export async function refreshCompany(
  companyId: string,
  workspaceSlug: string,
): Promise<{ status: string; company_id: string; message: string }> {
  return fetcher(`/api/v1/engine/companies/${encodeURIComponent(companyId)}/refresh?workspace_slug=${encodeURIComponent(workspaceSlug)}`, {
    method: 'POST',
  });
}

/** Latest refresh status for a company. */
export async function getCompanyRefreshStatus(
  companyId: string,
  workspaceSlug: string,
): Promise<{
  company_id: string;
  status: string;
  last_attempted_at: string | null;
  last_successful_at: string | null;
  research_timestamp: string | null;
  error_message: string | null;
  is_running: boolean;
}> {
  return fetcher(`/api/v1/engine/companies/${encodeURIComponent(companyId)}/refresh-status?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

/** Workspace demo-readiness report. */
export async function getDemoReadiness(workspaceSlug: string): Promise<DemoReadiness> {
  return fetcher(`/api/v1/engine/demo-readiness?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

/** Provider availability, capabilities and the active qualification policy. */
export async function getProviderOverview(
  workspaceSlug: string,
): Promise<ProviderOverview> {
  return fetcher(`/api/v1/engine/providers?workspace_slug=${encodeURIComponent(workspaceSlug)}`);
}

export async function getExportPreview(
  batchId: string,
  workspaceSlug: string,
  includeAll?: boolean,
): Promise<{ batch_id: string; count: number; rows: LeadExportRow[] }> {
  const q = new URLSearchParams({ workspace_slug: workspaceSlug });
  if (includeAll) q.set('include_all', 'true');
  return fetcher(`/api/v1/exports/preview/${batchId}?${q.toString()}`);
}

// Auth
export async function getAuthStatus(): Promise<AuthStatus> {
  return fetcher<AuthStatus>('/api/v1/auth/status');
}

export async function getAuthMe(workspaceSlug?: string): Promise<AuthSession> {
  const q = workspaceSlug ? `?workspace_slug=${encodeURIComponent(workspaceSlug)}` : '';
  return fetcher<AuthSession>(`/api/v1/auth/me${q}`);
}

export async function login(email: string, password: string): Promise<AuthSession> {
  return fetcher<AuthSession>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await fetcher<void>('/api/v1/auth/logout', { method: 'POST' });
}

// Workspace helper to discover current workspace
export async function getCurrentWorkspace(slug: string): Promise<{
  slug: string;
  profiles: ClientProfile[];
  icps: ICPProfile[];
  batches: ProspectBatch[];
}> {
  const profiles = await getClientProfiles(slug);
  const icps = await getICPProfiles(slug);  const batches = await getBatches(slug);
  return {
    slug,
    profiles,
    icps,
    batches: batches.items || [],
  };
}


