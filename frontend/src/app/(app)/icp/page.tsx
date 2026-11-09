'use client';

import { useEffect, useState, useCallback } from 'react';
import { getICPProfiles, getICPProfile, createICPProfile, updateICPProfile, ApiError } from '@/lib/api';
import { useWorkspaceSlug } from '@/lib/hooks/useAuth';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input, Textarea, Label, Select } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { SkeletonPage } from '@/components/ui/skeleton';
import { formatDate, cn } from '@/lib/utils';
import { Save, Plus } from 'lucide-react';
import type { ICPProfile } from '@/lib/types';

type FormState = {
  name: string;
  target_industries: string;
  sub_industries: string;
  target_countries: string;
  target_regions: string;
  company_size: string;
  employee_count_min: string;
  employee_count_max: string;
  revenue_min: string;
  revenue_max: string;
  preferred_company_types: string;
  target_audience: string;
  decision_maker_roles: string;
  additional_criteria: string;
  max_prospects: string;
  is_active: boolean;
};

const DEFAULT_FORM: FormState = {
  name: '',
  target_industries: '',
  sub_industries: '',
  target_countries: '',
  target_regions: '',
  company_size: '',
  employee_count_min: '',
  employee_count_max: '',
  revenue_min: '',
  revenue_max: '',
  preferred_company_types: '',
  target_audience: '',
  decision_maker_roles: '',
  additional_criteria: '',
  max_prospects: '20',
  is_active: true,
};

