import Link from "next/link";

import { EmptyState } from "@/components/states";
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
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{organization.name}</h1>
        <p className="text-muted-foreground text-sm">Signed in as {me.email}</p>
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
