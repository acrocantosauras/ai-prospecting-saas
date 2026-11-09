import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ToastProvider } from '@/components/ui/toast';
import { Sidebar } from '@/components/ui/sidebar';
import { AuthProvider } from '@/lib/hooks/useAuth';
import './globals.css';

const inter = Inter({
  variable: '--font-inter',
  subsets: ['latin'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Prospector — AI Prospecting SaaS',
  description: 'Synthetic demo prospect discovery and qualification platform.',
  icons: {
    icon: [
      {
        url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="%231e3a5f"/><path d="M50 20v30l25 10" stroke="white" stroke-width="6" fill="none" stroke-linecap="round"/></svg>',
        type: 'image/svg+xml',
      },
    ],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex">
        <AuthProvider>
          <ToastProvider>
            <Sidebar />
            <main className="flex-1 min-w-0 flex flex-col pt-14 lg:pt-0 lg:pl-64">
              {children}
            </main>
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
