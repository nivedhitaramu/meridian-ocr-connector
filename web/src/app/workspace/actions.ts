"use server";

import { revalidatePath } from "next/cache";

import { createOrganization } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

export type FormState = { error: string | null };

export async function startOrganization(_: FormState, form: FormData): Promise<FormState> {
  const name = String(form.get("name") ?? "").trim();
  if (!name) return { error: "Enter a name for your organization." };
  try {
    await createOrganization(await apiContext(), name);
  } catch {
    return { error: "We couldn't create your organization. Try again." };
  }
  revalidatePath("/workspace");
  return { error: null };
}
