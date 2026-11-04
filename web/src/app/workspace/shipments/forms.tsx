"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { createShipmentAction, type FormState, reviewAction, startJobAction, uploadAction } from "./actions";

const INITIAL: FormState = { error: null };

function Problem({ error }: { error: string | null }) {
  return error ? (
    <p role="alert" className="text-destructive text-sm">
      {error}
    </p>
  ) : null;
}

export function NewShipmentForm({ organizationId }: { organizationId: string }) {
  const [state, action, pending] = useActionState(createShipmentAction, INITIAL);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="organization" value={organizationId} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-72">
          <label htmlFor="shipment-reference" className="text-sm font-medium">
            Reference
          </label>
          <Input id="shipment-reference" name="reference" required maxLength={100} />
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Creating..." : "Create shipment"}
        </Button>
      </div>
      <Problem error={state.error} />
    </form>
  );
}

export function UploadForm({ organizationId, shipmentId }: { organizationId: string; shipmentId: string }) {
  const [state, action, pending] = useActionState(uploadAction, INITIAL);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (!pending && !state.error) form.current?.reset();
  }, [pending, state]);
  return (
    <form ref={form} action={action} className="space-y-2">
      <input type="hidden" name="organization" value={organizationId} />
      <input type="hidden" name="shipment" value={shipmentId} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-80">
          <label htmlFor="document-file" className="text-sm font-medium">
            Document
          </label>
          <Input id="document-file" name="file" type="file" required accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" />
        </div>
        <Button type="submit" variant="outline" disabled={pending}>
          {pending ? "Uploading..." : "Upload"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">PDF, PNG or JPEG, up to 10 MB. Synthetic documents only.</p>
      <Problem error={state.error} />
    </form>
  );
}

export function StartCheckForm({ organizationId, shipmentId, disabled }: { organizationId: string; shipmentId: string; disabled: boolean }) {
  const [state, action, pending] = useActionState(startJobAction, INITIAL);
  const [attempt] = useState(() => crypto.randomUUID());
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="organization" value={organizationId} />
      <input type="hidden" name="shipment" value={shipmentId} />
      <input type="hidden" name="attempt" value={attempt} />
      <Button type="submit" disabled={disabled || pending}>
        {pending ? "Starting..." : "Check quantities"}
      </Button>
      <Problem error={state.error} />
    </form>
  );
}

/** Keeps the page current while a job runs. Saved results still come from the server each time. */
export function RefreshWhileRunning({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), 3000);
    return () => clearInterval(timer);
  }, [active, router]);
  return null;
}

export function ReviewForm({ organizationId, jobId }: { organizationId: string; jobId: string }) {
  const [state, action, pending] = useActionState(reviewAction, INITIAL);
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="organization" value={organizationId} />
      <input type="hidden" name="job" value={jobId} />
      <div className="space-y-1">
        <label htmlFor={`reason-${jobId}`} className="text-sm font-medium">
          Reason
        </label>
        <Input id={`reason-${jobId}`} name="reason" required maxLength={300} />
        <p className="text-muted-foreground text-xs">Describe what was checked. Leave out names and contact details.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label htmlFor={`quantity-${jobId}`} className="block text-sm font-medium">
            Corrected quantity (optional)
          </label>
          <Input id={`quantity-${jobId}`} name="corrected_quantity" inputMode="numeric" pattern="[0-9]*" className="w-40" />
        </div>
        <Button type="submit" name="action" value="resolve" disabled={pending}>
          Resolve
        </Button>
        <Button type="submit" name="action" value="follow_up" variant="outline" disabled={pending}>
          Needs follow-up
        </Button>
      </div>
      <Problem error={state.error} />
    </form>
  );
}
