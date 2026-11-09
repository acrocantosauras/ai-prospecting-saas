'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Suspense, useMemo, useState } from 'react';
import { getExportPreview, downloadCsv, ApiError } from '@/lib/api';
import { useWorkspaceSlug } from '@/lib/hooks/useAuth';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input, Select, Label } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { Pagination } from '@/components/ui/pagination';
import { SkeletonTable } from '@/components/ui/skeleton';
import { useProspectSearch } from '@/lib/hooks/useApi';
import { Avatar } from '@/components/ui/avatar';
import { formatDate, cn, formatScore, scoreColor, readinessLabel } from '@/lib/utils';
import { Search, X, Download, Filter, CheckCircle2, AlertCircle, ArrowUpDown, Building, Mail } from 'lucide-react';
import type { Prospect } from '@/lib/types';

export default function ProspectsPage() {
  return (
    <Suspense fallback={<div className="p-6"><SkeletonTable rows={8} cols={6} /></div>}>
      <ProspectsPageContent />
    </Suspense>
  );
}

function ProspectsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const toast = useToast();
  const slug = useWorkspaceSlug();

  const initialBatchId = searchParams.get('batch') || undefined;

  const {
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
    sortBy,
    setSortBy,
    sortOrder,
    setSortOrder,
    batchId,
    data,
    loading,
    error,
    fetch: refetch,
    resetPage,
  } = useProspectSearch({ initialBatchId, initialPage: 1, initialPageSize: 20 });

  const [showFilters, setShowFilters] = useState(false);
  const [exporting, setExporting] = useState(false);
  const activeBatchId = batchId;

  const allIndustries = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((p: Prospect) => p.industry).filter((v): v is string => Boolean(v)))),
    [data],
  );
  const allCountries = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((p: Prospect) => p.country).filter((v): v is string => Boolean(v)))),
    [data],
  );

  const handleExport = async () => {
    if (!activeBatchId) {
      toast.addToast({ type: 'error', title: 'No batch selected', description: 'Select a batch to export.' });
      return;
    }
    setExporting(true);
    try {
      const { batch_id, count } = await getExportPreview(activeBatchId, slug, true);
      if (count === 0) {
        toast.addToast({ type: 'warning', title: 'Nothing to export', description: 'No prospects available for export.' });
        return;
      }
      const csv = await downloadCsv(batch_id, slug, true);
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `prospects-${batch_id.slice(0, 8)}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.addToast({ type: 'success', title: 'CSV exported', description: `Downloaded ${count} prospect${count !== 1 ? 's' : ''} ready for Outreach.` });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Export failed';
      toast.addToast({ type: 'error', title: 'Export failed', description: msg });
    } finally {
      setExporting(false);
    }
  };

  const clearFilters = () => {
    setSearch('');
    setIndustry('');
    setCountry('');
    setMinScore(undefined);
    setMaxScore(undefined);
    setReady(null);
    resetPage();
  };

  const hasFilters = search || industry || country || minScore !== undefined || maxScore !== undefined || ready !== null;

  const sortOptions = [
    { value: 'created_at', label: 'Date added' },
    { value: 'qualification_score', label: 'Score (high → low)' },
    { value: 'first_name', label: 'Name A–Z' },
    { value: 'full_name', label: 'Full name' },
    { value: 'company_name', label: 'Company' },
  ];

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Prospects"
        subtitle={`${data?.total ?? 0} prospect${data?.total !== 1 ? 's' : ''}`}
        breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Prospects' }]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)}>
              <Filter className="h-4 w-4 mr-1.5" />
              Filters
              {hasFilters && <Badge variant="secondary" className="ml-1">{hasFilters ? 'on' : ''}</Badge>}
            </Button>
            {activeBatchId && (
              <Button onClick={handleExport} loading={exporting} disabled={exporting}>
                <Download className="h-4 w-4 mr-1.5" />
                Export CSV
              </Button>
            )}
          </div>
        }
      />

      <div className="p-6 space-y-4 max-w-7xl">
        {/* Search bar */}
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by name, company, email, role…"
              value={search}
              onChange={e => { setSearch(e.target.value); resetPage(); }}
              className="pl-9"
            />
            {search && (
              <button
                onClick={() => { setSearch(''); resetPage(); }}
                className="absolute right-3 top-1/2 -translate-y-1/2"
                aria-label="Clear search"
              >
                <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <Select
              value={sortBy}
              onChange={e => setSortBy(e.target.value)}
              className="w-40"
            >
              {sortOptions.map((opt, i) => (
                <option key={i} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            <Button
              variant="outline"
              onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              aria-label="Toggle sort direction"
            >
              <ArrowUpDown className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Filters panel */}
        {showFilters && (
          <Card className="border-border/50">
            <CardContent className="p-4">
              <div className="grid grid-cols-12 gap-4 items-end">
                <div className="col-span-3">
                  <Label className="mb-1.5 block text-xs font-medium text-muted-foreground">Industry</Label>
                  <Select
                    value={industry}
                    onChange={e => { setIndustry(e.target.value); resetPage(); }}
                  >
                    <option value="">All industries</option>
                    {allIndustries.map((ind: string) => (
                      <option key={ind} value={ind}>{ind}</option>
                    ))}
                  </Select>
                </div>
                <div className="col-span-3">
                  <Label className="mb-1.5 block text-xs font-medium text-muted-foreground">Country</Label>
                  <Select
                    value={country}
                    onChange={e => { setCountry(e.target.value); resetPage(); }}
                  >
                    <option value="">All countries</option>
                    {allCountries.map((c: string) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </Select>
                </div>
                <div className="col-span-2">
                  <Label className="mb-1.5 block text-xs font-medium text-muted-foreground">Min Score</Label>
                  <Input
                    type="number"
                    min="0"
                    max="100"
                    value={minScore ?? ''}
                    onChange={e => { setMinScore(e.target.value ? parseInt(e.target.value, 10) : undefined); resetPage(); }}
                    placeholder="0"
                  />
                </div>
                <div className="col-span-2">
                  <Label className="mb-1.5 block text-xs font-medium text-muted-foreground">Max Score</Label>
                  <Input
                    type="number"
                    min="0"
                    max="100"
                    value={maxScore ?? ''}
                    onChange={e => { setMaxScore(e.target.value ? parseInt(e.target.value, 10) : undefined); resetPage(); }}
                    placeholder="100"
                  />
                </div>
                <div className="col-span-2">
                  <Label className="mb-1.5 block text-xs font-medium text-muted-foreground">Outreach Ready</Label>
                  <Select
                    value={ready === null ? '__null__' : String(ready)}
                    onChange={e => { setReady(e.target.value === '__null__' ? null : e.target.value === 'true'); resetPage(); }}
                  >
                    <option value="__null__">All statuses</option>
                    <option value="true">Ready</option>
                    <option value="false">Not ready</option>
                  </Select>
                </div>
                <div className="col-span-12">
                  <div className="flex justify-between items-center pt-2 border-t border-border">
                    <p className="text-xs text-muted-foreground">
                      {hasFilters ? `Filtering ${data?.total ?? 0} prospect${data?.total !== 1 ? 's' : ''}` : `${data?.total ?? 0} prospects`}
                    </p>
                    {hasFilters && (
                      <Button variant="ghost" size="sm" onClick={clearFilters}>
                        Clear filters
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Results table */}
        {loading ? (
          <SkeletonTable rows={8} cols={6} />
        ) : error ? (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="flex h-12 w-12 mx-auto rounded-full bg-red-50 items-center justify-center mb-4">
                <AlertCircle className="h-6 w-6 text-red-500" />
              </div>
              <p className="text-sm font-medium text-red-700">Failed to load prospects</p>
              <p className="text-xs text-red-600/80 mt-1">{error}</p>
              <Button className="mt-4" onClick={refetch}>
                Retry
              </Button>
            </CardContent>
          </Card>
        ) : data && data.items.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="flex h-12 w-12 mx-auto rounded-full bg-muted items-center justify-center mb-4">
                <svg className="h-6 w-6 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="11" cy="11" r="8" />
                  <path d="M21 21l-4.35-4.35" />
                </svg>
              </div>
              <p className="text-sm font-medium">No prospects found</p>
              <p className="text-xs text-muted-foreground mt-1">
                {hasFilters
                  ? 'Try adjusting your filters or search terms.'
                  : 'Run a prospecting batch to discover prospects.'}
              </p>
              {!activeBatchId && (
                <Link href="/prospecting">
                  <Button className="mt-4">
                    Start Prospecting
                  </Button>
                </Link>
              )}
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              {data && (
                <>                {/* Mobile summary */}
                <div className="block sm:hidden p-4 border-b border-border space-y-3 bg-muted/30">
                  {data.items.slice(0, 5).map((p: Prospect) => (
                    <Link
                      key={p.id}
                      href={`/prospects/${p.id}`}
                      className="flex items-center gap-3 p-2 -mx-2 rounded-lg hover:bg-secondary transition-colors"
                    >
                      <Avatar name={p.full_name || 'Prospect'} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{p.full_name || 'Unnamed prospect'}</p>
                        <p className="text-xs text-muted-foreground truncate">{p.company_name} · {p.role || 'No role'}</p>
                      </div>
                      <Badge variant={p.is_ready_for_outreach ? 'success' : 'secondary'} className="shrink-0">
                        {readinessLabel(p.is_ready_for_outreach)}
                      </Badge>
                    </Link>
                  ))}
                  {data.items.length > 5 && (
                    <p className="text-center text-xs text-muted-foreground pt-2">
                      +{data.items.length - 5} more — open on desktop for full table
                    </p>
                  )}
                </div>

                {/* Desktop table */}
                <div className="hidden sm:block overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/50">
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3 w-10">#</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Prospect</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Company</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3 hidden md:table-cell">Role</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3 hidden lg:table-cell">Email</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3 w-20">Score</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3 w-24">Ready</th>
                        <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Added</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {data.items.map((p: Prospect, i: number) => (
                        <tr
                          key={p.id}
                          onClick={() => router.push(`/prospects/${p.id}`)}
                          className="cursor-pointer hover:bg-secondary/50 transition-colors"
                        >
                          <td className="px-4 py-3 text-muted-foreground">
                            {(page - 1) * pageSize + i + 1}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <Avatar name={p.full_name || 'Prospect'} size="sm" />
                              <div className="min-w-0">
                                <Link
                                  href={`/prospects/${p.id}`}
                                  className="block font-medium text-sm truncate max-w-[200px] sm:max-w-[260px] hover:text-primary hover:underline"
                                >
                                  {p.full_name || 'Unnamed prospect'}
                                </Link>
                                {p.role && !p.industry && !p.country ? (
                                  <p className="text-xs text-muted-foreground truncate">{p.role}</p>
                                ) : null}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2 min-w-0">
                              {p.company_name ? (
                                <>
                                  <Building className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                  <span className="text-sm truncate max-w-[180px] sm:max-w-[220px] font-medium">
                                    {p.company_name}
                                  </span>
                                </>
                              ) : (
                                <span className="text-sm text-muted-foreground italic">—</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            <span className="text-sm text-muted-foreground">{p.role || '—'}</span>
                          </td>
                          <td className="px-4 py-3 hidden lg:table-cell">
                            {p.email ? (
                              <a
                                href={`mailto:${p.email}`}
                                onClick={e => e.stopPropagation()}
                                className="text-sm text-primary hover:underline flex items-center gap-1"
                                title={p.email}
                                suppressHydrationWarning
                              >
                                <Mail className="h-3 w-3" />
                                <span className="truncate max-w-[200px] sm:max-w-[240px]">{p.email}</span>
                              </a>
                            ) : (
                              <span className="text-sm text-muted-foreground italic">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <span className={cn(
                              'inline-flex items-center font-medium text-sm',
                              formatScore(p.qualification_score) === '—'
                                ? 'text-muted-foreground'
                                : scoreColor(p.qualification_score),
                            )}>
                              {formatScore(p.qualification_score)}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5">
                              {p.is_ready_for_outreach === null ? (
                                <Badge variant="outline" className="text-[11px]">Pending</Badge>
                              ) : p.is_ready_for_outreach ? (
                                <Badge variant="success" className="text-[11px]">
                                  <CheckCircle2 className="h-3 w-3 mr-0.5" />
                                  Ready
                                </Badge>
                              ) : (
                                <Badge variant="secondary" className="text-[11px]">
                                  <AlertCircle className="h-3 w-3 mr-0.5" />
                                  Not ready
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                            {formatDate(p.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {data && data.total > 0 && (
                  <div className="flex items-center justify-between border-t border-border px-4 py-3">
                    <p className="text-xs text-muted-foreground">
                      Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, data.total)} of {data.total}
                    </p>
                    <Pagination
                      page={page}
                      totalPages={totalPages}
                      onPageChange={setPage}
                    />
                  </div>
                )}
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* Batch context */}
        {activeBatchId && (
          <Card className="border-l-4 border-l-primary">
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Filtered by batch</p>
                <p className="text-sm font-medium">Batch {activeBatchId.slice(0, 8)}…</p>
              </div>
              <Badge variant="info">In view</Badge>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
