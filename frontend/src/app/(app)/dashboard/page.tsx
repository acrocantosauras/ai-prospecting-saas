'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth, useWorkspaceSlug } from '@/lib/hooks/useAuth';
import { getHealth, getBatches, getProspects, getCurrentWorkspace, getDemoReadiness, logout as apiLogout, ApiError } from '@/lib/api';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DashboardStats } from '@/components/dashboard/dashboard-stats';
import { SkeletonPage } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/toast';
import { LogOut } from 'lucide-react';
import type { Prospect, ProspectBatch, DemoReadiness } from '@/lib/types';

export default function DashboardPage() {
  const router = useRouter();
  const { selectedWorkspaceSlug, selectedWorkspace, workspaces, setWorkspace, loading: authLoading } = useAuth();
  const slug = useWorkspaceSlug();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [batches, setBatches] = useState<ProspectBatch[]>([]);
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [total, setTotal] = useState(0);
  const [health, setHealth] = useState<{ status: string } | null>(null);
  const [demoReadiness, setDemoReadiness] = useState<DemoReadiness | null>(null);

  useEffect(() => {
    async function load() {
      if (!slug) {
        setLoading(false);
        return;
      }
      try {
        const healthData = await getHealth();
        setHealth(healthData);
        const workspaceData = await getCurrentWorkspace(slug);
        setBatches(workspaceData.batches);
        const prospectData = await getProspects({
          workspaceSlug: slug,
          pageSize: 100,
          sortBy: 'created_at',
          sortOrder: 'desc',
        });
        setProspects(prospectData.items || []);
        setTotal(prospectData.total || 0);
        try {
          const dr = await getDemoReadiness(slug);
          setDemoReadiness(dr);
        } catch {
          // Demo readiness is optional for the overview.
        }
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
  }, [slug]);

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

  if (authLoading || loading) {
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
        subtitle={selectedWorkspace ? `${selectedWorkspace.name} — ${selectedWorkspace.slug}` : 'Select a workspace'}
        actions={
          <div className="flex items-center gap-2">
            {workspaces.length > 1 && (
              <select
                className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                value={selectedWorkspaceSlug ?? ''}
                onChange={(e) => { if (e.target.value) setWorkspace(e.target.value); else setWorkspace(workspaces[0]?.slug ?? ''); }}
                disabled={loading || authLoading}
              >
                {workspaces.map((w) => (
                  <option key={w.id} value={w.slug}>{w.name}</option>
                ))}
              </select>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await apiLogout();
                  window.location.href = '/login';
                } catch (e) {
                  toast.addToast({ type: 'error', title: 'Logout failed', description: e instanceof ApiError ? e.message : 'Could not log out' });
                }
              }}
            >
              <LogOut className="h-4 w-4 mr-1" />
              Sign out
            </Button>
            <Button onClick={() => router.push('/prospecting')} disabled={!slug || loading}>
              Start Prospecting
            </Button>
          </div>
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

        {demoReadiness && (
          <Card className="mt-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Demo Readiness</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div><p className="text-muted-foreground">Total prospects</p><p className="font-semibold">{demoReadiness.total_prospects}</p></div>
                <div><p className="text-muted-foreground">Fresh</p><p className="font-semibold">{demoReadiness.fresh_prospects}</p></div>
                <div><p className="text-muted-foreground">Aging</p><p className="font-semibold">{demoReadiness.aging_prospects}</p></div>
                <div><p className="text-muted-foreground">Stale</p><p className="font-semibold">{demoReadiness.stale_prospects}</p></div>
                <div><p className="text-muted-foreground">Incomplete</p><p className="font-semibold">{demoReadiness.incomplete_prospects}</p></div>
                <div><p className="text-muted-foreground">DM fresh evidence</p><p className="font-semibold">{demoReadiness.decision_makers_with_fresh_evidence}</p></div>
                <div><p className="text-muted-foreground">Broken sources</p><p className="font-semibold">{demoReadiness.broken_source_urls}</p></div>
                <div><p className="text-muted-foreground">Demo ready</p><p className="font-semibold">{demoReadiness.demo_ready ? 'Yes' : 'No'}</p></div>
              </div>
              {demoReadiness.qualification_blockers?.length > 0 && (
                <div className="mt-3 text-xs text-muted-foreground">
                  <p className="font-medium">Qualification blockers:</p>
                  <ul className="list-disc ml-4">
                    {demoReadiness.qualification_blockers.map((b: string, i: number) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
