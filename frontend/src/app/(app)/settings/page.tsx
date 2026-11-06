'use client';

import { useEffect, useState } from 'react';
import { getHealth, ApiError } from '@/lib/api';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckCircle2, AlertCircle, RefreshCw, Globe, Shield, Settings, Info } from 'lucide-react';
import { formatDate, cn } from '@/lib/utils';

export default function SettingsPage() {
  const toast = useToast();
  const [health, setHealth] = useState<{ status: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const checkHealth = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getHealth();
      setHealth(data);
      setCheckedAt(new Date());
    } catch (e) {
      setHealth(null);
      setError(e instanceof ApiError ? e.message : 'Connection failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then(data => {
        if (cancelled) return;
        setHealth(data);
        setCheckedAt(new Date());
      })
      .catch(e => {
        if (cancelled) return;
        setHealth(null);
        setError(e instanceof ApiError ? e.message : 'Connection failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Settings"
        subtitle="Workspace and platform configuration"
        breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Settings' }]}
        actions={
          <Button variant="outline" size="sm" onClick={checkHealth} loading={loading}>
            <RefreshCw className="h-4 w-4 mr-1.5" />
            Check Backend
          </Button>
        }
      />

      <div className="p-6 space-y-6 max-w-4xl">
        {/* System status */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="h-4 w-4 text-muted-foreground" />
              System Status
            </CardTitle>
            <CardDescription>Backend connection and platform health.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-12 gap-4">
              <div className="col-span-12 sm:col-span-6">
                <dl className="space-y-3">
                  <div className="flex items-center justify-between">
                    <dt className="text-sm text-muted-foreground">Backend service</dt>
                    <div className="flex items-center gap-2">
                      {health?.status === 'ok' ? (
                        <Badge variant="success" className="gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Connected
                        </Badge>
                      ) : health === null ? (
                        <Badge variant="outline">Checking…</Badge>
                      ) : (
                        <Badge variant="destructive" className="gap-1">
                          <AlertCircle className="h-3 w-3" />
                          {error || 'Unavailable'}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-sm text-muted-foreground">API base URL</dt>
                    <dd className="text-sm font-medium text-right break-all">
                      {process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-sm text-muted-foreground">Last checked</dt>
                    <dd className="text-sm text-muted-foreground text-right">
                      {checkedAt ? formatDate(checkedAt.toISOString()) : '—'}
                    </dd>
                  </div>
                </dl>
              </div>

              <div className="col-span-12 sm:col-span-6 border-t sm:border-t-0 sm:border-l border-border pt-4 sm:pl-4">
                <p className="text-xs text-muted-foreground mb-3">Environment configuration</p>
                <div className="rounded-lg bg-muted/50 p-3 font-mono text-xs text-muted-foreground break-all">
                  {process.env.NEXT_PUBLIC_API_BASE_URL ? (
                    <>
                      NEXT_PUBLIC_API_BASE_URL={process.env.NEXT_PUBLIC_API_BASE_URL}
                      <br />
                      (from .env.local)
                    </>
                  ) : (
                    <span className="text-amber-600">NEXT_PUBLIC_API_BASE_URL not set — falling back to http://localhost:8000</span>
                  )}
                </div>
                {!process.env.NEXT_PUBLIC_API_BASE_URL && (
                  <div className="mt-3 rounded-lg bg-amber-50 p-3 border border-amber-100 text-xs text-amber-800">
                    Create an <code className="rounded bg-amber-100 px-1 py-0.5">.env.local</code> file in the frontend/ directory with <code className="rounded bg-amber-100 px-1 py-0.5">NEXT_PUBLIC_API_BASE_URL=http://localhost:8000</code>.
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Workspace */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-muted-foreground" />
              Demo Workspace
            </CardTitle>
            <CardDescription>This is a synthetic demo environment.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <dt className="text-sm text-muted-foreground">Workspace</dt>
                <dd className="text-sm font-medium">Northbridge Growth Partners <span className="text-muted-foreground">(demo)</span></dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-sm text-muted-foreground">Mode</dt>
                <dd className="text-sm">
                  <Badge variant="info">Demo / synthetic</Badge>
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-sm text-muted-foreground">Data</dt>
                <dd className="text-sm text-muted-foreground">Synthetic companies, decision-makers, and emails — no real people or contacts used.</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-sm text-muted-foreground">Max prospects per batch</dt>
                <dd className="text-sm font-medium">100</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-sm text-muted-foreground">Data source</dt>
                <dd className="text-sm text-muted-foreground">Demo provider — deterministic synthetic data.</dd>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Outreach note */}
        <Card className="border-l-4 border-l-amber-400">
          <CardContent className="p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 rounded-full bg-amber-100 items-center justify-center">
                <Shield className="h-4 w-4 text-amber-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold">Security note</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  This is a public repository. Never commit <code className="rounded bg-muted px-1 py-0.5 text-[11px]">.env</code> files,
                  Google service-account JSON, or any real API keys. The backend uses a local SQLite database and a demo provider.
                  For a real deployment, configure environment variables on the hosting platform and connect real data sources.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* About */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Info className="h-4 w-4 text-muted-foreground" />
              About
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Application</dt>
                <dd className="font-medium">Prospector — AI Prospecting SaaS</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Stack</dt>
                <dd className="text-muted-foreground">Next.js 16 · React 19 · TypeScript · Tailwind CSS · Lucide icons</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Backend</dt>
                <dd className="text-muted-foreground">FastAPI · Pydantic · SQLAlchemy · SQLite · Python 3.12</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Purpose</dt>
                <dd className="text-muted-foreground">Synthetic demo prospecting platform that prepares leads for manual CSV handoff to Samprat&apos;s n8n Outreach workflow.</dd>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Local backend command */}
        <Card className="border-border/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Run the local backend</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-3">
              From the repository root, start FastAPI with the existing SQLite database:
            </p>
            <pre className="overflow-x-auto rounded-lg bg-muted/50 p-3 font-mono text-xs text-muted-foreground">
              <code>{`cd backend\npython -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`}</code>
            </pre>
            <p className="text-xs text-muted-foreground mt-2">
              Do not run the demo seed script when restarting; it is only for initial database setup.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
