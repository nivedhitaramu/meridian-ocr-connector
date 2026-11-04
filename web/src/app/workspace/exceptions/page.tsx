import Link from "next/link";

import { CheckBadge, errorLabel, JobBadge, when } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listExceptions } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { ReviewForm } from "../shipments/forms";

export const metadata = { title: "Exceptions | Meridian Intelligence" };

export default async function ExceptionsPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { organizationId, role, context } = await organizationFor(org);
  const exceptions = await listExceptions(context);
  const canReview = role !== "clerk";
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Exceptions</h1>
      {exceptions.length === 0 ? (
        <EmptyState title="Nothing needs review">
          <p>Mismatches and documents that need manual review appear here.</p>
        </EmptyState>
      ) : null}
      {exceptions.map((item) => (
        <Card key={item.job_id}>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <Link href={`/workspace/shipments/${item.shipment_id}?org=${organizationId}`} className="underline-offset-4 hover:underline">
                {item.reference}
              </Link>
              {item.check_status ? <CheckBadge status={item.check_status} /> : <JobBadge status={item.job_status} />}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p>{item.reason ?? errorLabel(item.error_class)}</p>
            <p className="text-muted-foreground text-xs tabular-nums">{when(item.created_at)}</p>
            {canReview ? (
              <ReviewForm organizationId={organizationId} jobId={item.job_id} />
            ) : (
              <p className="text-muted-foreground text-sm">A supervisor or admin can review this.</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
