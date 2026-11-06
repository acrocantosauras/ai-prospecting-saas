'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Briefcase,
  Target,
  Users,
  Plug,
  Settings,
  Zap,
  Menu,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/business-profile', label: 'Business Profile', icon: Briefcase },
  { href: '/icp', label: 'Ideal Customer Profile', icon: Target },
  { href: '/prospecting', label: 'Prospecting', icon: Zap },
  { href: '/prospects', label: 'Prospects', icon: Users },
  { href: '/integrations', label: 'Integrations', icon: Plug },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const renderLinks = (onNavigate?: () => void) => navItems.map(item => {
    const isActive =
      pathname === item.href ||
      (item.href !== '/' && pathname.startsWith(item.href));
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onNavigate}
        className={cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-primary/10 text-primary'
            : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
        )}
      >
        <item.icon className="h-4 w-4 shrink-0" />
        {item.label}
      </Link>
    );
  });

  return (
    <>
      <aside className="fixed left-0 top-0 z-40 hidden h-screen w-64 border-r border-border bg-card lg:flex lg:flex-col">
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b border-border px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" />
              <path d="M12 6v6l4 2" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold leading-none">Prospector</p>
            <p className="text-[10px] text-muted-foreground leading-tight">AI Prospecting SaaS</p>
          </div>
        </div>

        {/* Nav */}
        <nav aria-label="Primary navigation" className="flex-1 space-y-1 px-3 py-4">
          {renderLinks()}
        </nav>

        {/* Footer */}
        <div className="border-t border-border p-4">
          <div className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-green-500 text-[10px] font-bold text-white">
              NP
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium truncate">Demo Workspace</p>
              <p className="text-[10px] text-muted-foreground truncate">Northbridge Growth Partners</p>
            </div>
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground text-center">
            Synthetic demo mode — no real data
          </p>
        </div>
      </aside>

      <div className="fixed inset-x-0 top-0 z-50 border-b border-border bg-card lg:hidden">
        <div className="flex h-14 items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2" onClick={() => setMobileOpen(false)}>
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" />
                <path d="M12 6v6l4 2" />
              </svg>
            </span>
            <span className="text-sm font-semibold">Prospector</span>
          </Link>
          <button
            type="button"
            aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={mobileOpen}
            aria-controls="mobile-primary-navigation"
            onClick={() => setMobileOpen(open => !open)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
        {mobileOpen && (
          <nav
            id="mobile-primary-navigation"
            aria-label="Mobile primary navigation"
            className="relative z-50 space-y-1 border-t border-border bg-card px-3 py-2 shadow-lg"
            style={{ backgroundColor: 'var(--card)' }}
          >
            {renderLinks(() => setMobileOpen(false))}
          </nav>
        )}
      </div>
    </>
  );
}
