'use client';

import { useEffect, useState, useCallback } from 'react';
import { getClientProfiles, getClientProfile, createClientProfile, updateClientProfile, ApiError } from '@/lib/api';
import { useWorkspaceSlug } from '@/lib/hooks/useAuth';
import type { ClientProfile } from '@/lib/types';
import { TopBar } from '@/components/ui/topbar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input, Textarea, Label } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { SkeletonPage } from '@/components/ui/skeleton';
import { formatDate, cn, truncate } from '@/lib/utils';
import { Save, Plus, Edit2 } from 'lucide-react';

type FormState = {
  name: string;
  website: string;
  description: string;
  products_services: string;
  value_proposition: string;
  target_audience: string;
  problems_solved: string;
  usp: string;
  is_active: boolean;
};

const DEFAULT_FORM: FormState = {
  name: '',
  website: '',
  description: '',
  products_services: '',
  value_proposition: '',
  target_audience: '',
  problems_solved: '',
  usp: '',
  is_active: true,
};

export default function BusinessProfilePage() {
  const toast = useToast();
  const [mode, setMode] = useState<'read' | 'edit'>('read');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<ClientProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<ClientProfile | null>(null);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slug = useWorkspaceSlug();

  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getClientProfiles(slug);
      setProfiles(data as ClientProfile[] || []);
      setCreating(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load profiles');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    getClientProfiles(slug)
      .then(data => {
        if (cancelled) return;
        const list = (data as ClientProfile[]) || [];
        setProfiles(list);
        setCreating(false);
        // With a single profile the list is hidden, so select it explicitly.
        // Otherwise the page wrongly shows the "no profile yet" empty state.
        if (list.length > 0) {
          const first = list[0];
          setSelectedProfile(first);
          setSelectedId(first.id);
          setForm({
            name: first.name || '',
            website: first.website || '',
            description: first.description || '',
            products_services: first.products_services || '',
            value_proposition: first.value_proposition || '',
            target_audience: first.target_audience || '',
            problems_solved: first.problems_solved || '',
            usp: first.usp || '',
            is_active: first.is_active ?? true,
          });
        }
      })
      .catch(e => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : 'Failed to load profiles');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const selectProfile = async (id: string) => {
    try {
      const data = await getClientProfile(id, slug);
      setSelectedProfile(data || null);
      setSelectedId(id);
      if (data) {
        setForm({
          name: data.name || '',
          website: data.website || '',
          description: data.description || '',
          products_services: data.products_services || '',
          value_proposition: data.value_proposition || '',
          target_audience: data.target_audience || '',
          problems_solved: data.problems_solved || '',
          usp: data.usp || '',
          is_active: data.is_active ?? true,
        });
      }
      setMode('read');
      setCreating(false);
    } catch (e) {
      toast.addToast({ type: 'error', title: 'Failed to load profile', description: e instanceof ApiError ? e.message : 'Unknown error' });
    }
  };

  const startCreate = () => {
    setForm(DEFAULT_FORM);
    setSelectedProfile(null);
    setSelectedId(null);
    setMode('edit');
    setCreating(true);
  };

  const startEdit = () => {
    if (selectedProfile) {
      setMode('edit');
    }
  };

  const cancelEdit = () => {
    if (selectedProfile) {
      setSelectedProfile(selectedProfile);
      setForm({
        name: selectedProfile?.name || '',
        website: selectedProfile?.website || '',
        description: selectedProfile?.description || '',
        products_services: selectedProfile?.products_services || '',
        value_proposition: selectedProfile?.value_proposition || '',
        target_audience: selectedProfile?.target_audience || '',
        problems_solved: selectedProfile?.problems_solved || '',
        usp: selectedProfile?.usp || '',
        is_active: selectedProfile?.is_active ?? true,
      });
    }
    setMode('read');
    setCreating(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.addToast({ type: 'error', title: 'Business name is required' });
      return;
    }
    setSaving(true);
    try {
      let result: ClientProfile;
      if (creating) {
        result = await createClientProfile({
          workspace_id: slug,
          ...form,
        });
        toast.addToast({ type: 'success', title: 'Profile created' });
        setCreating(false);
      } else if (selectedId) {
        result = await updateClientProfile(selectedId, form, slug);
        toast.addToast({ type: 'success', title: 'Profile updated' });
      } else {
        throw new Error('No profile selected');
      }
      setSelectedProfile(result);
      const updated = await getClientProfiles(slug);
      setProfiles(updated || []);
      setMode('read');
    } catch (e) {
      toast.addToast({ type: 'error', title: 'Save failed', description: e instanceof ApiError ? e.message : 'Unknown error' });
    } finally {
      setSaving(false);
    }
  };



  if (loading && profiles.length === 0) {
    return (
      <div className="flex flex-col min-h-screen">
        <TopBar title="Business Profile" subtitle="Your company information" />
        <SkeletonPage />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar
        title="Business Profile"
        subtitle="Who you are and what you offer"
        breadcrumbs={[{ label: 'Overview', href: '/' }, { label: 'Business Profile' }]}
        actions={
          <div className="flex items-center gap-2">
            {!creating && mode === 'read' && (
              <>
                <Button variant="outline" size="sm" onClick={startCreate}>
                  <Plus className="h-4 w-4 mr-1.5" />
                  New Profile
                </Button>
                {selectedProfile && (
                  <Button variant="outline" size="sm" onClick={startEdit}>
                    <Edit2 className="h-4 w-4 mr-1.5" />
                    Edit
                  </Button>
                )}
              </>
            )}
            {(creating || mode === 'edit') && (
              <Button variant="ghost" size="sm" onClick={cancelEdit}>
                Cancel
              </Button>
            )}
          </div>
        }
      />

      <div className="p-6 space-y-6 max-w-3xl">
        {/* Profile list */}
        {profiles.length > 1 && !creating && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Profiles</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border">
                {profiles.map(p => (
                  <button
                    key={p.id}
                    onClick={() => selectProfile(p.id)}
                    className={cn(
                      'w-full flex items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-secondary',
                      selectedId === p.id ? 'bg-secondary/50' : '',
                    )}
                  >
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
                      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                        <path d="M3 7l9 6 9-6" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{p.name}</p>
                      <p className="text-xs text-muted-foreground">{formatDate(p.updated_at)}</p>
                    </div>
                    <Badge variant={p.is_active ? 'success' : 'secondary'}>
                      {p.is_active ? 'Active' : 'Inactive'}
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
              <CardTitle className="text-base">{creating ? 'Create Business Profile' : 'Edit Business Profile'}</CardTitle>
              <CardDescription>Tell us about your business. This helps us tailor prospect discovery to your offering.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-12 gap-4 items-start">
                  <div className="col-span-12 lg:col-span-6">
                    <Label htmlFor="name" className="mb-1.5">Business Name <span className="text-red-500">*</span></Label>
                    <Input
                      id="name"
                      value={form.name}
                      onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                      placeholder="Acme Corporation"
                      disabled={saving}
                    />
                  </div>
                  <div className="col-span-12 lg:col-span-6">
                    <Label htmlFor="website" className="mb-1.5">Website</Label>
                    <Input
                      id="website"
                      type="url"
                      value={form.website}
                      onChange={e => setForm(f => ({ ...f, website: e.target.value }))}
                      placeholder="https://acme.com"
                      disabled={saving}
                    />
                  </div>
                </div>

                <div className="col-span-12">
                  <Label htmlFor="description" className="mb-1.5">Business Description</Label>
                  <Textarea
                    id="description"
                    value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="What does your business do? Describe your core operations, market, and history in a few sentences."
                    rows={3}
                    disabled={saving}
                  />
                  <p className="mt-1.5 text-xs text-muted-foreground">This becomes the foundation for prospect research context.</p>
                </div>

                <div className="col-span-12">
                  <Label htmlFor="products_services" className="mb-1.5">Products & Services</Label>
                  <Textarea
                    id="products_services"
                    value={form.products_services}
                    onChange={e => setForm(f => ({ ...f, products_services: e.target.value }))}
                    placeholder="List your main products and services..."
                    rows={3}
                    disabled={saving}
                  />
                </div>

                <div className="grid grid-cols-12 gap-4 items-start">
                  <div className="col-span-12 lg:col-span-6">
                    <Label htmlFor="value_proposition" className="mb-1.5">Value Proposition</Label>
                    <Textarea
                      id="value_proposition"
                      value={form.value_proposition}
                      onChange={e => setForm(f => ({ ...f, value_proposition: e.target.value }))}
                      placeholder="Why do customers choose you over alternatives?"
                      rows={3}
                      disabled={saving}
                    />
                  </div>
                  <div className="col-span-12 lg:col-span-6">
                    <Label htmlFor="usp" className="mb-1.5">Unique Selling Proposition</Label>
                    <Textarea
                      id="usp"
                      value={form.usp}
                      onChange={e => setForm(f => ({ ...f, usp: e.target.value }))}
                      placeholder="Your single strongest differentiator..."
                      rows={3}
                      disabled={saving}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-12 gap-4 items-start">
                  <div className="col-span-12 lg:col-span-6">
                    <Label htmlFor="target_audience" className="mb-1.5">Target Audience</Label>
                    <Textarea
                      id="target_audience"
                      value={form.target_audience}
                      onChange={e => setForm(f => ({ ...f, target_audience: e.target.value }))}
                      placeholder="Who are your ideal customers? (job titles, departments, company roles)"
                      rows={3}
                      disabled={saving}
                    />
                  </div>
                  <div className="col-span-12 lg:col-span-6">
                    <Label htmlFor="problems_solved" className="mb-1.5">Problems Solved</Label>
                    <Textarea
                      id="problems_solved"
                      value={form.problems_solved}
                      onChange={e => setForm(f => ({ ...f, problems_solved: e.target.value }))}
                      placeholder="What business problems do you solve for your customers?"
                      rows={3}
                      disabled={saving}
                    />
                  </div>
                </div>

                {/* Preview */}
                {selectedProfile && !creating && (
                  <div className="col-span-12 pt-4 border-t border-border">
                    <p className="text-xs font-medium text-muted-foreground mb-2">Current saved profile</p>
                    <dl className="grid grid-cols-12 gap-x-4 gap-y-2 text-sm">
                      {selectedProfile.name && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Name</dt>
                          <dd className="col-span-9">{selectedProfile.name}</dd>
                        </>
                      )}
                      {selectedProfile.website && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Website</dt>
                          <dd className="col-span-9">{selectedProfile.website}</dd>
                        </>
                      )}
                      {selectedProfile.target_audience && (
                        <>
                          <dt className="col-span-3 text-muted-foreground">Target Audience</dt>
                          <dd className="col-span-9 text-sm text-muted-foreground">{truncate(selectedProfile.target_audience, 100)}</dd>
                        </>
                      )}
                    </dl>
                  </div>
                )}

                <div className="flex items-center justify-between pt-4 border-t border-border">
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <Save className="h-4 w-4" />
                    {creating ? 'Create' : 'Save changes'}
                  </div>
                  <Button type="submit" disabled={saving}>
                    <Save className="h-4 w-4 mr-1.5" />
                    {saving ? 'Saving…' : creating ? 'Create Profile' : 'Save Changes'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Read view */}
        {!creating && mode === 'read' && selectedProfile && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">{selectedProfile.name}</CardTitle>
                  <CardDescription>Last updated {formatDate(selectedProfile.updated_at)}</CardDescription>
                </div>
                <Badge variant={selectedProfile.is_active ? 'success' : 'secondary'}>
                  {selectedProfile.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-12 gap-x-6 gap-y-4 text-sm">
                {selectedProfile.description ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Description</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedProfile.description}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Description</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not provided</dd>
                  </>
                )}
                {selectedProfile.products_services ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Products & Services</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedProfile.products_services}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Products & Services</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not provided</dd>
                  </>
                )}
                {selectedProfile.value_proposition ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Value Proposition</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedProfile.value_proposition}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Value Proposition</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not provided</dd>
                  </>
                )}
                {selectedProfile.target_audience ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Target Audience</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedProfile.target_audience}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Target Audience</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not provided</dd>
                  </>
                )}
                {selectedProfile.problems_solved ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Problems Solved</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedProfile.problems_solved}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Problems Solved</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not provided</dd>
                  </>
                )}
                {selectedProfile.usp ? (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">USP</dt>
                    <dd className="col-span-12 lg:col-span-9">{selectedProfile.usp}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">USP</dt>
                    <dd className="col-span-12 lg:col-span-9 text-muted-foreground italic">Not provided</dd>
                  </>
                )}
                {selectedProfile.website && (
                  <>
                    <dt className="col-span-12 lg:col-span-3 text-muted-foreground font-medium">Website</dt>
                    <dd className="col-span-12 lg:col-span-9">
                      <a href={selectedProfile.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-sm">
                        {selectedProfile.website}
                        <svg className="ml-1 h-3 w-3 inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      </a>
                    </dd>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {!creating && mode === 'read' && !selectedProfile && (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="flex h-12 w-12 mx-auto rounded-full bg-muted items-center justify-center mb-4">
                <Briefcase className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">No business profile yet</p>
              <p className="text-xs text-muted-foreground mt-1">Create a profile to give the prospecting engine context about your business.</p>
              <Button className="mt-4" onClick={startCreate}>
                <Plus className="h-4 w-4 mr-1.5" />
                Create Profile
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// Inline icons needed
function Briefcase({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
      <path d="M3 7l9 6 9-6" />
    </svg>
  );
}
