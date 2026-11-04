import { CheckBadge, errorLabel, JobBadge } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, getObservability } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

export const metadata = { title: "Observability | Meridian Intelligence" };

const STAGES: [string, string][] = [
  ["ocr", "Read"],
  ["pii", "Mask"],
  ["llm", "Extract"],
  ["rule", "Check"],
];

function Timings({ timings }: { timings: Record<string, number> }) {
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {STAGES.map(([stage, label]) => (
        <div key={stage}>
          <dt className="text-muted-foreground text-sm">{label}</dt>
          <dd className="text-xl font-semibold tabular-nums">{timings[stage] ?? 0} ms</dd>
        </div>
      ))}
    </dl>
  );
}

function Counts({ title, counts }: { title: string; counts: Record<string, number> }) {
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
                <dt className="break-all">{key}</dt>
                <dd className="font-medium tabular-nums">{count}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

export default async function ObservabilityPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { context } = await organizationFor(org);
  const summary = await getObservability(context).catch((error) => {
    if (error instanceof ApiError && error.status === 403) return null;
    throw error;
  });
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Observability</h1>
        <p className="text-muted-foreground text-sm">Counts and timings from saved jobs. Document text and names are never recorded.</p>
      </header>
      {summary === null ? <EmptyState title="Only supervisors and admins can see this" /> : null}
      {summary?.latest === null ? (
        <EmptyState title="No finished jobs yet">
          <p>The latest trace appears here after a shipment is checked.</p>
        </EmptyState>
      ) : null}
      {summary?.latest ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                Latest trace
                {summary.latest.check_status ? <CheckBadge status={summary.latest.check_status} /> : <JobBadge status={summary.latest.job_status} />}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Timings timings={summary.latest.timings_ms} />
              {summary.latest.error_class ? <p className="text-sm">{errorLabel(summary.latest.error_class)}</p> : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Average over the last {summary.jobs_measured} jobs</CardTitle>
            </CardHeader>
            <CardContent>
              <Timings timings={summary.average_stage_ms} />
            </CardContent>
          </Card>
          <div className="grid gap-4 sm:grid-cols-2">
            <Counts title="Personal data masked, by type" counts={summary.entities_by_type} />
            <Counts title="Check results" counts={summary.checks_by_status} />
          </div>
        </>
      ) : null}
    </div>
  );
}
