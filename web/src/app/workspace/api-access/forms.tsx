"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { type AccessState, addWebhookAction, createKeyAction, removeWebhookAction, revokeKeyAction, rotateKeyAction } from "./actions";

const INITIAL: AccessState = { error: null, secret: null };

function Result({ state, what }: { state: AccessState; what: string }) {
  if (state.error) {
    return (
      <p role="alert" className="text-destructive text-sm">
        {state.error}
      </p>
    );
  }
  if (!state.secret) return null;
  return (
    <div role="status" className="bg-muted space-y-1 rounded-md p-3 text-sm">
      <p className="font-medium">Copy this {what} now. It won&apos;t be shown again.</p>
      <code className="block break-all">{state.secret}</code>
    </div>
  );
}

export function CreateKeyForm({ organizationId }: { organizationId: string }) {
  const [state, action, pending] = useActionState(createKeyAction, INITIAL);
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="organization" value={organizationId} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-72">
          <label htmlFor="key-name" className="text-sm font-medium">
            Key name
          </label>
          <Input id="key-name" name="name" required maxLength={100} />
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Creating..." : "Create key"}
        </Button>
      </div>
      <Result state={state} what="key" />
    </form>
  );
}

export function KeyActions({ organizationId, id, name }: { organizationId: string; id: string; name: string }) {
  const [rotated, rotate, rotating] = useActionState(rotateKeyAction, INITIAL);
  const [revoked, revoke, revoking] = useActionState(revokeKeyAction, INITIAL);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-end gap-2">
        <form action={rotate}>
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="id" value={id} />
          <Button type="submit" variant="outline" size="sm" disabled={rotating} aria-label={`Replace ${name}`}>
            Replace
          </Button>
        </form>
        <form action={revoke}>
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="id" value={id} />
          <Button type="submit" variant="outline" size="sm" disabled={revoking} aria-label={`Revoke ${name}`}>
            Revoke
          </Button>
        </form>
      </div>
      <Result state={rotated} what="key" />
      <Result state={revoked} what="key" />
    </div>
  );
}

export function AddWebhookForm({ organizationId }: { organizationId: string }) {
  const [state, action, pending] = useActionState(addWebhookAction, INITIAL);
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="organization" value={organizationId} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-96">
          <label htmlFor="webhook-url" className="text-sm font-medium">
            HTTPS address
          </label>
          <Input id="webhook-url" name="url" type="url" required maxLength={500} />
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Adding..." : "Add webhook"}
        </Button>
      </div>
      <Result state={state} what="signing secret" />
    </form>
  );
}

export function RemoveWebhookForm({ organizationId, id, url }: { organizationId: string; id: string; url: string }) {
  const [state, action, pending] = useActionState(removeWebhookAction, INITIAL);
  return (
    <form action={action} className="space-y-2 text-right">
      <input type="hidden" name="organization" value={organizationId} />
      <input type="hidden" name="id" value={id} />
      <Button type="submit" variant="outline" size="sm" disabled={pending} aria-label={`Remove ${url}`}>
        Remove
      </Button>
      <Result state={state} what="secret" />
    </form>
  );
}
