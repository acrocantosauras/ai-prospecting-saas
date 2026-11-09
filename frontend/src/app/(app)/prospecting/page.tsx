'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  getBatches,
  getICPProfiles,
  getClientProfiles,
  createBatch,
  getBatchProgress,
  getQualifications,
  ApiError,
} from '@/lib/api';
import { useWorkspaceSlug } from '@/lib/hooks/useAuth';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input, Label, Select } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { useToast } from '@/components/ui/toast';
import { SkeletonTable, SkeletonCard } from '@/components/ui/skeleton';
import { useLatestBatch, useBatchPoll } from '@/lib/hooks/useApi';
import { STAGE_LABELS, STAGE_DESCRIPTIONS, type ProspectBatch, type ProspectBatchCreate, type BatchStage } from '@/lib/types';
import { cn, formatDate } from '@/lib/utils';
import { Play, CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react';
import type { ClientProfile, ICPProfile } from '@/lib/types';
import { BatchExecutionView } from '@/components/batch/BatchExecutionView';

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

  // Active batch engine state
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [engineLoading, setEngineLoading] = useState(false);
  const { batch: polledBatch, loading: polledLoading, error: polledError, start: startPoll, stop: stopPoll } = useBatchPoll({
    onComplete: (completed) => {
      toast.addToast({ type: 'success', title: 'Prospecting complete', description: `${completed.total_qualified} prospects qualified.` });
      refreshBatches();
    },
    onError: (err) => {
      toast.addToast({ type: 'error', title: 'Prospecting failed', description: err });
    },
    intervalMs: 3000,
  });

  const slug = useWorkspaceSlug();

  // Load ICPs and client profiles for the creation form, plus recent batches.
  useEffect(() => {
    let cancelled = false;
    Promise.all([getICPProfiles(slug), getClientProfiles(slug)])
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

  // Refresh engine progress when active batch changes  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => {
    if (!activeBatchId || !slug) return;
    let cancelled = false;
    const id = setInterval(async () => {
      if (cancelled || !slug) return;
      try {
        const data = await getBatchProgress(activeBatchId, slug);
        if (!cancelled) setEngineLoading(false);
        if (data.batch.status === 'completed' || data.batch.status === 'failed') {
          clearInterval(id);
          if (data.batch.status === 'completed') {
            toast.addToast({ type: 'success', title: 'Prospecting complete', description: `${data.batch.total_qualified} prospects qualified.` });
          } else {
            toast.addToast({ type: 'error', title: 'Prospecting failed', description: data.batch.error_message || 'Pipeline failed.' });
          }
          refreshBatches();
        }
      } catch (e) {
        // Silently retry
      }
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeBatchId, slug, refreshBatches]);

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
        workspace_id: slug,
        icp_profile_id: selectedIcpId,
        client_profile_id: selectedClientProfileId,
        name: batchName.trim(),
        requested_prospect_count: count,
      };
      const data: ProspectBatch = await createBatch(payload);

      setActiveBatchId(data.id);
      startPoll(data.id);
      setEngineLoading(true);
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
    stopPoll?.();
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

  const activeBatch = activeBatchId ? polledBatch : null;

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
      />      <div className="p-6 space-y-6 max-w-5xl">
        <div role="note" className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-800">
          Synthetic demo data only. Company details and research are illustrative, not verified or live.
        </div>

        {/* Active batch view — real engine progress */}
        {activeBatchId ? (
          <BatchExecutionView
            batchId={activeBatchId}
            onClose={closeActiveBatch}
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
        )}</div>        {/* Creation modal */}
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
