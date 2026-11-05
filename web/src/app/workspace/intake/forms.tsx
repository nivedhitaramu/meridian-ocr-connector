"use client";

import { useActionState, useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { assignAction, discardAction, type IntakeState, uploadBatchAction } from "./actions";

const INITIAL: IntakeState = { error: null };

function Problem({ error }: { error: string | null }) {
  return error ? (
    <p role="alert" className="text-destructive text-sm">
      {error}
    </p>
  ) : null;
}

export function UploadBatchForm({ organizationId }: { organizationId: string }) {
  const [state, action, pending] = useActionState(uploadBatchAction, INITIAL);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (!pending && !state.error) form.current?.reset();
  }, [pending, state]);
  return (
    <form ref={form} action={action} className="space-y-2">
      <input type="hidden" name="organization" value={organizationId} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-96">
          <label htmlFor="intake-files" className="text-sm font-medium">
            Documents
          </label>
          <Input id="intake-files" name="files" type="file" multiple required accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" />
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Uploading..." : "Upload and group"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">Up to 20 PDF, PNG or JPEG files, about 10 MB in total here. Synthetic documents only.</p>
      <Problem error={state.error} />
    </form>
  );
}

export function ReviewItem({ organizationId, id, suggestion, label }: { organizationId: string; id: string; suggestion: string; label: string }) {
  const [assigned, assign, assigning] = useActionState(assignAction, INITIAL);
  const [discarded, discard, discarding] = useActionState(discardAction, INITIAL);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-3">
        <form action={assign} className="flex flex-wrap items-end gap-3">
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="id" value={id} />
          <div className="space-y-1">
            <label htmlFor={`reference-${id}`} className="text-sm font-medium">
              Shipment reference
            </label>
            <Input id={`reference-${id}`} name="reference" defaultValue={suggestion} required maxLength={100} className="w-56" />
          </div>
          <Button type="submit" disabled={assigning}>
            {assigning ? "Saving..." : "Assign"}
          </Button>
        </form>
        <form action={discard}>
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="id" value={id} />
          <Button type="submit" variant="outline" disabled={discarding} aria-label={`Discard ${label}`}>
            Discard
          </Button>
        </form>
      </div>
      <Problem error={assigned.error ?? discarded.error} />
    </div>
  );
}
