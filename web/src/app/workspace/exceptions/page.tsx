
import { CheckBadge, errorLabel, JobBadge, when } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listExceptions } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { ReviewForm, SubmitForm } from "../shipments/forms";

export const metadata = { title: "Exceptions | Meridian Intelligence" };

const REVIEW_WORDS: Record<string, string> = {
  submit: "Sent for approval",
  approve: "Step approved",
  follow_up: "Needs follow-up",
  resolve: "Resolved",
};

export default async function ExceptionsPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const exceptions = await listExceptions(context);
  const waiting = exceptions.filter((item) => item.approval.can_act && (item.approval.submitted || item.approval.approved > 0)).length;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Exceptions</h1>
      {waiting > 0 ? (
        <p role="status" className="text-sm font-medium">
          {waiting === 1 ? "1 case is" : `${waiting} cases are`} waiting for your approval.
        </p>
      ) : null}
      {exceptions.length === 0 ? (
        <EmptyState title="Nothing needs review">
          <p>Mismatches and documents that need manual review appear here.</p>
        </EmptyState>
      ) : null}
      {exceptions.map((item) => (
        <Card key={item.job_id}>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <a href={`/workspace/shipments/${item.shipment_id}?org=${organizationId}`} className="underline-offset-4 hover:underline">
                {item.reference}
              </a>
              {item.check_status ? <CheckBadge status={item.check_status} /> : <JobBadge status={item.job_status} />}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p>{item.reason ?? errorLabel(item.error_class)}</p>
            <p className="text-muted-foreground text-xs tabular-nums">{when(item.created_at)}</p>
            <p className="text-sm">
              {item.approval.approved} of {item.approval.required} {item.approval.required === 1 ? "approval" : "approvals"} recorded. Next:{" "}
              <span className="capitalize">{item.approval.next_role}</span>.
            </p>
            {item.history.length > 0 ? (
              <ol className="space-y-1 text-sm">
                {item.history.map((entry) => (
                  <li key={entry.id}>
                    <span className="font-medium">{REVIEW_WORDS[entry.action] ?? entry.action}:</span> {entry.reason}{" "}
                    <span className="text-muted-foreground text-xs tabular-nums">{when(entry.created_at)}</span>
                  </li>
                ))}
              </ol>
            ) : null}
            {item.approval.can_act ? (
              <ReviewForm organizationId={organizationId} jobId={item.job_id} lastStep={item.approval.is_last_step} />
            ) : item.approval.submitted ? (
              <p className="text-muted-foreground text-sm">Sent for approval. Someone else needs to act next.</p>
            ) : (
              <SubmitForm organizationId={organizationId} jobId={item.job_id} />
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
