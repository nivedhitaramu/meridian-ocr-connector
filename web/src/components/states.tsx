import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-3xl border border-dashed border-neutral-300 bg-white p-8">
      <h2 className="font-heading text-xl font-semibold">{title}</h2>
      {children ? <div className="text-muted-foreground mt-2 max-w-prose space-y-4 text-sm">{children}</div> : null}
    </div>
  );
}

export function ErrorState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div role="alert" className="border-destructive/40 rounded-3xl border bg-white p-6">
      <h2 className="text-destructive font-heading text-lg font-semibold">{title}</h2>
      {children ? <div className="text-muted-foreground mt-2 max-w-prose text-sm">{children}</div> : null}
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
