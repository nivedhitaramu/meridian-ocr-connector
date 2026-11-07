import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { ContainerArt } from "@/components/landing/art";
import { EmptyState } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, getMe, getOrganization, listMembers, listMyInvitations, type Member } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

import { MyInvitations } from "./my-invitations";
import { StartOrganizationForm } from "./start-organization-form";

async function membersIfAllowed(organizationId: string): Promise<Member[] | null> {
  try {
    return await listMembers(await apiContext(organizationId));
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) return null; // clerks don't see the list
    throw error;
  }
}

export default async function WorkspacePage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const context = await apiContext();
  const me = await getMe(context);
  const invitations = await listMyInvitations(context);

  if (me.memberships.length === 0) {
    return (
      <div className="space-y-6">
        <MyInvitations invitations={invitations} />
        <EmptyState title="Create your organization">
          <p>Your shipments and team live in an organization. You become its first admin.</p>
          <p>Joining a team instead? Ask an admin there to invite {me.email}.</p>
          <StartOrganizationForm />
        </EmptyState>
      </div>
    );
  }

  const chosen = me.memberships.find((m) => m.organization_id === org);
  if (!chosen && me.memberships.length > 1) {
    const organizations = await Promise.all(
      me.memberships.map(async (m) => getOrganization(await apiContext(m.organization_id))),
    );
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Choose an organization</h1>
        <MyInvitations invitations={invitations} />
        <ul className="divide-y rounded-lg border">
          {organizations.map((o) => (
            <li key={o.id}>
              <Link href={`/workspace?org=${o.id}`} className="hover:bg-accent flex justify-between gap-4 px-4 py-3 text-sm">
                <span className="font-medium">{o.name}</span>
                <span className="text-muted-foreground capitalize">{o.role}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  const organizationId = (chosen ?? me.memberships[0]).organization_id;
  const organization = await getOrganization(await apiContext(organizationId));
  const members = await membersIfAllowed(organizationId);

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-3xl bg-neutral-950 p-6 text-white md:p-8">
        <ContainerArt className="pointer-events-none absolute -right-16 -bottom-24 hidden w-96 opacity-60 md:block" />
        <div className="relative max-w-lg">
          <p className="text-xs font-semibold tracking-widest text-orange-400 uppercase">Workspace</p>
          <h1 className="font-display mt-2 text-3xl font-semibold tracking-tight text-balance md:text-4xl">{organization.name}</h1>
          <p className="mt-1 text-sm text-neutral-300">Signed in as {me.email}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href={`/workspace/shipments?org=${organizationId}`} className={buttonVariants({ size: "lg" })}>
              Start a check
              <ArrowRight aria-hidden className="size-4" />
            </Link>
            <Link
              href={`/workspace/intake?org=${organizationId}`}
              className={`${buttonVariants({ size: "lg", variant: "outline" })} !border-neutral-500 !bg-transparent text-white hover:!bg-neutral-800 hover:text-white`}
            >
              Upload a batch
            </Link>
          </div>
        </div>
      </header>

      <MyInvitations invitations={invitations} />

      <Card>
        <CardHeader>
          <CardTitle>Your access</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-8 text-sm">
          <div>
            <p className="text-muted-foreground">Role</p>
            <p className="font-medium capitalize">{organization.role}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Plan</p>
            <p className="font-medium capitalize">{organization.plan}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Team</CardTitle>
        </CardHeader>
        <CardContent>
          {members === null ? (
            <p className="text-muted-foreground text-sm">Only supervisors and admins can see the team list.</p>
          ) : (
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
                      <TableCell>
                        <Badge variant="secondary" className="capitalize">
                          {member.role}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
