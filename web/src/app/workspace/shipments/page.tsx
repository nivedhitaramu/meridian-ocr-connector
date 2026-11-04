import Link from "next/link";

import { when } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listShipments } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { NewShipmentForm } from "./forms";

export const metadata = { title: "Shipments | Meridian Intelligence" };

export default async function ShipmentsPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const shipments = await listShipments(context);
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
      {shipments.length === 0 ? (
        <EmptyState title="No shipments yet">
          <p>Create one above, then upload its invoice and packing list.</p>
        </EmptyState>
      ) : (
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
      )}
    </div>
  );
}
