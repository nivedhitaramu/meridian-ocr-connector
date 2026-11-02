"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { type FormState, startOrganization } from "./actions";

const INITIAL: FormState = { error: null };

export function StartOrganizationForm() {
  const [state, action, pending] = useActionState(startOrganization, INITIAL);
  return (
    <form action={action} className="max-w-sm space-y-3">
      <div className="space-y-1">
        <label htmlFor="organization-name" className="text-foreground text-sm font-medium">
          Organization name
        </label>
        <Input
          id="organization-name"
          name="name"
          required
          maxLength={200}
          aria-describedby={state.error ? "organization-error" : undefined}
        />
      </div>
      {state.error ? (
        <p id="organization-error" role="alert" className="text-destructive text-sm">
          {state.error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? "Creating..." : "Create organization"}
      </Button>
    </form>
  );
}
