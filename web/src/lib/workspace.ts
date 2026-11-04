import "server-only";

import { redirect } from "next/navigation";

import { getMe } from "./api";
import { apiContext } from "./server-api";

/** The organization for this page. No choice to make yet? The workspace page handles creating or choosing one. */
export async function organizationFor(org: string | undefined) {
  const me = await getMe(await apiContext());
  const chosen = me.memberships.find((m) => m.organization_id === org);
  if (!chosen && me.memberships.length !== 1) redirect("/workspace");
  const organizationId = (chosen ?? me.memberships[0]).organization_id;
  return { organizationId, role: (chosen ?? me.memberships[0]).role, context: await apiContext(organizationId) };
}
