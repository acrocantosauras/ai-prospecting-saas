import { clsx, type ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return '—';
  return score.toFixed(0);
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-muted-foreground';
  if (score >= 70) return 'text-green-600';
  if (score >= 40) return 'text-amber-600';
  return 'text-red-600';
}

export function scoreBg(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-muted';
  if (score >= 70) return 'bg-green-50 text-green-700';
  if (score >= 40) return 'bg-amber-50 text-amber-700';
  return 'bg-red-50 text-red-700';
}

export function readinessColor(ready: boolean | null | undefined): string {
  if (ready === null || ready === undefined) return 'text-muted-foreground';
  return ready ? 'text-green-600' : 'text-muted-foreground';
}

export function readinessLabel(ready: boolean | null | undefined): string {
  if (ready === null || ready === undefined) return 'Pending';
  return ready ? 'Ready' : 'Not ready';
}

export function confidenceColor(confidence: string | null | undefined): string {
  if (!confidence) return 'text-muted-foreground';
  const c = confidence.toLowerCase();
  if (c.includes('verified')) return 'text-green-600';
  if (c.includes('invalid') || c.includes('unavailable')) return 'text-red-500';
  return 'text-amber-600';
}

export function stageIndex(stage: string | null | undefined): number {
  const stages: string[] = [
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
  if (!stage) return 0;
  const idx = stages.indexOf(stage);
  return idx >= 0 ? idx : 0;
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export function capitalize(str: string | null | undefined): string {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function truncate(str: string | null | undefined, maxLen = 120): string {
  if (!str) return '';
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '…';
}

export function linkify(url: string | null | undefined, label?: string): string {
  if (!url) return label || '';
  try {
    const u = new URL(url);
    if (u.protocol === 'http:' || u.protocol === 'https:') {
      return label || url;
    }
  } catch {
    // not a url
  }
  return label || url;
}

export function externalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    if (u.protocol === 'http:' || u.protocol === 'https:') {
      return url;
    }
  } catch {
    return null;
  }
  return null;
}

export function parseCommaList(str: string | null | undefined): string[] {
  if (!str) return [];
  return str.split(',').map(s => s.trim()).filter(Boolean);
}

export function joinCommaList(items: string[]): string {
  return items.map(s => s.trim()).filter(Boolean).join(', ');
}
