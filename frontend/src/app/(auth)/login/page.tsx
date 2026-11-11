'use client';

import { useEffect, useState, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { logout as apiLogout } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from '@/components/ui/toast';
import { Loader2, Mail, Lock } from 'lucide-react';
import { ApiError } from '@/lib/api/client';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const auth = useAuth();
  const { login, loading: authLoading } = auth;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  useEffect(() => {
    if (!authLoading && auth.session?.workspaces?.length) {
      const target = searchParams.get('redirect') ?? '/dashboard';
      const params = new URLSearchParams(searchParams.toString());
      params.delete('redirect');
      const qs = params.toString() ? `?${params.toString()}` : '';
      router.replace(`${target}${qs}`);
    }
  }, [authLoading, auth.session, router, searchParams]);

  const validate = (): boolean => {
    let ok = true;
    if (!email.trim()) {
      setEmailError('Email is required');
      ok = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setEmailError('Enter a valid email address');
      ok = false;
    } else {
      setEmailError(null);
    }
    if (!password) {
      setPasswordError('Password is required');
      ok = false;
    } else if (password.length < 1) {
      setPasswordError('Password is required');
      ok = false;
    } else {
      setPasswordError(null);
    }
    return ok;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submittingRef.current) return;
    if (!validate()) return;
    submittingRef.current = true;
    setSubmitting(true);
    setFormError(null);
    try {
      await login(email.trim().toLowerCase(), password);
      const params = new URLSearchParams(searchParams.toString());
      params.delete('redirect');
      const qs = params.toString() ? `?${params.toString()}` : '';
      router.push(`/dashboard${qs}`);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : 'Login failed';
      setFormError(message);
      toast.addToast({ type: 'error', title: 'Login failed', description: message });
    } finally {
      setSubmitting(false);
      submittingRef.current = false;
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[calc(100vh-8rem)] p-6">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-lg">Sign in</CardTitle>
          <CardDescription>
            Enter your workspace credentials to continue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {formError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {formError}
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email" className="flex items-center gap-1.5">
                <Mail className="h-4 w-4" />
                Email
              </Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (emailError) setEmailError(null);
                }}
                placeholder="you@example.com"
                disabled={submitting}
                className={emailError ? 'border-red-300' : ''}
              />
              {emailError && (
                <p className="text-xs text-red-600">{emailError}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password" className="flex items-center gap-1.5">
                <Lock className="h-4 w-4" />
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (passwordError) setPasswordError(null);
                }}
                placeholder="Enter your password"
                disabled={submitting}
                className={passwordError ? 'border-red-300' : ''}
              />
              {passwordError && (
                <p className="text-xs text-red-600">{passwordError}</p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-[calc(100vh-8rem)]">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
