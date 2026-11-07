"use server";

import { acceptInvitation, createOrganization, declineInvitation } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

export type FormState = { error: string | null; reload?: boolean };

export async function startOrganization(_: FormState, form: FormData): Promise<FormState> {
  const name = String(form.get("name") ?? "").trim();
  if (!name) return { error: "Enter a name for your organization." };
  try {
    await createOrganization(await apiContext(), name);
  } catch {
    return { error: "We couldn't create your organization. Try again." };
  }
  return { error: null, reload: true }; // a full load, because updating in place could leave the page stuck
}

async function answer(form: FormData, call: typeof acceptInvitation | typeof declineInvitation): Promise<FormState> {
  try {
    await call(await apiContext(), String(form.get("invitation") ?? ""));
  } catch {
    return { error: "This invitation is no longer available." };
  }
  return { error: null, reload: true }; // the page loads again, with the new organization in place
}

export async function acceptInvitationAction(_: FormState, form: FormData): Promise<FormState> {
  return answer(form, acceptInvitation);
}

export async function declineInvitationAction(_: FormState, form: FormData): Promise<FormState> {
  return answer(form, declineInvitation);
}
