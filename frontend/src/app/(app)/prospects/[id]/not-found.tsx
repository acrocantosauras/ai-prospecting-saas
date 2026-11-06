'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { AlertCircle } from 'lucide-react';

export default function ProspectNotFound() {
  const router = useRouter();

  return (
    <Card>
      <CardContent className="py-12 text-center">
        <div className="flex h-12 w-12 mx-auto rounded-full bg-muted items-center justify-center mb-4">
          <AlertCircle className="h-6 w-6 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium">Prospect not found</p>
        <p className="text-xs text-muted-foreground mt-1 mb-4">
          This prospect may have been removed or the link is invalid.
        </p>
        <Link href="/prospects">
          <Button>
            Back to Prospects
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
