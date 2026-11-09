'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useWorkspaceSlug } from '@/lib/hooks/useAuth';

// This page is dynamic — prospect id is only known at request time.
export const dynamic = 'force-dynamic';
import { getProspect, getProspectVerification, getCompanyEvidence, ApiError } from '@/lib/api';

import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar } from '@/components/ui/avatar';
import { TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { formatDate, cn, formatScore, scoreColor, scoreBg, readinessLabel, confidenceColor, externalUrl, truncate, parseCommaList } from '@/lib/utils';
import { ArrowLeft, ArrowRight, Building2, User, Globe, Link2, Mail, ShieldCheck, AlertTriangle, Lightbulb, HelpCircle, Target, CheckCircle2, XCircle, Certificate } from 'lucide-react';
import type { ProspectDetail, EvidenceItem, EnrichmentRecord, VerificationRecord, ProspectVerification, CompanyEvidence } from '@/lib/types';

export default function ProspectDetailPage() {
  const params = useParams();
  const toast = useToast();
  const slug = useWorkspaceSlug();
  const prospectId = params.id as string;

  const [prospect, setProspect] = useState<ProspectDetail | null>(null);
  const [verification, setVerification] = useState<ProspectVerification | null>(null);
  const [companyEvidence, setCompanyEvidence] = useState<CompanyEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProspect = useCallback(async () => {
    if (!slug) return;
    try {
      setLoading(true);
      setError(null);
      const pData = await getProspect(prospectId, slug);
      const vData = await getProspectVerification(prospectId, slug);
      let cData: CompanyEvidence | null = null;
      if (pData.company_id) {
        try {
          cData = await getCompanyEvidence(pData.company_id, slug);
        } catch {
          // Company evidence may not be available; proceed without it
        }
      }
      setProspect(pData);
      setVerification(vData);
      setCompanyEvidence(cData);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load prospect');
    } finally {
      setLoading(false);
    }
  }, [prospectId, slug]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!slug) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const pData = await getProspect(prospectId, slug);
        if (cancelled) return;
        setProspect(pData);
        setError(null);
        const vData = await getProspectVerification(prospectId, slug);
        if (cancelled) return;
        setVerification(vData);
        let cData: CompanyEvidence | null = null;
        if (pData.company_id) {
          try {
            cData = await getCompanyEvidence(pData.company_id, slug);
          } catch {
            // Company evidence may not be available
          }
        }
        if (!cancelled) setCompanyEvidence(cData);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : 'Failed to load prospect');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [prospectId, slug]);

  if (loading && !prospect) {
    return (        <div className="flex-col min-h-screen">
          <TopBar title="Prospect" breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Prospects', href: '/prospects' }, { label: 'Loading…' }]} />
        <div className="p-6 max-w-5xl space-y-6">
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 lg:col-span-8 space-y-4">
              <div className="h-10 w-1/3 bg-muted rounded animate-pulse" />
              <div className="h-4 w-1/4 bg-muted rounded animate-pulse" />
              <Skeleton height={200} className="my-4" />
              <div className="h-4 w-full bg-muted rounded animate-pulse mb-2" />
              <div className="h-4 w-3/4 bg-muted rounded animate-pulse" />
            </div>
            <div className="col-span-12 lg:col-span-4 space-y-4">
              <div className="h-24 w-full bg-muted rounded animate-pulse" />
              <div className="h-20 w-full bg-muted rounded animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error && !prospect) {
    return (        <div className="flex-col min-h-screen">
          <TopBar title="Prospect" breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Prospects', href: '/prospects' }, { label: 'Error' }]} />
        <div className="p-6 max-w-5xl">
          <Card className="border-red-200">
            <CardContent className="py-12 text-center">
              <div className="flex h-12 w-12 mx-auto rounded-full bg-red-50 items-center justify-center mb-4">
                <AlertTriangle className="h-6 w-6 text-red-500" />
              </div>
              <p className="text-sm font-medium text-red-700">Could not load prospect</p>
              <p className="text-xs text-red-600/80 mt-1">{error}</p>
              <Button className="mt-4" onClick={loadProspect}>Retry</Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  const p = prospect;
  if (!p) return null;

  return (
    <div className="flex-col min-h-screen">
      <TopBar
        title={p.full_name || 'Prospect'}
        subtitle={p.company_name || 'Unknown company'}
        breadcrumbs={[
          { label: 'Overview', href: '/' },
          { label: 'Prospects', href: '/prospects' },
          { label: p.full_name || 'Prospect' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Link href="/prospects">
              <Button variant="outline" size="sm">
                <ArrowLeft className="h-4 w-4 mr-1.5" />
                All Prospects
              </Button>
            </Link>
            {p.company?.website && (
              <a
                href={externalUrl(p.company.website) || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-secondary transition-colors"
              >
                <Globe className="h-4 w-4" />
                Company site
              </a>
            )}
          </div>
        }
      />

      <div className="p-6 max-w-5xl space-y-6">
        {/* Header card */}
        <Card className="overflow-hidden">
          <div className="h-1 bg-primary" />
          <CardContent className="pt-5">
            <div className="flex flex-col sm:flex-row sm:items-start gap-4">
              <Avatar name={p.full_name || 'Prospect'} size="lg" className="shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                  <h1 className="text-xl font-semibold">{p.full_name || 'Unnamed prospect'}</h1>
                  {p.role && <p className="text-sm text-muted-foreground">{p.role}</p>}
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  {p.company_name && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">
                      <Building2 className="h-3 w-3" />
                      {p.company_name}
                    </span>
                  )}
                  {p.industry && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                      <Globe className="h-3 w-3" />
                      {p.industry}
                    </span>
                  )}
                  {p.country && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                      <Globe className="h-3 w-3" />
                      {p.country}
                    </span>
                  )}
                  <Badge variant={p.is_ready_for_outreach ? 'success' : p.is_ready_for_outreach === false ? 'destructive' : 'outline'}>
                    {readinessLabel(p.is_ready_for_outreach)}
                  </Badge>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className={cn('inline-flex items-center justify-center rounded-full px-3 py-1 text-lg font-semibold', scoreBg(p.qualification_score))}>
                  {formatScore(p.qualification_score)}
                </div>
                <p className="text-xs text-muted-foreground mt-1">Qualification score</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <TabsList defaultValue="overview">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="verification">Verification & Enrichment</TabsTrigger>
          <TabsTrigger value="evidence">Company Evidence</TabsTrigger>
          <TabsTrigger value="research">Research Findings</TabsTrigger>
          <TabsTrigger value="problem">Identified Problem</TabsTrigger>
          <TabsTrigger value="fit">Why This Fits</TabsTrigger>
          <TabsTrigger value="qualification">Qualification</TabsTrigger>

          <TabsContent value="overview">
          <div className="grid grid-cols-12 gap-4">
            {/* Company */}
            <Card className="col-span-12 lg:col-span-7">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  Company Overview
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <dl className="divide-y divide-border">
                  {p.company ? (
                    <>
                      <div className="py-3">
                        <dt className="text-xs text-muted-foreground font-medium mb-0.5">Company</dt>
                        <dd className="text-base font-medium">{p.company.name}</dd>
                      </div>
                      {p.company.website ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Website</dt>
                          <dd className="text-sm">
                            <a href={externalUrl(p.company.website) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline flex items-center gap-1">
                              <Globe className="h-3.5 w-3.5" />
                              {p.company.website}
                              <ArrowRight className="h-3 w-3" />
                            </a>
                          </dd>
                        </div>
                      ) : null}
                      {p.company.industry ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Industry</dt>
                          <dd className="text-sm">{p.company.industry}</dd>
                        </div>
                      ) : null}
                      {p.company.location || p.company.country || p.company.city ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Location</dt>
                          <dd className="text-sm">
                            {formatLocation([p.company.city, p.company.location, p.company.country])}
                          </dd>
                        </div>
                      ) : null}
                      {p.company.description ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">About this company</dt>
                          <dd className="text-sm text-muted-foreground">{p.company.description}</dd>
                        </div>
                      ) : null}
                      {p.company.products_services ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Products & Services</dt>
                          <dd className="text-sm text-muted-foreground">{p.company.products_services}</dd>
                        </div>
                      ) : null}
                      {p.company.company_size ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Company Size</dt>
                          <dd className="text-sm">{p.company.company_size}</dd>
                        </div>
                      ) : null}
                      {p.company.employee_count ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Employees</dt>
                          <dd className="text-sm">{p.company.employee_count}</dd>
                        </div>
                      ) : null}
                      {p.company.revenue ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Revenue</dt>
                          <dd className="text-sm">{p.company.revenue}</dd>
                        </div>
                      ) : null}
                      {p.company.linkedin_url ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">LinkedIn</dt>
                          <dd className="text-sm">
                            <a href={externalUrl(p.company.linkedin_url) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline flex items-center gap-1">
                              <Link2 className="h-3.5 w-3.5" />
                              {truncate(p.company.linkedin_url, 40)}
                            </a>
                          </dd>
                        </div>
                      ) : null}
                      {p.company.source_url ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Source</dt>
                          <dd className="text-sm text-muted-foreground">
                            <a href={externalUrl(p.company.source_url) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline flex items-center gap-1">
                              {p.company.source_name || 'Source'}
                            </a>
                          </dd>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="py-6 text-center">
                      <p className="text-sm text-muted-foreground italic">No company data available.</p>
                    </div>
                  )}
                </dl>
              </CardContent>
            </Card>

            {/* Decision-maker card */}
            <Card className="col-span-12 lg:col-span-5">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <User className="h-4 w-4 text-muted-foreground" />
                  Decision-Maker
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="pt-2">
                  {p.decision_maker ? (
                    <dl className="divide-y divide-border">
                      <div className="py-3 flex items-center gap-3">
                        <Avatar name={p.decision_maker.full_name || 'Decision Maker'} size="md" />
                        <div>
                          <p className="font-medium">{p.decision_maker.full_name || 'Unnamed decision-maker'}</p>
                          {p.decision_maker.job_title && (
                            <p className="text-sm text-muted-foreground">{p.decision_maker.job_title}</p>
                          )}
                        </div>
                      </div>
                      {p.decision_maker.professional_profile_url ? (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Professional Profile</dt>
                          <dd className="text-sm">
                            <a href={externalUrl(p.decision_maker.professional_profile_url) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline flex items-center gap-1">
                              <Link2 className="h-3.5 w-3.5" />
                              {p.decision_maker.profile_source || 'Profile'}
                            </a>
                          </dd>
                        </div>
                      ) : null}
                      {p.decision_maker.is_primary !== undefined ? (
                        <div className="py-3 flex items-center gap-2">
                          {p.decision_maker.is_primary ? (
                            <Badge variant="success">Primary contact</Badge>
                          ) : (
                            <Badge variant="secondary">Secondary</Badge>
                          )}
                        </div>
                      ) : null}
                      {p.email && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5 flex items-center gap-1">
                            <Mail className="h-3.5 w-3.5" />
                            Email
                          </dt>
                          <dd className="text-sm">              <a
                href={`mailto:${p.email}`}
                className="text-primary hover:underline"
              >
                {p.email}
              </a>
                          </dd>
                        </div>
                      )}
                      {p.linkedin_url && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">LinkedIn</dt>
                          <dd className="text-sm">
                            <a href={externalUrl(p.linkedin_url) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline flex items-center gap-1">
                              <Link2 className="h-3.5 w-3.5" />
                              {truncate(p.linkedin_url, 40)}
                            </a>
                          </dd>
                        </div>
                      )}
                      {p.instagram_url && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Instagram</dt>
                          <dd className="text-sm">
                            <a href={externalUrl(p.instagram_url) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline flex items-center gap-1">
                              <Link2 className="h-3.5 w-3.5" />
                              {truncate(p.instagram_url, 40)}
                            </a>
                          </dd>
                        </div>
                      )}
                    </dl>
                  ) : (
                    <div className="py-6 text-center">
                      <p className="text-sm text-muted-foreground italic">No decision-maker identified yet.</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Evidence */}
            {p.evidence && p.evidence.length > 0 && (
              <Card className="col-span-12">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Certificate className="h-4 w-4 text-muted-foreground" />
                    Research Evidence & Sources
                  </CardTitle>
                  <CardDescription>Research notes for this prospect. Synthetic demo records are illustrative, not verified.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    {p.evidence.map((ev: EvidenceItem) => (
                      <div key={ev.id} className="py-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{ev.label || 'Source'}</p>
                            {ev.content && (
                              <p className="text-xs text-muted-foreground mt-0.5">{truncate(ev.content, 120)}</p>
                            )}
                          </div>
                          {ev.url && externalUrl(ev.url) && (
                            <a href={ev.url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1">
                              <Link2 className="h-3 w-3" />
                              Visit source
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Enrichment & verification */}
            {(p.enrichment_records.length > 0 || p.verification_records.length > 0) && (
              <Card className="col-span-12">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                    Data Enrichment & Verification
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="grid grid-cols-12 gap-4">
                    {p.enrichment_records.length > 0 && (
                      <div className="col-span-12 lg:col-span-6">
                        <div className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Enrichment Records</div>
                        <div className="space-y-2">
                          {p.enrichment_records.map((er: EnrichmentRecord) => (
                            <div key={er.id} className="rounded-lg bg-muted/50 p-3 text-sm">
                              <div className="flex items-center justify-between">
                                <span className="font-medium">{er.provider || 'Unknown provider'}</span>
                                {er.email_status && (
                                  <Badge variant={er.email_status === 'deliverable' ? 'success' : er.email_status === 'unavailable' ? 'destructive' : 'warning'}>
                                    {er.email_status}
                                  </Badge>
                                )}
                              </div>
                              {er.email && (
                                <p className="text-xs text-muted-foreground mt-1">
                                  <a href={`mailto:${er.email}`} className="hover:underline">{er.email}</a>
                                </p>
                              )}
                              {er.linkedin_url && (
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  LinkedIn: {truncate(er.linkedin_url, 50)}
                                </p>
                              )}
                              {er.instagram_url && (
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  Instagram: {truncate(er.instagram_url, 50)}
                                </p>
                              )}
                              {er.email_confidence !== null && (
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  Confidence: {er.email_confidence}%
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {p.verification_records.length > 0 && (
                      <div className="col-span-12 lg:col-span-6">
                        <div className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Email Verification</div>
                        <div className="space-y-2">
                          {p.verification_records.map((vr: VerificationRecord) => (
                            <div key={vr.id} className="rounded-lg bg-muted/50 p-3 text-sm">
                              <div className="flex items-center justify-between">
                                <span className="font-medium">{vr.email || '—'}</span>
                                {vr.status && (
                                  <Badge variant={vr.status === 'verified' ? 'success' : vr.status === 'invalid' || vr.status === 'unavailable' ? 'destructive' : 'warning'}>
                                    {vr.status}
                                  </Badge>
                                )}
                                {vr.provider && (
                                  <span className="text-xs text-muted-foreground ml-1">{vr.provider}</span>
                                )}
                              </div>
                              {vr.details && (
                                <p className="text-xs text-muted-foreground mt-1">{vr.details}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="research">
          <div className="space-y-4">
            {/* Research summary */}
            {p.research_summary ? (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Lightbulb className="h-4 w-4 text-muted-foreground" />
                    Research Summary
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none text-muted-foreground">
                    <p className="whitespace-pre-wrap">{p.research_summary}</p>
                  </div>
                  <div className="mt-4 flex items-start gap-2 rounded-lg bg-blue-50 p-3 border border-blue-100">
                    <HelpCircle className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-blue-800">
                      This summary was generated from synthetic demo records, not from public company research.
                      Treat it as illustrative demo data, never as verified fact.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  No research summary available yet.
                </CardContent>
              </Card>
            )}

            {/* Observations */}
            {p.research_summary && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Target className="h-4 w-4 text-muted-foreground" />
                    Key Company Observations
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[
                      { label: 'Business type', value: p.company?.company_size || '—' },
                      { label: 'Scale', value: p.company?.employee_count || p.company?.revenue || '—' },
                      { label: 'Industry position', value: p.industry || '—' },
                      { label: 'Geography', value: formatLocation([p.company?.city, p.company?.location, p.company?.country]) || '—' },
                      { label: 'Observed offering', value: p.company?.products_services ? truncate(p.company.products_services, 120) : '—' },
                      { label: 'Digital presence', value: (p.company?.linkedin_url || p.company?.website) ? 'Active' : 'Limited' },
                    ].map((item, i) => (
                      <div key={i} className="rounded-lg border border-border bg-muted/30 p-3">
                        <dt className="text-xs text-muted-foreground uppercase tracking-wide">{item.label}</dt>
                        <dd className="text-sm font-medium mt-0.5">{item.value}</dd>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="problem">
          <Card className="border-l-4 border-l-amber-400">
            <CardContent className="p-5">
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 rounded-full bg-amber-100 items-center justify-center">
                  <Lightbulb className="h-5 w-5 text-amber-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold">Identified Business Problem</h2>
                    {p.business_problem && (
                      <Badge variant="warning">Synthetic demo</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {p.problem_evidence
                      ? 'Illustrative supporting context from synthetic demo data.'
                      : 'Illustrative text based on synthetic company and industry data.'}
                  </p>
                  <div className="mt-3 rounded-lg bg-amber-50 p-4 border border-amber-100">
                    {p.business_problem ? (
                      <blockquote className="prose prose-sm max-w-none">
                        <p className="whitespace-pre-wrap">{p.business_problem}</p>
                      </blockquote>
                    ) : (
                      <p className="text-sm text-muted-foreground italic">No specific problem identified yet.</p>
                    )}
                  </div>
                  {p.problem_evidence && (
                    <div className="mt-3 text-xs text-muted-foreground">
                      <span className="font-medium">Supporting evidence:</span> {p.problem_evidence}
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="fit">
          <div className="space-y-4">
            {/* Why it fits - hero card */}
            <Card className="bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20">
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 rounded-full bg-primary items-center justify-center">
                    <Target className="h-6 w-6 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h2 className="text-lg font-semibold text-primary">Why {p.company_name || 'This Company'} Is a Strong Fit</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                      This synthetic demo match connects the company&apos;s illustrative profile to your offering.
                      It is not verified company research; review claims independently before outreach.
                    </p>
                  </div>
                </div>

                {p.solution_match ? (
                  <div className="mt-5 rounded-xl border border-border bg-card p-5">
                    <blockquote className="prose prose-sm max-w-none">
                      <p className="whitespace-pre-wrap">{p.solution_match}</p>
                    </blockquote>
                  </div>
                ) : (
                  <div className="mt-5 rounded-xl border border-dashed border-border bg-muted/50 p-5 text-center">
                    <HelpCircle className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">Solution fit analysis not available yet.</p>
                  </div>
                )}

                {/* Fit breakdown */}
                <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <FitFactor
                    label="Company situation"
                    value={p.research_summary ? 'Context gathered' : '—'}
                    verified={!!p.research_summary}
                  />
                  <FitFactor
                    label="Identified problem"
                    value={p.business_problem ? 'Problem surfaced' : '—'}
                    verified={!!p.business_problem}
                  />
                  <FitFactor
                    label="Solution alignment"
                    value={p.solution_match ? 'Match articulated' : '—'}
                    verified={!!p.solution_match}
                  />
                </div>

                <div className="mt-4 text-xs text-muted-foreground flex items-start gap-2">
                  <ShieldCheck className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  <p>
                    {p.is_ready_for_outreach === true
                      ? 'This prospect is marked ready for outreach. Review the qualification section before sending.'
                      : p.is_ready_for_outreach === false
                      ? 'This prospect is not yet ready for outreach. Additional qualification or missing information is needed.'
                      : 'Readiness assessment is pending.'}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Detailed fit explanation */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">How the Fit Was Determined</CardTitle>
                <CardDescription>Illustrative steps generated from synthetic demo data.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4 text-sm">
                  <FitStep
                    step="1"
                    label="Company context"
                    content={p.company?.description || p.company?.products_services ? 'Context available from company data.' : 'Limited company context available.'}
                  />
                  <FitStep
                    step="2"
                    label="Problem identification"
                    content={p.business_problem ? 'The demo provider created a sample problem narrative from synthetic company and industry attributes.' : 'No problem identified yet.'}
                  />
                  <FitStep
                    step="3"
                    label="Offering match"
                    content={p.solution_match ? "The client's offering was matched against the identified problem." : 'No match analysis available yet.'}
                  />
                  <FitStep
                    step="4"
                    label="Qualification"
                    content={`Qualification score: ${formatScore(p.qualification_score)} — ${p.research_confidence || 'Confidence not assessed'}.`}
                  />
                </div>
                <div className="mt-4 pt-3 border-t border-border text-xs text-muted-foreground">
                  <p className="flex items-start gap-2">
                    <Lightbulb className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    Synthetic demo fit analysis. Do not treat company claims as verified research.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="qualification">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Score card */}
            <Card className="md:col-span-1">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Target className="h-4 w-4 text-muted-foreground" />
                  Qualification Score
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4">
                  <div className={cn(
                    'flex h-16 w-16 shrink-0 items-center justify-center rounded-full text-2xl font-semibold',
                    scoreBg(p.qualification_score),
                  )}>
                    {formatScore(p.qualification_score)}
                  </div>
                  <div>
                    <p className="text-sm font-medium">
                      {p.qualification_score >= 70 ? 'Strong fit' : p.qualification_score >= 40 ? 'Moderate fit' : 'Weak fit'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {p.research_confidence ? `Research confidence: ${p.research_confidence}` : 'Confidence not assessed'}
                    </p>
                  </div>
                </div>
                {p.qualification_reasons ? (
                  <div className="mt-4 rounded-lg bg-muted/50 p-3 text-sm">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Scoring reasons</p>
                    <p className="whitespace-pre-wrap">{p.qualification_reasons}</p>
                  </div>
                ) : (
                  <div className="mt-4 rounded-lg border border-dashed border-border bg-muted/30 p-3 text-sm text-muted-foreground text-center">
                    Scoring rationale not available.
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Readiness card */}
            <Card className="md:col-span-1">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                  Outreach Readiness
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between py-2 border-b border-border">
                    <span className="text-sm text-muted-foreground">Ready for outreach</span>
                    <Badge variant={p.is_ready_for_outreach ? 'success' : p.is_ready_for_outreach === false ? 'destructive' : 'outline'}>
                      {readinessLabel(p.is_ready_for_outreach)}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between py-2 border-b border-border">
                    <span className="text-sm text-muted-foreground">Email verified</span>
                    {p.verification_records.length > 0 ? (
                      <Badge variant={p.verification_records.some(v => v.status === 'verified') ? 'success' : 'warning'}>
                        {p.verification_records.some(v => v.status === 'verified') ? 'Verified' : 'Not verified'}
                      </Badge>
                    ) : (
                      <Badge variant="outline">Not checked</Badge>
                    )}
                  </div>
                  <div className="flex items-center justify-between py-2 border-b border-border">
                    <span className="text-sm text-muted-foreground">Decision-maker found</span>
                    <Badge variant={p.decision_maker ? 'success' : 'secondary'}>
                      {p.decision_maker ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between py-2">
                    <span className="text-sm text-muted-foreground">Missing information</span>
                    <div className="max-w-[60%] text-right">
                      {p.missing_information ? (
                        <span className="text-sm text-amber-600">{truncate(p.missing_information, 80)}</span>
                      ) : (
                        <span className="text-sm text-green-600">None identified</span>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Missing info detail */}
            {p.missing_information && (
              <Card className="md:col-span-2">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                    Missing Information
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="rounded-lg bg-amber-50 p-4 border border-amber-100 text-sm">
                    <p className="whitespace-pre-wrap">{p.missing_information}</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Source links */}
            {p.source_links && (
              <Card className="md:col-span-2">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Link2 className="h-4 w-4 text-muted-foreground" />
                    Company Links (synthetic demo)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {parseCommaList(p.source_links).map((link, i) =>
                      externalUrl(link) ? (
                        <a
                          key={i}
                          href={link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-secondary/80 hover:text-foreground transition-colors"
                        >
                          <Link2 className="h-3 w-3" />
                          {truncate(link, 40)}
                        </a>
                      ) : (
                        <span key={i} className="inline-flex rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                          {truncate(link, 40)}
                        </span>
                      )
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* Verification & Enrichment tab */}
        <TabsContent value="verification">
          <div className="space-y-4">
            {/* Email verification status */}
            {verification && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                    Email Verification Status
                  </CardTitle>
                  <CardDescription>
                    {verification.email_verified
                      ? 'Email has been verified by a provider.'
                      : verification.email_status === 'unverified'
                      ? 'Email has not been verified. DNS/MX records alone do not constitute verification.'
                      : 'Email verification status is unavailable.'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      'flex h-12 w-12 shrink-0 items-center justify-center rounded-full',
                      verification.email_verified ? 'bg-green-50 text-green-600' : 'bg-amber-50 text-amber-600'
                    )}>
                      {verification.email_verified ? (
                        <CheckCircle2 className="h-6 w-6" />
                      ) : (
                        <AlertTriangle className="h-6 w-6" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium">
                        {verification.email_verified ? 'Verified' : 'Not verified'}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Email: {verification.email || '—'}<br />
                        Status: {verification.email_status || 'unknown'}<br />
                        Qualification: {verification.qualification_status || 'not assessed'}
                      </p>
                    </div>
                  </div>
                  {verification.missing_information.length > 0 && (
                    <div className="mt-4 rounded-lg bg-amber-50 p-3 border border-amber-100">
                      <p className="text-xs font-medium text-amber-800 uppercase tracking-wide mb-1">Missing Information</p>
                      <ul className="text-xs text-amber-700 space-y-0.5 list-disc list-inside">
                        {verification.missing_information.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Enrichment records from engine */}
            {verification && verification.enrichment.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <User className="h-4 w-4 text-muted-foreground" />
                    Enrichment Records (engine)
                  </CardTitle>
                  <CardDescription>Contact and profile data from prospecting providers.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    {verification.enrichment.map((er, i) => {
                      const e = er as Record<string, string | number | null | undefined>;
                      return (
                        <div key={i} className="py-3">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="text-sm font-medium">{String(e.provider || 'Unknown provider')}</p>
                              {String(e.email_status || '') && (
                                <Badge variant={e.email_status === 'deliverable' ? 'success' : e.email_status === 'unavailable' ? 'destructive' : 'warning'}>
                                  {String(e.email_status)}
                                </Badge>
                              )}
                            </div>
                            {typeof e.email_confidence === 'number' && e.email_confidence !== null && (
                              <span className="text-xs text-muted-foreground">Confidence: {e.email_confidence}%</span>
                            )}
                          </div>
                          {String(e.email || '') && (
                            <p className="text-xs text-muted-foreground mt-1">
                              <a href={`mailto:${e.email}`} className="hover:underline">{e.email}</a>
                            </p>
                          )}
                          {String(e.linkedin_url || '') && (
                            <p className="text-xs text-muted-foreground mt-0.5">
                              LinkedIn: <a href={e.linkedin_url as string} target="_blank" rel="noopener noreferrer" className="hover:underline">{truncate(String(e.linkedin_url), 50)}</a>
                            </p>
                          )}
                          {String(e.notes || '') && (
                            <p className="text-xs text-muted-foreground mt-1">{String(e.notes)}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Verification records from engine */}
            {verification && verification.verification.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                    Provider Verification Attempts
                  </CardTitle>
                  <CardDescription>Results from email verification providers. DNS/MX existence alone does not mean verified.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    {verification.verification.map((vr, i) => (
                      <div key={i} className="py-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{String(vr.provider || 'Unknown provider')}</p>
                            <span className="text-xs text-muted-foreground">{String(vr.email || '')}</span>
                          </div>
                          <Badge variant={
                            String(vr.status) === 'verified' ? 'success' :
                            String(vr.status) === 'invalid' || String(vr.status) === 'unavailable' ? 'destructive' : 'warning'
                          }>
                            {String(vr.status) || 'unknown'}
                          </Badge>
                        </div>
                        {String(vr.details || '') && (
                          <p className="text-xs text-muted-foreground mt-1">{String(vr.details)}</p>
                        )}
                        {vr.verified_at && (
                          <p className="text-xs text-muted-foreground mt-0.5">Verified at: {formatDate(String(vr.verified_at))}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Legacy verification records (from prospect endpoint) */}
            {p.verification_records.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Certificate className="h-4 w-4 text-muted-foreground" />
                    Verification Records (legacy)
                  </CardTitle>
                  <CardDescription>Previously stored verification data from the prospecting system.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    {p.verification_records.map((vr) => (
                      <div key={vr.id} className="py-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{vr.provider || 'Unknown provider'}</p>
                            {vr.status && (
                              <Badge variant={vr.status === 'verified' ? 'success' : vr.status === 'invalid' || vr.status === 'unavailable' ? 'destructive' : 'warning'}>
                                {vr.status}
                              </Badge>
                            )}
                          </div>
                        </div>
                        {vr.email && (
                          <p className="text-xs text-muted-foreground mt-1">
                            <a href={`mailto:${vr.email}`} className="hover:underline">{vr.email}</a>
                          </p>
                        )}
                        {vr.details && (
                          <p className="text-xs text-muted-foreground mt-1">{vr.details}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Legacy enrichment records */}
            {p.enrichment_records.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <User className="h-4 w-4 text-muted-foreground" />
                    Enrichment Records (legacy)
                  </CardTitle>
                  <CardDescription>Previously stored enrichment data from the prospecting system.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    {p.enrichment_records.map((er) => (
                      <div key={er.id} className="py-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{er.provider || 'Unknown provider'}</p>
                            {er.email_status && (
                              <Badge variant={er.email_status === 'deliverable' ? 'success' : er.email_status === 'unavailable' ? 'destructive' : 'warning'}>
                                {er.email_status}
                              </Badge>
                            )}
                          </div>
                        </div>
                        {er.email && (
                          <p className="text-xs text-muted-foreground mt-1">
                            <a href={`mailto:${er.email}`} className="hover:underline">{er.email}</a>
                          </p>
                        )}
                        {er.linkedin_url && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            LinkedIn: {truncate(er.linkedin_url, 50)}
                          </p>
                        )}
                        {er.instagram_url && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Instagram: {truncate(er.instagram_url, 50)}
                          </p>
                        )}
                        {er.email_confidence !== null && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Confidence: {er.email_confidence}%
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* Company Evidence tab */}
        <TabsContent value="evidence">
          {companyEvidence ? (
            <div className="space-y-4">
              {/* Company research summary */}
              {companyEvidence.research && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-muted-foreground" />
                      Company Research
                    </CardTitle>
                    <CardDescription>
                      {companyEvidence.research.synthetic
                        ? 'Synthetic/illustrative research data — not from public company research.'
                        : `Research by ${companyEvidence.research.provider}. Confidence: ${companyEvidence.research.confidence !== null ? companyEvidence.research.confidence + '%' : 'not assessed'}.`}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <dl className="divide-y divide-border">
                      {companyEvidence.research.what_it_does && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">What they do</dt>
                          <dd className="text-sm">{companyEvidence.research.what_it_does}</dd>
                        </div>
                      )}
                      {companyEvidence.research.what_it_sells && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">What they sell</dt>
                          <dd className="text-sm">{companyEvidence.research.what_it_sells}</dd>
                        </div>
                      )}
                      {companyEvidence.research.who_it_serves && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Who they serve</dt>
                          <dd className="text-sm">{companyEvidence.research.who_it_serves}</dd>
                        </div>
                      )}
                      {companyEvidence.research.positioning && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Positioning</dt>
                          <dd className="text-sm">{companyEvidence.research.positioning}</dd>
                        </div>
                      )}
                      {companyEvidence.research.public_developments && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Public developments</dt>
                          <dd className="text-sm">{companyEvidence.research.public_developments}</dd>
                        </div>
                      )}
                      {companyEvidence.research.missing_information && Array.isArray(companyEvidence.research.missing_information) && companyEvidence.research.missing_information.length > 0 && (
                        <div className="py-3">
                          <dt className="text-xs text-muted-foreground font-medium mb-0.5">Missing information</dt>
                          <dd className="text-sm text-amber-600">
                            {companyEvidence.research.missing_information.map((item, i: number) => (
                              <div key={i}>• {String(item)}</div>
                            ))}
                          </dd>
                        </div>
                      )}
                    </dl>
                    <div className="mt-4 pt-3 border-t border-border text-xs text-muted-foreground">
                      <p>Research timestamp: {formatDate(companyEvidence.research.research_timestamp)}</p>
                      <p>Provider: {companyEvidence.research.provider}</p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Evidence items */}
              {companyEvidence.evidence.length > 0 ? (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Link2 className="h-4 w-4 text-muted-foreground" />
                      Evidence & Sources
                    </CardTitle>
                    <CardDescription>Supporting evidence collected during research.</CardDescription>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="divide-y divide-border">
                      {companyEvidence.evidence.map((ev, i) => (
                        <div key={i} className="py-3">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="text-sm font-medium">{String(ev.label || 'Source')}</p>
                              {String(ev.content || '') && (
                                <p className="text-xs text-muted-foreground mt-0.5">{truncate(String(ev.content), 150)}</p>
                              )}
                            </div>
                            {String(ev.url || '') && externalUrl(String(ev.url)) && (
                              <a href={ev.url as string} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1">
                                <Link2 className="h-3 w-3" />
                                Visit source
                              </a>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">
                            Type: {String(ev.evidence_type || 'unknown')}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="py-8 text-center text-sm text-muted-foreground">
                    No evidence items collected yet.
                  </CardContent>
                </Card>
              )}
            </div>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                <HelpCircle className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                Company evidence not available. This may mean no research has been conducted yet, or the evidence endpoint is not accessible.
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </TabsList>
      </div>
    </div>
  );
}

function formatLocation(parts: Array<string | null | undefined>): string {
  // Synthetic records often repeat the country inside `location`; collapse
  // duplicates so the demo does not show e.g. "Berlin, United States, United States".
  const tokens = parts
    .filter((v): v is string => Boolean(v))
    .flatMap(v => v.split(','))
    .map(v => v.trim())
    .filter(Boolean);
  return tokens.filter(
    (token, i) => tokens.findIndex(other => other.toLowerCase() === token.toLowerCase()) === i,
  ).join(', ');
}

function FitFactor({ label, value, verified }: { label: string; value: string; verified: boolean }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground uppercase tracking-wide">{label}</dt>
      <dd className="text-sm font-medium mt-0.5 flex items-center gap-1">
        {value}
        {verified ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <span className="text-muted-foreground italic">—</span>
        )}
      </dd>
    </div>
  );
}

function FitStep({ step, label, content }: { step: string; label: string; content: string }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
        {step}
      </div>
      <div>
        <p className="font-medium">{label}</p>
        <p className="text-sm text-muted-foreground mt-0.5">{content}</p>
      </div>
    </div>
  );
}