export default function ICPPage() {
  const toast = useToast();
  const [mode, setMode] = useState<'read' | 'edit'>('read');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [icps, setIcpProfiles] = useState<ICPProfile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedIcp, setSelectedIcp] = useState<ICPProfile | null>(null);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);

  const slug = useWorkspaceSlug();

  const loadICPs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getICPProfiles(slug);
      setIcpProfiles(data || []);
      setCreating(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load ICP profiles');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    getICPProfiles(slug)
      .then(data => {
        if (cancelled) return;
        const list = data || [];
        setIcpProfiles(list);
        setCreating(false);
        // The profile list is hidden when there is exactly one ICP, so select
        // it explicitly instead of showing an empty state for existing data.
        if (list.length > 0) {
          const first = list[0];
          setSelectedIcp(first);
          setSelectedId(first.id);
          setForm({
            name: first.name || '',
            target_industries: first.target_industries || '',
            sub_industries: first.sub_industries || '',
            target_countries: first.target_countries || '',
            target_regions: first.target_regions || '',
            company_size: first.company_size || '',
            employee_count_min: first.employee_count_min?.toString() || '',
            employee_count_max: first.employee_count_max?.toString() || '',
            revenue_min: first.revenue_min || '',
            revenue_max: first.revenue_max || '',
            preferred_company_types: first.preferred_company_types || '',
            target_audience: first.target_audience || '',
            decision_maker_roles: first.decision_maker_roles || '',
            additional_criteria: first.additional_criteria || '',
            max_prospects: first.max_prospects?.toString() || '20',
            is_active: first.is_active ?? true,
          });
        }
      })
      .catch(e => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : 'Failed to load ICP profiles');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const selectIcp = async (id: string) => {
    try {
      const data = await getICPProfile(id, slug);
      setSelectedIcp(data);
      setSelectedId(id);
      if (data) {
        setForm({
          name: data.name || '',
          target_industries: data.target_industries || '',
          sub_industries: data.sub_industries || '',
          target_countries: data.target_countries || '',
          target_regions: data.target_regions || '',
          company_size: data.company_size || '',
          employee_count_min: data.employee_count_min?.toString() || '',
          employee_count_max: data.employee_count_max?.toString() || '',
          revenue_min: data.revenue_min || '',
          revenue_max: data.revenue_max || '',
          preferred_company_types: data.preferred_company_types || '',
          target_audience: data.target_audience || '',
          decision_maker_roles: data.decision_maker_roles || '',
          additional_criteria: data.additional_criteria || '',
          max_prospects: data.max_prospects?.toString() || '20',
          is_active: data.is_active ?? true,
        });
      }
      setMode('read');
      setCreating(false);
    } catch (e) {
      toast.addToast({ type: 'error', title: 'Failed to load ICP', description: e instanceof ApiError ? e.message : 'Unknown error' });
    }
  };

  const startCreate = () => {
    setForm(DEFAULT_FORM);
    setSelectedIcp(null);
    setSelectedId(null);
    setMode('edit');
    setCreating(true);
  };

  const startEdit = () => {
    if (selectedIcp) setMode('edit');
  };

  const cancelEdit = () => {
    if (selectedIcp) {
      setSelectedIcp(selectedIcp);
      setForm({
        name: selectedIcp?.name || '',
        target_industries: selectedIcp?.target_industries || '',
        sub_industries: selectedIcp?.sub_industries || '',
        target_countries: selectedIcp?.target_countries || '',
        target_regions: selectedIcp?.target_regions || '',
        company_size: selectedIcp?.company_size || '',
        employee_count_min: selectedIcp?.employee_count_min?.toString() || '',
        employee_count_max: selectedIcp?.employee_count_max?.toString() || '',
        revenue_min: selectedIcp?.revenue_min || '',
        revenue_max: selectedIcp?.revenue_max || '',
        preferred_company_types: selectedIcp?.preferred_company_types || '',
        target_audience: selectedIcp?.target_audience || '',
        decision_maker_roles: selectedIcp?.decision_maker_roles || '',
        additional_criteria: selectedIcp?.additional_criteria || '',
        max_prospects: selectedIcp?.max_prospects?.toString() || '20',
        is_active: selectedIcp?.is_active ?? true,
      });
    }
    setMode('read');
    setCreating(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.addToast({ type: 'error', title: 'ICP name is required' });
      return;
    }
    const maxP = parseInt(form.max_prospects, 10);
    if (isNaN(maxP) || maxP < 1 || maxP > 100) {
      toast.addToast({ type: 'error', title: 'Maximum prospects must be between 1 and 100' });
      return;
    }

    setSaving(true);
    try {
      const payload = {
        workspace_id: slug,
        name: form.name,
        target_industries: form.target_industries || null,
        sub_industries: form.sub_industries || null,
        target_countries: form.target_countries || null,
        target_regions: form.target_regions || null,
        company_size: form.company_size || null,
        employee_count_min: form.employee_count_min ? parseInt(form.employee_count_min, 10) : null,
        employee_count_max: form.employee_count_max ? parseInt(form.employee_count_max, 10) : null,
        revenue_min: form.revenue_min || null,
        revenue_max: form.revenue_max || null,
        preferred_company_types: form.preferred_company_types || null,
        target_audience: form.target_audience || null,
        decision_maker_roles: form.decision_maker_roles || null,
        additional_criteria: form.additional_criteria || null,
        max_prospects: maxP,
        is_active: form.is_active,
      };

      let result: ICPProfile;
      if (creating) {
        result = await createICPProfile(payload);
        toast.addToast({ type: 'success', title: 'ICP profile created' });
        setCreating(false);
      } else if (selectedId) {
        const updatePayload: Partial<ICPProfile> = {};
        for (const [k, v] of Object.entries(payload)) {
          if (k !== 'workspace_id') (updatePayload as Record<string, unknown>)[k] = v;
        }
        result = await updateICPProfile(selectedId, updatePayload, slug);
        toast.addToast({ type: 'success', title: 'ICP updated' });
      } else {
        throw new Error('No ICP selected');
      }

      setSelectedIcp(result);
      const updated = await getICPProfiles(slug);
      setIcpProfiles(updated || []);
      setMode('read');
    } catch (e) {
      toast.addToast({ type: 'error', title: 'Save failed', description: e instanceof ApiError ? e.message : 'Unknown error' });
    } finally {
      setSaving(false);
    }
  };

  if (loading && icps.length === 0) {
    return (
      <div className="flex flex-col min-h-screen">
        <TopBar title="Ideal Customer Profile" subtitle="Define who you want to reach" />
        <SkeletonPage />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Ideal Customer Profile"
        subtitle="Configure who the prospecting engine should target"
        breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Ideal Customer Profile' }]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={startCreate}>
              <Plus className="h-4 w-4 mr-1.5" />
              New ICP
            </Button>
            {selectedIcp && mode === 'read' && (
              <Button variant="outline" size="sm" onClick={startEdit}>
                <Save className="h-4 w-4 mr-1.5" />
                Edit
              </Button>
            )}
            {mode === 'edit' && !creating && (
              <Button variant="ghost" size="sm" onClick={cancelEdit}>
                Cancel
              </Button>
            )}
          </div>
        }
      />

      <div className="p-6 space-y-6 max-w-4xl">
        {/* ICP list */}
        {icps.length > 1 && !creating && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">ICP Profiles</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border">
                {icps.map(icp => (
                  <button
                    key={icp.id}
                    onClick={() => selectIcp(icp.id)}
                    className={cn(
                      'w-full flex items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-secondary',
                      selectedId === icp.id ? 'bg-secondary/50' : '',
                    )}
                  >
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
                      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="12" cy="12" r="10" />
                        <circle cx="12" cy="12" r="6" />
                        <circle cx="12" cy="12" r="2" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{icp.name}</p>
                      <p className="text-xs text-muted-foreground">Max {icp.max_prospects} prospects · {formatDate(icp.updated_at)}</p>
                    </div>
                    <Badge variant={icp.is_active ? 'success' : 'secondary'}>
                      {icp.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Form */}
        {(creating || mode === 'edit') && (
          <Card className="border-primary/20">
            <CardHeader>
              <CardTitle className="text-base">{creating ? 'Create Ideal Customer Profile' : 'Edit ICP'}</CardTitle>
              <CardDescription>
                Define the characteristics of the companies and decision-makers you want to prospect.
                The prospecting engine uses this profile to find matching targets.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Identity */}
                <fieldset>
                  <legend className="text-sm font-medium text-muted-foreground mb-3">Identity</legend>
                  <div className="grid grid-cols-12 gap-4 items-start">
                    <div className="col-span-12">
                      <Label htmlFor="icp-name" className="mb-1.5">Profile Name <span className="text-red-500">*</span></Label>
                      <Input
                        id="icp-name"
                        value={form.name}
                        onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                        placeholder="Mid-Market Enterprise SaaS Buyers"
                        disabled={saving}
                      />
                    </div>
                  </div>
                </fieldset>

                {/* Geography */}
                <fieldset>
                  <legend className="text-sm font-medium text-muted-foreground mb-3">Geography</legend>
                  <div className="grid grid-cols-12 gap-4 items-start">
                    <div className="col-span-6">
                      <Label htmlFor="countries" className="mb-1.5">Target Countries</Label>
                      <Input
                        id="countries"
                        value={form.target_countries}
                        onChange={e => setForm(f => ({ ...f, target_countries: e.target.value }))}
                        placeholder="US, UK, Canada (comma separated)"
                        disabled={saving}
                      />
                      <p className="mt-1 text-xs text-muted-foreground">Comma-separated country names or ISO codes</p>
                    </div>
                    <div className="col-span-6">
                      <Label htmlFor="regions" className="mb-1.5">Regions & Cities</Label>
                      <Input
                        id="regions"
                        value={form.target_regions}
                        onChange={e => setForm(f => ({ ...f, target_regions: e.target.value }))}
                        placeholder="Northeast US, Bay Area, London"
                        disabled={saving}
                      />
                    </div>
                  </div>
                </fieldset>

                {/* Company characteristics */}
                <fieldset>
                  <legend className="text-sm font-medium text-muted-foreground mb-3">Company Characteristics</legend>
                  <div className="grid grid-cols-12 gap-4 items-start">
                    <div className="col-span-6">
                      <Label htmlFor="industries" className="mb-1.5">Target Industries</Label>
                      <Input
                        id="industries"
                        value={form.target_industries}
                        onChange={e => setForm(f => ({ ...f, target_industries: e.target.value }))}
                        placeholder="Technology, Financial Services, Healthcare"
                        disabled={saving}
                      />
                    </div>
                    <div className="col-span-6">
                      <Label htmlFor="sub-industries" className="mb-1.5">Sub-Industries</Label>
                      <Input
                        id="sub-industries"
                        value={form.sub_industries}
                        onChange={e => setForm(f => ({ ...f, sub_industries: e.target.value }))}
                        placeholder="SaaS, FinTech, HealthTech"
                        disabled={saving}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-12 gap-4 items-start mt-4">
                    <div className="col-span-4">
                      <Label htmlFor="company_size" className="mb-1.5">Company Size</Label>
                      <Select
                        id="company_size"
                        value={form.company_size}
                        onChange={e => setForm(f => ({ ...f, company_size: e.target.value }))}
                        disabled={saving}
                      >
                        <option value="">Select size…</option>
                        <option value="startup">Startup (seed–Series B)</option>
                        <option value="small">Small (11–50 employees)</option>
                        <option value="medium">Medium (51–200 employees)</option>
                        <option value="mid-market">Mid-Market (201–1000 employees)</option>
                        <option value="enterprise">Enterprise (1000+ employees)</option>
                      </Select>
                    </div>
                    <div className="col-span-4">
                      <Label htmlFor="emp_min" className="mb-1.5">Min Employees</Label>
                      <Input
                        id="emp_min"
                        type="number"
                        min="1"
                        value={form.employee_count_min}
                        onChange={e => setForm(f => ({ ...f, employee_count_min: e.target.value }))}
                        placeholder="10"
                        disabled={saving}
                      />
                    </div>
                    <div className="col-span-4">
                      <Label htmlFor="emp_max" className="mb-1.5">Max Employees</Label>
                      <Input
                        id="emp_max"
                        type="number"
                        min="1"
                        value={form.employee_count_max}
                        onChange={e => setForm(f => ({ ...f, employee_count_max: e.target.value }))}
                        placeholder="500"
                        disabled={saving}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-6 gap-4 items-start mt-4">
                    <div className="col-span-3">
                      <Label htmlFor="revenue_min" className="mb-1.5">Min Revenue</Label>
                      <Input
                        id="revenue_min"
                        value={form.revenue_min}
                        onChange={e => setForm(f => ({ ...f, revenue_min: e.target.value }))}
                        placeholder="$10M"
                        disabled={saving}
                      />
                    </div>
                    <div className="col-span-3">
                      <Label htmlFor="revenue_max" className="mb-1.5">Max Revenue</Label>
                      <Input
                        id="revenue_max"
                        value={form.revenue_max}
                        onChange={e => setForm(f => ({ ...f, revenue_max: e.target.value }))}
                        placeholder="$500M"
                        disabled={saving}
                      />
                    </div>
                  </div>
                  <div className="col-span-12">
                    <Label htmlFor="company_types" className="mb-1.5">Preferred Company Types</Label>
                    <Input
                      id="company_types"
                      value={form.preferred_company_types}
                      onChange={e => setForm(f => ({ ...f, preferred_company_types: e.target.value }))}
                      placeholder="Public, Private, Venture-backed"
                      disabled={saving}
                    />
                  </div>
                </fieldset>

                {/* Audience & roles */}
                <fieldset>
                  <legend className="text-sm font-medium text-muted-foreground mb-3">Audience & Roles</legend>
                  <div className="grid grid-cols-12 gap-4 items-start">
                    <div className="col-span-6">
                      <Label htmlFor="target_audience" className="mb-1.5">Target Audience</Label>
                      <Textarea
                        id="target_audience"
                        value={form.target_audience}
                        onChange={e => setForm(f => ({ ...f, target_audience: e.target.value }))}
                        placeholder="VPs of Engineering, CTOs, Product Directors at growing tech companies"
                        rows={2}
                        disabled={saving}
                      />
                    </div>
                    <div className="col-span-6">
                      <Label htmlFor="decision_maker_roles" className="mb-1.5">Decision-Maker Roles</Label>
                      <Textarea
                        id="decision_maker_roles"
                        value={form.decision_maker_roles}
                        onChange={e => setForm(f => ({ ...f, decision_maker_roles: e.target.value }))}
                        placeholder="VP Engineering, CTO, Head of Product"
                        rows={2}
                        disabled={saving}
                      />
                      <p className="mt-1 text-xs text-muted-foreground">The prospecting engine will prioritize these titles when finding contacts.</p>
                    </div>
                  </div>
                </fieldset>

                {/* Additional criteria */}
                <fieldset>
                  <legend className="text-sm font-medium text-muted-foreground mb-3">Additional Criteria</legend>
                  <div className="col-span-12">
                    <Label htmlFor="additional_criteria" className="mb-1.5">Additional Criteria</Label>
                    <Textarea
                      id="additional_criteria"
                      value={form.additional_criteria}
                      onChange={e => setForm(f => ({ ...f, additional_criteria: e.target.value }))}
                      placeholder="Any additional filters or notes for the prospecting engine..."
                      rows={2}
                      disabled={saving}
                    />
                  </div>
                </fieldset>

                {/* Prospect count */}
                <fieldset>
                  <legend className="text-sm font-medium text-muted-foreground mb-3">Batch Size</legend>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <Label htmlFor="max_prospects" className="mb-1.5">Maximum Prospects per Batch</Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="max_prospects"
                          type="number"
                          min="1"
                          max="100"
                          value={form.max_prospects}
                          onChange={e => setForm(f => ({ ...f, max_prospects: e.target.value }))}
                          disabled={saving}
                        />
                        <span className="text-sm text-muted-foreground">/ 100 max</span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        The platform enforces a hard maximum of 100 prospects per batch.
                      </p>
                    </div>
                  </div>
                </fieldset>

                {/* Read view */}
                {selectedIcp && !creating && (
                  <div className="col-span-12 pt-4 border-t border-border">
                    <p className="text-xs font-medium text-muted-foreground mb-2">Current saved ICP</p>
                    <dl className="grid grid-cols-12 gap-x-4 gap-y-2 text-sm">
                      {selectedIcp.target_industries && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Industries</dt>
                          <dd className="col-span-9">{selectedIcp.target_industries}</dd>
                        </>
                      )}
                      {selectedIcp.target_countries && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Countries</dt>
                          <dd className="col-span-9">{selectedIcp.target_countries}</dd>
                        </>
                      )}
                      {selectedIcp.company_size && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Company Size</dt>
                          <dd className="col-span-9">{selectedIcp.company_size}</dd>
                        </>
                      )}
                      {selectedIcp.decision_maker_roles && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Decision-Maker Roles</dt>
                          <dd className="col-span-9 text-sm text-muted-foreground">{selectedIcp.decision_maker_roles}</dd>
                        </>
                      )}
                      <>
                        <dt className="col-span-3 text-muted-foreground">Max Prospects</dt>
                        <dd className="col-span-9 font-medium">{selectedIcp.max_prospects}</dd>
                      </>
                    </dl>
                  </div>
                )}

                <div className="flex items-center justify-between pt-4 border-t border-border">
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <Save className="h-4 w-4" />
                    {creating ? 'Create ICP' : 'Save changes'}
                  </div>
                  <Button type="submit" disabled={saving}>
                    <Save className="h-4 w-4 mr-1.5" />
                    {saving ? 'Saving…' : creating ? 'Create ICP' : 'Save Changes'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Read view */}
        {!creating && mode === 'read' && selectedIcp && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">{selectedIcp.name}</CardTitle>
                  <CardDescription>Last updated {formatDate(selectedIcp.updated_at)}</CardDescription>
                </div>
                <Badge variant={selectedIcp.is_active ? 'success' : 'secondary'}>
                  {selectedIcp.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-12 gap-x-6 gap-y-4 text-sm">
                {selectedIcp.target_industries ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Industries</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.target_industries}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Industries</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.sub_industries ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Sub-Industries</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.sub_industries}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Sub-Industries</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.target_countries ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Countries</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.target_countries}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Countries</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.target_regions ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Regions</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.target_regions}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Regions</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.company_size ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Company Size</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.company_size}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Company Size</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.employee_count_min !== null || selectedIcp.employee_count_max !== null ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Employee Range</dt>
                    <dd className="col-span-12 lg:col-span-9">
                      {selectedIcp.employee_count_min} – {selectedIcp.employee_count_max}
                    </dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Employee Range</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.revenue_min || selectedIcp.revenue_max ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Revenue Range</dt>
                    <dd className="col-span-12 lg:col-span-9">
                      {selectedIcp.revenue_min} – {selectedIcp.revenue_max}
                    </dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Revenue Range</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.preferred_company_types ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Company Types</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.preferred_company_types}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Company Types</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.target_audience ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Target Audience</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.target_audience}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Target Audience</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.decision_maker_roles ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Decision-Maker Roles</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.decision_maker_roles}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Decision-Maker Roles</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not specified</dd>
                  </>
                )}
                {selectedIcp.additional_criteria ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Additional Criteria</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedIcp.additional_criteria}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Additional Criteria</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">None</dd>
                  </>
                )}
                <>
                  <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Max Prospects</dt>
                  <dd className="col-span-12 lg:col-span-9 font-medium">{selectedIcp.max_prospects}</dd>
                </>
              </div>
            </CardContent>
          </Card>
        )}

        {!creating && mode === 'read' && !selectedIcp && (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="flex h-12 w-12 mx-auto rounded-full bg-muted items-center justify-center mb-4">
                <svg className="h-6 w-6 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <circle cx="12" cy="12" r="6" />
                  <circle cx="12" cy="12" r="2" />
                </svg>
              </div>
              <p className="text-sm font-medium">No ICP profile yet</p>
              <p className="text-xs text-muted-foreground mt-1">Create an ideal customer profile to guide prospect discovery.</p>
              <Button className="mt-4" onClick={startCreate}>
                <Plus className="h-4 w-4 mr-1.5" />
                Create ICP Profile
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
