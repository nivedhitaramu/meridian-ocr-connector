
import { DOCUMENT_LABELS, when } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listIntake } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { ReloadWhenFinished } from "../shipments/forms";
import { ReviewItem, UploadBatchForm } from "./forms";

export const metadata = { title: "Intake | Meridian Intelligence" };

const REASONS: Record<string, string> = {
  poor_scan: "The scan is too unclear to trust.",
  no_reference: "No reference was found.",
  conflicting_references: "The document shows more than one reference.",
  unreadable: "The file couldn't be read.",
  unknown_type: "The document type wasn't recognized.",
  duplicate_type: "This batch has more than one of this document for the reference.",
  similar_reference: "This reference is very close to another, which may be a misread.",
  shipment_already_checked: "This shipment has already been checked.",
  no_matching_document: "No other document or shipment confirms this reference.",
};

const STATUSES: Record<string, string> = {
  queued: "Reading",
  grouped: "Grouped automatically",
  assigned: "Assigned by a person",
  discarded: "Discarded",
  expired: "File removed",
  failed: "Couldn't start",
};

export default async function IntakePage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { organizationId, context } = await organizationFor(org);
  const items = await listIntake(context);
  const waiting = items.filter((item) => item.status === "needs_review");
  const others = items.filter((item) => item.status !== "needs_review");
  return (
    <div className="space-y-6">
      <ReloadWhenFinished statusUrl={items.some((item) => item.status === "queued") ? `/workspace/intake/status?org=${organizationId}` : null} />
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Intake</h1>
        <p className="text-muted-foreground text-sm">
          Upload documents together. A clear reference joins its shipment, and anything uncertain waits here. You still start each check.
        </p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Upload a batch</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadBatchForm organizationId={organizationId} />
        </CardContent>
      </Card>
      {items.length === 0 ? <EmptyState title="Nothing uploaded yet" /> : null}
      {waiting.map((item) => (
        <Card key={item.id}>
          <CardHeader>
            <CardTitle>{DOCUMENT_LABELS[item.document_type ?? "unknown"] ?? "Unknown document"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">{REASONS[item.reason ?? ""] ?? "This needs a person to check it."}</p>
            <p className="text-muted-foreground text-xs tabular-nums">Uploaded {when(item.created_at)}. Files waiting about an hour are removed.</p>
            <ReviewItem organizationId={organizationId} id={item.id} suggestion={item.reference ?? ""} label={DOCUMENT_LABELS[item.document_type ?? "unknown"] ?? "document"} />
          </CardContent>
        </Card>
      ))}
      {others.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Recent documents</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Reference</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {others.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{DOCUMENT_LABELS[item.document_type ?? ""] ?? "Not read yet"}</TableCell>
                    <TableCell>
                      {item.shipment_id ? (
                        <a href={`/workspace/shipments/${item.shipment_id}?org=${organizationId}`} className="underline-offset-4 hover:underline">
                          {item.reference ?? "Open shipment"}
                        </a>
                      ) : (
                        item.reference
                      )}
                    </TableCell>
                    <TableCell>{STATUSES[item.status] ?? item.status}</TableCell>
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
