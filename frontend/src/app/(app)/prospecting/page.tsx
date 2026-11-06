'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getBatches, getICPProfiles, getClientProfiles, createBatch, ApiError } from '@/lib/api';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input, Label, Select } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { useToast } from '@/components/ui/toast';
import { SkeletonTable, SkeletonCard } from '@/components/ui/skeleton';
import { useLatestBatch, useBatchPoll, WORKSPACE_SLUG } from '@/lib/hooks/useApi';
import { STAGE_LABELS, STAGE_DESCRIPTIONS, type ProspectBatch, type ProspectBatchCreate, type BatchStage } from '@/lib/types';
import { cn, formatDate } from '@/lib/utils';
import { Play, CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react';
import type { ClientProfile, ICPProfile } from '@/lib/types';

const STAGE_ORDER: BatchStage[] = [
  'configured',
  'discovering_companies',
  'researching_companies',
  'discovering_decision_makers',
  'enriching_contacts',
  'identifying_problems',
  'matching_solutions',
  'qualifying',
  'completed',
];

export default function ProspectingPage() {
  const toast = useToast();
  const { batch: latestBatch, loading: batchLoading, refresh: refreshBatches } = useLatestBatch();

  // Creation form state
  const [showForm, setShowForm] = useState(false);
  const [prospectCount, setProspectCount] = useState('20');
  const [selectedIcpId, setSelectedIcpId] = useState<string | null>(null);
  const [selectedClientProfileId, setSelectedClientProfileId] = useState<string | null>(null);
  const [batchName, setBatchName] = useState('');
  const [icps, setIcps] = useState<ICPProfile[]>([]);
  const [clients, setClients] = useState<ClientProfile[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Active batch poll state
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const { batch, loading, error, start: startPoll, stop: stopPoll } = useBatchPoll({
    onComplete: (completed) => {
      toast.addToast({ type: 'success', title: 'Prospecting complete', description: `${completed.total_qualified} prospects qualified.` });
      refreshBatches();
    },
    onError: (err) => {
      toast.addToast({ type: 'error', title: 'Prospecting failed', description: err });
    },
    intervalMs: 2000,
  });

  // Load ICPs and client profiles for the creation form, plus recent batches.
  useEffect(() => {
    let cancelled = false;
    Promise.all([getICPProfiles(WORKSPACE_SLUG), getClientProfiles(WORKSPACE_SLUG)])
      .then(([icpData, clientData]) => {
        if (cancelled) return;
        setIcps(icpData || []);
        setClients(clientData || []);
      })
      .catch(() => {
        // Non-fatal: the form still shows a helpful empty state.
      });
    refreshBatches();
    return () => { cancelled = true; };
  }, [refreshBatches]);

  const isFormValid = () => {
    const count = parseInt(prospectCount, 10);
    return (
      prospectCount.trim() &&
      !isNaN(count) &&
      count >= 1 &&
      count <= 100 &&
      selectedIcpId &&
      batchName.trim()
    );
  };

  const handleCreateBatch = async () => {
    if (!isFormValid()) {
      toast.addToast({ type: 'error', title: 'Please complete the form' });
      return;
    }

    setSubmitting(true);
    setFormError(null);
    try {
      const count = parseInt(prospectCount, 10);
      if (!selectedIcpId) {
        setSubmitting(false);
        return;
      }
      const payload: ProspectBatchCreate = {
        workspace_id: WORKSPACE_SLUG,
        icp_profile_id: selectedIcpId,
        client_profile_id: selectedClientProfileId,
        name: batchName.trim(),
        requested_prospect_count: count,
      };
      const data: ProspectBatch = await createBatch(payload);

      setActiveBatchId(data.id);
      startPoll(data.id);
      toast.addToast({ type: 'success', title: 'Batch created', description: 'Pipeline starting…' });
      setShowForm(false);
      setSubmitting(false);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to create batch';
      setFormError(msg);
      toast.addToast({ type: 'error', title: 'Batch creation failed', description: msg });
      setSubmitting(false);
    }
  };

  const handleCancelForm = () => {
    setShowForm(false);
    setFormError(null);
    setSubmitting(false);
  };

  const closeActiveBatch = () => {
    setActiveBatchId(null);
    stopPoll();
  };

  if (batchLoading) {
    return (
      <div className="flex flex-col min-h-screen">
        <TopBar title="Prospecting" subtitle="Synthetic demo prospect discovery pipeline" breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Prospecting' }]} />
        <div className="p-6 space-y-6 max-w-5xl">
          <SkeletonCard />
          <SkeletonTable rows={6} cols={5} />
        </div>
      </div>
    );
  }

  const activeBatch = activeBatchId ? batch : null;

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Prospecting"
        subtitle="Synthetic demo prospect discovery pipeline"
        breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Prospecting' }]}
        actions={
          <div className="flex items-center gap-2">
            {activeBatch ? (
              <Button variant="outline" size="sm" onClick={closeActiveBatch}>
                <XCircle className="h-4 w-4 mr-1.5" />
                Close
              </Button>
            ) : (
              <Button onClick={() => setShowForm(true)}>
                <Play className="h-4 w-4 mr-1.5" />
                Start Prospecting
              </Button>
            )}
          </div>
        }
      />

      <div className="p-6 space-y-6 max-w-5xl">
        <div role="note" className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-800">
          Synthetic demo data only. Company details and research are illustrative, not verified or live.
        </div>

        {/* Active batch view */}
        {activeBatch ? (
          <ActiveBatchView
            batch={activeBatch}
            error={error}
            onClose={closeActiveBatch}
            stageOrder={STAGE_ORDER}
          />
        ) : (
          <>
            {/* Latest batch summary */}
            {latestBatch && (
              <Card className="border-l-4 border-l-primary">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Latest Batch</p>
                      <p className="text-base font-semibold mt-0.5">{latestBatch.name}</p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <Badge variant={latestBatch.status === 'completed' ? 'success' : latestBatch.status === 'failed' ? 'destructive' : 'info'}>
                          {latestBatch.status}
                        </Badge>
                        <span className="text-sm text-muted-foreground">{formatDate(latestBatch.created_at)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <p className="text-2xl font-semibold">{latestBatch.total_qualified}</p>
                        <p className="text-xs text-muted-foreground">qualified</p>
                      </div>

                      <Link href={`/prospects?batch=${latestBatch.id}`} className="ml-3">
                        View prospects
                      </Link>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Empty state */}
            {!latestBatch && (
              <Card>
                <CardContent className="py-12 text-center">
                  <div className="flex h-12 w-12 mx-auto rounded-full bg-muted items-center justify-center mb-4">
                    <Play className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">No prospecting batches yet</p>
                  <p className="text-xs text-muted-foreground mt-1">Start a synthetic demo run to generate illustrative prospects and qualification results.</p>
                  <Button className="mt-4" onClick={() => setShowForm(true)}>
                    <Play className="h-4 w-4 mr-1.5" />
                    Start Prospecting
                  </Button>
                </CardContent>
              </Card>
            )}
          </>
        )}

      </div>        {/* Creation modal */}
      <Modal
        open={showForm || submitting}
        onClose={handleCancelForm}
        title="Start a Prospecting Batch"
        description="Configure a new prospect discovery run using your ICP profile."
        className="max-w-lg"
      >
        <form onSubmit={e => { e.preventDefault(); handleCreateBatch(); }} className="space-y-4">
          {formError && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700 border border-red-200">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium">Could not create batch</p>
                <p className="text-red-600/80 mt-0.5">{formError}</p>
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="batch-name">Batch Name <span className="text-red-500">*</span></Label>
            <Input
              id="batch-name"
              value={batchName}
              onChange={e => setBatchName(e.target.value)}
              placeholder="Q1 Enterprise Campaign"
              maxLength={60}
              disabled={submitting}
            />
            <p className="text-xs text-muted-foreground">A descriptive name for this prospecting run.</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="icp-select">ICP Profile <span className="text-red-500">*</span></Label>
            <Select
              id="icp-select"
              value={selectedIcpId ?? ''}
              onChange={e => setSelectedIcpId(e.target.value)}
              disabled={submitting}
            >
              <option value="">Select an ICP profile…</option>
              {icps.map(icp => (
                <option key={icp.id} value={icp.id}>
                  {icp.name} — {icp.max_prospects} prospects max
                </option>
              ))}
            </Select>
            {icps.length === 0 && (
              <p className="text-xs text-muted-foreground mt-1">No ICP profiles available. Create one first.</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="client-select">Client Profile (optional)</Label>
            <Select
              id="client-select"
              value={selectedClientProfileId ?? ''}
              onChange={e => setSelectedClientProfileId(e.target.value)}
              disabled={submitting}
            >
              <option value="">None — use default target audience</option>
              {clients.map(c => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">Associates this batch with a specific client profile for context.</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="prospect-count">Number of Prospects</Label>
            <div className="flex items-center gap-3">
              <Input
                id="prospect-count"
                type="number"
                min="1"
                max="100"
                value={prospectCount}
                onChange={e => setProspectCount(e.target.value)}
                disabled={submitting}
                className="w-24"
              />
              <span className="text-sm text-muted-foreground">
                (max 100 per batch)
              </span>
            </div>
            <p className="text-xs text-muted-foreground">How many prospects the pipeline should discover and qualify.</p>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="ghost" onClick={handleCancelForm} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !isFormValid()}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  Creating…
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-1.5" />
                  Start Prospecting
                </>
              )}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function ActiveBatchView({
  batch,
  error,
  onClose,
  stageOrder,
}: {
  batch: ProspectBatch;
  error: string | null;
  onClose: () => void;
  stageOrder: BatchStage[];
}) {
  const currentStageIndex = batch.current_stage
    ? stageOrder.indexOf(batch.current_stage)
    : stageOrder.indexOf('configured');

  const progressPct = batch.status === 'completed'
    ? 100
    : currentStageIndex >= 0
    ? (currentStageIndex / (stageOrder.length - 1)) * 100
    : 0;

  const stages = stageOrder.map((stage, idx) => {
    const isCompleted = idx < currentStageIndex || batch.status === 'completed';
    const isCurrent = idx === currentStageIndex && batch.status !== 'completed';
    const isFailed = error !== null && idx === currentStageIndex;
    return { stage, idx, label: STAGE_LABELS[stage], description: STAGE_DESCRIPTIONS[stage], isCompleted, isCurrent, isFailed };
  });

  return (
    <div className="space-y-6">
      {/* Batch header */}
      <Card className="border-l-4 border-l-primary">
        <CardContent className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Active Batch</p>
              <p className="text-lg font-semibold mt-0.5">{batch.name}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <Badge variant={batch.status === 'completed' ? 'success' : batch.status === 'failed' ? 'destructive' : 'info'}>
                  {batch.status}
                </Badge>
                {batch.current_stage && (
                  <span className="text-sm text-muted-foreground">
                    Stage: {STAGE_LABELS[batch.current_stage]}
                  </span>
                )}
                <span className="text-sm text-muted-foreground">{formatDate(batch.created_at)}</span>
              </div>
              {error && (
                <p className="text-sm text-red-600 mt-1">{error}</p>
              )}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{batch.total_qualified}</span>
                <span>/ {batch.requested_prospect_count} qualified</span>
              </div>
              <Button variant="outline" size="sm" onClick={onClose}>
                <XCircle className="h-4 w-4 mr-1.5" />
                Close
              </Button>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Progress</span>
              <span>{Math.round(progressPct)}%</span>
            </div>
            <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-700 ease-out"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stage timeline */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Pipeline Stages</CardTitle>
          <CardDescription>The synthetic demo pipeline moves through these stages automatically.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {stages.map((s, idx) => {
              const Icon = s.isCompleted
                ? CheckCircle2
                : s.isFailed
                ? XCircle
                : s.isCurrent
                ? Loader2
                : null;

              return (
                <div
                  key={s.stage}
                  className={cn(
                    'flex items-start gap-4 px-5 py-4',
                    idx < stages.length - 1 && 'border-b border-border/60',
                  )}
                >
                  {/* Stage number / icon */}
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors">
                    {s.isCompleted && (
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-green-500 text-white">
                        <CheckCircle2 className="h-5 w-5" />
                      </div>
                    )}
                    {s.isFailed && (
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-red-500 text-white">
                        <XCircle className="h-5 w-5" />
                      </div>
                    )}
                    {s.isCurrent && (
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-white">
                        <Loader2 className="h-5 w-5 animate-spin" />
                      </div>
                    )}
                    {!s.isCompleted && !s.isFailed && !s.isCurrent && (
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted">
                        <span className="text-xs font-semibold text-muted-foreground">{idx + 1}</span>
                      </div>
                    )}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        'font-medium',
                        !s.isCompleted && 'text-muted-foreground',
                        s.isCurrent && 'text-primary',
                      )}>
                        {s.label}
                      </span>
                      {s.isCompleted && (
                        <Badge variant="success" className="text-[10px] px-1.5 py-0">Done</Badge>
                      )}
                      {s.isFailed && (
                        <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Failed</Badge>
                      )}
                      {s.isCurrent && !s.isCompleted && !s.isFailed && (
                        <Badge variant="info" className="text-[10px] px-1.5 py-0">In progress</Badge>
                      )}
                    </div>
                    <p className={cn(
                      'text-sm mt-0.5',
                      !s.isCompleted && 'text-muted-foreground',
                    )}>
                      {s.description}
                    </p>
                  </div>

                  {/* Stage connector */}
                  {idx < stages.length - 1 && (
                    <div className="flex flex-col items-center">
                      <div className={cn(
                        'h-0.5 w-full transition-colors',
                        s.isCompleted ? 'bg-green-400' : 'bg-border',
                      )} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Discovered" value={batch.total_discovered} color="primary" />
        <StatCard label="Researched" value={batch.total_researched} color="info" />
        <StatCard label="Enriched" value={batch.total_enriched} color="warning" />
        <StatCard label="Qualified" value={batch.total_qualified} color="success" />
      </div>

      {/* Source mode */}
      <Card className="border-border/50">
        <CardContent className="py-3 px-5 flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
            <svg className="h-4 w-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" />
              <path d="M12 6v6l4 2" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium">Source Mode: {batch.source_mode}</p>
            <p className="text-xs text-muted-foreground">
              {batch.source_mode === 'demo'
                ? 'Synthetic demo data generated by the prospecting engine. No real profiles or emails are used.'
                : 'Configured data source mode.'}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    primary: 'bg-primary/10 text-primary',
    info: 'bg-blue-50 text-blue-600',
    warning: 'bg-amber-50 text-amber-600',
    success: 'bg-green-50 text-green-600',
  };
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2">
          <div className={cn('rounded-lg p-1.5', colorMap[color])}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="text-right">
            <p className="text-2xl font-semibold">{value}</p>
            <p className="text-xs text-muted-foreground">{label}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
