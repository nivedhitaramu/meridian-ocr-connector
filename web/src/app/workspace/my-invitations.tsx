"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MyInvitation } from "@/lib/api";

import { acceptInvitationAction, declineInvitationAction, type FormState } from "./actions";
import { useReloadAfter } from "./shipments/forms";

const INITIAL: FormState = { error: null };

function Offer({ invitation }: { invitation: MyInvitation }) {
  const [accepted, accept, accepting] = useActionState(acceptInvitationAction, INITIAL);
  const [declined, decline, declining] = useActionState(declineInvitationAction, INITIAL);
  useReloadAfter(accepted);
  useReloadAfter(declined);
  const busy = accepting || declining || accepted.reload || declined.reload;
  const name = invitation.organization_name;
  return (
    <li className="space-y-2 py-3 first:pt-0 last:pb-0">
      <p className="text-sm">
        <span className="font-medium">{name}</span> invited you as a <span className="capitalize">{invitation.role}</span>
        {invitation.invited_by ? <> (sent by {invitation.invited_by})</> : null}.
      </p>
      <p className="text-muted-foreground text-xs">Organization names aren&apos;t verified. Accept only if you know the sender.</p>
      <div className="flex flex-wrap gap-2">
        <form action={accept}>
          <input type="hidden" name="invitation" value={invitation.id} />
          <Button type="submit" size="sm" disabled={busy} aria-label={`Accept invitation to ${name}`}>
            Accept
          </Button>
        </form>
        <form action={decline}>
          <input type="hidden" name="invitation" value={invitation.id} />
          <Button type="submit" variant="outline" size="sm" disabled={busy} aria-label={`Decline invitation to ${name}`}>
            Decline
          </Button>
        </form>
      </div>
      {accepted.error || declined.error ? (
        <p role="alert" className="text-destructive text-sm">
          {accepted.error ?? declined.error}
        </p>
      ) : null}
    </li>
  );
}

export function MyInvitations({ invitations }: { invitations: MyInvitation[] }) {
  if (invitations.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {invitations.map((invitation) => (
            <Offer key={invitation.id} invitation={invitation} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
