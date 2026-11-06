'use client';

import * as React from 'react';
import Link from 'next/link';
import { Users, Building2, UserCheck, MailCheck, TrendingUp, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui';
import { Badge } from '@/components/ui/badge';
import { ProgressRing } from '@/components/ui/progress-ring';
import { formatDate, formatScore, scoreColor } from '@/lib/utils';
import type { ProspectBatch, Prospect } from '@/lib/types';
import { STAGE_LABELS } from '@/lib/types';

interface DashboardStatsProps {
  totalProspects: number;
  qualifiedProspects: number;
  companiesDiscovered: number;
  decisionMakers: number;
  emailBreakdown?: {
    verified: number;
    unverified: number;
    unavailable: number;
  };
  batches: ProspectBatch[];
  recentProspects?: Prospect[];
  loading: boolean;
}

export function DashboardStats({ totalProspects, qualifiedProspects, companiesDiscovered, decisionMakers, emailBreakdown, batches, recentProspects, loading }: DashboardStatsProps) {
  const completionRate = totalProspects > 0 ? Math.round((qualifiedProspects / totalProspects) * 100) : 0;

  if (loading) {
    return (
      <div className="grid grid-cols-12 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="col-span-12 sm:col-span-6 lg:col-span-3">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="h-8 w-8 rounded-lg bg-muted mb-3 animate-pulse" />
                  <div className="h-8 w-20 bg-muted rounded animate-pulse mb-1" />
                  <div className="h-4 w-12 bg-muted rounded animate-pulse" />
                </div>
                <div className="h-14 w-14 rounded-full bg-muted animate-pulse" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <>
      {/* Metric cards */}
      <div className="grid grid-cols-12 gap-4">
        <MetricCard
          icon={<Users className="h-4 w-4" />}
          label="Total Prospects"
          value={totalProspects}
          subtitle={`Across ${batches.length} batch${batches.length !== 1 ? 'es' : ''}`}
          color="primary"
          className="col-span-12 sm:col-span-6 lg:col-span-3"
        />
        <MetricCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Qualified"
          value={qualifiedProspects}
          subtitle={`${completionRate}% of total`}
          color="success"
          className="col-span-12 sm:col-span-6 lg:col-span-3"
        />
        <MetricCard
          icon={<Building2 className="h-4 w-4" />}
          label="Companies"
          value={companiesDiscovered}
          subtitle="Discovered"
          color="info"
          className="col-span-12 sm:col-span-6 lg:col-span-3"
        />
        <MetricCard
          icon={<UserCheck className="h-4 w-4" />}
          label="Decision-Makers"
          value={decisionMakers}
          subtitle="Identified"
          color="warning"
          className="col-span-12 sm:col-span-6 lg:col-span-3"
        />
      </div>

      {/* Email breakdown + recent batches */}
      <div className="grid grid-cols-12 gap-4 mt-4">
        {/* Email status breakdown */}
        <Card className="col-span-12 sm:col-span-6 lg:col-span-4">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <MailCheck className="h-4 w-4 text-muted-foreground" />
              Contact Data Quality
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-green-500" />
                  <span className="text-muted-foreground">Verified</span>
                </div>
                <span className="font-medium">{emailBreakdown?.verified ?? 0}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-amber-500" />
                  <span className="text-muted-foreground">Unverified</span>
                </div>
                <span className="font-medium">{emailBreakdown?.unverified ?? 0}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-red-400" />
                  <span className="text-muted-foreground">Unavailable</span>
                </div>
                <span className="font-medium">{emailBreakdown?.unavailable ?? 0}</span>
              </div>
              <div className="pt-2 border-t border-border mt-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Total contacts</span>
                  <span className="font-semibold">{totalProspects}</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Completion ring */}
        <Card className="col-span-12 sm:col-span-6 lg:col-span-4">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Outreach Readiness</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <ProgressRing progress={completionRate} size={72} strokeWidth={6} showLabel color={completionRate >= 50 ? 'stroke-green-500' : 'stroke-primary'} />
              <div className="space-y-1">
                <p className="text-sm font-medium">{qualifiedProspects} of {totalProspects} prospects</p>
                <p className="text-sm text-muted-foreground">
                  {completionRate >= 50
                    ? 'Ready for outreach pipeline'
                    : 'Still building your prospect pool'}
                </p>
                <div className="mt-2 flex gap-2">
                  <Badge variant={qualifiedProspects > 0 ? 'success' : 'secondary'}>
                    {qualifiedProspects} ready
                  </Badge>
                  <Badge variant="outline">{totalProspects - qualifiedProspects} pending</Badge>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Latest batch status */}
        <Card className="col-span-12 sm:col-span-6 lg:col-span-4">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center justify-between">
              <span>Latest Batch</span>
              {batches[0] && (
                <Badge variant={batches[0].status === 'completed' ? 'success' : batches[0].status === 'failed' ? 'destructive' : 'info'}>
                  {batches[0].status}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {batches[0] ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <p className="font-medium text-sm">{batches[0].name}</p>
                  <span className="text-xs text-muted-foreground">{formatDate(batches[0].created_at)}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="bg-muted rounded-lg p-2">
                    <p className="text-lg font-semibold">{batches[0].total_discovered}</p>
                    <p className="text-muted-foreground">Discovered</p>
                  </div>
                  <div className="bg-muted rounded-lg p-2">
                    <p className="text-lg font-semibold">{batches[0].total_researched}</p>
                    <p className="text-muted-foreground">Researched</p>
                  </div>
                  <div className="bg-muted rounded-lg p-2">
                    <p className="text-lg font-semibold">{batches[0].total_qualified}</p>
                    <p className="text-muted-foreground">Qualified</p>
                  </div>
                </div>
                {batches[0].current_stage && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                    Stage: <span className="font-medium text-foreground">{STAGE_LABELS[batches[0].current_stage]}</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No batches yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent batches */}
      {batches.length > 0 && (
        <Card className="mt-4 col-span-12">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center justify-between">
              <span>Recent Batches</span>                              <Link href="/prospecting" className="text-xs text-primary hover:underline flex items-center gap-1">
                                View all <ArrowUpRight className="h-3 w-3" />
                              </Link>
                            </CardTitle>
                            </CardHeader>
                            <CardContent>
                              <div className="space-y-2">
                                {batches.slice(0, 5).map(batch => (
                <div key={batch.id} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-8 w-8 rounded-lg bg-muted shrink-0 flex items-center justify-center">
                      {batch.status === 'completed' ? (
                        <svg className="h-4 w-4 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      ) : batch.status === 'failed' ? (
                        <svg className="h-4 w-4 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6" strokeLinecap="round"/></svg>
                      ) : (
                        <div className="h-4 w-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{batch.name}</p>
                      <p className="text-xs text-muted-foreground">{formatDate(batch.created_at)} · {batch.source_mode} mode</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <Badge variant={batch.status === 'completed' ? 'success' : batch.status === 'failed' ? 'destructive' : 'info'}>
                      {batch.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{batch.requested_prospect_count} requested</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent prospects */}
      {recentProspects && recentProspects.length > 0 && (
        <Card className="mt-4 col-span-12">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center justify-between">
              <span>Latest Prospects</span>
              <Link href="/prospects" className="text-xs text-primary hover:underline flex items-center gap-1">
                View all <ArrowUpRight className="h-3 w-3" />
              </Link>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left text-xs font-medium text-muted-foreground pb-2">Prospect</th>
                    <th className="text-left text-xs font-medium text-muted-foreground pb-2">Company</th>
                    <th className="text-left text-xs font-medium text-muted-foreground pb-2">Role</th>
                    <th className="text-left text-xs font-medium text-muted-foreground pb-2">Score</th>
                    <th className="text-left text-xs font-medium text-muted-foreground pb-2">Readiness</th>
                  </tr>
                </thead>
                <tbody>
                  {recentProspects.slice(0, 5).map(p => (
                    <tr key={p.id} className="border-b border-border last:border-0">
                      <td className="py-2">
                        <p className="font-medium text-sm">{p.full_name || '—'}</p>
                      </td>
                      <td className="py-2 text-sm text-muted-foreground">{p.company_name || '—'}</td>
                      <td className="py-2 text-sm text-muted-foreground">{p.role || '—'}</td>
                      <td className="py-2">
                        <span className={cn('text-sm font-medium', formatScore(p.qualification_score) === '—' ? '' : scoreColor(p.qualification_score))}>
                          {formatScore(p.qualification_score)}
                        </span>
                      </td>
                      <td className="py-2">
                        {p.is_ready_for_outreach === null ? (
                          <Badge variant="outline">Pending</Badge>
                        ) : p.is_ready_for_outreach ? (
                          <Badge variant="success">Ready</Badge>
                        ) : (
                          <Badge variant="secondary">Not ready</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </>
  );
}

function MetricCard({
  icon,
  label,
  value,
  subtitle,
  color,
  className,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  subtitle?: string;
  color: 'primary' | 'success' | 'info' | 'warning';
  className?: string;
}) {
  const colorMap = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-50 text-green-600',
    info: 'bg-blue-50 text-blue-600',
    warning: 'bg-amber-50 text-amber-600',
  };
  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <div className={cn('rounded-lg p-2.5', colorMap[color])}>
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
