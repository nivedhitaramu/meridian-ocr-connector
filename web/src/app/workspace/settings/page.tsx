import { redirect } from "next/navigation";

import { ApiError, getMe, getOrganization, getUsage, listAuditEvents, listInvitations, listMembers } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

import { SettingsView } from "./settings-view";

export const metadata = { title: "Settings | Meridian Intelligence" };

/** A section this person's role can't see comes back as null, and the API decides that. */
async function ifAllowed<T>(load: () => Promise<T>): Promise<T | null> {
  try {
    return await load();
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) return null;
    throw error;
  }
}

export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const me = await getMe(await apiContext());
  const chosen = me.memberships.find((m) => m.organization_id === org);
  if (!chosen && me.memberships.length !== 1) redirect("/workspace"); // create or choose an organization there

  const organizationId = (chosen ?? me.memberships[0]).organization_id;
  const context = await apiContext(organizationId);
  const [organization, members, invitations, events, usage] = await Promise.all([
    getOrganization(context),
    ifAllowed(() => listMembers(context)),
    ifAllowed(() => listInvitations(context)),
    ifAllowed(() => listAuditEvents(context)),
    ifAllowed(() => getUsage(context)),
  ]);
  return <SettingsView organization={organization} members={members} invitations={invitations} events={events} usage={usage} />;
}
