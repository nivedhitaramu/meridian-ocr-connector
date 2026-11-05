"use client";

import { useActionState } from "react";

import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditEvent, Invitation, Member, Organization, Role } from "@/lib/api";

import { approvalStepsAction, cancelInvitationAction, changeRoleAction, inviteAction, removeMemberAction, renameAction, retentionAction, type SettingsFormState } from "./actions";

const INITIAL: SettingsFormState = { error: null, saved: false };
const ROLES: Role[] = ["clerk", "supervisor", "admin"];
const SELECT_CLASS =
  "border-input bg-background focus-visible:ring-ring/50 h-8 rounded-md border px-2 text-sm capitalize outline-none focus-visible:ring-3";

const ACTION_LABELS: Record<string, string> = {
  "organization.created": "Organization created",
  "organization.renamed": "Organization renamed",
  "member.added": "Member added",
  "member.removed": "Member removed",
  "member.role_changed": "Role changed",
  "member.invited": "Member invited",
  "invitation.cancelled": "Invitation cancelled",
  "invitation.declined": "Invitation declined",
  "session.started": "Signed in",
  "document.uploaded": "Document uploaded",
  "review.recorded": "Review recorded",
  "approval.submitted": "Sent for approval",
  "approval.steps_changed": "Approval steps changed",
  "api_key.created": "API key created",
  "api_key.rotated": "API key replaced",
  "api_key.revoked": "API key revoked",
  "webhook.added": "Webhook added",
  "webhook.removed": "Webhook removed",
  "intake.uploaded": "Batch uploaded",
  "intake.grouped": "Document grouped automatically",
  "intake.assigned": "Document assigned by a person",
  "intake.discarded": "Document discarded",
  "retention.changed": "Retention changed",
  "retention.applied": "Old records deleted",
};

function FormMessage({ state, success }: { state: SettingsFormState; success?: string }) {
  if (state.error) {
    return (
      <p role="alert" className="text-destructive text-sm">
        {state.error}
      </p>
    );
  }
  return state.saved && success ? <p className="text-muted-foreground text-sm">{success}</p> : null;
}

function RenameForm({ organization }: { organization: Organization }) {
  const [state, action, pending] = useActionState(renameAction, INITIAL);
  return (
    <form action={action} className="max-w-md space-y-3">
      <input type="hidden" name="organization" value={organization.id} />
      <div className="space-y-1">
        <label htmlFor="settings-name" className="text-sm font-medium">
          Organization name
        </label>
        <Input id="settings-name" name="name" defaultValue={organization.name} required maxLength={200} />
      </div>
      <FormMessage state={state} success="Saved." />
      <Button type="submit" disabled={pending}>
        {pending ? "Saving..." : "Save name"}
      </Button>
    </form>
  );
}

function ApprovalForm({ organization }: { organization: Organization }) {
  const [state, action, pending] = useActionState(approvalStepsAction, INITIAL);
  const steps = organization.approval_steps.join(",");
  const current = steps === "admin" ? "admin" : steps === "supervisor,admin" ? "both" : "supervisor";
  return (
    <form action={action} className="max-w-md space-y-3">
      <input type="hidden" name="organization" value={organization.id} />
      <div className="space-y-1">
        <label htmlFor="settings-approval" className="block text-sm font-medium">
          Who approves an exception?
        </label>
        <select id="settings-approval" name="steps" defaultValue={current} className={SELECT_CLASS + " w-full normal-case"}>
          <option value="supervisor">A supervisor or admin</option>
          <option value="admin">An admin</option>
          <option value="both">A supervisor, then a different admin</option>
        </select>
      </div>
      <FormMessage state={state} success="Saved." />
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Saving..." : "Save approval steps"}
      </Button>
    </form>
  );
}

function RetentionForm({ organization }: { organization: Organization }) {
  const [state, action, pending] = useActionState(retentionAction, INITIAL);
  return (
    <form action={action} className="max-w-md space-y-3">
      <input type="hidden" name="organization" value={organization.id} />
      <div className="space-y-1">
        <label htmlFor="settings-retention" className="text-sm font-medium">
          Keep shipment records for (days)
        </label>
        <Input id="settings-retention" name="days" inputMode="numeric" defaultValue={organization.retention_days ?? ""} aria-describedby="settings-retention-help" />
        <p id="settings-retention-help" className="text-muted-foreground text-xs">
          Leave empty to keep them. Otherwise, older shipments and their results are permanently deleted each night. The activity log stays.
        </p>
      </div>
      <FormMessage state={state} success="Saved." />
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Saving..." : "Save retention"}
      </Button>
    </form>
  );
}

function InviteForm({ organizationId }: { organizationId: string }) {
  const [state, action, pending] = useActionState(inviteAction, INITIAL);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="organization" value={organizationId} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-auto sm:max-w-xs sm:min-w-0 sm:flex-1">
          <label htmlFor="member-email" className="text-sm font-medium">
            Email
          </label>
          <Input id="member-email" name="email" type="email" required maxLength={320} />
        </div>
        <div className="space-y-1">
          <label htmlFor="member-role" className="block text-sm font-medium">
            Role
          </label>
          <select id="member-role" name="role" defaultValue="clerk" className={SELECT_CLASS}>
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Inviting..." : "Invite"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        We don&apos;t send email yet, so tell them to sign in with this address. They join only after they accept, and the invitation lasts 7 days.
      </p>
      <FormMessage state={state} success="Invited." />
    </form>
  );
}

