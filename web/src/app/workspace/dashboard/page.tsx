import Link from "next/link";

import { CheckBadge, JobBadge, jobLabel, when } from "@/components/labels";
import { ListFilter } from "@/components/list-filter";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getAnalytics, listJobs } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

export const metadata = { title: "Dashboard | Meridian Intelligence" };

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <p className="text-muted-foreground text-sm">{label}</p>
        <p className="text-3xl font-semibold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

function Counts({ title, counts, label }: { title: string; counts: Record<string, number>; label?: (key: string) => string }) {
  const rows = Object.entries(counts).sort(([, a], [, b]) => b - a);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">None yet.</p>
        ) : (
          <dl className="space-y-2 text-sm">
            {rows.map(([key, count]) => (
              <div key={key} className="flex justify-between gap-4">
                <dt>{label ? label(key) : key}</dt>
                <dd className="font-medium tabular-nums">{count}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

const JOB_STATUSES: [string, string][] = ["queued", "running", "succeeded", "failed", "manual_review"].map((status) => [status, jobLabel(status)]);

export default async function DashboardPage({ searchParams }: { searchParams: Promise<{ org?: string; q?: string; status?: string }> }) {
  const { org, q = "", status = "" } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const [summary, history] = await Promise.all([getAnalytics(context), listJobs(context, { q, status })]);
  if (summary.shipments === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <EmptyState title="No activity yet">
          <p>
            <Link href={`/workspace/shipments?org=${organizationId}`} className="underline underline-offset-4">
              Create a shipment
            </Link>{" "}
            to see counts here.
          </p>
        </EmptyState>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
      <div className="grid gap-4 sm:grid-cols-2">
        <Stat label="Shipments" value={summary.shipments} />
        <Stat label="Open exceptions" value={summary.open_exceptions} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Counts title="Check results" counts={summary.checks_by_status} />
        <Counts title="Jobs" counts={summary.jobs_by_status} label={jobLabel} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Processing history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ListFilter
            action="/workspace/dashboard"
            organizationId={organizationId}
            searchLabel="Search references"
            statusLabel="Job status"
            q={q}
            status={status}
            statuses={JOB_STATUSES}
          />
          {history.length === 0 ? (
            <p className="text-muted-foreground text-sm">No jobs match.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Reference</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead>Started</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.map((job) => (
                    <TableRow key={job.id}>
                      <TableCell>
                        <Link href={`/workspace/shipments/${job.shipment_id}?org=${organizationId}`} className="underline-offset-4 hover:underline">
                          {job.reference}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <JobBadge status={job.status} />
                      </TableCell>
                      <TableCell>{job.check_status ? <CheckBadge status={job.check_status} /> : null}</TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">{when(job.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
