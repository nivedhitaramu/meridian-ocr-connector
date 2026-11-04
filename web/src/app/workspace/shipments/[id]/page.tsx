import { notFound } from "next/navigation";

import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, getJob, getShipment } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { RefreshWhileRunning, StartCheckForm, UploadForm } from "../forms";
import { Result } from "../result";

export default async function ShipmentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ org?: string }>;
}) {
  const { id } = await params;
  const { org } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const shipment = await getShipment(context, id).catch((error) => {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });
  const latest = shipment.jobs[0];
  const job = latest ? await getJob(context, latest.id) : null;
  const running = latest?.status === "queued" || latest?.status === "running";
  const waiting = shipment.documents.filter((d) => d.processing_status === "pending").length;
  return (
    <div className="space-y-6">
      <RefreshWhileRunning active={running} />
      <h1 className="text-2xl font-semibold tracking-tight break-words">{shipment.reference}</h1>
      <Card>
        <CardHeader>
          <CardTitle>Documents</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <UploadForm organizationId={organizationId} shipmentId={shipment.id} />
          <p className="text-sm">
            {waiting === 0 ? "No documents are waiting." : `${waiting} ${waiting === 1 ? "document is" : "documents are"} ready to check.`}
          </p>
          <StartCheckForm organizationId={organizationId} shipmentId={shipment.id} disabled={waiting === 0 || running} />
        </CardContent>
      </Card>
      {job ? (
        <Result job={job} />
      ) : (
        <EmptyState title="Not checked yet">
          <p>Upload the invoice and packing list, then check quantities.</p>
        </EmptyState>
      )}
    </div>
  );
}
