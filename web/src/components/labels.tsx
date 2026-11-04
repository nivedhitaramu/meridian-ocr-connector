import { Badge } from "@/components/ui/badge";

/** Words for values the API returns. The API decides every status; these only name them. */
const JOB_LABELS: Record<string, string> = {
  queued: "Waiting",
  running: "Reading",
  succeeded: "Finished",
  failed: "Failed",
  manual_review: "Needs manual review",
};

const ERROR_LABELS: Record<string, string> = {
  manual_review_residual_pii: "Personal data may remain, so it wasn't sent to the model.",
  manual_review_unknown_type: "The scan is too unclear to redact safely.",
  manual_review_no_boxes: "No readable text was found to redact.",
  manual_review_required: "The scan is too unclear to read.",
  manual_review_too_many_pages: "The scan has too many pages to send safely.",
  too_many_pages: "The PDF has too many pages.",
  queue_unavailable: "The check couldn't start.",
  no_documents: "There were no documents to read.",
  file_unavailable: "A stored file couldn't be read.",
};

export const DOCUMENT_LABELS: Record<string, string> = {
  commercial_invoice: "Commercial invoice",
  packing_list: "Packing list",
  delivery_receipt: "Delivery receipt",
  unknown: "Unknown document",
};

export function jobLabel(status: string): string {
  return JOB_LABELS[status] ?? status;
}

export function errorLabel(errorClass: string | null): string {
  if (!errorClass) return "";
  return ERROR_LABELS[errorClass] ?? "The document couldn't be read.";
}

export function CheckBadge({ status }: { status: string }) {
  const variant = status === "Mismatch" ? "destructive" : status === "Match" ? "default" : "secondary";
  return <Badge variant={variant}>{status}</Badge>;
}

export function JobBadge({ status }: { status: string }) {
  const variant = status === "failed" || status === "manual_review" ? "destructive" : "secondary";
  return <Badge variant={variant}>{jobLabel(status)}</Badge>;
}

export function when(iso: string | null): string {
  return iso ? `${iso.slice(0, 16).replace("T", " ")} UTC` : "";
}
