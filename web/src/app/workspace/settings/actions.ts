"use server";

import { revalidatePath } from "next/cache";

import { addMember, ApiError, changeRole, removeMember, renameOrganization, type Role, setApprovalSteps, setRetention } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

export type SettingsFormState = { error: string | null; saved: boolean };

const ROLES: Role[] = ["admin", "supervisor", "clerk"];

function text(form: FormData, field: string): string {
  return String(form.get(field) ?? "").trim();
}

function role(form: FormData): Role | null {
  const value = text(form, "role") as Role;
  return ROLES.includes(value) ? value : null;
}

/** The API has the final say on every action. These messages only explain its answer. */
function message(error: unknown, conflict: string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Only admins can do this.";
    if (error.status === 409) return conflict;
  }
  return "That didn't work. Try again.";
}

async function run(form: FormData, call: (organizationId: string) => Promise<unknown>, conflict: string) {
  try {
    await call(text(form, "organization"));
  } catch (error) {
    return { error: message(error, conflict), saved: false };
  }
  revalidatePath("/workspace", "layout");
  return { error: null, saved: true };
}

export async function renameAction(_: SettingsFormState, form: FormData): Promise<SettingsFormState> {
  const name = text(form, "name");
  if (!name) return { error: "Enter a name.", saved: false };
  return run(form, async (id) => renameOrganization(await apiContext(id), name), "That name can't be used.");
}

const APPROVAL_CHOICES: Record<string, Role[]> = {
  supervisor: ["supervisor"],
  admin: ["admin"],
  both: ["supervisor", "admin"],
};

export async function approvalStepsAction(_: SettingsFormState, form: FormData): Promise<SettingsFormState> {
  const steps = APPROVAL_CHOICES[text(form, "steps")];
  if (!steps) return { error: "Choose who approves.", saved: false };
  return run(form, async (id) => setApprovalSteps(await apiContext(id), steps), "That choice can't be used.");
}

export async function retentionAction(_: SettingsFormState, form: FormData): Promise<SettingsFormState> {
  const value = text(form, "days");
  const days = value === "" ? null : Number(value);
  if (days !== null && (!Number.isInteger(days) || days < 7 || days > 3650)) {
    return { error: "Enter a whole number from 7 to 3650, or leave it empty.", saved: false };
  }
  return run(form, async (id) => setRetention(await apiContext(id), days), "That number can't be used.");
}

export async function addMemberAction(_: SettingsFormState, form: FormData): Promise<SettingsFormState> {
  const email = text(form, "email");
  const newRole = role(form);
  if (!email.includes("@") || !newRole) return { error: "Enter an email and choose a role.", saved: false };
  try {
    await addMember(await apiContext(text(form, "organization")), email, newRole);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { error: "We can't add this person yet. Ask them to sign in once, then try again.", saved: false };
    }
    return { error: message(error, "This person is already a member."), saved: false };
  }
  revalidatePath("/workspace", "layout");
  return { error: null, saved: true };
}

export async function changeRoleAction(_: SettingsFormState, form: FormData): Promise<SettingsFormState> {
  const newRole = role(form);
  if (!newRole) return { error: "Choose a role.", saved: false };
  return run(
    form,
    async (id) => changeRole(await apiContext(id), text(form, "user"), newRole),
    "An organization needs at least one admin.",
  );
}

export async function removeMemberAction(_: SettingsFormState, form: FormData): Promise<SettingsFormState> {
  return run(
    form,
    async (id) => removeMember(await apiContext(id), text(form, "user")),
    "This person can't be removed: they may be the last admin, or have recorded reviews.",
  );
}
