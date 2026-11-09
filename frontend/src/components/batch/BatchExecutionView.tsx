'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import {
  getBatchProgress,
  cancelBatch,
  getQualifications,
  ApiError,
} from '@/lib/api';
import { useToast } from '@/components/ui/toast';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn, formatDate } from '@/lib/utils';
import {
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Clock,
  DollarSign,
  Building2,
  Users,
  Mail,
  Target,
  X,
  Play,
} from 'lucide-react';
import type {
  EngineBatchSnapshot,
  StageRun,
  QualificationDecision,
  BatchStage,
} from '@/lib/types';

type UsageState = {
  total_cost_usd: number;
  total_calls: number;
};
import { STAGE_LABELS } from '@/lib/types';

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

interface Props {
  batchId: string;
  onClose: () => void;
}

export function BatchExecutionView({ batchId, onClose }: Props) {
  const { selectedWorkspaceSlug } = useAuth();
  const toast = useToast();
  const [snapshot, setSnapshot] = useState<EngineBatchSnapshot | null>(null);
  const [stages, setStages] = useState<StageRun[]>([]);
  const [progress, setProgress] = useState(0);
  const [usage, setUsage] = useState<UsageState | null>(null);
  const [counts, setCounts] = useState<{
    qualified_companies: number;
    rejected_companies: number;
    recheck_companies: number;
  }>({ qualified_companies: 0, rejected_companies: 0, recheck_companies: 0 });
  const [qualifications, setQualifications] = useState<QualificationDecision[]>([]);
  const [loading, setLoading] = useState(true);
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slug = selectedWorkspaceSlug ?? '';

  const refresh = useCallback(async () => {
    if (!slug) return;
    try {
      setError(null);
      const data = await getBatchProgress(batchId, slug);
      setSnapshot(data.batch);
      setStages(data.stages);
      setProgress(Math.round(data.progress_percent));
      setUsage(data.usage ?? null);
      setCounts({
        qualified_companies: data.qualified_companies,
        rejected_companies: data.rejected_companies,
        recheck_companies: data.recheck_companies,
      });
      // Only refresh qualifications on terminal states
      if (data.batch.status === 'completed' || data.batch.status === 'failed') {
        const qs = await getQualifications(batchId, slug, { limit: 200 });
        setQualifications(qs);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load batch progress');
    }
  }, [slug, batchId]);

  useEffect(() => {
    let cancelled = false;
    const id = setInterval(() => {
      if (cancelled) return;
      refresh().catch(() => {});
    }, 3000);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh().catch(() => {});
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [refresh]);

  const handleCancel = async () => {
    if (!slug) return;
    setCanceling(true);
    try {
      await cancelBatch(batchId, slug);
      toast.addToast({ type: 'info', title: 'Cancellation requested', description: 'The batch will stop as soon as possible.' });
      await refresh();
    } catch (e) {
      toast.addToast({ type: 'error', title: 'Cancel failed', description: e instanceof ApiError ? e.message : 'Could not cancel batch' });
    } finally {
      setCanceling(false);
    }
  };

  const snapshotData = snapshot;
  if (loading && !snapshotData) {
    return (
      <div className="space-y-6">
        <Skeleton height={180} className="rounded-lg" />
        <Skeleton height={400} className="rounded-lg" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} height={120} className="rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (error && !snapshotData) {
    return (
      <Card className="border-red-200">
        <CardContent className="py-12 text-center">
          <AlertTriangle className="h-10 w-10 mx-auto text-red-500 mb-4" />
          <p className="text-sm font-medium text-red-700">Could not load batch</p>
          <p className="text-xs text-red-600/80 mt-1">{error}</p>
          <Button className="mt-4" onClick={refresh}>Retry</Button>
        </CardContent>
      </Card>
    );
  }

  const batch = snapshotData!;
  const currentStageIndex = batch.current_stage
    ? STAGE_ORDER.indexOf(batch.current_stage as BatchStage)
    : STAGE_ORDER.indexOf('configured');

  const stageRuns: Array<{
    stage: BatchStage;
    idx: number;
    label: string;
    isCompleted: boolean;
    isCurrent: boolean;
    isFailed: boolean;
    run: StageRun | undefined;
  }> = STAGE_ORDER.map((stage, idx) => {
    const run = stages.find(r => r.stage === stage);
    const isCompleted =
      idx < currentStageIndex ||
      (stage === 'completed' && batch.status === 'completed') ||
      (stage !== 'completed' &&
        stages.some(r => r.stage === stage && r.status === 'completed'));
    const isCurrent =
      idx === currentStageIndex && batch.status !== 'completed' && batch.status !== 'failed';
    const isFailed = run?.status === 'failed' || batch.status === 'failed';
    return { stage, idx, label: STAGE_LABELS[stage as BatchStage], isCompleted, isCurrent, isFailed, run };
  });

  const canCancel = batch.status === 'pending' || batch.status === 'running';

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="border-l-4 border-l-primary">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Active Batch</p>
                {batch.status === 'completed' && (
                  <Badge variant="success">Completed</Badge>
                )}
                {batch.status === 'failed' && (
                  <Badge variant="destructive">Failed</Badge>
                )}
                {batch.status === 'running' && (
                  <Badge variant="info">Running</Badge>
                )}
                {batch.status === 'pending' && (
                  <Badge variant="secondary">Pending</Badge>
                )}
              </div>
              <p className="text-lg font-semibold mt-1">{batch.name}</p>
              <div className="flex flex-wrap items-center gap-3 mt-1.5 text-sm text-muted-foreground">                  <span className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    {formatDate(batch.created_at)}
                  </span>
                {batch.source_mode && (
                  <span className="flex items-center gap-1">
                    <Play className="h-3.5 w-3.5" />
                    {batch.source_mode}
                  </span>
                )}
                {batch.current_stage && batch.status !== 'completed' && batch.status !== 'failed' && (
                  <span className="flex items-center gap-1">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {STAGE_LABELS[batch.current_stage as BatchStage]}
                  </span>
                )}
              </div>
              {batch.error_message && (
                <p className="text-sm text-red-600 mt-1">{batch.error_message}</p>
              )}
              {error && !batch.error_message && (
                <p className="text-sm text-red-600 mt-1">{error}</p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {canCancel && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCancel}
                  disabled={canceling}
                >
                  {canceling ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      Canceling…
                    </>
                  ) : (
                    <>
                      <X className="h-4 w-4 mr-1.5" />
                      Cancel batch
                    </>
                  )}
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="h-4 w-4 mr-1.5" />
                Close
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Progress bar */}
      <Card className="border-border/50">
        <CardContent className="p-5">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="text-muted-foreground">Progress</span>
            <span className="font-medium">{progress}%</span>
          </div>
          <div className="h-2.5 w-full bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full transition-all duration-700 ease-out rounded-full',
                batch.status === 'completed' ? 'bg-green-500' : batch.status === 'failed' ? 'bg-red-500' : 'bg-primary',
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Stage timeline */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Pipeline Stages</CardTitle>
          <CardDescription>Stage-by-stage progress from the prospecting engine.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {stageRuns.map((s) => {
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
                    s.idx < stageRuns.length - 1 && 'border-b border-border/60',
                  )}
                >
                  {/* Icon */}
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
                        <span className="text-xs font-semibold text-muted-foreground">{s.idx + 1}</span>
                      </div>
                    )}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          'font-medium',
                          !s.isCompleted && 'text-muted-foreground',
                          s.isCurrent && 'text-primary',
                        )}
                      >
                        {s.label}
                      </span>
                      {s.isCompleted && !s.isFailed && (
                        <Badge variant="success" className="text-[10px] px-1.5 py-0">Done</Badge>
                      )}
                      {s.isFailed && (
                        <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Failed</Badge>
                      )}
                      {s.isCurrent && !s.isCompleted && !s.isFailed && (
                        <Badge variant="info" className="text-[10px] px-1.5 py-0">In progress</Badge>
                      )}
                    </div>
                    {s.run?.detail && (
                      <p className="text-xs text-muted-foreground mt-0.5">{s.run.detail}</p>
                    )}
                    {s.run?.status && !s.isCompleted && !s.isFailed && !s.isCurrent && (
                      <p className="text-xs text-muted-foreground mt-0.5">Status: {s.run.status}</p>
                    )}
                  </div>

                  {/* Connector */}
                  {s.idx < stageRuns.length - 1 && (
                    <div className="flex flex-col items-center">
                      <div
                        className={cn(
                          'h-0.5 w-full transition-colors',
                          s.isCompleted ? 'bg-green-400' : 'bg-border',
                        )}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Discovered"
          value={batch.total_discovered}
          icon={<Building2 className="h-4 w-4" />}
          color="primary"
        />
        <StatCard
          label="Researched"
          value={batch.total_researched}
          icon={<Target className="h-4 w-4" />}
          color="info"
        />
        <StatCard
          label="Qualified"
          value={batch.total_qualified}
          icon={<Users className="h-4 w-4" />}
          color="success"
        />
        <StatCard
          label="Enriched"
          value={batch.total_enriched}
          icon={<Mail className="h-4 w-4" />}
          color="warning"
        />
      </div>

      {/* Counts */}
      {(counts.qualified_companies > 0 || counts.rejected_companies > 0 || counts.recheck_companies > 0) && (
        <Card className="border-border/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Company Status</CardTitle>
            <CardDescription>Companies at each stage of the qualification pipeline.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              <div className="rounded-lg bg-green-50 p-3 text-center border border-green-100">
                <p className="text-2xl font-semibold text-green-700">{counts.qualified_companies}</p>
                <p className="text-xs text-green-600 mt-0.5">Qualified companies</p>
              </div>
              <div className="rounded-lg bg-red-50 p-3 text-center border border-red-100">
                <p className="text-2xl font-semibold text-red-700">{counts.rejected_companies}</p>
                <p className="text-xs text-red-600 mt-0.5">Rejected companies</p>
              </div>
              <div className="rounded-lg bg-amber-50 p-3 text-center border border-amber-100">
                <p className="text-2xl font-semibold text-amber-700">{counts.recheck_companies}</p>
                <p className="text-xs text-amber-600 mt-0.5">Recheck needed</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Provider usage */}
      {usage && (
        <Card className="border-border/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              Provider Usage
            </CardTitle>
            <CardDescription>Measured provider calls and derived costs.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Total calls</p>
                <p className="text-xl font-semibold mt-0.5">{usage.total_calls}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Total cost</p>
                <p className="text-xl font-semibold mt-0.5">
                  ${usage.total_cost_usd.toFixed(4)}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {usage.total_cost_usd === 0 ? 'No paid provider calls' : 'Derived from provider rates'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Qualifications */}
      {qualifications.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="h-4 w-4 text-muted-foreground" />
              Qualification Decisions
            </CardTitle>
            <CardDescription>
              {qualifications.filter(q => q.status === 'qualified').length} qualified,{' '}
              {qualifications.filter(q => q.status === 'rejected').length} rejected
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {qualifications.slice(0, 50).map((q) => (
                <div key={q.id} className="py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={q.status === 'qualified' ? 'success' : q.status === 'rejected' ? 'destructive' : 'secondary'}
                      >
                        {q.status}
                      </Badge>
                      {q.scope && (
                        <span className="text-xs text-muted-foreground">{q.scope}</span>
                      )}
                    </div>
                    {q.reasons && (
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">{String(q.reasons)}</p>
                    )}
                  </div>
                  {q.score !== undefined && q.score !== null && (
                    <span className="text-sm font-medium shrink-0">
                      {Number(q.score).toFixed(1)}
                    </span>
                  )}
                </div>
              ))}
              {qualifications.length > 50 && (
                <div className="py-3 text-center text-xs text-muted-foreground">
                  Showing 50 of {qualifications.length} decisions
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Source mode notice */}
      <Card className="border-border/50">
        <CardContent className="py-3 px-5 flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 rounded-full bg-muted items-center justify-center">
            <Play className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <p className="text-sm font-medium">Source Mode: {batch.source_mode}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {batch.source_mode === 'demo'
                ? 'Synthetic demo data generated by the prospecting engine. No real profiles or emails are used in this mode.'
                : 'Configured data source mode. Real provider data requires API keys.'}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    primary: 'bg-primary/10 text-primary',
    info: 'bg-blue-50 text-blue-600',
    warning: 'bg-amber-50 text-amber-600',
    success: 'bg-green-50 text-green-600',
  };
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className={cn('rounded-lg p-2', colorMap[color])}>{icon}</div>
          <div className="text-right">
            <p className="text-2xl font-semibold">{value}</p>
            <p className="text-xs text-muted-foreground">{label}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
