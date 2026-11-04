import Link from "next/link";

import { jobLabel, when } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getAnalytics, listShipments } from "@/lib/api";
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

export default async function DashboardPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const [summary, recent] = await Promise.all([getAnalytics(context), listShipments(context, 10)]);
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
          <CardTitle>Recent shipments</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Reference</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.map((shipment) => (
                <TableRow key={shipment.id}>
                  <TableCell>
                    <Link href={`/workspace/shipments/${shipment.id}?org=${organizationId}`} className="underline-offset-4 hover:underline">
                      {shipment.reference}
                    </Link>
                  </TableCell>
                  <TableCell className="capitalize">{shipment.status}</TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">{when(shipment.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
