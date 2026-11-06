'use client';


import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { SkeletonCard } from '@/components/ui/skeleton';
import { useLatestBatch } from '@/lib/hooks/useApi';
import { ArrowRight, Download, Link2, FileSpreadsheet, AlertCircle, Zap, ArrowUpRight } from 'lucide-react';

export default function IntegrationsPage() {
  const router = useRouter();
  const { batch: latestBatch, loading } = useLatestBatch();

  if (loading) {
    return (
      <div className="flex flex-col min-h-screen">
        <TopBar title="Integrations" subtitle="Connect your outreach workflow" breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Integrations' }]} />
        <div className="p-6 space-y-4 max-w-4xl">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Integrations"
        subtitle="Connect Prospecting to your outreach workflow"
        breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Integrations' }]}
        actions={
          <Link href="/prospecting">
            <Button>
              <Zap className="h-4 w-4 mr-1.5" />
              Run Prospecting
            </Button>
          </Link>
        }
      />

      <div className="p-6 space-y-6 max-w-4xl">
        {/* Intro */}
        <div className="rounded-xl bg-primary/5 border border-primary/20 p-5">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 rounded-full bg-primary/10 items-center justify-center">
              <Link2 className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-primary">Outreach Integration</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Prospecting exports a CSV in the format your n8n Outreach workflow expects.
                Google Sheets is not connected: download the CSV and manually add its rows to your existing Leads sheet.
              </p>
            </div>
          </div>
        </div>

        {/* Workflow diagram */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Zap className="h-4 w-4 text-muted-foreground" />
              Export Workflow
            </CardTitle>
            <CardDescription>How a prospecting batch flows into your n8n Outreach workflow.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="space-y-0">
              <div className="flex items-center gap-4 p-4 border-b border-border">
                <div className="flex h-10 w-10 shrink-0 rounded-full bg-primary/10 items-center justify-center text-primary font-semibold text-sm">1</div>
                <div>
                  <p className="font-medium text-sm">Run Prospecting</p>
                  <p className="text-xs text-muted-foreground">Configure an ICP-based batch. The deterministic demo provider generates synthetic prospect records; it does not perform live company research.</p>
                </div>
              </div>
              <div className="flex justify-center">
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="flex items-center gap-4 p-4 border-b border-border">
                <div className="flex h-10 w-10 shrink-0 rounded-full bg-primary/10 items-center justify-center text-primary font-semibold text-sm">2</div>
                <div>
                  <p className="font-medium text-sm">Review Qualified Prospects</p>
                  <p className="text-xs text-muted-foreground">Open the Prospects table or a prospect detail to review scores, evidence, and outreach readiness.</p>
                </div>
              </div>
              <div className="flex justify-center">
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="flex items-center gap-4 p-4 border-b border-border">
                <div className="flex h-10 w-10 shrink-0 rounded-full bg-primary/10 items-center justify-center text-primary font-semibold text-sm">3</div>
                <div>
                  <p className="font-medium text-sm">Export CSV</p>
                  <p className="text-xs text-muted-foreground">Download a CSV export from the Prospects page. The file uses Samprat&apos;s existing Outreach column structure exactly.</p>
                </div>
              </div>
              <div className="flex justify-center">
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="flex items-center gap-4 p-4">
                <div className="flex h-10 w-10 shrink-0 rounded-full bg-green-100 items-center justify-center text-green-700 font-semibold text-sm">4</div>
                <div>
                  <p className="font-medium text-sm">Manual handoff to n8n</p>
                  <p className="text-xs text-muted-foreground">After you manually add CSV rows to your existing Google Sheets <code className="rounded bg-muted px-1 py-0.5 text-[11px]">Leads</code> tab, its n8n workflow can process rows with <code className="rounded bg-muted px-1 py-0.5 text-[11px]">status = new</code>. Prospecting does not push to Sheets.</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Google Sheets bridge */}
        <Card className="border-l-4 border-l-blue-400">
          <CardContent className="p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 rounded-full bg-blue-100 items-center justify-center">
                <FileSpreadsheet className="h-4 w-4 text-blue-600" />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold">Google Sheets — the bridge for this demo</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Samprat&apos;s n8n Outreach workflow pulls leads from a Google Sheets <code className="rounded bg-muted px-1 py-0.5 text-[11px]">Leads</code> tab.
                  The Prospecting module exports a CSV with the exact columns that sheet expects.
                  For this demo, download the CSV and paste it into your Sheets Leads tab manually —
                  or wire the export endpoint into your sheet refresh if you configure Google Sheets access.
                </p>
                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                  <AlertCircle className="h-3.5 w-3.5" />
                  <span>Google Sheets is not connected in this demo. No authenticated integration exists.</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Outreach field mapping */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
              Outreach Column Mapping
            </CardTitle>
            <CardDescription>
              The CSV export preserves Samprat&apos;s existing Outreach field structure exactly.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Column</th>
                    <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Source</th>
                    <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  <MappingRow col="lead_id" source="Prospect.id" note="Unique prospect identifier" />
                  <MappingRow col="first_name" source="Prospect.first_name" note="Decision-maker first name" />
                  <MappingRow col="last_name" source="Prospect.last_name" note="Decision-maker last name" />
                  <MappingRow col="email" source="Prospect.email" note="Verified where available" />
                  <MappingRow col="company" source="Prospect.company_name" note="Company name" />
                  <MappingRow col="website" source="Prospect.company_website" note="Company website" />
                  <MappingRow col="role" source="Prospect.role" note="Decision-maker role / title" />
                  <MappingRow col="client_id" source="Workspace ID" note="Northbridge Growth Partners" />
                  <MappingRow col="status" source="'new' (always)" note="Outreach workflow filters on status = new" />
                  <MappingRow col="draft_date" source="' (empty)" note="Left empty — workflow handles draft date" />
                  <MappingRow col="notes" source="Problem, fit, research, and missing information" note="Synthetic demo context; not verified company research" />
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Demo export action */}
        {latestBatch ? (
          <Card className="border-l-4 border-l-primary">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Latest Batch Export</p>
                  <p className="text-base font-semibold mt-0.5">{latestBatch.name}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {latestBatch.total_qualified} prospect{latestBatch.total_qualified !== 1 ? 's' : ''} ready for Outreach export
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Link href={`/prospects?batch=${latestBatch.id}`}>
                    <Button variant="outline">
                      Review prospects
                    </Button>
                  </Link>
                  <Link href={`/prospects?batch=${latestBatch.id}`}>
                    <Button>
                      <Download className="h-4 w-4 mr-1.5" />
                      Review &amp; Export
                    </Button>
                  </Link>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="py-8 text-center">
              <div className="flex h-10 w-10 mx-auto rounded-full bg-muted items-center justify-center mb-3">
                <Download className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">No batch to export yet</p>
              <p className="text-xs text-muted-foreground mt-1">Run a prospecting batch first, then export the qualified prospects.</p>
              <Link href="/prospecting" className="mt-4 inline-block">
                <Button className="mt-4">
                  <Zap className="h-4 w-4 mr-1.5" />
                  Start Prospecting
                </Button>
              </Link>
            </CardContent>
          </Card>
        )}

        {/* What NOT to do */}
        <Card className="border-border/50 bg-muted/30">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 rounded-full bg-amber-100 items-center justify-center">
                <AlertCircle className="h-4 w-4 text-amber-600" />
              </div>
              <div>
                <h3 className="text-sm font-medium">Important</h3>
                <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground list-disc list-inside">
                  <li>Do not rebuild the n8n Outreach workflow — it already exists and consumes the Sheets Leads tab.</li>
                  <li>Do not claim Google Sheets is connected unless an authenticated integration is configured.</li>
                  <li>Do not invent credentials or service-account JSON. The export here is a CSV download.</li>
                  <li>Never commit .env files or service-account keys to this repository.</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MappingRow({ col, source, note }: { col: string; source: string; note: string }) {
  return (
    <tr className="hover:bg-secondary/30">
      <td className="px-4 py-3">
        <code className="rounded bg-muted px-1.5 py-0.5 text-[12px]">{col}</code>
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{source}</td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{note}</td>
    </tr>
  );
}
