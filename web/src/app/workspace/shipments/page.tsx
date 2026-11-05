import Link from "next/link";

import { when } from "@/components/labels";
import { ListFilter } from "@/components/list-filter";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listShipments } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { NewShipmentForm } from "./forms";

export const metadata = { title: "Shipments | Meridian Intelligence" };

const STATUSES: [string, string][] = [
  ["open", "Open"],
  ["processing", "Processing"],
  ["checked", "Checked"],
];

export default async function ShipmentsPage({ searchParams }: { searchParams: Promise<{ org?: string; q?: string; status?: string }> }) {
  const { org, q = "", status = "" } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const shipments = await listShipments(context, { q, status });
  const filtered = Boolean(q.trim() || status);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Shipments</h1>
      <Card>
        <CardHeader>
          <CardTitle>New shipment</CardTitle>
        </CardHeader>
        <CardContent>
          <NewShipmentForm organizationId={organizationId} />
        </CardContent>
      </Card>
      <ListFilter
        action="/workspace/shipments"
        organizationId={organizationId}
        searchLabel="Search references"
        statusLabel="Status"
        q={q}
        status={status}
        statuses={STATUSES}
      />
      {shipments.length === 0 && filtered ? <EmptyState title="No shipments match this search" /> : null}
      {shipments.length === 0 && !filtered ? (
        <EmptyState title="No shipments yet">
          <p>Create one above, then upload its invoice and packing list.</p>
        </EmptyState>
      ) : null}
      {shipments.length > 0 ? (
        <Card>
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
                {shipments.map((shipment) => (
                  <TableRow key={shipment.id}>
                    <TableCell>
                      <Link href={`/workspace/shipments/${shipment.id}?org=${organizationId}`} className="font-medium underline-offset-4 hover:underline">
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
      ) : null}
    </div>
  );
}
