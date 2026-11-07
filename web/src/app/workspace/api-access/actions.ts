"use server";

import { revalidatePath } from "next/cache";

import { addWebhook, ApiError, createApiKey, removeWebhook, revokeApiKey, rotateApiKey } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

/** A secret travels only in this one response and is never stored in the website. */
export type AccessState = { error: string | null; secret: string | null };

const text = (form: FormData, field: string) => String(form.get(field) ?? "").trim();
const context = (form: FormData) => apiContext(text(form, "organization"));

function done(secret: string | null = null): AccessState {
  revalidatePath("/workspace/api-access");
  return { error: null, secret };
}

const failed = (message: string): AccessState => ({ error: message, secret: null });

export async function createKeyAction(_: AccessState, form: FormData): Promise<AccessState> {
  const name = text(form, "name");
  if (!name) return failed("Name this key.");
  try {
    return done((await createApiKey(await context(form), name)).key);
  } catch {
    return failed("We couldn't create this key. Try again.");
  }
}

export async function rotateKeyAction(_: AccessState, form: FormData): Promise<AccessState> {
  try {
    return done((await rotateApiKey(await context(form), text(form, "id"))).key);
  } catch {
    return failed("We couldn't replace this key. Try again.");
  }
}

export async function revokeKeyAction(_: AccessState, form: FormData): Promise<AccessState> {
  try {
    await revokeApiKey(await context(form), text(form, "id"));
    return done();
  } catch {
    return failed("We couldn't revoke this key. Try again.");
  }
}

export async function addWebhookAction(_: AccessState, form: FormData): Promise<AccessState> {
  try {
    const format = text(form, "format") === "wms_receipt" ? "wms_receipt" : "event";
    return done((await addWebhook(await context(form), text(form, "url"), format)).secret);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) return failed("Use a public HTTPS address.");
    return failed("We couldn't add this webhook. Try again.");
  }
}

export async function removeWebhookAction(_: AccessState, form: FormData): Promise<AccessState> {
  try {
    await removeWebhook(await context(form), text(form, "id"));
    return done();
  } catch {
    return failed("We couldn't remove this webhook. Try again.");
  }
}
