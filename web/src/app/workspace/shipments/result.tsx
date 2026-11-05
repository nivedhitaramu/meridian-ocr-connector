import { CheckBadge, DOCUMENT_LABELS, errorLabel, JobBadge } from "@/components/labels";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Job, JobDocument } from "@/lib/api";

const FIELDS: [string, string][] = [
  ["invoice_number", "Invoice or reference"],
  ["shipper_name", "Shipper"],
  ["receiver_name", "Receiver"],
  ["shipment_date", "Date"],
  ["total_quantity", "Total quantity"],
  ["total_weight_kg", "Total weight (kg)"],
];

function fieldValue(document: JobDocument, field: string): string {
  const value = document.fields[field];
  if (value === null || value === undefined) return "Not found";
  if (field === "total_quantity" && document.quantity_unit) return `${value} ${document.quantity_unit}`;
  return String(value);
}

function Comparison({ documents }: { documents: JobDocument[] }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Field</TableHead>
            {documents.map((document) => (
              <TableHead key={document.id}>{DOCUMENT_LABELS[document.document_type ?? "unknown"] ?? "Document"}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {FIELDS.map(([field, label]) => {
            const differs = new Set(documents.map((d) => fieldValue(d, field))).size > 1;
            return (
              <TableRow key={field}>
                <TableCell className="font-medium">{label}</TableCell>
                {documents.map((document) => (
                  <TableCell key={document.id} className={differs ? "font-medium" : undefined}>
                    {fieldValue(document, field)}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

export function Result({ job }: { job: Job }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Latest check {job.check ? <CheckBadge status={job.check.status} /> : <JobBadge status={job.status} />}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {job.check ? <p>{job.check.reason}</p> : null}
        {!job.check && job.error_class ? <p>{errorLabel(job.error_class)} Check the paper documents by hand.</p> : null}
        {job.documents.length > 0 ? <Comparison documents={job.documents} /> : null}
        {job.documents.length > 0 ? (
          <p className="text-muted-foreground text-xs">Weight is shown for reference, and never changes the status. Source files are deleted after each check.{job.config_version ? ` Rules version: ${job.config_version}.` : ""}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
