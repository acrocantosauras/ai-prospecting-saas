'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getHealth, getBatches, getProspects, getCurrentWorkspace, ApiError } from '@/lib/api';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { DashboardStats } from '@/components/dashboard/dashboard-stats';
import { SkeletonPage } from '@/components/ui/skeleton';
import { WORKSPACE_SLUG } from '@/lib/hooks/useApi';
import type { Prospect, ProspectBatch } from '@/lib/types';

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [batches, setBatches] = useState<ProspectBatch[]>([]);
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [total, setTotal] = useState(0);
  const [health, setHealth] = useState<{ status: string } | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const healthData = await getHealth();
        setHealth(healthData);
        const workspaceData = await getCurrentWorkspace(WORKSPACE_SLUG);
        setBatches(workspaceData.batches);
        const prospectData = await getProspects({
          workspaceSlug: WORKSPACE_SLUG,
          pageSize: 100,
          sortBy: 'created_at',
          sortOrder: 'desc',
        });
        setProspects(prospectData.items || []);
        setTotal(prospectData.total || 0);
      } catch (e) {
        if (e instanceof ApiError) {
          setError(`Backend unavailable (${e.status}). ${e.message}`);
        } else {
          setError('Failed to load dashboard data.');
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const qualified = prospects.filter(p => p.is_ready_for_outreach === true).length;
  const companies = new Set<string>();
  const dmSet = new Set<string>();
  prospects.forEach(p => {
    if (p.company_name) companies.add(p.company_name);
    if (p.decision_maker_id) dmSet.add(p.decision_maker_id);
  });

  // Email breakdown based on the recorded confidence label, not a guess.
  const emailVerified = prospects.filter(p => p.email && /verified|deliverable/i.test(p.research_confidence ?? '')).length;
  const emailUnavailable = prospects.filter(p => !p.email).length;
  const emailUnverified = Math.max(0, prospects.length - emailVerified - emailUnavailable);

  if (loading) {
    return (
      <div className="flex flex-col min-h-screen">
        <SkeletonPage />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col min-h-screen">
        <TopBar title="Overview" subtitle="AI Prospecting Platform" />
        <div className="p-6 space-y-4">
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex items-start gap-4">
              <div className="rounded-full bg-red-100 p-2">
                <svg className="h-5 w-5 text-red-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 8v4M12 16h.01" strokeLinecap="round" />
                </svg>
              </div>
              <div className="flex-1">
                <h2 className="text-base font-semibold text-red-700">Backend unavailable</h2>
                <p className="text-sm text-red-600/80 mt-1">{error}</p>
                <p className="text-xs text-red-600/60 mt-2">Make sure the FastAPI backend is running at http://localhost:8000</p>
              </div>
            </div>
          </div>
          <Button
            variant="outline"
            onClick={() => window.location.reload()}
            type="button"
          >
            Retry connection
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Overview"
        subtitle={`${WORKSPACE_SLUG === 'demo' ? 'Demo Workspace — Northbridge Growth Partners' : WORKSPACE_SLUG}`}
        actions={
          <Button onClick={() => router.push('/prospecting')}>
            Start Prospecting
          </Button>
        }
      />
      <div className="p-6 space-y-6 max-w-7xl">
        {/* Health indicator */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <div className={`h-2 w-2 rounded-full ${health?.status === 'ok' ? 'bg-green-500' : 'bg-red-400'}`} />
          Backend: {health?.status === 'ok' ? 'Connected' : 'Unavailable'} · {batches.length} batch{batches.length !== 1 ? 'es' : ''} · {total} prospect{total !== 1 ? 's' : ''}
        </div>

        <DashboardStats
          totalProspects={total}
          qualifiedProspects={qualified}
          companiesDiscovered={companies.size}
          decisionMakers={dmSet.size}
          emailBreakdown={{
            verified: emailVerified,
            unverified: emailUnverified,
            unavailable: emailUnavailable,
          }}
          batches={batches}
          recentProspects={prospects}
          loading={false}
        />
      </div>
    </div>
  );
}