function InvitationRow({ invitation, organizationId }: { invitation: Invitation; organizationId: string }) {
  const [state, action, pending] = useActionState(cancelInvitationAction, INITIAL);
  return (
    <TableRow>
      <TableCell className="min-w-52 break-all whitespace-normal">
        {invitation.email}
        <FormMessage state={state} />
      </TableCell>
      <TableCell className="capitalize">{invitation.role}</TableCell>
      <TableCell>{invitation.expired ? "Expired" : `Until ${invitation.expires_at.slice(0, 10)}`}</TableCell>
      <TableCell className="text-right">
        <form action={action}>
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="invitation" value={invitation.id} />
          <Button type="submit" variant="ghost" size="sm" disabled={pending} aria-label={`Cancel invitation for ${invitation.email}`}>
            Cancel
          </Button>
        </form>
      </TableCell>
    </TableRow>
  );
}

function Invitations({ invitations, organizationId }: { invitations: Invitation[]; organizationId: string }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Invited</h3>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {invitations.map((invitation) => (
              <InvitationRow key={invitation.id} invitation={invitation} organizationId={organizationId} />
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function MemberRow({ member, organizationId }: { member: Member; organizationId: string }) {
  const [roleState, roleAction, rolePending] = useActionState(changeRoleAction, INITIAL);
  const [removeState, removeAction, removePending] = useActionState(removeMemberAction, INITIAL);
  return (
    <TableRow>
      <TableCell className="min-w-52 break-all whitespace-normal">
        {member.email}
        <FormMessage state={roleState} />
        <FormMessage state={removeState} />
      </TableCell>
      <TableCell>
        <form action={roleAction} className="flex items-center gap-2">
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="user" value={member.user_id} />
          <select aria-label={`Role for ${member.email}`} name="role" defaultValue={member.role} className={SELECT_CLASS}>
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <Button type="submit" variant="outline" size="sm" disabled={rolePending}>
            Save
          </Button>
        </form>
      </TableCell>
      <TableCell className="text-right">
        <form action={removeAction}>
          <input type="hidden" name="organization" value={organizationId} />
          <input type="hidden" name="user" value={member.user_id} />
          <Button type="submit" variant="ghost" size="sm" disabled={removePending} aria-label={`Remove ${member.email}`}>
            Remove
          </Button>
        </form>
      </TableCell>
    </TableRow>
  );
}

function ReadOnlyMembers({ members }: { members: Member[] }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Role</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((member) => (
            <TableRow key={member.user_id}>
              <TableCell>{member.email}</TableCell>
              <TableCell className="capitalize">{member.role}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function SettingsView({
  organization,
  members,
  invitations,
  events,
}: {
  organization: Organization;
  members: Member[] | null;
  invitations: Invitation[] | null;
  events: AuditEvent[] | null;
}) {
  const isAdmin = organization.role === "admin";
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground text-sm">
          {organization.name}. Your role is <span className="capitalize">{organization.role}</span>.
        </p>
      </header>

      {isAdmin ? (
        <Card>
          <CardHeader>
            <CardTitle>Organization</CardTitle>
          </CardHeader>
          <CardContent>
            <RenameForm organization={organization} />
            <div className="mt-6">
              <ApprovalForm organization={organization} />
            </div>
            <div className="mt-6">
              <RetentionForm organization={organization} />
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Team</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {members === null ? (
            <p className="text-muted-foreground text-sm">Only supervisors and admins can see the team list.</p>
          ) : isAdmin ? (
            <>
              <InviteForm organizationId={organization.id} />
              {invitations?.length ? <Invitations invitations={invitations} organizationId={organization.id} /> : null}
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Email</TableHead>
                      <TableHead>Role</TableHead>
                      <TableHead className="text-right">
                        <span className="sr-only">Actions</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {members.map((member) => (
                      <MemberRow key={member.user_id} member={member} organizationId={organization.id} />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : (
            <ReadOnlyMembers members={members} />
          )}
        </CardContent>
      </Card>

      {events !== null ? (
        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {events.length === 0 ? (
              <EmptyState title="No activity yet" />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>When (UTC)</TableHead>
                      <TableHead>What</TableHead>
                      <TableHead>Record</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {events.map((event, index) => (
                      <TableRow key={`${event.created_at}-${index}`}>
                        <TableCell className="whitespace-nowrap tabular-nums">
                          {event.created_at.slice(0, 16).replace("T", " ")}
                        </TableCell>
                        <TableCell>{ACTION_LABELS[event.action] ?? event.action}</TableCell>
                        <TableCell className="text-muted-foreground font-mono text-xs">{event.target ?? ""}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
